"""The optional Publora add-on: off by default, every gate in order, and no way to send twice or send without the typed confirmation."""
import datetime
import json
import os
import shutil
import subprocess
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from tests.helpers import jdump, jload, make_workspace, rtext

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "runtime"))
import approvals  # noqa: E402
import package_builder as pb  # noqa: E402
import postkit  # noqa: E402
import publish_publora as pp  # noqa: E402
import visual_engine as ve  # noqa: E402

TEXT = "Most weekly reviews fail in week 3.\n\nBecause nobody decided what the review is for.\n"
KEY = "sk_test_do_not_leak_0123456789"


class Fake(BaseHTTPRequestHandler):
    calls = []
    create_status = 200
    connections = {"connections": [{"platformId": "linkedin-abc123"}, {"platformId": "x-777"}]}

    def _body(self):
        n = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(n).decode()) if n else None

    def _reply(self, status, obj):
        raw = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        Fake.calls.append(("GET", self.path, self.headers.get("x-publora-key"), None))
        self._reply(200, Fake.connections)

    def do_POST(self):
        body = self._body()
        Fake.calls.append(("POST", self.path, self.headers.get("x-publora-key"), body))
        if Fake.create_status >= 400:
            self._reply(Fake.create_status, {"error": "nope " + str(self.headers.get("x-publora-key"))})
        else:
            self._reply(Fake.create_status, {"postGroupId": "pg-1", "status": "scheduled"})

    def log_message(self, *a):
        pass


class Base(unittest.TestCase):
    def setUp(self):
        Fake.calls, Fake.create_status = [], 200
        Fake.connections = {"connections": [{"platformId": "linkedin-abc123"}, {"platformId": "x-777"}]}
        self.srv = HTTPServer(("127.0.0.1", 0), Fake)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.saved = {k: os.environ.get(k) for k in ("PUBLORA_API_KEY", "PUBLORA_BASE_URL", "PUBLORA_PLATFORM_ID", "LBA_BROWSER")}
        os.environ["PUBLORA_BASE_URL"] = "http://127.0.0.1:%d" % self.srv.server_port
        os.environ["PUBLORA_API_KEY"] = KEY
        os.environ.pop("PUBLORA_PLATFORM_ID", None)
        os.environ["LBA_BROWSER"] = ""
        self.ws = make_workspace({"users": ["Asha"], "setup_completed": True, "auto_post": {"provider": "publora", "enabled": True}})
        self.id = postkit.new_post(self.ws, "Why reviews stick", "Utility")

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        for k, v in self.saved.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
        shutil.rmtree(self.ws, ignore_errors=True)

    def approved_and_built(self, with_visual=True):
        postkit.save_text(self.ws, self.id, TEXT)
        postkit.set_fields(self.ws, self.id, {"idea": {"title": "Reviews need a purpose", "angle": "one job"}, "suggested_time": "Tue 08:00", "first_comment": "A question?"})
        postkit.save_visual_spec(self.ws, self.id, ve.EXAMPLES["process_flow"])
        postkit.render_final(self.ws, self.id, png=False)
        for d, w in ((1, "idea"), (2, "visual"), (3, "content"), (4, "package")):
            approvals.record(self.ws, self.id, d, w, "app")
        pb.build(self.ws, self.id, track=False)

    def when(self, minutes=60):
        return (datetime.datetime.now().astimezone() + datetime.timedelta(minutes=minutes)).isoformat(timespec="seconds")


