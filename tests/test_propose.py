"""`mark propose`: suggested choices for a gate. A suggestion never fails: bad input saves nothing, exit 0."""
from __future__ import annotations

import io
import json
import unittest

from tests._support import add_ticket, hook, make_repo

from mark import board, cli, flow, propose
from mark.config import load_config


class Tty(io.StringIO):
    def isatty(self):
        return True


class ProposeTest(unittest.TestCase):
    def setUp(self):
        self.root = make_repo()
        add_ticket(self.root, "feature", "0001-a", "review-plan", gates=("ticket-approved",))
        add_ticket(self.root, "feature", "0002-b", "blocked-unclear", gates=("ticket-approved",))
        add_ticket(self.root, "feature", "0003-c", "developing", gates=("ticket-approved",))
        self.cfg = load_config(self.root)

    def run_cli(self, *argv, stdin=""):
        out = io.StringIO()
        inp = stdin if isinstance(stdin, io.StringIO) else io.StringIO(stdin)
        code = cli.main(list(argv), cwd=self.root, out=out, err=out, inp=inp)
        return code, out.getvalue()

    def saved(self, tid):
        status = flow.load(self.cfg, tid).ticket.status
        return propose.load(self.cfg, tid, status)

    def test_anything_wrong_saves_nothing_and_exits_0(self):
        cases = [
            ("0002-b", "not json {"),                              # bad JSON
            ("0002-b", "[1, 2]"),                                  # wrong shape
            ("0002-b", '{"options": [{"label": "x", "to": "passed"}]}'),  # no legal option
            ("0002-b", Tty('{"options": []}')),                    # nothing piped in
            ("0003-c", '{"options": [{"label": "x"}]}'),           # does not wait on the human
        ]
        for tid, stdin in cases:
            code, out = self.run_cli("propose", tid, stdin=stdin)
            self.assertEqual(code, 0, out)
            self.assertIn("Do not retry", out)
            self.assertIsNone(self.saved(tid))

    def test_blocked_keeps_legal_targets_and_one_recommendation(self):
        targets = flow.approve_targets(flow.load(self.cfg, "0002-b"))
        data = {"question": "Which key?", "options": [
            {"label": "Email", "to": targets[0], "answer": "use the email", "recommended": True},
            {"label": "Nowhere", "to": "passed"},                  # not a legal move: dropped
            {"label": "Reject", "verb": "reject", "items": ["x"]},  # no rejecting a blocked ticket
            {"label": "Also", "to": targets[-1], "recommended": True},
        ]}
        code, out = self.run_cli("propose", "0002-b", stdin=json.dumps(data))
        self.assertEqual(code, 0, out)
        self.assertIn("Nowhere, Reject", out)
        p = self.saved("0002-b")
        self.assertEqual(p["question"], "Which key?")
        self.assertEqual([o["label"] for o in p["options"]], ["Email", "Also"])
        self.assertEqual([o["recommended"] for o in p["options"]], [True, False])
        self.assertEqual(p["options"][0]["answer"], "use the email")

    def test_review_takes_approve_and_reject_with_comments(self):
        data = {"options": [{"label": "Ship it"}, {"label": "Fix AC-3", "verb": "reject", "items": ["AC-3 has no test"]},
                            {"label": "Empty reject", "verb": "reject"}, {"label": "Jump", "to": "developing"}]}
        self.run_cli("propose", "0001-a", stdin=json.dumps(data))
        opts = self.saved("0001-a")["options"]
        self.assertEqual([(o["label"], o["verb"]) for o in opts], [("Ship it", "approve"), ("Fix AC-3", "reject")])
        self.assertEqual(opts[1]["items"], ["AC-3 has no test"])

    def test_any_status_write_retires_the_proposal(self):
        self.run_cli("propose", "0001-a", stdin='{"options": [{"label": "Ship it"}]}')
        self.assertTrue(propose.path(self.cfg, "0001-a").is_file())
        ctx = flow.load(self.cfg, "0001-a")
        flow.set_status(ctx, "superseded")  # any status write; a gate allows only this one by hand
        self.assertFalse(propose.path(self.cfg, "0001-a").exists())

    def test_a_proposal_for_another_status_is_not_shown(self):
        self.run_cli("propose", "0001-a", stdin='{"options": [{"label": "Ship it"}]}')
        self.assertIsNone(propose.load(self.cfg, "0001-a", "review-design"))

    def test_next_tells_how_to_propose_at_a_stop_only(self):
        _, out = self.run_cli("next", "0002-b")
        self.assertIn("mark propose 0002-b <<'EOF'", out)
        self.assertIn('"to": "<status>"', out)
        _, out = self.run_cli("next", "0001-a")
        self.assertIn('"verb": "reject"', out)
        _, out = self.run_cli("next", "0003-c")
        self.assertNotIn("mark propose", out)

    def test_board_shows_the_proposal_with_the_wait(self):
        self.run_cli("propose", "0001-a", stdin='{"question": "Ship?", "options": [{"label": "Ship it"}]}')
        waits = {t["id"]: t["wait"] for t in board.snapshot(self.cfg, board.History(self.cfg))["tickets"]}
        self.assertEqual(waits["0001-a"]["proposal"]["question"], "Ship?")
        self.assertNotIn("proposal", waits["0002-b"])

    def test_only_the_orchestrator_proposes(self):
        cmd = "mark propose 0002-b <<'EOF'\n{\"options\": []}\nEOF"
        payload = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "cwd": str(self.root),
                   "tool_input": {"command": cmd}}
        self.assertEqual(hook("pre-bash", payload)[0], 0)
        self.assertEqual(hook("pre-bash", {**payload, "agent_type": "mark:coder-impl"})[0], 2)


if __name__ == "__main__":
    unittest.main()
