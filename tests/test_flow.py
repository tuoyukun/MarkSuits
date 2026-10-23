"""Orchestration: review rounds, human tokens, next action, status moves, approve/reject, dispatch."""
import io
import json
import os
import time
import socket
import unittest
import zlib

from tests._support import (FULL_CONFIG, add_origin, add_templates, add_ticket, add_worktree, hook,
                            human_typed, make_project, make_repo, sh, status_text)

from mark import cli, flow, human, reviews, states, tickets
from mark.config import load_config

ALL_GATES = ["ticket-approved", "design-approved", "plan-approved"]


def run(root, *argv):
    out, err = io.StringIO(), io.StringIO()
    code = cli.main(list(argv), cwd=root, out=out, err=err)
    return code, out.getvalue(), err.getvalue()


def ctx_of(root, ref):
    return flow.load(load_config(root), ref)


def ctx_next(root, ref):
    return flow.next_action(ctx_of(root, ref))


def write(path, text=""):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class ReviewsTest(unittest.TestCase):
    def test_rounds_number_across_rounds_and_settle(self):
        p = make_project() / "review-design.md"
        self.assertEqual(reviews.append_round(p, "en", "0001-a", "design", ["too slow", "no label"],
                                              now="T1"), (1, ["R-1", "R-2"]))
        self.assertEqual(reviews.settle(p, "en"), [1])
        n, refs = reviews.append_round(p, "en", "0001-a", "design", ["drop R-1"], now="T2")
        self.assertEqual((n, refs), (2, ["R-3"]))
        rounds = reviews.read(p)
        self.assertEqual([(r.number, r.pending, r.refs) for r in rounds],
                         [(1, False, ["R-1", "R-2"]), (2, True, ["R-3"])])
        text = p.read_text()
        self.assertIn("## Round 1 · T1 · done <!-- mark:round 1 done -->", text)
        self.assertIn("- R-1: too slow", text)

    def test_localized_heading(self):
        p = make_project() / "review-plan.md"
        reviews.append_round(p, "zh-CN", "0001-a", "plan", ["x"], now="T")
        self.assertIn("## 第 1 轮 · T · 待处理 <!-- mark:round 1 pending -->", p.read_text())
        reviews.settle(p, "zh-CN")
        self.assertIn("## 第 1 轮 · T · 已处理 <!-- mark:round 1 done -->", p.read_text())


class HumanTokenTest(unittest.TestCase):
    def setUp(self):
        self.root = make_project()
        self.cfg = load_config(self.root)

    def test_parse(self):
        self.assertEqual(human.parse_prompt("/mark:approve 0012"), ("approve", "0012", []))
        self.assertEqual(human.parse_prompt("  /reject b0003 too slow"), ("reject", "b0003", ["too", "slow"]))
        self.assertEqual(human.parse_prompt("/mark:approve 0012 planning。\nmore"), ("approve", "0012", ["planning"]))
        self.assertIsNone(human.parse_prompt("please approve 0012"))
        self.assertIsNone(human.parse_prompt("/mark:status"))

    def test_resuming_a_ticket_opens_nothing(self):
        self.assertIsNone(human.record(self.cfg, "/mark:feature 0012"))
        self.assertIsNotNone(human.record(self.cfg, "/mark:feature add dark mode"))

    def test_consume_matches_ticket_once(self):
        human.record(self.cfg, "/mark:approve 0012")
        self.assertFalse(human.consume(self.cfg, ("approve",), "0013-x"))
        self.assertFalse(human.consume(self.cfg, ("reject",), "0012-x"))
        self.assertTrue(human.consume(self.cfg, ("approve",), "0012-x"))
        self.assertFalse(human.consume(self.cfg, ("approve",), "0012-x"))

    def test_tokens_expire(self):
        human.record(self.cfg, "/mark:approve 0012", now=time.time() - human.TOKEN_TTL["approve"] - 1)
        self.assertFalse(human.consume(self.cfg, ("approve",), "0012-x"))

    def test_opening_tokens_expire_sooner(self):
        human.record(self.cfg, "/mark:feature dark mode", now=time.time() - 3 * 3600)
        self.assertFalse(human.consume(self.cfg, ("feature",)))
        human.record(self.cfg, "/mark:feature dark mode", now=time.time() - 3600)
        self.assertTrue(human.consume(self.cfg, ("feature",)))

    def test_token_without_ticket_approves_nothing(self):
        human.record(self.cfg, "/mark:approve")
        self.assertFalse(human.consume(self.cfg, ("approve",), "0012-x"))

    def test_word_must_be_what_the_human_typed(self):
        human.record(self.cfg, "/mark:approve 0012 planning")
        self.assertFalse(human.consume(self.cfg, ("approve",), "0012-x", word="developing"))
        self.assertTrue(human.consume(self.cfg, ("approve",), "0012-x", word="planning"))

    def test_hook_records_token(self):
        self.assertEqual(human_typed(self.root, "/mark:reject 0012 nope")[0], 0)
        self.assertTrue(human.consume(self.cfg, ("reject",), "0012-a"))


