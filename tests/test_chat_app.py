"""Tests for the browser app: real HTTP against the real server with the stand-in AI. Covers the whole pipeline and the security rules."""
import http.client
import json
import os
import re
import shutil
import sys
import threading
import time
import unittest
import urllib.parse

from tests.helpers import AGENT_COUNT, COMMAND_COUNT, SKILL_COUNT, make_workspace, rtext

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "runtime"))
import chat_app  # noqa: E402
from tests.test_autopost import Fake  # noqa: E402

DEMO_AI = json.dumps([sys.executable, os.path.join(ROOT, "runtime", "demo_ai.py")])


class Client:
    def __init__(self, httpd, url):
        self.port = httpd.server_address[1]
        self.token = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["t"][0]
        self.cookie = None

    def raw(self, method, path, body=None, headers=None, host=None, cookie=True):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=30)
        hdr = {"Host": host or "127.0.0.1:%d" % self.port}
        if cookie and self.cookie:
            hdr["Cookie"] = self.cookie
        hdr.update(headers or {})
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            hdr.setdefault("Content-Type", "application/json")
        conn.request(method, path, body=data, headers=hdr)
        r = conn.getresponse()
        payload = r.read()
        conn.close()
        return r, payload

    def login(self):
        r, _ = self.raw("GET", "/?t=" + self.token, cookie=False)
        assert r.status == 302, r.status
        self.cookie = r.getheader("Set-Cookie").split(";")[0]

    def api(self, method, path, body=None):
        r, payload = self.raw(method, path, body, {"X-LBA": "1"} if method == "POST" else None)
        return r.status, json.loads(payload.decode())

    def job(self, path, body):
        st, j = self.api("POST", path, body)
        assert st == 200, j
        for _ in range(200):
            st, s = self.api("GET", "/api/job/" + j["job"])
            if s["state"] != "running":
                return s
            time.sleep(0.05)
        raise AssertionError("job did not finish")


class Base(unittest.TestCase):
    env = {}

    def setUp(self):
        self.ws = make_workspace({"users": ["Priya"], "setup_completed": True, "language": "English", "run_tool": "claude", "posting_tool": "Buffer"})
        self.saved = {k: os.environ.get(k) for k in ("LBA_AI_CMD", "LBA_BROWSER", "LBA_DEMO_EVIDENCE_GAP", "LBA_DEMO_FAIL", "LBA_DEMO_BAD_JSON_ONCE")}
        os.environ["LBA_AI_CMD"] = DEMO_AI
        os.environ["LBA_BROWSER"] = ""
        for k, v in self.env.items():
            os.environ[k] = v
        self.httpd, self.app, url = chat_app.start(self.ws, 0, True)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.c = Client(self.httpd, url)
        self.c.login()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        for k, v in self.saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.ws, ignore_errors=True)

    def new_post(self):
        return self.c.api("POST", "/api/post/new", {"title": "", "role": "Utility"})[1]["post_id"]

    def step(self, pid, step, **kw):
        s = self.c.job("/api/post/%s/step" % pid, dict(step=step, **kw))
        self.assertEqual(s["state"], "done", s)
        return s["result"]

    def decide(self, pid, n, **kw):
        return self.c.api("POST", "/api/post/%s/decision" % pid, dict(decision=n, **kw))


