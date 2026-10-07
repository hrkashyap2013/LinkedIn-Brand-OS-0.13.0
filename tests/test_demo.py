"""Tests for demo mode: the sample workspace builds safely and runs the whole real pipeline with the stand-in AI."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

from tests.helpers import rtext

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Demo(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.dest = os.path.join(self.tmp, "demo")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def build(self, dest=None):
        return subprocess.run([sys.executable, os.path.join(ROOT, "runtime", "demo.py"), "--dir", dest or self.dest, "--build-only"], capture_output=True, text=True)

    def test_builds_a_complete_blank_sample_workspace(self):
        r = self.build()
        self.assertEqual(r.returncode, 0, r.stderr)
        for f in ("docs/brand-profile.md", "docs/settings.json", "memory/approval-log.md", "memory/registry.json", "scripts/chat_app.py", "scripts/app/app.js",
                  "scripts/demo_ai.py", "prompts/governance.md", ".claude/agents/governance.md", ".lba-demo"):
            self.assertTrue(os.path.exists(os.path.join(self.dest, f)), f)
        self.assertNotIn("| A-", rtext(os.path.join(self.dest, "memory", "approval-log.md")))      # registers start empty
        self.assertIn("Brightpath", rtext(os.path.join(self.dest, "docs", "brand-profile.md")))

    def test_it_refuses_to_touch_a_folder_that_is_not_a_demo(self):
        os.makedirs(self.dest)
        with open(os.path.join(self.dest, "precious.txt"), "w") as fh:
            fh.write("mine")
        r = self.build()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("not a demo folder", r.stderr + r.stdout)
        self.assertEqual(os.listdir(self.dest), ["precious.txt"])

    def test_a_second_run_keeps_the_demos_own_history(self):
        self.build()
        log = os.path.join(self.dest, "memory", "approval-log.md")
        with open(log, "a") as fh:
            fh.write("| keep-me |\n")
        self.build()
        self.assertIn("keep-me", rtext(log))

    def test_it_never_uses_the_real_workspace_or_the_users_profile(self):
        self.build()
        self.assertNotIn("kashyap", rtext(os.path.join(self.dest, "docs", "brand-profile.md")).lower())

    def test_the_built_demo_runs_the_terminal_pipeline(self):
        self.build()
        env = dict(os.environ, LBA_BROWSER="")
        script = "\n".join([":new", ":ideas", ":pick 1", "APPROVE", ":draft", ":previews", ":pickvisual 1", "APPROVE", ":render", ":check", ":approve content", "APPROVE",
                            ":approve package", "APPROVE", ":build", ":status", ":quit"]) + "\n"
        r = subprocess.run([sys.executable, os.path.join(self.dest, "scripts", "chat_cli.py"), "--workspace", self.dest, "--demo"], input=script, capture_output=True, text=True, env=env, timeout=120)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("DEMO MODE", r.stdout)
        self.assertIn("Package built", r.stdout)
        self.assertEqual(r.stdout.count("Decision") >= 4, True)
        pkg = os.path.join(self.dest, "exports", "ready-to-paste")
        self.assertTrue(os.path.exists(os.path.join(pkg, os.listdir(pkg)[0], "PACKAGE.md")))


if __name__ == "__main__":
    unittest.main()
