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

    def test_rejects_invalid_toml(self):
        root = make_project("mark_schema = [\n")
        with self.assertRaises(ConfigError):
            load_config(root)


if __name__ == "__main__":
    unittest.main()
