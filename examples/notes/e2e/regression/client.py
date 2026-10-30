"""A tiny HTTP client for the end-to-end tests: the service is reached only over HTTP."""
import json
import os
import urllib.error
import urllib.request

BASE = os.environ.get("NOTES_URL", "http://127.0.0.1:8000")


def call(method: str, path: str, body: object = None) -> tuple[int, object]:
    """(status, decoded JSON body or None)."""
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as res:
            raw = res.read()
            return res.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as err:
        with err:
            raw = err.read()
            return err.code, json.loads(raw) if raw else None


def clear() -> None:
    """Delete every note, through the API, so each test starts from an empty service."""
    for note in call("GET", "/api/notes")[1]:
        call("DELETE", f"/api/notes/{note['id']}")