class Pipeline(Base):
    def test_whole_journey_over_http(self):
        pid = self.new_post()
        self.step(pid, "ideas")
        self.assertEqual(self.decide(pid, 1, choice=1)[0], 200)
        self.step(pid, "draft")
        self.step(pid, "visuals")
        self.assertEqual(self.decide(pid, 2, choice=1)[0], 200)
        self.step(pid, "render", format="portrait")
        self.step(pid, "check")
        self.assertEqual(self.decide(pid, 3)[0], 200)
        self.assertEqual(self.decide(pid, 4)[0], 200)
        st, built = self.c.api("POST", "/api/post/%s/build" % pid, {})
        self.assertEqual(st, 200, built)
        self.assertIn("PACKAGE.md", built["files"])
        st, status = self.c.api("GET", "/api/post/" + pid)
        self.assertTrue(all(s["done"] for s in status["steps"]), status["steps"])
        self.assertTrue(all(d["current"] for d in status["decisions"].values()))
        r, body = self.c.raw("GET", "/files/%s/package/post.txt" % pid)
        self.assertEqual(r.status, 200)
        self.assertIn("Most weekly reviews fail", body.decode())
        st, live = self.c.api("POST", "/api/post/%s/live" % pid, {"url": "https://example.com/p", "windows": ["24h", "72h"]})
        self.assertEqual((st, live["reminders_added"]), (200, 2))
        st, runs = self.c.api("GET", "/api/runs")
        self.assertEqual(st, 200)

    def test_steps_are_refused_out_of_order_with_a_plain_reason(self):
        pid = self.new_post()
        for step, word in (("draft", "idea"), ("visuals", "post"), ("render", "visual"), ("check", "Render")):
            s = self.c.job("/api/post/%s/step" % pid, {"step": step})
            self.assertEqual(s["state"], "error")
            self.assertIn(word, s["error"])
        self.assertEqual(self.decide(pid, 3)[0], 400)
        self.assertEqual(self.decide(pid, 4)[0], 400)
        st, b = self.c.api("POST", "/api/post/%s/build" % pid, {})
        self.assertEqual(st, 400)
        self.assertIn("Decision 1 is missing", b["error"])

    def test_editing_after_approval_turns_decisions_stale_and_blocks_build(self):
        pid = self.new_post()
        self.step(pid, "ideas"); self.decide(pid, 1, choice=2); self.step(pid, "draft"); self.step(pid, "visuals"); self.decide(pid, 2, choice=1)
        self.step(pid, "render"); self.step(pid, "check"); self.decide(pid, 3); self.decide(pid, 4)
        st, status = self.c.api("GET", "/api/post/" + pid)
        text = status["post_text"]
        self.c.api("POST", "/api/post/%s/fields" % pid, {"post_text": text.replace("week 3", "week 4")})
        st, status = self.c.api("GET", "/api/post/" + pid)
        self.assertEqual([status["decisions"][str(n)]["current"] for n in (1, 2, 3, 4)], [True, True, False, False])
        self.assertEqual(self.c.api("POST", "/api/post/%s/build" % pid, {})[0], 400)

    def test_an_unknown_render_format_gets_a_clear_message(self):
        pid = self.new_post()
        self.step(pid, "ideas"); self.decide(pid, 1, choice=1); self.step(pid, "draft"); self.step(pid, "visuals"); self.decide(pid, 2, choice=1)
        s = self.c.job("/api/post/%s/step" % pid, {"step": "render", "format": ""})
        self.assertEqual(s["state"], "error")
        self.assertIn("Choose a format", s["error"])

    def test_only_listed_fields_are_editable(self):
        pid = self.new_post()
        st, r = self.c.api("POST", "/api/post/%s/fields" % pid, {"fields": {"created": "1999", "measurement_windows": ["24h"]}})
        self.assertEqual(st, 400)
        self.assertEqual(self.c.api("POST", "/api/post/%s/fields" % pid, {"fields": {"suggested_time": "Tue 9am"}})[0], 200)

    def test_a_carousel_replaces_the_visual_and_needs_decision_two_again(self):
        pid = self.new_post()
        self.step(pid, "ideas"); self.decide(pid, 1, choice=1); self.step(pid, "draft"); self.step(pid, "visuals"); self.decide(pid, 2, choice=1); self.step(pid, "render")
        self.step(pid, "carousel")
        st, status = self.c.api("GET", "/api/post/" + pid)
        self.assertEqual(status["visual_type"], "carousel")
        self.assertFalse(status["decisions"]["2"]["current"])
        self.assertEqual(self.decide(pid, 2)[0], 200)
        self.assertTrue(self.c.api("GET", "/api/post/" + pid)[1]["decisions"]["2"]["current"])

    def test_findings_must_be_accepted_to_approve_with_open_defects(self):
        pid = self.new_post()
        self.step(pid, "ideas"); self.decide(pid, 1, choice=1); self.step(pid, "draft"); self.step(pid, "visuals"); self.decide(pid, 2, choice=1); self.step(pid, "render"); self.step(pid, "check")
        state = os.path.join(self.ws, "drafts", pid, "state.json")
        data = json.loads(rtext(state))
        data["check"]["qa"] = {"score": 70, "pass": False, "defects": ["Make the labels bigger"]}
        with open(state, "w") as fh:
            json.dump(data, fh)
        st, r = self.decide(pid, 3)
        self.assertEqual(st, 400)
        self.assertIn("open findings", r["error"])
        self.assertEqual(self.decide(pid, 3, accept_findings=True)[0], 200)
        data["check"]["governance"]["status"] = "STOP"
        with open(state, "w") as fh:
            json.dump(data, fh)
        self.assertEqual(self.decide(pid, 3, accept_findings=True)[0], 400)


