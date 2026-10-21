"""The built-ins and the project template must give files the engine accepts, in every locale.

Two layers:

- Source checks (always run): the config template, the built-in role agents (`agents/`),
  prompt templates and artifact formats (`defaults/<locale>/`) against what the engine expects.
- Generated checks: generate a project per locale with the real `mark init`, then render
  every dispatch scenario through `mark.brief`.
"""
import io
import re
import shutil
import subprocess
import tempfile
import tomllib
import unittest
from pathlib import Path

from tests._support import PLUGIN_ROOT

from mark import brief, budget, cli, scaffold, tickets
from mark.config import MAIN, MarkConfig, load_config
from mark.flow import SCENARIOS, Action, Ctx
from mark.i18n import t

TEMPLATE = PLUGIN_ROOT / "template"
DEFAULTS = PLUGIN_ROOT / "defaults"
AGENTS = PLUGIN_ROOT / "agents"
LOCALES = ("en", "zh-CN")
ANSWERS = {"locale": "en", "profile": "web-fullstack", "project_name": "demo", "main_branch": "main",
           "frontend_dir": "frontend", "backend_dir": "backend", "ui_dir": "frontend/src/ui",
           "tests_dir": "tests", "regression_cmd": "make test",
           "worktree_setup": "npm ci"}

# Anchors each artifact format must show (language-neutral, see CLAUDE.md rule 7).
FORMAT_ANCHORS = {
    "requirement.md": ["<!-- mark:ac -->", "AC-1", "<!-- mark:open-questions -->"],
    "bug.md": [],
    "design.md": ["<!-- mark:states -->", "S-1", "<!-- mark:open-questions -->"],
    "design-qa.md": ["<!-- mark:qa-round 1 -->", "<!-- mark:qa passed -->", "<!-- mark:qa blocked -->", "D-1"],
    "tech-plan.md": ["<!-- mark:tasks -->", "T-1", "SD-1", "sequenceDiagram", "<!-- mark:open-questions -->"],
    "fix-plan.md": ["<!-- mark:ac -->", "AC-1", "[inline]", "<!-- mark:open-questions -->"],
    "handoff.md": ["<!-- mark:ac-table -->", "<!-- mark:blocked -->"],
    "verdict.md": ["<!-- mark:verdict FAILED -->", "FAIL-3", "failureType:", "routeTo:"],
}
FAILURE_TYPES = ("impl-bug", "needs-unit-test", "design-flaw", "unclear")
_FORMAT_REF = re.compile(r"mark format ([a-z-]+\.md)")


def render(text: str) -> str:
    return scaffold._fill(text, ANSWERS, toml=False)


def localized(name: str, locale: str) -> Path:
    """Built-in dir `defaults/<locale>/<name>`."""
    return DEFAULTS / locale / name


def frontmatter(text: str) -> dict[str, object]:
    """Tiny YAML subset: `key: value` and `key:` followed by `  - item` lines."""
    assert text.startswith("---\n"), "missing frontmatter"
    block = text[4:text.index("\n---", 4)]
    out: dict[str, object] = {}
    key = None
    for line in block.splitlines():
        if line.startswith("  - ") and key:
            out.setdefault(key, [])
            out[key].append(line[4:].strip())  # type: ignore[union-attr]
        elif ":" in line:
            key, _, value = line.partition(":")
            key = key.strip()
            if value.strip():
                out[key] = value.strip()
    return out


class TemplateConfigTest(unittest.TestCase):
    def setUp(self):
        self.cfg = MarkConfig(Path("."), tomllib.loads(scaffold.render(ANSWERS)[".mark/config.toml"]))

    def test_schema_supported(self):
        self.assertEqual(self.cfg.schema, 1)

    def test_regression_answer_reaches_merge(self):
        self.assertEqual(self.cfg.merge_regression, "make test")

    def test_setup_answer_reaches_worktree(self):
        self.assertEqual((self.cfg.worktree_setup, self.cfg.worktree_setup_timeout), ("npm ci", 300))

    def test_workflow_comes_from_engine_defaults(self):
        for key in ("roles", "gates", "outputs"):
            self.assertNotIn(key, self.cfg.data)
        self.assertEqual(self.cfg.roles, {"designer", "coder-plan", "coder-impl", "tester", "fix-plan"})
        self.assertEqual(self.cfg.outputs["designer"], ["design.md", "preview.html"])

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

    def test_ticket_briefs_are_main_only(self):
        for name in ("requirement.md", "bug.md"):
            self.assertEqual(self.cfg.write_rules[[r.glob for r in self.cfg.write_rules]
                                                  .index(f"**/{name}")].roles, {MAIN}, name)

    def test_quotes_in_answers_stay_valid_toml(self):
        files = scaffold.render({**ANSWERS, "regression_cmd": 'npm test -- --grep "a\\b"'})
        self.assertEqual(tomllib.loads(files[".mark/config.toml"])["merge"]["regression"], 'npm test -- --grep "a\\b"')

    def test_template_uses_only_known_answers(self):
        for loc in LOCALES:
            for p in (TEMPLATE / loc).rglob("*.tmpl"):
                for name in re.findall(r"\{\{\s*(\w+)\s*\}\}", p.read_text(encoding="utf-8")):
                    self.assertIn(name, scaffold.KEYS, p)