class NextActionTest(unittest.TestCase):
    def setUp(self):
        self.root = make_repo()

    def next(self, ref, **kw):
        return flow.next_action(ctx_of(self.root, ref), **kw)

    def test_feature_initial_needs_requirement(self):
        d = add_ticket(self.root, "feature", "0001-a", "designing", gates=["ticket-approved"])
        self.assertEqual(self.next("0001").message, "next.no_brief")
        write(d / "requirement.md", "AC-1")
        a = self.next("0001")
        self.assertEqual((a.kind, a.role, a.scenario), ("dispatch", "designer", "designer-initial"))

    def test_unapproved_ticket_stops(self):
        add_ticket(self.root, "feature", "0001-a", "designing")
        self.assertEqual(self.next("0001").message, "next.ticket_gate")

    def test_review_rework_carries_pending_rounds(self):
        d = add_ticket(self.root, "feature", "0001-a", "designing", gates=["ticket-approved"])
        reviews.append_round(d / "review-design.md", "en", "0001-a", "design", ["a", "b"])
        reviews.settle(d / "review-design.md", "en")
        reviews.append_round(d / "review-design.md", "en", "0001-a", "design", ["c"])
        a = self.next("0001")
        self.assertEqual(a.scenario, "designer-review-rework")
        self.assertEqual((a.pending_rounds, a.pending_refs), ([2], ["R-3"]))

    def test_designer_rework_after_test_failure(self):
        d = add_ticket(self.root, "feature", "0001-a", "designing", gates=["ticket-approved"])
        write(d / "verdict.md", "FAIL-2 and FAIL-10")
        a = self.next("0001")
        self.assertEqual(a.scenario, "designer-rework")
        self.assertEqual(a.trigger, "FAIL-2, FAIL-10 (verdict.md)")

    def test_artifacts_found_in_worktree(self):
        add_ticket(self.root, "feature", "0001-a", "testing", gates=ALL_GATES)
        self.assertEqual(self.next("0001").scenario, "tester-initial")
        wt = add_worktree(self.root, "feature", "0001-a")
        write(wt / ".mark/features/0001-a/verdict.md", "FAIL-1")
        self.assertEqual(self.next("0001").scenario, "tester-reverify")

    def test_failed_impl_routes_by_trigger(self):
        d = add_ticket(self.root, "feature", "0001-a", "failed-impl", gates=ALL_GATES)
        write(d / "design-qa.md", "D-1 <!-- mark:qa blocked -->")
        a = self.next("0001")
        self.assertEqual((a.scenario, a.trigger), ("coder-impl-fix", "D-1 (design-qa.md)"))
        reviews.append_round(d / "review-merge.md", "en", "0001-a", "merge", ["rename it"])
        self.assertEqual(self.next("0001").scenario, "coder-impl-merge-rework")

    def test_bug_chain_scenarios(self):
        d = add_ticket(self.root, "bug", "b0001-crash", "planning", gates=["ticket-approved"])
        write(d / "bug.md", "crash")
        self.assertEqual(self.next("b0001").scenario, "fix-plan-initial")
        write(d / "fix-plan.md", "plan")
        self.assertEqual(self.next("b0001").scenario, "fix-plan-rework")

    def test_human_and_terminal_statuses(self):
        cases = [("0001-r", "review-plan", "next.review"), ("0002-m", "pending-merge", "next.merge"),
                 ("0003-b", "blocked-plan", "next.blocked_plan")]
        for ticket_id, status, key in cases:
            add_ticket(self.root, "feature", ticket_id, status, gates=ALL_GATES)
            self.assertEqual(self.next(ticket_id).message, key)
        p = add_ticket(self.root, "feature", "0009-done", "passed") / "status.md"
        p.write_text(p.read_text().replace("desc:", "leftover: 0\ndesc:"))
        self.assertEqual(self.next("0009").kind, "done")

    def test_lock_means_wait_and_result_means_record(self):
        d = add_ticket(self.root, "feature", "0001-a", "planning", gates=ALL_GATES)
        locks = self.root / ".mark" / "locks"
        write(locks / "0001-a.coder-plan.lock", "{}")
        self.assertEqual(self.next("0001").kind, "wait")
        (locks / "0001-a.coder-plan.lock").unlink()
        result = locks / "0001-a.coder-plan.result.json"
        write(result, json.dumps({"result": "PASSED", "reason": "outputs present",
                                  "at": (d / "status.md").stat().st_mtime + 5}))
        a = self.next("0001")
        self.assertEqual((a.kind, a.options), ("record", ["blocked-unclear", "review-plan"]))
        self.assertEqual(a.params["wrapup"], "")
        write(result, json.dumps({"result": "FAILED", "reason": "missing", "at": time.time() + 5}))
        self.assertEqual(self.next("0001").message, "next.output_failed")
        self.assertEqual(self.next("0001", retry=True).kind, "dispatch")

    def test_dispatch_that_never_started_is_not_waited_on(self):
        add_ticket(self.root, "feature", "0001-a", "planning", gates=ALL_GATES)
        lock = self.root / ".mark/locks/0001-a.coder-plan.lock"
        write(lock, json.dumps({"created": time.time() - 120}))
        self.assertEqual(self.next("0001").kind, "dispatch")
        write(lock, json.dumps({"created": time.time() - 120, "agent_id": "a1"}))
        self.assertEqual(self.next("0001").kind, "wait")

    def test_design_review_points_at_preview(self):
        add_ticket(self.root, "feature", "0001-a", "review-design", gates=["ticket-approved"])
        self.assertEqual(self.next("0001").params["preview"], "")
        wt = add_worktree(self.root, "feature", "0001-a")
        write(wt / ".mark/features/0001-a/preview.html", "<html></html>")
        self.assertIn(str(wt / ".mark/features/0001-a/preview.html"), self.next("0001").params["preview"])

    def test_record_before_pending_merge_mentions_wrap_up(self):
        d = add_ticket(self.root, "bug", "b0001-a", "testing", gates=ALL_GATES)
        write(self.root / ".mark/locks/b0001-a.tester.result.json",
              json.dumps({"result": "PASSED", "at": (d / "status.md").stat().st_mtime + 5}))
        a = self.next("b0001")
        self.assertIn("pending-merge", a.options)
        self.assertIn("log.md", a.params["wrapup"])
        self.assertIn("mark commit b0001-a", a.params["wrapup"])
        self.assertNotIn("design-flaw", a.params["route"])   # a bug has no designer

    def test_tester_failures_are_routed_by_failure_type(self):
        d = add_ticket(self.root, "feature", "0001-a", "testing", gates=ALL_GATES)
        write(self.root / ".mark/locks/0001-a.tester.result.json",
              json.dumps({"result": "PASSED", "at": (d / "status.md").stat().st_mtime + 5}))
        a = self.next("0001")
        self.assertIn("`design-flaw` -> `blocked-spec`", a.params["route"])

    def test_coder_impl_can_send_a_ui_fix_to_the_designer(self):
        for status in ("developing", "failed-impl"):
            self.assertTrue(states.can_move("feature", status, "blocked-spec"), status)
            self.assertFalse(states.can_move("bug", status, "blocked-spec"), status)

    def test_previous_conclusion_is_the_newest_result(self):
        add_ticket(self.root, "feature", "0001-a", "planning", gates=ALL_GATES)
        ctx = ctx_of(self.root, "0001")
        self.assertEqual(flow.previous_conclusion(ctx), "")
        locks = self.root / ".mark/locks"
        write(locks / "0001-a.designer.result.json", json.dumps({"at": 10, "conclusion": "design done"}))
        write(locks / "0001-a.coder-plan.result.json", json.dumps({"at": 20, "conclusion": "plan done"}))
        write(locks / "0002-b.tester.result.json", json.dumps({"at": 30, "conclusion": "other ticket"}))
        self.assertEqual(flow.previous_conclusion(ctx), "plan done")

    def test_stale_result_is_ignored(self):
        d = add_ticket(self.root, "feature", "0001-a", "planning", gates=ALL_GATES)
        write(self.root / ".mark/locks/0001-a.coder-plan.result.json",
              json.dumps({"result": "PASSED", "at": (d / "status.md").stat().st_mtime - 5}))
        self.assertEqual(self.next("0001").kind, "dispatch")


