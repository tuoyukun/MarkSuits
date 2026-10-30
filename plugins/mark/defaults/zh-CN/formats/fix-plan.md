# 格式：fix-plan.md

由 fix-plan 写；直接交给 coder-impl（无人审闸门）。保持精简：它指路，不装实现。

```markdown
# <编号> · 修复方案

## 根因
<哪里错了、为什么，附文件和行号>

## 复现步骤
1. <步骤>
→ <会发生什么>

## 修复方案
- <文件或模块>：<改什么、为什么> [inline]
- <UI 目录里的组件>：<改什么、为什么> [ui]

## 修复验收点
<!-- mark:ac -->
- AC-1：<可判定的检查：bug 已消失>
- AC-2：回归：<什么必须仍然正常>

## 端到端覆盖
<!-- mark:e2e-plan -->
| AC | action | test | suite | 要加的步骤 / 为什么没有已有用例能扩展 |
|---|---|---|---|---|
| AC-1 | new | <本单短用例的标题> | acceptance | <这个用例证明什么> |
| AC-2 | extend | <living main journey 的完整标题> | regression | <要加哪些步骤，加在哪一步之后> |
| AC-3 | unit | - | - | <由单元测试覆盖（coder-impl）> |

## 影响文件
- <路径>

## 返工记录
- <日期> · <触发源（R-N 或 blocked-plan）> · <改了什么>

## 风险与待确认
<!-- mark:open-questions -->
- 无
```

规则：

- 至少有一条验收点是回归检查。
- 用户操作触达不到的验收点标 `[unit]`，由 coder-impl 用单测覆盖。未标注的用端到端测试验证。
- **端到端覆盖：**先读 `<tests>/JOURNEYS.md`。每条 `AC-N` 至少一行；一个短用例覆盖一簇标准时，
  这些 AC 写在同一行。`suite` 取 `acceptance`、`regression` 或 `-`。`acceptance` 默认 `new`：每个
  用户能独立验证的 AC 簇一个短用例，写明完整标题；已合入工单的 acceptance 用例是冻结的。`regression`
  行扩展路径经过改动状态的 living main journey，并写明加哪几步；不经过任何全链路时写
  `| AC-N | - | none | regression | none |`。tester 不能新建这张表没写成 new 的用例。
  `extend`、`new`、`unit` 在任何语言下都照写。
- 改 UI 目录的修复项标 `[ui]`：由 designer 在 coder-impl 之前完成，你的 outcome 为 `designing`。
  `inline`、`ui` 在任何语言下都照写。
- 修复若要动数据模型、跨模块契约或框架，它就不是 bug 修复：写进待确认。
