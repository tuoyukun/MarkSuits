import os
import subprocess
import sys
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from tests._support import PLUGIN_ROOT, make_project

from mark import tickets
from mark.config import load_config


def write_ticket(root: Path, kind_dir: str, ticket_id: str, text: str) -> Path:
    d = root / ".mark" / kind_dir / ticket_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "status.md").write_text(text, encoding="utf-8")
    return d


STATUS_OK = "---\nstatus: developing\nowner: coder-impl\nupdated: 2026-01-02\nupdater: orchestrator\ndesc: Add login\n---\n\nWaiting on CI.\n"


class StatusFormatTest(unittest.TestCase):
    def test_parse_fields_and_note(self):
        fields, note = tickets.parse_status(STATUS_OK)
        self.assertEqual(fields["status"], "developing")
        self.assertEqual(fields["desc"], "Add login")
        self.assertEqual(note, "Waiting on CI.")

    def test_hyphenated_keys_are_kept(self):
        fields, _ = tickets.parse_status("---\nstatus: testing\nmerge-after: [0012, b0003]\n---\n")
        self.assertEqual(fields["merge-after"], "[0012, b0003]")

    def test_missing_frontmatter(self):
        self.assertEqual(tickets.parse_status("just text"), ({}, "just text"))

    def test_format_roundtrip_and_order(self):
        fields = {"leftover": "0", "desc": "d", "status": "passed", "x-extra": "1"}
        text = tickets.format_status(fields, "note")
        self.assertTrue(text.startswith("---\nstatus: passed\ndesc: d\nleftover: 0\nx-extra: 1\n---"))
        self.assertEqual(tickets.parse_status(text), (fields, "note"))

    def test_parse_merge_after(self):
        self.assertEqual(tickets.parse_merge_after("[0012, b0003]"), ["0012", "b0003"])
        self.assertEqual(tickets.parse_merge_after("[]"), [])
        self.assertIsNone(tickets.parse_merge_after("0012"))
        self.assertIsNone(tickets.parse_merge_after("[12]"))


class CheckTest(unittest.TestCase):
    def setUp(self):
        self.root = make_project()
        self.cfg = load_config(self.root)

    def keys(self):
        return [p.key for p in tickets.check(self.cfg)]

    def test_clean_ticket(self):
        write_ticket(self.root, "features", "0001-login", STATUS_OK)
        self.assertEqual(self.keys(), [])

    def test_missing_status_file(self):
        (self.root / ".mark" / "features" / "0001-login").mkdir(parents=True)
        self.assertEqual(self.keys(), ["check.missing"])

    def test_claim_marker_dir_is_not_a_ticket(self):
        (self.root / ".mark" / "features" / ".numbers").mkdir(parents=True)
        self.assertEqual(self.keys(), [])

    def test_status_must_fit_kind(self):
        write_ticket(self.root, "bugs", "b0001-crash", STATUS_OK.replace("developing", "review-design"))
        self.assertEqual(self.keys(), ["check.bad_status"])

    def test_length_limits(self):
        long_desc = STATUS_OK.replace("Add login", "x" * 201).replace("Waiting on CI.", "y" * 241)
        write_ticket(self.root, "features", "0001-login", long_desc)
        self.assertEqual(sorted(self.keys()), ["check.desc_long", "check.note_long"])

    def test_leftover_required_from_pending_merge(self):
        write_ticket(self.root, "features", "0001-a", STATUS_OK.replace("developing", "pending-merge"))
        write_ticket(self.root, "features", "0002-b",
                     STATUS_OK.replace("developing", "passed").replace("desc:", "leftover: two\ndesc:"))
        self.assertEqual(sorted(self.keys()), ["check.bad_leftover", "check.no_leftover"])

    def test_bad_merge_after(self):
        write_ticket(self.root, "features", "0001-a", STATUS_OK.replace("desc:", "merge-after: 12\ndesc:"))
        self.assertEqual(self.keys(), ["check.bad_merge_after"])

    def test_all_tickets_sorted_newest_first(self):
        write_ticket(self.root, "features", "0001-old", STATUS_OK)
        write_ticket(self.root, "bugs", "b0001-new", STATUS_OK.replace("2026-01-02", "2026-02-01"))
        self.assertEqual([t.id for t in tickets.all_tickets(self.cfg)], ["b0001-new", "0001-old"])


