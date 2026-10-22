"""pre-write guards: scope, worktree, ticket, status, budget (run through the real hook)."""
import unittest

from tests._support import (FULL_CONFIG, add_ticket, add_worktree, hook, make_project, make_repo,
                            sh, status_text)


def write(root, path, agent=None, content="x", tool="Write", **extra):
    payload = {"hook_event_name": "PreToolUse", "tool_name": tool, "cwd": str(root),
               "tool_input": {"file_path": str(path), "content": content, **extra}}
    if agent:
        payload["agent_type"] = agent
    return hook("pre-write", payload)


class ScopeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = make_repo()
        add_ticket(cls.root, "feature", "0001-login", "developing",
                   gates=["ticket-approved", "design-approved", "plan-approved"])
        cls.wt = add_worktree(cls.root, "feature", "0001-login")
        cls.tdir = cls.wt / ".mark" / "features" / "0001-login"

    def test_role_writes_its_own_files(self):
        self.assertEqual(write(self.wt, self.wt / "frontend/app.ts", "coder-impl")[0], 0)
        self.assertEqual(write(self.wt, self.tdir / "handoff.md", "coder-impl")[0], 0)

    def test_artifact_names_outside_ticket_dirs_follow_project_rules(self):
        self.assertEqual(write(self.wt, self.wt / "frontend/preview.html", "coder-impl")[0], 0)
        self.assertEqual(write(self.wt, self.wt / "frontend/preview.html", "designer")[0], 2)
        self.assertEqual(write(self.wt, self.tdir / "preview.html", "coder-impl")[0], 2)
        self.assertEqual(write(self.wt, self.tdir / "preview.html", "designer")[0], 0)

    def test_plugin_prefixed_role_is_normalized(self):
        self.assertEqual(write(self.wt, self.wt / "frontend/app.ts", "mark:coder-impl")[0], 0)

    def test_plan_role_cannot_write_code(self):
        code, err = write(self.wt, self.wt / "frontend/app.ts", "coder-plan")
        self.assertEqual(code, 2)
        self.assertIn("`coder-plan` may not write `frontend/app.ts`", err)

    def test_impl_role_cannot_rewrite_plan(self):
        self.assertEqual(write(self.wt, self.tdir / "tech-plan.md", "coder-impl")[0], 2)

    def test_main_thread_cannot_write_role_owned_code(self):
        self.assertEqual(write(self.wt, self.wt / "frontend/app.ts")[0], 2)

    def test_subagent_cannot_touch_control_files(self):
        for rel in (".claude/settings.json", ".mark/config.toml", ".mark/gates/0001-login.plan-approved",
                    ".mark/features/0001-login/review-plan.md"):
            self.assertEqual(write(self.wt, self.wt / rel, "tester")[0], 2, rel)

    def test_template_record_and_base_copies_are_protected(self):
        self.assertEqual(write(self.wt, self.wt / ".mark/template.toml", "tester")[0], 2)
        self.assertEqual(write(self.wt, self.wt / ".mark/template.toml")[0], 0)
        self.assertEqual(write(self.wt, self.wt / ".mark/.base/CLAUDE.md.base")[0], 2)

    def test_main_thread_may_edit_control_files_in_worktree(self):
        self.assertEqual(write(self.wt, self.wt / ".claude/agents/designer.md")[0], 0)

    def test_unassigned_path_is_the_main_threads(self):
        for rel in ("package.json", "README.md", "scripts/x.mjs"):
            code, err = write(self.wt, self.wt / rel, "coder-impl")
            self.assertEqual(code, 2, rel)
            self.assertIn("no write rule assigns this path", err)
        self.assertEqual(write(self.wt, self.wt / "package.json")[0], 0)            # main thread
        self.assertEqual(write(self.wt, self.wt / "package.json", "Explore")[0], 0)  # not a pipeline role

    def test_role_keeps_working_files_in_its_ticket_dir(self):
        self.assertEqual(write(self.wt, self.tdir / "notes.md", "tester")[0], 0)

    def test_default_doc_rules(self):
        self.assertEqual(write(self.wt, self.wt / "CLAUDE.md", "coder-impl")[0], 0)
        self.assertEqual(write(self.wt, self.wt / "CLAUDE.md", "tester")[0], 2)
        self.assertEqual(write(self.wt, self.wt / "backend/CONTEXT.md", "coder-plan")[0], 0)
        self.assertEqual(write(self.wt, self.wt / "docs/adr/0001-x.md", "coder-plan")[0], 0)
        self.assertEqual(write(self.wt, self.wt / "docs/adr/0001-x.md", "coder-impl")[0], 2)

    def test_general_purpose_agent_cannot_write_role_files(self):
        self.assertEqual(write(self.wt, self.tdir / "verdict.md", "general-purpose")[0], 2)

    def test_path_outside_project_is_ignored(self):
        outside = make_project(None) / "notes.txt"
        self.assertEqual(write(self.wt, outside, "coder-plan")[0], 0)


class WorktreeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = make_repo()
        cls.tdir = add_ticket(cls.root, "feature", "0001-login", "designing", gates=["ticket-approved"])

    def test_role_writing_in_main_checkout_is_blocked(self):
        code, err = write(self.root, self.tdir / "design.md", "designer")
        self.assertEqual(code, 2)
        self.assertIn("MAIN checkout", err)

    def test_main_thread_writes_state_lanes_on_main(self):
        self.assertEqual(write(self.root, self.tdir / "requirement.md")[0], 0)

    def test_main_thread_cannot_write_code_in_main_checkout(self):
        code, err = write(self.root, self.root / "docs/guide.md")
        self.assertEqual(code, 2)
        self.assertIn("state lane", err)

    def test_main_writable_opens_extra_paths(self):
        root = make_repo(FULL_CONFIG + '\n[worktree]\nmain_writable = ["docs/**"]\n')
        self.assertEqual(write(root, root / "docs/guide.md")[0], 0)

    def test_non_git_project_skips_worktree_rules(self):
        root = make_project(FULL_CONFIG)
        self.assertEqual(write(root, root / "docs/guide.md")[0], 0)


class GeneralLaneWriteTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = make_repo()
        cls.lane = cls.root / ".claude/worktrees/general-1"
        sh(cls.root, "git", "worktree", "add", "-q", "-b", "chore/general-1", str(cls.lane), "main")

    def test_main_thread_writes_docs_in_lane_but_never_code(self):
        self.assertEqual(write(self.lane, self.lane / "docs/guide.md")[0], 0)
        code, err = write(self.lane, self.lane / "frontend/app.ts")
        self.assertEqual(code, 2)
        self.assertIn("coder-impl", err)

    def test_main_checkout_refusal_points_to_lane(self):
        code, err = write(self.root, self.root / "docs/guide.md")
        self.assertEqual(code, 2)
        self.assertIn("mark general new", err)


class TicketTest(unittest.TestCase):
    def setUp(self):
        self.root = make_repo()
        self.tdir = add_ticket(self.root, "bug", "b0001-crash", "planning")

    def test_artifact_without_ticket_approval_is_blocked(self):
        code, err = write(self.root, self.tdir / "bug.md")
        self.assertEqual(code, 2)
        self.assertIn("/mark:approve b0001-crash", err)
        self.assertNotIn("touch", err)

    def test_approved_ticket_accepts_artifacts(self):
        (self.root / ".mark" / "gates").mkdir()
        (self.root / ".mark" / "gates" / "b0001-crash.ticket-approved").write_text("ok")
        self.assertEqual(write(self.root, self.tdir / "bug.md")[0], 0)


def bash(root, command, agent=None):
    payload = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "cwd": str(root),
               "tool_input": {"command": command}}
    if agent:
        payload["agent_type"] = agent
    return hook("pre-bash", payload)