class TemplatePromptsTest(unittest.TestCase):
    def test_every_scenario_in_every_locale(self):
        for loc in LOCALES:
            names = {p.stem for p in localized("prompts", loc).glob("*.md")} - {"README"}
            self.assertEqual(names, set(SCENARIOS), loc)

    def test_role_placeholders_and_outputs(self):
        for loc in LOCALES:
            for path in sorted(localized("prompts", loc).glob("*.md")):
                if path.stem == "README":
                    continue
                with self.subTest(locale=loc, scenario=path.stem):
                    tpl = brief.parse_template(path.read_text(encoding="utf-8"))
                    self.assertEqual(tpl.role, SCENARIOS[path.stem])
                    used = set(brief.placeholders(tpl.body))
                    self.assertLessEqual(used, brief.PLACEHOLDERS)
                    self.assertIn("brief", used)
                    for out in tpl.outputs or []:
                        self.assertIn(out, FORMAT_ANCHORS)

    def test_review_scenarios_name_the_open_rounds(self):
        for loc in LOCALES:
            folder = localized("prompts", loc)
            for name in ("designer-review-rework", "coder-plan-rework", "coder-impl-merge-rework"):
                body = (folder / f"{name}.md").read_text(encoding="utf-8")
                for ph in ("{{review_file}}", "{{pending_rounds}}", "{{pending_refs}}"):
                    self.assertIn(ph, body, f"{loc}/{name}")

    def test_integration_qa_overrides_outputs(self):
        for loc in LOCALES:
            path = localized("prompts", loc) / "designer-integration-qa.md"
            tpl = brief.parse_template(path.read_text(encoding="utf-8"))
            self.assertEqual(tpl.outputs, ["design-qa.md"])
            self.assertIn("<!-- mark:qa passed -->", tpl.body)


class BuiltinAgentsTest(unittest.TestCase):
    def setUp(self):
        self.roles = set(MarkConfig(Path("."), {}).roles)

    def test_one_agent_per_role_with_role_rules(self):
        self.assertEqual({p.name for p in AGENTS.iterdir()}, {f"{r}.md" for r in self.roles})
        for role in self.roles:
            with self.subTest(role=role):
                text = (AGENTS / f"{role}.md").read_text(encoding="utf-8")
                meta = frontmatter(text)
                self.assertEqual(meta["name"], role)
                self.assertIn("mark:role-rules", meta.get("skills", []))
                self.assertNotIn("Agent", str(meta.get("tools", "")))
                # Ignored for plugin agents; Mark's guards live in hooks/hooks.json.
                for field in ("hooks", "mcpServers", "permissionMode"):
                    self.assertNotIn(field, meta)
                self.assertNotIn("{{", text)
                self.assertIn("mark rules role", text)

    def test_agents_name_failure_types_and_outcomes(self):
        tester = (AGENTS / "tester.md").read_text(encoding="utf-8")
        for ft in FAILURE_TYPES:
            self.assertIn(f"`{ft}`", tester)


class TemplateFormatsTest(unittest.TestCase):
    def test_same_formats_and_anchors_in_every_locale(self):
        for loc in LOCALES:
            folder = localized("formats", loc)
            self.assertEqual({p.name for p in folder.glob("*.md")}, set(FORMAT_ANCHORS), loc)
            for name, anchors in FORMAT_ANCHORS.items():
                text = (folder / name).read_text(encoding="utf-8")
                for anchor in anchors:
                    self.assertIn(anchor, text, f"{loc}/{name}")

    def test_referenced_formats_exist(self):
        for loc in LOCALES:
            texts = [p.read_text(encoding="utf-8")
                     for d in (localized("prompts", loc), AGENTS) for p in d.iterdir()]
            refs = {m for text in texts for m in _FORMAT_REF.findall(text)}
            self.assertTrue(refs)
            self.assertLessEqual(refs, set(FORMAT_ANCHORS), loc)

    def test_locales_ship_the_same_files(self):
        sets = [{p.relative_to(DEFAULTS / loc).as_posix() for p in (DEFAULTS / loc).rglob("*") if p.is_file()}
                for loc in LOCALES]
        self.assertEqual(sets[0], sets[1])
        self.assertIn("collaboration.md", sets[0])

    def test_builtins_fit_the_default_budget(self):
        cfg = MarkConfig(Path("."), tomllib.loads(scaffold.render(ANSWERS)[".mark/config.toml"]))
        files = {f".claude/agents/{p.name}": p for p in AGENTS.iterdir()}
        for loc in LOCALES:
            for kind in ("prompts", "formats"):
                files.update({f".mark/{kind}/{p.name}#{loc}": p for p in localized(kind, loc).iterdir()})
        for rel, path in files.items():
            limit = budget.limit_for(cfg, rel.split("#")[0])
            self.assertTrue(limit, rel)
            self.assertLessEqual(path.stat().st_size, limit, rel)


