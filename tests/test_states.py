import unittest

import tests._support  # noqa: F401  (sys.path)

from mark import states


class StateMachineTest(unittest.TestCase):
    def test_feature_happy_path_is_legal(self):
        path = ["designing", "review-design", "planning", "review-plan", "developing",
                "design-qa", "testing", "pending-merge", "passed"]
        for old, new in zip(path, path[1:]):
            self.assertTrue(states.can_move("feature", old, new), f"{old} -> {new}")

    def test_bug_happy_path_is_legal(self):
        path = ["planning", "developing", "testing", "pending-merge", "passed"]
        for old, new in zip(path, path[1:]):
            self.assertTrue(states.can_move("bug", old, new), f"{old} -> {new}")

    def test_cannot_skip_review_gates(self):
        self.assertFalse(states.can_move("feature", "designing", "planning"))
        self.assertFalse(states.can_move("feature", "planning", "developing"))

    def test_bug_has_no_review_or_qa_states(self):
        for s in ("review-design", "review-plan", "design-qa"):
            self.assertFalse(states.is_valid("bug", s), s)

    def test_terminal_states_have_no_exit(self):
        for kind in states.KINDS:
            for s in states.TERMINAL:
                self.assertEqual(states.TRANSITIONS[kind][s], frozenset())

    def test_any_open_status_can_be_superseded(self):
        for kind in states.KINDS:
            for s in states.statuses(kind) - states.TERMINAL:
                self.assertTrue(states.can_move(kind, s, "superseded"), f"{kind}:{s}")

    def test_every_edge_targets_a_known_status(self):
        for kind, edges in states.TRANSITIONS.items():
            for s, targets in edges.items():
                self.assertLessEqual(targets, states.statuses(kind), f"{kind}:{s}")

    def test_every_status_has_a_side(self):
        for kind in states.KINDS:
            for s in states.statuses(kind):
                self.assertNotEqual(states.side(s), "unknown", s)

    def test_agent_statuses_map_to_a_role(self):
        for kind in states.KINDS:
            for s in states.statuses(kind) & states.AGENT:
                self.assertIn(s, states.ROLE_FOR_STATUS[kind], f"{kind}:{s}")

    def test_initial_roles(self):
        self.assertEqual(states.INITIAL["feature"], "drafting")
        self.assertEqual(states.owner("feature", "drafting"), "orchestrator")
        self.assertEqual(states.side("drafting"), "agent")
        self.assertEqual(states.side("review-requirement"), "human")
        self.assertEqual(states.ROLE_FOR_STATUS["bug"][states.INITIAL["bug"]], "fix-plan")


if __name__ == "__main__":
    unittest.main()
