"""pre-write guards: scope, worktree, ticket, status (run through the real hook)."""
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

    def test_main_thread_may_edit_control_files_in_worktree(self):
        self.assertEqual(write(self.wt, self.wt / ".claude/agents/designer.md")[0], 0)

    def test_unmatched_path_is_open(self):
        self.assertEqual(write(self.wt, self.wt / "README.md", "tester")[0], 0)

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


class TicketTest(unittest.TestCase):
    def setUp(self):
        self.root = make_repo()
        self.tdir = add_ticket(self.root, "bug", "b0001-crash", "planning")

    def test_artifact_without_ticket_approval_is_blocked(self):
        code, err = write(self.root, self.tdir / "bug.md")
        self.assertEqual(code, 2)
        self.assertIn("touch .mark/gates/b0001-crash.ticket-approved", err)

    def test_status_file_needs_no_approval(self):
        self.assertEqual(write(self.root, self.tdir / "status.md", content=status_text("planning"))[0], 0)

    def test_approved_ticket_accepts_artifacts(self):
        (self.root / ".mark" / "gates").mkdir()
        (self.root / ".mark" / "gates" / "b0001-crash.ticket-approved").write_text("ok")
        self.assertEqual(write(self.root, self.tdir / "bug.md")[0], 0)


class StatusTest(unittest.TestCase):
    def setUp(self):
        self.root = make_repo()
        self.tdir = add_ticket(self.root, "feature", "0001-login", "designing", gates=["ticket-approved"])
        self.status = self.tdir / "status.md"

    def test_legal_move(self):
        self.assertEqual(write(self.root, self.status, content=status_text("review-design"))[0], 0)

    def test_skipping_a_review_gate_is_blocked(self):
        code, err = write(self.root, self.status, content=status_text("planning"))
        self.assertEqual(code, 2)
        self.assertIn("Illegal status move `designing` -> `planning`", err)

    def test_edit_is_simulated(self):
        payload = {"old_string": "status: designing", "new_string": "status: developing"}
        code, err = write(self.root, self.status, tool="Edit", **payload)
        self.assertEqual(code, 2)
        self.assertIn("Illegal status move", err)

    def test_invalid_content_is_blocked(self):
        code, err = write(self.root, self.status, content=status_text("designing", desc="x" * 201))
        self.assertEqual(code, 2)
        self.assertIn("`desc` is 201 chars", err)

    def test_status_cannot_change_in_worktree(self):
        sh(self.root, "git", "add", ".")
        wt = add_worktree(self.root, "feature", "0001-login")
        code, err = write(wt, wt / ".mark/features/0001-login/status.md", content=status_text("review-design"))
        self.assertEqual(code, 2)
        self.assertIn("only changes in the main checkout", err)

    def test_status_only_on_main_branch(self):
        sh(self.root, "git", "checkout", "-q", "-b", "side")
        code, err = write(self.root, self.status, content=status_text("review-design"))
        self.assertEqual(code, 2)
        self.assertIn("main checkout is on `side`", err)


def merge_status(status, after):
    return status_text(status, **{"merge-after": after, "leftover": "0"})


class MergeAfterTest(unittest.TestCase):
    def setUp(self):
        self.root = make_repo()
        add_ticket(self.root, "feature", "0002-dep", "testing", gates=["ticket-approved"])
        self.tdir = add_ticket(self.root, "feature", "0001-login", "pending-merge", gates=["ticket-approved"])
        self.status = self.tdir / "status.md"
        self.status.write_text(merge_status("pending-merge", "[0002]"))

    def test_removing_an_entry_is_blocked_adding_is_free(self):
        code, err = write(self.root, self.status, content=merge_status("pending-merge", "[]"))
        self.assertEqual(code, 2)
        self.assertIn("removes `merge-after` entries (0002)", err)
        add = merge_status("pending-merge", "[0002, b0009]")
        self.assertEqual(write(self.root, self.status, content=add)[0], 0)

    def test_passed_by_hand_needs_dependencies(self):
        code, err = write(self.root, self.status, content=merge_status("passed", "[0002]"))
        self.assertEqual(code, 2)
        self.assertIn("0002-dep (testing)", err)


class EntryTest(unittest.TestCase):
    def test_silent_outside_mark_project(self):
        root = make_project(None)
        self.assertEqual(write(root, root / "frontend/x.ts", "coder-plan"), (0, ""))

    def test_unknown_group_allows(self):
        self.assertEqual(hook("nope", {})[0], 0)


if __name__ == "__main__":
    unittest.main()
