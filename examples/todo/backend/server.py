"""Todo app server: JSON API under /api, static frontend for everything else.

    python3 backend/server.py [--port 8000]

API
    GET    /api/todos          -> [todo]
    POST   /api/todos          {title}            -> 201 todo
    PATCH  /api/todos/<id>     {title?, done?}    -> todo
    DELETE /api/todos/<id>                        -> 204
Errors are {"error": "<message>"} with 400 (invalid input) or 404 (unknown id/route).
A todo is {"id": int, "title": str, "done": bool}.
"""
from __future__ import annotations

import argparse
import json
import re
from functools import partial
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from store import Invalid, NotFound, TodoStore

FRONTEND = Path(__file__).resolve().parent.parent / "frontend"
ITEM = re.compile(r"^/api/todos/(\d+)$")


class Handler(SimpleHTTPRequestHandler):
    store: TodoStore

    def log_message(self, fmt: str, *args) -> None:  # keep test output quiet
        pass

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    # --- helpers -----------------------------------------------------------
    def _json(self, status: int, body: object = None) -> None:
        data = b"" if body is None else json.dumps(body).encode()
        self.send_response(status)
        if body is not None:
            self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        try:
            data = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            raise Invalid("body must be JSON") from None
        if not isinstance(data, dict):
            raise Invalid("body must be a JSON object")
        return data

    def _api(self, method: str) -> None:
        path = self.path.split("?", 1)[0]
        try:
            if path == "/api/todos" and method == "GET":
                return self._json(HTTPStatus.OK, self.store.list())
            if path == "/api/todos" and method == "POST":
                return self._json(HTTPStatus.CREATED, self.store.add(self._body().get("title")))
            match = ITEM.match(path)
            if match and method == "PATCH":
                return self._json(HTTPStatus.OK, self.store.update(int(match[1]), self._body()))
            if match and method == "DELETE":
                self.store.delete(int(match[1]))
                return self._json(HTTPStatus.NO_CONTENT)
            self._json(HTTPStatus.NOT_FOUND, {"error": "no such route"})
        except Invalid as exc:
            self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except NotFound:
            self._json(HTTPStatus.NOT_FOUND, {"error": "no such todo"})

    # --- verbs -------------------------------------------------------------
    def do_GET(self) -> None:
        if self.path.startswith("/api/"):
            return self._api("GET")
        super().do_GET()

    def do_POST(self) -> None:
        self._api("POST")

    def do_PATCH(self) -> None:
        self._api("PATCH")

    def do_DELETE(self) -> None:
        self._api("DELETE")


def make_server(port: int, store: TodoStore | None = None) -> ThreadingHTTPServer:
    handler = type("BoundHandler", (Handler,), {"store": store or TodoStore()})
    return ThreadingHTTPServer(("127.0.0.1", port), partial(handler, directory=str(FRONTEND)))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    server = make_server(args.port)
    print(f"todo: http://127.0.0.1:{args.port}/  (UI preview: /src/ui/preview.html)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
