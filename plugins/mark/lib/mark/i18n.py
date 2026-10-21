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
    "guard.scope_unassigned": (
        "`{who}` may not write `{rel}`: no write rule assigns this path to a role, so only the main thread writes it.\n"
        "Each module keeps its own dependencies, config and scripts in its own directory (layout: `CLAUDE.md`). "
        "If the file belongs to a module, put it there. Otherwise do not route around this with another tool: "
        "say in your result what you need and why; the human can assign the path in `[[write_rules]]`."
    ),
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
        "add it to `[worktree] main_writable` in .mark/config.toml. For a docs/config change that belongs\n"
        "to no ticket, open a throwaway lane with `mark general new` (/mark:general)."
    ),
    "guard.budget": (
        "`{rel}` would be {size} bytes; its doc budget is {limit} (`[[doc_budget]]` in .mark/config.toml).\n"
        "Cut at least {cut} bytes. Every role that loads this file pays for each line on every dispatch,\n"
        "so make room instead of appending: merge overlapping rules, drop history and rationale (they\n"
        "belong in the commit message), move one-role details to that role's file. Longest lines:\n{lines}\n"
        "Raising the budget is a human decision in .mark/config.toml, not a way around this."
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
    "guard.status.merge_after": (
        "This edit removes `merge-after` entries ({refs}) from `{rel}`. Declaring a dependency is free;\n"
        "dropping one is a human decision. Ask the human to edit the file themselves."
    ),
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
    "guard.dispatch.not_loaded": (
        "The `{role}` agent is not loaded in this session, so the dispatch for `{id}` never started; its lock\n"
        "is released. A session sees only the agents that existed when it started (for example, not one added\n"
        "to .claude/agents/ or shipped by a Mark update since). Do not substitute another agent type. Tell the\n"
        "human to restart Claude Code (/exit, then `claude -c` to keep this conversation) and run /mark:feature {id} again."
    ),
    "guard.dispatch.failed": (
        "The `{role}` dispatch for `{id}` failed before the agent started; its lock is released.\n"
        "Fix what the error says, then `mark next {id}` and dispatch again."
    ),
    "guard.output.missing": (
        "You (`{role}`) are about to stop, but required output is missing:\n{missing}\n"
        "Checked these ticket directories:\n{checked}\n"
        "Do not stop yet: write the missing file(s) at the paths listed under \"missing\" above, then finish. If a file does\n"
        "exist somewhere above, say where in your result and finish; do not create a second copy."
    ),
    "guard.bash.merge_main": "Do not merge `{ref}` into {main} by hand. `mark merge <id>` checks merge order, runs the regression and lands it.",
    "guard.bash.merge_lane": "Do not merge `{ref}` into {main} by hand. `mark general merge {ref}` runs the regression, lands it and removes the lane.",
    "guard.bash.commit_main": "`{who}` may not commit on main. Run git in your worktree: `git -C <worktree> commit ...`.",
    "guard.bash.push_main": "`{who}` may not push to main. Push your ticket branch; merging into main has its own path.",
    "guard.bash.shell_write": "This command writes `{rel}` through the shell. Shell writes follow the same rules as Edit/Write:\n{why}",
    "guard.bash.discard_dirty": (
        "Forced removal of `{wt}` would delete uncommitted changes. Commit and push them first; "
        "if the human wants them gone, they run the command themselves."
    ),
    "guard.bash.discard_unpushed": (
        "Forced removal of `{ref}` would lose {n} commit(s) that are on no remote and not on main. "
        "Push them first; if the human wants them gone, they run the command themselves."
    ),
    "guard.bash.checkout_main": (
        "Do not check out `{branch}` in the main checkout; every session shares it. Use a worktree:\n"
        "  git worktree add \"{wt}\" \"{branch}\""
    ),
    "cli.unlock.ok": "Released lock {id}.{role}.",
    "cli.unlock.none": "No lock {id}.{role}.",
    "cli.format.unknown": "No artifact format `{name}`.",
})

