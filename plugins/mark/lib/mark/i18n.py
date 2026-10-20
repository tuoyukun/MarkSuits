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
            "  mark status [--active | --json | --check]\n"
            "  mark unlock <ticket-id> <role>"
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
            "  mark status [--active | --json | --check]\n"
            "  mark unlock <工单编号> <角色>"
        ),
    },
}


def t(locale: str, key: str, **params: object) -> str:
    table = MESSAGES.get(locale) or MESSAGES["en"]
    template = table.get(key) or MESSAGES["en"][key]
    return template.format(**params)


# --------------------------------------------------------------------------
# Guard messages. Each one says what was blocked, why, and the exact way out.
# --------------------------------------------------------------------------
MESSAGES["en"].update({
    "guard.scope": (
        "`{who}` may not write `{rel}` (rule `{glob}` allows: {allowed}).\n"
        "Write scopes keep roles apart: planning never writes code, implementation never rewrites the plan,\n"
        "and only the main thread touches workflow control files. Do not route around this with another tool.\n"
        "If the change belongs to another role, say so in your result and let the orchestrator dispatch it."
    ),
    "guard.worktree.role": (
        "`{who}` is writing in the MAIN checkout ({path}), not in its ticket worktree.\n"
        "The Agent tool has no cwd parameter; you inherit wherever the orchestrator stood. Anchor every action\n"
        "to the worktree path from your brief (under `{wt_dir}/`): use absolute paths for file tools, and\n"
        "`cd <worktree> && ...` or `git -C <worktree> ...` in Bash."
    ),
    "guard.worktree.main": (
        "`{rel}` may not be written in the main checkout. The main checkout is a state lane: only ticket\n"
        "directories, gates and locks change here. Make the change in a ticket worktree (under `{wt_dir}/`)\n"
        "so it reaches main through the normal merge path. If this path is meant to be edited on main,\n"
        "add it to `[worktree] main_writable` in .mark/config.toml."
    ),
    "guard.ticket": (
        "Opening {kind} `{id}` has not been approved by a human (missing `{gate}`).\n"
        "Opening a ticket is a scheduling decision, not an agent decision. Stop and explain to the human what\n"
        "you found, why it needs its own ticket, and the suggested priority. Only after explicit approval:\n"
        "  touch {gate}"
    ),
    "guard.status.not_main": (
        "`{rel}` is ticket state and only changes in the main checkout. Report the status change in your\n"
        "result; the orchestrator records it on main."
    ),
    "guard.status.branch": (
        "Ticket state only changes on `{main}`, but the main checkout is on `{branch}`.\n"
        "  git checkout {main}"
    ),
    "guard.status.invalid": "This status.md would be invalid:\n{problems}",
    "guard.status.move": (
        "Illegal status move `{old}` -> `{new}`. From `{old}` the allowed moves are: {allowed}.\n"
        "Review gates cannot be skipped by editing status.md; use /mark:approve or /mark:reject."
    ),
    "guard.target.missing": (
        "Cannot tell which ticket this `{role}` dispatch is for. Put exactly one anchor in the prompt:\n"
        "  <!-- mark:ticket features/<id> -->   (or bugs/<id>)\n"
        "or the ticket path `{state}/features/<id>/`. Prompt templates include the anchor."
    ),
    "guard.target.unknown": "Ticket {kind} `{id}` does not exist in the main checkout. Check the id (`mark status`).",
    "guard.target.ambiguous": "The prompt points at several tickets ({targets}). Name exactly one target with a `mark:ticket` anchor.",
    "guard.target.short_ambiguous": "Short ticket id `{ref}` matches several directories. Use the full id.",
    "guard.gate": (
        "`{role}` needs human approval first: missing `{gate}`.\n"
        "Stop, report what the previous step produced, and wait for the human to run /mark:approve {id}.\n"
        "If this gate has nothing to review for this ticket (e.g. no UI work), the human may create\n"
        "`{gate}.waived` instead. Never write the approval yourself."
    ),
    "guard.branch.missing": (
        "Ticket `{id}` has no branch and no worktree yet. Set up isolation first:\n"
        "  git fetch origin && git branch \"{branch}\" {base}\n"
        "  git push -u origin \"{branch}\"\n"
        "  git worktree add \"{wt}\" \"{branch}\"\n"
        "No agent has started yet, so nothing is lost."
    ),
    "guard.branch.no_worktree": (
        "Branch `{branch}` exists but no worktree has it checked out. The agent would write in another\n"
        "ticket's directory.\n  git worktree add \"{wt}\" \"{branch}\""
    ),
    "guard.branch.in_main": (
        "Branch `{branch}` is checked out in the MAIN checkout, which every session shares.\n"
        "  git checkout main\n  git worktree add \"{wt}\" \"{branch}\""
    ),
    "guard.branch.base": (
        "`{branch}` was not cut from {base}: unmerged branch `{other}` is its ancestor, so merging it would\n"
        "carry `{other}`'s unreviewed changes along. Recreate the branch from {base} and cherry-pick this\n"
        "ticket's commits. If the dependency is intended, record `base-branch: {other}` in the ticket's status.md."
    ),
    "guard.branch.no_remote": (
        "`origin/{branch}` does not exist; the ticket's work would live only on this machine.\n"
        "  git push -u origin \"{branch}\""
    ),
    "guard.branch.unpushed": (
        "`{branch}` has {n} commit(s) not on origin. Push before stacking another stage on top:\n"
        "  git push origin \"{branch}\""
    ),
    "guard.commit.dirty": (
        "Ticket state for `{id}` on main is not committed:\n{files}\n"
        "Commit and push it before dispatching the next agent:\n"
        "  git add {dir} && git commit -m \"<id>: <status change>\" && git push"
    ),
    "guard.commit.unpushed": "Local `{main}` is ahead of origin. Push it before dispatching:\n  git push origin {main}",
    "guard.commit.reminder": (
        "Ticket state for `{id}` changed on {main}. Commit and push it now:\n"
        "  git add {dir} && git commit -m \"{id}: <status change>\" && git push"
    ),
    "guard.dedup.pending": (
        "A `{role}` dispatch for `{id}` was reserved {age}s ago and is not confirmed yet. Wait; if it never\n"
        "started, the reservation clears itself after 90s."
    ),
    "guard.dedup.running": (
        "`{role}` is already working on `{id}` (agent {agent}, started {age} min ago). Do not dispatch a\n"
        "second one: wait for it to finish. Slow is normal. If that session is gone for sure, a human runs:\n"
        "  mark unlock {id} {role}"
    ),
    "guard.dedup.race": "Another `{role}` dispatch for `{id}` started at the same moment. Wait for it.",
    "guard.output.missing": (
        "You (`{role}`) are about to stop, but required output is missing:\n{missing}\n"
        "Checked these ticket directories:\n{checked}\n"
        "Do not stop yet: write the missing file(s) to the first location, then finish. If the file does\n"
        "exist somewhere above, say where in your result and finish; do not create a second copy."
    ),
    "guard.bash.commit_main": "`{who}` may not commit on main. Run git in your worktree: `git -C <worktree> commit ...`.",
    "guard.bash.push_main": "`{who}` may not push to main. Push your ticket branch; merging into main has its own path.",
    "guard.bash.checkout_main": (
        "Do not check out `{branch}` in the main checkout; every session shares it. Use a worktree:\n"
        "  git worktree add \"{wt}\" \"{branch}\""
    ),
    "cli.unlock.ok": "Released lock {id}.{role}.",
    "cli.unlock.none": "No lock {id}.{role}.",
})