class CliOnlyTest(unittest.TestCase):
    """Gates, ticket status and review rounds record human decisions: only the `mark` CLI writes them."""

    @classmethod
    def setUpClass(cls):
        cls.root = make_repo()
        cls.tdir = add_ticket(cls.root, "feature", "0001-login", "review-design", gates=["ticket-approved"])
        cls.wt = add_worktree(cls.root, "feature", "0001-login")
        cls.files = [".mark/gates/0001-login.design-approved", ".mark/gates/0001-login.plan-approved.waived",
                     ".mark/features/0001-login/status.md", ".mark/features/0001-login/review-design.md"]

    def test_no_tool_call_writes_them_main_thread_included(self):
        for rel in self.files:
            for root in (self.root, self.wt):
                code, err = write(root, root / rel, content=status_text("planning"))
                self.assertEqual(code, 2, (root, rel))
                self.assertIn("only by the `mark` CLI", err)
            self.assertEqual(write(self.wt, self.wt / rel, "designer")[0], 2, rel)

    def test_edit_of_status_is_blocked(self):
        code, _ = write(self.root, self.tdir / "status.md", tool="Edit",
                        old_string="status: review-design", new_string="status: planning")
        self.assertEqual(code, 2)

    def test_main_thread_shell_writes_are_blocked(self):
        for cmd in ("touch .mark/gates/0001-login.design-approved",
                    "echo ok > .mark/gates/0001-login.design-approved",
                    "cp /tmp/x .mark/features/0001-login/status.md",
                    f"cd {self.wt} && tee .mark/features/0001-login/review-design.md < /dev/null"):
            code, err = bash(self.root, cmd)
            self.assertEqual(code, 2, cmd)
            self.assertIn("only by the `mark` CLI", err)

    def test_main_thread_shell_is_otherwise_free(self):
        for cmd in ("git log > /tmp/log.txt", "touch notes.txt", "mark set 0001 planning --note 'a > b'",
                    "cat .mark/gates/0001-login.ticket-approved > /tmp/copy"):
            self.assertEqual(bash(self.root, cmd)[0], 0, cmd)

    def test_roles_still_follow_their_scope_in_the_shell(self):
        self.assertEqual(bash(self.wt, "touch frontend/x.ts", "coder-plan")[0], 2)
        self.assertEqual(bash(self.wt, "touch frontend/x.ts", "coder-impl")[0], 0)


BUDGET = """
[[doc_budget]]
glob = "docs/archive.md"
max_bytes = 0

[[doc_budget]]
glob = "docs/*.md"
max_bytes = 20
"""


class BudgetTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = make_repo(FULL_CONFIG + BUDGET)
        add_ticket(cls.root, "feature", "0001-login", "developing", gates=["ticket-approved"])
        cls.wt = add_worktree(cls.root, "feature", "0001-login")
        cls.doc = cls.wt / "docs/guide.md"
        cls.doc.parent.mkdir(parents=True, exist_ok=True)

    def test_write_over_budget_is_blocked_with_how_much_to_cut(self):
        code, err = write(self.wt, self.doc, None, content="short line\n" + "y" * 30 + "\n")
        self.assertEqual(code, 2)
        self.assertIn("`docs/guide.md` would be 42 bytes; its doc budget is 20", err)
        self.assertIn("Cut at least 22 bytes", err)
        self.assertIn("L2 (30 B)", err)

    def test_within_budget_exempt_and_unbudgeted_paths_pass(self):
        self.assertEqual(write(self.wt, self.doc, None, content="ok")[0], 0)
        self.assertEqual(write(self.wt, self.wt / "docs/archive.md", None, content="z" * 99)[0], 0)
        self.assertEqual(write(self.wt, self.wt / "README.md", None, content="z" * 99)[0], 0)

    def test_doc_already_over_budget_may_shrink_but_not_grow(self):
        self.doc.write_text("x" * 40)
        self.addCleanup(self.doc.unlink)
        shrink = {"old_string": "xxxxx", "new_string": ""}
        self.assertEqual(write(self.wt, self.doc, None, tool="Edit", **shrink)[0], 0)
        grow = {"old_string": "x", "new_string": "xx"}
        self.assertEqual(write(self.wt, self.doc, None, tool="Edit", **grow)[0], 2)


class EntryTest(unittest.TestCase):
    def test_silent_outside_mark_project(self):
        root = make_project(None)
        self.assertEqual(write(root, root / "frontend/x.ts", "coder-plan"), (0, ""))

    def test_unknown_group_allows(self):
        self.assertEqual(hook("nope", {})[0], 0)


if __name__ == "__main__":
    unittest.main()
