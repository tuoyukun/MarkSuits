"""Black-box rules for the end-to-end test directory (`[paths] tests`).

The tester proves behaviour by driving the app the way a user does. Two kinds of check:

- every file under the test directory: added lines may not import production code or read
  its source (white-box tests belong to the modules' own selftest.sh);
- `[tests] profile = "playwright"` spec files: each new or changed `test(...)` block performs
  a user action and asserts after it, is not skipped, does not sleep, and does not stub the
  network or reach into the page's internals.

Only what a write adds is judged: existing files are not held to rules they predate.
Pure functions; `guards.write.e2e_guard` applies them.
"""
from __future__ import annotations

import posixpath
import re
from dataclasses import dataclass

PROFILES = ("none", "playwright")

_SPEC = re.compile(r"\.(spec|test)\.[cm]?[jt]sx?$")
# A specifier in an import / require / dynamic import / `from x import`.
_IMPORT = re.compile(r"""(?:\bfrom\s+|\bimport\s*\(?\s*|\brequire\s*\(\s*)['"]([^'"]+)['"]""")
_PY_IMPORT = re.compile(r"^\s*(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))")
_READ_SOURCE = re.compile(r"\b(readFileSync|readFile|createReadStream|read_text|open)\s*\(|\bgrep\b")
_PATH_TOKEN = re.compile(r"(?<![\w/.-])([\w.-]*/[\w./-]+)")

_TEST_START = re.compile(r"(?m)^[ \t]*test(?:\.(only|skip|fixme|fail|slow))?\s*\(")
_RUNTIME_SKIP = re.compile(r"\btest\.(skip|fixme)\s*\(")
_ACTION = re.compile(
    r"\.(click|dblclick|fill|type|press|pressSequentially|check|uncheck|selectOption|setChecked|"
    r"setInputFiles|dragTo|hover|tap|clear|selectText)\s*\(|\.(keyboard|mouse|touchscreen)\.\w+\s*\(")
_EXPECT = re.compile(r"\bexpect(?:\.\w+)?\s*\(")
_SLEEP = re.compile(r"\bwaitForTimeout\s*\(\s*(\d+)")
_STUB = re.compile(r"\b(?:page|context)\.route(?:FromHAR)?\s*\(|\.fulfill\s*\(|\.dispatchEvent\s*\(")
_POKE = re.compile(r"\.evaluate(?:Handle)?\s*\([^;]*?(?:window\.\w+\s*=[^=]|\.dispatch\s*\(|setState\s*\()",
                   re.S)
SLEEP_MAX_MS = 200
_FUNC_DEF = re.compile(r"(?:\bfunction\s+(\w+)\s*\(|\b(?:const|let)\s+(\w+)\s*=\s*(?:async\s*)?(?:\(|\w+\s*=>))")
_LOCAL_IMPORT = re.compile(r"""\bfrom\s+['"](\.[^'"]+)['"]""")
_ASSERT_NAME = re.compile(r"(?:expect|assert|verify|should)\w*$", re.I)


@dataclass(frozen=True)
class Problem:
    key: str        # i18n key under "e2e."
    where: str      # test title or the offending line


def added_lines(old: str | None, new: str) -> list[str]:
    """Lines of `new` that `old` does not have (all of them for a new file)."""
    have = set((old or "").splitlines())
    return [ln for ln in new.splitlines() if ln not in have]


def _escapes(tests_dir: str, rel_file: str, spec: str) -> str | None:
    """Repo path a relative specifier points at, when it leaves the test directory."""
    if not spec.startswith("."):
        return None
    target = posixpath.normpath(posixpath.join(posixpath.dirname(rel_file), spec))
    inside = target == tests_dir or target.startswith(tests_dir + "/")
    return None if inside else target


def source_problems(rel_file: str, old: str | None, new: str, tests_dir: str,
                    module_dirs: list[str]) -> list[Problem]:
    """Added lines that import production code or read its source."""
    out: list[Problem] = []
    modules = [d for d in module_dirs if d]
    python = rel_file.endswith(".py")
    for line in added_lines(old, new):
        text = line.strip()
        specs = [] if python else _IMPORT.findall(line)
        py = _PY_IMPORT.match(line) if python else None
        if py:
            specs.append((py.group(1) or py.group(2)).replace(".", "/"))
        for spec in specs:
            if _escapes(tests_dir, rel_file, spec) or any(spec == d or spec.startswith(d + "/") for d in modules):
                out.append(Problem("e2e.import", text))
                break
        else:
            if _READ_SOURCE.search(line):
                for lit in _PATH_TOKEN.findall(line):
                    target = _escapes(tests_dir, rel_file, lit) or lit
                    if any(target == d or target.startswith(d + "/") for d in modules):
                        out.append(Problem("e2e.read_source", text))
                        break
    return out


