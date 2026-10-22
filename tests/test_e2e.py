"""Black-box rules for the tester's end-to-end tests (mark.e2e and the pre-write guard)."""
import unittest

from tests._support import FULL_CONFIG, add_ticket, add_worktree, hook, make_repo

from mark import e2e

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


class GuardTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = make_repo(FULL_CONFIG + '\n[paths]\ntests = "tests"\nfrontend = "frontend"\n'
                                           'backend = "backend"\n\n[tests]\nprofile = "playwright"\n')
        add_ticket(cls.root, "feature", "0001-a", "testing",
                   gates=["ticket-approved", "design-approved", "plan-approved"])
        cls.wt = add_worktree(cls.root, "feature", "0001-a")

    def write(self, rel, content, agent="tester"):
        return hook("pre-write", {"hook_event_name": "PreToolUse", "tool_name": "Write", "cwd": str(self.wt),
                                  "agent_type": agent,
                                  "tool_input": {"file_path": str(self.wt / rel), "content": content}})

    def test_tester_writes_a_real_journey(self):
        self.assertEqual(self.write("tests/e2e/a.spec.ts", GOOD)[0], 0)

    def test_white_box_spec_is_blocked_with_every_reason(self):
        bad = 'import { api } from "../../frontend/src/api";\n' + block('  await page.goto("/");', "opens")
        code, err = self.write("tests/e2e/a.spec.ts", bad)
        self.assertEqual(code, 2)
        self.assertIn("imports production code", err)
        self.assertIn("no user action", err)
        self.assertIn(": opens", err)
        self.assertIn("needs-unit-test", err)


if __name__ == "__main__":
    unittest.main()
