# End-to-end journeys

Every end-to-end test, one row each (format: `mark format journeys.md`). Planners extend the
test whose path already reaches a state before they add a new one.

<!-- mark:journeys -->
| test | file | path | covers |
|---|---|---|---|
| add expenses, the total sums them and survives a reload | e2e/expenses.spec.js | / → add Lunch 12 → add Train 30 → listed, total 42.00, inputs cleared → reload → still listed, total 42.00 | baseline/add |
| an invalid amount is refused and kept for correction | e2e/expenses.spec.js | / → add Lunch "abc" → error shown, amount kept, list empty | baseline/invalid |
| delete removes one expense and updates the total | e2e/expenses.spec.js | / → add a 5, b 7 → delete a → only b, total 7.00 | baseline/delete |
| empty list shows a hint and a zero total | e2e/expenses.spec.js | / → add one → delete it → empty hint, total 0.00 | baseline/empty |