class NoDesignerTest(unittest.TestCase):
    """`profile = "service"`: features skip the designer."""

    def setUp(self):
        self.root = make_repo('mark_schema = 1\nlocale = "en"\nprofile = "service"\n[project]\nmain_branch = "main"\n')

    def test_feature_starts_at_planning_and_needs_its_requirement(self):
        t = tickets.claim(load_config(self.root), "feature", "add an endpoint")
        self.assertEqual(t.status, "planning")
        self.assertEqual(t.get("owner"), "coder-plan")
        gate = self.root / ".mark/gates" / f"{t.id}.ticket-approved"
        write(gate, "ok\n")
        self.assertEqual(ctx_next(self.root, t.id).message, "next.no_brief")
        write(t.path.parent / "requirement.md", "AC-1")
        a = ctx_next(self.root, t.id)
        self.assertEqual((a.kind, a.role, a.scenario), ("dispatch", "coder-plan", "coder-plan"))

    def test_no_move_to_a_designer_status(self):
        add_ticket(self.root, "feature", "0001-a", "blocked-unclear", gates=ALL_GATES)
        ctx = ctx_of(self.root, "0001")
        self.assertNotIn("designing", flow.approve_targets(ctx))
        with self.assertRaises(flow.FlowError) as e:
            flow._move(ctx, "designing", None)
        self.assertEqual(e.exception.key, "flow.no_role")

    def test_blocked_spec_goes_back_to_planning(self):
        add_ticket(self.root, "feature", "0001-a", "blocked-spec", gates=ALL_GATES)
        human_typed(self.root, "/mark:approve 0001")
        code, out, err = run(self.root, "approve", "0001")
        self.assertEqual(code, 0, err)
        self.assertIn("status: planning", (self.root / ".mark/features/0001-a/status.md").read_text())


class MovesTest(unittest.TestCase):
    def setUp(self):
        self.root = make_repo()
        self.origin = add_origin(self.root)

    def status(self, kind_dir, ticket_id):
        return (self.root / ".mark" / kind_dir / ticket_id / "status.md").read_text()

    def test_set_validates_commits_and_pushes(self):
        add_ticket(self.root, "feature", "0001-a", "designing", gates=["ticket-approved"])
        code, out, err = run(self.root, "set", "0001", "review-design", "--note", "design ready")
        self.assertEqual(code, 0, err)
        self.assertIn("`designing` -> `review-design`", out)
        text = self.status("features", "0001-a")
        self.assertIn("status: review-design\nowner: human", text)
        self.assertIn("design ready", text)
        self.assertEqual(sh(self.root, "git", "status", "--porcelain"), "")
        self.assertEqual(sh(self.root, "git", "rev-parse", "main"), sh(self.root, "git", "rev-parse", "origin/main"))

    def test_set_refuses_illegal_and_gate_moves(self):
        add_ticket(self.root, "feature", "0001-a", "designing", gates=["ticket-approved"])
        code, _, err = run(self.root, "set", "0001", "developing")
        self.assertEqual(code, 1)
        self.assertIn("Illegal move", err)
        run(self.root, "set", "0001", "review-design")
        code, _, err = run(self.root, "set", "0001", "planning")
        self.assertEqual(code, 1)
        self.assertIn("waits on the human", err)

    def test_set_cannot_leave_human_states(self):
        for status, new in (("blocked-spec", "developing"), ("blocked-plan", "planning"),
                            ("blocked-unclear", "developing"), ("pending-merge", "failed-impl")):
            add_ticket(self.root, "feature", f"0001-{status}", status, gates=ALL_GATES)
            code, _, err = run(self.root, "set", f"0001-{status}", new, "--no-commit")
            self.assertEqual(code, 1, status)
            self.assertIn("waits on the human", err)
            self.assertEqual(run(self.root, "set", f"0001-{status}", "superseded", "--no-commit")[0], 0, status)

    def test_design_qa_must_pass_before_testing(self):
        add_ticket(self.root, "feature", "0001-a", "design-qa", gates=ALL_GATES)
        qa = self.root / ".mark/features/0001-a/design-qa.md"
        write(qa, "<!-- mark:qa-round 1 -->\nD-1\n<!-- mark:qa blocked -->")
        code, _, err = run(self.root, "set", "0001", "testing", "--no-commit")
        self.assertEqual(code, 1)
        self.assertIn("mark:qa passed", err)
        write(qa, "<!-- mark:qa-round 1 -->\n<!-- mark:qa passed -->")
        self.assertEqual(run(self.root, "set", "0001", "testing", "--no-commit")[0], 0)

    def test_pending_merge_needs_leftover(self):
        add_ticket(self.root, "feature", "0001-a", "testing", gates=ALL_GATES)
        self.assertIn("leftover", run(self.root, "set", "0001", "pending-merge")[2])
        self.assertEqual(run(self.root, "set", "0001", "pending-merge", "--leftover", "0")[0], 0)

    def test_design_qa_required_for_ui_changes(self):
        cfg_path = self.root / ".mark" / "config.toml"
        cfg_path.write_text(cfg_path.read_text() + '\n[design_qa]\npaths = ["frontend/**"]\n'
                            'exclude = ["**/__tests__/**"]\n')
        sh(self.root, "git", "commit", "-qam", "qa config")
        sh(self.root, "git", "push", "-q", "origin", "main")
        add_ticket(self.root, "feature", "0001-a", "developing", gates=ALL_GATES)
        sh(self.root, "git", "push", "-q", "origin", "main")
        wt = add_worktree(self.root, "feature", "0001-a", base="origin/main")
        write(wt / ".mark/features/0001-a/design.md", "d")
        write(wt / "frontend/__tests__/a.test.ts", "t")
        sh(wt, "git", "add", ".")
        sh(wt, "git", "commit", "-qm", "tests only")
        self.assertEqual(run(self.root, "set", "0001", "testing", "--no-commit")[0], 0)

        run(self.root, "set", "0001", "failed-impl", "--no-commit")
        write(wt / "frontend/src/page.tsx", "x")
        sh(wt, "git", "add", ".")
        sh(wt, "git", "commit", "-qm", "ui")
        code, _, err = run(self.root, "set", "0001", "testing", "--no-commit")
        self.assertEqual(code, 1)
        self.assertIn("mark set 0001-a design-qa", err)
        write(wt / ".mark/features/0001-a/design-qa.md", "<!-- mark:qa passed -->")
        self.assertEqual(run(self.root, "set", "0001", "testing", "--no-commit")[0], 0)

    def test_design_qa_stops_after_two_blocked_rounds(self):
        add_ticket(self.root, "feature", "0001-a", "design-qa", gates=ALL_GATES)
        qa = self.root / ".mark/features/0001-a/design-qa.md"
        write(qa, "<!-- mark:qa-round 1 -->\nD-1\n<!-- mark:qa blocked -->")
        self.assertEqual(run(self.root, "set", "0001", "failed-impl", "--no-commit")[0], 0)
        run(self.root, "set", "0001", "design-qa", "--no-commit")
        write(qa, "<!-- mark:qa-round 2 -->\nD-2\n<!-- mark:qa blocked -->")
        code, _, err = run(self.root, "set", "0001", "failed-impl", "--no-commit")
        self.assertEqual(code, 1)
        self.assertIn("mark set 0001-a blocked-spec", err)
        self.assertEqual(run(self.root, "set", "0001", "blocked-spec", "--no-commit")[0], 0)

    def test_passed_requires_merged_branch(self):
        add_ticket(self.root, "bug", "b0001-x", "pending-merge", gates=["ticket-approved"])
        p = self.root / ".mark/bugs/b0001-x/status.md"
        p.write_text(p.read_text().replace("desc:", "leftover: 0\ndesc:"))
        sh(self.root, "git", "commit", "-qam", "leftover")
        wt = add_worktree(self.root, "bug", "b0001-x")
        write(wt / "fix.txt", "fix")
        sh(wt, "git", "add", ".")
        sh(wt, "git", "commit", "-qm", "fix")
        code, _, err = run(self.root, "set", "b0001", "passed")
        self.assertEqual(code, 1)
        self.assertIn("1 commit(s) not on main", err)
        sh(self.root, "git", "merge", "-q", "--ff-only", "bug/b0001-x")
        self.assertEqual(run(self.root, "set", "b0001", "passed")[0], 0)


