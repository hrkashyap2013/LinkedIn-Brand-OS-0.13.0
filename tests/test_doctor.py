"""The doctor: honest statuses, a fix for every problem, no AI call unless asked, and the right exit codes."""
import json
import os
import shutil
import subprocess
import sys
import unittest

from tests.helpers import jdump, make_workspace, wtext

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "runtime"))
import doctor  # noqa: E402


def by_title(res, title):
    return next(r for r in res if r["title"].startswith(title))


class Doctor(unittest.TestCase):
    def setUp(self):
        self.ws = make_workspace({"setup_completed": True, "language": "English", "run_tool": "claude"})
        self.saved = {k: os.environ.get(k) for k in ("CLAUDE_BIN", "CODEX_BIN", "LBA_AI_CMD", "LBA_BROWSER", "PUBLORA_API_KEY")}
        for k in self.saved:
            os.environ.pop(k, None)
        os.environ["CLAUDE_BIN"] = "definitely-not-installed"

    def tearDown(self):
        for k, v in self.saved.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
        shutil.rmtree(self.ws, ignore_errors=True)

    def test_every_warning_and_failure_comes_with_a_fix(self):
        res = doctor.run_checks(self.ws)
        for r in res:
            if r["status"] in ("WARN", "FAIL"):
                self.assertTrue(r["fix"], r["title"])
        self.assertEqual(by_title(res, "AI tool")["status"], "FAIL")
        self.assertIn("demo.py", by_title(res, "AI tool")["fix"])

    def test_a_missing_core_folder_is_a_failure_and_stops_early(self):
        shutil.rmtree(os.path.join(self.ws, "memory"))
        res = doctor.run_checks(self.ws)
        self.assertEqual(by_title(res, "Workspace folders")["status"], "FAIL")
        self.assertLessEqual(len(res), 3)

    def test_setup_and_profile_are_reported_honestly(self):
        res = doctor.run_checks(self.ws)
        self.assertEqual(by_title(res, "Setup questions")["status"], "OK")
        self.assertEqual(by_title(res, "Brand profile")["status"], "WARN")             # the shipped template is blank
        jdump({"setup_completed": False}, os.path.join(self.ws, "docs", "settings.json"))
        self.assertEqual(by_title(doctor.run_checks(self.ws), "Setup questions")["status"], "WARN")

    @unittest.skipIf(os.name == "nt", "uses a POSIX shell script as the stand-in tool")
    def test_a_found_tool_is_ok_and_a_custom_command_is_noted(self):
        stub = os.path.join(self.ws, "claude")
        wtext(stub, "#!/bin/sh\necho 'claude 9.9.9'\n")
        os.chmod(stub, 0o755)
        os.environ["CLAUDE_BIN"] = stub
        r = by_title(doctor.run_checks(self.ws), "AI tool")
        self.assertEqual(r["status"], "OK")
        self.assertIn("9.9.9", r["detail"])
        os.environ["CLAUDE_BIN"] = "nope"
        os.environ["LBA_AI_CMD"] = json.dumps([sys.executable, "-c", "print(1)"])
        self.assertEqual(by_title(doctor.run_checks(self.ws), "AI tool")["status"], "INFO")

    def test_a_windows_batch_shim_is_a_warning_with_a_fix(self):
        """Works on every system: the tool lookup is replaced, so no real file is needed."""
        import chat_core
        saved = (doctor.shutil.which, chat_core.is_batch_shim)
        doctor.shutil.which = lambda name, *a, **k: "C:\\npm\\claude.cmd"
        chat_core.is_batch_shim = lambda exe, system=None: str(exe).lower().endswith(".cmd")
        try:
            r = by_title(doctor.run_checks(self.ws), "AI tool")
        finally:
            doctor.shutil.which, chat_core.is_batch_shim = saved
        self.assertEqual(r["status"], "WARN")
        self.assertIn("batch shim", r["detail"])
        self.assertIn("LBA_ALLOW_CMD_SHIM", r["fix"])
        self.assertIn("CLAUDE_BIN", r["fix"])

    def test_no_ai_request_is_made_unless_asked(self):
        marker = os.path.join(self.ws, "called.txt")
        os.environ["LBA_AI_CMD"] = json.dumps([sys.executable, "-c", "open(%r, 'w').write('x'); print('OK')" % marker])
        doctor.run_checks(self.ws)
        self.assertFalse(os.path.exists(marker))
        res = doctor.run_checks(self.ws, test_ai=True)
        self.assertTrue(os.path.exists(marker))
        self.assertEqual(by_title(res, "AI test request")["status"], "OK")
        os.environ["LBA_AI_CMD"] = json.dumps([sys.executable, "-c", "import sys; sys.stderr.write('no plan'); sys.exit(2)"])
        bad = by_title(doctor.run_checks(self.ws, test_ai=True), "AI test request")
        self.assertEqual(bad["status"], "FAIL")
        self.assertIn("no plan", bad["detail"])

    def test_notification_and_auto_post_settings_are_checked(self):
        jdump({"setup_completed": True, "notifications": {"phone": True}, "auto_post": {"provider": "publora", "enabled": True}}, os.path.join(self.ws, "docs", "settings.json"))
        res = doctor.run_checks(self.ws)
        self.assertEqual(by_title(res, "Phone push")["status"], "WARN")
        self.assertEqual(by_title(res, "Auto-post add-on")["status"], "WARN")
        jdump({"ntfy_topic": "t"}, os.path.join(self.ws, "config.local.json"))
        os.environ["PUBLORA_API_KEY"] = "k"
        res = doctor.run_checks(self.ws)
        self.assertEqual(by_title(res, "Phone push")["status"], "OK")
        self.assertEqual(by_title(res, "Auto-post add-on")["status"], "OK")

    @unittest.skipIf(os.name == "nt", "POSIX file modes")
    def test_a_world_readable_private_file_is_flagged(self):
        path = os.path.join(self.ws, "config.local.json")
        jdump({"ntfy_topic": "t"}, path)
        os.chmod(path, 0o644)
        self.assertEqual(by_title(doctor.run_checks(self.ws), "Private file")["status"], "WARN")
        os.chmod(path, 0o600)
        self.assertFalse([r for r in doctor.run_checks(self.ws) if r["title"].startswith("Private file")])

    def test_broken_memory_is_a_failure(self):
        path = os.path.join(self.ws, "memory", "approval-log.md")
        wtext(path, "not a register at all")
        self.assertEqual(by_title(doctor.run_checks(self.ws), "Memory registers")["status"], "FAIL")

    def test_command_line_exit_codes_and_json(self):
        run = lambda *a: subprocess.run([sys.executable, os.path.join(self.ws, "scripts", "doctor.py"), "--workspace", self.ws, *a], capture_output=True, text=True,
                                        env=dict(os.environ))
        r = run()
        self.assertEqual(r.returncode, 1)                       # no AI tool here
        self.assertIn("fix:", r.stdout)
        data = json.loads(run("--json").stdout)
        self.assertTrue(all({"status", "title", "detail", "fix"} <= set(x) for x in data))
        os.environ["LBA_AI_CMD"] = json.dumps([sys.executable, "-c", "print(1)"])
        self.assertEqual(run().returncode, 0)


if __name__ == "__main__":
    unittest.main()