class Additions(Base):
    def journey(self, upto="build"):
        pid = self.new_post()
        self.step(pid, "ideas"); self.decide(pid, 1, choice=1); self.step(pid, "draft"); self.step(pid, "visuals"); self.decide(pid, 2, choice=1)
        self.step(pid, "render"); self.step(pid, "check"); self.decide(pid, 3); self.decide(pid, 4)
        if upto == "build":
            self.assertEqual(self.c.api("POST", "/api/post/%s/build" % pid, {})[0], 200)
        return pid

    def test_the_status_carries_writing_checks_at_the_chosen_tier(self):
        pid = self.new_post()
        self.step(pid, "ideas"); self.decide(pid, 1, choice=1); self.step(pid, "draft")
        wc = self.c.api("GET", "/api/post/" + pid)[1]["writing_checks"]
        self.assertEqual(wc["tier"], "strict")
        self.assertTrue(wc["lint_ok"])
        self.assertIn("tells_score", wc)
        self.assertTrue(any(f["code"] == "FIGURES" for f in wc["lint"]) or wc["stats"]["words"] > 10)
        with open(os.path.join(self.ws, "docs", "settings.json")) as fh:
            st = json.load(fh)
        st["humanizer_tier"] = "forensic"
        with open(os.path.join(self.ws, "docs", "settings.json"), "w") as fh:
            json.dump(st, fh)
        self.assertEqual(self.c.api("GET", "/api/post/" + pid)[1]["writing_checks"]["tier"], "forensic")

    def test_editing_in_a_machine_sounding_line_shows_up_in_the_checks(self):
        pid = self.new_post()
        self.step(pid, "ideas"); self.decide(pid, 1, choice=1); self.step(pid, "draft")
        text = self.c.api("GET", "/api/post/" + pid)[1]["post_text"] + "\nHere's the thing. Let that sink in. In today's fast-paced world, leverage robust, seamless, pivotal habits."
        self.c.api("POST", "/api/post/%s/fields" % pid, {"post_text": text})
        wc = self.c.api("GET", "/api/post/" + pid)[1]["writing_checks"]
        self.assertTrue({"FILLER_BRIDGE", "AI_VOCABULARY"} <= {t["code"] for t in wc["tells"]})
        self.assertGreater(wc["tells_score"], 10)

    def test_the_auto_post_card_is_off_and_the_endpoint_refuses_when_it_is_off(self):
        self.assertFalse(self.c.api("GET", "/api/meta")[1]["auto_post"])
        pid = self.journey()
        st, r = self.c.api("POST", "/api/post/%s/autopost" % pid, {"action": "preview", "mode": "draft", "text_only": True})
        self.assertEqual(st, 200)
        self.assertFalse(r["ok"])
        self.assertTrue(any("Auto-post is off" in p for p in r["problems"]))
        st, r = self.c.api("POST", "/api/post/%s/autopost" % pid, {"action": "send", "mode": "draft", "text_only": True, "confirm": "PUBLISH"})
        self.assertEqual(st, 400)
        self.assertIn("Not sent", r["error"])

    def test_the_add_on_through_the_app_needs_the_typed_word_and_cannot_repeat(self):
        import threading
        from http.server import HTTPServer
        Fake.calls, Fake.create_status = [], 200
        srv = HTTPServer(("127.0.0.1", 0), Fake)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        saved = {k: os.environ.get(k) for k in ("PUBLORA_API_KEY", "PUBLORA_BASE_URL")}
        os.environ["PUBLORA_API_KEY"] = "sk_test_not_a_real_key_000000"
        os.environ["PUBLORA_BASE_URL"] = "http://127.0.0.1:%d" % srv.server_port
        try:
            with open(os.path.join(self.ws, "docs", "settings.json")) as fh:
                st = json.load(fh)
            st["auto_post"] = {"provider": "publora", "enabled": True}
            with open(os.path.join(self.ws, "docs", "settings.json"), "w") as fh:
                json.dump(st, fh)
            self.assertTrue(self.c.api("GET", "/api/meta")[1]["auto_post"])
            pid = self.journey()
            url = "/api/post/%s/autopost" % pid
            blocked = self.c.api("POST", url, {"action": "preview", "mode": "draft"})[1]
            self.assertFalse(blocked["ok"])
            self.assertTrue(any("public web link" in p for p in blocked["problems"]))
            ok = self.c.api("POST", url, {"action": "preview", "mode": "draft", "text_only": True})[1]
            self.assertTrue(ok["ok"])
            self.assertEqual(Fake.calls, [])
            self.assertEqual(self.c.api("POST", url, {"action": "send", "mode": "draft", "text_only": True, "confirm": "yes"})[0], 400)
            self.assertEqual(Fake.calls, [])
            st, done = self.c.api("POST", url, {"action": "send", "mode": "draft", "text_only": True, "confirm": "PUBLISH"})
            self.assertEqual((st, done["record"]["status"]), (200, "draft"))
            self.assertEqual(len([c for c in Fake.calls if c[0] == "POST"]), 1)
            self.assertEqual(self.c.api("POST", url, {"action": "send", "mode": "draft", "text_only": True, "confirm": "PUBLISH"})[0], 400)
            self.assertEqual(len([c for c in Fake.calls if c[0] == "POST"]), 1)
        finally:
            srv.shutdown()
            srv.server_close()
            for k, v in saved.items():
                os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)

    def test_mark_live_with_reply_windows_sets_both_kinds(self):
        pid = self.journey()
        st, r = self.c.api("POST", "/api/post/%s/live" % pid, {"url": "https://example.com/p", "windows": ["24h"], "reply_windows": ["1h", "6h"]})
        self.assertEqual((st, r["reminders_added"]), (200, 3))
        kinds = sorted(i.get("kind") for i in self.c.api("GET", "/api/post/" + pid)[1]["reminders"])
        self.assertEqual(kinds, ["reply", "reply", "results"])
        st, bad = self.c.api("POST", "/api/post/%s/live" % pid, {"url": "x", "windows": ["24h"], "reply_windows": ["7d"]})
        self.assertEqual(st, 400)

    def test_meta_lists_the_new_agents_for_the_at_menu(self):
        names = [a["name"] for a in self.c.api("GET", "/api/meta")[1]["agents"]]
        for n in ("interviewer", "reply", "comment", "repurposer", "hook-extractor", "profile-optimizer"):
            self.assertIn(n, names)
        cmds = [c["name"] for c in self.c.api("GET", "/api/meta")[1]["commands"]]
        for n in ("interview", "reply", "comment", "repurpose", "hook", "profile", "comments"):
            self.assertIn(n, cmds)

    def test_chat_with_the_interviewer_keeps_the_conversation_and_offers_saving(self):
        j = self.c.job("/api/chat", {"message": "@interviewer let us start"})
        self.assertEqual(j["state"], "done")
        self.assertEqual(j["result"]["mentions"], ["interviewer"])
        entry = "REGISTER ENTRY\nregister: experience-bank\nStory ID: S-20261006-01\nDate: 2026-10-06\nTitle: First team review\nStory (owner's words): We tried a weekly review.\nConfirmed true and usable: yes\nTopics: reviews\nUsed in posts: \nNotes: none"
        st, r = self.c.api("POST", "/api/memory/apply", {"text": entry, "agent": "interviewer"})
        self.assertEqual(st, 200, r)
        st, r = self.c.api("POST", "/api/memory/apply", {"text": entry.replace("experience-bank", "ideas-and-examples"), "agent": "interviewer"})
        self.assertEqual(st, 400)                                      # the interviewer may write only the Experience Bank


