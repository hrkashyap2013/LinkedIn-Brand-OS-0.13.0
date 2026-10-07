"""Tests for the scheduled-preparation runner and schedule registration (bash), using a stand-in AI tool."""
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASH = shutil.which("bash")


@unittest.skipUnless(BASH and os.name != "nt", "needs bash on macOS/Linux")
class Runner(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.ws = os.path.join(self.tmp, "ws")
        self.env = dict(os.environ, HOME=self.tmp)
        subprocess.run([BASH, os.path.join(ROOT, "install.sh"), "--project", self.ws], capture_output=True, env=self.env, check=True)
        json.dump({"publish_utc_offset": "+05:30", "prep_lead_hours": None,
                   "slots": [{"day": "Mon", "time": "10:00", "role": "Test role A"}, {"day": "Thu", "time": "10:00", "role": "Test role B"}]},
                  open(os.path.join(self.ws, "docs", "schedule.json"), "w"))
        self.prompt = os.path.join(self.tmp, "prompt.txt")
        self.stub = os.path.join(self.tmp, "claude")
        open(self.stub, "w").write(f'#!/usr/bin/env bash\n[ "$1" = "-p" ] || exit 9\nprintf "%s" "$2" > "{self.prompt}"\necho "3 ideas (stub)"\n')
        os.chmod(self.stub, os.stat(self.stub).st_mode | stat.S_IEXEC)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_sh(self, script, *args, **env):
        return subprocess.run([BASH, os.path.join(self.ws, "scripts", script), *args], capture_output=True, text=True, cwd=self.ws,
                              env=dict(self.env, **env))

    def test_run_substitutes_everything_and_names_new_agents(self):
        r = self.run_sh("run-scheduled.sh", "--slot", "Mon", CLAUDE_BIN=self.stub)
        self.assertEqual(r.returncode, 0, r.stderr)
        text = open(self.prompt).read()
        self.assertIn("Test role A", text)
        self.assertIn("10:00 (UTC+05:30)", text)
        self.assertNotIn("{{", text)
        self.assertIn("idea-generation", text)
        self.assertNotRegex(text, r"linkedin-|\bA\d\d\b")
        out = [f for f in os.listdir(os.path.join(self.ws, "runs")) if f.endswith("-Mon.md")]
        self.assertEqual(len(out), 1)
        self.assertIn("Nothing has been drafted", open(os.path.join(self.ws, "runs", out[0])).read())

    def test_second_run_is_skipped_and_force_redoes(self):
        self.run_sh("run-scheduled.sh", "--slot", "Mon", CLAUDE_BIN=self.stub)
        self.assertIn("Already prepared", self.run_sh("run-scheduled.sh", "--slot", "Mon", CLAUDE_BIN=self.stub).stdout)
        self.assertIn("Prepared:", self.run_sh("run-scheduled.sh", "--slot", "Mon", "--force", CLAUDE_BIN=self.stub).stdout)

    def test_missing_tool_writes_a_failed_file(self):
        r = self.run_sh("run-scheduled.sh", "--slot", "Thu", CLAUDE_BIN="definitely-not-installed")
        self.assertEqual(r.returncode, 1)
        self.assertTrue(any(f.endswith("Thu.FAILED.md") for f in os.listdir(os.path.join(self.ws, "runs"))))

    def _phone_sink(self):
        got = []

        class H(BaseHTTPRequestHandler):
            def do_POST(h):
                got.append(json.loads(h.rfile.read(int(h.headers["Content-Length"])).decode("utf-8")))
                h.send_response(200)
                h.end_headers()

            def log_message(h, *a):
                pass

        srv = HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        with open(os.path.join(self.ws, "docs", "settings.json"), "w") as fh:
            json.dump({"notifications": {"desktop": False, "phone": True, "phone_server": "http://127.0.0.1:%d" % srv.server_port}}, fh)
        with open(os.path.join(self.ws, "config.local.json"), "w") as fh:
            json.dump({"ntfy_topic": "lba-runner-test"}, fh)
        return got

    def test_run_sends_a_generic_push_when_prepared_and_never_the_idea_text(self):
        got = self._phone_sink()
        r = self.run_sh("run-scheduled.sh", "--slot", "Mon", CLAUDE_BIN=self.stub)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]["topic"], "lba-runner-test")
        self.assertIn("Mon", got[0]["message"])
        self.assertNotIn("stub", json.dumps(got[0]))       # the stand-in tool printed "3 ideas (stub)"; none of it may leave the machine

    def test_failed_run_sends_a_failure_push_and_still_fails_normally(self):
        got = self._phone_sink()
        r = self.run_sh("run-scheduled.sh", "--slot", "Thu", CLAUDE_BIN="definitely-not-installed")
        self.assertEqual(r.returncode, 1)
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]["title"], "Preparation failed")

    def test_unreachable_notification_server_never_breaks_a_run(self):
        with open(os.path.join(self.ws, "docs", "settings.json"), "w") as fh:
            json.dump({"notifications": {"phone": True, "phone_server": "http://127.0.0.1:9"}}, fh)
        with open(os.path.join(self.ws, "config.local.json"), "w") as fh:
            json.dump({"ntfy_topic": "x"}, fh)
        r = self.run_sh("run-scheduled.sh", "--slot", "Mon", CLAUDE_BIN=self.stub)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("FAILED", open(os.path.join(self.ws, "runs", "scheduler.log")).read())

    def test_notifications_can_be_switched_off_for_a_run(self):
        got = self._phone_sink()
        self.run_sh("run-scheduled.sh", "--slot", "Mon", CLAUDE_BIN=self.stub, LBA_NOTIFY="0")
        self.assertEqual(got, [])

    def test_registration_refuses_without_lead_time(self):
        r = self.run_sh("register-schedule.sh", "--dry-run")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("not guessed", r.stderr + r.stdout)

    def test_registration_times_are_converted_correctly(self):
        r = self.run_sh("register-schedule.sh", "--lead-hours", "12", "--dry-run", TZ="UTC")
        self.assertEqual(r.returncode, 0, r.stderr)
        # Mon 10:00 at +05:30 is 04:30 UTC, minus 12h is Sunday 16:30 UTC; Thursday becomes Wednesday 16:30
        self.assertIn("30 16 * * 0 ", r.stdout)
        self.assertIn("30 16 * * 3 ", r.stdout)

    def test_crontab_roundtrip_keeps_other_jobs(self):
        store = os.path.join(self.tmp, "cron.store")
        open(store, "w").write("0 5 * * * /usr/bin/other-job\n")
        fake = os.path.join(self.tmp, "fakecron")
        open(fake, "w").write(f'#!/usr/bin/env bash\ncase "$1" in -l) cat "{store}" ;; -) cat > "{store}" ;; esac\n')
        os.chmod(fake, os.stat(fake).st_mode | stat.S_IEXEC)
        self.assertEqual(self.run_sh("register-schedule.sh", "--lead-hours", "12", CRONTAB_CMD=fake, TZ="UTC").returncode, 0)
        text = open(store).read()
        self.assertIn("other-job", text)
        self.assertEqual(text.count("run-scheduled"), 2)
        self.run_sh("register-schedule.sh", "--lead-hours", "12", CRONTAB_CMD=fake, TZ="UTC")
        self.assertEqual(open(store).read().count("run-scheduled"), 2)  # no duplicates
        self.run_sh("register-schedule.sh", "--remove", CRONTAB_CMD=fake)
        text = open(store).read()
        self.assertIn("other-job", text)
        self.assertNotIn("run-scheduled", text)


class Metrics(unittest.TestCase):
    def test_dashboard_values(self):
        tmp = tempfile.mkdtemp()
        try:
            csv = os.path.join(tmp, "m.csv")
            open(csv, "w").write("Post ID,Date,Title,Impressions,Reactions,Comments,Reposts,Saves,Sends,Profile views,Followers gained\n"
                                 'p1,2026-09-01,Alpha,"1,000",20,4,2,10,3,40,5\np2,2026-09-03,Beta,2000,30,6,4,20,6,80,8\np3,2026-09-05,Gamma,500,5,1,0,0,0,0,0\n')
            r = subprocess.run([sys.executable, os.path.join(ROOT, "runtime", "metrics.py"), csv, "--map", os.path.join(tmp, "none"), "--out", tmp],
                               capture_output=True, text=True, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("Median followers per 1,000 impressions: 4.00", r.stdout)   # 5.0, 4.0, 0.0
            self.assertIn("Median profile-to-follow proxy %: 11.25", r.stdout)         # 12.5 and 10.0; zero-view post excluded
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
