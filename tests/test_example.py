"""The example projects in `examples/` must stay valid, current Mark projects.

- Always: its config loads, every scenario renders for it, its own unit tests pass,
  and `examples/sandbox.py` turns it into a working repository.
- Rendering the template from the recorded answers reproduces the committed files, so the
  example never drifts from the template. Only the files a project is expected to edit
  (`PROJECT_OWNED`) may differ; their pristine copies in `.mark/.base/` may not.
"""
import io
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

from tests._support import REPO_ROOT

from mark import brief, budget, cli, scaffold, tickets
from mark.config import load_config
from mark.flow import SCENARIOS, Action, Ctx

# Example -> (module whose selftest.sh runs its unit tests, commands its CLAUDE.md must name).
EXAMPLES = {
    "todo": ("backend", ("npm --prefix e2e ci", "bash scripts/selftest.sh", "bash scripts/start.sh",
                         "npx playwright test", "bash scripts/selftest.sh && bash scripts/regression.sh")),
    "notes": ("service", ("bash scripts/selftest.sh", "bash scripts/start.sh", "bash regression.sh -k",
                          "bash scripts/selftest.sh && bash scripts/regression.sh")),
    "expenses": ("frontend", ("npm --prefix e2e ci", "bash scripts/selftest.sh", "bash scripts/start.sh",
                              "npx playwright test", "bash scripts/selftest.sh && bash scripts/regression.sh")),
    "habits": ("backend", ("cd app && npm ci", "bash scripts/selftest.sh", "bash scripts/start.sh",
                           "cd e2e && bash regression.sh", "bash scripts/selftest.sh && bash scripts/regression.sh")),
    "tally": ("app", ("cd app && npm ci", "bash scripts/selftest.sh", "bash scripts/start.sh",
                      "cd e2e && bash regression.sh", "bash scripts/selftest.sh && bash scripts/regression.sh")),
}
EXAMPLE = REPO_ROOT / "examples" / "todo"
SANDBOX = REPO_ROOT / "examples" / "sandbox.py"
# Generated once, then filled in by the project.
PROJECT_OWNED = {"CLAUDE.md", ".gitignore"}
SKIP_DIRS = {"node_modules", "test-results", "playwright-report", "__pycache__", ".expo"}


def _answers(root: Path) -> dict[str, str]:
    return tomllib.loads((root / scaffold.RECORD).read_text(encoding="utf-8"))["answers"]


class ExampleProjectTest(unittest.TestCase):
    def examples(self):
        for name in EXAMPLES:
            with self.subTest(example=name):
                yield name, REPO_ROOT / "examples" / name

    def test_config_and_paths(self):
        for _, root in self.examples():
            cfg = load_config(root)
            self.assertEqual(cfg.locale, "en")
            for d in (*cfg.module_dirs, cfg.path("tests")):
                self.assertTrue((root / d).is_dir(), d)

    def test_docs_fit_their_budget(self):
        for _, root in self.examples():
            cfg = load_config(root)
            for p in root.rglob("*.md"):
                rel = p.relative_to(root).as_posix()
                limit = budget.limit_for(cfg, rel)
                if limit and not SKIP_DIRS & set(p.parts):
                    self.assertLessEqual(p.stat().st_size, limit, rel)

    def test_claude_md_is_filled_in(self):
        for name, root in self.examples():
            text = (root / "CLAUDE.md").read_text(encoding="utf-8")
            self.assertNotIn("TODO", text)
            for command in EXAMPLES[name][1]:
                self.assertIn(command, text)

    def test_answers_are_recorded(self):
        for _, root in self.examples():
            answers = _answers(root)
            self.assertEqual(answers, scaffold.resolve(answers, root))
            self.assertEqual(answers["locale"], "en")

    def test_every_scenario_renders(self):
        tmp = Path(tempfile.mkdtemp(prefix="mark-example-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        for name, src in self.examples():
            root = tmp / name
            shutil.copytree(src / ".mark", root / ".mark")
            cfg = load_config(root)
            feature = Ctx(cfg, tickets.claim(cfg, "feature", "demo", slug="demo"))
            bug = Ctx(cfg, tickets.claim(cfg, "bug", "demo", slug="demo"))
            for scenario, role in SCENARIOS.items():
                if role not in cfg.roles:
                    continue
                ctx = bug if role == "fix-plan" else feature
                with self.subTest(example=name, scenario=scenario):
                    action = Action("dispatch", role=role, scenario=scenario, trigger="FAIL-1 (verdict.md)",
                                    review=str(ctx.state_dir / "review-design.md"),
                                    pending_rounds=[1], pending_refs=["R-1"])
                    out = brief.render(ctx, action, prev="done")
                    self.assertNotIn("{{", out)

    def test_unit_tests_pass(self):
        for name, root in self.examples():
            res = subprocess.run(["bash", "selftest.sh"], cwd=root / EXAMPLES[name][0],
                                 capture_output=True, text=True, timeout=120)
            self.assertEqual(res.returncode, 0, res.stderr[-2000:])

    def test_service_example_regression_passes(self):
        root = REPO_ROOT / "examples" / "notes"
        res = subprocess.run(["bash", "scripts/regression.sh"], cwd=root, capture_output=True, text=True,
                             timeout=120)
        self.assertEqual(res.returncode, 0, res.stdout[-2000:] + res.stderr[-2000:])

    def test_sandbox_creates_a_working_repository(self):
        tmp = Path(tempfile.mkdtemp(prefix="mark-sandbox-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        dest = tmp / "todo"
        res = subprocess.run([sys.executable, str(SANDBOX), str(dest)], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertTrue((tmp / "todo.origin.git").is_dir())
        self.assertFalse((dest / "node_modules").exists())
        log = subprocess.run(["git", "log", "--oneline", "origin/main"], cwd=dest,
                             capture_output=True, text=True, check=True).stdout
        self.assertEqual(len(log.splitlines()), 1)
        out = io.StringIO()
        self.assertEqual(cli.main(["status", "--check"], cwd=dest, out=out, err=io.StringIO()), 0)
        # A second run refuses to overwrite.
        again = subprocess.run([sys.executable, str(SANDBOX), str(dest)], capture_output=True, text=True)
        self.assertEqual(again.returncode, 2)


def _files(root: Path) -> dict[str, bytes]:
    out = {}
    for path in root.rglob("*"):
        rel = path.relative_to(root)
        if path.is_file() and not SKIP_DIRS.intersection(rel.parts):
            out[rel.as_posix()] = path.read_bytes()
    return out


class ExampleScaffoldSyncTest(unittest.TestCase):
    def test_scaffold_matches_the_template(self):
        for name in EXAMPLES:
            root = REPO_ROOT / "examples" / name
            with self.subTest(example=name):
                generated, example = scaffold.render(_answers(root)), _files(root)
                stale = [rel for rel, text in generated.items()
                         if (rel not in PROJECT_OWNED and example.get(rel) != text.encode())
                         or example.get(scaffold.base_path(rel)) != text.encode()]
                self.assertEqual(stale, [], f"examples/{name} is out of date with the template; regenerate "
                                            "it (see examples/README.md, 'Updating the examples')")
                for rel in PROJECT_OWNED:
                    self.assertIn(rel, example)
                self.assertTrue(example[".gitignore"].startswith(generated[".gitignore"].encode()))


if __name__ == "__main__":
    unittest.main()
