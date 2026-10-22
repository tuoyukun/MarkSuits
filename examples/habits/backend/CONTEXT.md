# backend

- `server.py`: HTTP server. `/api/habits` routes (contract in the module docstring). Errors
  are `{"error": "..."}` with 400 or 404.
- `store.py`: `HabitStore`, an in-memory dict guarded by a lock. `today()` honours
  `HABITS_TODAY`; `streak` counts consecutive checked-in days ending today or yesterday;
  a check-in may be toggled only within the last 7 days.
- `test_store.py`: unit tests for the streak, the store and the routes (real server on a free port).
