"""The documentation must not drift from the code: links resolve, versions agree, every type and flag is mentioned."""
import glob
import os
import re
import sys
import unittest

from tests.helpers import AGENT_COUNT, COMMAND_COUNT, rtext

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "runtime"))
import visual_engine as ve  # noqa: E402

DOCS = ["README.md", "INSTALL.md", "CHANGELOG.md"] + sorted(glob.glob(os.path.join(ROOT, "docs", "*.md")))


class Docs(unittest.TestCase):
    def test_version_matches_the_changelog(self):
        version = rtext(os.path.join(ROOT, "VERSION")).strip()
        self.assertRegex(version, r"^\d+\.\d+\.\d+$")
        first = re.search(r"^## (\d+\.\d+\.\d+)", rtext(os.path.join(ROOT, "CHANGELOG.md")), re.M).group(1)
        self.assertEqual(version, first)

    def test_relative_links_resolve(self):
        for doc in DOCS:
            path = doc if os.path.isabs(doc) else os.path.join(ROOT, doc)
            for target in re.findall(r"\]\(([^)#\s]+)(?:#[^)]*)?\)", rtext(path)):
                if re.match(r"^(https?:|mailto:)", target):
                    continue
                self.assertTrue(os.path.exists(os.path.normpath(os.path.join(os.path.dirname(path), target))), "%s links to missing %s" % (os.path.basename(path), target))

    def test_visual_reference_covers_every_type_and_theme_field(self):
        text = rtext(os.path.join(ROOT, "docs", "VISUALS.md"))
        for t in ve.DIAGRAM_TYPES + ve.SLIDE_ONLY:
            self.assertIn("### " + t, text)
        for w in ("text_overflow", "small_text", "stat_needs_source", "contrast", "1080 x 1350"):
            self.assertIn(w, text)

    def test_install_guide_matches_the_installers(self):
        guide = rtext(os.path.join(ROOT, "INSTALL.md"))
        for token in ("--auto", "-Auto", "AUTO-INSTALL-RESULT", "answers.json", "setup_wizard.py", "demo.py", "portable/all-in-one.md"):
            self.assertIn(token, guide)
        self.assertIn("AUTO-INSTALL-RESULT", rtext(os.path.join(ROOT, "install.sh")))
        self.assertIn("AUTO-INSTALL-RESULT", rtext(os.path.join(ROOT, "install.ps1")))
        self.assertIn("INSTALL.md", rtext(os.path.join(ROOT, "README.md")).split("## Install")[0])      # AI assistants find it at the top

    def test_the_install_guide_starts_by_checking_it_is_on_the_owners_computer(self):
        guide = rtext(os.path.join(ROOT, "INSTALL.md"))
        self.assertLess(guide.index("## Step 0. Check where you are running"), guide.index("## Step 1."))
        step0 = guide.split("## Step 0.")[1].split("## Step 1.")[0]
        for phrase in ("temporary sandbox", "Stop here", "Claude Code", "owner's own computer", "paste into a terminal"):
            self.assertIn(phrase, step0)
        self.assertIn("unless Step 0 showed", guide)
        readme = rtext(os.path.join(ROOT, "README.md"))
        self.assertIn("temporary sandbox", readme)
        self.assertLess(readme.index("Where \"install <URL>\" works"), readme.index("**By hand.**"))

    def test_the_install_guide_example_answers_are_accepted_by_the_wizard(self):
        import json
        import shutil
        import setup_wizard as w
        from tests.helpers import make_workspace
        block = re.search(r"```json\n(\{.*?\})\n```", rtext(os.path.join(ROOT, "INSTALL.md")), re.S).group(1)
        ws = make_workspace()
        try:
            res = w.apply_answers(ws, json.loads(block))
            self.assertTrue(res["settings"]["setup_completed"])
            self.assertEqual(len(res["schedule"]["slots"]), 2)
        finally:
            shutil.rmtree(ws, ignore_errors=True)

    def test_readme_is_honest_about_what_was_not_tested(self):
        text = rtext(os.path.join(ROOT, "README.md"))
        self.assertIn("Honest limits", text)
        for phrase in ("real Claude Code or Codex", "stand-in", "ntfy.sh", "Chromium 153"):
            self.assertIn(phrase, text)

    def test_ci_workflow_covers_three_systems_and_both_pythons(self):
        text = rtext(os.path.join(ROOT, ".github", "workflows", "tests.yml"))
        for token in ("ubuntu", "macos", "windows", '"3.8"', '"3.12"', "tests/run_all.py", "build.py --check"):
            self.assertIn(token, text)

    def test_runtime_readme_lists_every_script(self):
        text = rtext(os.path.join(ROOT, "runtime", "README.md"))
        for f in sorted(os.listdir(os.path.join(ROOT, "runtime"))):
            if f.endswith((".py", ".sh", ".md")) and f != "README.md" and f != "scheduled-prompt.md":
                base = f.rsplit(".", 1)[0]
                self.assertIn(base.replace("_", "_"), text, f)


class Counts(unittest.TestCase):
    def test_the_agent_counts_in_the_docs_match_the_build(self):
        n = AGENT_COUNT
        readme = rtext(os.path.join(ROOT, "README.md"))
        self.assertIn("**%d agents** (%d specialists plus one orchestrator)" % (n + 1, n), readme)
        self.assertIn("| %d agents |" % (n + 1), readme)
        self.assertIn("with %d specialist agents plus an orchestrator" % n, rtext(os.path.join(ROOT, "INSTALL.md")))
        self.assertIn("as %d specialist subagents" % n, rtext(os.path.join(ROOT, "CLAUDE.md")))
        self.assertIn("(%d agents, four decisions)" % (n + 1), rtext(os.path.join(ROOT, "docs", "FLOWCHART.md")))
        self.assertIn("%d LinkedIn specialist agents" % n, rtext(os.path.join(ROOT, ".claude-plugin", "plugin.json")))

    def test_every_agent_is_in_the_readme_table_with_its_command_and_skill(self):
        import re
        readme = rtext(os.path.join(ROOT, "README.md"))
        for name in __import__("build").ORDER:
            meta = re.search(r"^display_name:\s*(.+)$", rtext(os.path.join(ROOT, "src", "stages", name + ".md")), re.M).group(1).strip()
            self.assertRegex(readme, r"\| %s \|" % re.escape(meta), name)
            self.assertIn("`$%s`" % name, readme, name)

    def test_every_new_script_is_explained_in_the_user_guide_or_troubleshooting(self):
        text = rtext(os.path.join(ROOT, "docs", "USER-GUIDE.md")) + rtext(os.path.join(ROOT, "docs", "TROUBLESHOOTING.md"))
        for script in ("post_lint", "ai_tells", "reply_filter", "doctor.py", "agent_evals.py", "publish_publora.py"):
            self.assertIn(script, text, script)

    def test_the_add_on_is_described_as_off_by_default_everywhere_it_appears(self):
        for rel in ("README.md", "docs/USER-GUIDE.md", "docs/SECURITY-AND-PRIVACY.md", "SECURITY.md", "CHANGELOG.md"):
            text = rtext(os.path.join(ROOT, rel))
            if "Publora" in text:
                self.assertRegex(text.lower(), r"off by default|is off unless|off \(the default\)|off unless", rel)

    def test_the_command_count_is_stable_and_documented_by_the_build(self):
        import glob
        self.assertEqual(len(glob.glob(os.path.join(ROOT, ".claude", "commands", "*.md"))), COMMAND_COUNT)


if __name__ == "__main__":
    unittest.main()
