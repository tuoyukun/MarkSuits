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


# --------------------------------------------------------------------------
# Orchestration: mark next | dispatch | set | approve | reject | commit
# --------------------------------------------------------------------------
_USAGE_EN = (
    "usage: mark <command> [options]\n"
    "  mark status [--active | --json | --check]      ticket board\n"
    "  mark next <id> [--json]                        what happens next for a ticket\n"
    "  mark dispatch <id> [--prev \"<text>\"] [--trigger \"<text>\"] [--retry]\n"
    "                                                 prepare the worktree, print the dispatch prompt\n"
    "  mark set <id> <status> [--note \"<text>\"] [--leftover N] [--no-commit]\n"
    "  mark approve <id> [--no-commit]                human only (/mark:approve)\n"
    "  mark reject <id> --item \"<text>\"... [--to planning] [--no-commit]   human only (/mark:reject)\n"
    "  mark claim <feature|bug> \"<description>\" [--slug <slug>]\n"
    "  mark commit <id> [-m \"<message>\"]             commit + push the ticket's state on main\n"
    "  mark unlock <id> <role>                        release a dead agent's lock (human)\n"
    "  mark rules [orchestrator | role]               print a rulebook (orchestrator by default)"
)
_USAGE_ZH = (
    "用法：mark <命令> [选项]\n"
    "  mark status [--active | --json | --check]      工单看板\n"
    "  mark next <编号> [--json]                      这张工单下一步做什么\n"
    "  mark dispatch <编号> [--prev \"<文本>\"] [--trigger \"<文本>\"] [--retry]\n"
    "                                                 备好 worktree，输出派活 prompt\n"
    "  mark set <编号> <状态> [--note \"<文本>\"] [--leftover N] [--no-commit]\n"
    "  mark approve <编号> [--no-commit]              仅限人（/mark:approve）\n"
    "  mark reject <编号> --item \"<文本>\"... [--to planning] [--no-commit]   仅限人（/mark:reject）\n"
    "  mark claim <feature|bug> \"<描述>\" [--slug <slug>]\n"
    "  mark commit <编号> [-m \"<说明>\"]               在 main 上提交并推送工单状态\n"
    "  mark unlock <编号> <角色>                      释放已死 agent 的锁（由人执行）\n"
    "  mark rules [orchestrator | role]               打印规则（默认 orchestrator）"
)

