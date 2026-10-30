"""Black-box rules for the end-to-end test directory (`[paths] tests`).

The tester proves behaviour by driving the app the way a user does. Two kinds of check:

- every file under the test directory: added lines may not import production code or read
  its source (white-box tests belong to the modules' own selftest.sh);
- `[tests] profile = "playwright"` spec files: each new or changed `test(...)` block performs
  a user action and asserts after it, is not skipped, does not sleep, and does not stub the
  network or reach into the page's internals;
- `[tests] profile = "maestro"` flow files (`*.yaml`, outside `subflows/`): each new or changed
  flow performs a user action and asserts after it (a `runFlow` of a subflow counts as what
  the subflow does), and no path in it leaves the test directory.

Only what a write adds is judged: existing files are not held to rules they predate.
Pure functions; `guards.write.e2e_guard` applies them.
"""
from __future__ import annotations

import posixpath
import re
from dataclasses import dataclass

PROFILES = ("none", "playwright", "maestro")

_SPEC = re.compile(r"\.(spec|test)\.[cm]?[jt]sx?$")
_CODE = re.compile(r"\.(?:[cm]?[jt]sx?|py|ya?ml|sh)$")


def is_code(rel_file: str) -> bool:
    """A test file whose content the write rules judge (not a log or a report)."""
    return bool(_CODE.search(rel_file))

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
        if _YAML.search(rel_file):
            specs = _PATH_TOKEN.findall(line) if _YAML_PATH_KEY.match(line) else []
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


# Maestro: one flow file is one test. Config header (appId, name, tags...) above `---`,
# commands below as a YAML list. Files under a `subflows/` directory are helpers that flows
# reach through `runFlow`; `config.yaml` is the workspace config.
_YAML = re.compile(r"\.ya?ml$")
_STEP = re.compile(r"^\s*-\s*(\w+)\b", re.M)
_YAML_PATH_KEY = re.compile(r"^\s*(?:-\s*)?(?:runFlow|runScript|file)\s*:")
_FLOW_REF = re.compile(r"""^\s*(?:-\s*)?(?:runFlow|file)\s*:\s*['"]?([^'"\s#]+\.ya?ml)""", re.M)
MAESTRO_ACTIONS = frozenset({
    "tapOn", "doubleTapOn", "longPressOn", "inputText", "inputRandomText", "inputRandomNumber",
    "inputRandomEmail", "inputRandomPersonName", "eraseText", "swipe", "scroll",
    "scrollUntilVisible", "pressKey", "back", "copyTextFrom", "pasteText"})
MAESTRO_ASSERTS = frozenset({"assertVisible", "assertNotVisible", "assertTrue", "assertWithAI",
                             "assertNoDefectsWithAI"})


def is_flow(rel_file: str) -> bool:
    """A Maestro flow that counts as a test (not a subflow, not the workspace config)."""
    parts = rel_file.split("/")
    return bool(_YAML.search(rel_file)) and parts[-1] not in ("config.yaml", "config.yml") \
        and "subflows" not in parts[:-1]


def _split_flow(text: str) -> tuple[str, str]:
    """(config header, commands); a file without `---` is all commands."""
    m = re.search(r"(?m)^---\s*$", text)
    return (text[:m.start()], text[m.end():]) if m else ("", text)


def flow_title(rel_file: str, text: str) -> str:
    """The flow's `name:`, else its file name without the extension."""
    m = re.search(r"(?m)^name\s*:\s*(.+?)\s*$", _split_flow(text)[0])
    if m:
        return m.group(1).strip("'\"")
    return _YAML.sub("", posixpath.basename(rel_file))


def flow_refs(rel_file: str, text: str) -> list[str]:
    """Repo paths of the flows this one runs (`runFlow: x.yaml`, `file: x.yaml`), resolved
    against its own directory as Maestro does."""
    return [_resolve(rel_file, r) for r in _FLOW_REF.findall(text)]


def _resolve(rel_file: str, ref: str) -> str:
    return posixpath.normpath(posixpath.join(posixpath.dirname(rel_file), ref))


def _flow_steps(rel_file: str, text: str, flows: dict[str, str], seen: frozenset = frozenset()) -> list[str]:
    """Kinds of the commands in order ("act", "assert" or ""), a `runFlow` standing for what
    the flow it runs does first and last."""
    out = []
    lines = _split_flow(text)[1].splitlines()
    for i, line in enumerate(lines):
        m = _STEP.match(line)
        if not m:
            ref = _FLOW_REF.match(line)                 # `file:` under a block-style runFlow
            name = "runFlow" if ref else ""
        else:
            name, ref = m.group(1), _FLOW_REF.match(line)
            if _optional(lines, i):                     # may not happen, so proves nothing
                continue
        if name in MAESTRO_ACTIONS:
            out.append("act")
        elif name in MAESTRO_ASSERTS:
            out.append("assert")
        elif ref:
            target = _resolve(rel_file, ref.group(1))
            if target in flows and target not in seen:
                out += _flow_steps(target, flows[target], flows, seen | {rel_file})
    return out