def _strip(text: str) -> str:
    """Blank out comments and string contents, keeping offsets, so braces and calls in them
    do not count."""
    out, i, n = list(text), 0, len(text)
    while i < n:
        c = text[i]
        if text.startswith("//", i) or text.startswith("/*", i):
            end = text.find("\n" if text[i + 1] == "/" else "*/", i + 2)
            end = n if end < 0 else end + (0 if text[i + 1] == "/" else 2)
            for k in range(i, end):
                if out[k] != "\n":
                    out[k] = " "
            i = end
        elif c in "'\"`":
            k = i + 1
            while k < n and text[k] != c:
                k += 2 if text[k] == "\\" else 1
            for j in range(i + 1, min(k, n)):
                if out[j] != "\n":
                    out[j] = " "
            i = k + 1
        else:
            i += 1
    return "".join(out)


@dataclass(frozen=True)
class Block:
    title: str
    modifier: str       # "" or only / skip / fixme / ...
    body: str           # source text of the whole call, comments and strings kept
    code: str           # the same span with comments and string contents blanked


def extract_tests(text: str) -> list[Block]:
    """Top-level `test(...)` calls (not test.describe / test.beforeEach)."""
    code = _strip(text)
    blocks: list[Block] = []
    for m in _TEST_START.finditer(code):
        start = m.start()
        title_m = re.match(r"\s*(['\"`])(.*?)\1", text[m.end():], re.S)
        title = title_m.group(2) if title_m else ""
        depth, end = 0, None
        for k in range(m.end() - 1, len(code)):     # from the opening parenthesis
            ch = code[k]
            if ch in "({[":
                depth += 1
            elif ch in ")}]":
                depth -= 1
                if depth == 0:
                    end = k + 1
                    break
        end = end or len(code)
        blocks.append(Block(title, m.group(1) or "", text[start:end], code[start:end]))
    return blocks


def _brace_span(code: str, start: int) -> str:
    """From the first `{` at or after `start` to its match; "" when there is none."""
    open_at = code.find("{", start)
    if open_at < 0:
        return ""
    depth = 0
    for k in range(open_at, len(code)):
        depth += {"{": 1, "}": -1}.get(code[k], 0)
        if depth == 0:
            return code[open_at:k + 1]
    return code[open_at:]


def local_imports(text: str) -> list[str]:
    """Relative specifiers a spec imports; the guard reads them to find helpers."""
    return _LOCAL_IMPORT.findall(text)


def helpers(sources: list[str], probe: re.Pattern) -> set[str]:
    """Functions whose body does what `probe` finds, directly or through another such
    function (two rounds cover a helper calling a helper). Calling one counts as doing it."""
    defs = []
    for src in sources:
        code = _strip(src)
        for m in _FUNC_DEF.finditer(code):
            start = m.end()
            if code[start - 1] == "(":          # skip the parameters: TS types have braces too
                depth = 0
                for k in range(start - 1, len(code)):
                    depth += {"(": 1, ")": -1}.get(code[k], 0)
                    if depth == 0:
                        start = k + 1
                        break
            defs.append((m.group(1) or m.group(2), _brace_span(code, start)))
    names: set[str] = set()
    for _ in range(2):
        for name, body in defs:
            if probe.search(body) or any(re.search(rf"\b{re.escape(n)}\s*\(", body) for n in names):
                names.add(name)
    return names


def _calls(code: str, names: set[str]) -> list[int]:
    return [m.start() for n in names for m in re.finditer(rf"(?<![\w.]){re.escape(n)}\s*\(", code)]


def spec_problems(old: str | None, new: str, imported: list[str] = ()) -> list[Problem]:
    """Playwright rules for the test blocks a write adds or changes. `imported`: the source
    of the files the spec imports locally, where its helpers live."""
    before = {b.title: b.body for b in extract_tests(old or "")}
    ops = helpers([new, *imported], _ACTION)
    checks = helpers([new, *imported], _EXPECT)
    out: list[Problem] = []
    for b in extract_tests(new):
        if before.get(b.title) == b.body:
            continue
        where = b.title or b.body.splitlines()[0].strip()
        if b.modifier in ("skip", "fixme") or _RUNTIME_SKIP.search(b.code):
            out.append(Problem("e2e.skipped", where))
        acts = [m.start() for m in _ACTION.finditer(b.code)] + _calls(b.code, ops)
        asserts = [m.start() for m in _EXPECT.finditer(b.code)] + _calls(b.code, checks)
        asserts += [m.start() for m in re.finditer(r"(?<![\w.])(\w+)\s*\(", b.code) if _ASSERT_NAME.match(m.group(1))]
        if not acts:
            out.append(Problem("e2e.no_action", where))
        elif not any(a > min(acts) for a in asserts):
            out.append(Problem("e2e.no_assert_after", where))
        if any(int(ms) > SLEEP_MAX_MS for ms in _SLEEP.findall(b.code)):
            out.append(Problem("e2e.sleep", where))
        if _STUB.search(b.code):
            out.append(Problem("e2e.stub", where))
        if _POKE.search(b.code):
            out.append(Problem("e2e.poke", where))
    return out