MESSAGES["zh-CN"].update({
    "guard.scope_unassigned": (
        "`{who}` 不能写 `{rel}`：没有写入规则把这个路径分给任何角色，所以只有主线程能写。\n"
        "每个模块的依赖、配置和脚本都放在自己的目录里（布局见 `CLAUDE.md`）。这个文件属于某个模块，就放进那个模块；"
        "否则不要换个工具绕过去，在结论里写明需要什么、为什么，由 Human 在 `[[write_rules]]` 里分配。"
    ),
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
        "如果这个路径本来就该在 main 上改，把它加进 .mark/config.toml 的 `[worktree] main_writable`。\n"
        "不属于任何工单的文档/配置改动，用 `mark general new`（/mark:general）开一条一次性车道。"
    ),
    "guard.budget": (
        "`{rel}` 写入后将有 {size} 字节，超出文档预算 {limit}（.mark/config.toml 的 `[[doc_budget]]`）。\n"
        "至少删掉 {cut} 字节。加载这份文件的每个角色每次派发都要为每一行付费，\n"
        "所以先腾地方再加：合并重叠的规则，删掉历史和理由（它们属于 commit 正文），\n"
        "只有一个角色用的细节挪进该角色的文件。最长的几行：\n{lines}\n"
        "提高预算是人在 .mark/config.toml 里做的决定，不是绕过它的办法。"
    ),
    "guard.ticket": (
        "{kind} `{id}` 的建单还没有经过人同意（缺少 `{gate}`）。\n"
        "建单是排期决定，不归 agent。先停下，用人话向 Human 说明：发现了什么、为什么要单独立单、建议什么优先级。\n"
        "得到明确同意之后，才写下凭证：\n  touch {gate}"
    ),
    "guard.status.not_main": "`{rel}` 是工单状态，只能在主仓里改。把状态变更写进你的结论，由 orchestrator 在 main 上记录。",
    "guard.status.branch": "工单状态只能在 `{main}` 上改，但主仓现在在 `{branch}` 上。\n  git checkout {main}",
    "guard.status.invalid": "这样写 status.md 不合规：\n{problems}",
    "guard.status.merge_after": "这次编辑会从 `{rel}` 删掉 `merge-after` 条目（{refs}）。声明依赖随时可以，撤销依赖要人来决定：请人亲手编辑这个文件。",
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
    "guard.dispatch.not_loaded": (
        "本会话没有加载 `{role}` agent，所以 `{id}` 的派发根本没启动；锁已释放。会话只认得启动时已存在的 agent\n"
        "（之后新加进 .claude/agents/ 的、或 Mark 升级后新带来的都不算）。不要换成别的 agent 类型。请 Human\n"
        "重启 Claude Code（/exit，然后 `claude -c` 保留本次对话），再运行 /mark:feature {id}。"
    ),
    "guard.dispatch.failed": "`{id}` 的 `{role}` 派发在 agent 启动前就失败了；锁已释放。按报错修好后，`mark next {id}` 再派一次。",
    "guard.output.missing": (
        "你（`{role}`）正要结束，但必交产物缺失：\n{missing}\n"
        "已查过这些工单目录：\n{checked}\n"
        "先别结束：把缺的文件写到上面「缺失」列出的路径，再结束。如果文件其实在上面某处，在结论里写明位置后直接结束，不要另写一份。"
    ),
    "guard.bash.merge_main": "不要手工把 `{ref}` 合进 {main}。`mark merge <编号>` 会检查合并顺序、跑回归再合入。",
    "guard.bash.merge_lane": "不要手工把 `{ref}` 合进 {main}。`mark general merge {ref}` 会跑回归、合入并拆掉车道。",
    "guard.bash.commit_main": "`{who}` 不能在 main 上提交。请在你的 worktree 里执行：`git -C <worktree> commit ...`。",
    "guard.bash.push_main": "`{who}` 不能推送到 main。请推送工单分支，合并进 main 有专门的路径。",
    "guard.bash.shell_write": "这条命令通过 shell 写 `{rel}`。shell 写入和 Edit/Write 守同一套规则：\n{why}",
    "guard.bash.discard_dirty": "强制删除 `{wt}` 会丢掉未提交的改动。先提交并推送；如果 Human 确实要丢弃，请 Human 自己执行这条命令。",
    "guard.bash.discard_unpushed": "强制删除 `{ref}` 会丢掉 {n} 个既不在任何远端、也不在 main 上的提交。先推送；如果 Human 确实要丢弃，请 Human 自己执行这条命令。",
    "guard.bash.checkout_main": "不要在主仓里检出 `{branch}`，主仓是所有会话共用的。请用 worktree：\n  git worktree add \"{wt}\" \"{branch}\"",
    "cli.unlock.ok": "已释放锁 {id}.{role}。",
    "cli.unlock.none": "没有锁 {id}.{role}。",
    "cli.format.unknown": "没有制品格式 `{name}`。",
})