_OPTIONAL = re.compile(r"\boptional\s*:\s*true\b")


def _optional(lines: list[str], i: int) -> bool:
    """The step starting at lines[i] has `optional: true` (inline, or in its own block)."""
    if _OPTIONAL.search(lines[i]):
        return True
    dash = len(lines[i]) - len(lines[i].lstrip())
    for line in lines[i + 1:]:
        if line.strip() and len(line) - len(line.lstrip()) <= dash:
            return False
        if re.match(r"^\s*optional\s*:\s*true\b", line) \
                and len(line) - len(line.lstrip()) <= dash + 4:   # the step's own key, not a nested one
            return True
    return False


def flow_problems(rel_file: str, old: str | None, new: str, flows: dict[str, str]) -> list[Problem]:
    """Maestro rules for a flow a write adds or changes. `flows`: {repo path: text} of the
    flows it runs, directly or further down."""
    if not is_flow(rel_file) or old == new:
        return []
    where = flow_title(rel_file, new)
    steps = _flow_steps(rel_file, new, flows)
    if "act" not in steps:
        return [Problem("e2e.no_action", where)]
    if "assert" not in steps[steps.index("act") + 1:]:
        return [Problem("e2e.no_assert_after", where)]
    return []


def problems(rel_file: str, old: str | None, new: str, tests_dir: str, module_dirs: list[str],
             profile: str, imported: list[str] | dict[str, str] = ()) -> list[Problem]:
    """`imported`: playwright, the source of the files the spec imports; maestro, the flows it
    runs ({repo path: text})."""
    found = source_problems(rel_file, old, new, tests_dir, module_dirs)
    if profile == "playwright" and _SPEC.search(rel_file):
        found += spec_problems(old, new, list(imported))
    elif profile == "maestro":
        found += flow_problems(rel_file, old, new, dict(imported) if isinstance(imported, dict) else {})
    return found


def holds_tests(rel_file: str, profile: str) -> bool:
    return bool(_SPEC.search(rel_file)) if profile == "playwright" else profile == "maestro" and is_flow(rel_file)


def tests_in(rel_file: str, text: str, profile: str) -> list[Block]:
    """The tests a file holds under `profile`: playwright `test(...)` blocks in a spec, or the
    one Maestro flow; none for any other file."""
    if not holds_tests(rel_file, profile):
        return []
    if profile == "playwright":
        return extract_tests(text)
    return [Block(flow_title(rel_file, text), "", text, text)]


# --------------------------------------------------------------------------
# Layout and coverage.
#
# `[paths] tests` is the suite root:
#
#   <tests>/regression/         the few core journeys `mark merge` runs; shared, extendable
#   <tests>/tickets/<ticket>/   this ticket's acceptance tests: one per AC, frozen on merge
#   <tests>/regression/JOURNEYS.md
#
# The plan does not name tests: the tester derives one acceptance test per criterion and
# decides whether the ticket adds a regression journey or extends one. The pre-write guard
# keeps writes in the right directory; merge re-checks the layout, the AC coverage and the
# regression index, since shell writes can bypass the guard.
# --------------------------------------------------------------------------

REGRESSION_DIR = "regression"
TICKETS_DIR = "tickets"
INDEX_ANCHOR = "<!-- mark:journeys -->"
INDEX_FILE = "JOURNEYS.md"
AC_ANCHOR = "<!-- mark:ac -->"


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


def indexed(index: str) -> set[str]:
    """Test titles listed in JOURNEYS.md (first column)."""
    return {r[0] for r in table_rows(index, INDEX_ANCHOR) if r and r[0]}


def suite(root, tests_dir: str, profile: str, skip: str | None = None,
          sub: str | None = None) -> dict[str, str]:
    """{test title: file} for every test file under `root/tests_dir[/sub]`, except `skip`."""
    out: dict[str, str] = {}
    base = root / tests_dir / sub if sub else root / tests_dir
    if not base.is_dir():
        return out
    for path in sorted(base.rglob("*")):
        rel = path.relative_to(root).as_posix()
        if "node_modules" in path.parts or not path.is_file() or rel == skip or not holds_tests(rel, profile):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for b in tests_in(rel, text, profile):
            out.setdefault(b.title, rel)
    return out


