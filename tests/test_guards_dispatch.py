"""pre-dispatch, post-dispatch, subagent-stop and pre-bash guards."""
import json
import os
import time
import unittest

from tests._support import add_origin, add_ticket, add_worktree, hook, make_repo, sh

ALL_GATES = ["ticket-approved", "design-approved", "plan-approved"]


def dispatch(root, role, prompt):
    return hook("pre-dispatch", {"hook_event_name": "PreToolUse", "tool_name": "Agent", "cwd": str(root),
                                 "tool_input": {"subagent_type": role, "prompt": prompt}})


def anchor(kind_dir, ticket_id):
    return f"<!-- mark:ticket {kind_dir}/{ticket_id} -->\nDo the work."


class TargetAndGateTest(unittest.TestCase):
    def setUp(self):
        self.root = make_repo()

    def test_non_pipeline_agent_passes(self):
        self.assertEqual(dispatch(self.root, "Explore", "look around")[0], 0)

    def test_missing_target(self):
        code, err = dispatch(self.root, "designer", "design something")
        self.assertEqual(code, 2)
        self.assertIn("mark:ticket features/<id>", err)

    def test_unknown_ticket(self):
        self.assertIn("does not exist", dispatch(self.root, "designer", anchor("features", "0009-x"))[1])

    def test_ambiguous_target(self):
        add_ticket(self.root, "feature", "0001-a", "designing")
        add_ticket(self.root, "feature", "0002-b", "designing")
        prompt = anchor("features", "0001-a") + anchor("features", "0002-b")
        self.assertIn("several tickets", dispatch(self.root, "designer", prompt)[1])

    def test_anchor_wins_over_reference_paths(self):
        add_ticket(self.root, "feature", "0001-a", "designing")
        add_worktree(self.root, "feature", "0001-a")
        prompt = anchor("features", "0001-a") + "\nSee .mark/features/0002-b/design.md for style."
        self.assertEqual(dispatch(self.root, "designer", prompt)[0], 0)

    def test_short_id_resolves(self):
        add_ticket(self.root, "feature", "0001-a", "designing")
        add_worktree(self.root, "feature", "0001-a")
        self.assertEqual(dispatch(self.root, "designer", anchor("features", "0001"))[0], 0)

    def test_feature_gate_required(self):
        add_ticket(self.root, "feature", "0001-a", "planning", gates=["ticket-approved"])
        add_worktree(self.root, "feature", "0001-a")
        code, err = dispatch(self.root, "coder-plan", anchor("features", "0001-a"))
        self.assertEqual(code, 2)
        self.assertIn("missing `.mark/gates/0001-a.design-approved`", err)

    def test_waived_gate_passes(self):
        add_ticket(self.root, "feature", "0001-a", "planning", gates=["ticket-approved", "design-approved.waived"])
        add_worktree(self.root, "feature", "0001-a")
        self.assertEqual(dispatch(self.root, "coder-plan", anchor("features", "0001-a"))[0], 0)

    def test_bug_chain_has_no_gates(self):
        add_ticket(self.root, "bug", "b0001-crash", "developing", gates=["ticket-approved"])
        add_worktree(self.root, "bug", "b0001-crash")
        self.assertEqual(dispatch(self.root, "coder-impl", anchor("bugs", "b0001-crash"))[0], 0)


