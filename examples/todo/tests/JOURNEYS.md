# End-to-end journeys

Every end-to-end test, one row each (format: `mark format journeys.md`). Planners extend the
test whose path already reaches a state before they add a new one.

<!-- mark:journeys -->
| test | file | path | covers |
|---|---|---|---|
| add a todo and it survives a reload | e2e/todo.spec.js | / → type a padded title → Add → listed, trimmed, input cleared → reload → still listed | baseline/add |
| blank input adds nothing | e2e/todo.spec.js | / → type spaces → Enter → empty hint stays | baseline/blank |
| delete removes a todo | e2e/todo.spec.js | / → add two → delete the first → only the second left | baseline/delete |
| empty list shows a hint | e2e/todo.spec.js | / → add one → delete it → empty hint | baseline/empty |
| toggle marks a todo done | e2e/todo.spec.js | / → add one → check it → marked done | baseline/toggle |
