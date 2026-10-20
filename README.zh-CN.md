# MarkSuits

**Mark** 是一套给 [Claude Code](https://code.claude.com) 用的多 agent 研发流程，由一个插件和一份项目模板组成，类似 starter：新工程装上就有完整的多 agent 协作架构。

> 状态：v0.5.0。引擎和项目模板（角色 agent、派活模板、制品格式，`en` 与 `zh-CN` 两套）已完成；
> 下一步是在示例工程上做端到端验证。尚不可用于生产。

## 核心机制

- **一个编排者 + 无状态角色 agent**：主线程每次只派一步；designer / coder-plan / coder-impl / tester / fix-plan 每次从零启动，只通过落盘制品通信。
- **工单即目录**：每个 feature / bug 一个目录，制品按 requirement → design → tech-plan → handoff → verdict 流转。
- **人审闸门**：`/mark:approve` 写 gate 文件，gate 不存在就派不出下一个 agent。
- **机制强制**：hook 以 exit 2 拦截越权写入、跳闸门、重复派发、写错分支。
- **隔离**：一单一分支一 worktree，代码只能经唯一的合并通道进 main。

## 分层

| 层 | 内容 | 升级方式 |
|---|---|---|
| 插件 `plugins/mark/` | hooks、编排 skills、CLI | `claude plugin update` |
| 模板 `copier.yml` + `template/project/` | 角色定义、派活模板、制品格式、`.mark/config.toml` | `copier update -a .mark/.copier-answers.yml`（三方合并） |
| 项目内容 | 模块边界、写域、契约 | 不升级 |

模板提供 `zh-CN` 与 `en` 两套文本，生成项目时选择。

开发说明见 [README.md](README.md#development)。

## 许可证

[MIT](LICENSE)