class MergeTest(unittest.TestCase):
    def setUp(self):
        self.root = make_repo()
        self.origin = add_origin(self.root)
        self.dir = add_ticket(self.root, "bug", "b0001-x", "pending-merge", gates=["ticket-approved"])
        p = self.dir / "status.md"
        p.write_text(p.read_text().replace("desc:", "leftover: 0\ndesc:"))
        sh(self.root, "git", "commit", "-qam", "leftover")
        sh(self.root, "git", "push", "-q", "origin", "main")
        self.wt = add_worktree(self.root, "bug", "b0001-x")
        self.commit_wt("fix.txt", "fix", verdict="PASSED")
        sh(self.wt, "git", "push", "-q", "-u", "origin", "bug/b0001-x")

    def commit_wt(self, name, text, verdict=None):
        write(self.wt / name, text)
        if verdict:
            write(self.wt / ".mark/bugs/b0001-x/verdict.md", f"<!-- mark:verdict {verdict} -->\n")
        sh(self.wt, "git", "add", ".")
        sh(self.wt, "git", "commit", "-qm", name)

    def regression(self, cmd):
        cfg = self.root / ".mark/config.toml"
        cfg.write_text(cfg.read_text() + f'\n[merge]\nregression = "{cmd}"\n')
        sh(self.root, "git", "commit", "-qam", "regression")
        sh(self.root, "git", "push", "-q", "origin", "main")

    def test_next_says_merge(self):
        self.assertEqual(ctx_next(self.root, "b0001").kind, "merge")

    def test_merges_latest_main_runs_regression_and_cleans_up(self):
        self.regression("test -f fix.txt && test -f other.txt")  # sees both sides of the merge
        write(self.root / "other.txt", "o")
        sh(self.root, "git", "add", "other.txt")
        sh(self.root, "git", "commit", "-qm", "main moved")
        sh(self.root, "git", "push", "-q", "origin", "main")
        code, out, err = run(self.root, "merge", "b0001")
        self.assertEqual(code, 0, err + out)
        self.assertIn("Regression passed", out)
        self.assertTrue((self.root / "fix.txt").is_file())
        self.assertIn("status: passed", (self.dir / "status.md").read_text())
        self.assertEqual(sh(self.root, "git", "rev-parse", "main"), sh(self.root, "git", "rev-parse", "origin/main"))
        self.assertEqual(sh(self.root, "git", "status", "--porcelain", "--untracked-files=no"), "")
        self.assertFalse(self.wt.exists())
        self.assertEqual(sh(self.root, "git", "branch", "--list", "bug/*"), "")
        self.assertNotIn("bug/b0001-x", sh(self.root, "git", "ls-remote", "--heads", "origin"))
        self.assertEqual(ctx_next(self.root, "b0001").kind, "done")

    def test_red_regression_lands_nothing_and_next_stops(self):
        self.regression("echo boom && exit 3")
        before = sh(self.root, "git", "rev-parse", "main")
        code, _, err = run(self.root, "merge", "b0001")
        self.assertEqual(code, 1)
        self.assertIn("exit 3", err)
        self.assertIn("boom", err)
        self.assertEqual(sh(self.root, "git", "rev-parse", "main"), before)
        self.assertIn("status: pending-merge", (self.dir / "status.md").read_text())
        action = ctx_next(self.root, "b0001")
        self.assertEqual((action.kind, action.message), ("stop", "next.merge_failed"))
        self.assertIn("boom", action.params["reason"])

    def test_conflict_aborts(self):
        write(self.root / "fix.txt", "main side")
        sh(self.root, "git", "add", "fix.txt")
        sh(self.root, "git", "commit", "-qm", "conflicting")
        sh(self.root, "git", "push", "-q", "origin", "main")
        code, _, err = run(self.root, "merge", "b0001")
        self.assertEqual(code, 1)
        self.assertIn("conflicts", err)
        self.assertEqual(sh(self.wt, "git", "status", "--porcelain"), "")
        self.assertEqual((self.root / "fix.txt").read_text(), "main side")

    def test_doc_grown_past_budget_lands_nothing(self):
        cfg = self.root / ".mark/config.toml"
        cfg.write_text(cfg.read_text() + '\n[[doc_budget]]\nglob = "*.md"\nmax_bytes = 10\n')
        sh(self.root, "git", "commit", "-qam", "budget")
        sh(self.root, "git", "push", "-q", "origin", "main")
        self.commit_wt("NOTES.md", "n" * 11)  # e.g. written through Bash, past the pre-write guard
        before = sh(self.root, "git", "rev-parse", "main")
        code, _, err = run(self.root, "merge", "b0001")
        self.assertEqual(code, 1)
        self.assertIn("NOTES.md (11 B > 10 B)", err)
        self.assertEqual(sh(self.root, "git", "rev-parse", "main"), before)
        self.commit_wt("NOTES.md", "short")
        code, out, err = run(self.root, "merge", "b0001")
        self.assertEqual(code, 0, err + out)

    def test_needs_passing_verdict_and_merge_after(self):
        self.commit_wt("more.txt", "m", verdict="FAILED")
        code, _, err = run(self.root, "merge", "b0001")
        self.assertEqual(code, 1)
        self.assertIn("mark:verdict PASSED", err)
        self.commit_wt("more2.txt", "m", verdict="PASSED")
        add_ticket(self.root, "feature", "0002-y", "testing", gates=["ticket-approved"])
        p = self.dir / "status.md"
        p.write_text(p.read_text().replace("desc:", "merge-after: [0002]\ndesc:"))
        code, _, err = run(self.root, "merge", "b0001")
        self.assertEqual(code, 1)
        self.assertIn("0002-y (testing)", err)


