# End-to-end journeys

The core-flow regression journeys, one row each (format: `mark format journeys.md`).
Acceptance tests live in `e2e/tickets/<id>/` and are not listed.

<!-- mark:journeys -->
| test | file | path | covers |
|---|---|---|---|
| add a counter | regression/add-counter.yaml | open app → type a name → Add → card listed at 0 | baseline/add |
| count up and down | regression/count-up-down.yaml | add a counter → + twice → 2 → − three times → 0 (never below) | baseline/count, baseline/floor |