def problems(rel_file: str, old: str | None, new: str, tests_dir: str, module_dirs: list[str],
             profile: str, imported: list[str] = ()) -> list[Problem]:
    found = source_problems(rel_file, old, new, tests_dir, module_dirs)
    if profile == "playwright" and _SPEC.search(rel_file):
        found += spec_problems(old, new, imported)
    return found


# --------------------------------------------------------------------------
# Journey reuse: extend an existing end-to-end test before adding a new one.
#
# The plan (tech-plan.md / fix-plan.md) decides, per acceptance criterion, which existing test
# gets more steps or which new journey is added and why no existing one could be extended; the
# human reviews that with the plan. The tester may add only the tests the plan names as new.
# `<tests>/JOURNEYS.md` lists every test so the planner can see what already exists.
# --------------------------------------------------------------------------

PLAN_ANCHOR = "<!-- mark:e2e-plan -->"
INDEX_ANCHOR = "<!-- mark:journeys -->"
INDEX_FILE = "JOURNEYS.md"
PLAN_FILES = ("tech-plan.md", "fix-plan.md")


def table_rows(text: str, anchor: str) -> list[list[str]]:
    """Cells of the Markdown table that follows `anchor` (header and separator dropped)."""
    at = text.find(anchor)
    if at < 0:
        return []
    rows: list[list[str]] = []
    started = False
    for line in text[at + len(anchor):].splitlines():
        line = line.strip()
        if not line.startswith("|"):
            if started:
                break
            continue
        started = True
        cells = [c.strip().strip("`").strip() for c in line.strip("|").split("|")]
        if all(set(c) <= set("-: ") for c in cells):
            continue
        rows.append(cells)
    return rows[1:]                                   # first row is the header


def planned_new(plan: str) -> set[str]:
    """Titles of the tests the plan adds (`| AC-N | new | <title> | ... |`)."""
    return {r[2] for r in table_rows(plan, PLAN_ANCHOR) if len(r) > 2 and r[1].lower() == "new" and r[2]}


def indexed(index: str) -> set[str]:
    """Test titles listed in JOURNEYS.md (first column)."""
    return {r[0] for r in table_rows(index, INDEX_ANCHOR) if r and r[0]}


def suite(root, tests_dir: str, skip: str | None = None) -> dict[str, str]:
    """{test title: file} for every spec under `root/tests_dir`, except the file `skip`."""
    out: dict[str, str] = {}
    base = root / tests_dir
    if not base.is_dir():
        return out
    for path in sorted(base.rglob("*")):
        rel = path.relative_to(root).as_posix()
        if "node_modules" in path.parts or not path.is_file() or not _SPEC.search(path.name) or rel == skip:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for b in extract_tests(text):
            out.setdefault(b.title, rel)
    return out


def added_tests(old: str | None, new: str, elsewhere: set[str]) -> list[str]:
    """Titles a write adds that no other spec has (moving a test between files is not adding)."""
    before = {b.title for b in extract_tests(old or "")}
    return [b.title for b in extract_tests(new) if b.title not in before and b.title not in elsewhere]


_COVERS = re.compile(r"covers:\s*([^\n*]+?)\s*(?:\*/|$)", re.M)


def index_drift(root, tests_dir: str) -> tuple[list[str], list[str]]:
    """(rows to add, rows to drop) that would make JOURNEYS.md match the suite under `root`.
    New rows carry the file and the `covers:` the test declares; the path is left to write."""
    tests = suite(root, tests_dir)
    path = root / tests_dir / INDEX_FILE
    listed = indexed(path.read_text(encoding="utf-8")) if path.is_file() else set()
    add = []
    for title in sorted(set(tests) - listed):
        rel = tests[title]
        text = (root / rel).read_text(encoding="utf-8", errors="replace")
        body = next((b.body for b in extract_tests(text) if b.title == title), "")
        covers = ", ".join(m.strip() for m in _COVERS.findall(body)) or "-"
        add.append(f"| {title} | {rel[len(tests_dir) + 1:]} | TODO: entry → steps → outcome | {covers} |")
    return add, sorted(listed - set(tests))
