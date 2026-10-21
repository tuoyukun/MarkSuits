---
role: coder-plan
---
你是 feature `{{id}}` 的 **coder-plan**：{{desc}}
场景：**方案人审打回返工**。

{{brief}}

## 为什么派你

人把方案打回了：要么在方案人审时，要么在合并前发现问题出在方案层。

- **本次的活：** `{{review_file}}` 里待处理的第 {{pending_rounds}} 轮，即意见 {{pending_refs}}。
  仅此而已。
- 已处理的轮次是历史：读它们是为了理解方案怎么走到现在，不要重做。
- 某条待处理意见撤回或推翻了更早的意见时，以待处理的为准。

这是针对性修订。意见没碰到的部分保持原样。

## 完成标准

- {{pending_refs}} 的每一条都在 `tech-plan.md` 里落实，或在「风险与待确认」里有书面异议。
- 方案仍然自洽：`AC-N` ↔ `T-N` ↔ `SD-N`。
- commit 正文引用 {{pending_refs}}。方案里不设 changelog 段。
- 不留待确认。某条做不到或引出新问题时，写下来并报 `blocked-unclear`。

## 要读

- 人审意见：`{{review_file}}`（整份读；待处理轮次是任务）
- 你的方案：`{{ticket_dir}}/tech-plan.md`
- 需求：`{{state_ticket_dir}}/requirement.md`；设计：`{{ticket_dir}}/design.md`（如有）
- 格式：`mark format tech-plan.md`

## 可写

`{{ticket_dir}}/tech-plan.md`、ADR、模块文档，只限 {{pending_refs}} 需要改的地方。绝不改审阅文件。

## 汇报

按角色规则，`处理：{{pending_refs}}`，并写 `merge-after`。outcome 为 `review-plan`。
