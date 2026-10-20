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
                         {"0001-add-login": "designing", "b0001-crash": "planning"})

        self.assertEqual(run(self.root, "status", "--check")[0], 0)

    def test_active_hides_done(self):
        run(self.root, "claim", "feature", "done thing")
        p = self.root / ".mark" / "features" / "0001-done-thing" / "status.md"
        p.write_text(p.read_text().replace("designing", "passed").replace("desc:", "leftover: 0\ndesc:"))
        self.assertIn("## 已结案 (1)", run(self.root, "status")[1])
        self.assertNotIn("## 已结案", run(self.root, "status", "--active")[1])

    def test_check_reports_problems(self):
        (self.root / ".mark" / "bugs" / "b0001-x").mkdir(parents=True)
        code, out, _ = run(self.root, "status", "--check")
        self.assertEqual(code, 1)
        self.assertIn(".mark/bugs/b0001-x/status.md", out)

    def test_bad_usage(self):
        self.assertEqual(run(self.root, "claim", "epic", "x")[0], 2)
        self.assertEqual(run(self.root, "claim", "feature")[0], 2)
        self.assertEqual(run(self.root, "nope")[0], 2)

    def test_claim_too_long_fails_cleanly(self):
        code, _, err = run(self.root, "claim", "feature", "x" * 300)
        self.assertEqual(code, 1)
        self.assertIn("立单失败", err)

    def test_pipe_in_note_does_not_break_table(self):
        run(self.root, "claim", "feature", "a | b")
        self.assertIn("a \\| b", run(self.root, "status")[1])


if __name__ == "__main__":
    unittest.main()
