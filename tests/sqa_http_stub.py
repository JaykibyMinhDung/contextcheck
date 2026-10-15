"""Configurable HTTP stub used by the SQA test suites.

Each route maps to a function `body -> (status_code, json_payload, delay_seconds)`. Every
received request is recorded so tests can assert on payloads, headers and retry counts.
"""

import json
import threading
import time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class StubState:
    def __init__(self, routes: dict):
        self.routes = routes
        self.received: list[dict] = []
        self.lock = threading.Lock()

    def hits(self, path: str) -> list[dict]:
        with self.lock:
            return [r for r in self.received if r["path"] == path]


def echo(body: dict):
    return 200, {"message": body.get("message")}, 0


def status(code: int):
    return lambda body: (code, {"error": f"HTTP {code}"}, 0)


def slow(seconds: float):
    return lambda body: (200, {"message": "late"}, seconds)


def fixed(payload: dict):
    return lambda body: (200, payload, 0)


def _make_handler(state: StubState):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            raw = self.rfile.read(int(self.headers.get("Content-Length", 0)) or 0)
            body = json.loads(raw or b"{}")
            with state.lock:
                state.received.append(
                    {"path": self.path, "body": body, "headers": dict(self.headers)}
                )
            route = state.routes.get(self.path)
            code, payload, delay = route(body) if route else (404, {"error": "not found"}, 0)
            time.sleep(delay)
            out = json.dumps(payload).encode()
            try:
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(out)))
                self.end_headers()
                self.wfile.write(out)
            except (BrokenPipeError, ConnectionResetError):
                pass  # Client gave up (e.g. timeout)

    return Handler


class _Server(ThreadingHTTPServer):
    request_queue_size = 128
    daemon_threads = True


@contextmanager
def run_stub(routes: dict):
    """Start the stub on a free port; yields (base_url, state)."""
    state = StubState(routes)
    server = _Server(("127.0.0.1", 0), _make_handler(state))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}", state
    finally:
        server.shutdown()
        server.server_close()
