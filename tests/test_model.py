"""The board's model setting: what it accepts, what the page sees, how a session is launched."""
from __future__ import annotations

import stat
import unittest

from tests._support import make_repo

from mark import model
from mark.config import load_config

DEEPSEEK = {"provider": "custom", "model": "deepseek-chat", "base_url": "https://api.deepseek.com/anthropic",
            "api_key": "sk-secret"}


class ModelTest(unittest.TestCase):
    def setUp(self):
        self.cfg = load_config(make_repo())

    def test_default_is_opus_on_the_cli_login(self):
        self.assertEqual(model.load(self.cfg), {"provider": "anthropic", "model": "opus"})
        args, env = model.launch(model.load(self.cfg), {"ANTHROPIC_API_KEY": "a", "X": "1"})
        self.assertEqual((args, env), (["--model=opus"], {"ANTHROPIC_API_KEY": "a", "X": "1"}))

    def test_custom_endpoint_gets_its_own_credentials_only(self):
        self.assertEqual(model.save(self.cfg, DEEPSEEK), (True, ""))
        self.assertEqual(stat.S_IMODE(model.path(self.cfg).stat().st_mode), 0o600)
        args, env = model.launch(model.load(self.cfg), {"ANTHROPIC_API_KEY": "a", "CLAUDE_CODE_OAUTH_TOKEN": "o",
                                                        "CLAUDE_CODE_USE_BEDROCK": "1", "X": "1"})
        self.assertEqual(args, ["--model=deepseek-chat"])
        self.assertEqual(env["ANTHROPIC_BASE_URL"], "https://api.deepseek.com/anthropic")
        self.assertEqual(env["ANTHROPIC_AUTH_TOKEN"], "sk-secret")
        for var in ("ANTHROPIC_MODEL", "ANTHROPIC_DEFAULT_OPUS_MODEL", "ANTHROPIC_DEFAULT_HAIKU_MODEL",
                    "CLAUDE_CODE_SUBAGENT_MODEL"):
            self.assertEqual(env[var], "deepseek-chat")
        for gone in ("ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN", "CLAUDE_CODE_USE_BEDROCK"):
            self.assertNotIn(gone, env)
        self.assertEqual(env["X"], "1")

    def test_an_empty_key_keeps_the_stored_one_and_the_page_never_sees_it(self):
        model.save(self.cfg, DEEPSEEK)
        self.assertEqual(model.save(self.cfg, {**DEEPSEEK, "model": "deepseek-reasoner", "api_key": ""}), (True, ""))
        self.assertEqual(model.load(self.cfg)["api_key"], "sk-secret")
        pub = model.public(model.load(self.cfg))
        self.assertNotIn("sk-secret", str(pub))
        self.assertEqual((pub["has_key"], pub["label"]), (True, "deepseek-reasoner @ api.deepseek.com"))
        model.save(self.cfg, {"provider": "anthropic", "model": "sonnet"})
        self.assertEqual(model.load(self.cfg), {"provider": "anthropic", "model": "sonnet"})

    def test_bad_settings_are_refused(self):
        for req in ({"provider": "openai", "model": "x"}, {"provider": "anthropic", "model": ""},
                    {"provider": "anthropic", "model": "opus --dangerously"}, {"provider": "anthropic", "model": 1},
                    {**DEEPSEEK, "base_url": "file:///etc"}, {**DEEPSEEK, "api_key": ""}, "x"):
            self.assertEqual(model.save(self.cfg, req), (False, "bad request"), req)
        self.assertFalse(model.path(self.cfg).exists())

    def test_a_broken_file_falls_back_to_the_default(self):
        model.path(self.cfg).parent.mkdir(parents=True, exist_ok=True)
        model.path(self.cfg).write_text('{"provider": "custom", "model": "x"}')
        self.assertEqual(model.load(self.cfg), model.DEFAULT)


if __name__ == "__main__":
    unittest.main()
