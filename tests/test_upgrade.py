"""`mark upgrade`: 3-way merge against .mark/.base/ on a general lane, stale-template notice."""
import io
import re
import tomllib
import unittest
from pathlib import Path

from tests._support import sh
from tests.test_scaffold import init, repo

from mark import cli, scaffold


def run(cwd: Path, *args: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    code = cli.main(list(args), cwd=cwd, out=out, err=err)
    return code, out.getvalue(), err.getvalue()


def write(root: Path, rel: str, text: str) -> None:
    (root / rel).parent.mkdir(parents=True, exist_ok=True)
    (root / rel).write_text(text, encoding="utf-8")


def read(root: Path, rel: str) -> str:
    return (root / rel).read_text(encoding="utf-8")


def age(root: Path, version: str = "0.1.0") -> None:
    """Pretend the project was set up by an older plugin."""
    rec = read(root, scaffold.RECORD)
    write(root, scaffold.RECORD, re.sub(r'version = "[^"]+"', f'version = "{version}"', rec))


class UpgradeTest(unittest.TestCase):
    def setUp(self):
        self.root = repo(self)
        code, _, err = init(self.root)
        self.assertEqual(code, 0, err)

    def commit(self):
        sh(self.root, "git", "add", "-A")
        sh(self.root, "git", "commit", "-q", "-m", "old template")

    def test_current_project_is_not_upgraded_and_has_no_notice(self):
        code, _, err = run(self.root, "upgrade")
        self.assertEqual(code, 1)
        self.assertIn("already at", err)
        self.assertNotIn("/mark:upgrade", run(self.root, "status")[1])

    def test_stale_notice_in_status_and_next(self):
        age(self.root)
        self.commit()
        self.assertIn("/mark:upgrade", run(self.root, "status")[1])
        sh(self.root, "git", "rm", "-q", scaffold.RECORD)
        self.assertNotIn("/mark:upgrade", run(self.root, "status")[1])

    def test_dry_run_writes_nothing(self):
        age(self.root)
        self.commit()
        head = sh(self.root, "git", "rev-parse", "HEAD")
        code, out, err = run(self.root, "upgrade", "--dry-run")
        self.assertEqual(code, 0, err)
        self.assertIn("v0.1.0 ->", out)
        self.assertEqual(sh(self.root, "git", "rev-parse", "HEAD"), head)
        self.assertEqual(sh(self.root, "git", "branch", "--list", "chore/general-*"), "")

    def test_three_way_upgrade_on_a_lane(self):
        r = self.root
        new = {rel: read(r, scaffold.base_path(rel)) for rel in
               (".mark/prompts/coder-impl.md", ".claude/agents/designer.md",
                ".mark/collaboration.md", ".mark/formats/bug.md")}
        old = {rel: "OLD FIRST LINE\n" + text.split("\n", 1)[1] for rel, text in new.items()}
        for rel, text in old.items():
            write(r, scaffold.base_path(rel), text)
        write(r, ".mark/prompts/coder-impl.md", old[".mark/prompts/coder-impl.md"])         # untouched
        write(r, ".claude/agents/designer.md", old[".claude/agents/designer.md"] + "PROJECT RULE\n")
        write(r, ".mark/collaboration.md", "PROJECT FIRST LINE\n" + new[".mark/collaboration.md"].split("\n", 1)[1])
        (r / ".mark/formats/bug.md").unlink()                                              # project deleted it
        write(r, ".mark/prompts/obsolete.md", "gone\n")                                    # template dropped it
        write(r, scaffold.base_path(".mark/prompts/obsolete.md"), "gone\n")
        (r / ".mark/formats/verdict.md").unlink()                                          # template added it
        (r / scaffold.base_path(".mark/formats/verdict.md")).unlink()
        age(r)
        self.commit()
        main_head = sh(r, "git", "rev-parse", "HEAD")

        code, out, err = run(r, "upgrade")
        self.assertEqual(code, 0, err)
        self.assertEqual(sh(r, "git", "rev-parse", "HEAD"), main_head)                     # main untouched
        branch = re.search(r"`(chore/general-[\d-]+)`", out).group(1)
        wt = Path(re.search(r"worktree (\S+)\.", out).group(1))
        rows = {line.split()[1]: line.split()[0] for line in out.splitlines() if line.startswith("  ")
                and len(line.split()) > 1 and line.split()[1].startswith(".")}
        self.assertEqual(rows[".mark/prompts/coder-impl.md"], "updated")
        self.assertEqual(rows[".claude/agents/designer.md"], "merged")
        self.assertEqual(rows[".mark/collaboration.md"], "CONFLICT")
        self.assertEqual(rows[".mark/formats/bug.md"], "skipped")
        self.assertEqual(rows[".mark/prompts/obsolete.md"], "removed")
        self.assertEqual(rows[".mark/formats/verdict.md"], "added")

        self.assertEqual(read(wt, ".mark/prompts/coder-impl.md"), new[".mark/prompts/coder-impl.md"])
        designer = read(wt, ".claude/agents/designer.md")
        self.assertFalse(designer.startswith("OLD"))
        self.assertTrue(designer.endswith("PROJECT RULE\n"))
        self.assertIn("<<<<<<< project", read(wt, ".mark/collaboration.md"))
        self.assertFalse((wt / ".mark/formats/bug.md").exists())
        self.assertFalse((wt / ".mark/prompts/obsolete.md").exists())
        self.assertFalse((wt / scaffold.base_path(".mark/prompts/obsolete.md")).exists())
        self.assertTrue((wt / ".mark/formats/verdict.md").exists())
        for rel, text in new.items():
            self.assertEqual(read(wt, scaffold.base_path(rel)), text)
        rec = tomllib.loads(read(wt, scaffold.RECORD))
        self.assertEqual(rec["version"], scaffold.version())
        self.assertEqual(sh(wt, "git", "status", "--porcelain"), "")

        code, _, err = run(r, "general", "merge", branch)
        self.assertEqual(code, 1)
        self.assertIn("conflict markers", err)
        self.assertIn(".mark/collaboration.md", err)

        write(wt, ".mark/collaboration.md", "PROJECT FIRST LINE\n" + new[".mark/collaboration.md"].split("\n", 1)[1])
        sh(wt, "git", "commit", "-q", "-am", "resolve")
        code, _, err = run(r, "general", "merge", branch)
        self.assertEqual(code, 0, err)
        self.assertEqual(tomllib.loads(read(r, scaffold.RECORD))["version"], scaffold.version())
        self.assertNotIn("/mark:upgrade", run(r, "status")[1])

    def test_project_claude_md_without_base_is_left_alone(self):
        root = repo(self, {"CLAUDE.md": "# mine\n"})
        self.assertEqual(init(root)[0], 0)
        age(root)
        sh(root, "git", "commit", "-qam", "old")
        code, out, err = run(root, "upgrade", "--dry-run")
        self.assertEqual(code, 0, err)
        self.assertNotIn("CLAUDE.md", out)


if __name__ == "__main__":
    unittest.main()
