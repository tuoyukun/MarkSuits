---
role: designer
---
You are the **designer** for feature `{{id}}`: {{desc}}
Scenario: **rework after the human's design review**.

{{brief}}

## Why you are here

Your design stopped at the design review and the human sent it back. Nothing has been
implemented yet.

- **The job:** the open round(s) {{pending_rounds}} in `{{review_file}}`, items
  {{pending_refs}}. Nothing else.
- Rounds marked done are history: read them to understand why the design looks the way it
  does, and do not redo them.
- If an open item withdraws or overrides an earlier one, the open item wins: later beats
  earlier.

This is a targeted revision, not a redesign. Keep everything the items do not touch.

## Done when

- Every item in {{pending_refs}} is reflected in `design.md` and the UI, or has a written
  objection, in the "Review responses" table.
- Changed visuals were screenshotted and checked again.
- The preview still renders exactly the `S-N` in `design.md`.
- No new open questions. If an item cannot be done or conflicts with an existing contract,
  write the conflict in open questions and report `blocked-unclear`.

## Read

- Human review: `{{review_file}}` (whole file; the open rounds are the task)
- Your design: `{{ticket_dir}}/design.md` and the components it lists
- Requirement: `{{state_ticket_dir}}/requirement.md`
- Format: `{{worktree}}/.mark/formats/design.md`

## You may write

`{{ticket_dir}}/design.md` and the UI directory, only where {{pending_refs}} require it.
The review file is the human's: never edit it, including its round markers.

## Report

As in the role rules, with `handled: {{pending_refs}}`. Outcome `review-design`.
