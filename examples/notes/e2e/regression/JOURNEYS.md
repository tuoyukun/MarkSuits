# End-to-end journeys

The core-flow regression journeys, one row each (format: `mark format journeys.md`).
Acceptance tests live in `e2e/tickets/<id>/` and are not listed.

<!-- mark:journeys -->
| test | file | path | covers |
|---|---|---|---|
| test_create_read_and_list_a_note | regression/test_notes.py | POST a padded text → 201, trimmed → GET by id → GET list | baseline/create |
| test_blank_text_is_refused | regression/test_notes.py | POST blank text → 400 with error → list still empty | baseline/blank |
| test_delete_removes_a_note | regression/test_notes.py | POST two → DELETE the first → GET it 404 → list has only the second | baseline/delete |
