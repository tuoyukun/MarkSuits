"""Habits backend: a JSON API for the mobile app.

    python3 backend/server.py [--port 8300]

API
    GET  /api/habits                         -> {today, habits: [habit]}
    POST /api/habits              {name}     -> 201 habit
    POST /api/habits/<id>/toggle  {date}     -> habit (checks the day in, or clears it)
Errors are {"error": "<message>"} with 400 (invalid input) or 404 (unknown id/route).
A habit is {"id": int, "name": str, "days": ["YYYY-MM-DD", ...], "streak": int}.
`today` is the backend's date (HABITS_TODAY pins it); `date` must be within the last 7 days.
"""
from __future__ import annotations

import argparse
import json
import re
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from store import HabitStore, Invalid, NotFound

TOGGLE = re.compile(r"^/api/habits/(\d+)/toggle$")


class Handler(BaseHTTPRequestHandler):
    store: HabitStore

    def log_message(self, fmt: str, *args) -> None:  # keep test output quiet
        pass

    def _json(self, status: int, body: object) -> None:
        data = json.dumps(body).encode()
        self.send_response(status)
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
            if path == "/api/habits" and method == "GET":
                return self._json(HTTPStatus.OK, self.store.list())
            if path == "/api/habits" and method == "POST":
                return self._json(HTTPStatus.CREATED, self.store.add(self._body().get("name")))
            match = TOGGLE.match(path)
            if match and method == "POST":
                return self._json(HTTPStatus.OK, self.store.toggle(int(match[1]), self._body().get("date")))
            self._json(HTTPStatus.NOT_FOUND, {"error": "no such route"})
        except Invalid as exc:
            self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except NotFound:
            self._json(HTTPStatus.NOT_FOUND, {"error": "no such habit"})

    def do_GET(self) -> None:
        self._route("GET")

    def do_POST(self) -> None:
        self._route("POST")


def make_server(port: int, store: HabitStore | None = None) -> ThreadingHTTPServer:
    handler = type("BoundHandler", (Handler,), {"store": store or HabitStore()})
    # All interfaces: a phone or an Android emulator reaches it through the host's address.
    return ThreadingHTTPServer(("0.0.0.0", port), handler)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, default=8300)
    args = parser.parse_args()
    server = make_server(args.port)
    print(f"habits: http://127.0.0.1:{args.port}/api/habits", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