class RoleRulesTest(unittest.TestCase):
    def test_skill_is_hidden_and_printable(self):
        text = (PLUGIN_ROOT / "skills/role-rules/SKILL.md").read_text(encoding="utf-8")
        meta = frontmatter(text)
        self.assertEqual(meta["name"], "role-rules")
        self.assertEqual(meta["user-invocable"], "false")
        out = subprocess.run([str(PLUGIN_ROOT / "bin/mark"), "rules", "role"],
                             capture_output=True, text=True, check=True).stdout
        self.assertTrue(out.startswith("# Mark role rules"))


class GeneratedProjectTest(unittest.TestCase):
    """`mark init` per locale, then render every scenario with the real engine."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="mark-gen-"))
        cls.projects: dict[str, Path] = {}
        for loc in LOCALES:
            dest = cls.tmp / loc
            dest.mkdir()
            err = io.StringIO()
            code = cli.main(["init", "--locale", loc, "--project-name", "demo"], cwd=dest,
                            out=io.StringIO(), err=err)
            assert code == 0, err.getvalue()
            cls.projects[loc] = dest

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_layout(self):
        for loc, root in self.projects.items():
            paths = [p.relative_to(root).as_posix() for p in root.rglob("*")
                     if p.is_file() and ".git" not in p.relative_to(root).parts]
            for p in paths:
                self.assertNotIn("{", p, f"{loc}: unrendered path {p}")
            for want in ["CLAUDE.md", ".mark/config.toml", ".mark/README.md", ".mark/template.toml", ".gitignore"]:
                self.assertIn(want, paths, loc)
            for p in paths:  # built-ins stay in the plugin
                self.assertFalse(p.startswith((".claude/", ".mark/prompts/", ".mark/formats/")), f"{loc}: {p}")
            record = tomllib.loads((root / ".mark/template.toml").read_text(encoding="utf-8"))
            self.assertEqual(record["answers"]["locale"], loc)
            self.assertEqual(record["version"], scaffold.version())
            for rel in scaffold.render(record["answers"]):
                self.assertEqual((root / scaffold.base_path(rel)).read_text(encoding="utf-8"),
                                 (root / rel).read_text(encoding="utf-8"), f"{loc}: base of {rel}")

    def test_rendered_docs_have_no_placeholders_left(self):
        for loc, root in self.projects.items():
            for rel in ("CLAUDE.md", ".mark/README.md"):
                text = (root / rel).read_text(encoding="utf-8")
                self.assertNotIn("{%", text, f"{loc}/{rel}")
                self.assertNotIn("{{ ", text, f"{loc}/{rel}")
            self.assertTrue((root / "CLAUDE.md").read_text(encoding="utf-8").startswith("# CLAUDE.md — demo"))
            self.assertEqual(load_config(root).locale, loc)

    def test_shipped_docs_fit_the_default_budget(self):
        for loc, root in self.projects.items():
            cfg = load_config(root)
            self.assertTrue(cfg.doc_budget, loc)
            for p in root.rglob("*.md"):
                rel = p.relative_to(root).as_posix()
                limit = budget.limit_for(cfg, rel)
                if limit:
                    self.assertLessEqual(p.stat().st_size, limit, f"{loc}/{rel}")

    def test_every_scenario_renders(self):
        for loc, root in self.projects.items():
            cfg = load_config(root)
            feature = Ctx(cfg, tickets.claim(cfg, "feature", "demo feature", slug="demo"))
            bug = Ctx(cfg, tickets.claim(cfg, "bug", "demo bug", slug="crash"))
            for scenario, role in SCENARIOS.items():
                ctxs = [bug] if role == "fix-plan" else [feature] if role in ("designer", "coder-plan") else [feature, bug]
                for ctx in ctxs:
                    with self.subTest(locale=loc, scenario=scenario, kind=ctx.kind):
                        review = ctx.state_dir / "review-design.md"
                        action = Action("dispatch", role=role, scenario=scenario, trigger="FAIL-1 (verdict.md)",
                                        review=str(review), pending_rounds=[1], pending_refs=["R-1"])
                        out = brief.render(ctx, action, prev="previous step done")
                        self.assertTrue(out.startswith("<!-- mark:ticket "), out[:80])
                        self.assertNotIn("{{", out)
                        self.assertIn(t(loc, "brief.title"), out)
                        self.assertIn(str(ctx.worktree), out)
                        if scenario == "designer-integration-qa":
                            self.assertIn("<!-- mark:outputs design-qa.md -->", out)


if __name__ == "__main__":
    unittest.main()
