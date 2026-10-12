"""Mock server for manual testing of ContextCheck (standard library only).

Run it in its own terminal:

    python examples/manual_testing/mock_server.py                    # normal RAG
    python examples/manual_testing/mock_server.py --empty-retriever  # retriever returns nothing

Routes (POST, JSON body). Any route accepts `?delay=<seconds>` to slow the answer down.
    /echo           -> {"message": <message or prompt of the request>}
    /qa             -> {"message": <RAG answer>}  (knows the capitals of Poland and France)
    /slow           -> like /echo but waits --slow-seconds (default 35 s, above the 30 s timeout)
    /status/<code>  -> empty answer with HTTP status <code> (e.g. /status/500, /status/429)
    /int            -> {"message": 42}  (wrong type)
GET /health         -> {"status": "ok"}  (open it in a browser to check the server is up)
"""

import argparse
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

KNOWLEDGE_BASE = {
    "poland": "Warsaw is the capital of Poland.",
    "france": "Paris is the capital of France.",
}
NO_ANSWER = "I don't know."


def make_handler(options):
    class Handler(BaseHTTPRequestHandler):
        def _reply(self, status: int, payload: dict):
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if urlparse(self.path).path == "/health":
                self._reply(200, {"status": "ok", "empty_retriever": options.empty_retriever})
            else:
                self._reply(404, {"error": "not found"})

        def do_POST(self):
            url = urlparse(self.path)
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length) or b"{}")
            text = body.get("message") or body.get("prompt") or body.get("query") or ""
            time.sleep(float(parse_qs(url.query).get("delay", ["0"])[0]))

            if url.path == "/echo":
                self._reply(200, {"message": text})
            elif url.path == "/qa":
                self._reply(200, {"message": self._answer(text)})
            elif url.path == "/slow":
                time.sleep(options.slow_seconds)
                self._reply(200, {"message": text})
            elif url.path.startswith("/status/"):
                code = int(url.path.rsplit("/", 1)[-1])
                self._reply(code, {"error": f"simulated HTTP {code}"})
            elif url.path == "/int":
                self._reply(200, {"message": 42})
            else:
                self._reply(404, {"error": "not found"})

        def _answer(self, question: str) -> str:
            if options.empty_retriever:
                return NO_ANSWER
            for key, answer in KNOWLEDGE_BASE.items():
                if key in question.lower():
                    return answer
            return NO_ANSWER

    return Handler


class Server(ThreadingHTTPServer):
    request_queue_size = 128  # Enough for the 50-request concurrency test
    daemon_threads = True


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--empty-retriever", action="store_true", help="RAG finds no documents")
    parser.add_argument("--slow-seconds", type=float, default=35.0)
    options = parser.parse_args()

    server = Server(("127.0.0.1", options.port), make_handler(options))
    mode = "EMPTY retriever" if options.empty_retriever else "normal retriever"
    print(f"Mock server on http://127.0.0.1:{options.port} ({mode}). Ctrl+C to stop.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