class GeneralLaneTest(unittest.TestCase):
    def setUp(self):
        self.root = make_repo()
        self.origin = add_origin(self.root)

    def new_lane(self):
        code, out, err = run(self.root, "general", "new")
        self.assertEqual(code, 0, err)
        branch = next(w.strip("`,") for w in out.split() if w.startswith("`chore/general-"))
        wt = self.root / sh(self.root, "git", "worktree", "list").splitlines()[1].split()[0]
        return branch, wt

    def commit(self, wt, name="README.md", text="docs"):
        write(wt / name, text)
        sh(wt, "git", "add", ".")
        sh(wt, "git", "commit", "-qm", name)

    def test_lane_lands_through_regression_and_is_removed(self):
        cfg = self.root / ".mark/config.toml"
        cfg.write_text(cfg.read_text() + '\n[merge]\nregression = "test -f README.md"\n')
        sh(self.root, "git", "commit", "-qam", "regression")
        sh(self.root, "git", "push", "-q", "origin", "main")
        branch, wt = self.new_lane()
        self.assertTrue(wt.is_dir())
        self.commit(wt)
        code, out, err = run(self.root, "general", "merge", branch)
        self.assertEqual(code, 0, err + out)
        self.assertIn("Regression passed", out)
        self.assertEqual((self.root / "README.md").read_text(), "docs")
        self.assertEqual(sh(self.root, "git", "rev-parse", "main"), sh(self.root, "git", "rev-parse", "origin/main"))
        self.assertFalse(wt.exists())
        self.assertEqual(sh(self.root, "git", "branch", "--list", "chore/*"), "")

    def test_lane_carrying_workflow_state_is_refused(self):
        add_ticket(self.root, "feature", "0001-a", "review-design", gates=["ticket-approved"])
        sh(self.root, "git", "push", "-q", "origin", "main")
        branch, wt = self.new_lane()
        self.commit(wt, ".mark/gates/0001-a.design-approved", "forged")  # e.g. via `python -c`
        before = sh(self.root, "git", "rev-parse", "main")
        code, _, err = run(self.root, "general", "merge", branch)
        self.assertEqual(code, 1)
        self.assertIn(".mark/gates/0001-a.design-approved", err)
        self.assertEqual(sh(self.root, "git", "rev-parse", "main"), before)
        self.assertFalse((self.root / ".mark/gates/0001-a.design-approved").exists())

    def test_lane_may_carry_template_copies(self):
        branch, wt = self.new_lane()
        self.commit(wt, ".mark/.base/CLAUDE.md.base", "base")
        self.assertEqual(run(self.root, "general", "merge", branch)[0], 0)

    def test_red_regression_keeps_lane_and_main(self):
        cfg = self.root / ".mark/config.toml"
        cfg.write_text(cfg.read_text() + '\n[merge]\nregression = "exit 4"\n')
        sh(self.root, "git", "commit", "-qam", "regression")
        branch, wt = self.new_lane()
        self.commit(wt)
        before = sh(self.root, "git", "rev-parse", "main")
        code, _, err = run(self.root, "general", "merge", branch)
        self.assertEqual(code, 1)
        self.assertIn("exit 4", err)
        self.assertEqual(sh(self.root, "git", "rev-parse", "main"), before)
        self.assertTrue(wt.is_dir())

    def test_provisioned_lane_still_merges_and_is_removed(self):
        (self.root / ".mark/config.toml").write_text(
            FULL_CONFIG + '\n[worktree]\nsetup = \'echo k > .env && ln -s "$MARK_MAIN_CHECKOUT/.mark" node_modules\'\n')
        write(self.root / ".gitignore", ".claude/\n.mark/locks/\n.env\nnode_modules\n")
        sh(self.root, "git", "add", "-A")
        sh(self.root, "git", "commit", "-qm", "setup")
        sh(self.root, "git", "push", "-q", "origin", "main")
        branch, wt = self.new_lane()
        self.assertTrue((wt / "node_modules").is_symlink())
        self.commit(wt)
        code, out, err = run(self.root, "general", "merge", branch)
        self.assertEqual(code, 0, err + out)
        self.assertFalse(wt.exists())
        self.assertTrue((self.root / ".mark/config.toml").is_file())  # link target untouched

    def test_failed_setup_leaves_no_lane(self):
        (self.root / ".mark/config.toml").write_text(FULL_CONFIG + '\n[worktree]\nsetup = "exit 1"\n')
        sh(self.root, "git", "commit", "-qam", "setup")
        sh(self.root, "git", "push", "-q", "origin", "main")
        code, out, err = run(self.root, "general", "new")
        self.assertEqual(code, 1)
        self.assertIn("failed (exit 1)", err)
        self.assertEqual(len(sh(self.root, "git", "worktree", "list").splitlines()), 1)
        self.assertEqual(sh(self.root, "git", "branch", "--list", "chore/*"), "")

    def test_refusals(self):
        branch, wt = self.new_lane()
        code, _, err = run(self.root, "general", "merge", branch)
        self.assertEqual(code, 1)
        self.assertIn("no commits beyond main", err)
        write(wt / "notes.md", "x")
        code, _, err = run(self.root, "general", "merge", branch)
        self.assertIn("uncommitted", err)
        code, _, err = run(self.root, "general", "merge", "feature/0001-a")
        self.assertIn("not a general lane", err)
        code, _, err = run(self.root, "general", "merge", "chore/general-19990101-000000")
        self.assertIn("no worktree", err)
        self.assertEqual(run(self.root, "general")[0], 2)

    def test_drop_removes_an_empty_lane(self):
        branch, wt = self.new_lane()
        sh(wt, "git", "push", "-q", "-u", "origin", branch)
        code, out, err = run(self.root, "general", "drop", branch)
        self.assertEqual(code, 0, err + out)
        self.assertIn("dropped", out)
        self.assertFalse(wt.exists())
        self.assertEqual(sh(self.root, "git", "branch", "--list", "chore/*"), "")
        self.assertEqual(sh(self.root, "git", "ls-remote", "--heads", "origin", branch), "")

    def test_drop_refuses_to_lose_work_without_force(self):
        branch, wt = self.new_lane()
        write(wt / "notes.md", "x")
        code, _, err = run(self.root, "general", "drop", branch)
        self.assertEqual(code, 1)
        self.assertIn("1 uncommitted", err)
        self.commit(wt, "notes.md", "x")
        code, _, err = run(self.root, "general", "drop", branch)
        self.assertIn("1 commit(s)", err)
        self.assertTrue(wt.is_dir())
        before = sh(self.root, "git", "rev-parse", "main")
        write(wt / "more.md", "y")
        code, out, err = run(self.root, "general", "drop", branch, "--force")
        self.assertEqual(code, 0, err + out)
        self.assertFalse(wt.exists())
        self.assertEqual(sh(self.root, "git", "branch", "--list", "chore/*"), "")
        self.assertEqual(sh(self.root, "git", "rev-parse", "main"), before)

    def test_drop_refusals(self):
        code, _, err = run(self.root, "general", "drop", "feature/0001-a")
        self.assertIn("not a general lane", err)
        code, _, err = run(self.root, "general", "drop", "chore/general-19990101-000000")
        self.assertIn("no branch", err)
        self.assertEqual(run(self.root, "general", "drop", "chore/general-x", "--now")[0], 2)


