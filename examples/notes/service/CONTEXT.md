# service

- `server.py`: HTTP server. `/api/notes` routes (contract in the module docstring). Errors
  are `{"error": "..."}` with 400 or 404.
- `store.py`: `NoteStore`, an in-memory dict guarded by a lock. `clean_text` strips and
  enforces 1–1000 characters. Reads return copies.
- `test_store.py`: unit tests for the store and the routes (real server on a free port).
