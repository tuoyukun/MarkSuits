import io
import json
import unittest
from contextlib import redirect_stderr

from tests._support import make_project

from mark.hookio import EXIT_ALLOW, EXIT_BLOCK, block, normalize_agent_type, run


def _run(payload, handler):
    stream = io.StringIO(json.dumps(payload))
    err = io.StringIO()
    with redirect_stderr(err), self_raises_exit() as box:
        run(handler, stream=stream)
    return box.code, err.getvalue()


class self_raises_exit:
    """Capture SystemExit code from run()."""

    def __enter__(self):
        self.code = None
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is SystemExit:
            self.code = exc.code
            return True
        return False


class NormalizeAgentTypeTest(unittest.TestCase):
    def test_strips_plugin_prefix(self):
        self.assertEqual(normalize_agent_type("mark:coder-impl"), "coder-impl")

    def test_keeps_bare_name(self):
        self.assertEqual(normalize_agent_type("tester"), "tester")

    def test_main_thread_is_none(self):
        self.assertIsNone(normalize_agent_type(None))


class RunTest(unittest.TestCase):
    def test_silent_outside_mark_project(self):
        called = []
        code, _ = _run({"cwd": str(make_project(None))}, called.append)
        self.assertEqual(code, EXIT_ALLOW)
        self.assertEqual(called, [])

    def test_handler_receives_context(self):
        seen = {}

        def handler(ctx):
            seen["agent"] = ctx.agent_type
            seen["locale"] = ctx.config.locale

        root = make_project()
        code, _ = _run({"cwd": str(root), "agent_type": "mark:tester"}, handler)
        self.assertEqual(code, EXIT_ALLOW)
        self.assertEqual(seen, {"agent": "tester", "locale": "zh-CN"})

    def test_handler_can_block(self):
        root = make_project()
        code, err = _run({"cwd": str(root)}, lambda ctx: block("nope"))
        self.assertEqual(code, EXIT_BLOCK)
        self.assertIn("[BLOCKED] nope", err)

    def test_incompatible_config_blocks(self):
        root = make_project("mark_schema = 99\n")
        code, err = _run({"cwd": str(root)}, lambda ctx: None)
        self.assertEqual(code, EXIT_BLOCK)
        self.assertIn("mark_schema=99", err)


class BrokenConfigTest(unittest.TestCase):
    """A config that does not load must not lock the human out: they need to fix it."""

    def setUp(self):
        from tests._support import hook
        self.hook = hook
        self.root = make_project("mark_schema = 1\nlocale = 'en\n")  # broken TOML
        self.config = str(self.root / ".mark" / "config.toml")

    def run_group(self, group, agent=None, **payload):
        payload = {"cwd": str(self.root), **payload}
        if agent:
            payload["agent_type"] = agent
        return self.hook(group, payload)[0]

    def test_prompts_still_reach_claude(self):
        self.assertEqual(self.run_group("user-prompt", prompt="help me fix the config"), 0)

    def test_main_thread_may_fix_the_config_and_use_bash(self):
        self.assertEqual(self.run_group("pre-write", tool_name="Edit", tool_input={"file_path": self.config}), 0)
        self.assertEqual(self.run_group("pre-write", tool_name="Edit",
                                        tool_input={"file_path": ".mark/config.toml"}), 0)
        self.assertEqual(self.run_group("pre-bash", tool_input={"command": "cat .mark/config.toml"}), 0)

    def test_everything_else_stays_blocked(self):
        self.assertEqual(self.run_group("pre-write", tool_name="Write",
                                        tool_input={"file_path": str(self.root / "x.md")}), 2)
        self.assertEqual(self.run_group("pre-write", "tester", tool_name="Edit",
                                        tool_input={"file_path": self.config}), 2)
        self.assertEqual(self.run_group("pre-bash", "coder-impl", tool_input={"command": "ls"}), 2)
        self.assertEqual(self.run_group("pre-dispatch", tool_input={"subagent_type": "designer"}), 2)


if __name__ == "__main__":
    unittest.main()
