"""Update notice: published version vs installed plugin, checked at most once a day."""
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import tests._support  # noqa: F401 - puts the plugin lib on sys.path

from mark import updates


class NewerTest(unittest.TestCase):
    def setUp(self):
        base = Path(tempfile.mkdtemp(prefix="mark-upd-"))
        self.addCleanup(shutil.rmtree, base, True)
        self.plugins = base / "plugins"
        self.plugin = self.plugins / "cache" / "marksuits" / "mark" / "0.15.0"
        (self.plugin / ".claude-plugin").mkdir(parents=True)
        (self.plugin / ".claude-plugin" / "plugin.json").write_text('{"version": "0.15.0"}')
        (self.plugins / "known_marketplaces.json").write_text(json.dumps(
            {"marksuits": {"source": {"source": "git", "url": "https://github.com/o/MarkSuits.git"}}}))
        self.urls = []
        env = {k: v for k, v in os.environ.items() if k not in ("MARK_NO_UPDATE_CHECK", "CLAUDE_PLUGIN_DATA")}
        patcher = mock.patch.dict(os.environ, env, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def check(self, published, now=1000.0):
        def fetch(url):
            self.urls.append(url)
            return published
        return updates.newer(self.plugin, fetch=fetch, now=now)

    def test_newer_version_is_reported_and_cached_for_a_day(self):
        self.assertEqual(self.check("0.16.0"), ("marksuits", "0.16.0"))
        self.assertEqual(self.urls, ["https://raw.githubusercontent.com/o/MarkSuits/HEAD/plugins/mark/.claude-plugin/plugin.json"])
        self.assertTrue((self.plugins / "data" / "mark-marksuits" / "update-check.json").is_file())
        self.assertEqual(self.check("0.17.0", now=2000.0), ("marksuits", "0.16.0"))
        self.assertEqual(len(self.urls), 1)
        self.assertEqual(self.check("0.17.0", now=1000.0 + updates.CHECK_EVERY), ("marksuits", "0.17.0"))

    def test_same_or_unreachable_says_nothing(self):
        self.assertIsNone(self.check("0.15.0"))

        def offline(url):
            raise OSError("offline")
        self.assertIsNone(updates.newer(self.plugin, fetch=offline, now=1000.0 + updates.CHECK_EVERY))

    def test_local_checkout_and_opt_out_skip_the_check(self):
        self.assertIsNone(updates.newer(Path(updates.__file__).resolve().parents[2], fetch=self.fail))
        os.environ["MARK_NO_UPDATE_CHECK"] = "1"
        self.assertIsNone(self.check("9.0.0"))
        self.assertEqual(self.urls, [])
