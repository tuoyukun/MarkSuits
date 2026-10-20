"""User-facing messages in every supported locale.

Engine code refers to messages by key; the project's `locale` picks the text.
Keep keys stable: tests and docs refer to them. Missing keys fall back to `en`.
"""
from __future__ import annotations

LOCALES = ("en", "zh-CN")

MESSAGES: dict[str, dict[str, str]] = {
    "en": {
        # status view
        "status.title": "# Tickets (generated, not stored)",
        "status.summary": "> {total} tickets: waiting on you **{human}** · in progress {agent} · done {done}",
        "status.source": "> Source of truth: each ticket's `status.md`. Regenerate with `mark status`.",
        "status.leftover": "> Leftover items **{total}** (from {tickets} tickets, deferred or dropped at wrap-up)",
        "status.head": "| id | kind | description | status | owner | updated | note |",
        "status.sec.human": "Waiting on you",
        "status.sec.agent": "In progress",
        "status.sec.unknown": "Invalid status",
        "status.sec.done": "Done",
        "status.empty": "No tickets yet. Create one with `mark claim feature \"<description>\"`.",
        # check
        "check.ok": "[STATUS] OK: {n} tickets, all status.md files valid.",
        "check.failed": "[STATUS] Check failed:",
        "check.missing": "{rel}: missing. Every ticket directory needs a status.md.",
        "check.bad_status": "{rel}: `status: {status}` is not a valid {kind} status.",
        "check.desc_long": "{rel}: `desc` is {n} chars, limit {limit}. Put details in the ticket's requirement/bug file.",
        "check.note_long": "{rel}: note is {n} chars, limit {limit}. Put details in log.md.",
        "check.no_updated": "{rel}: missing `updated` (YYYY-MM-DD).",
        "check.no_leftover": "{rel}: `status: {status}` requires `leftover: <N>` (count of wrap-up items not resolved in this ticket; write 0 if none).",
        "check.bad_leftover": "{rel}: `leftover: {value}` must be a non-negative integer.",
        "check.bad_merge_after": "{rel}: `merge-after: {value}` must look like `[0012, b0007]`.",
        # claim
        "claim.ok": "TICKET-ID: {id}",
        "claim.failed": "Claim failed: {error} (number released, safe to retry).",
        "claim.desc_long": "Description is {n} chars, limit {limit}. Shorten it; details go in the requirement/bug file.",
        "claim.exhausted": "{n} consecutive numbers are taken in {path}; giving up.",
        # cli
        "cli.not_project": "Not a Mark project: no .mark/config.toml at or above {cwd}.",
        "cli.config_error": "Config error: {error}",
        "cli.usage": (
            "usage: mark <command> [options]\n"
            "  mark claim <feature|bug> \"<description>\" [--slug <slug>]\n"
            "  mark status [--active | --json | --check]"
        ),
    },
    "zh-CN": {
        "status.title": "# 工单汇总（现生成，未落盘）",
        "status.summary": "> 共 {total} 单：待你介入 **{human}** · 在飞 {agent} · 已结案 {done}",
        "status.source": "> 真相源是各单的 `status.md`；本视图由 `mark status` 现算。",
        "status.leftover": "> 遗留挂账 **{total}** 条（{tickets} 单在收尾结算时挂到别单或不做）",
        "status.head": "| id | 类型 | 描述 | 状态 | 待办方 | 更新 | 备注 |",
        "status.sec.human": "待你介入",
        "status.sec.agent": "在飞",
        "status.sec.unknown": "状态值非法",
        "status.sec.done": "已结案",
        "status.empty": "还没有工单。用 `mark claim feature \"<描述>\"` 建一张。",
        "check.ok": "[STATUS] OK：{n} 个工单的 status.md 全部合规。",
        "check.failed": "[STATUS] 体检未通过：",
        "check.missing": "{rel}：缺失。每个工单目录都必须有 status.md。",
        "check.bad_status": "{rel}：`status: {status}` 不是合法的 {kind} 状态。",
        "check.desc_long": "{rel}：`desc` {n} 字符，超出上限 {limit}。细节写进工单的需求或 bug 文件。",
        "check.note_long": "{rel}：备注 {n} 字符，超出上限 {limit}。过程细节写 log.md。",
        "check.no_updated": "{rel}：缺 `updated`（YYYY-MM-DD）。",
        "check.no_leftover": "{rel}：`status: {status}` 必须写 `leftover: <N>`（收尾结算中未在本单解决的条数，没有就写 0）。",
        "check.bad_leftover": "{rel}：`leftover: {value}` 必须是非负整数。",
        "check.bad_merge_after": "{rel}：`merge-after: {value}` 格式应为 `[0012, b0007]`。",
        "claim.ok": "TICKET-ID: {id}",
        "claim.failed": "立单失败：{error}（号已释放，可原样重试）",
        "claim.desc_long": "描述 {n} 字符，超出上限 {limit}。请缩短，细节写进需求或 bug 文件。",
        "claim.exhausted": "{path} 下连续 {n} 个号都已被占，放弃。",
        "cli.not_project": "不是 Mark 项目：{cwd} 及其上级目录都没有 .mark/config.toml。",
        "cli.config_error": "配置错误：{error}",
        "cli.usage": (
            "用法：mark <命令> [选项]\n"
            "  mark claim <feature|bug> \"<描述>\" [--slug <slug>]\n"
            "  mark status [--active | --json | --check]"
        ),
    },
}


def t(locale: str, key: str, **params: object) -> str:
    table = MESSAGES.get(locale) or MESSAGES["en"]
    template = table.get(key) or MESSAGES["en"][key]
    return template.format(**params)