MESSAGES["en"].update({
    "cli.usage": _USAGE_EN,
    # next
    "next.dispatch": "Next for {id}: dispatch `{role}` (template `{scenario}`).\n  mark dispatch {id} --prev \"<the previous step's conclusion, verbatim>\"",
    "next.record": (
        "`{role}` finished {id} ({reason}). Record its outcome next (dispatch nothing else first); pick from its conclusion:\n"
        "  mark set {id} <{options}> --note \"<one line>\"{wrapup}"
    ),
    "next.record.wrapup": "\nBefore `pending-merge`: write the wrap-up table in the ticket's log.md and run `mark commit {id}`.",
    "next.wait": "{roles} is still working on {id}. Wait for its completion notice; never dispatch a second one.",
    "next.review": (
        "{id} is at `{status}`, a human review gate. Report what the last step produced in plain words, then stop.\n"
        "The human answers with /mark:approve {id} or /mark:reject {id} <comments>."
    ),
    "next.merge": (
        "{id} passed testing and waits for merge. This version has no automatic merge: the human merges the\n"
        "ticket branch into main and pushes, then `mark set {id} passed`. To send it back: /mark:reject {id} <comments>."
    ),
    "next.blocked_spec": "{id} is `blocked-spec`: the design contract has a problem. Report it to the human and stop. /mark:approve {id} sends it back to the designer.",
    "next.blocked_plan": "{id} is `blocked-plan`: the plan has a hole. Report it to the human and stop. /mark:approve {id} sends it back to planning.",
    "next.blocked_unclear": (
        "{id} is `blocked-unclear`: the requirement is not clear enough. Clarify with the human, update the\n"
        "requirement/bug file, then move it where the human decides: `mark set {id} <status>`."
    ),
    "next.done": "{id} is `{status}`. Nothing to do.",
    "next.invalid": "{id}: status `{status}` is not valid. Run `mark status --check`.",
    "next.ticket_gate": "Opening {id} has not been approved by a human. Ask them; they approve with /mark:approve {id}.",
    "next.no_brief": "{id} has no `{file}` yet. Write it with the human before the first dispatch, then `mark commit {id}`.",
    "next.output_failed": (
        "`{role}` stopped on {id} without its required output ({reason}). Re-dispatch once:\n"
        "  mark dispatch {id} --retry --prev \"<its conclusion>\"\nIf that fails too, report to the human."
    ),
    # flow errors and notes
    "flow.no_ticket": "No ticket `{ref}`. See `mark status`.",
    "flow.ambiguous": "`{ref}` matches several tickets: {hits}. Use the full id.",
    "flow.not_main": "Ticket state only changes on `{main}`, but the main checkout is on `{branch}`.\n  git checkout {main}",
    "flow.commit_failed": "Commit of {paths} failed. Check `git status` in the main checkout.",
    "flow.committed": "Committed ticket state on main.",
    "flow.pushed": "Pushed main.",
    "flow.push_failed": "Pushing main failed. Push it before the next dispatch: git push origin main",
    "flow.iso.in_main": "Branch `{branch}` is checked out in the main checkout. Switch the main checkout back to main first.",
    "flow.iso.branch": "Created branch {branch} from {base}.",
    "flow.iso.dirty": (
        "The worktree of {id} has uncommitted changes, so the previous step's work is not saved on its branch:\n"
        "{files}\nCommit them on the ticket branch, then dispatch again:\n"
        "  cd \"{wt}\" && git add -A && git commit -m \"{id}: <role> output\""
    ),
    "flow.iso.worktree": "Created worktree {wt}.",
    "flow.iso.branch_failed": "Could not create branch {branch} from {base}.",
    "flow.iso.worktree_failed": "Could not create worktree {wt} for {branch}.",
    "flow.iso.push_failed": "Could not push {branch} to origin. Fix the remote and retry; the work must not live on one machine only.",
    "flow.invalid_status": "The new status.md would be invalid:\n{problems}",
    "flow.illegal": "Illegal move `{old}` -> `{new}`. Allowed from `{old}`: {allowed}.",
    "flow.human_gate": "{id} is at `{status}`, a human review gate. Only /mark:approve or /mark:reject move it.",
    "flow.need_design_qa": "{id} has a design and its branch changes UI paths, so it goes through design QA before testing:\n  mark set {id} design-qa",
    "flow.unmerged": "`{branch}` has {n} commit(s) not on {main}. `passed` means the work is on {main}: merge and push first.",
    "flow.no_human": (
        "`mark {verb}` needs a human decision, and nobody typed `/mark:{verb} {id}` in the last 12 hours.\n"
        "Ask the human to type it. Never approve or reject on their behalf."
    ),
    "flow.approve_nothing": "{id} is at `{status}`; there is nothing to approve here.",
    "flow.reject_nothing": (
        "{id} is at `{status}`, not at a human gate. /mark:reject works at review-design, review-plan and\n"
        "pending-merge. Test failures are routed from the tester's verdict, not by rejecting."
    ),
    "flow.reject_empty": "No comments given. Pass each one as --item \"<text>\".",
    "flow.reject_to": "`--to {to}` is not valid from `{status}`; only pending-merge may go back to planning.",
    "set.done": "{id}: `{old}` -> `{new}`.",
    "approve.ticket": "Opening {id} approved (wrote {gate}).",
    "approve.done": "Approved {id}: `{old}` -> `{new}`.",
    "approve.gate": "Gate written: {gate}",
    "approve.rounds": "Review rounds settled: {rounds}",
    "reject.done": "Recorded round {round} ({refs}) in {file}. {id}: `{old}` -> `{new}`.",
    "claim.approved": "Opening approved by the human's /mark:{verb}; wrote {gate}.",
    "claim.unapproved": "No /mark:feature or /mark:fix was typed, so opening {id} is not approved yet: artifacts stay blocked until the human runs /mark:approve {id}.",
    # brief
    "brief.no_template": "No prompt template `{path}` for scenario `{scenario}`. The project's templates live in [paths] prompts.",
    "brief.not_dispatch": "{id}: the next step is `{kind}`, not a dispatch. Run `mark next {id}`.",
    "brief.role_mismatch": "Template `{scenario}` declares role `{got}`, but this step needs `{want}`. Fix the template's frontmatter.",
    "brief.unknown_placeholder": "Template `{scenario}` uses unknown placeholder(s): {names}.",
    "brief.title": "[Brief · verified by the orchestrator; do not re-check these with commands]",
    "brief.worktree": "- Worktree: `{wt}`. You are NOT inside it: use absolute paths under it for file tools, and `cd \"{wt}\" && ...` for every Bash command.",
    "brief.branch": "- Branch: `{branch}` (checked before dispatch: cut from main, pushed to origin).",
    "brief.work_dir": "- Ticket artifacts (write here): `{dir}` — present: {files}",
    "brief.state_dir": "- Ticket state on main (read only): `{dir}` — present: {files}",
    "brief.outputs": "- You must leave before stopping: {files}",
    "brief.trigger": "- Trigger: {trigger}",
    "brief.prev": "- Previous step reported: {prev}",
    "brief.review": "- Human review: `{file}`. Only round(s) {rounds} are open ({refs}); earlier rounds are history, do not redo them.",
    "brief.none": "(none)",
    "brief.first": "first dispatch for this step",
    "brief.no_prev": "(first step)",
    # review files
    "review.header": (
        "# Review · {id} · {gate}\n\n"
        "> Human review comments. /mark:reject appends a round; /mark:approve marks pending rounds done.\n"
        "> R-N numbers run across rounds. Only /mark:approve and /mark:reject write this file; subagents only read it."
    ),
    "review.round": "Round {n}",
    "review.state.pending": "pending",
    "review.state.done": "done",
    # bash guard
    "guard.bash.mark_cli": "`{who}` may not run `mark {sub}`: ticket state belongs to the orchestrator. Put the outcome in your result.",
    "guard.bash.human_tokens": "Commands may not touch `{dir}`: it holds proof that a human typed a command.",
})

