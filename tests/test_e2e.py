"""Black-box rules for the tester's end-to-end tests (mark.e2e and the pre-write guard)."""
import unittest

from tests._support import FULL_CONFIG, add_origin, add_ticket, add_worktree, hook, make_repo, sh
from tests.test_flow import run, write

from mark import e2e

CONFIG = (FULL_CONFIG + '\n[paths]\ntests = "tests"\nfrontend = "frontend"\nbackend = "backend"\n'
          '\n[tests]\nprofile = "playwright"\n')


def plan(*rows):
    body = "\n".join(f"| {' | '.join(r)} |" for r in rows)
    return ("# plan\n\n## End-to-end coverage\n<!-- mark:e2e-plan -->\n"
            "| AC | action | test | steps / why not extend |\n|---|---|---|---|\n" + body + "\n\n## Risks\n")


def index(*titles):
    return ("# Journeys\n\n<!-- mark:journeys -->\n| test | file | path | covers |\n|---|---|---|---|\n"
            + "".join(f"| {t} | e2e/a.spec.ts | / → add → listed | 0001/AC-1 |\n" for t in titles))

GOOD = '''import { expect, test } from "@playwright/test";

test("add a todo", async ({ page }) => {
  // covers: 0001/AC-1
  await page.goto("/");
  await page.getByTestId("new").fill("milk");
  await page.getByTestId("new").press("Enter");
  await expect(page.getByTestId("title")).toHaveText(["milk"]);
});
'''


def keys(rel, old, new, profile="playwright"):
    return [p.key for p in e2e.problems(rel, old, new, "tests", ["frontend", "backend"], profile)]


def block(body, title="t", head='test("{title}", async ({{ page }}) => {{'):
    return head.format(title=title) + "\n" + body + "\n});\n"


class SpecRulesTest(unittest.TestCase):
    def test_a_user_journey_passes(self):
        self.assertEqual(keys("tests/e2e/a.spec.ts", None, GOOD), [])

    def test_navigation_and_assertions_alone_are_not_a_test(self):
        new = block('  await page.goto("/");\n  await expect(page.getByText("Hi")).toBeVisible();')
        self.assertEqual(keys("tests/e2e/a.spec.ts", None, new), ["e2e.no_action"])

    def test_assertions_only_before_the_action_do_not_count(self):
        new = block('  await expect(page.getByText("Hi")).toBeVisible();\n  await page.getByRole("button").click();')
        self.assertEqual(keys("tests/e2e/a.spec.ts", None, new), ["e2e.no_assert_after"])

    def test_calls_inside_comments_and_strings_do_not_count(self):
        new = block('  // await page.click("x"); expect(1)\n  await page.goto("/.click(");')
        self.assertEqual(keys("tests/e2e/a.spec.ts", None, new), ["e2e.no_action"])

    def test_skip_sleep_stub_and_poke(self):
        cases = {
            'test.skip("t", async ({ page }) => {\n  await page.click("a");\n  expect(1);\n});\n': "e2e.skipped",
            block('  test.skip(true, "later");\n  await page.click("a");\n  expect(1);'): "e2e.skipped",
            block('  await page.click("a");\n  await page.waitForTimeout(1000);\n  expect(1);'): "e2e.sleep",
            block('  await page.route("**/api", r => r.fulfill({}));\n  await page.click("a");\n  expect(1);'): "e2e.stub",
            block('  await page.evaluate(() => { window.__state = 1; });\n  await page.click("a");\n  expect(1);'):
                "e2e.poke",
        }
        for new, key in cases.items():
            with self.subTest(key=key):
                self.assertIn(key, keys("tests/e2e/a.spec.ts", None, new))
        short = block('  await page.click("a");\n  await page.waitForTimeout(100);\n  expect(1);')
        self.assertEqual(keys("tests/e2e/a.spec.ts", None, short), [])
        read_only = block('  await page.click("a");\n  expect(await page.evaluate(() => window.innerWidth)).toBe(1);')
        self.assertEqual(keys("tests/e2e/a.spec.ts", None, read_only), [])

    def test_only_added_or_changed_blocks_are_judged(self):
        legacy = block('  await page.goto("/");\n  expect(1);', "old")
        self.assertEqual(keys("tests/e2e/a.spec.ts", legacy, legacy + GOOD), [])
        changed = block('  await page.goto("/x");\n  expect(1);', "old")
        self.assertEqual(keys("tests/e2e/a.spec.ts", legacy, changed), ["e2e.no_action"])

    def test_describe_and_hooks_are_not_test_blocks(self):
        new = ('test.describe("g", () => {\n'
               '  test.beforeEach(async ({ page }) => { await page.goto("/"); });\n'
               '  test("x", async ({ page }) => {\n    await page.click("a");\n    expect(1);\n  });\n});\n')
        self.assertEqual([b.title for b in e2e.extract_tests(new)], ["x"])
        self.assertEqual(keys("tests/e2e/a.spec.ts", None, new), [])

    def test_profile_none_and_non_spec_files_skip_block_rules(self):
        bad = block('  await page.goto("/");')
        self.assertEqual(keys("tests/e2e/a.spec.ts", None, bad, profile="none"), [])
        self.assertEqual(keys("tests/helpers/login.ts", None, bad), [])


