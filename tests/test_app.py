"""Menu bar app build, the `mark` launcher, the plugin update, and install.sh."""
import importlib.util
import io
import json
import os
import plistlib
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import tests._support  # noqa: F401 - puts the plugin lib on sys.path

from mark import app, cli

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("mark_launcher", ROOT / "plugins/mark/macos/launcher.py")
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


def done(code=0, out="", err=""):
    return subprocess.CompletedProcess([], code, out, err)


class Base(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="mark-app-"))
        self.addCleanup(shutil.rmtree, self.base, True)
        (self.base / "plugins").mkdir()

    def install(self, version, scope="user", key="mark@marksuits", extra=()):
        path = self.base / "plugins" / "cache" / key.split("@")[1] / "mark" / version
        (path / "bin").mkdir(parents=True, exist_ok=True)
        (path / "bin" / "mark").write_text("")
        (self.base / "plugins" / "installed_plugins.json").write_text(json.dumps({"version": 2, "plugins": {
            "other@x": [{"scope": "user", "version": "9.9.9", "installPath": "/nope"}],
            key: [*extra, {"scope": scope, "version": version, "installPath": str(path)}]}}))
        return path


class LauncherTest(Base):
    def test_runs_the_user_scope_install(self):
        self.assertIsNone(launcher.plugin_root(self.base))
        path = self.install("0.60.0", extra=[{"scope": "project", "version": "0.50.0", "installPath": "/old"}])
        self.assertEqual(launcher.plugin_root(self.base), path)
        self.assertEqual(app.plugin_entry(self.base)[1]["version"], "0.60.0")

    def test_a_missing_bin_is_not_installed(self):
        shutil.rmtree(self.install("0.60.0") / "bin")
        self.assertIsNone(launcher.plugin_root(self.base))

    def test_written_with_this_python(self):
        dest = app.write_launcher(self.base / "bin" / "mark", python="/usr/local/bin/python3.13")
        text = dest.read_text()
        self.assertTrue(text.startswith("#!/usr/local/bin/python3.13\n\"\"\""), text[:60])
        self.assertTrue(os.access(dest, os.X_OK))


class BuildTest(Base):
    def setUp(self):
        super().setUp()
        self.dest = self.base / "Applications" / "Mark.app"
        (self.dest / "Contents").mkdir(parents=True)
        (self.dest / "Contents" / "old").write_text("old")

    def test_no_swiftc(self):
        with mock.patch("shutil.which", return_value=None):
            self.assertEqual(app.build_app("1.0.0", self.dest), (False, "app.no_swiftc"))

    def test_a_failed_build_keeps_the_old_app(self):
        with mock.patch("shutil.which", return_value="/usr/bin/swiftc"):
            ok, error = app.build_app("1.0.0", self.dest, run=lambda *a, **k: done(1, err="boom"))
        self.assertEqual((ok, error), (False, "boom"))
        self.assertTrue((self.dest / "Contents" / "old").exists())

    def test_a_build_swaps_the_app_in(self):
        cmds = []
        def swiftc(cmd, **_):
            cmds.append(cmd)
            if "--iconset" not in cmd:  # swiftc and iconutil both write their -o
                Path(cmd[cmd.index("-o") + 1]).write_text("binary")
            return done()
        with mock.patch("shutil.which", return_value="/usr/bin/swiftc"):
            self.assertEqual(app.build_app("1.2.3", self.dest, launcher=Path("/l/mark"), run=swiftc), (True, ""))
        self.assertFalse((self.dest / "Contents" / "old").exists())
        info = plistlib.loads((self.dest / "Contents" / "Info.plist").read_bytes())
        self.assertEqual((info["CFBundleShortVersionString"], info["MarkCLI"], info["MarkApp"]),
                         ("1.2.3", "/l/mark", str(self.dest / "Contents" / "MacOS" / "Mark")))
        self.assertEqual([p.name for p in self.dest.parent.iterdir()], ["Mark.app"])  # no temp dir left
        self.assertEqual([c[1] for c in cmds[1:]], ["--iconset", "-c"])  # the binary draws the icon, iconutil packs it
        self.assertEqual(info["CFBundleIconFile"], "Mark")
        self.assertTrue((self.dest / "Contents" / "Resources" / "Mark.icns").exists())

    def test_no_icon_still_builds(self):
        def run(cmd, **_):
            if cmd[0] == "/usr/bin/swiftc":
                Path(cmd[cmd.index("-o") + 1]).write_text("binary")
                return done()
            raise FileNotFoundError(cmd[0])
        with mock.patch("shutil.which", return_value="/usr/bin/swiftc"):
            self.assertEqual(app.build_app("1.2.3", self.dest, run=run), (True, ""))
        self.assertTrue((self.dest / "Contents" / "MacOS" / "Mark").exists())


class UpdateTest(Base):
    def setUp(self):
        super().setUp()
        env = {k: v for k, v in os.environ.items() if k != "MARK_NO_UPDATE_CHECK"}
        for p in (mock.patch.dict(os.environ, {**env, "CLAUDE_CONFIG_DIR": str(self.base)}, clear=True),
                  mock.patch("mark.runner.find_claude", return_value="/bin/claude")):
            p.start()
            self.addCleanup(p.stop)
        self.calls = []

    def test_updated(self):
        self.install("0.60.0", key="mark@fork")

        def run(cmd, **_):
            self.calls.append(cmd[1:])
            if cmd[2] == "update":
                self.install("0.61.0", key="mark@fork")
            return done()
        self.assertEqual(app.update(run), ("app.updated", {"old": "0.60.0", "new": "0.61.0"}))
        self.assertEqual(self.calls, [["plugin", "marketplace", "update", "fork"],
                                      ["plugin", "update", "mark@fork", "--scope", "user"]])

    def test_current_failed_and_missing(self):
        self.assertEqual(app.update(lambda *a, **k: done())[0], "app.no_plugin")
        self.install("0.60.0")
        self.assertEqual(app.update(lambda *a, **k: done())[0], "app.current")
        self.assertEqual(app.update(lambda *a, **k: done(1, err="offline")), ("app.update_failed", {"error": "offline"}))
        with mock.patch("mark.runner.find_claude", return_value=None):
            self.assertEqual(app.update()[0], "app.no_claude")
        with mock.patch.dict(os.environ, {"MARK_NO_UPDATE_CHECK": "1"}):
            self.assertEqual(app.update()[0], "app.update_off")


class CliTest(unittest.TestCase):
    def test_usage(self):
        for args in (["app"], ["app", "build"], ["app", "install", "--bad"]):
            self.assertEqual(cli.main(args, out=io.StringIO(), err=io.StringIO()), 2, args)

    def test_scripts_parse(self):
        for name in ("install.sh", "uninstall.sh"):
            self.assertEqual(subprocess.run(["bash", "-n", str(ROOT / name)]).returncode, 0, name)

    def test_uninstall_knows_the_launcher(self):
        # uninstall.sh deletes ~/.local/bin/mark only when it is ours
        self.assertIn("Mark plugin", (ROOT / "plugins/mark/macos/launcher.py").read_text())


if __name__ == "__main__":
    unittest.main()