class Gates(Base):
    def test_off_by_default_in_the_shipped_template(self):
        self.assertEqual(jload(os.path.join(ROOT, "docs", "settings.json"))["auto_post"], {"provider": "publora", "enabled": False})

    def test_switched_off_blocks_everything_even_with_a_key(self):
        self.approved_and_built()
        jdump({"auto_post": {"provider": "publora", "enabled": False}}, os.path.join(self.ws, "docs", "settings.json"))
        pre = pp.preflight(self.ws, self.id, "draft", media_url="https://img.example.com/a.png")
        self.assertFalse(pre["ok"])
        self.assertTrue(any("Auto-post is off" in p for p in pre["problems"]))
        with self.assertRaises(pp.AutopostError):
            pp.send(self.ws, self.id, "draft", media_url="https://img.example.com/a.png", confirm="PUBLISH")
        self.assertEqual(Fake.calls, [])

    def test_no_key_no_send(self):
        self.approved_and_built()
        os.environ.pop("PUBLORA_API_KEY")
        self.assertTrue(any("PUBLORA_API_KEY" in p for p in pp.preflight(self.ws, self.id, "draft", media_url="https://i.example.com/a.png")["problems"]))

    def test_needs_all_four_decisions_to_match_and_a_current_package(self):
        postkit.save_text(self.ws, self.id, TEXT)
        pre = pp.preflight(self.ws, self.id, "draft", text_only=True)
        self.assertFalse(pre["ok"])
        self.assertTrue(any("Decision 1 is missing" in p for p in pre["problems"]))
        self.approved_and_built()
        self.assertTrue(pp.preflight(self.ws, self.id, "draft", text_only=True)["ok"])
        postkit.set_fields(self.ws, self.id, {"first_comment": "changed after approval"})
        pre = pp.preflight(self.ws, self.id, "draft", text_only=True)
        self.assertFalse(pre["ok"])
        self.assertTrue(any("Decision 4 no longer matches" in p for p in pre["problems"]))

    def test_an_unbuilt_or_stale_package_folder_is_refused(self):
        self.approved_and_built()
        shutil.rmtree(os.path.join(self.ws, "exports"))
        self.assertTrue(any("Build the ready-to-paste package" in p for p in pp.preflight(self.ws, self.id, "draft", text_only=True)["problems"]))

    def test_the_visual_cannot_be_uploaded_so_text_only_must_be_chosen_on_purpose(self):
        self.approved_and_built()
        pre = pp.preflight(self.ws, self.id, "draft")
        self.assertFalse(pre["ok"])
        self.assertTrue(any("public web link" in p for p in pre["problems"]))
        ok = pp.preflight(self.ws, self.id, "draft", text_only=True)
        self.assertTrue(ok["ok"])
        self.assertTrue(any("WITHOUT its visual" in w for w in ok["warnings"]))
        self.assertTrue(pp.preflight(self.ws, self.id, "draft", media_url="https://img.example.com/a.png")["ok"])
        self.assertFalse(pp.preflight(self.ws, self.id, "draft", media_url="http://img.example.com/a.png")["ok"])

    def test_scheduling_rules(self):
        self.approved_and_built()
        for at, bad in ((None, True), ("tomorrow", True), (self.when(1), True), (self.when(60 * 24 * 120), True), (self.when(120), False)):
            pre = pp.preflight(self.ws, self.id, "schedule", at, text_only=True)
            self.assertEqual(not pre["ok"], bad, at)
        pre = pp.preflight(self.ws, self.id, "schedule", self.when(120), text_only=True)
        self.assertRegex(pre["payload"]["scheduledTime"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.000Z$")

    def test_there_is_no_post_now_mode(self):
        self.approved_and_built()
        self.assertFalse(pp.preflight(self.ws, self.id, "now", text_only=True)["ok"])

    def test_the_preview_sends_nothing_and_shows_no_key(self):
        self.approved_and_built()
        pre = pp.preflight(self.ws, self.id, "draft", text_only=True)
        self.assertEqual(Fake.calls, [])
        self.assertNotIn(KEY, json.dumps(pre))

    def test_the_base_url_must_be_https_or_local(self):
        os.environ["PUBLORA_BASE_URL"] = "http://api.example.com"
        with self.assertRaises(pp.AutopostError):
            pp.base_url()


class Sending(Base):
    def test_a_draft_goes_out_with_the_right_request_and_is_recorded(self):
        self.approved_and_built()
        rec = pp.send(self.ws, self.id, "draft", text_only=True, confirm="PUBLISH")
        self.assertEqual((rec["status"], rec["remote_id"]), ("draft", "pg-1"))
        method, path, key, body = Fake.calls[-1]
        self.assertEqual((method, path, key), ("POST", "/create-post", KEY))
        self.assertEqual(body["platforms"], ["linkedin-abc123"])
        self.assertEqual(body["content"].strip(), TEXT.strip())
        self.assertNotIn("scheduledTime", body)
        self.assertNotIn("mediaUrls", body)
        self.assertNotIn("first_comment", json.dumps(body))
        self.assertIn("draft in Publora", rtext(os.path.join(self.ws, "memory", "post-tracker.md")))
        log = rtext(os.path.join(self.ws, "runs", "publish-log.jsonl"))
        self.assertIn('"result": "sent"', log)
        self.assertNotIn(KEY, log)
        self.assertNotIn("Most weekly reviews", log)

    def test_a_scheduled_post_carries_utc_time_and_the_image_link(self):
        self.approved_and_built()
        pp.send(self.ws, self.id, "schedule", self.when(180), "https://img.example.com/a.png", False, "PUBLISH")
        body = Fake.calls[-1][3]
        self.assertTrue(body["scheduledTime"].endswith("Z"))
        self.assertEqual(body["mediaUrls"], ["https://img.example.com/a.png"])

    def test_the_confirm_word_is_exact(self):
        self.approved_and_built()
        for typed in ("", "publish", "PUBLISH now", "yes"):
            with self.assertRaises(pp.AutopostError):
                pp.send(self.ws, self.id, "draft", text_only=True, confirm=typed)
        self.assertEqual(Fake.calls, [])

    def test_the_same_package_cannot_be_sent_twice(self):
        self.approved_and_built()
        pp.send(self.ws, self.id, "draft", text_only=True, confirm="PUBLISH")
        calls = len(Fake.calls)
        with self.assertRaises(pp.AutopostError) as cm:
            pp.send(self.ws, self.id, "draft", text_only=True, confirm="PUBLISH")
        self.assertIn("already sent", str(cm.exception))
        self.assertEqual(len(Fake.calls), calls)

    def test_changed_content_is_a_new_package_and_needs_new_approvals_first(self):
        self.approved_and_built()
        pp.send(self.ws, self.id, "draft", text_only=True, confirm="PUBLISH")
        postkit.save_text(self.ws, self.id, TEXT + "One more line.\n")
        with self.assertRaises(pp.AutopostError) as cm:
            pp.send(self.ws, self.id, "draft", text_only=True, confirm="PUBLISH")
        self.assertIn("Decision 3", str(cm.exception))

    def test_a_refusal_by_the_service_is_reported_without_the_key_and_leaves_no_lock(self):
        self.approved_and_built()
        Fake.create_status = 400
        with self.assertRaises(pp.AutopostError) as cm:
            pp.send(self.ws, self.id, "draft", text_only=True, confirm="PUBLISH")
        self.assertIn("HTTP 400", str(cm.exception))
        self.assertNotIn(KEY, str(cm.exception))
        self.assertFalse(os.path.exists(pp.published_path(self.ws, self.id)))
        Fake.create_status = 200
        self.assertEqual(pp.send(self.ws, self.id, "draft", text_only=True, confirm="PUBLISH")["status"], "draft")        # a clean 4xx may be retried by the owner

    def test_a_server_error_locks_the_package_because_the_outcome_is_unclear(self):
        self.approved_and_built()
        Fake.create_status = 503
        with self.assertRaises(pp.AutopostError) as cm:
            pp.send(self.ws, self.id, "draft", text_only=True, confirm="PUBLISH")
        self.assertIn("locked", str(cm.exception))
        self.assertEqual(jload(pp.published_path(self.ws, self.id))["status"], "unknown")
        Fake.create_status = 200
        calls = len(Fake.calls)
        with self.assertRaises(pp.AutopostError):
            pp.send(self.ws, self.id, "draft", text_only=True, confirm="PUBLISH")
        self.assertEqual(len(Fake.calls), calls)                          # no automatic or blind retry
        self.assertTrue(pp.forget(self.ws, self.id))
        self.assertEqual(pp.send(self.ws, self.id, "draft", text_only=True, confirm="PUBLISH")["status"], "draft")

    def test_no_answer_at_all_also_locks(self):
        self.approved_and_built()
        os.environ["PUBLORA_BASE_URL"] = "http://127.0.0.1:1"
        with self.assertRaises(pp.AutopostError):
            pp.send(self.ws, self.id, "draft", text_only=True, confirm="PUBLISH")
        self.assertEqual(jload(pp.published_path(self.ws, self.id))["status"], "unknown")

    def test_connection_lookup_rules(self):
        self.approved_and_built()
        Fake.connections = {"connections": [{"platformId": "x-1"}]}
        with self.assertRaises(pp.AutopostError) as cm:
            pp.send(self.ws, self.id, "draft", text_only=True, confirm="PUBLISH")
        self.assertIn("No LinkedIn connection", str(cm.exception))
        Fake.connections = {"connections": [{"platformId": "linkedin-a"}, {"platformId": "linkedin-b"}]}
        with self.assertRaises(pp.AutopostError) as cm:
            pp.send(self.ws, self.id, "draft", text_only=True, confirm="PUBLISH")
        self.assertIn("More than one", str(cm.exception))
        os.environ["PUBLORA_PLATFORM_ID"] = "linkedin-b"
        self.assertEqual(pp.send(self.ws, self.id, "draft", text_only=True, confirm="PUBLISH")["status"], "draft")
        self.assertEqual(Fake.calls[-1][3]["platforms"], ["linkedin-b"])

    def test_the_command_line_refuses_to_send_without_a_keyboard(self):
        self.approved_and_built()
        r = subprocess.run([sys.executable, os.path.join(self.ws, "scripts", "publish_publora.py"), "--workspace", self.ws, "send", "--id", self.id, "--text-only"],
                           capture_output=True, text=True, stdin=subprocess.DEVNULL, env=dict(os.environ))
        self.assertEqual(r.returncode, 2)
        self.assertIn("person at a keyboard", r.stderr)
        self.assertEqual(Fake.calls, [])
        pv = subprocess.run([sys.executable, os.path.join(self.ws, "scripts", "publish_publora.py"), "--workspace", self.ws, "preview", "--id", self.id, "--text-only"],
                            capture_output=True, text=True, env=dict(os.environ))
        self.assertEqual(pv.returncode, 0, pv.stderr)
        self.assertIn("Nothing was sent", pv.stdout)
        self.assertNotIn(KEY, pv.stdout + pv.stderr)


if __name__ == "__main__":
    unittest.main()
