# 格式：tech-plan.md

由 coder-plan 写；在 `review-plan` 由人审阅；此后对所有人只读。

~~~markdown
# <编号> · 技术方案

## 数据模型
<新增或变更的实体、字段、迁移；或「无变更」>

## 接口
<API、事件、模块契约：签名、输入、输出、错误>

## 模块改动
| 模块 | 改动 | 依赖 |
|---|---|---|

## 时序图
### SD-1 · <流程>（AC-1、AC-2）
```mermaid
sequenceDiagram
  participant UI as frontend/project
  participant API as projects API
  UI->>API: GET /projects/:id
  alt 不存在
    API-->>UI: 404
  else 正常
    API-->>UI: Project
  end
```

## 任务拆解
<!-- mark:tasks -->
- T-1：<具体改动>（SD-1；AC-1）
- T-2：……

## 完整使用路径
<本单做完后用户从入口到完成怎么走；哪里还断着>

## 端到端覆盖
<!-- mark:e2e-plan -->
| AC | action | test | suite | 要加的步骤 / 为什么没有已有用例能扩展 |
|---|---|---|---|---|
| AC-1 | new | <本单短用例的标题> | acceptance | <这个用例证明什么> |
| AC-2 | extend | <living main journey 的完整标题> | regression | <要加哪些步骤，加在哪一步之后> |
| AC-3 | unit | - | - | <由单元测试覆盖（coder-impl）> |

## 自查
- 已复用：<既有模块/工具 → 用在 T-N>
- 坚持新建：<什么，为什么不能扩展既有实现>
- 排查过：<查过哪些地方>

## ADR
- <新写或受影响的 ADR 编号，或「无」>

## 风险与待确认
<!-- mark:open-questions -->
- 无
~~~

规则：

- 每条 `AC-N` 至少被一个 `T-N` 覆盖；只有端到端测试能交付的，标「tester」。每个 `T-N` 都出现在
  某张 `SD-N` 里。
- 每个 `T-N` 都是 coder-impl 的活：不落在 UI 目录（designer）或端到端测试目录（tester）。
- **端到端覆盖：**先读 `<tests>/JOURNEYS.md`。每条 `AC-N` 至少一行；一个短用例覆盖一簇标准时，
  这些 AC 写在同一行的 AC 列。`suite` 取 `acceptance`、`regression` 或 `-`。
- `acceptance` 是默认，且为 `new`：每个用户能独立验证的 AC 簇一个短用例，写明它将用的完整标题。
  不要默认 `extend`：已合入工单的 acceptance 用例是冻结的。
- `regression` 行记录对全链路的影响：action 写 `extend`，test 写路径已经经过这个状态的 living main
  journey，步骤列写加哪几步。改动不经过任何全链路时写 `| AC-N | - | none | regression | none |`。
  不要默认 extend 冻结的历史 flow。
- `-` 配 `unit`：用户操作触达不到的标准，由 coder-impl 用单测覆盖。`extend`、`new`、`unit` 在任何
  语言下都照写。人在这里审新用例；tester 不能新建这里没写的用例。
- 时序图用 Mermaid `sequenceDiagram`，并画出失败分支。
- 不设 changelog 段：返工历史写在 commit 正文里，引用 `R-N`。
