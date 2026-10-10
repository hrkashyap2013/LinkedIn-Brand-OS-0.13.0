"""Consistency tests for the agents, commands, memory and docs. Run: python3 tests/run_all.py"""
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

from tests.helpers import AGENT_COUNT, COMMAND_COUNT, SKILL_COUNT

sys.dont_write_bytecode = True
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import build  # noqa: E402

AGENTS = build.ORDER


def read(*p):
    with open(os.path.join(ROOT, *p), encoding="utf-8") as f:
        return f.read()


def frontmatter(text):
    m = re.match(r"---\n(.*?)\n---\n", text, re.S)
    assert m, "no frontmatter"
    return dict(line.split(":", 1) for line in m.group(1).splitlines() if ":" in line)


class GeneratedFiles(unittest.TestCase):
    def test_generated_files_are_up_to_date(self):
        r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "build.py"), "--check"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_counts(self):
        self.assertEqual(len(AGENTS), AGENT_COUNT)
        self.assertEqual(len(glob.glob(os.path.join(ROOT, ".claude", "agents", "*.md"))), AGENT_COUNT)
        self.assertEqual(len(glob.glob(os.path.join(ROOT, "codex", "skills", "*", "SKILL.md"))), SKILL_COUNT)  # agents + orchestrator
        self.assertEqual(len(glob.glob(os.path.join(ROOT, "prompts", "*.md"))), AGENT_COUNT + 2)  # agents + orchestrator + README


class AgentSources(unittest.TestCase):
    def test_source_files_match_order(self):
        found = sorted(os.path.basename(p)[:-3] for p in glob.glob(os.path.join(ROOT, "src", "stages", "*.md")))
        self.assertEqual(found, sorted(AGENTS))

    def test_every_agent_has_the_contract_sections(self):
        for n in AGENTS:
            t = read("src", "stages", n + ".md")
            self.assertIn("Purpose:", t, n)
            for h in ("## Output", "## Handoff", "## Stop condition"):
                self.assertIn(h, t, f"{n} lacks {h}")
            self.assertTrue("## Inputs" in t or "## Start condition" in t, n)

    def test_frontmatter_is_yaml_safe(self):
        for p in glob.glob(os.path.join(ROOT, ".claude", "**", "*.md"), recursive=True) + glob.glob(os.path.join(ROOT, "codex", "skills", "*", "SKILL.md")):
            fm = frontmatter(open(p, encoding="utf-8").read())
            desc = fm["description"].strip()
            self.assertNotIn(": ", desc, p)
            self.assertNotIn(" #", desc, p)
            self.assertFalse(desc.startswith(("'", '"', "[", "{", "&", "*", "!", "|", ">", "%", "@", "`")), p)

    def test_tool_policy(self):
        for n in AGENTS:
            tools = frontmatter(read(".claude", "agents", n + ".md"))["tools"]
            for forbidden in ("Bash", "Write", "Edit", "NotebookEdit"):
                self.assertNotIn(forbidden, tools, f"{n} must not have {forbidden}")
            self.assertEqual("WebSearch" in tools, n in ("research", "brand"), n)

    def test_names_have_no_codes_or_prefix(self):
        for n in AGENTS:
            self.assertNotRegex(n, r"^linkedin-")
        for p in glob.glob(os.path.join(ROOT, "src", "**", "*.md"), recursive=True):
            self.assertNotRegex(open(p, encoding="utf-8").read(), r"\bA(0[1-9]|1[0-9])\b", p)

    def test_orchestrator_mentions_every_agent(self):
        t = read("src", "orchestrator.md")
        for n in AGENTS:
            self.assertIn("{{call:%s}}" % n, t, n)
        for ref in set(re.findall(r"\{\{call:([a-z-]+)\}\}", t)):
            self.assertIn(ref, AGENTS, ref)

    def test_only_posting_prepares_sending_and_no_agent_can_send(self):
        for n in AGENTS:
            t = read("src", "stages", n + ".md")
            self.assertNotRegex(t, r"(?i)\byou (may|can|will) (publish|post) ", n)
        self.assertIn("no sending tool", read("src", "stages", "posting.md"))

    def test_four_decisions_everywhere(self):
        for p in ("src/orchestrator.md", "src/stages/governance.md", "src/stages/posting.md"):
            self.assertRegex(read(*p.split("/")), r"(?i)four", p)


class Commands(unittest.TestCase):
    def test_every_agent_has_a_command(self):
        for n in AGENTS + ["orchestrator"]:
            self.assertTrue(os.path.exists(os.path.join(ROOT, ".claude", "commands", n + ".md")), n)

    def test_commands_only_reference_real_subagents(self):
        for p in glob.glob(os.path.join(ROOT, ".claude", "commands", "*.md")):
            t = open(p, encoding="utf-8").read()
            for ref in re.findall(r"(?:the|then) ([a-z]+(?:-[a-z]+)*) subagent", t):
                self.assertIn(ref, AGENTS, f"{os.path.basename(p)} references {ref}")


