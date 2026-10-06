"""A small in-process HTTP server that imitates a RAG API for integration tests.

It implements the routes used by `ContextClueApiWrapper` (documents, semantic search, QA) and
an extra `/cc/qa` route returning `{"message": ...}` so it can be used as a `cc_prompt_llm`
endpoint under test.
"""

import json
import random
import threading
import time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

KNOWLEDGE_BASE = {
    "poland": ("Warsaw is the capital of Poland.", "Poland is a country. Its capital is Warsaw."),
    "france": ("Paris is the capital of France.", "France is a country. Its capital is Paris."),
}
NO_ANSWER = "I don't know."


class MockRagState:
    def __init__(self):
        self.documents = [{"id": "1", "name": "Geography"}]
        self.chunks = [chunk for _, chunk in KNOWLEDGE_BASE.values()] * 5
        self.retriever_empty = False  # Simulates a retriever returning no documents
        self.delay = (0.0, 0.0)  # Random per-request latency range in seconds
        self.lock = threading.Lock()
        self.active = 0
        self.max_active = 0
        self.requests = 0

    def retrieve(self, query: str) -> list[dict]:
        if self.retriever_empty:
            return []
        return [
            {"chunk": chunk, "metadata": {"document_name": "Geography"}}
            for key, (_, chunk) in KNOWLEDGE_BASE.items()
            if key in query.lower()
        ]

    def answer(self, query: str) -> str:
        if self.retriever_empty:
            return NO_ANSWER
        for key, (answer, _) in KNOWLEDGE_BASE.items():
            if key in query.lower():
                return answer
        return NO_ANSWER


def _make_handler(state: MockRagState):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _reply(self, payload: dict, status: int = 200):
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _track(self, handler):
            with state.lock:
                state.requests += 1
                state.active += 1
                state.max_active = max(state.max_active, state.active)
            try:
                time.sleep(random.uniform(*state.delay))
                handler()
            finally:
                with state.lock:
                    state.active -= 1

        def do_GET(self):
            def handle():
                parts = [p for p in self.path.split("/") if p]
                if parts == ["documents"]:
                    self._reply({"documents": state.documents})
                elif len(parts) == 2 and parts[0] == "documents":
                    self._reply({"document": {"chunks": state.chunks}})
                else:
                    self._reply({"error": "not found"}, status=404)

            self._track(handle)

        def do_POST(self):
            def handle():
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])) or b"{}")
                query = body.get("query") or body.get("prompt") or ""
                if self.path == "/semantic_search/get_relevant_documents":
                    entries = state.retrieve(query)
                    self._reply({"relevant_documents": {"collection_retriever_entries": entries}})
                elif self.path == "/qa/ask":
                    self._reply(
                        {
                            "result": state.answer(query),
                            "relevant_documents": {
                                "collection_retriever_entries": state.retrieve(query)
                            },
                        }
                    )
                elif self.path == "/cc/qa":
                    self._reply({"message": state.answer(query)})
                elif self.path == "/echo":
                    self._reply({"message": query})
                else:
                    self._reply({"error": "not found"}, status=404)

            self._track(handle)

    return Handler


class _Server(ThreadingHTTPServer):
    # The default backlog (5) resets connections when many clients connect at once
    request_queue_size = 128
    daemon_threads = True


@contextmanager
def run_mock_rag_server():
    """Start the mock server on a free port; yields (base_url, state)."""
    state = MockRagState()
    server = _Server(("127.0.0.1", 0), _make_handler(state))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}", state
    finally:
        server.shutdown()
        server.server_close()
