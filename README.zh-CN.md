# MarkSuits

**Mark** 是一套给 [Claude Code](https://code.claude.com) 用的多 agent 研发流程，装一个插件即可，项目文件由插件生成，类似 starter：新工程装上就有完整的多 agent 协作架构。

> 状态：v0.13.0。引擎、项目模板（`en` 与 `zh-CN`）和示例工程已完成，bug 链与 feature 链都已在
> 示例工程上端到端跑通，见 [examples/](examples/)。工单已能自动合并（`mark merge`），不属于任何工单的文档/配置改动走 `/mark:general`，每个角色都加载的文档受字节预算约束（`[[doc_budget]]`），每个新 worktree 在 agent 开工前先由项目的 `[worktree] setup` 准备好环境。`/mark:init` 可在新工程或已有工程里启用 Mark。尚不可用于生产。

## 核心机制

- **一个编排者 + 无状态角色 agent**：主线程每次只派一步；designer / coder-plan / coder-impl / tester / fix-plan 每次从零启动，只通过落盘制品通信。
- **工单即目录**：每个 feature / bug 一个目录，制品按 requirement → design → tech-plan → handoff → verdict 流转。
- **人审闸门**：`/mark:approve` 写 gate 文件，gate 不存在就派不出下一个 agent。
- **机制强制**：hook 以 exit 2 拦截越权写入、跳闸门、重复派发、写错分支、文档超出预算。
- **隔离**：一单一分支一 worktree，代码只能经唯一的合并通道进 main。

## 分层

| 层 | 内容 | 升级方式 |
|---|---|---|
| 插件 `plugins/mark/` | hooks、编排 skills、CLI | `claude plugin update` |
| 模板 `plugins/mark/template/` | 角色定义、派活模板、制品格式、`.mark/config.toml`，由 `mark init` 写入项目 | `/mark:upgrade`（三方合并，保留你的改动，在通用车道里完成，由你决定是否合入） |
| 项目内容 | 模块边界、写域、契约 | 不升级 |

模板提供 `zh-CN` 与 `en` 两套文本，生成项目时选择。

## 安装

```bash
claude plugin marketplace add tuoyukun/MarkSuits --scope project
claude plugin install mark@marksuits --scope project
```

然后在仓库里打开 Claude Code，运行 `/mark:init`。它会先读项目（新工程或已有工程），确认是 web 全栈应用（目前唯一的角色包），给出一份答案草案（语言、目录、测试和安装命令），你确认后在 main 上一次提交写入项目文件。已有的 `CLAUDE.md` 保留并补充，已有的 `.gitignore` 只追加 Mark 需要的行。不经 agent 也可以：先 `mark init --dry-run`，再 `mark init --<答案> <值>...`。

Claude Code 不会自己更新这个 marketplace 里的插件。可以在 `/plugin` > Marketplaces > marksuits > Enable auto-update 打开一次自动更新，或者手动 `claude plugin update mark@marksuits` 后重启。`mark status` 和 `mark next` 每天查一次已发布的版本，有新版就提示（`MARK_NO_UPDATE_CHECK=1` 关闭）；项目文件落后于插件时也会提示，`/mark:upgrade` 在通用车道里把新模板三方合并进来，你点头才落地。

开发说明见 [README.md](README.md#development)。

## 许可证

[MIT](LICENSE)
