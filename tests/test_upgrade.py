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
        # Only the version moved: built-ins already reach the project, nothing to upgrade.
        self.assertNotIn("/mark:upgrade", run(self.root, "status")[1])
        write(self.root, scaffold.base_path(".gitignore"), "# old\n")
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

    def lane(self, out):
        branch = re.search(r"`(chore/general-[\d-]+)`", out).group(1)
        wt = Path(re.search(r"worktree (\S+)\.", out).group(1))
        rows = {line.split()[1]: line.split()[0] for line in out.splitlines() if line.startswith("  ")
                and len(line.split()) > 1 and line.split()[1].startswith((".", "C"))}
        return branch, wt, rows

    def test_three_way_upgrade_on_a_lane(self):
        r = self.root
        new = {rel: read(r, scaffold.base_path(rel)) for rel in (".gitignore", ".mark/config.toml", "CLAUDE.md")}
        old = {rel: "# OLD FIRST LINE\n" + text.split("\n", 1)[1] for rel, text in new.items()}
        for rel, text in old.items():
            write(r, scaffold.base_path(rel), text)
        write(r, ".gitignore", old[".gitignore"])                                         # untouched
        write(r, ".mark/config.toml", old[".mark/config.toml"] + "\n[[write_rules]]\nglob = \"docs/**\"\nroles = [\"main\"]\n")
        write(r, "CLAUDE.md", "# PROJECT FIRST LINE\n" + new["CLAUDE.md"].split("\n", 1)[1])
        (r / ".mark/README.md").unlink()                                                   # template added it
        (r / scaffold.base_path(".mark/README.md")).unlink()
        age(r)
        self.commit()
        main_head = sh(r, "git", "rev-parse", "HEAD")

        code, out, err = run(r, "upgrade")
        self.assertEqual(code, 0, err)
        self.assertEqual(sh(r, "git", "rev-parse", "HEAD"), main_head)                     # main untouched
        branch, wt, rows = self.lane(out)
        self.assertEqual(rows[".gitignore"], "updated")
        self.assertEqual(rows[".mark/config.toml"], "merged")
        self.assertEqual(rows["CLAUDE.md"], "CONFLICT")
        self.assertEqual(rows[".mark/README.md"], "added")

        self.assertEqual(read(wt, ".gitignore"), new[".gitignore"])
        config = read(wt, ".mark/config.toml")
        self.assertFalse(config.startswith("# OLD"))
        self.assertIn('glob = "docs/**"', config)
        self.assertIn("<<<<<<< project", read(wt, "CLAUDE.md"))
        for rel, text in new.items():
            self.assertEqual(read(wt, scaffold.base_path(rel)), text)
        rec = tomllib.loads(read(wt, scaffold.RECORD))
        self.assertEqual(rec["version"], scaffold.version())
        self.assertEqual(sh(wt, "git", "status", "--porcelain"), "")

        code, _, err = run(r, "general", "merge", branch)
        self.assertEqual(code, 1)
        self.assertIn("conflict markers", err)
        self.assertIn("CLAUDE.md", err)

        write(wt, "CLAUDE.md", "# PROJECT FIRST LINE\n" + new["CLAUDE.md"].split("\n", 1)[1])
        sh(wt, "git", "commit", "-q", "-am", "resolve")
        code, _, err = run(r, "general", "merge", branch)
        self.assertEqual(code, 0, err)
        self.assertEqual(tomllib.loads(read(r, scaffold.RECORD))["version"], scaffold.version())
        self.assertNotIn("/mark:upgrade", run(r, "status")[1])

    def test_project_deleted_file_stays_deleted(self):
        r = self.root
        write(r, scaffold.base_path(".mark/README.md"), "# old\n")
        (r / ".mark/README.md").unlink()
        age(r)
        self.commit()
        code, out, err = run(r, "upgrade", "--dry-run")
        self.assertEqual(code, 0, err)
        self.assertIn("skipped    .mark/README.md", out)

    def test_copies_of_builtins_from_v016_become_overrides_only_if_edited(self):
        """Up to v0.16, init copied role agents, prompts and formats into the project."""
        r = self.root
        for rel, text in ((".claude/agents/designer.md", "designer v0.16\n"),
                          (".mark/prompts/coder-plan.md", "prompt v0.16\n"),
                          (".mark/collaboration.md", "collab v0.16\n")):
            write(r, rel, text)
            write(r, scaffold.base_path(rel), text)
        write(r, ".mark/prompts/coder-plan.md", "prompt v0.16\nOUR RULE\n")              # the project edited it
        age(r)
        self.commit()
        code, out, err = run(r, "upgrade")
        self.assertEqual(code, 0, err)
        _, wt, rows = self.lane(out)
        self.assertEqual(rows[".claude/agents/designer.md"], "removed")
        self.assertEqual(rows[".mark/collaboration.md"], "removed")
        self.assertEqual(rows[".mark/prompts/coder-plan.md"], "kept")
        self.assertFalse((wt / ".claude/agents/designer.md").exists())
        self.assertEqual(read(wt, ".mark/prompts/coder-plan.md"), "prompt v0.16\nOUR RULE\n")
        self.assertFalse((wt / scaffold.base_path(".mark/prompts/coder-plan.md")).exists())

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
