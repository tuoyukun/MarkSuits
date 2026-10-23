# End-to-end journeys

Every end-to-end test, one row each (format: `mark format journeys.md`). Planners extend the
test whose path already reaches a state before they add a new one.

<!-- mark:journeys -->
| test | file | path | covers |
|---|---|---|---|
| add a counter | add-counter.yaml | open app → type a name → Add → card listed at 0 | baseline/add |
| count up and down | count-up-down.yaml | add a counter → + twice → 2 → − three times → 0 (never below) | baseline/count, baseline/floor |
