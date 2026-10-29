# Mark 项目如何协作开发

一个 orchestrator（Claude Code 主会话）每次把工单往前推一步。每一步由一个全新的**角色 agent**
完成：读文件、写文件、结束。人负责开单、在三道人审闸门上放行或打回；合并是自动的。

## 命令

| 你输入 | 会发生什么 |
|---|---|
| `/mark:feature [--discuss] <描述>` | orchestrator 先和你讨论需求（大单依次谈范围、技术选型、架构；`--discuss` 强制按大单），你同意后开单，并写好需求交你审 |
| `/mark:feature <编号>` | 把该 feature 再推进一步 |
| `/mark:fix <描述或编号>` | 开 bug 单或继续推进，一路跑到 `passed`（无人审闸门） |
| `/mark:approve <编号> [<状态>]` | 放行开单、需求、设计、方案，或决定阻塞的工单下一步去哪；随后继续推进 |
| `/mark:reject <编号> <意见>` | 带着你的意见把需求、设计、方案或已完成的分支打回；随后继续推进 |
| `/mark:status` | 看板：哪些在等你、哪些在进行中 |
| `/mark:general <改动>` | 不属于任何工单的文档/配置改动：orchestrator 在一次性车道上改完，经回归合入。代码永远不走这条路 |

只有人亲手输入、并写明工单编号的放行才算数（`/mark:approve 0012`）。agent 无法放行任何东西。
`/mark:feature`、`/mark:fix` 对开单的批准在 2 小时内有效。

## 两条链

```
feature: drafting → review-requirement → designing → review-design → planning → review-plan → developing
         → (design-qa) → testing → pending-merge → passed
bug:     planning → developing → testing → pending-merge → passed
```

没有 UI 的项目（`profile = "service"`）没有 designer：需求审批通过后直接进入 `planning`，没有设计评审，
也没有设计验收。

| 状态 | 谁来做 | 制品 |
|---|---|---|
| `drafting` | orchestrator | `requirement.md`，和你一起写：验收标准和决策（`DEC-N`） |
| `review-requirement` | **你** | 读（或直接改）`requirement.md`；放行，或带意见打回 |
| `designing` | designer | `design.md` + UI 组件 + 预览 + `preview.html`（人审看它） |
| `review-design` | **你** | 放行，或带意见打回 |
| `planning` | coder-plan（feature）/ fix-plan（bug） | `tech-plan.md` / `fix-plan.md` |
| `review-plan` | **你** | 放行，或带意见打回 |
| `developing` | coder-impl | 代码、单元测试、`handoff.md` |
| `design-qa` | designer | `design-qa.md`（真实应用对照设计；仅 UI 有改动时） |
| `testing` | tester | 端到端测试、`verdict.md` |
| `failed-impl` | coder-impl | 修复 `FAIL-N` / `D-N` / 你的合并意见 |
| `pending-merge` | orchestrator | `mark merge`；失败时由**你**决定（重试或打回） |
| `blocked-*` | **你** | 看原因；`/mark:approve <编号>` 原路退回，`/mark:approve <编号> developing` 按现状继续；`blocked-unclear` 必须写明状态（`designing`、`planning` 或 `developing`） |

## 东西放在哪

- main 上的 `.mark/features/<id>/`、`.mark/bugs/<id>/`：`status.md`、`requirement.md` 或
  `bug.md`、你的审阅意见（`review-*.md`）、`log.md`。
- 每单有一个分支 `feature/<id>` 或 `bug/<id>`，以及 `.claude/worktrees/` 下的一个 worktree。
  角色 agent 只在那里写；它们的制品放在 worktree 里同一个工单路径下。
- 角色 agent、派活模板和制品格式随 Mark 插件发布、随插件升级（`mark format <名字>` 打印某个格式）。
  想为本项目改某一个，就放一个同名文件：`.claude/agents/<角色>.md`、`.mark/prompts/<场景>.md`
  或 `.mark/formats/<名字>.md`，项目里的文件优先。

## 编号

| 编号 | 出处 | 含义 |
|---|---|---|
| `AC-N` | 需求 / 修复方案 | 验收标准 |
| `DEC-N` | 需求 | 和你谈定的决策（范围、技术选型、架构） |
| `S-N` | 设计 | 一个 UI 状态 |
| `T-N`、`SD-N` | 技术方案 | 任务、时序图 |
| `R-N` | 审阅文件 | 你的一条审阅意见（跨轮连续编号） |
| `D-N` | 设计验收 | 真实应用与设计之间的一处缺陷 |
| `FAIL-N` | 验收报告 | 一条测试失败 |

编号永不复用，所以「R-4 撤回 R-1」这样的意见始终不会有歧义。

## 合并

到 `pending-merge` 时，orchestrator 执行 `mark merge <id>`：把最新 main 合入工单分支，在 worktree 里
跑 `.mark/config.toml` 中 `[merge] regression` 配置的命令，快进 main、推送，把工单标为 `passed`，
并删除它的 worktree 和分支。如果 tester 的 `mark regress` 已在同一份代码上通过（合入 main 后除工单文档外
没有变化），就不再跑回归。任何一步失败（冲突、回归变红、推送失败），main 都不会被改动，
orchestrator 会停下等你：处理好原因后让它重新合并，或用 `/mark:reject <id> <意见>` 打回。

每个角色都会加载的文档（CLAUDE.md、本文件、角色文件、派活模板、制品格式、修复方案）在
`.mark/config.toml` 的 `[[doc_budget]]` 里有字节预算。写入后超预算会被拒绝，让文档超预算的合并也会：
先腾地方再加。提高预算由你决定。

## 所有人遵守的规则

1. agent 之间从不直接对话；落盘的文件是唯一通道。
2. 信息只向下游流动：需求 → 设计 → 方案 → 代码 → 测试。
3. 开单、通过人审闸门、降低验收标准，都是人的决定。
4. 约束来自会拦截（exit 2）的 hook。只写在纸上的规则只是愿望。