class MergeOrderTest(unittest.TestCase):
    def setUp(self):
        self.root = make_repo()

    def ticket(self, ticket_id, status, after=None):
        kind = "bug" if ticket_id.startswith("b") else "feature"
        d = add_ticket(self.root, kind, ticket_id, status, gates=["ticket-approved"], commit=False)
        extra = {"merge-after": after} if after else {}
        if status in ("pending-merge", "passed"):
            extra["leftover"] = "0"
        (d / "status.md").write_text(status_text(status, **extra))
        return d

    def blockers(self, ref):
        ctx = ctx_of(self.root, ref)
        return flow.merge_blockers(ctx.cfg, ctx.ticket)

    def test_passed_and_superseded_satisfy(self):
        self.ticket("0001-a", "passed")
        self.ticket("0002-b", "superseded")
        self.ticket("0003-c", "pending-merge", "[0001, 0002]")
        self.assertIsNone(self.blockers("0003"))

    def test_unmet_unknown_and_ambiguous_block(self):
        self.ticket("0001-a", "testing")
        self.ticket("0004-x", "passed")
        self.ticket("b0004-y", "passed")
        self.ticket("0003-c", "pending-merge", "[0001, 0009, 0004]")
        err = self.blockers("0003")
        self.assertEqual(err.key, "merge.waiting")
        deps = err.params["deps"]
        self.assertIn("0001-a (testing)", deps)
        self.assertIn("0009 (No ticket", deps)
        self.assertNotIn("0004 (", deps)   # `0004` is an exact prefix of one feature only
        a = flow.next_action(ctx_of(self.root, "0003"))
        self.assertEqual((a.kind, a.message), ("stop", "merge.waiting"))

    def test_cycle_is_named(self):
        self.ticket("0001-a", "pending-merge", "[0002]")
        self.ticket("0002-b", "testing", "[0003]")
        self.ticket("0003-c", "developing", "[0001]")
        err = self.blockers("0001")
        self.assertEqual(err.key, "merge.cycle")
        self.assertEqual(err.params["cycle"], "0001-a -> 0002-b -> 0003-c -> 0001-a")
        self.ticket("0003-c", "superseded", "[0001]")   # a finished link breaks the cycle
        self.assertEqual(self.blockers("0001").key, "merge.waiting")

    def test_set_adds_merge_after_and_refuses_passed(self):
        self.ticket("0001-a", "testing")
        d = self.ticket("0002-b", "planning", "[0001]")
        sh(self.root, "git", "add", ".")
        sh(self.root, "git", "commit", "-qm", "t")
        self.assertIn("Not a ticket reference: x1", run(self.root, "set", "0002", "review-plan", "--merge-after", "x1")[2])
        code, _, err = run(self.root, "set", "0002", "review-plan", "--merge-after", "0001, b0003", "--no-commit")
        self.assertEqual(code, 0, err)
        self.assertIn("merge-after: [0001, b0003]", (d / "status.md").read_text())
        self.ticket("0003-c", "pending-merge", "[0001]")
        self.assertIn("0001-a (testing)", run(self.root, "set", "0003", "passed", "--no-commit")[2])

    def test_waiting_is_not_recorded_as_a_failed_merge(self):
        self.ticket("0001-a", "testing")
        self.ticket("0002-b", "pending-merge", "[0001]")
        sh(self.root, "git", "add", ".")
        sh(self.root, "git", "commit", "-qm", "t")
        code, _, err = run(self.root, "merge", "0002")
        self.assertEqual(code, 1)
        self.assertIn("0001-a (testing)", err)
        self.assertFalse((self.root / ".mark/locks/0002-b.merge.result.json").exists())
        self.ticket("0001-a", "passed")
        self.assertEqual(ctx_next(self.root, "0002").kind, "merge")


class HumanDecisionTest(unittest.TestCase):
    def setUp(self):
        self.root = make_repo()

    def test_approve_requires_a_human(self):
        add_ticket(self.root, "feature", "0001-a", "review-design", gates=["ticket-approved"])
        code, _, err = run(self.root, "approve", "0001")
        self.assertEqual(code, 1)
        self.assertIn("/mark:approve 0001-a", err)
        self.assertFalse((self.root / ".mark/gates/0001-a.design-approved").exists())

    def test_approve_design_settles_rounds_and_writes_gate(self):
        d = add_ticket(self.root, "feature", "0001-a", "review-design", gates=["ticket-approved"])
        reviews.append_round(d / "review-design.md", "en", "0001-a", "design", ["x"])
        human_typed(self.root, "/mark:approve 0001")
        code, out, err = run(self.root, "approve", "0001")
        self.assertEqual(code, 0, err)
        self.assertIn("`review-design` -> `planning`", out)
        self.assertIn("approved_by: human", (self.root / ".mark/gates/0001-a.design-approved").read_text())
        self.assertEqual(reviews.pending(d / "review-design.md"), [])
        self.assertIn("status: planning\nowner: coder-plan", (d / "status.md").read_text())
        self.assertEqual(sh(self.root, "git", "status", "--porcelain"), "")

    def test_approve_opening_first(self):
        d = add_ticket(self.root, "feature", "0001-a", "review-design")
        human_typed(self.root, "/mark:approve 0001-a")
        code, out, _ = run(self.root, "approve", "0001")
        self.assertIn("Opening 0001-a approved", out)
        self.assertTrue((self.root / ".mark/gates/0001-a.ticket-approved").exists())
        self.assertIn("status: review-design", (d / "status.md").read_text())

    def test_blocked_spec_goes_back_to_design_without_gate(self):
        add_ticket(self.root, "feature", "0001-a", "blocked-spec", gates=ALL_GATES)
        human_typed(self.root, "/mark:approve 0001")
        self.assertIn("`blocked-spec` -> `designing`", run(self.root, "approve", "0001")[1])

    def test_human_picks_where_a_blocked_ticket_goes(self):
        add_ticket(self.root, "feature", "0001-a", "blocked-spec", gates=ALL_GATES)
        human_typed(self.root, "/mark:approve 0001")
        code, _, err = run(self.root, "approve", "0001", "--to", "developing")
        self.assertEqual(code, 1)  # the human did not choose developing
        self.assertIn("/mark:approve 0001-a developing", err)
        human_typed(self.root, "/mark:approve 0001 developing")
        self.assertIn("`blocked-spec` -> `developing`", run(self.root, "approve", "0001", "--to", "developing")[1])

    def test_blocked_unclear_needs_a_target(self):
        add_ticket(self.root, "feature", "0001-a", "blocked-unclear", gates=ALL_GATES)
        human_typed(self.root, "/mark:approve 0001")
        code, _, err = run(self.root, "approve", "0001")
        self.assertEqual(code, 1)
        self.assertIn("designing, developing, planning", err)
        human_typed(self.root, "/mark:approve 0001 testing")
        self.assertIn("not possible", run(self.root, "approve", "0001", "--to", "testing")[2])
        human_typed(self.root, "/mark:approve 0001 planning")
        self.assertIn("`blocked-unclear` -> `planning`", run(self.root, "approve", "0001", "--to", "planning")[1])

    def test_review_gates_take_no_target(self):
        add_ticket(self.root, "feature", "0001-a", "review-plan", gates=["ticket-approved", "design-approved"])
        human_typed(self.root, "/mark:approve 0001 developing")
        self.assertIn("not possible", run(self.root, "approve", "0001", "--to", "developing")[2])

    def test_nothing_to_approve(self):
        add_ticket(self.root, "feature", "0001-a", "developing", gates=ALL_GATES)
        human_typed(self.root, "/mark:approve 0001")
        self.assertIn("nothing to approve", run(self.root, "approve", "0001")[2])

    def test_reject_appends_round_and_routes(self):
        d = add_ticket(self.root, "feature", "0001-a", "review-plan", gates=["ticket-approved", "design-approved"])
        human_typed(self.root, "/mark:reject 0001 split T-2; add rollback")
        code, out, err = run(self.root, "reject", "0001", "--item", "split T-2", "--item", "add rollback")
        self.assertEqual(code, 0, err)
        self.assertIn("round 1 (R-1, R-2)", out)
        self.assertIn("`review-plan` -> `planning`", out)
        self.assertEqual([r.refs for r in reviews.pending(d / "review-plan.md")], [["R-1", "R-2"]])
        a = flow.next_action(ctx_of(self.root, "0001"))
        self.assertEqual((a.scenario, a.pending_refs), ("coder-plan-rework", ["R-1", "R-2"]))

    def test_reject_rules(self):
        add_ticket(self.root, "feature", "0001-a", "testing", gates=ALL_GATES)
        human_typed(self.root, "/mark:reject 0001 x")
        self.assertIn("not at a human gate", run(self.root, "reject", "0001", "--item", "x")[2])
        add_ticket(self.root, "feature", "0002-b", "review-design", gates=["ticket-approved"])
        human_typed(self.root, "/mark:reject 0002 x")
        self.assertIn("--to planning", run(self.root, "reject", "0002", "--item", "x", "--to", "planning")[2])
        self.assertIn("--item", run(self.root, "reject", "0002")[2])

    def test_reject_merge_back_to_planning(self):
        d = add_ticket(self.root, "bug", "b0001-x", "pending-merge", gates=["ticket-approved"])
        p = d / "status.md"
        p.write_text(p.read_text().replace("desc:", "leftover: 0\ndesc:"))
        human_typed(self.root, "/mark:reject b0001 wrong approach")
        code, out, _ = run(self.root, "reject", "b0001", "--item", "wrong approach", "--to", "planning")
        self.assertEqual(code, 0)
        self.assertEqual(flow.next_action(ctx_of(self.root, "b0001")).scenario, "fix-plan-rework")

    def test_claim_approval_follows_human_command(self):
        code, out, err = run(self.root, "claim", "bug", "crash on save")
        self.assertIn("not approved", err)
        self.assertFalse((self.root / ".mark/gates/b0001-crash-on-save.ticket-approved").exists())
        human_typed(self.root, "/mark:fix crash on load")
        code, out, err = run(self.root, "claim", "bug", "crash on load")
        self.assertEqual(out, "TICKET-ID: b0002-crash-on-load\n")
        self.assertIn("approved", err)
        self.assertTrue((self.root / ".mark/gates/b0002-crash-on-load.ticket-approved").exists())


