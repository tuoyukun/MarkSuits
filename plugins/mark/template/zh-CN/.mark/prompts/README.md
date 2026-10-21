# 派活模板

`mark dispatch <id>` 选出其中一份，用它核实过的事实填空，打印出 prompt；orchestrator 原样交给
角色 agent。没有人手写派活 prompt：无状态的 agent 每次都从这份模板加上开工简报拿到所需的一切，
而且形状始终一致。

## 场景

| 模板 | 角色 | 何时（由 `mark next` 判定） |
|---|---|---|
| `designer-initial` | designer | `designing`，没有待处理的设计人审，也没有下游发现 |
| `designer-review-rework` | designer | `designing`，且 `review-design.md` 有待处理轮次 |
| `designer-rework` | designer | `designing`，验收报告或设计验收把设计退了回来 |
| `designer-integration-qa` | designer | `design-qa` |
| `coder-plan` | coder-plan | feature `planning`，没有待处理的方案或合并审阅 |
| `coder-plan-rework` | coder-plan | feature `planning`，且 `review-plan.md` 或 `review-merge.md` 有待处理轮次 |
| `fix-plan-initial` | fix-plan | bug `planning`，还没有方案 |
| `fix-plan-rework` | fix-plan | bug `planning`，已有方案（`blocked-plan` 之后）或有待处理的合并审阅轮次 |
| `coder-impl` | coder-impl | `developing` |
| `coder-impl-fix` | coder-impl | `failed-impl`，来自验收报告（`FAIL-N`）或设计验收（`D-N`） |
| `coder-impl-merge-rework` | coder-impl | `failed-impl`，且 `review-merge.md` 有待处理轮次 |
| `tester-initial` | tester | `testing`，还没有验收报告 |
| `tester-reverify` | tester | `testing`，已有之前的验收报告 |

## 文件结构

```markdown
---
role: designer            # 必须与这一步需要的角色一致（会校验）
outputs: design-qa.md     # 可选：本场景覆盖 config.toml 里的 [outputs]
---
正文，含 {{占位符}}。
```

## 占位符

| 占位符 | 值 |
|---|---|
| `{{id}}`、`{{kind}}`、`{{desc}}`、`{{status}}` | 工单编号、`feature`/`bug`、描述、状态 |
| `{{role}}`、`{{scenario}}` | 角色，以及本模板名 |
| `{{worktree}}`、`{{branch}}` | 工单的 worktree（绝对路径）和分支 |
| `{{ticket_dir}}` | worktree 里的工单目录：角色写在这里 |
| `{{state_ticket_dir}}` | main 上的工单目录：需求、bug 报告、审阅意见（只读） |
| `{{outputs}}` | 角色必须留下的文件 |
| `{{trigger}}` | 这次派活回应什么（`R-N`、`FAIL-N`、`D-N` 及所在文件） |
| `{{prev}}` | 上一环的结论原话 |
| `{{review_file}}`、`{{pending_rounds}}`、`{{pending_refs}}` | 有待处理轮次的审阅文件、轮次号、意见编号 |
| `{{brief}}` | 核实过的开工简报（模板没放时自动置顶） |

未知占位符在派活时直接报错，拼写错误永远到不了 agent 手里。

## 修改规则

- 写**什么**有问题、边界在哪；绝不写**怎么**修。修法是角色的专业判断。
- 长期有效的规则放进角色文件（`.claude/agents/<role>.md`）；模板只放本场景特有的内容。
- 模板属于项目：跑出经验就改，在 commit 正文里说明原因。
