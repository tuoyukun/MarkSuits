# End-to-end journeys

The core-flow regression journeys, one row each (format: `mark format journeys.md`).
Acceptance tests live in `e2e/tickets/<id>/` and are not listed.

<!-- mark:journeys -->
| test | file | path | covers |
|---|---|---|---|
| add a todo and it survives a reload | regression/todo.spec.js | / → type a padded title → Add → listed, trimmed, input cleared → reload → still listed | baseline/add |
| blank input adds nothing | regression/todo.spec.js | / → type spaces → Enter → empty hint stays | baseline/blank |
| delete removes a todo | regression/todo.spec.js | / → add two → delete the first → only the second left | baseline/delete |
| empty list shows a hint | regression/todo.spec.js | / → add one → delete it → empty hint | baseline/empty |
| toggle marks a todo done | regression/todo.spec.js | / → add one → check it → marked done | baseline/toggle |
