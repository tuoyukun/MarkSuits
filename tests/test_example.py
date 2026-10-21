"""The example project in `examples/todo` must stay a valid, current Mark project.

- Always: its config loads, every scenario renders for it, its own unit tests pass,
  and `examples/sandbox.py` turns it into a working repository.
- With Copier: regenerating the scaffold from the recorded answers reproduces the
  committed files, so the example never drifts from the template. Only the files a
  project is expected to edit (`PROJECT_OWNED`) may differ.
"""
import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests._support import REPO_ROOT

from mark import brief, budget, cli, tickets
from mark.config import load_config
from mark.flow import SCENARIOS, Action, Ctx

EXAMPLE = REPO_ROOT / "examples" / "todo"
SANDBOX = REPO_ROOT / "examples" / "sandbox.py"
# Generated once, then filled in by the project.
PROJECT_OWNED = {"CLAUDE.md", ".gitignore"}
SKIP_DIRS = {"node_modules", "test-results", "playwright-report", "__pycache__"}


def _answers(root: Path) -> dict[str, str]:
    out = {}
    for line in (root / ".mark/.copier-answers.yml").read_text(encoding="utf-8").splitlines():
        key, sep, value = line.partition(": ")
        if sep and not key.startswith("#"):
            out[key] = value
    return out


class ExampleProjectTest(unittest.TestCase):
    def test_config_and_paths(self):
        cfg = load_config(EXAMPLE)
        self.assertEqual(cfg.locale, "en")
        for key in ("frontend", "backend", "ui", "tests"):
            self.assertTrue((EXAMPLE / cfg._section("paths")[key]).is_dir(), key)

    def test_docs_fit_their_budget(self):
        cfg = load_config(EXAMPLE)
        for p in EXAMPLE.rglob("*.md"):
            rel = p.relative_to(EXAMPLE).as_posix()
            limit = budget.limit_for(cfg, rel)
            if limit and not SKIP_DIRS & set(p.parts):
                self.assertLessEqual(p.stat().st_size, limit, rel)

    def test_claude_md_is_filled_in(self):
        text = (EXAMPLE / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertNotIn("TODO", text)
        for command in ("npm ci", "npm run test:unit", "npm run check", "npx playwright test", "npm test"):
            self.assertIn(command, text)

    def test_answers_point_at_this_repo(self):
        answers = _answers(EXAMPLE)
        self.assertEqual(answers["_src_path"], "../..")
        self.assertEqual(answers["locale"], "en")

    def test_every_scenario_renders(self):
        tmp = Path(tempfile.mkdtemp(prefix="mark-example-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        root = tmp / "todo"
        shutil.copytree(EXAMPLE / ".mark", root / ".mark")
        cfg = load_config(root)
        feature = Ctx(cfg, tickets.claim(cfg, "feature", "demo", slug="demo"))
        bug = Ctx(cfg, tickets.claim(cfg, "bug", "demo", slug="demo"))
        for scenario, role in SCENARIOS.items():
            ctx = bug if role == "fix-plan" else feature
            with self.subTest(scenario=scenario):
                action = Action("dispatch", role=role, scenario=scenario, trigger="FAIL-1 (verdict.md)",
                                review=str(ctx.state_dir / "review-design.md"),
                                pending_rounds=[1], pending_refs=["R-1"])
                out = brief.render(ctx, action, prev="done")
                self.assertNotIn("{{", out)

    def test_backend_unit_tests_pass(self):
        res = subprocess.run([sys.executable, "-m", "unittest", "-q"], cwd=EXAMPLE / "backend",
                             capture_output=True, text=True, timeout=120)
        self.assertEqual(res.returncode, 0, res.stderr[-2000:])

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


def _copier() -> str | None:
    return os.environ.get("MARK_COPIER") or shutil.which("copier")


def _files(root: Path) -> dict[str, bytes]:
    out = {}
    for path in root.rglob("*"):
        rel = path.relative_to(root)
        if path.is_file() and not SKIP_DIRS.intersection(rel.parts):
            out[rel.as_posix()] = path.read_bytes()
    return out


@unittest.skipUnless(_copier(), "copier not installed (set MARK_COPIER or put copier on PATH)")
class ExampleScaffoldSyncTest(unittest.TestCase):
    def test_scaffold_matches_the_template(self):
        tmp = Path(tempfile.mkdtemp(prefix="mark-example-gen-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        answers = {k: v for k, v in _answers(EXAMPLE).items() if not k.startswith("_")}
        args = [a for k, v in answers.items() for a in ("-d", f"{k}={v}")]
        subprocess.run([_copier(), "copy", "--defaults", "--quiet", "--vcs-ref", "HEAD", *args,
                        str(REPO_ROOT), str(tmp)], check=True, capture_output=True, text=True)
        generated, example = _files(tmp), _files(EXAMPLE)
        stale = [rel for rel, data in generated.items()
                 if rel not in PROJECT_OWNED and rel != ".mark/.copier-answers.yml"
                 and example.get(rel) != data]
        self.assertEqual(stale, [], "examples/todo is out of date with the template; regenerate it "
                                    "(see examples/README.md, 'Updating the example')")
        for rel in PROJECT_OWNED:
            self.assertIn(rel, example)
        self.assertTrue(example[".gitignore"].startswith(generated[".gitignore"]))


if __name__ == "__main__":
    unittest.main()
