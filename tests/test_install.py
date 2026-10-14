"""Installer tests (bash always when available; PowerShell when pwsh is on PATH or $PWSH)."""
import glob
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

from tests.helpers import AGENT_COUNT, COMMAND_COUNT, SKILL_COUNT

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASH = shutil.which("bash")
PWSH = os.environ.get("PWSH") or shutil.which("pwsh")


def count(path, pattern="*"):
    return len(glob.glob(os.path.join(path, pattern)))


@unittest.skipUnless(BASH and os.name != "nt", "bash installer tests need bash on macOS/Linux")
class BashInstaller(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp()
        self.ws = os.path.join(tempfile.mkdtemp(), "ws")
        self.env = dict(os.environ, HOME=self.home, CODEX_HOME=os.path.join(self.home, ".codex"))

    def tearDown(self):
        shutil.rmtree(self.home, ignore_errors=True)
        shutil.rmtree(os.path.dirname(self.ws), ignore_errors=True)

    def sh(self, script, *args):
        return subprocess.run([BASH, os.path.join(ROOT, script), *args], capture_output=True, text=True, env=self.env)

    def test_project_install_all_tools(self):
        r = self.sh("install.sh", "--project", self.ws, "--tool", "all")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(count(os.path.join(self.ws, ".claude", "agents")), AGENT_COUNT)
        self.assertEqual(count(os.path.join(self.ws, ".claude", "commands")), COMMAND_COUNT)
        self.assertEqual(count(os.path.join(self.home, ".codex", "skills")), SKILL_COUNT)
        for f in ("CLAUDE.md", "AGENTS.md", "docs/brand-profile.md", "docs/schedule.json", "memory/registry.json", "memory/approval-log.md",
                  "scripts/memory_guard.py", "scripts/metrics.py", "scripts/notify.py", "scripts/setup_wizard.py", "docs/settings.json", "runs/README.md", "drafts/README.md", "inbox/README.md"):
            self.assertTrue(os.path.exists(os.path.join(self.ws, f)), f)

    def test_guard_runs_inside_an_installed_workspace(self):
        self.sh("install.sh", "--project", self.ws)
        r = subprocess.run([sys.executable, os.path.join(self.ws, "scripts", "memory_guard.py"), "--workspace", self.ws, "check"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_rerun_is_idempotent_and_user_data_survives(self):
        self.sh("install.sh", "--project", self.ws)
        prof = os.path.join(self.ws, "docs", "brand-profile.md")
        open(prof, "w").write("MY PROFILE")
        open(os.path.join(self.ws, "memory", "content-memory.md"), "a").write("my row\n")
        r = self.sh("install.sh", "--project", self.ws)
        self.assertIn("0 updated", r.stdout)
        self.assertEqual(open(prof).read(), "MY PROFILE")
        self.assertIn("my row", open(os.path.join(self.ws, "memory", "content-memory.md")).read())

    def test_legacy_agents_are_removed(self):
        legacy = os.path.join(self.home, ".claude", "agents")
        os.makedirs(legacy)
        for n in ("linkedin-governance", "linkedin-content-planner"):
            open(os.path.join(legacy, n + ".md"), "w").write("old")
        self.sh("install.sh", "--global")
        self.assertFalse(os.path.exists(os.path.join(legacy, "linkedin-governance.md")))
        self.assertFalse(os.path.exists(os.path.join(legacy, "linkedin-content-planner.md")))
        self.assertEqual(count(legacy, "*.md"), AGENT_COUNT)

    def test_no_questions_are_asked_without_a_terminal_and_flags_are_documented(self):
        r = self.sh("install.sh", "--project", self.ws)   # stdin is not a terminal here: must not hang or prompt
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("setup questions now", r.stdout)
        self.assertIn("setup_wizard.py", r.stdout)
        self.assertIn("--no-wizard", self.sh("install.sh", "--help").stdout)

    def test_wizard_flag_without_a_terminal_fails_politely_and_install_still_succeeds(self):
        r = self.sh("install.sh", "--project", self.ws, "--wizard")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("needs a terminal", r.stderr + r.stdout)
        self.assertIn("Setup was not completed", r.stdout)
        self.assertTrue(os.path.exists(os.path.join(self.ws, "memory", "registry.json")))

    def test_auto_mode_installs_everything_without_questions(self):
        env = dict(self.env)
        r = subprocess.run([BASH, os.path.join(ROOT, "install.sh"), "--auto"], capture_output=True, text=True, env=env, stdin=subprocess.DEVNULL)
        self.assertEqual(r.returncode, 0, r.stderr)
        ws = os.path.join(self.home, "linkedin")                 # the default workspace
        self.assertIn("AUTO-INSTALL-RESULT", r.stdout)
        self.assertIn("status: ok", r.stdout)
        self.assertIn("workspace: " + ws, r.stdout)
        self.assertIn("tools: all", r.stdout)
        self.assertIn("Doctor (checks your setup", r.stdout)               # the doctor ran and its result is shown
        self.assertIn("The install itself succeeded. The doctor lines above check your SETUP", r.stdout)
        self.assertIn("Workspace folders: docs, memory and scripts are present", r.stdout)
        self.assertRegex(r.stdout, r"doctor: (ok|attention|problems)")
        self.assertLess(r.stdout.index("Doctor (checks"), r.stdout.index("AUTO-INSTALL-RESULT"))
        self.assertEqual(count(os.path.join(ws, ".claude", "agents")), AGENT_COUNT)
        self.assertEqual(count(os.path.join(self.home, ".codex", "skills")), SKILL_COUNT)            # Codex skills go to the Codex folder
        for f in ("scripts/chat_app.py", "scripts/app/app.js", "scripts/app/index.html", "scripts/visual_engine.py", "scripts/demo.py", "prompts/governance.md",
                  "prompts/00-orchestrator.md", "docs/USER-GUIDE.md", "docs/SECURITY-AND-PRIVACY.md", "VERSION", "scripts/doctor.py", "scripts/post_lint.py", "scripts/ai_tells.py",
                  "scripts/reply_filter.py", "scripts/agent_evals.py", "scripts/publish_publora.py", "prompts/interviewer.md", "prompts/reply.md"):
            self.assertTrue(os.path.exists(os.path.join(ws, f)), f)
        self.assertFalse(os.path.exists(os.path.join(ws, "scripts", "__pycache__")))
        again = subprocess.run([BASH, os.path.join(ROOT, "install.sh"), "--auto"], capture_output=True, text=True, env=env, stdin=subprocess.DEVNULL)
        self.assertIn("0 updated", again.stdout)

    def test_the_next_steps_name_real_skills_and_number_each_step_once(self):
        import re
        r = subprocess.run([BASH, os.path.join(ROOT, "install.sh"), "--auto"], capture_output=True, text=True, env=self.env, stdin=subprocess.DEVNULL)
        self.assertEqual(r.returncode, 0, r.stderr)
        block = r.stdout.split("Next steps:")[1].split("Try it without")[0]
        self.assertNotIn("linkedin-orchestrator", r.stdout)
        for name in re.findall(r"Use \$([a-z-]+)", block):
            self.assertTrue(os.path.isdir(os.path.join(ROOT, "codex", "skills", name)), "the next steps name a skill that does not exist: " + name)
        self.assertIn("Use $orchestrator", block)
        numbers = re.findall(r"^\s+(\d)\. ", block, re.M)
        self.assertEqual(numbers, sorted(set(numbers)), numbers)                  # no step number appears twice
        self.assertIn("     or: codex", block)

    def test_a_failing_doctor_never_fails_the_install(self):
        env = dict(self.env, CLAUDE_BIN="definitely-not-installed", CODEX_BIN="definitely-not-installed")
        r = subprocess.run([BASH, os.path.join(ROOT, "install.sh"), "--auto"], capture_output=True, text=True, env=env, stdin=subprocess.DEVNULL)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("status: ok", r.stdout)
        self.assertIn("doctor: problems", r.stdout)                         # no AI tool on this machine: reported, not fatal

    def test_dry_run_does_not_run_the_doctor(self):
        r = subprocess.run([BASH, os.path.join(ROOT, "install.sh"), "--auto", "--dry-run"], capture_output=True, text=True, env=self.env, stdin=subprocess.DEVNULL)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("Doctor (checks", r.stdout)
        self.assertIn("doctor: skipped", r.stdout)

    def test_auto_mode_honours_a_chosen_folder_and_tool(self):
        env = dict(self.env, LBA_WORKSPACE=self.ws)
        r = subprocess.run([BASH, os.path.join(ROOT, "install.sh"), "--auto", "--tool", "claude"], capture_output=True, text=True, env=env, stdin=subprocess.DEVNULL)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("workspace: " + self.ws, r.stdout)
        self.assertIn("tools: claude", r.stdout)
        self.assertFalse(os.path.exists(os.path.join(self.home, ".codex")))

    def test_the_installed_app_starts_from_the_installed_workspace(self):
        self.sh("install.sh", "--project", self.ws, "--no-wizard")
        r = subprocess.run([sys.executable, os.path.join(self.ws, "scripts", "demo.py"), "--dir", os.path.join(self.home, "demo"), "--build-only"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        meta = subprocess.run([sys.executable, "-c", "import sys; sys.path.insert(0, %r); import chat_core as c; print(len(c.agents(%r)), len(c.commands(%r)))" %
                               (os.path.join(self.ws, "scripts"), self.ws, self.ws)], capture_output=True, text=True)
        self.assertEqual(meta.stdout.split()[0], str(AGENT_COUNT), meta.stderr)

    def test_check_and_uninstall(self):
        self.sh("install.sh", "--project", self.ws)
        self.assertEqual(self.sh("install.sh", "--check", "--project", self.ws).returncode, 0)
        os.remove(os.path.join(self.ws, ".claude", "commands", "next.md"))
        self.assertEqual(self.sh("install.sh", "--check", "--project", self.ws).returncode, 1)
        open(os.path.join(self.ws, "docs", "brand-profile.md"), "w").write("MINE")
        self.sh("uninstall.sh", "--project", self.ws)
        self.assertEqual(count(os.path.join(self.ws, ".claude", "agents"), "*.md"), 0)
        self.assertEqual(open(os.path.join(self.ws, "docs", "brand-profile.md")).read(), "MINE")


@unittest.skipUnless(PWSH, "PowerShell not available")
class PowerShellInstaller(unittest.TestCase):
    def test_project_install_and_check(self):
        home, ws = tempfile.mkdtemp(), os.path.join(tempfile.mkdtemp(), "ws")
        env = dict(os.environ, HOME=home, USERPROFILE=home, CODEX_HOME=os.path.join(home, ".codex"), DOTNET_SYSTEM_GLOBALIZATION_INVARIANT="1")
        run = lambda *a: subprocess.run([PWSH, "-NoProfile", "-File", os.path.join(ROOT, a[0]), *a[1:]], capture_output=True, text=True, env=env)
        try:
            r = run("install.ps1", "-Project", ws, "-Tool", "all")
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertEqual(count(os.path.join(ws, ".claude", "agents")), AGENT_COUNT)
            self.assertEqual(count(os.path.join(home, ".codex", "skills")), SKILL_COUNT)
            self.assertTrue(os.path.exists(os.path.join(ws, "memory", "registry.json")))
            self.assertEqual(run("install.ps1", "-Check", "-Project", ws, "-Tool", "all").returncode, 0)
            self.assertTrue(os.path.exists(os.path.join(ws, "scripts", "app", "app.js")))
            self.assertTrue(os.path.exists(os.path.join(ws, "prompts", "governance.md")))
            auto_home = tempfile.mkdtemp()
            try:
                env2 = dict(env, HOME=auto_home, USERPROFILE=auto_home, CODEX_HOME=os.path.join(auto_home, ".codex"))
                r2 = subprocess.run([PWSH, "-NoProfile", "-File", os.path.join(ROOT, "install.ps1"), "-Auto"], capture_output=True, text=True, env=env2)
                self.assertEqual(r2.returncode, 0, r2.stdout + r2.stderr)
                self.assertIn("AUTO-INSTALL-RESULT", r2.stdout)
                self.assertIn("Doctor (checks your setup", r2.stdout)
                self.assertNotIn("linkedin-orchestrator", r2.stdout)
                self.assertIn("Use $orchestrator", r2.stdout)
                steps = re.findall(r"^\s+(\d)\. ", r2.stdout.split("Next steps:")[1].split("Try it without")[0], re.M)
                self.assertEqual(steps, sorted(set(steps)), steps)
                self.assertRegex(r2.stdout, r"doctor: (ok|attention|problems)")
                self.assertTrue(os.path.exists(os.path.join(auto_home, "linkedin", "scripts", "chat_app.py")))
                self.assertEqual(count(os.path.join(auto_home, ".codex", "skills")), SKILL_COUNT)
            finally:
                shutil.rmtree(auto_home, ignore_errors=True)
            open(os.path.join(ws, "docs", "brand-profile.md"), "w").write("MINE")
            run("uninstall.ps1", "-Project", ws, "-Tool", "all")
            self.assertEqual(open(os.path.join(ws, "docs", "brand-profile.md")).read(), "MINE")
        finally:
            shutil.rmtree(home, ignore_errors=True)
            shutil.rmtree(os.path.dirname(ws), ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
