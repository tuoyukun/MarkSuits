import io
import json
import unittest

from tests._support import make_project

from mark import cli


def run(root, *argv):
    out, err = io.StringIO(), io.StringIO()
    code = cli.main(list(argv), cwd=root, out=out, err=err)
    return code, out.getvalue(), err.getvalue()


class CliTest(unittest.TestCase):
    def setUp(self):
        self.root = make_project()  # locale zh-CN

    def test_outside_mark_project_exits_2(self):
        code, _, err = run(make_project(None), "status")
        self.assertEqual(code, 2)
        self.assertIn("Not a Mark project", err)

    def test_empty_status(self):
        code, out, _ = run(self.root, "status")
        self.assertEqual(code, 0)
        self.assertIn("还没有工单", out)

    def test_claim_then_status_views(self):
        self.assertEqual(run(self.root, "claim", "feature", "Add login")[1], "TICKET-ID: 0001-add-login\n")
        self.assertEqual(run(self.root, "claim", "bug", "崩溃", "--slug", "crash")[1], "TICKET-ID: b0001-crash\n")

        code, out, _ = run(self.root, "status")
        self.assertEqual(code, 0)
        self.assertIn("## 在飞 (2)", out)
        self.assertIn("[0001-add-login](features/0001-add-login/)", out)

        data = json.loads(run(self.root, "status", "--json")[1])
        self.assertEqual({d["id"]: d["status"] for d in data},
                         {"0001-add-login": "drafting", "b0001-crash": "planning"})

        self.assertEqual(run(self.root, "status", "--check")[0], 0)

    def test_a_missing_gate_shows_under_waiting_on_you(self):
        from tests._support import add_ticket
        add_ticket(self.root, "feature", "0001-a", "planning", gates=["ticket-approved"], commit=False)
        out = run(self.root, "status")[1]
        self.assertIn("## 待你介入 (1)", out)
        self.assertIn("0001-a", out)

    def test_active_hides_done(self):
        run(self.root, "claim", "feature", "done thing")
        p = self.root / ".mark" / "features" / "0001-done-thing" / "status.md"
        p.write_text(p.read_text().replace("drafting", "passed").replace("desc:", "leftover: 0\ndesc:"))
        self.assertIn("## 已结案 (1)", run(self.root, "status")[1])
        self.assertNotIn("## 已结案", run(self.root, "status", "--active")[1])

    def test_check_reports_problems(self):
        (self.root / ".mark" / "bugs" / "b0001-x").mkdir(parents=True)
        code, out, _ = run(self.root, "status", "--check")
        self.assertEqual(code, 1)
        self.assertIn(".mark/bugs/b0001-x/status.md", out)

    def test_format_prints_the_override_else_the_builtin(self):
        code, out, _ = run(self.root, "format", "design")
        self.assertEqual(code, 0)
        self.assertIn("<!-- mark:states -->", out)
        self.assertIn("设计", out)  # locale zh-CN
        (self.root / ".mark" / "formats").mkdir()
        (self.root / ".mark" / "formats" / "design.md").write_text("ours\n")
        self.assertEqual(run(self.root, "format", "design.md")[1], "ours\n")
        self.assertEqual(run(self.root, "format", "nope")[0], 1)
        self.assertEqual(run(self.root, "format", "../config.toml")[0], 2)

    def test_orchestrator_rules_name_the_language(self):
        self.assertIn("都用简体中文和 Human 说话", run(self.root, "rules")[1])

    def test_rules_collaboration_follows_the_project_locale(self):
        self.assertIn("协作", run(self.root, "rules", "collaboration")[1])
        self.assertIn("How a Mark project is built", run(make_project(None), "rules", "collaboration")[1])

    def test_unlock_takes_a_short_id(self):
        run(self.root, "claim", "feature", "Add login")
        lock = self.root / ".mark" / "locks" / "0001-add-login.designer.lock"
        lock.parent.mkdir(parents=True, exist_ok=True)
        lock.write_text("{}")
        self.assertEqual(run(self.root, "unlock", "0001", "designer")[0], 0)
        self.assertFalse(lock.exists())

    def test_bad_usage(self):
        self.assertEqual(run(self.root, "claim", "epic", "x")[0], 2)
        self.assertEqual(run(self.root, "claim", "feature")[0], 2)
        self.assertEqual(run(self.root, "nope")[0], 2)

    def test_claim_too_long_fails_cleanly(self):
        code, _, err = run(self.root, "claim", "feature", "x" * 300)
        self.assertEqual(code, 1)
        self.assertIn("立单失败", err)

    def test_claim_no_design_is_a_feature_only_flag(self):
        self.assertEqual(run(self.root, "claim", "feature", "Data pipeline", "--no-design")[0], 0)
        data = json.loads(run(self.root, "status", "--json")[1])
        self.assertEqual(data[0]["design"], "none")
        code, _, err = run(self.root, "claim", "bug", "Crash", "--no-design")
        self.assertEqual(code, 1)
        self.assertIn("只有 feature", err)

    def test_set_marks_and_clears_no_design(self):
        run(self.root, "claim", "feature", "Data pipeline")
        d = self.root / ".mark" / "features" / "0001-data-pipeline"
        (d / "requirement.md").write_text(
            "## 验收标准\n<!-- mark:ac -->\n- AC-1：能跑\n\n"
            "## 待确认\n<!-- mark:open-questions -->\n- 无\n", encoding="utf-8")
        code, out, err = run(self.root, "set", "0001", "review-requirement", "--design", "none")
        self.assertEqual(code, 0, err)
        self.assertIn("design: none", (d / "status.md").read_text())
        self.assertIn("跳过 designer", out)
        code, out, err = run(self.root, "set", "0001", "review-requirement", "--design", "default")
        self.assertEqual(code, 0, err)
        self.assertNotIn("design:", (d / "status.md").read_text())
        self.assertIn("恢复常规", out)

    def test_set_refuses_an_unknown_design_value(self):
        run(self.root, "claim", "feature", "Data pipeline")
        code, _, err = run(self.root, "set", "0001", "drafting", "--design", "ui", "--no-commit")
        self.assertEqual(code, 1)
        self.assertIn("--design", err)

    def test_pipe_in_note_does_not_break_table(self):
        run(self.root, "claim", "feature", "a | b")
        self.assertIn("a \\| b", run(self.root, "status")[1])


if __name__ == "__main__":
    unittest.main()