MESSAGES["zh-CN"].update({
    "cli.usage": _USAGE_ZH,
    "next.dispatch": "{id} 下一步：派 `{role}`（模板 `{scenario}`）。\n  mark dispatch {id} --prev \"<上一环交回的结论原话>\"",
    "next.record": (
        "`{role}` 已交回 {id}（{reason}）。接下来记录结果（在此之前不要派其他活）；按它的结论选一个：\n"
        "  mark set {id} <{options}> --note \"<一句话>\"{wrapup}"
    ),
    "next.record.wrapup": "\n进入 `pending-merge` 之前：先在本单 log.md 写好收尾表，再运行 `mark commit {id}`。",
    "next.wait": "{roles} 还在处理 {id}。等它的完成通知，绝不派第二个。",
    "next.review": (
        "{id} 停在 `{status}`，这是人审闸门。用人话报告上一步的产出，然后停下。\n"
        "由 Human 用 /mark:approve {id} 或 /mark:reject {id} <意见> 答复。"
    ),
    "next.merge": (
        "{id} 已测试通过，等待合并。当前版本没有自动合并：由 Human 把工单分支合进 main 并推送，\n"
        "再执行 `mark set {id} passed`。要打回：/mark:reject {id} <意见>。"
    ),
    "next.blocked_spec": "{id} 是 `blocked-spec`：设计契约有问题。报告 Human 后停下。/mark:approve {id} 会退回 designer 返工。",
    "next.blocked_plan": "{id} 是 `blocked-plan`：方案有洞。报告 Human 后停下。/mark:approve {id} 会退回出方案的环节。",
    "next.blocked_unclear": (
        "{id} 是 `blocked-unclear`：需求不够清楚。和 Human 澄清并更新需求/bug 文件，\n"
        "再按 Human 的决定推进：`mark set {id} <状态>`。"
    ),
    "next.done": "{id} 已是 `{status}`，无事可做。",
    "next.invalid": "{id}：状态 `{status}` 不合法。请跑 `mark status --check`。",
    "next.ticket_gate": "{id} 的建单还没经过人同意。问 Human；同意后由 Human 执行 /mark:approve {id}。",
    "next.no_brief": "{id} 还没有 `{file}`。第一次派活前先和 Human 一起写好它，再 `mark commit {id}`。",
    "next.output_failed": (
        "`{role}` 在 {id} 上结束时没留下必交产物（{reason}）。重派一次：\n"
        "  mark dispatch {id} --retry --prev \"<它的结论>\"\n再失败就报告 Human。"
    ),
    "flow.no_ticket": "没有工单 `{ref}`。见 `mark status`。",
    "flow.ambiguous": "`{ref}` 匹配到多张工单：{hits}。请写完整编号。",
    "flow.not_main": "工单状态只能在 `{main}` 上改，但主仓现在在 `{branch}` 上。\n  git checkout {main}",
    "flow.commit_failed": "提交 {paths} 失败。请在主仓查看 `git status`。",
    "flow.committed": "已在 main 上提交工单状态。",
    "flow.pushed": "已推送 main。",
    "flow.push_failed": "推送 main 失败。下次派活前先推送：git push origin main",
    "flow.iso.in_main": "分支 `{branch}` 被检出在主仓里。先把主仓切回 main。",
    "flow.iso.branch": "已从 {base} 建分支 {branch}。",
    "flow.iso.dirty": (
        "{id} 的 worktree 有未提交的改动，上一步的产出还没存进工单分支：\n"
        "{files}\n先在工单分支上提交，再派活：\n"
        "  cd \"{wt}\" && git add -A && git commit -m \"{id}: <角色> 产出\""
    ),
    "flow.iso.worktree": "已建 worktree {wt}。",
    "flow.iso.branch_failed": "无法从 {base} 建分支 {branch}。",
    "flow.iso.worktree_failed": "无法为 {branch} 建 worktree {wt}。",
    "flow.iso.push_failed": "无法把 {branch} 推到 origin。修好远端后重试；产出不能只存在一台机器上。",
    "flow.invalid_status": "新的 status.md 不合规：\n{problems}",
    "flow.illegal": "非法跳转 `{old}` -> `{new}`。从 `{old}` 只能到：{allowed}。",
    "flow.human_gate": "{id} 停在 `{status}`，这是人审闸门。只有 /mark:approve 或 /mark:reject 能推动它。",
    "flow.need_design_qa": "{id} 有设计稿，且分支改到了 UI 路径，测试前要先过集成态设计验收：\n  mark set {id} design-qa",
    "flow.unmerged": "`{branch}` 还有 {n} 个提交不在 {main} 上。`passed` 意味着代码已在 {main}：先合并并推送。",
    "flow.no_human": (
        "`mark {verb}` 需要人的决定，但最近 12 小时内没有人输入 `/mark:{verb} {id}`。\n"
        "请 Human 亲自输入。绝不能替人批准或打回。"
    ),
    "flow.approve_nothing": "{id} 停在 `{status}`，这里没有可批准的东西。",
    "flow.reject_nothing": (
        "{id} 停在 `{status}`，不在人审闸门上。/mark:reject 只在 review-design、review-plan、pending-merge 生效。\n"
        "测试失败按 tester 的结论路由，不走打回。"
    ),
    "flow.reject_empty": "没有意见。每条意见用 --item \"<文本>\" 传入。",
    "flow.reject_to": "从 `{status}` 不能 `--to {to}`；只有 pending-merge 可以退回 planning。",
    "set.done": "{id}：`{old}` -> `{new}`。",
    "approve.ticket": "已批准建单 {id}（写入 {gate}）。",
    "approve.done": "已放行 {id}：`{old}` -> `{new}`。",
    "approve.gate": "已写闸门：{gate}",
    "approve.rounds": "已结清人审轮次：{rounds}",
    "reject.done": "已在 {file} 记下第 {round} 轮（{refs}）。{id}：`{old}` -> `{new}`。",
    "claim.approved": "Human 输入了 /mark:{verb}，建单已获同意；已写 {gate}。",
    "claim.unapproved": "没有人输入 /mark:feature 或 /mark:fix，所以 {id} 的建单还没获同意：在 Human 执行 /mark:approve {id} 之前，制品写入都会被拦。",
    "brief.no_template": "场景 `{scenario}` 缺少派活模板 `{path}`。项目的模板放在 [paths] prompts 指定的目录。",
    "brief.not_dispatch": "{id}：下一步是 `{kind}`，不是派活。请跑 `mark next {id}`。",
    "brief.role_mismatch": "模板 `{scenario}` 声明的角色是 `{got}`，这一步需要 `{want}`。请修正模板头部。",
    "brief.unknown_placeholder": "模板 `{scenario}` 用了未知占位符：{names}。",
    "brief.title": "【开工简报 · orchestrator 已核实，不要再用命令确认】",
    "brief.worktree": "- 工作目录：`{wt}`。你**不在**里面：文件工具一律用它下面的绝对路径，Bash 每条命令都写 `cd \"{wt}\" && ...`。",
    "brief.branch": "- 分支：`{branch}`（派发前已验：从 main 拉出、已推到 origin）。",
    "brief.work_dir": "- 工单制品（写在这里）：`{dir}` —— 现有：{files}",
    "brief.state_dir": "- main 上的工单状态（只读）：`{dir}` —— 现有：{files}",
    "brief.outputs": "- 结束前必须留下：{files}",
    "brief.trigger": "- 本次触发源：{trigger}",
    "brief.prev": "- 上一环结论：{prev}",
    "brief.review": "- 人审意见：`{file}`。只有第 {rounds} 轮是待办（{refs}）；更早的轮次是历史，不要重做。",
    "brief.none": "（无）",
    "brief.first": "本环首次派活",
    "brief.no_prev": "（首次派活，无上一环）",
    "review.header": (
        "# 人审意见 · {id} · {gate}\n\n"
        "> 人审意见落盘。每次 /mark:reject 追加一轮；/mark:approve 把全部待处理轮次标为已处理。\n"
        "> R-N 编号跨轮连续，不按轮次重置。本文件只由 /mark:approve 和 /mark:reject 写入，subagent 只读。"
    ),
    "review.round": "第 {n} 轮",
    "review.state.pending": "待处理",
    "review.state.done": "已处理",
    "guard.bash.mark_cli": "`{who}` 不能执行 `mark {sub}`：工单状态归 orchestrator 管。把结果写进你的结论。",
    "guard.bash.human_tokens": "命令不能碰 `{dir}`：那里存放的是「人亲手输入过命令」的凭证。",
})
