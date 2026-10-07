"""Tests for results-check reminders: due dates, catching up after the computer was off, privacy of the message."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from tests.helpers import jdump, jload

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "runtime"))
import reminders as rm  # noqa: E402


class Reminders(unittest.TestCase):
    def setUp(self):
        self.ws = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.ws, "docs"))
        self.t0 = datetime(2026, 10, 6, 9, 0, tzinfo=timezone.utc)

    def tearDown(self):
        shutil.rmtree(self.ws, ignore_errors=True)

    def test_due_dates_follow_the_windows(self):
        items = rm.add(self.ws, "P-20261006-01", rm.parse_windows("24h,72h,7d,90d"), self.t0.isoformat())
        due = {i["window"]: rm.parse_time(i["due_at"]) for i in items}
        self.assertEqual(due["24h"], self.t0 + timedelta(hours=24))
        self.assertEqual(due["72h"], self.t0 + timedelta(days=3))
        self.assertEqual(due["7d"], self.t0 + timedelta(days=7))
        self.assertEqual(due["90d"], self.t0 + timedelta(days=90))

    def test_adding_twice_does_not_duplicate(self):
        rm.add(self.ws, "P-20261006-01", ["24h"], self.t0.isoformat())
        self.assertEqual(rm.add(self.ws, "P-20261006-01", ["24h", "72h"], self.t0.isoformat())[0]["window"], "72h")
        self.assertEqual(len(rm.load(self.ws)["items"]), 2)

    def test_nothing_fires_early(self):
        rm.add(self.ws, "P-20261006-01", ["24h"], self.t0.isoformat())
        self.assertEqual(rm.tick(self.ws, self.t0 + timedelta(hours=23, minutes=59), send=False), [])

    def test_a_missed_reminder_fires_at_the_next_tick_and_says_it_was_late(self):
        rm.add(self.ws, "P-20261006-01", ["24h", "72h"], self.t0.isoformat())
        fired = rm.tick(self.ws, self.t0 + timedelta(days=5), send=False)    # computer was off for days
        self.assertEqual([i["window"] for i in fired], ["24h", "72h"])
        self.assertGreater(fired[0]["late_hours"], 90)
        self.assertIn("computer was off", rm.message_for(fired[0], fired[0]["late_hours"]))
        self.assertNotIn("computer was off", rm.message_for(fired[0], 0.5))
        self.assertEqual(rm.tick(self.ws, self.t0 + timedelta(days=6), send=False), [])    # fired once only

    def test_fired_reminders_stay_on_the_due_list_until_marked_done(self):
        rm.add(self.ws, "P-20261006-01", ["24h"], self.t0.isoformat())
        rm.tick(self.ws, self.t0 + timedelta(days=2), send=False)
        self.assertEqual(len(rm.due(self.ws, self.t0 + timedelta(days=3))), 1)
        self.assertEqual(rm.mark(self.ws, "P-20261006-01", "24h", "done"), 1)
        self.assertEqual(rm.due(self.ws, self.t0 + timedelta(days=3)), [])

    def test_cancel_stops_future_reminders(self):
        rm.add(self.ws, "P-20261006-01", ["24h", "7d"], self.t0.isoformat())
        rm.mark(self.ws, "P-20261006-01", None, "cancelled")
        self.assertEqual(rm.tick(self.ws, self.t0 + timedelta(days=30), send=False), [])

    def test_bad_input_is_rejected(self):
        for bad in ("2h", "", "24h,banana"):
            with self.assertRaises(ValueError):
                rm.parse_windows(bad)
        with self.assertRaises(ValueError):
            rm.add(self.ws, "bad id/../x", ["24h"])

    def test_naive_and_z_times_parse(self):
        self.assertEqual(rm.parse_time("2026-10-06T09:00:00Z"), self.t0)
        self.assertIsNotNone(rm.parse_time("2026-10-06T09:00:00").tzinfo)

    def test_notification_is_generic_and_sent_to_the_phone_channel(self):
        import threading
        from http.server import BaseHTTPRequestHandler, HTTPServer
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
        jdump({"notifications": {"phone": True, "phone_server": "http://127.0.0.1:%d" % srv.server_port}}, os.path.join(self.ws, "docs", "settings.json"))
        jdump({"ntfy_topic": "t-reminder"}, os.path.join(self.ws, "config.local.json"))
        rm.add(self.ws, "P-20261006-01", ["24h"], self.t0.isoformat())
        fired = rm.tick(self.ws, self.t0 + timedelta(hours=25))
        self.assertTrue(fired[0]["delivered"])
        self.assertEqual(len(got), 1)
        self.assertIn("P-20261006-01", got[0]["message"])
        self.assertIn("/metrics", got[0]["message"])

    def test_no_channel_still_records_that_it_fired(self):
        rm.add(self.ws, "P-20261006-01", ["24h"], self.t0.isoformat())
        fired = rm.tick(self.ws, self.t0 + timedelta(hours=25))
        self.assertFalse(fired[0]["delivered"])
        self.assertEqual(fired[0]["status"], "fired")

    def test_cli_round_trip(self):
        run = lambda *a: subprocess.run([sys.executable, os.path.join(ROOT, "runtime", "reminders.py"), "--workspace", self.ws, *a], capture_output=True, text=True)
        self.assertEqual(run("add", "--post-id", "P-20261006-01", "--windows", "24h", "--live-at", self.t0.isoformat()).returncode, 0)
        r = run("tick", "--now", (self.t0 + timedelta(days=2)).isoformat(), "--no-notify")
        self.assertIn("1 fired", r.stdout)
        self.assertIn("/metrics", run("due").stdout)
        self.assertEqual(run("done", "--post-id", "P-20261006-01", "--window", "24h").returncode, 0)
        self.assertIn("No results checks", run("due").stdout)
        self.assertEqual(run("add", "--post-id", "P-20261006-01", "--windows", "5h").returncode, 2)

    def test_reply_checks_are_a_separate_kind_with_their_own_windows_and_message(self):
        items = rm.add(self.ws, "P-20261006-01", rm.parse_windows("1h,6h", "reply"), self.t0.isoformat(), "reply")
        self.assertEqual([(i["kind"], i["window"]) for i in items], [("reply", "1h"), ("reply", "6h")])
        self.assertEqual(rm.parse_time(items[1]["due_at"]), self.t0 + timedelta(hours=6))
        rm.add(self.ws, "P-20261006-01", ["24h"], self.t0.isoformat())              # a results 24h check does not clash with a reply 24h check
        rm.add(self.ws, "P-20261006-01", ["24h"], self.t0.isoformat(), "reply")
        self.assertEqual(len(rm.load(self.ws)["items"]), 4)
        fired = rm.tick(self.ws, self.t0 + timedelta(hours=7), send=False)
        self.assertEqual([i["window"] for i in fired], ["1h", "6h"])
        self.assertIn("/reply", rm.message_for(fired[0], 0.2))
        self.assertNotIn("/metrics", rm.message_for(fired[0], 0.2))
        self.assertIn("/metrics", rm.message_for({"post_id": "P-1", "window": "24h"}, 0.2))      # old items without a kind are results checks

    def test_a_missed_reply_check_still_arrives_and_stays_until_marked_done_by_kind(self):
        rm.add(self.ws, "P-20261006-01", ["24h"], self.t0.isoformat())
        rm.add(self.ws, "P-20261006-01", ["24h"], self.t0.isoformat(), "reply")
        rm.tick(self.ws, self.t0 + timedelta(days=3), send=False)
        self.assertEqual(sorted(rm.kind_of(i) for i in rm.due(self.ws, self.t0 + timedelta(days=3))), ["reply", "results"])
        self.assertEqual(rm.mark(self.ws, "P-20261006-01", "24h", "done", "reply"), 1)
        left = rm.due(self.ws, self.t0 + timedelta(days=3))
        self.assertEqual([rm.kind_of(i) for i in left], ["results"])

    def test_reply_windows_are_validated_separately(self):
        with self.assertRaises(ValueError):
            rm.parse_windows("7d", "reply")
        with self.assertRaises(ValueError):
            rm.parse_windows("3h", "results")
        with self.assertRaises(ValueError):
            rm.add(self.ws, "P-20261006-01", ["1h"], None, "nonsense")

    def test_cli_reply_kind_defaults_and_done(self):
        run = lambda *a: subprocess.run([sys.executable, os.path.join(ROOT, "runtime", "reminders.py"), "--workspace", self.ws, *a], capture_output=True, text=True)
        r = run("add", "--post-id", "P-20261006-01", "--kind", "reply", "--live-at", self.t0.isoformat())
        self.assertIn("2 reply reminder(s)", r.stdout)
        run("tick", "--now", (self.t0 + timedelta(hours=10)).isoformat(), "--no-notify")
        self.assertIn("/reply", run("due").stdout)
        self.assertEqual(run("done", "--post-id", "P-20261006-01", "--window", "1h", "--kind", "reply").returncode, 0)

    def test_stale_lock_is_cleared(self):
        os.makedirs(os.path.join(self.ws, "runs"))
        lock = os.path.join(self.ws, "runs", ".reminders.lock")
        open(lock, "w").close()
        old = os.path.getmtime(lock) - 600
        os.utime(lock, (old, old))
        rm.add(self.ws, "P-20261006-01", ["24h"], self.t0.isoformat())     # must not hang
        self.assertTrue(os.path.exists(rm.store_path(self.ws)))


if __name__ == "__main__":
    unittest.main()