# --------------------------------------------------------------------------
# Orchestration: mark next | dispatch | set | approve | reject | commit
# --------------------------------------------------------------------------
_USAGE_EN = (
    "usage: mark <command> [options]\n"
    "  mark init [--dry-run] [--<answer> <value>]...  set up Mark in this repository (/mark:init)\n"
    "  mark upgrade [--dry-run]                       merge the new template into a general lane (/mark:upgrade)\n"
    "  mark status [--active | --json | --check]      ticket board\n"
    "  mark next <id> [--json]                        what happens next for a ticket\n"
    "  mark dispatch <id> [--prev \"<text>\"] [--trigger \"<text>\"] [--retry]\n"
    "                                                 prepare the worktree, print the dispatch prompt\n"
    "  mark set <id> <status> [--note \"<text>\"] [--leftover N] [--merge-after <ids>] [--no-commit]\n"
    "  mark approve <id> [--no-commit]                human only (/mark:approve)\n"
    "  mark reject <id> --item \"<text>\"... [--to planning] [--no-commit]   human only (/mark:reject)\n"
    "  mark claim <feature|bug> \"<description>\" [--slug <slug>]\n"
    "  mark commit <id> [-m \"<message>\"]             commit + push the ticket's state on main\n"
    "  mark merge <id>                                pending-merge -> passed: merge main in, regression, ff-only, push\n"
    "  mark general new | merge <branch> | drop <branch> [--force]\n"
    "                                                 no-ticket lane for docs/config (/mark:general)\n"
    "  mark unlock <id> <role>                        release a dead agent's lock (human)\n"
    "  mark rules [orchestrator | role | collaboration]  print a rulebook (orchestrator by default)\n"
    "  mark format <name>                             print an artifact format (design.md, verdict.md ...)"
)
_USAGE_ZH = (
    "用法：mark <命令> [选项]\n"
    "  mark init [--dry-run] [--<答案> <值>]...       在本仓库启用 Mark（/mark:init）\n"
    "  mark upgrade [--dry-run]                       把新模板合进一条通用车道（/mark:upgrade）\n"
    "  mark status [--active | --json | --check]      工单看板\n"
    "  mark next <编号> [--json]                      这张工单下一步做什么\n"
    "  mark dispatch <编号> [--prev \"<文本>\"] [--trigger \"<文本>\"] [--retry]\n"
    "                                                 备好 worktree，输出派活 prompt\n"
    "  mark set <编号> <状态> [--note \"<文本>\"] [--leftover N] [--merge-after <编号>] [--no-commit]\n"
    "  mark approve <编号> [--no-commit]              仅限人（/mark:approve）\n"
    "  mark reject <编号> --item \"<文本>\"... [--to planning] [--no-commit]   仅限人（/mark:reject）\n"
    "  mark claim <feature|bug> \"<描述>\" [--slug <slug>]\n"
    "  mark commit <编号> [-m \"<说明>\"]               在 main 上提交并推送工单状态\n"
    "  mark merge <编号>                              pending-merge -> passed：合入 main、回归、ff-only、推送\n"
    "  mark general new | merge <分支> | drop <分支> [--force]\n"
    "                                                 不属于任何工单的文档/配置改动车道（/mark:general）\n"
    "  mark unlock <编号> <角色>                      释放已死 agent 的锁（由人执行）\n"
    "  mark rules [orchestrator | role | collaboration]  打印规则（默认 orchestrator）\n"
    "  mark format <名字>                             打印制品格式（design.md、verdict.md ……）"
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
        "The human answers with /mark:approve {id} or /mark:reject {id} <comments>.{preview}"
    ),
    "next.preview": "Design preview (give the human this path; it opens in a browser, offline):\n  {path}",
    "next.merge": (
        "{id} passed testing. Merge it next (run in the background if the regression is slow):\n  mark merge {id}"
    ),
    "next.merge_failed": (
        "The last `mark merge {id}` failed, and main was not changed:\n{reason}\n"
        "Report it to the human and stop. They fix it and ask for `mark merge {id}` again, or send it back with /mark:reject {id} <comments>."
    ),
    "merge.status": "{id} is at `{status}`; only `pending-merge` tickets are merged.",
    "merge.no_git": "This project is not a git repository; there is nothing to merge.",
    "merge.verdict": "{id}: verdict.md does not end with `<!-- mark:verdict PASSED -->`. Only a passing tester verdict is merged.",
    "merge.waiting": "{id} must merge after: {deps}. Those tickets must be `passed` or `superseded` first.",
    "merge.cycle": (
        "`merge-after` forms a cycle, so none of these can ever merge first: {cycle}.\n"
        "This is a deadlock, not a wait. A human resolves it: merge the tickets, split them differently, or\n"
        "remove one `merge-after` entry by editing status.md."
    ),
    "merge.no_worktree": "{id} has no worktree on `{branch}`. Run `mark dispatch` once to restore it, or merge by hand.",
    "merge.fetch_failed": "Could not fetch origin/{main}. Fix the remote and retry.",
    "merge.conflict": (
        "Merging {base} into `{branch}` conflicts; the merge was aborted and nothing changed.\n"
        "The branch needs rework against the latest main: /mark:reject {id} \"resolve the conflict with main\"."
    ),
    "merge.budget": (
        "The branch leaves docs over their budget (`[[doc_budget]]`); main was not changed:\n{files}\n"
        "Trim them on the branch, commit, and merge again."
    ),
    "merge.red": (
        "Regression `{cmd}` failed (exit {code}) after merging main into the branch; main was not changed.\n"
        "Full log: {log}\n--- last lines ---\n{tail}"
    ),
    "merge.ff_failed": "`{main}` cannot fast-forward to `{branch}` (it has commits the branch lacks). Push or drop them, then retry.",
    "merge.push_failed": "Pushing {main} failed, so the local fast-forward was undone. Pull, then retry `mark merge`.",
    "merge.no_regression": "No `[merge] regression` command is configured; merging on the tester's verdict alone.",
    "merge.green": "Regression passed: `{cmd}`.",
    "merge.landed": "`{branch}` fast-forwarded into {main} and pushed.",
    "merge.kept_worktree": "Could not remove worktree {wt} (untracked files?). Remove it by hand.",
    "merge.kept_branch": "Could not delete branch {branch}. Delete it by hand.",
    "merge.kept_remote": "Could not delete origin/{branch}. Delete it by hand.",
    "merge.done": "{id} merged: `pending-merge` -> `passed`.",
    "general.new": (
        "Lane ready: branch `{branch}`, worktree {wt}\n"
        "Edit there with absolute paths, commit, then land it:\n"
        "  git -C \"{wt}\" add -A && git -C \"{wt}\" commit -m \"<message>\"\n"
        "  mark general merge {branch}"
    ),
    "general.not_lane": "`{branch}` is not a general lane (lanes are `{prefix}<stamp>`). Tickets merge with `mark merge <id>`.",
    "general.no_lane": "`{branch}` has no worktree. Lanes are created by `mark general new`.",
    "general.dirty": "The lane {wt} has uncommitted changes:\n{files}\nCommit them first:\n  git -C \"{wt}\" add -A && git -C \"{wt}\" commit -m \"<message>\"",
    "general.empty": "`{branch}` has no commits beyond main; nothing to merge. Commit in the lane first, or drop it:\n  mark general drop {branch}",
    "general.no_branch": "There is no branch `{branch}`. `git branch --list 'chore/general-*'` lists the lanes.",
    "general.unsaved": (
        "`{branch}` has work that is not on main ({commits} commit(s), {files} uncommitted file(s)); "
        "dropping it would lose that work. Land it with `mark general merge {branch}`, or, only if the "
        "human says to discard it:\n  mark general drop {branch} --force"
    ),
    "general.dropped": "`{branch}` was dropped: its worktree and branch are gone, main is unchanged.",
    "general.conflict": (
        "Merging {base} into `{branch}` conflicts; the merge was aborted and nothing changed.\n"
        "Report it to the human. The lane is kept at {wt}."
    ),
    "general.done": "`{branch}` landed and the lane was removed.",
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
    "flow.bad_merge_after": "Not a ticket reference: {refs}. Use `0012` or `b0007`.",
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
    "flow.iso.setup": "Provisioned the new worktree: `{cmd}`.",
    "flow.iso.setup_failed": (
        "Worktree setup `{cmd}` failed ({result}), so the new worktree was removed and no agent was started.\n"
        "Fix `[worktree] setup` in .mark/config.toml (or what it needs in the main checkout), then retry.\n"
        "Full log: {log}\n--- last lines ---\n{tail}"
    ),
    "flow.iso.setup_dirty": (
        "Worktree setup `{cmd}` left files git sees, so the new worktree was removed:\n{files}\n"
        "Gitignore them (a symlink needs `name`, not `name/`), then retry. Full log: {log}"
    ),
    "flow.iso.branch_failed": "Could not create branch {branch} from {base}.",
    "flow.iso.worktree_failed": "Could not create worktree {wt} for {branch}.",
    "flow.iso.push_failed": "Could not push {branch} to origin. Fix the remote and retry; the work must not live on one machine only.",
    "flow.invalid_status": "The new status.md would be invalid:\n{problems}",
    "flow.illegal": "Illegal move `{old}` -> `{new}`. Allowed from `{old}`: {allowed}.",
    "flow.human_gate": "{id} is at `{status}`, a human review gate. Only /mark:approve or /mark:reject move it.",
    "flow.need_design_qa": "{id} has a design and its branch changes UI paths, so it goes through design QA before testing:\n  mark set {id} design-qa",
    "flow.qa_cap": (
        "{id}: design QA is still blocked after round {n}. Stop iterating; the human decides. Record it and report:\n"
        "  mark set {id} blocked-spec"
    ),
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
        "由 Human 用 /mark:approve {id} 或 /mark:reject {id} <意见> 答复。{preview}"
    ),
    "next.preview": "设计预览（把这个路径交给 Human，浏览器直接打开，无需联网）：\n  {path}",
    "next.merge": (
        "{id} 已测试通过。下一步合并（回归慢就放后台跑）：\n  mark merge {id}"
    ),
    "next.merge_failed": (
        "上一次 `mark merge {id}` 失败，main 未被改动：\n{reason}\n"
        "报告 Human 后停下。由 Human 处理后让你重跑 `mark merge {id}`，或用 /mark:reject {id} <意见> 打回。"
    ),
    "merge.status": "{id} 处于 `{status}`；只合并 `pending-merge` 的工单。",
    "merge.no_git": "本项目不是 git 仓库，没有可合并的东西。",
    "merge.verdict": "{id}：verdict.md 结尾不是 `<!-- mark:verdict PASSED -->`。只合并 tester 判通过的工单。",
    "merge.waiting": "{id} 必须排在这些工单之后合并：{deps}。它们须先到 `passed` 或 `superseded`。",
    "merge.cycle": (
        "`merge-after` 成环，环上谁都不可能先合：{cycle}。\n"
        "这是死锁，不是等待。由人来解：合并这几单、重新划分，或亲手编辑 status.md 删掉一条 `merge-after`。"
    ),
    "merge.no_worktree": "{id} 在 `{branch}` 上没有 worktree。跑一次 `mark dispatch` 恢复，或手工合并。",
    "merge.fetch_failed": "拉取 origin/{main} 失败。修好远端后重试。",
    "merge.conflict": (
        "把 {base} 合入 `{branch}` 有冲突；已中止合并，什么都没改。\n"
        "分支需要基于最新 main 返工：/mark:reject {id} \"解决与 main 的冲突\"。"
    ),
    "merge.budget": (
        "分支上有文档超出预算（`[[doc_budget]]`）；main 未被改动：\n{files}\n"
        "在分支上精简、提交后再合并。"
    ),
    "merge.red": (
        "合入 main 后回归 `{cmd}` 失败（退出码 {code}）；main 未被改动。\n"
        "完整日志：{log}\n--- 最后几行 ---\n{tail}"
    ),
    "merge.ff_failed": "`{main}` 无法快进到 `{branch}`（main 上有分支没有的提交）。先推送或丢弃它们，再重试。",
    "merge.push_failed": "推送 {main} 失败，本地快进已撤销。先拉取，再重试 `mark merge`。",
    "merge.no_regression": "没有配置 `[merge] regression` 命令；仅凭 tester 结论合并。",
    "merge.green": "回归通过：`{cmd}`。",
    "merge.landed": "`{branch}` 已快进合入 {main} 并推送。",
    "merge.kept_worktree": "无法删除 worktree {wt}（有未跟踪文件？）。请手工删除。",
    "merge.kept_branch": "无法删除分支 {branch}。请手工删除。",
    "merge.kept_remote": "无法删除 origin/{branch}。请手工删除。",
    "merge.done": "{id} 已合并：`pending-merge` -> `passed`。",
    "general.new": (
        "车道已就绪：分支 `{branch}`，worktree {wt}\n"
        "用绝对路径在那里改，提交后合入：\n"
        "  git -C \"{wt}\" add -A && git -C \"{wt}\" commit -m \"<说明>\"\n"
        "  mark general merge {branch}"
    ),
    "general.not_lane": "`{branch}` 不是通用车道（车道一律是 `{prefix}<时间戳>`）。工单用 `mark merge <编号>` 合并。",
    "general.no_lane": "`{branch}` 没有 worktree。车道由 `mark general new` 创建。",
    "general.dirty": "车道 {wt} 有未提交的改动：\n{files}\n先提交：\n  git -C \"{wt}\" add -A && git -C \"{wt}\" commit -m \"<说明>\"",
    "general.empty": "`{branch}` 相对 main 没有新提交，没有可合并的东西。先在车道里提交，或者丢弃：\n  mark general drop {branch}",
    "general.no_branch": "没有分支 `{branch}`。`git branch --list 'chore/general-*'` 可列出所有车道。",
    "general.unsaved": (
        "`{branch}` 有尚未进入 main 的工作（{commits} 个提交，{files} 个未提交文件），丢弃会丢掉这些工作。"
        "用 `mark general merge {branch}` 合入；只有人明确说要丢弃时才执行：\n  mark general drop {branch} --force"
    ),
    "general.dropped": "`{branch}` 已丢弃：worktree 和分支已删除，main 未改动。",
    "general.conflict": (
        "把 {base} 合进 `{branch}` 时冲突；已中止合并，什么都没改。\n"
        "报告给人。车道保留在 {wt}。"
    ),
    "general.done": "`{branch}` 已合入，车道已拆除。",
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
    "flow.bad_merge_after": "不是工单引用：{refs}。请写 `0012` 或 `b0007`。",
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
    "flow.iso.setup": "新 worktree 已完成准备：`{cmd}`。",
    "flow.iso.setup_failed": (
        "worktree 准备命令 `{cmd}` 失败（{result}），新 worktree 已删除，没有派出任何 agent。\n"
        "修好 .mark/config.toml 的 `[worktree] setup`（或它在主仓依赖的东西）后重试。\n"
        "完整日志：{log}\n--- 最后几行 ---\n{tail}"
    ),
    "flow.iso.setup_dirty": (
        "worktree 准备命令 `{cmd}` 留下了 git 能看见的文件，新 worktree 已删除：\n{files}\n"
        "把它们加进 .gitignore（软链要写 `name`，不能写 `name/`）后重试。完整日志：{log}"
    ),
    "flow.iso.branch_failed": "无法从 {base} 建分支 {branch}。",
    "flow.iso.worktree_failed": "无法为 {branch} 建 worktree {wt}。",
    "flow.iso.push_failed": "无法把 {branch} 推到 origin。修好远端后重试；产出不能只存在一台机器上。",
    "flow.invalid_status": "新的 status.md 不合规：\n{problems}",
    "flow.illegal": "非法跳转 `{old}` -> `{new}`。从 `{old}` 只能到：{allowed}。",
    "flow.human_gate": "{id} 停在 `{status}`，这是人审闸门。只有 /mark:approve 或 /mark:reject 能推动它。",
    "flow.need_design_qa": "{id} 有设计稿，且分支改到了 UI 路径，测试前要先过集成态设计验收：\n  mark set {id} design-qa",
    "flow.qa_cap": "{id}：集成态设计验收第 {n} 轮仍未通过。不再迭代，交给 Human 决定。记录后报告：\n  mark set {id} blocked-spec",
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

