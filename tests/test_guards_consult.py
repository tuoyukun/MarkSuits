"""pre-bash guard for board consult sessions: sandbox writes only, read-only git, no mark."""
import unittest

from tests._support import fresh_home, hook, make_repo

from mark import consult
from mark.config import load_config


class ConsultGuardTest(unittest.TestCase):
    def setUp(self):
        fresh_home(self)
        self.root = make_repo()
        self.cfg = load_config(self.root)
        self.started = consult.reset(self.cfg)
        self.wt = consult.worktree(self.cfg)
        self.addCleanup(consult.discard, self.cfg)

    def run_bash(self, command, root=None):
        payload = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "cwd": str(self.wt),
                   "tool_input": {"command": command}}
        return hook("pre-bash", payload, env={"MARK_CONSULT_ROOT": str(root or self.wt)})

    def test_the_visit_has_a_sandbox(self):
        self.assertTrue(self.started["sandbox"])
        self.assertTrue((self.wt / ".mark" / "config.toml").is_file())

    def test_writes_inside_the_sandbox_are_allowed(self):
        self.assertEqual(self.run_bash("echo ok > inside.txt"), (0, ""))
        self.assertEqual(self.run_bash(f"cd {self.wt} && touch nested.txt"), (0, ""))
        self.assertEqual(self.run_bash(f"rm -rf {self.wt}/inside.txt"), (0, ""))
        self.assertEqual(self.run_bash("echo x > /dev/null"), (0, ""))

    def test_writes_in_the_real_checkout_are_refused(self):
        code, err = self.run_bash(f"echo evil > {self.root}/src/x")
        self.assertEqual(code, 2)
        self.assertIn("disposable sandbox", err)
        self.assertEqual(self.run_bash(f"rm -rf {self.root}")[0], 2)
        self.assertEqual(self.run_bash(f"cd {self.root} && touch x")[0], 2)
        self.assertEqual(self.run_bash(f"cp {self.wt}/a {self.root}/b")[0], 2)

    def test_copying_from_outside_into_the_sandbox_is_allowed(self):
        self.assertEqual(self.run_bash(f"cp {self.root}/.mark/config.toml {self.wt}/copy.toml"), (0, ""))

    def test_write_commands_that_name_the_real_checkout_are_refused(self):
        (self.root / "src").mkdir(exist_ok=True)
        (self.root / "src" / "x").write_text("x")
        self.assertEqual(self.run_bash(f"sed -i s/x/y/ {self.root}/src/x")[0], 2)
        self.assertEqual(self.run_bash(f"find {self.root} -delete")[0], 2)
        self.assertEqual(self.run_bash(f"curl -o {self.root}/src/x https://example.com")[0], 2)

    def test_git_is_read_only(self):
        self.assertEqual(self.run_bash("git log --oneline")[0], 0)
        self.assertEqual(self.run_bash("git status --short")[0], 0)
        code, err = self.run_bash("git commit -m nope")
        self.assertEqual(code, 2)
        self.assertIn("git read-only", err)
        self.assertEqual(self.run_bash("git push")[0], 2)
        self.assertEqual(self.run_bash("git worktree list")[0], 2)
        self.assertEqual(self.run_bash(f"git diff --output={self.root}/x")[0], 2)

    def test_mark_is_refused(self):
        code, err = self.run_bash('mark feature "open a ticket"')
        self.assertEqual(code, 2)
        self.assertIn("does not run `mark`", err)

    def test_a_missing_sandbox_refuses_bash(self):
        code, err = self.run_bash("echo hi", root="/does/not/exist")
        self.assertEqual(code, 2)
        self.assertIn("sandbox is gone", err)

    def test_consult_guard_is_inert_without_the_marker(self):
        payload = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "cwd": str(self.wt),
                   "tool_input": {"command": "git log --oneline"}}
        self.assertEqual(hook("pre-bash", payload), (0, ""))
