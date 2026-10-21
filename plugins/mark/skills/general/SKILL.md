---
description: Make a small change that belongs to no ticket (docs, prompts, config, other non-code files) on a throwaway lane, and land it through the regression. Use when the human asks for such a change in a Mark project.
argument-hint: <what to change>
allowed-tools: Bash(mark:*)
---

!`mark rules`

## /mark:general

Argument: `$ARGUMENTS`

General mode is for changes outside the pipeline: docs, prompts, role files, config. No
ticket, no subagents, no review gates. You edit the files yourself, on a throwaway lane.

1. **Check it fits.** If the change touches code, tests or UI, or makes an architecture
   decision, it is not general work: say so and suggest `/mark:fix` or `/mark:feature`, then
   stop. Write scopes enforce the same line; a `[BLOCKED]` on a code path means you are here.
2. **Agree on the change** with the human when it is not obvious from the request.
3. **Open a lane.** `mark general new` prints the branch and worktree.
4. **Edit in the lane** with absolute paths under that worktree, never in the main checkout.
5. **Commit in the lane**: `git -C "<worktree>" add -A && git -C "<worktree>" commit -m "<message>"`.
6. **Land it.** `mark general merge <branch>` merges the latest main in, runs the project's
   regression, fast-forwards main, pushes and removes the lane. Run it in the background if
   the regression is slow.
7. **Report** what changed in plain words. If the merge failed, main was not changed and the
   lane is kept: report the reason and stop; do not merge by hand.
