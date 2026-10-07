"""Tests for notify.py: loopback push server, desktop command building, privacy and failure behaviour."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "runtime"))
import notify  # noqa: E402


class Sink(BaseHTTPRequestHandler):
    received = []
    status = 200

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        Sink.received.append(json.loads(body.decode("utf-8")))
        self.send_response(Sink.status)
        self.end_headers()
        self.wfile.write(b"{}")

    def log_message(self, *a):
        pass


def make_workspace(desktop=False, phone=False, topic="lba-test-topic", server="http://127.0.0.1:1"):
    ws = tempfile.mkdtemp()
    os.makedirs(os.path.join(ws, "docs"))
    with open(os.path.join(ws, "docs", "settings.json"), "w") as fh:
        json.dump({"notifications": {"desktop": desktop, "phone": phone, "phone_server": server}}, fh)
    if topic:
        with open(os.path.join(ws, "config.local.json"), "w") as fh:
            json.dump({"ntfy_topic": topic}, fh)
    return ws


class Phone(unittest.TestCase):
    def setUp(self):
        Sink.received, Sink.status = [], 200
        self.srv = HTTPServer(("127.0.0.1", 0), Sink)
        self.url = "http://127.0.0.1:%d" % self.srv.server_port
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.ws = make_workspace(phone=True, server=self.url)

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        shutil.rmtree(self.ws, ignore_errors=True)

    def test_push_message_is_sent_as_utf8_json(self):
        res = notify.notify(self.ws, "prepared", message="Ideen f\u00fcr Montag sind bereit \u2713")
        self.assertEqual([(c, ok) for c, ok, _ in res], [("phone", True)])
        got = Sink.received[0]
        self.assertEqual(got["topic"], "lba-test-topic")
        self.assertEqual(got["message"], "Ideen f\u00fcr Montag sind bereit \u2713")
        self.assertEqual(got["title"], "Ideas are ready")

    def test_control_characters_and_length_are_cleaned(self):
        notify.notify(self.ws, "failed", title="T\x00\x07itle", message="line\x1b[31m " + "x" * 1000)
        got = Sink.received[0]
        self.assertNotRegex(got["title"] + got["message"], r"[\x00-\x08\x1b]")
        self.assertLessEqual(len(got["message"]), 300)

    def test_failed_delivery_is_reported_not_raised(self):
        Sink.status = 500
        res = notify.notify(self.ws, "prepared")
        self.assertFalse(res[0][1])
        self.assertIn("500", res[0][2])

    def test_cli_exit_codes(self):
        run = lambda *a: subprocess.run([sys.executable, os.path.join(ROOT, "runtime", "notify.py"), "--workspace", self.ws, *a], capture_output=True, text=True)
        self.assertEqual(run("--event", "test").returncode, 0)
        Sink.status = 500
        self.assertEqual(run("--event", "test").returncode, 1)       # the wizard needs to hear about it
        self.assertEqual(run("--event", "prepared").returncode, 0)   # a scheduled run must never break
        self.assertNotIn("lba-test-topic", run("--event", "test", "--dry-run").stdout)

    def test_dry_run_sends_nothing(self):
        notify.notify(self.ws, "prepared", dry_run=True)
        self.assertEqual(Sink.received, [])


class Rules(unittest.TestCase):
    def test_nothing_enabled_is_a_quiet_noop(self):
        ws = make_workspace()
        try:
            self.assertEqual(notify.notify(ws, "prepared"), [])
            r = subprocess.run([sys.executable, os.path.join(ROOT, "runtime", "notify.py"), "--workspace", ws, "--event", "prepared"], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0)
            r = subprocess.run([sys.executable, os.path.join(ROOT, "runtime", "notify.py"), "--workspace", ws, "--event", "test"], capture_output=True, text=True)
            self.assertEqual(r.returncode, 1)
        finally:
            shutil.rmtree(ws, ignore_errors=True)

    def test_phone_without_topic_or_with_insecure_server_is_refused(self):
        ws = make_workspace(phone=True, topic="", server="https://ntfy.sh")
        try:
            self.assertIn("no phone topic", notify.notify(ws, "test")[0][2])
        finally:
            shutil.rmtree(ws, ignore_errors=True)
        self.assertFalse(notify.valid_server("http://ntfy.example.com"))
        self.assertFalse(notify.valid_server("ftp://x"))
        self.assertTrue(notify.valid_server("https://ntfy.example.com"))
        self.assertTrue(notify.valid_server("http://127.0.0.1:8080"))
        ws = make_workspace(phone=True, server="http://ntfy.example.com")
        try:
            self.assertFalse(notify.notify(ws, "test")[0][1])
        finally:
            shutil.rmtree(ws, ignore_errors=True)

    def test_topic_comes_from_the_local_file_not_settings(self):
        ws = make_workspace(phone=True, topic="secret-topic-value")
        try:
            with open(os.path.join(ws, "docs", "settings.json")) as fh:
                self.assertNotIn("secret-topic-value", fh.read())
            self.assertEqual(notify.load_config(ws)["topic"], "secret-topic-value")
        finally:
            shutil.rmtree(ws, ignore_errors=True)

    def test_default_texts_are_generic(self):
        for event, (title, msg) in notify.EVENTS.items():
            self.assertLess(len(msg), 120, event)
            self.assertNotRegex(msg, r"(?i)idea \d|draft:|impressions|\d{3,}")

    def test_desktop_command_never_goes_through_a_shell_and_keeps_text_as_one_argument(self):
        nasty = 'quote " and $(touch /tmp/pwned) and `x` ; & |'
        for system in ("Darwin", "Linux", "Windows"):
            orig = (notify.platform.system, notify.shutil.which)
            notify.platform.system = lambda s=system: s
            notify.shutil.which = lambda name: "/usr/bin/" + name
            try:
                argv, why = notify.desktop_command("Title", nasty)
            finally:
                notify.platform.system, notify.shutil.which = orig
            self.assertIsNone(why, system)
            self.assertIsInstance(argv, list)
            if system == "Windows":
                self.assertNotIn(nasty, " ".join(argv))   # text is base64-encoded into the script
                self.assertIn("FromBase64String", argv[-1])
            else:
                self.assertIn(nasty, argv)               # one list item, never interpolated into a command line
        self.assertFalse(os.path.exists("/tmp/pwned"))

    def test_missing_desktop_tool_is_reported(self):
        orig = (notify.platform.system, notify.shutil.which)
        notify.platform.system = lambda: "Linux"
        notify.shutil.which = lambda name: None
        try:
            ok, why = notify.send_desktop("T", "M")
        finally:
            notify.platform.system, notify.shutil.which = orig
        self.assertFalse(ok)
        self.assertIn("notify-send", why)


if __name__ == "__main__":
    unittest.main()
