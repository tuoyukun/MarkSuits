# End-to-end journeys

Every end-to-end test, one row each (format: `mark format journeys.md`). Planners extend the
test whose path already reaches a state before they add a new one.

<!-- mark:journeys -->
| test | file | path | covers |
|---|---|---|---|
| add a habit | add-habit.yaml | open app → type a name → Add → card listed with "No streak yet" | baseline/add |
| check-ins build a streak | check-in-streak.yaml | add a habit → tap yesterday and today → "2-day streak" → untap today → "1-day streak" | baseline/streak, baseline/undo |
