# 格式：JOURNEYS.md

`<tests>/regression/JOURNEYS.md`（端到端用例根目录是 `[paths] tests`）。由 tester 维护；
新增 regression 用例前先读它，能扩展现有旅程就不要新建。每个 regression 用例一行。
验收用例放在 `<tests>/tickets/<id>/`，不列在这里。

```markdown
# Regression 旅程

<!-- mark:journeys -->
| test | file | path | covers |
|---|---|---|---|
| <用例的完整标题> | regression/<文件> | <入口> → <关键步骤> → <结果> | <工单>/AC-1, baseline/<流程> |
```

规则：

- 只有 `<tests>/regression/` 下的用例进这张表：merge 要跑的少数核心流程。验收用例是本单自己的
  证据，绝不复制进 regression。
- `test` 与 spec 里的标题一字不差；有用例没有对应行、或有行没有对应用例，`mark merge` 都会拒绝。
  `mark journeys <worktree>` 会列出要加和要删的行；它填好 file 和 covers，path 要自己写。
- `path` 是能否复用的依据：从哪里开始、经过哪些状态、在哪里结束。扩展一个用例时，同步更新它的
  path 和 covers。
- 修改用例时保持标题不变：换了标题就算新用例。
- 核心流程有改动但还没有旅程时，补一条；不碰核心流程的工单什么都不加。