class BranchTest(unittest.TestCase):
    def setUp(self):
        self.root = make_repo()
        add_ticket(self.root, "feature", "0001-a", "developing", gates=ALL_GATES)
        self.prompt = anchor("features", "0001-a")

    def test_no_branch_no_worktree(self):
        code, err = dispatch(self.root, "coder-impl", self.prompt)
        self.assertEqual(code, 2)
        self.assertIn('git worktree add ".claude/worktrees/feature-0001-a" "feature/0001-a"', err)

    def test_branch_without_worktree(self):
        sh(self.root, "git", "branch", "feature/0001-a")
        self.assertIn("no worktree", dispatch(self.root, "coder-impl", self.prompt)[1])

    def test_branch_checked_out_in_main(self):
        sh(self.root, "git", "checkout", "-q", "-b", "feature/0001-a")
        self.assertIn("MAIN checkout", dispatch(self.root, "coder-impl", self.prompt)[1])

    def test_wrong_base_branch(self):
        add_ticket(self.root, "feature", "0002-b", "developing", gates=ALL_GATES)
        other = add_worktree(self.root, "feature", "0002-b")
        (other / "b.txt").write_text("b")
        sh(other, "git", "add", ".")
        sh(other, "git", "commit", "-q", "-m", "b work")
        add_worktree(self.root, "feature", "0001-a", base="feature/0002-b")
        code, err = dispatch(self.root, "coder-impl", self.prompt)
        self.assertEqual(code, 2)
        self.assertIn("unmerged branch `feature/0002-b` is its ancestor", err)

    def test_declared_base_branch_is_allowed(self):
        add_ticket(self.root, "feature", "0002-b", "developing", gates=ALL_GATES)
        other = add_worktree(self.root, "feature", "0002-b")
        (other / "b.txt").write_text("b")
        sh(other, "git", "add", ".")
        sh(other, "git", "commit", "-q", "-m", "b work")
        status = self.root / ".mark/features/0001-a/status.md"
        status.write_text(status.read_text().replace("desc: d", "desc: d\nbase-branch: feature/0002-b"))
        sh(self.root, "git", "commit", "-q", "-am", "declare base")
        add_worktree(self.root, "feature", "0001-a", base="feature/0002-b")
        self.assertEqual(dispatch(self.root, "coder-impl", self.prompt)[0], 0)

    def test_remote_backup_required(self):
        add_origin(self.root)
        wt = add_worktree(self.root, "feature", "0001-a")
        self.assertIn("origin/feature/0001-a` does not exist", dispatch(self.root, "coder-impl", self.prompt)[1])
        sh(wt, "git", "push", "-q", "-u", "origin", "feature/0001-a")
        self.assertEqual(dispatch(self.root, "coder-impl", self.prompt)[0], 0)
        sh(self.root, "rm", "-f", str(self.root / ".mark/locks/0001-a.coder-impl.lock"))
        (wt / "x.txt").write_text("x")
        sh(wt, "git", "add", ".")
        sh(wt, "git", "commit", "-q", "-m", "work")
        self.assertIn("1 commit(s) not on origin", dispatch(self.root, "coder-impl", self.prompt)[1])


class CommitAndDedupTest(unittest.TestCase):
    def setUp(self):
        self.root = make_repo()
        self.tdir = add_ticket(self.root, "feature", "0001-a", "developing", gates=ALL_GATES)
        self.wt = add_worktree(self.root, "feature", "0001-a")
        self.prompt = anchor("features", "0001-a")

    def test_uncommitted_status_blocks_dispatch(self):
        (self.tdir / "status.md").write_text((self.tdir / "status.md").read_text() + "\nnote\n")
        code, err = dispatch(self.root, "coder-impl", self.prompt)
        self.assertEqual(code, 2)
        self.assertIn("is not committed", err)

    def test_unpushed_main_blocks_dispatch(self):
        add_origin(self.root)
        sh(self.wt, "git", "push", "-q", "-u", "origin", "feature/0001-a")
        (self.root / "notes.txt").write_text("n")
        sh(self.root, "git", "add", ".")
        sh(self.root, "git", "commit", "-q", "-m", "local only")
        self.assertIn("ahead of origin", dispatch(self.root, "coder-impl", self.prompt)[1])

    def test_second_dispatch_is_blocked_until_ghost_expires(self):
        self.assertEqual(dispatch(self.root, "coder-impl", self.prompt)[0], 0)
        self.assertIn("not confirmed yet", dispatch(self.root, "coder-impl", self.prompt)[1])
        lock = self.root / ".mark/locks/0001-a.coder-impl.lock"
        meta = json.loads(lock.read_text())
        meta["created"] = time.time() - 120
        lock.write_text(json.dumps(meta))
        self.assertEqual(dispatch(self.root, "coder-impl", self.prompt)[0], 0)

    def test_other_roles_are_independent(self):
        self.assertEqual(dispatch(self.root, "coder-impl", self.prompt)[0], 0)
        self.assertEqual(dispatch(self.root, "tester", self.prompt)[0], 0)