class EvidenceGap(Base):
    env = {"LBA_DEMO_EVIDENCE_GAP": "1"}

    def test_the_post_is_not_written_until_real_support_is_given(self):
        pid = self.new_post()
        self.step(pid, "ideas"); self.decide(pid, 1, choice=1)
        res = self.step(pid, "draft")
        self.assertEqual(res["evidence_status"], "INSUFFICIENT EVIDENCE")
        st, status = self.c.api("GET", "/api/post/" + pid)
        self.assertEqual(status["post_text"], "")
        self.assertTrue(status["state"]["evidence_gaps"])
        res = self.step(pid, "draft", support="Last spring my team dropped the review in week 3, so I gave it one job.")
        self.assertEqual(res["evidence_status"], "OK")
        self.assertIn("Last spring", self.c.api("GET", "/api/post/" + pid)[1]["post_text"])


class BadAnswers(Base):
    env = {"LBA_DEMO_BAD_JSON_ONCE": "1"}

    def test_a_malformed_answer_is_retried_once_automatically(self):
        pid = self.new_post()
        self.assertEqual(self.c.job("/api/post/%s/step" % pid, {"step": "ideas"})["state"], "done")


class Failing(Base):
    env = {"LBA_DEMO_FAIL": "ideas"}

    def test_an_unusable_answer_is_reported_and_nothing_is_saved(self):
        pid = self.new_post()
        s = self.c.job("/api/post/%s/step" % pid, {"step": "ideas"})
        self.assertEqual(s["state"], "error")
        self.assertIn("could not be used", s["error"])
        self.assertEqual(self.c.api("GET", "/api/post/" + pid)[1]["state"]["ideas"], [])


