# 格式：verdict.md

由 tester 写；决定 orchestrator 的下一步。每次跑测都重写：它只描述最近一次运行（更早的运行留在
git 历史里）。

```markdown
# <编号> · 验收报告
<!-- mark:verdict FAILED -->

结论：FAILED
运行：<跑了哪些命令> · <结果摘要行>
回归：main@<sha> · <全量回归命令> · exit 0     （仅 PASSED 轮）

## 失败项
### FAIL-3 · <简短标题>
- failureType: impl-bug
- routeTo: coder-impl
- 标准：AC-2
- 看到：<发生了什么>
- 复现：<步骤或测试用例编号>
- 期望：<本应发生什么>
- 证据：<截图 / trace / 录像路径>

## 带掉修复
- 无
```

规则：

- 结论只能是 `PASSED` 或 `FAILED`，锚点和「结论：」行一致。任何地方都不出现其他值。
- `failureType` 取 `impl-bug`、`needs-unit-test`、`design-flaw`、`unclear` 之一。
- `FAIL-N` 永不复用：从上一份报告的最大编号往后编。上次之后已修好的失败不再重复；orchestrator
  会把本文件里所有 `FAIL-N` 交给下一个角色。
- `PASSED` 报告没有「失败项」段，且有「回归」行。
