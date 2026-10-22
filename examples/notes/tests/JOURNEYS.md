# End-to-end journeys

Every end-to-end test, one row each (format: `mark format journeys.md`). Planners extend the
test whose path already reaches a state before they add a new one.

<!-- mark:journeys -->
| test | file | path | covers |
|---|---|---|---|
| test_create_read_and_list_a_note | e2e/test_notes.py | POST a padded text → 201, trimmed → GET by id → GET list | baseline/create |
| test_blank_text_is_refused | e2e/test_notes.py | POST blank text → 400 with error → list still empty | baseline/blank |
| test_delete_removes_a_note | e2e/test_notes.py | POST two → DELETE the first → GET it 404 → list has only the second | baseline/delete |