# --------------------------------------------------------------------------
# mark init
# --------------------------------------------------------------------------
MESSAGES["en"].update({
    "init.plan": "Mark v{version} setup for {root}, with these answers:",
    "init.writes": "Writes {n} files (plus .mark/template.toml and a pristine copy of each under .mark/.base/).",
    "init.kept": "Keeps the existing {rel} as it is; add what Mark needs to it afterwards (/mark:init does this in a general lane).",
    "init.append": "Adds to the existing {rel}: {lines}",
    "init.dry_run": "Dry run: nothing was written. Run again without --dry-run to apply.",
    "init.done": (
        "Mark is set up: one commit on {main}. Next:\n"
        "  - fill in the TODOs in CLAUDE.md (stack, module boundaries, commands); roles read it first\n"
        "  - set `[merge] regression` and `[worktree] setup` in .mark/config.toml once the project has tests\n"
        "  - start work with /mark:feature or /mark:fix"
    ),
    "init.pushed": "Pushed {main} to origin.",
    "init.push_failed": "Pushing {main} to origin failed; push it yourself before opening tickets or lanes.",
    "init.already": "{root} is already a Mark project (.mark/config.toml exists).",
    "init.not_repo": "{root} is not a git repository and not empty. Make it a repository and commit its files first (git init && git add -A && git commit), or run in an empty directory.",
    "init.not_main": "You are on `{branch}`, but the main branch answer is `{main}`. Switch to {main}, or pass --main-branch {branch}.",
    "init.dirty": "The working tree has uncommitted changes; commit or stash them first:\n{files}",
    "init.no_identity": "git has no user name/email, so Mark cannot commit. Set them: git config --global user.name \"...\" && git config --global user.email \"...\"",
    "init.conflicts": "These files already exist and Mark would overwrite them:\n{files}\nRename or remove them (or merge them by hand after init), then retry.",
    "init.unknown_answer": "Unknown answer(s): {keys}. Run `mark init --dry-run` to see every answer.",
    "init.bad_choice": "`{answer}` must be one of: {choices} (got `{value}`).",
    "init.bad_answer": "`{answer}` must be a single non-empty line (got `{value}`).",
    "init.bad_dir": "`{answer}` must be a path inside the repository, like `frontend` (got `{value}`).",
    "init.unknown_var": "Template uses an unknown answer `{name}` (a bug in the Mark template).",
    "init.bad_config": "The answers produce an invalid .mark/config.toml: {error}",
    "init.git_failed": "`{step}` failed; the files written so far are left in place. Fix the problem and commit them by hand.",
})
MESSAGES["zh-CN"].update({
    "init.plan": "在 {root} 启用 Mark v{version}，答案如下：",
    "init.writes": "写入 {n} 个文件（另加 .mark/template.toml，以及每个文件在 .mark/.base/ 下的原样副本）。",
    "init.kept": "保留现有的 {rel} 不动；之后要往里补 Mark 需要的内容（/mark:init 会在通用车道里做）。",
    "init.append": "往现有的 {rel} 追加：{lines}",
    "init.dry_run": "试运行：什么都没写。去掉 --dry-run 再跑一次即生效。",
    "init.done": (
        "Mark 已启用：{main} 上一次提交。接下来：\n"
        "  - 补完 CLAUDE.md 里的 TODO（技术栈、模块边界、命令），每个角色开工先读它\n"
        "  - 工程有了测试后，在 .mark/config.toml 里设置 `[merge] regression` 和 `[worktree] setup`\n"
        "  - 用 /mark:feature 或 /mark:fix 开始干活"
    ),
    "init.pushed": "已把 {main} 推到 origin。",
    "init.push_failed": "把 {main} 推到 origin 失败；开工单或车道之前请自己推一下。",
    "init.already": "{root} 已经是 Mark 项目（.mark/config.toml 已存在）。",
    "init.not_repo": "{root} 不是 git 仓库，而且不是空目录。先把它变成仓库并提交现有文件（git init && git add -A && git commit），或者在空目录里运行。",
    "init.not_main": "当前在 `{branch}`，但主分支答案是 `{main}`。切到 {main}，或者传 --main-branch {branch}。",
    "init.dirty": "工作区有未提交的改动，先提交或 stash：\n{files}",
    "init.no_identity": "git 没有设置用户名/邮箱，Mark 无法提交。先设置：git config --global user.name \"...\" && git config --global user.email \"...\"",
    "init.conflicts": "这些文件已存在，Mark 会覆盖它们：\n{files}\n改名或移走（也可以 init 之后再手动合并回去），然后重试。",
    "init.unknown_answer": "未知的答案：{keys}。跑 `mark init --dry-run` 可看到全部答案。",
    "init.bad_choice": "`{answer}` 只能是：{choices}（收到 `{value}`）。",
    "init.bad_answer": "`{answer}` 必须是一行非空文本（收到 `{value}`）。",
    "init.bad_dir": "`{answer}` 必须是仓库内的路径，比如 `frontend`（收到 `{value}`）。",
    "init.unknown_var": "模板用了未知的答案 `{name}`（Mark 模板的 bug）。",
    "init.bad_config": "这组答案生成的 .mark/config.toml 不合法：{error}",
    "init.git_failed": "`{step}` 失败；已写入的文件保留在原处。解决问题后手动提交。",
})