class LifecycleTest(unittest.TestCase):
    def setUp(self):
        self.root = make_repo()
        add_ticket(self.root, "feature", "0001-a", "developing", gates=ALL_GATES)
        self.wt = add_worktree(self.root, "feature", "0001-a")
        self.lock = self.root / ".mark/locks/0001-a.coder-impl.lock"

    def start(self, prompt=None):
        prompt = prompt or anchor("features", "0001-a")
        self.assertEqual(dispatch(self.root, "coder-impl", prompt)[0], 0)
        hook("post-dispatch", {"hook_event_name": "PostToolUse", "tool_name": "Agent", "cwd": str(self.root),
                               "tool_input": {"subagent_type": "coder-impl", "prompt": prompt},
                               "tool_response": {"agentId": "agent-1"}})

    def stop(self, active=False, message=None):
        payload = {"hook_event_name": "SubagentStop", "cwd": str(self.root), "agent_id": "agent-1",
                   "agent_type": "coder-impl", "stop_hook_active": active}
        if message is not None:
            payload["last_assistant_message"] = message
        return hook("subagent-stop", payload)

    def test_bound_lock_blocks_duplicates(self):
        self.start()
        self.assertEqual(json.loads(self.lock.read_text())["agent_id"], "agent-1")
        self.assertIn("already working", dispatch(self.root, "coder-impl", anchor("features", "0001-a"))[1])

    def test_missing_output_keeps_subagent_running(self):
        self.start()
        code, err = self.stop()
        self.assertEqual(code, 2)
        self.assertIn("handoff.md", err)
        self.assertTrue(self.lock.exists())

    def test_output_in_worktree_releases_lock(self):
        self.start()
        (self.wt / ".mark/features/0001-a/handoff.md").write_text("done")
        self.assertEqual(self.stop()[0], 0)
        self.assertFalse(self.lock.exists())
        result = json.loads((self.root / ".mark/locks/0001-a.coder-impl.result.json").read_text())
        self.assertEqual(result["result"], "PASSED")
        self.assertEqual(result["conclusion"], "")

    def test_result_keeps_the_final_report(self):
        self.start()
        (self.wt / ".mark/features/0001-a/handoff.md").write_text("done")
        self.assertEqual(self.stop(message="0001-a · coder-impl · outcome: testing\n")[0], 0)
        result = json.loads((self.root / ".mark/locks/0001-a.coder-impl.result.json").read_text())
        self.assertEqual(result["conclusion"], "0001-a · coder-impl · outcome: testing")

    def test_second_stop_attempt_releases_with_failure(self):
        self.start()
        self.assertEqual(self.stop(active=True)[0], 0)
        self.assertFalse(self.lock.exists())
        result = json.loads((self.root / ".mark/locks/0001-a.coder-impl.result.json").read_text())
        self.assertEqual(result["result"], "FAILED")

    def test_outputs_anchor_overrides_default(self):
        self.start(anchor("features", "0001-a") + "\n<!-- mark:outputs design-qa.md -->")
        self.assertEqual(json.loads(self.lock.read_text())["required"], ["design-qa.md"])

    def post(self):
        prompt = anchor("features", "0001-a")
        hook("post-dispatch", {"hook_event_name": "PostToolUse", "tool_name": "Agent", "cwd": str(self.root),
                               "tool_input": {"subagent_type": "coder-impl", "prompt": prompt},
                               "tool_response": {"agentId": "agent-1"}})

    def test_foreground_order_stop_before_post(self):
        self.assertEqual(dispatch(self.root, "coder-impl", anchor("features", "0001-a"))[0], 0)
        self.assertEqual(self.stop()[0], 2)          # no output yet, lock bound on the fly
        self.assertEqual(json.loads(self.lock.read_text())["agent_id"], "agent-1")
        (self.wt / ".mark/features/0001-a/handoff.md").write_text("done")
        self.assertEqual(self.stop()[0], 0)
        self.post()                                   # arrives after the agent finished
        self.assertFalse(self.lock.exists())

    def test_ambiguous_unbound_locks_are_left_alone(self):
        add_ticket(self.root, "feature", "0002-b", "developing", gates=ALL_GATES)
        add_worktree(self.root, "feature", "0002-b")
        dispatch(self.root, "coder-impl", anchor("features", "0001-a"))
        dispatch(self.root, "coder-impl", anchor("features", "0002-b"))
        self.assertEqual(self.stop()[0], 0)
        self.assertTrue(self.lock.exists())

    def test_unrelated_agent_stop_is_ignored(self):
        self.assertEqual(hook("subagent-stop", {"cwd": str(self.root), "agent_id": "zzz"})[0], 0)


