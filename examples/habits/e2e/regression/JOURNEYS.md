# End-to-end journeys

The core-flow regression journeys, one row each (format: `mark format journeys.md`).
Acceptance tests live in `e2e/tickets/<id>/` and are not listed.

<!-- mark:journeys -->
| test | file | path | covers |
|---|---|---|---|
| add a habit | regression/add-habit.yaml | open app → type a name → Add → card listed with "No streak yet" | baseline/add |
| check-ins build a streak | regression/check-in-streak.yaml | add a habit → tap yesterday and today → "2-day streak" → untap today → "1-day streak" | baseline/streak, baseline/undo |
