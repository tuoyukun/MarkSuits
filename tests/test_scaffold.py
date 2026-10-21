"""`mark init`: checks before writing, existing-project handling, commit and push."""
import io
import shutil
import tempfile
import tomllib
import unittest
from pathlib import Path

from tests._support import add_origin, sh

from mark import cli, scaffold
from mark.config import load_config


def init(cwd: Path, *args: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    code = cli.main(["init", *args], cwd=cwd, out=out, err=err)
    return code, out.getvalue(), err.getvalue()


def tmpdir(test: unittest.TestCase) -> Path:
    d = Path(tempfile.mkdtemp(prefix="mark-init-")).resolve()
    test.addCleanup(shutil.rmtree, d, True)
    return d


def repo(test: unittest.TestCase, files: dict[str, str] | None = None, branch: str = "main") -> Path:
    root = tmpdir(test)
    sh(root, "git", "init", "-q", "-b", branch)
    for rel, text in (files or {"README.md": "hi\n"}).items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")
    sh(root, "git", "add", "-A")
    sh(root, "git", "commit", "-q", "-m", "existing")
    return root


class FreshDirectoryTest(unittest.TestCase):
    def test_empty_dir_becomes_a_mark_repository(self):
        root = tmpdir(self)
        code, out, err = init(root, "--project-name", "demo")
        self.assertEqual(code, 0, err)
        self.assertEqual(sh(root, "git", "branch", "--show-current"), "main")
        self.assertEqual(sh(root, "git", "log", "--format=%s"), f"chore: set up Mark v{scaffold.version()}")
        self.assertEqual(sh(root, "git", "status", "--porcelain"), "")
        self.assertEqual(load_config(root).data["project"]["name"], "demo")
        self.assertIn("TODO", (root / "CLAUDE.md").read_text(encoding="utf-8"))

    def test_non_empty_dir_without_git_is_refused(self):
        root = tmpdir(self)
        (root / "app.py").write_text("x\n")
        code, _, err = init(root)
        self.assertEqual(code, 1)
        self.assertIn("not a git repository", err)
        self.assertFalse((root / ".git").exists())


class ChecksTest(unittest.TestCase):
    def test_already_a_mark_project(self):
        root = repo(self)
        self.assertEqual(init(root)[0], 0)
        code, _, err = init(root)
        self.assertEqual(code, 1)
        self.assertIn("already a Mark project", err)

    def test_dirty_tree_is_refused(self):
        root = repo(self)
        (root / "README.md").write_text("changed\n")
        code, _, err = init(root)
        self.assertEqual(code, 1)
        self.assertIn("uncommitted changes", err)
        self.assertFalse((root / ".mark").exists())

    def test_wrong_branch_is_refused(self):
        root = repo(self, branch="develop")
        code, _, err = init(root, "--main-branch", "main")
        self.assertEqual(code, 1)
        self.assertIn("`develop`", err)

    def test_main_branch_defaults_to_the_current_one(self):
        root = repo(self, branch="trunk")
        self.assertEqual(init(root)[0], 0)
        self.assertEqual(load_config(root).main_branch, "trunk")

    def test_existing_role_file_is_a_conflict(self):
        root = repo(self, {".claude/agents/tester.md": "mine\n"})
        code, _, err = init(root)
        self.assertEqual(code, 1)
        self.assertIn(".claude/agents/tester.md", err)
        self.assertFalse((root / ".mark").exists())
        self.assertEqual((root / ".claude/agents/tester.md").read_text(), "mine\n")

    def test_bad_answers(self):
        root = repo(self)
        for args, text in ((["--frontend-dir", "../web"], "inside the repository"),
                           (["--locale", "fr"], "must be one of"),
                           (["--colour", "red"], "Unknown answer"),
                           (["--project-name"], "usage")):
            with self.subTest(args=args):
                code, _, err = init(root, *args)
                self.assertNotEqual(code, 0)
                self.assertIn(text, err)
        self.assertFalse((root / ".mark").exists())

    def test_dry_run_writes_nothing(self):
        root = repo(self)
        code, out, _ = init(root, "--dry-run", "--regression-cmd", "npm test")
        self.assertEqual(code, 0)
        self.assertIn('--regression-cmd "npm test"', out)
        self.assertFalse((root / ".mark").exists())


class ExistingProjectTest(unittest.TestCase):
    def setUp(self):
        self.root = repo(self, {"CLAUDE.md": "# Our project\n", ".gitignore": "node_modules\n.env\n",
                                "web/index.html": "<p>\n"})
        self.origin = add_origin(self.root)
        code, self.out, err = init(self.root, "--frontend-dir", "web", "--regression-cmd", 'make "all"')
        self.assertEqual(code, 0, err)

    def test_claude_md_is_kept_and_not_recorded_as_template(self):
        self.assertEqual((self.root / "CLAUDE.md").read_text(), "# Our project\n")
        self.assertFalse((self.root / scaffold.base_path("CLAUDE.md")).exists())

    def test_gitignore_gains_only_missing_lines(self):
        lines = (self.root / ".gitignore").read_text().splitlines()
        self.assertEqual(lines.count(".env"), 1)
        self.assertIn(".claude/worktrees/", lines)
        self.assertEqual(lines[0], "node_modules")

    def test_answers_reach_config_and_record(self):
        cfg = load_config(self.root)
        self.assertEqual(cfg.merge_regression, 'make "all"')
        self.assertIn("web/src/ui/**", [r.glob for r in cfg.write_rules])
        record = tomllib.loads((self.root / scaffold.RECORD).read_text())
        self.assertEqual(record["answers"]["ui_dir"], "web/src/ui")

    def test_committed_and_pushed(self):
        self.assertEqual(sh(self.root, "git", "status", "--porcelain"), "")
        self.assertEqual(sh(self.root, "git", "rev-parse", "main"), sh(self.origin, "git", "rev-parse", "main"))
        self.assertIn("Pushed main", self.out)

    def test_mark_commands_work_afterwards(self):
        out = io.StringIO()
        self.assertEqual(cli.main(["status", "--check"], cwd=self.root / "web", out=out, err=io.StringIO()), 0)


if __name__ == "__main__":
    unittest.main()
