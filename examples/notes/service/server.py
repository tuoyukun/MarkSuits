"""Notes service: a JSON API, nothing else.

    python3 service/server.py [--port 8000]

API
    GET    /api/notes          -> [note]
    POST   /api/notes          {text}   -> 201 note
    GET    /api/notes/<id>              -> note
    DELETE /api/notes/<id>              -> 204
Errors are {"error": "<message>"} with 400 (invalid input) or 404 (unknown id/route).
A note is {"id": int, "text": str}.
"""
from __future__ import annotations

import argparse
import json
import re
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from store import Invalid, NotFound, NoteStore

ITEM = re.compile(r"^/api/notes/(\d+)$")


class Handler(BaseHTTPRequestHandler):
    store: NoteStore

    def log_message(self, fmt: str, *args) -> None:  # keep test output quiet
        pass

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

    def _route(self, method: str) -> None:
        path = self.path.split("?", 1)[0]
        try:
            if path == "/api/notes" and method == "GET":
                return self._json(HTTPStatus.OK, self.store.list())
            if path == "/api/notes" and method == "POST":
                return self._json(HTTPStatus.CREATED, self.store.add(self._body().get("text")))
            match = ITEM.match(path)
            if match and method == "GET":
                return self._json(HTTPStatus.OK, self.store.get(int(match[1])))
            if match and method == "DELETE":
                self.store.delete(int(match[1]))
                return self._json(HTTPStatus.NO_CONTENT)
            self._json(HTTPStatus.NOT_FOUND, {"error": "no such route"})
        except Invalid as exc:
            self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except NotFound:
            self._json(HTTPStatus.NOT_FOUND, {"error": "no such note"})

    def do_GET(self) -> None:
        self._route("GET")

    def do_POST(self) -> None:
        self._route("POST")

    def do_DELETE(self) -> None:
        self._route("DELETE")


def make_server(port: int, store: NoteStore | None = None) -> ThreadingHTTPServer:
    handler = type("BoundHandler", (Handler,), {"store": store or NoteStore()})
    return ThreadingHTTPServer(("127.0.0.1", port), handler)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    server = make_server(args.port)
    print(f"notes: http://127.0.0.1:{args.port}/api/notes", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