def bash(root, command, agent=None):
    payload = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "cwd": str(root),
               "tool_input": {"command": command}}
    if agent:
        payload["agent_type"] = agent
    return hook("pre-bash", payload)


class BashTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = make_repo()
        add_ticket(cls.root, "feature", "0001-a", "developing", gates=ALL_GATES)
        cls.wt = add_worktree(cls.root, "feature", "0001-a")

    def test_subagent_commit_on_main_is_blocked(self):
        self.assertEqual(bash(self.root, "git add . && git commit -m x", "coder-impl")[0], 2)

    def test_subagent_commit_in_worktree_is_allowed(self):
        self.assertEqual(bash(self.root, f'git -C "{self.wt}" commit -m x', "coder-impl")[0], 0)
        self.assertEqual(bash(self.root, f'cd "{self.wt}" && git commit -m x', "coder-impl")[0], 0)

    def test_main_thread_commits_state_on_main(self):
        self.assertEqual(bash(self.root, "git commit -m 'status'")[0], 0)

    def test_subagent_push_to_main_is_blocked(self):
        self.assertEqual(bash(self.root, "git push origin main", "tester")[0], 2)
        self.assertEqual(bash(self.wt, "git push origin feature/0001-a", "tester")[0], 0)

    def test_checking_out_ticket_branch_in_main_is_blocked(self):
        code, err = bash(self.root, "git checkout feature/0001-a")
        self.assertEqual(code, 2)
        self.assertIn("git worktree add", err)

    def test_merging_ticket_branch_into_main_by_hand_is_blocked(self):
        code, err = bash(self.root, "git merge --no-ff feature/0001-a")
        self.assertEqual(code, 2)
        self.assertIn("mark merge", err)
        self.assertEqual(bash(self.root, "git merge origin/bug/b0002-x")[0], 2)
        code, err = bash(self.root, "git merge chore/general-20260101-000000")
        self.assertEqual(code, 2)
        self.assertIn("mark general merge", err)
        self.assertEqual(bash(self.wt, "git merge main")[0], 0)   # main into the ticket branch
        self.assertEqual(bash(self.root, "git merge --abort")[0], 0)

    def test_heredoc_body_is_not_a_command(self):
        cmd = "cat > notes.txt <<'EOF'\ngit commit -m x\nEOF"
        self.assertEqual(bash(self.root, cmd, "coder-impl")[0], 0)

    def test_env_prefix_and_global_options(self):
        self.assertEqual(bash(self.root, "GIT_EDITOR=true git -c core.x=1 commit -m x", "tester")[0], 2)


if __name__ == "__main__":
    unittest.main()
