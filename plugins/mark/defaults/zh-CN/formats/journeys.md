# 格式：JOURNEYS.md

`<tests>/JOURNEYS.md`（端到端测试目录）。由 tester 维护；coder-plan 和 fix-plan 读它，决定验收点扩展
哪个已有用例。每个端到端用例一行。

```markdown
# 端到端旅程

<!-- mark:journeys -->
| test | file | suite | path | covers |
|---|---|---|---|---|
| <用例的完整标题> | e2e/<文件> | acceptance | <入口> → <关键步骤> → <结果> | 0003/AC-1, 0007/AC-2 |
```

规则：

- `suite` 取 `acceptance`（本单的短用例）或 `regression`（merge 回归跑的少数全链路 journey）。
  已合入工单的 acceptance 用例是冻结的：不要扩展它，扩展 living regression journey 或新建本单的
  acceptance 用例。
- `test` 与 spec 里的标题一字不差；有用例没有对应行、或有行没有对应用例，`mark merge` 都会拒绝。
  `mark journeys <worktree>` 会列出要加和要删的行；它填好 file 和 covers，suite 要自己补。
- `path` 是能否复用的依据：从哪里开始、经过哪些状态、在哪里结束。扩展一个用例时，同步更新它的
  path 和 covers。
- 修改用例时保持标题不变：换了标题就算新用例。