class SourceRulesTest(unittest.TestCase):
    def test_imports_of_production_code(self):
        for line in ('import { api } from "../../frontend/src/api";', 'const s = require("../../backend/store");',
                     'const m = await import("../../frontend/src/app.js");'):
            with self.subTest(line=line):
                self.assertEqual(keys("tests/e2e/a.spec.ts", None, line + "\n"), ["e2e.import"])
        self.assertEqual(keys("tests/test_api.py", None, "from backend.store import Store\n"), ["e2e.import"])

    def test_imports_inside_the_test_directory_are_fine(self):
        text = 'import { login } from "./helpers/login";\nimport { x } from "../fixtures/x";\nimport os\n'
        self.assertEqual(keys("tests/e2e/a.ts", None, text), [])
        self.assertEqual(keys("tests/e2e/a.py", None, "import backend_client\nfrom . import helpers\n"), [])

    def test_reading_source_files(self):
        self.assertEqual(keys("tests/e2e/a.ts", None, 'const s = fs.readFileSync("../../frontend/src/app.js");\n'),
                         ["e2e.read_source"])
        self.assertEqual(keys("tests/e2e/a.ts", None, 'execSync("grep -c Foo frontend/src/app.js");\n'),
                         ["e2e.read_source"])
        # Starting the app is fine; it is how a black-box test reaches it.
        self.assertEqual(keys("tests/playwright.config.js", None, 'command: "python3 ../backend/server.py",\n'), [])

    def test_existing_lines_are_not_judged(self):
        old = 'import { api } from "../frontend/src/api";\n'
        self.assertEqual(keys("tests/e2e/a.ts", old, old + "// more\n"), [])


class PlanTablesTest(unittest.TestCase):
    def test_planned_new_and_index(self):
        text = plan(("AC-1", "new", "`checkout as guest`", "closest: login; guest has no session"),
                    ("AC-2", "extend", "login", "add a step"), ("AC-3", "NEW", "pay", "x"))
        self.assertEqual(e2e.planned_new(text), {"checkout as guest", "pay"})
        self.assertEqual(e2e.planned_new("no table"), set())
        self.assertEqual(e2e.indexed(index("a", "b")), {"a", "b"})


class GuardTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = make_repo(CONFIG)
        add_ticket(cls.root, "feature", "0001-a", "testing",
                   gates=["ticket-approved", "design-approved", "plan-approved"])
        cls.wt = add_worktree(cls.root, "feature", "0001-a")
        write(cls.wt / ".mark/features/0001-a/tech-plan.md",
              plan(("AC-1", "new", "add a todo", "closest: none, first journey"),
                   ("AC-2", "extend", "old one", "add a reload step")))
        write(cls.wt / "tests/e2e/old.spec.ts", block('  await page.click("a");\n  expect(1);', "old one"))

    def write(self, rel, content, agent="tester"):
        return hook("pre-write", {"hook_event_name": "PreToolUse", "tool_name": "Write", "cwd": str(self.wt),
                                  "agent_type": agent,
                                  "tool_input": {"file_path": str(self.wt / rel), "content": content}})

    def test_tester_writes_a_real_journey(self):
        self.assertEqual(self.write("tests/e2e/a.spec.ts", GOOD)[0], 0)

    def test_an_unplanned_new_test_is_blocked(self):
        code, err = self.write("tests/e2e/a.spec.ts", GOOD + block('  await page.click("b");\n  expect(2);', "extra"))
        self.assertEqual(code, 2)
        self.assertIn("  - extra", err)
        self.assertIn("may add (plan, `<!-- mark:e2e-plan -->`): add a todo.", err)
        self.assertIn("tests/JOURNEYS.md", err)

    def test_extending_or_moving_an_existing_test_is_free(self):
        longer = block('  await page.click("a");\n  await page.reload();\n  expect(1);', "old one")
        self.assertEqual(self.write("tests/e2e/old.spec.ts", longer)[0], 0)
        self.assertEqual(self.write("tests/e2e/moved.spec.ts", longer)[0], 0)

    def test_white_box_spec_is_blocked_with_every_reason(self):
        bad = 'import { api } from "../../frontend/src/api";\n' + block('  await page.goto("/");', "add a todo")
        code, err = self.write("tests/e2e/a.spec.ts", bad)
        self.assertEqual(code, 2)
        self.assertIn("imports production code", err)
        self.assertIn("no user action", err)
        self.assertIn(": add a todo", err)
        self.assertIn("needs-unit-test", err)


