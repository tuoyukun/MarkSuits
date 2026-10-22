import unittest

from tests._support import make_project

from mark.config import ConfigError, find_project_root, load_config


class FindProjectRootTest(unittest.TestCase):
    def test_finds_root_from_nested_dir(self):
        root = make_project()
        nested = root / "a" / "b"
        nested.mkdir(parents=True)
        self.assertEqual(find_project_root(nested), root.resolve())

    def test_returns_none_outside_mark_project(self):
        self.assertIsNone(find_project_root(make_project(config_text=None)))

    def test_returns_none_for_empty_start(self):
        self.assertIsNone(find_project_root(None))


class LoadConfigTest(unittest.TestCase):
    def test_loads_locale_and_state_dir(self):
        root = make_project()
        cfg = load_config(root)
        self.assertEqual(cfg.locale, "zh-CN")
        self.assertEqual(cfg.state_dir, root / ".mark")

    def test_rejects_unknown_schema(self):
        root = make_project('mark_schema = 99\n')
        with self.assertRaises(ConfigError):
            load_config(root)

    def test_doc_budget_is_optional_and_skips_malformed_rules(self):
        self.assertEqual(load_config(make_project()).doc_budget, [])
        cfg = load_config(make_project('mark_schema = 1\n'
                                       '[[doc_budget]]\nglob = "a.md"\nmax_bytes = 10\n'
                                       '[[doc_budget]]\nglob = "b.md"\nmax_bytes = "10"\n'
                                       '[[doc_budget]]\nglob = "c.md"\nmax_bytes = -1\n'
                                       '[[doc_budget]]\nmax_bytes = 5\n'))
        self.assertEqual([(r.glob, r.max_bytes) for r in cfg.doc_budget], [("a.md", 10)])

    def test_worktree_setup_is_optional(self):
        cfg = load_config(make_project())
        self.assertEqual((cfg.worktree_setup, cfg.worktree_setup_timeout), ("", 300))
        cfg = load_config(make_project('mark_schema = 1\n[worktree]\nsetup = " npm ci "\nsetup_timeout = 60\n'))
        self.assertEqual((cfg.worktree_setup, cfg.worktree_setup_timeout), ("npm ci", 60))
        cfg = load_config(make_project('mark_schema = 1\n[worktree]\nsetup_timeout = "60"\n'))
        self.assertEqual(cfg.worktree_setup_timeout, 300)

    def test_worktree_ports_are_optional_and_skip_bad_ranges(self):
        cfg = load_config(make_project())
        self.assertEqual((cfg.worktree_ports, cfg.worktree_port_slots), ({}, 100))
        cfg = load_config(make_project(
            'mark_schema = 1\n[worktree]\nport_slots = 10\n'
            'ports = { OK = 5200, "bad-name" = 5300, LOW = 80, HIGH = 65530, TEXT = "5400" }\n'))
        self.assertEqual((cfg.worktree_ports, cfg.worktree_port_slots), ({"OK": 5200}, 10))

    def test_artifact_write_rules_default_and_project_rules_replace_them(self):
        cfg = load_config(make_project('mark_schema = 1\n[[write_rules]]\nglob = "**/design.md"\n'
                                       'roles = ["designer", "main"]\n[[write_rules]]\nglob = "src/**"\nroles = ["coder-impl"]\n'))
        rules = {r.glob: r.roles for r in cfg.write_rules}
        self.assertEqual(rules[".mark/*/*/requirement.md"], {"main"})
        self.assertEqual(rules["**/design.md"], {"designer", "main"})
        self.assertNotIn(".mark/*/*/design.md", rules)   # a legacy **/ override still replaces it
        self.assertEqual([r.glob for r in cfg.write_rules].count("**/design.md"), 1)
        self.assertEqual(cfg.write_rules[-1].glob, "src/**")   # defaults come first
        self.assertEqual(cfg.outputs["designer"], ["design.md", "preview.html"])

    def test_rejects_invalid_toml(self):
        root = make_project("mark_schema = [\n")
        with self.assertRaises(ConfigError):
            load_config(root)


if __name__ == "__main__":
    unittest.main()
