"""Tests for runtime/memory_guard.py."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUARD = os.path.join(ROOT, "runtime", "memory_guard.py")


class GuardCase(unittest.TestCase):
    def setUp(self):
        self.ws = tempfile.mkdtemp()
        shutil.copytree(os.path.join(ROOT, "memory"), os.path.join(self.ws, "memory"))
        os.makedirs(os.path.join(self.ws, "docs"))
        shutil.copy(os.path.join(ROOT, "docs", "brand-profile.md"), os.path.join(self.ws, "docs"))
        for d in ("runs", "drafts", "reports", "inbox"):
            os.makedirs(os.path.join(self.ws, d))
            open(os.path.join(self.ws, d, "README.md"), "w").write("keep")

    def tearDown(self):
        shutil.rmtree(self.ws, ignore_errors=True)

    def run_guard(self, *args, stdin="", env=None):
        e = dict(os.environ, **(env or {}))
        return subprocess.run([sys.executable, GUARD, "--workspace", self.ws, *args], input=stdin, capture_output=True, text=True, env=e)

    def reg(self, name):
        return open(os.path.join(self.ws, "memory", name + ".md"), encoding="utf-8").read()


ENTRY = "REGISTER ENTRY\nregister: content-memory\nPost ID: P-001\nDate: 2026-10-05\nTopic/Title: Why onboarding fails | really\nSaves: 12\n"


class Apply(GuardCase):
    def test_allowed_agent_writes_a_verified_row(self):
        r = self.run_guard("apply", "--agent", "learning", stdin=ENTRY)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("P-001", self.reg("content-memory"))
        self.assertIn("Why onboarding fails \\| really", self.reg("content-memory"))
        self.assertTrue(os.listdir(os.path.join(self.ws, "memory", ".history")))

    def test_wrong_agent_is_refused_and_nothing_changes(self):
        before = self.reg("content-memory")
        r = self.run_guard("apply", "--agent", "writing", stdin=ENTRY)
        self.assertEqual(r.returncode, 3)
        self.assertEqual(self.reg("content-memory"), before)

    def test_unknown_column_and_register_are_rejected(self):
        r = self.run_guard("apply", "--agent", "learning", stdin="REGISTER ENTRY\nregister: content-memory\nBogus: x\n")
        self.assertEqual(r.returncode, 2)
        r = self.run_guard("apply", "--agent", "learning", stdin="REGISTER ENTRY\nregister: nope\nA: b\n")
        self.assertEqual(r.returncode, 2)
        r = self.run_guard("apply", "--agent", "learning", stdin="no entry here")
        self.assertEqual(r.returncode, 2)

    def test_duplicate_row_is_skipped(self):
        self.run_guard("apply", "--agent", "learning", stdin=ENTRY)
        r = self.run_guard("apply", "--agent", "learning", stdin=ENTRY)
        self.assertEqual(r.returncode, 0)
        self.assertIn("skipped duplicate", r.stdout)
        self.assertEqual(self.reg("content-memory").count("P-001"), 1)

    def test_row_goes_inside_the_table_not_at_the_end(self):
        r = self.run_guard("apply", "--agent", "experiment", stdin="REGISTER ENTRY\nregister: experiment-register\nExp ID: E-1\nPrimary Variable: hook\n")
        self.assertEqual(r.returncode, 0, r.stderr)
        text = self.reg("experiment-register")
        self.assertLess(text.index("| E-1 |"), text.index("Per-experiment") if "Per-experiment" in text else len(text))

    def test_fenced_input_and_multiple_entries(self):
        stdin = "```\n" + ENTRY + "\nREGISTER ENTRY\nregister: learning-register\nLearning: x\n```\n"
        r = self.run_guard("apply", "--agent", "learning", stdin=stdin)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("2 row(s) written", r.stdout)

    def test_busy_lock_is_reported(self):
        open(os.path.join(self.ws, "memory", ".lock"), "w").write("x")
        r = self.run_guard("apply", "--agent", "learning", stdin=ENTRY, env={"MEMORY_GUARD_LOCK_TIMEOUT": "0.3"})
        self.assertEqual(r.returncode, 5)

    def test_every_register_accepts_its_first_listed_writer(self):
        reg = json.load(open(os.path.join(ROOT, "memory", "registry.json")))
        for name, writers in reg["registers"].items():
            header = open(os.path.join(ROOT, "memory", name + ".md"), encoding="utf-8").read().split("\n")
            col = next(l for l in header if l.startswith("|")).split("|")[1].strip()
            r = self.run_guard("apply", "--agent", writers[0], stdin=f"REGISTER ENTRY\nregister: {name}\n{col}: test\n")
            self.assertEqual(r.returncode, 0, f"{name}: {r.stderr}")


class UndoHistoryCheck(GuardCase):
    def test_undo_restores_previous_content(self):
        before = self.reg("content-memory")
        self.run_guard("apply", "--agent", "learning", stdin=ENTRY)
        r = self.run_guard("undo")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.reg("content-memory"), before)
        self.assertEqual(self.run_guard("undo").returncode, 2)  # nothing left to undo

    def test_history_lists_events(self):
        self.run_guard("apply", "--agent", "learning", stdin=ENTRY)
        out = self.run_guard("history").stdout
        self.assertIn('"op": "apply"', out)

    def test_check_passes_then_detects_damage(self):
        self.assertEqual(self.run_guard("check").returncode, 0)
        p = os.path.join(self.ws, "memory", "content-memory.md")
        open(p, "a", encoding="utf-8").write("| only | two |\n")
        r = self.run_guard("check")
        self.assertEqual(r.returncode, 1)
        self.assertIn("BROKEN", r.stdout)

    def test_registry_command_lists_all_registers(self):
        out = self.run_guard("registry").stdout
        self.assertIn("approval-log", out)
        self.assertIn("brand profile", out)


class ProfileExportForget(GuardCase):
    SECTION = "Voice"

    def test_profile_set_needs_approver_and_allowed_agent(self):
        self.assertEqual(self.run_guard("profile-set", "--section", self.SECTION, "--approved-by", "", stdin="x").returncode, 3)
        self.assertEqual(self.run_guard("profile-set", "--section", self.SECTION, "--approved-by", "Owner", "--agent", "writing", stdin="x").returncode, 3)

    def test_profile_set_replaces_only_that_section_and_can_be_undone(self):
        p = os.path.join(self.ws, "docs", "brand-profile.md")
        before = open(p, encoding="utf-8").read()
        r = self.run_guard("profile-set", "--section", self.SECTION, "--approved-by", "Owner", stdin="- Core voice: plain and direct")
        self.assertEqual(r.returncode, 0, r.stderr)
        after = open(p, encoding="utf-8").read()
        self.assertIn("plain and direct", after)
        self.assertIn("## 3. Audience", after)
        self.assertEqual(self.run_guard("undo").returncode, 0)
        self.assertEqual(open(p, encoding="utf-8").read(), before)

    def test_export_contains_data_but_not_history(self):
        self.run_guard("apply", "--agent", "learning", stdin=ENTRY)
        out = os.path.join(self.ws, "out.zip")
        self.assertEqual(self.run_guard("export", "--out", out).returncode, 0)
        names = zipfile.ZipFile(out).namelist()
        self.assertTrue(any(n.endswith("content-memory.md") for n in names))
        self.assertFalse(any(".history" in n for n in names))

    def test_forget_needs_confirmation_then_clears_rows_and_files(self):
        self.run_guard("apply", "--agent", "learning", stdin=ENTRY)
        open(os.path.join(self.ws, "runs", "2026-10-05-Mon.md"), "w").write("x")
        self.assertEqual(self.run_guard("forget").returncode, 2)
        self.assertIn("P-001", self.reg("content-memory"))
        self.assertEqual(self.run_guard("forget", "--confirm", "DELETE-MY-DATA").returncode, 0)
        self.assertNotIn("P-001", self.reg("content-memory"))
        self.assertFalse(os.path.exists(os.path.join(self.ws, "runs", "2026-10-05-Mon.md")))
        self.assertTrue(os.path.exists(os.path.join(self.ws, "runs", "README.md")))
        self.assertFalse(os.path.exists(os.path.join(self.ws, "memory", ".history")))
        self.assertEqual(self.run_guard("check").returncode, 0)


if __name__ == "__main__":
    unittest.main()
