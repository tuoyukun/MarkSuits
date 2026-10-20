# backend

- `server.py`: HTTP server. `/api/todos` routes (contract in the module docstring), static
  files from `frontend/` for everything else. Errors are `{"error": "..."}` with 400 or 404.
- `store.py`: `TodoStore`, an in-memory list guarded by a lock. `clean_title` collapses
  whitespace and enforces 1–200 characters. Reads return copies.
- `test_store.py`: unit tests for the store and the API (real server on a random port).