class MergeJourneyTest(unittest.TestCase):
    def setUp(self):
        self.root = make_repo(CONFIG)
        add_origin(self.root)
        write(self.root / "tests/e2e/a.spec.ts", block('  await page.click("a");\n  expect(1);', "old one"))
        write(self.root / "tests/JOURNEYS.md", index("old one"))
        sh(self.root, "git", "add", "-A")
        sh(self.root, "git", "commit", "-qm", "suite")
        status = add_ticket(self.root, "bug", "b0001-x", "pending-merge", gates=["ticket-approved"]) / "status.md"
        status.write_text(status.read_text().replace("desc:", "leftover: 0\ndesc:"))
        sh(self.root, "git", "commit", "-qam", "leftover")
        sh(self.root, "git", "push", "-q", "origin", "main")
        self.wt = add_worktree(self.root, "bug", "b0001-x")
        self.tdir = self.wt / ".mark/bugs/b0001-x"
        write(self.tdir / "verdict.md", "<!-- mark:verdict PASSED -->\n")
        write(self.tdir / "fix-plan.md", plan(("AC-1", "new", "guest checkout", "closest: old one; no login")))

    def commit(self, spec, titles):
        write(self.wt / "tests/e2e/a.spec.ts", spec)
        write(self.wt / "tests/JOURNEYS.md", index(*titles))
        sh(self.wt, "git", "add", "-A")
        sh(self.wt, "git", "commit", "-qm", "tests")
        sh(self.wt, "git", "push", "-q", "-u", "origin", "bug/b0001-x")

    def test_planned_new_test_with_its_index_row_lands(self):
        old = block('  await page.click("a");\n  await page.reload();\n  expect(1);', "old one")
        new = block('  await page.click("g");\n  expect(2);', "guest checkout")
        self.commit(old + new, ["old one", "guest checkout"])
        code, out, err = run(self.root, "merge", "b0001")
        self.assertEqual(code, 0, err + out)

    def test_unplanned_test_is_refused(self):
        spec = block('  await page.click("a");\n  expect(1);', "old one") + block('  await page.click("z");\n  expect(3);', "sneaky")
        self.commit(spec, ["old one", "sneaky"])
        code, _, err = run(self.root, "merge", "b0001")
        self.assertEqual(code, 1)
        self.assertIn("does not name as new", err)
        self.assertIn("  - sneaky", err)

    def test_journeys_command_drafts_the_missing_rows(self):
        code, out, _ = run(self.root, "journeys")
        self.assertEqual(code, 0, out)
        write(self.root / "tests/e2e/b.spec.ts",
              block('  // covers: 0002/AC-1, 0002/AC-3\n  await page.click("a");\n  expect(1);', "new flow"))
        write(self.root / "tests/JOURNEYS.md", index("old one", "gone"))
        code, out, _ = run(self.root, "journeys", str(self.root))
        self.assertEqual(code, 1)
        self.assertIn("| new flow | e2e/b.spec.ts | TODO: entry → steps → outcome | 0002/AC-1, 0002/AC-3 |", out)
        self.assertIn("  - gone", out)

    def test_index_must_match_the_suite(self):
        spec = block('  await page.click("a");\n  expect(1);', "old one") + block('  await page.click("g");\n  expect(2);', "guest checkout")
        self.commit(spec, ["old one", "gone"])
        code, _, err = run(self.root, "merge", "b0001")
        self.assertEqual(code, 1)
        self.assertIn("Tests with no row:\n  - guest checkout", err)
        self.assertIn("Rows with no test:\n  - gone", err)


if __name__ == "__main__":
    unittest.main()