class ClaimTest(unittest.TestCase):
    def setUp(self):
        self.root = make_project()
        self.cfg = load_config(self.root)

    def test_first_feature_and_bug(self):
        f = tickets.claim(self.cfg, "feature", "Add Login page!", today="2026-03-01")
        b = tickets.claim(self.cfg, "bug", "Crash on save")
        self.assertEqual(f.id, "0001-add-login-page")
        self.assertEqual(b.id, "b0001-crash-on-save")
        fields, _ = tickets.parse_status(f.path.read_text(encoding="utf-8"))
        self.assertEqual(fields, {"status": "designing", "owner": "designer", "updated": "2026-03-01",
                                  "updater": "orchestrator", "desc": "Add Login page!"})
        self.assertEqual(tickets.load_ticket(self.cfg, "bug", b.id).get("owner"), "fix-plan")

    def test_numbers_continue_after_existing_dirs_and_markers(self):
        (self.root / ".mark" / "features" / "0007-old").mkdir(parents=True)
        numbers = self.root / ".mark" / "features" / ".numbers"
        numbers.mkdir()
        (numbers / "0009").write_text("{}")
        self.assertEqual(tickets.claim(self.cfg, "feature", "next one").id, "0010-next-one")

    def test_non_ascii_description_needs_slug_or_gets_timestamp(self):
        t = tickets.claim(self.cfg, "feature", "登录页", slug="login")
        self.assertEqual(t.id, "0001-login")
        t2 = tickets.claim(self.cfg, "feature", "注册页")
        self.assertRegex(t2.id, r"^0002-\d{8}-\d{6}$")

    def test_description_too_long_claims_nothing(self):
        with self.assertRaises(tickets.ClaimError):
            tickets.claim(self.cfg, "feature", "x" * 201)
        self.assertEqual(tickets.used_numbers(self.cfg, "feature"), set())

    def test_failure_after_reservation_releases_number(self):
        orig = tickets.format_status
        tickets.format_status = lambda *a, **k: (_ for _ in ()).throw(OSError("disk full"))
        try:
            with self.assertRaises(OSError):
                tickets.claim(self.cfg, "feature", "boom")
        finally:
            tickets.format_status = orig
        markers = self.root / ".mark" / "features" / ".numbers"
        self.assertEqual(list(markers.iterdir()), [])

    def test_concurrent_claims_get_unique_numbers(self):
        with ThreadPoolExecutor(max_workers=16) as pool:
            ids = list(pool.map(lambda i: tickets.claim(self.cfg, "feature", f"task {i}").id, range(40)))
        numbers = [tickets.ticket_number("feature", i) for i in ids]
        self.assertEqual(sorted(numbers), list(range(1, 41)))

    def test_concurrent_processes_get_unique_numbers(self):
        mark = str(PLUGIN_ROOT / "bin" / "mark")
        procs = [subprocess.Popen([sys.executable, mark, "claim", "bug", f"same text {i % 2}"],
                                  cwd=self.root, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
                 for i in range(12)]
        ids = [p.communicate()[0].strip().removeprefix("TICKET-ID: ") for p in procs]
        self.assertTrue(all(p.returncode == 0 for p in procs))
        numbers = [tickets.ticket_number("bug", i) for i in ids]
        self.assertEqual(sorted(numbers), list(range(1, 13)))


def git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", "-c", "user.email=t@example.com", "-c", "user.name=t", *args],
                   cwd=cwd, check=True, capture_output=True)


class MainRootTest(unittest.TestCase):
    def test_worktree_resolves_to_main_checkout(self):
        root = make_project()
        git(root, "init", "-q", "-b", "main")
        git(root, "add", ".")
        git(root, "commit", "-q", "-m", "init")
        wt = root / ".claude" / "worktrees" / "feature-x"
        git(root, "worktree", "add", "-q", "-b", "feature/x", str(wt))
        self.assertEqual(tickets.main_root(wt), root.resolve())

        env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
        out = subprocess.run([sys.executable, str(PLUGIN_ROOT / "bin" / "mark"), "claim", "feature", "from worktree"],
                             cwd=wt, capture_output=True, text=True, env=env)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertTrue((root / ".mark" / "features" / "0001-from-worktree" / "status.md").is_file())
        self.assertFalse((wt / ".mark" / "features").exists())

    def test_outside_git_returns_root(self):
        root = make_project()
        self.assertEqual(tickets.main_root(root), root)


if __name__ == "__main__":
    unittest.main()