def in_layout(rel_file: str, tests_dir: str) -> bool:
    """A test file under `<tests>/regression/` or `<tests>/tickets/<id>/`."""
    parts = rel_file[len(tests_dir) + 1:].split("/")
    return parts[0] == REGRESSION_DIR or (parts[0] == TICKETS_DIR and len(parts) >= 3)


def ticket_layout(rel_file: str, tests_dir: str, ticket_id: str) -> bool:
    """A test file this ticket may add: regression, or its own acceptance directory."""
    parts = rel_file[len(tests_dir) + 1:].split("/")
    return parts[0] == REGRESSION_DIR or (parts[0] == TICKETS_DIR and len(parts) >= 3
                                          and parts[1] == ticket_id)


def unlaid_tests(root, tests_dir: str, profile: str) -> list[str]:
    """Test files outside the two directories the layout allows."""
    base = root / tests_dir
    out = []
    for path in sorted(base.rglob("*")) if base.is_dir() else []:
        rel = path.relative_to(root).as_posix()
        if "node_modules" not in path.parts and path.is_file() and holds_tests(rel, profile) \
                and not in_layout(rel, tests_dir):
            out.append(rel)
    return out


_AC_LINE = re.compile(r"(?m)^\s*-\s*(AC-\d+)\b(.*)$")
_COVER = re.compile(r"\b([A-Za-z0-9-]+)/(AC-\d+)\b")
_COVERS = re.compile(r"covers:\s*([^\n*]+?)\s*(?:\*/|$)", re.M)


def criteria(text: str) -> dict[str, bool]:
    """{AC-N: tagged [unit]} under `<!-- mark:ac -->` (requirement.md or fix-plan.md)."""
    at = text.find(AC_ANCHOR)
    if at < 0:
        return {}
    section = re.split(r"(?m)^#{1,6} ", text[at + len(AC_ANCHOR):], maxsplit=1)[0]
    return {m.group(1): "[unit]" in m.group(2).lower() for m in _AC_LINE.finditer(section)}


def acceptance_tests(root, tests_dir: str, ticket_id: str, profile: str) -> dict[str, tuple[str, str]]:
    """{test title: (file, body)} in this ticket's acceptance directory."""
    out: dict[str, tuple[str, str]] = {}
    base = root / tests_dir / TICKETS_DIR / ticket_id
    if not base.is_dir():
        return out
    for path in sorted(base.rglob("*")):
        rel = path.relative_to(root).as_posix()
        if "node_modules" in path.parts or not path.is_file() or not holds_tests(rel, profile):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for b in tests_in(rel, text, profile):
            out.setdefault(b.title, (rel, b.body))
    return out


def coverage_problems(plan_text: str, tests: dict[str, tuple[str, str]], ref: str) -> list[Problem]:
    """Strict one test per criterion: every non-unit AC has exactly one acceptance test, and
    each test declares exactly one of this ticket's criteria in its `covers:`."""
    acs = criteria(plan_text)
    if not acs:
        return []
    by_ac: dict[str, list[str]] = {ac: [] for ac in acs}
    out: list[Problem] = []
    for title, (_, body) in sorted(tests.items()):
        own = sorted({ac for ticket, ac in _COVER.findall(body) if ticket == ref and ac in acs})
        if len(own) != 1:
            out.append(Problem("e2e.ac_not_one", title))
        for ac in own:
            by_ac[ac].append(title)
    for ac, unit in acs.items():
        if unit:
            continue
        if not by_ac[ac]:
            out.append(Problem("e2e.ac_uncovered", ac))
        elif len(by_ac[ac]) > 1:
            out.append(Problem("e2e.ac_shared", ac))
    return out


def index_path(tests_dir: str) -> str:
    return f"{tests_dir}/{REGRESSION_DIR}/{INDEX_FILE}"


def index_drift(root, tests_dir: str, profile: str) -> tuple[list[str], list[str]]:
    """(rows to add, rows to drop) that would make the regression JOURNEYS.md match the suite.
    New rows carry the file and the `covers:` the test declares; the path is left to write."""
    tests = suite(root, tests_dir, profile, sub=REGRESSION_DIR)
    path = root / tests_dir / REGRESSION_DIR / INDEX_FILE
    listed = indexed(path.read_text(encoding="utf-8")) if path.is_file() else set()
    add = []
    for title in sorted(set(tests) - listed):
        rel = tests[title]
        text = (root / rel).read_text(encoding="utf-8", errors="replace")
        body = next((b.body for b in tests_in(rel, text, profile) if b.title == title), "")
        covers = ", ".join(m.strip() for m in _COVERS.findall(body)) or "-"
        add.append(f"| {title} | {rel[len(tests_dir) + 1:]} | TODO: entry → steps → outcome | {covers} |")
    return add, sorted(listed - set(tests))