MESSAGES["zh-CN"].update({
    "guard.scope": (
        "`{who}` 不能写 `{rel}`（规则 `{glob}` 只允许：{allowed}）。\n"
        "写域用来隔开角色：出方案的不写代码，写代码的不改方案，流程控制文件只有主线程能动。不要换个工具绕过去。\n"
        "如果这处改动属于别的角色，在你的结论里写明，由 orchestrator 派对应角色去改。"
    ),
    "guard.worktree.role": (
        "`{who}` 正在**主仓**里写文件（{path}），而不是本工单的 worktree。\n"
        "Agent 工具没有 cwd 参数，你继承的是 orchestrator 派你时所在的目录。每个操作都要锚定到简报里给的\n"
        "worktree 路径（在 `{wt_dir}/` 下）：文件工具用绝对路径，Bash 用 `cd <worktree> && ...` 或 `git -C <worktree> ...`。"
    ),
    "guard.worktree.main": (
        "主仓里不能写 `{rel}`。主仓只是状态车道：只改工单目录、gates 和 locks。\n"
        "请在工单的 worktree（`{wt_dir}/` 下）里改，走正常合并进 main。\n"
        "如果这个路径本来就该在 main 上改，把它加进 .mark/config.toml 的 `[worktree] main_writable`。"
    ),
    "guard.ticket": (
        "{kind} `{id}` 的建单还没有经过人同意（缺少 `{gate}`）。\n"
        "建单是排期决定，不归 agent。先停下，用人话向 Human 说明：发现了什么、为什么要单独立单、建议什么优先级。\n"
        "得到明确同意之后，才写下凭证：\n  touch {gate}"
    ),
    "guard.status.not_main": "`{rel}` 是工单状态，只能在主仓里改。把状态变更写进你的结论，由 orchestrator 在 main 上记录。",
    "guard.status.branch": "工单状态只能在 `{main}` 上改，但主仓现在在 `{branch}` 上。\n  git checkout {main}",
    "guard.status.invalid": "这样写 status.md 不合规：\n{problems}",
    "guard.status.move": (
        "非法的状态跳转 `{old}` -> `{new}`。从 `{old}` 只能跳到：{allowed}。\n"
        "不能靠改 status.md 跳过人审闸门，请用 /mark:approve 或 /mark:reject。"
    ),
    "guard.target.missing": (
        "认不出这次派 `{role}` 是为哪张工单。请在 prompt 里放且只放一个锚点：\n"
        "  <!-- mark:ticket features/<id> -->   （或 bugs/<id>）\n"
        "或写出工单路径 `{state}/features/<id>/`。派活模板里自带这个锚点。"
    ),
    "guard.target.unknown": "主仓里没有 {kind} 工单 `{id}`。请核对编号（`mark status`）。",
    "guard.target.ambiguous": "prompt 指向了多张工单（{targets}）。请用 `mark:ticket` 锚点只写一个目标。",
    "guard.target.short_ambiguous": "短编号 `{ref}` 匹配到多个目录，请写完整编号。",
    "guard.gate": (
        "派 `{role}` 之前需要人审放行：缺少 `{gate}`。\n"
        "先停下，向 Human 报告上一步的产出，等 Human 执行 /mark:approve {id}。\n"
        "如果这张工单在这道闸门上确实没有可审的东西（比如没有 UI 改动），可以由 Human 建 `{gate}.waived` 豁免。\n"
        "绝不能自己写审批文件。"
    ),
    "guard.branch.missing": (
        "工单 `{id}` 还没有分支和 worktree。先建隔离环境：\n"
        "  git fetch origin && git branch \"{branch}\" {base}\n"
        "  git push -u origin \"{branch}\"\n"
        "  git worktree add \"{wt}\" \"{branch}\"\n"
        "agent 还没启动，没有任何损失。"
    ),
    "guard.branch.no_worktree": (
        "分支 `{branch}` 存在，但没有任何 worktree 检出它，agent 会写进别的工单的目录。\n"
        "  git worktree add \"{wt}\" \"{branch}\""
    ),
    "guard.branch.in_main": (
        "分支 `{branch}` 被检出在**主仓**里，而主仓是所有会话共用的。\n"
        "  git checkout main\n  git worktree add \"{wt}\" \"{branch}\""
    ),
    "guard.branch.base": (
        "`{branch}` 不是从 {base} 拉出来的：未合并的 `{other}` 是它的祖先，合并时会把 `{other}` 未过审的改动一起带进去。\n"
        "请从 {base} 重建分支，再 cherry-pick 本工单的提交。如果确实要依赖它，在本工单 status.md 里写 `base-branch: {other}`。"
    ),
    "guard.branch.no_remote": "远端没有 `origin/{branch}`，这张工单的产出只存在这台机器上。\n  git push -u origin \"{branch}\"",
    "guard.branch.unpushed": "`{branch}` 有 {n} 个提交还没推到远端。先推送，再叠下一阶段：\n  git push origin \"{branch}\"",
    "guard.commit.dirty": (
        "main 上 `{id}` 的工单状态还没提交：\n{files}\n"
        "派下一个 agent 之前先提交并推送：\n"
        "  git add {dir} && git commit -m \"<id>: <状态变化>\" && git push"
    ),
    "guard.commit.unpushed": "本地 `{main}` 领先远端，派活前先推送：\n  git push origin {main}",
    "guard.commit.reminder": (
        "`{id}` 的工单状态在 {main} 上改了，现在就提交并推送：\n"
        "  git add {dir} && git commit -m \"{id}: <状态变化>\" && git push"
    ),
    "guard.dedup.pending": "`{id}` 的 `{role}` 派发在 {age} 秒前已预留、尚未确认。请等待；如果它根本没启动，90 秒后预留会自动清除。",
    "guard.dedup.running": (
        "`{role}` 已经在处理 `{id}`（agent {agent}，{age} 分钟前启动）。不要再派第二个，等它结束；慢是正常的。\n"
        "如果确认那个会话已经没了，由 Human 执行：\n  mark unlock {id} {role}"
    ),
    "guard.dedup.race": "另一个 `{role}` 派发在同一时刻启动了 `{id}`，请等待它。",
    "guard.output.missing": (
        "你（`{role}`）正要结束，但必交产物缺失：\n{missing}\n"
        "已查过这些工单目录：\n{checked}\n"
        "先别结束：把缺的文件写到第一个位置，再结束。如果文件其实在上面某处，在结论里写明位置后直接结束，不要另写一份。"
    ),
    "guard.bash.commit_main": "`{who}` 不能在 main 上提交。请在你的 worktree 里执行：`git -C <worktree> commit ...`。",
    "guard.bash.push_main": "`{who}` 不能推送到 main。请推送工单分支，合并进 main 有专门的路径。",
    "guard.bash.checkout_main": "不要在主仓里检出 `{branch}`，主仓是所有会话共用的。请用 worktree：\n  git worktree add \"{wt}\" \"{branch}\"",
    "cli.unlock.ok": "已释放锁 {id}.{role}。",
    "cli.unlock.none": "没有锁 {id}.{role}。",
})
