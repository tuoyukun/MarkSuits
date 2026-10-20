"""The project template must render into a config the engine accepts."""
import re
import tomllib
import unittest
from pathlib import Path

from tests._support import REPO_ROOT

from mark.config import MAIN, MarkConfig

ANSWERS = {"locale": "zh-CN", "profile": "web-fullstack", "project_name": "demo", "main_branch": "main",
           "frontend_dir": "frontend", "backend_dir": "backend", "ui_dir": "frontend/src/ui",
           "tests_dir": "tests"}


def render(text: str) -> str:
    return re.sub(r"\{\{\s*(\w+)\s*\}\}", lambda m: ANSWERS[m.group(1)], text)


class TemplateConfigTest(unittest.TestCase):
    def setUp(self):
        src = (REPO_ROOT / "template/project/.mark/config.toml.jinja").read_text(encoding="utf-8")
        self.cfg = MarkConfig(Path("."), tomllib.loads(render(src)))

    def test_schema_supported(self):
        self.assertEqual(self.cfg.schema, 1)

    def test_rules_only_name_known_roles(self):
        known = self.cfg.roles | {MAIN}
        for rule in self.cfg.write_rules:
            self.assertLessEqual(rule.roles, known, rule.glob)

    def test_gates_and_outputs_cover_roles(self):
        self.assertLessEqual(set(self.cfg.gates), self.cfg.roles)
        self.assertEqual(set(self.cfg.outputs), set(self.cfg.roles))

    def test_ui_rule_precedes_frontend_rule(self):
        globs = [r.glob for r in self.cfg.write_rules]
        self.assertLess(globs.index("frontend/src/ui/**"), globs.index("frontend/**"))


if __name__ == "__main__":
    unittest.main()