class MemoryTemplates(unittest.TestCase):
    def test_registry_matches_agents_and_files(self):
        reg = json.loads(read("memory", "registry.json"))
        allowed = set(AGENTS) | {"orchestrator"}
        self.assertEqual(sorted(reg["registers"]), sorted(["content-memory", "visual-memory", "experiment-register", "change-register", "learning-register",
                                                           "ideas-and-examples", "experience-bank", "post-tracker", "evidence-library", "approval-log", "profile-proposals"]))
        for r, writers in reg["registers"].items():
            self.assertTrue(os.path.exists(os.path.join(ROOT, "memory", r + ".md")), r)
            for w in writers:
                self.assertIn(w, allowed, f"{r}: {w}")
        for w in reg["profile"]["propose"] + reg["profile"]["apply"]:
            self.assertIn(w, allowed)

    def test_json_docs_parse(self):
        for f in ("schedule.json", "schedule.example.json", "settings.json", "metrics-columns.json"):
            json.loads(read("docs", f))

    def test_settings_template_is_blank_and_holds_no_secrets(self):
        s = json.loads(read("docs", "settings.json"))
        self.assertFalse(s["setup_completed"])
        self.assertEqual((s["language"], s["users"], s["run_tool"]), ("", [], ""))
        self.assertFalse(s["notifications"]["desktop"] or s["notifications"]["phone"])
        self.assertNotIn("topic", json.dumps(s).replace("private phone topic", ""))  # the topic lives in config.local.json only
        self.assertIn("*.local.json", read(".gitignore"))

    def test_registers_start_empty(self):
        sys.path.insert(0, os.path.join(ROOT, "runtime"))
        import memory_guard as g
        for r in g.REGISTERS:
            lines = read("memory", r + ".md").split("\n")
            tbl = g.find_table(lines)
            self.assertIsNotNone(tbl, r)
            self.assertEqual(tbl[1] - tbl[0], 1, f"{r} should ship with no data rows")


class GitTracking(unittest.TestCase):
    @unittest.skipUnless(shutil.which("git"), "git not available")
    def test_nothing_the_installer_needs_is_git_ignored(self):
        tmp = tempfile.mkdtemp()
        try:
            dst = os.path.join(tmp, "repo")
            shutil.copytree(ROOT, dst, ignore=shutil.ignore_patterns(".git", "__pycache__"))
            run = lambda *a: subprocess.run(["git", *a], cwd=dst, capture_output=True, text=True)
            run("init", "-q")
            run("add", "-A")
            ignored = [l[3:] for l in run("status", "--porcelain", "--ignored").stdout.splitlines() if l.startswith("!!")]
            self.assertEqual(ignored, [], f"these files would not reach GitHub: {ignored}")
            tracked = run("ls-files").stdout.split("\n")
            for need in ("reports/README.md", "drafts/README.md", "inbox/README.md", "runs/README.md", "memory/registry.json",
                         "runtime/memory_guard.py", "docs/brand-profile.md", ".gitignore", ".gitattributes"):
                self.assertIn(need, tracked, need)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class Privacy(unittest.TestCase):
    def test_no_personal_details_or_secrets(self):
        bad = re.compile(r"(?i)helly|crystal phoenix|hrkashyap|kashyap|api[_-]?key\s*[:=]\s*\S{12,}|sk-[A-Za-z0-9]{20,}")
        for p in glob.glob(os.path.join(ROOT, "**", "*"), recursive=True):
            q = p.replace(os.sep, "/")                                   # Windows paths use backslashes
            if os.path.isdir(p) or "/.git/" in q or q.endswith((".png", ".jpg", ".zip", ".pyc")) or "/tests/" in q:
                continue
            try:
                t = open(p, encoding="utf-8").read()
            except (UnicodeDecodeError, OSError):
                continue
            self.assertIsNone(bad.search(t), p)


class LineEndings(unittest.TestCase):
    def test_a_crlf_checkout_is_not_reported_as_out_of_date(self):
        """On Windows git may check files out with CRLF; the generated-files check must not call that a difference."""
        tmp = tempfile.mkdtemp()
        try:
            dst = os.path.join(tmp, "repo")
            shutil.copytree(ROOT, dst, ignore=shutil.ignore_patterns(".git", "__pycache__", "node_modules"))
            converted = 0
            for dirpath, _dirs, files in os.walk(dst):
                for f in files:
                    if f.endswith((".md", ".json", ".yml", ".txt", ".py", ".yaml")) and not f.endswith(".sh"):
                        p = os.path.join(dirpath, f)
                        with open(p, "rb") as fh:
                            data = fh.read()
                        with open(p, "wb") as fh:
                            fh.write(data.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
                        converted += 1
            self.assertGreater(converted, 100)
            r = subprocess.run([sys.executable, os.path.join(dst, "scripts", "build.py"), "--check"], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_gitattributes_forces_lf_except_for_powershell(self):
        text = read(".gitattributes")
        self.assertIn("* text=auto eol=lf", text)
        self.assertIn("*.ps1 text eol=crlf", text)


if __name__ == "__main__":
    unittest.main()