# --------------------------------------------------------------------------
# mark upgrade
# --------------------------------------------------------------------------
MESSAGES["en"].update({
    "upgrade.stale": "> Mark project files are from v{old}; the plugin is v{new}. Run /mark:upgrade to bring them up to date.",
    "update.available": (
        "> Mark v{new} is published (installed: v{old}); Claude Code does not update it on its own. Tell the human:\n"
        ">   /plugin marketplace update {market}, restart Claude Code, then /mark:upgrade.\n"
        "> For automatic updates: /plugin > Marketplaces > {market} > Enable auto-update."
    ),
    "upgrade.plan": "Upgrade Mark project files v{old} -> v{new}:",
    "upgrade.row.added": "  added      {rel}",
    "upgrade.row.updated": "  updated    {rel}",
    "upgrade.row.merged": "  merged     {rel} (template change merged into your edits)",
    "upgrade.row.conflict": "  CONFLICT   {rel} (your edits and the template's change overlap)",
    "upgrade.row.deleted": "  skipped    {rel} (you deleted it; the template changed it)",
    "upgrade.row.removed": "  removed    {rel} (no longer in the template)",
    "upgrade.row.orphaned": "  kept       {rel} (you edited it; Mark now ships its own copy, so this file overrides it from here on)",
    "upgrade.nothing": "  (no file changes; only the recorded version moves)",
    "upgrade.dry_run": "Dry run: nothing was written. Run `mark upgrade` to write it on a general lane.",
    "upgrade.done": (
        "Upgrade committed on lane `{branch}`, worktree {wt}. Main is unchanged.\n"
        "Review it:  git -C \"{wt}\" show --stat HEAD\n"
        "Land it:    mark general merge {branch}\n"
        "Discard it: mark general drop {branch} --force"
    ),
    "upgrade.conflicts": (
        "{n} file(s) have conflict markers. Resolve them in the lane (keep the project's edits and add the\n"
        "template's change), remove every marker, commit; `mark general merge` refuses markers."
    ),
    "upgrade.no_record": "No {record}, so the template version and answers are unknown. Projects set up before v0.13 need the migration note in docs/architecture.md.",
    "upgrade.current": "Mark project files are already at v{version} (plugin v{plugin}); nothing to upgrade.",
    "upgrade.merge_failed": "`git merge-file` failed: {error}",
    "upgrade.git_failed": "Committing the upgrade in {wt} failed; the lane was dropped and main is unchanged.",
    "general.markers": (
        "The lane {wt} still has conflict markers in:\n{files}\n"
        "Resolve them, commit in the lane, then merge again."
    ),
})
MESSAGES["zh-CN"].update({
    "upgrade.stale": "> Mark 项目文件来自 v{old}，插件已是 v{new}。运行 /mark:upgrade 升级。",
    "update.available": (
        "> Mark v{new} 已发布（当前安装 v{old}），Claude Code 不会自动更新它。请告诉 Human：\n"
        ">   /plugin marketplace update {market}，重启 Claude Code，再运行 /mark:upgrade。\n"
        "> 想自动更新：/plugin > Marketplaces > {market} > Enable auto-update。"
    ),
    "upgrade.plan": "升级 Mark 项目文件 v{old} -> v{new}：",
    "upgrade.row.added": "  新增       {rel}",
    "upgrade.row.updated": "  更新       {rel}",
    "upgrade.row.merged": "  合并       {rel}（模板的改动已并入你的修改）",
    "upgrade.row.conflict": "  冲突       {rel}（你的修改和模板的改动重叠）",
    "upgrade.row.deleted": "  跳过       {rel}（你删了它，模板改了它）",
    "upgrade.row.removed": "  删除       {rel}（模板已不再包含）",
    "upgrade.row.orphaned": "  保留       {rel}（你改过它；Mark 现在自带这个文件，此后由你的这份覆盖插件内置的）",
    "upgrade.nothing": "  （没有文件改动，只更新记录的版本）",
    "upgrade.dry_run": "试运行：什么都没写。运行 `mark upgrade` 会在一条通用车道上写入。",
    "upgrade.done": (
        "升级已提交到车道 `{branch}`，worktree {wt}。main 未改动。\n"
        "查看：git -C \"{wt}\" show --stat HEAD\n"
        "合入：mark general merge {branch}\n"
        "丢弃：mark general drop {branch} --force"
    ),
    "upgrade.conflicts": (
        "{n} 个文件有冲突标记。在车道里解决（保留项目的修改，再加上模板的改动），删掉所有标记后提交；\n"
        "`mark general merge` 会拒绝带冲突标记的车道。"
    ),
    "upgrade.no_record": "没有 {record}，无法得知模板版本和答案。v0.13 之前搭建的项目请看 docs/architecture.md 里的迁移说明。",
    "upgrade.current": "Mark 项目文件已是 v{version}（插件 v{plugin}），无需升级。",
    "upgrade.merge_failed": "`git merge-file` 失败：{error}",
    "upgrade.git_failed": "在 {wt} 提交升级失败；车道已丢弃，main 未改动。",
    "general.markers": (
        "车道 {wt} 里这些文件还有冲突标记：\n{files}\n"
        "解决后在车道里提交，再合并。"
    ),
})
