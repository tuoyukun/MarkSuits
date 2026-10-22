---
description: Bring this Mark project's files (config, and any role agents, prompts or formats it keeps) up to the installed Mark plugin, on a general lane the human reviews before it lands. Use when the human asks to upgrade Mark, or `mark status` / `mark next` say the project files are older than the plugin.
allowed-tools: Bash(mark:*)
---

!`mark rules`

## /mark:upgrade

`mark upgrade` merges the new template into the project's files three ways (the pristine copy
in `.mark/.base/`, the project's file, the new template) and commits the result on a general
lane. Main does not change until the human says to land it. Speak the human's language.

1. **Preview.** Run `mark upgrade --dry-run`. If it says there is nothing to upgrade or no
   record, tell the human and stop.
2. **Write the lane.** Run `mark upgrade`. It prints the branch, the worktree and one row per file.
3. **Resolve conflicts**, if any rows say CONFLICT. In the lane (absolute paths under the
   worktree, never the main checkout), open each file, keep what the project changed and add
   what the template changed, and remove every `<<<<<<<` / `=======` / `>>>>>>>` line. When the
   intent of either side is unclear, ask the human instead of guessing. Then commit in the lane:
   `git -C "<worktree>" add -A && git -C "<worktree>" commit -m "chore: resolve upgrade conflicts"`.
   Never edit `.mark/.base/` or `.mark/template.toml`; `mark upgrade` owns them.
4. **Module entry points.** When the upgrade adds `scripts/` (the merge check becomes
   `bash scripts/selftest.sh && bash scripts/regression.sh`), the lane cannot land until every
   existing module has its entry points. In the lane, write `selftest.sh` in the frontend and
   backend, `regression.sh` in the test directory, and `start.sh` / `stop.sh` in each module
   that runs a server, each wrapping the commands `CLAUDE.md` lists today; point the Commands
   section of `CLAUDE.md` at `scripts/`; run both scripts once; commit in the lane.
5. **Show the human** what the upgrade changes: the rows, `git -C "<worktree>" diff <main>...HEAD --stat`,
   and in plain words what changed in the files they edited (merged or resolved). Mention rows
   that say skipped: those files did not get the template's change. Rows that say kept are
   files the project edited that Mark now ships itself (role agents, prompts, formats): the
   project's copy overrides the built-in and stops receiving Mark's updates. Show the human
   how it differs from the built-in (`mark format <name>`, or the file under the plugin's
   `agents/` and `defaults/`) and suggest deleting it when the edit is no longer needed.
6. **The human decides.**
   - Land it: `mark general merge <branch>` (regression, fast-forward, push, lane removed).
     If it fails, main is unchanged and the lane is kept: report the reason and stop.
   - Not now: leave the lane; it can be landed later.
   - Discard it: only when the human says so, `mark general drop <branch> --force`.
