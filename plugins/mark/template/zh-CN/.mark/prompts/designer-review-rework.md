---
role: designer
---
你是 feature `{{id}}` 的 **designer**：{{desc}}
场景：**设计人审打回返工**。

{{brief}}

## 为什么派你

你的设计停在设计人审，人把它打回了。还没有开始实现。

- **本次的活：** `{{review_file}}` 里待处理的第 {{pending_rounds}} 轮，即意见 {{pending_refs}}。
  仅此而已。
- 已处理的轮次是历史：读它们是为了理解设计为什么长这样，不要重做。
- 某条待处理意见撤回或推翻了更早的意见时，以待处理的为准：后写的覆盖先写的。

这是针对性修订，不是重新设计。意见没碰到的部分保持原样。

## 完成标准

- {{pending_refs}} 的每一条都在 `design.md` 和 UI 里落实，或有书面异议，记在「人审回应」表里。
- 改过的视觉重新截图检查过。
- `{{ticket_dir}}/preview.html` 已按改过的组件重新构建。
- 预览渲染的仍恰好是 `design.md` 里的 `S-N`。
- 不新增待确认。某条做不到或与既有契约冲突时，把冲突写进待确认，报 `blocked-unclear`。

## 要读

- 人审意见：`{{review_file}}`（整份读；待处理轮次是任务）
- 你的设计：`{{ticket_dir}}/design.md` 及其列出的组件
- 需求：`{{state_ticket_dir}}/requirement.md`
- 格式：`{{worktree}}/.mark/formats/design.md`

## 可写

`{{ticket_dir}}/design.md`、`{{ticket_dir}}/preview.html` 和 UI 目录，只限 {{pending_refs}} 需要改的地方。审阅文件属于人：
绝不改它，包括轮次标记。

## 汇报

按角色规则，`处理：{{pending_refs}}`。outcome 为 `review-design`。