class Chat(Base):
    def test_chat_with_mention_command_and_history(self):
        j = self.c.job("/api/chat", {"message": "@governance is this safe to post?"})
        self.assertEqual(j["state"], "done")
        self.assertEqual(j["result"]["mentions"], ["governance"])
        self.assertIn("Demo stand-in", j["result"]["reply"])
        j = self.c.job("/api/chat", {"message": "/next please"})
        self.assertEqual(j["state"], "done")
        hist = self.c.api("GET", "/api/chat/history")[1]["history"]
        self.assertEqual([m["role"] for m in hist], ["owner", "assistant", "owner", "assistant"])
        self.c.api("POST", "/api/chat/new", {})
        self.assertEqual(self.c.api("GET", "/api/chat/history")[1]["history"], [])

    def test_meta_lists_all_agents_for_the_at_menu(self):
        meta = self.c.api("GET", "/api/meta")[1]
        self.assertEqual(len(meta["agents"]), AGENT_COUNT)
        self.assertIn("governance", [a["name"] for a in meta["agents"]])
        self.assertTrue(len(meta["commands"]) >= 40)
        self.assertTrue(meta["demo"])

    def test_memory_entries_in_a_reply_are_applied_only_through_the_guard_for_an_allowed_agent(self):
        entry = "REGISTER ENTRY\nregister: ideas-and-examples\nType: idea\nSummary: a sample idea\n"
        st, r = self.c.api("POST", "/api/memory/apply", {"text": entry, "agent": "writing"})
        self.assertEqual(st, 400)                        # 'writing' may not write that register
        self.assertIn("not allowed", r["message"])
        st, r = self.c.api("POST", "/api/memory/apply", {"text": entry, "agent": "not-an-agent"})
        self.assertEqual(st, 400)