class DispatchTest(unittest.TestCase):
    def setUp(self):
        self.root = make_repo()
        self.origin = add_origin(self.root)
        add_templates(self.root)
        self.dir = add_ticket(self.root, "feature", "0001-a", "planning", gates=["ticket-approved", "design-approved"])
        sh(self.root, "git", "push", "-q", "origin", "main")

    def test_dispatch_sets_up_isolation_and_passes_guards(self):
        code, out, err = run(self.root, "dispatch", "0001", "--prev", "design approved")
        self.assertEqual(code, 0, err)
        self.assertIn("Created branch feature/0001-a from origin/main", err)
        head, prompt = out.split("--- prompt ---\n")
        self.assertIn("subagent_type: mark:coder-plan", head)  # the plugin's agent
        self.assertTrue(prompt.startswith("<!-- mark:ticket features/0001-a -->"))
        wt = self.root / ".claude/worktrees/feature-0001-a"
        self.assertIn(f"Work on 0001-a in {wt}/.mark/features/0001-a.", prompt)
        self.assertIn("Previous step reported: design approved", prompt)
        self.assertIn("tech-plan.md", prompt)
        self.assertTrue(wt.is_dir())
        self.assertIn("feature/0001-a", sh(self.root, "git", "ls-remote", "--heads", "origin"))
        # The prompt as printed passes every pre-dispatch guard.
        code, err = hook("pre-dispatch", {"hook_event_name": "PreToolUse", "tool_name": "Agent",
                                          "cwd": str(self.root),
                                          "tool_input": {"subagent_type": "coder-plan", "prompt": prompt}})
        self.assertEqual(code, 0, err)
        # Idempotent: a second dispatch reuses everything (the lock now says wait).
        self.assertIn("still working", run(self.root, "dispatch", "0001")[2])

    def test_uncommitted_worktree_blocks_next_dispatch(self):
        self.assertEqual(run(self.root, "dispatch", "0001")[0], 0)
        for lock in (self.root / ".mark/locks").glob("*.lock"):
            lock.unlink()
        wt = self.root / ".claude/worktrees/feature-0001-a"
        write(wt / ".mark/features/0001-a/tech-plan.md", "plan")
        code, _, err = run(self.root, "dispatch", "0001")
        self.assertEqual(code, 1)
        self.assertIn("uncommitted changes", err)
        self.assertIn(".mark/features/0001-a/tech-plan.md", err)
        sh(wt, "git", "add", "-A")
        sh(wt, "git", "commit", "-qm", "plan")
        self.assertEqual(run(self.root, "dispatch", "0001")[0], 0)
        self.assertEqual(sh(wt, "git", "rev-parse", "HEAD"),
                         sh(self.root, "git", "rev-parse", "origin/feature/0001-a"))

    def set_setup(self, cmd, extra=""):
        (self.root / ".mark/config.toml").write_text(FULL_CONFIG + f"\n[worktree]\nsetup = '{cmd}'\n{extra}")
        write(self.root / ".gitignore", ".claude/\n.mark/locks/\n.env\nnode_modules\n")
        sh(self.root, "git", "add", "-A")
        sh(self.root, "git", "commit", "-qm", "setup")
        sh(self.root, "git", "push", "-q", "origin", "main")

    def test_setup_provisions_only_new_worktrees(self):
        write(self.root / "deps/lib.txt", "x")
        self.set_setup('cp "$MARK_MAIN_CHECKOUT/.gitignore" .env && ln -s "$MARK_MAIN_CHECKOUT/deps" node_modules'
                       ' && echo "$MARK_BRANCH" >> "$MARK_MAIN_CHECKOUT/runs"')
        code, out, err = run(self.root, "dispatch", "0001")
        self.assertEqual(code, 0, err)
        self.assertIn("Provisioned the new worktree", err)
        wt = self.root / ".claude/worktrees/feature-0001-a"
        self.assertTrue((wt / ".env").is_file())
        self.assertEqual((wt / "node_modules/lib.txt").read_text(), "x")
        for lock in (self.root / ".mark/locks").glob("*.lock"):
            lock.unlink()
        self.assertEqual(run(self.root, "dispatch", "0001")[0], 0)  # reused: no second setup
        self.assertEqual((self.root / "runs").read_text(), "feature/0001-a\n")

    def test_failed_setup_removes_the_new_worktree(self):
        self.set_setup("echo boom; exit 3")
        code, out, err = run(self.root, "dispatch", "0001")
        self.assertEqual(code, 1)
        self.assertIn("failed (exit 3)", err)
        self.assertIn("boom", err)
        self.assertIn(".mark/locks/0001-a.setup.log", err)
        self.assertEqual(out, "")
        self.assertFalse((self.root / ".claude/worktrees/feature-0001-a").exists())
        self.assertEqual(len(sh(self.root, "git", "worktree", "list").splitlines()), 1)

    def test_setup_that_leaves_tracked_noise_or_hangs_fails(self):
        self.set_setup("touch junk.txt")
        code, _, err = run(self.root, "dispatch", "0001")
        self.assertEqual(code, 1)
        self.assertIn("junk.txt", err)
        self.assertIn("Gitignore them", err)
        self.assertFalse((self.root / ".claude/worktrees/feature-0001-a").exists())
        self.set_setup("sleep 5", "setup_timeout = 1\n")
        code, _, err = run(self.root, "dispatch", "0001")
        self.assertIn("timeout 1s", err)
        # Once setup is fixed, the next dispatch starts over and succeeds.
        self.set_setup("true")
        self.assertEqual(run(self.root, "dispatch", "0001")[0], 0)

    def listen(self, port):
        srv = socket.socket()
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("127.0.0.1", port))
        srv.listen()
        self.addCleanup(srv.close)

    def test_new_worktrees_get_their_own_free_ports(self):
        self.set_setup('cp "$MARK_MAIN_CHECKOUT/.env" .', "ports = { A_PORT = 41000, B_PORT = 42000 }\nport_slots = 5\n")
        write(self.root / ".env", "A_PORT=5173\nOTHER=x\nA_PORT=9\n")
        start = zlib.crc32(b"feature-0001-a") % 5
        self.listen(42000 + start)  # something outside this repo holds the first slot's B port
        code, out, err = run(self.root, "dispatch", "0001")
        self.assertEqual(code, 0, err)
        env = (self.root / ".claude/worktrees/feature-0001-a/.env").read_text()
        slot = (start + 1) % 5
        self.assertEqual(env, f"A_PORT={41000 + slot}\nOTHER=x\nB_PORT={42000 + slot}\n")
        self.assertIn(f"own ports in its .env: A_PORT={41000 + slot}, B_PORT={42000 + slot}", err)
        self.assertIn(f"Ports of this worktree (from its `.env`): A_PORT={41000 + slot}, B_PORT=", out)
        # A second ticket never gets a slot another worktree holds.
        add_ticket(self.root, "feature", "0002-b", "planning", gates=["ticket-approved", "design-approved"])
        sh(self.root, "git", "push", "-q", "origin", "main")
        self.assertEqual(run(self.root, "dispatch", "0002")[0], 0)
        env2 = (self.root / ".claude/worktrees/feature-0002-b/.env").read_text()
        self.assertNotIn(f"A_PORT={41000 + slot}\n", env2)
        self.assertNotIn(f"A_PORT={41000 + start}\n", env2)

    def test_no_free_port_slot_removes_the_new_worktree(self):
        self.set_setup("true", "ports = { A_PORT = 41100 }\nport_slots = 1\n")
        self.listen(41100)
        code, _, err = run(self.root, "dispatch", "0001")
        self.assertEqual(code, 1)
        self.assertIn("No free port slot among the 1", err)
        self.assertFalse((self.root / ".claude/worktrees/feature-0001-a").exists())

    def test_project_agent_overrides_the_builtin(self):
        write(self.root / ".claude/agents/coder-plan.md", "---\nname: coder-plan\n---\nours\n")
        sh(self.root, "git", "add", "-A")
        sh(self.root, "git", "commit", "-q", "-m", "own coder-plan")
        sh(self.root, "git", "push", "-q", "origin", "main")
        code, out, err = run(self.root, "dispatch", "0001")
        self.assertEqual(code, 0, err)
        self.assertIn("subagent_type: coder-plan\n", out)

    def test_builtin_prompt_when_the_project_has_none(self):
        for p in (self.root / ".mark/prompts").iterdir():
            p.unlink()
        code, out, err = run(self.root, "dispatch", "0001")
        self.assertEqual(code, 0, err)
        self.assertIn("mark format tech-plan.md", out)

    def test_outputs_override_and_template_errors(self):
        (self.root / ".mark/prompts/coder-plan.md").write_text("---\nrole: designer\n---\nx\n")
        self.assertIn("declares role `designer`", run(self.root, "dispatch", "0001")[2])
        (self.root / ".mark/prompts/coder-plan.md").write_text("---\nrole: coder-plan\n---\n{{nope}}\n")
        self.assertIn("unknown placeholder(s): nope", run(self.root, "dispatch", "0001")[2])
        self.assertFalse((self.root / ".claude/worktrees/feature-0001-a").exists())

    def test_scenario_outputs_anchor(self):
        add_ticket(self.root, "feature", "0002-b", "design-qa", gates=ALL_GATES)
        sh(self.root, "git", "push", "-q", "origin", "main")
        code, out, err = run(self.root, "dispatch", "0002")
        self.assertEqual(code, 0, err)
        self.assertIn("<!-- mark:outputs design-qa.md -->", out)


class GuardTest(unittest.TestCase):
    def setUp(self):
        self.root = make_repo()

    def bash(self, command, agent_type=None):
        payload = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "cwd": str(self.root),
                   "tool_input": {"command": command}}
        if agent_type:
            payload["agent_type"] = agent_type
        return hook("pre-bash", payload)

    def test_subagents_cannot_change_state_through_cli(self):
        code, err = self.bash("cd /tmp && mark set 0001 testing", "coder-impl")
        self.assertEqual(code, 2)
        self.assertIn("mark set", err)
        self.assertEqual(self.bash("mark merge 0001", "tester")[0], 2)
        self.assertEqual(self.bash("mark next 0001", "coder-impl")[0], 0)
        self.assertEqual(self.bash("mark set 0001 testing")[0], 0)

    def test_nobody_touches_human_tokens(self):
        self.assertEqual(self.bash("touch .mark/locks/human/approve-1.json")[0], 2)
        code, _ = hook("pre-write", {"hook_event_name": "PreToolUse", "tool_name": "Write",
                                     "cwd": str(self.root),
                                     "tool_input": {"file_path": str(self.root / ".mark/locks/human/x.json"),
                                                    "content": "{}"}})
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
