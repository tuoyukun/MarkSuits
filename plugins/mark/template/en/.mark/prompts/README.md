# Dispatch prompt templates

`mark dispatch <id>` picks one of these files, fills it with facts it has verified, and
prints the prompt the orchestrator passes to the role agent unchanged. Nobody writes a
dispatch prompt by hand: a stateless agent gets everything it needs from this file plus the
brief, every time, in the same shape.

## Scenarios

| template | role | when (`mark next` decides) |
|---|---|---|
| `designer-initial` | designer | `designing`, no design review pending, no downstream finding |
| `designer-review-rework` | designer | `designing` with open rounds in `review-design.md` |
| `designer-rework` | designer | `designing` after a verdict or design QA sent the design back |
| `designer-integration-qa` | designer | `design-qa` |
| `coder-plan` | coder-plan | feature `planning`, no open plan or merge review |
| `coder-plan-rework` | coder-plan | feature `planning` with open rounds in `review-plan.md` or `review-merge.md` |
| `fix-plan-initial` | fix-plan | bug `planning`, no plan yet |
| `fix-plan-rework` | fix-plan | bug `planning` with a plan (after `blocked-plan`) or open merge review rounds |
| `coder-impl` | coder-impl | `developing` |
| `coder-impl-fix` | coder-impl | `failed-impl` from a verdict (`FAIL-N`) or design QA (`D-N`) |
| `coder-impl-merge-rework` | coder-impl | `failed-impl` with open rounds in `review-merge.md` |
| `tester-initial` | tester | `testing`, no verdict yet |
| `tester-reverify` | tester | `testing` with an earlier verdict |

## File shape

```markdown
---
role: designer            # must match the role the step needs (checked)
outputs: design-qa.md     # optional: overrides [outputs] in config.toml for this scenario
---
Body with {{placeholders}}.
```

## Placeholders

| placeholder | value |
|---|---|
| `{{id}}`, `{{kind}}`, `{{desc}}`, `{{status}}` | ticket id, `feature`/`bug`, description, status |
| `{{role}}`, `{{scenario}}` | the role and this template's name |
| `{{worktree}}`, `{{branch}}` | the ticket's worktree (absolute) and branch |
| `{{ticket_dir}}` | ticket dir in the worktree: where the role writes |
| `{{state_ticket_dir}}` | ticket dir on main: requirement, bug report, reviews (read only) |
| `{{outputs}}` | files the role must leave |
| `{{trigger}}` | what this dispatch answers (`R-N`, `FAIL-N`, `D-N` and the file) |
| `{{prev}}` | the previous step's conclusion, verbatim |
| `{{review_file}}`, `{{pending_rounds}}`, `{{pending_refs}}` | review file with open rounds, their numbers and item ids |
| `{{brief}}` | the verified brief (put at the top if the template does not place it) |

An unknown placeholder is an error at dispatch time, so a typo never reaches an agent.

## Rules for editing

- Say **what** is wrong and where the boundaries are; never **how** to fix it. The fix is
  the role's judgement.
- Durable rules belong in the role file (`.claude/agents/<role>.md`); a template holds only
  what is specific to its scenario.
- Templates are project files: change them as you learn, and explain why in the commit
  message.