class Security(Base):
    def test_no_access_without_the_secret_cookie(self):
        r, _ = self.c.raw("GET", "/api/meta", cookie=False)
        self.assertEqual(r.status, 403)
        r, _ = self.c.raw("GET", "/?t=wrong", cookie=False)
        self.assertEqual(r.status, 403)

    def test_wrong_host_header_is_refused_which_stops_dns_rebinding(self):
        r, _ = self.c.raw("GET", "/api/meta", host="evil.example.com")
        self.assertEqual(r.status, 403)
        r, _ = self.c.raw("POST", "/api/post/new", {}, {"X-LBA": "1"}, host="evil.example.com:%d" % self.c.port)
        self.assertEqual(r.status, 403)

    def test_cross_site_posts_are_refused(self):
        r, _ = self.c.raw("POST", "/api/post/new", {}, {"X-LBA": "1", "Origin": "https://evil.example.com"})
        self.assertEqual(r.status, 403)
        r, _ = self.c.raw("POST", "/api/post/new", {})                       # a plain form post has no custom header
        self.assertEqual(r.status, 403)
        r, _ = self.c.raw("POST", "/api/post/new", {}, {"X-LBA": "1", "Content-Type": "text/plain"})
        self.assertEqual(r.status, 415)

    def test_files_cannot_escape_their_folders(self):
        pid = self.new_post()
        for path in ("/files/%s/final/../../../docs/settings.json" % pid, "/files/%s/final/..%%2F..%%2Fsettings.json" % pid, "/files/%s/secrets/x.txt" % pid,
                     "/files/%s/final/.hidden" % pid, "/files/../x/final/a.png", "/static/../chat_core.py"):
            r, _ = self.c.raw("GET", path)
            self.assertIn(r.status, (400, 403, 404), path)
        self.assertEqual(self.c.raw("GET", "/api/post/P-20000101-01")[0].status, 404)

    def test_pages_carry_a_strict_content_security_policy_and_no_cache(self):
        r, body = self.c.raw("GET", "/")
        self.assertEqual(r.status, 200)
        self.assertIn("default-src 'none'", r.getheader("Content-Security-Policy"))
        self.assertIn("script-src 'self'", r.getheader("Content-Security-Policy"))
        self.assertEqual(r.getheader("Cache-Control"), "no-store")
        self.assertNotIn(b"<script>", body)           # no inline script: everything is in /static/app.js

    def test_the_server_listens_on_this_computer_only(self):
        self.assertEqual(self.httpd.server_address[0], "127.0.0.1")

    def test_errors_never_show_a_stack_trace(self):
        st, r = self.c.api("POST", "/api/post/new", {"title": "x"})
        pid = r["post_id"]
        with open(os.path.join(self.ws, "drafts", pid, "package.json"), "w") as fh:
            fh.write("{not json")
        r, body = self.c.raw("GET", "/api/post/" + pid)
        self.assertNotIn(b"Traceback", body)

    def test_the_ui_never_uses_innerhtml(self):
        js = rtext(os.path.join(ROOT, "runtime", "app", "app.js"))
        for bad in ("innerHTML", "outerHTML", "document.write", "eval(", "insertAdjacentHTML"):
            self.assertFalse(bad in js, "app.js must not use " + bad)


if __name__ == "__main__":
    unittest.main()


@unittest.skipUnless(__import__("shutil").which("node"), "Node.js is not installed")
class UiSmoke(Base):
    """Runs the real app.js under Node with a stand-in DOM against the live server and clicks through all nine cards."""

    def test_the_pipeline_can_be_clicked_through_end_to_end(self):
        import subprocess
        r = subprocess.run(["node", os.path.join(ROOT, "tests", "ui_smoke.js"), "http://127.0.0.1:%d" % self.c.port, self.c.token], capture_output=True, text=True, timeout=180)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        out = json.loads(r.stdout.strip().splitlines()[-1])
        self.assertNotIn("fatal", out)
        self.assertEqual(out["errors"], [])
        self.assertEqual(out["stepsDone"], out["stepsTotal"], out)
        self.assertEqual(out["pills"], 4)
        self.assertGreaterEqual(out["copyBoxes"], 6)
        self.assertEqual(out["agentMenu"], 1)               # "@gov" -> governance
        self.assertEqual(out["afterPick"], "@governance ")
        self.assertGreaterEqual(out["commandMenu"], 1)
        self.assertEqual(out["allAgents"], AGENT_COUNT)
        self.assertTrue(out["emailMenuHidden"])             # an e-mail address must not open the agent menu
