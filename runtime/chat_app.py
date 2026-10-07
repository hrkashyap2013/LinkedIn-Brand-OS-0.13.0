#!/usr/bin/env python3
"""The browser app: chat with your agents (type @ for the agent menu) and walk a post through your four decisions.

    python3 scripts/chat_app.py               # opens your browser on this computer
    python3 scripts/chat_app.py --demo        # try everything with a stand-in AI: no account, no cost
    python3 scripts/chat_app.py --no-browser  # just print the link

Safety:
  * It listens on 127.0.0.1 only (this computer), on a random port, and the link carries a secret token.
    Other computers cannot reach it, and other web pages cannot drive it (host, origin and token are checked).
  * Your AI tool (Claude Code or Codex, already installed and signed in) only returns text. This program writes the
    files and records your decisions when YOU click Approve. No API key is used or stored.
  * Nothing is ever posted. The end of the road is a ready-to-paste package that you post yourself.

Needs Python 3.8+ and nothing else.
"""
import argparse
import hmac
import json
import os
import re
import secrets
import socketserver
import sys
import threading
import urllib.parse
import webbrowser
from http import server as httpserver

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import approvals  # noqa: E402
import chat_core as cc  # noqa: E402
import postkit  # noqa: E402
import publish_publora  # noqa: E402
import reminders  # noqa: E402
import visual_engine as ve  # noqa: E402

APP_DIR = os.path.join(HERE, "app")
MAX_BODY = 1024 * 1024
SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,100}$")
TYPES = {".png": "image/png", ".svg": "image/svg+xml", ".pdf": "application/pdf", ".html": "text/html; charset=utf-8", ".txt": "text/plain; charset=utf-8",
         ".md": "text/plain; charset=utf-8", ".json": "application/json", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8"}
EDITABLE = ("first_comment", "pin_comment", "link_comment", "suggested_time", "audience", "objective", "content_role", "territory", "expected_takeaway",
            "cta_type", "experiment_id", "visual_prompt", "hashtags", "mentions", "reply_starters", "sources", "title", "role")
PAGE_CSP = "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
FILE_CSP = "sandbox; default-src 'none'; style-src 'unsafe-inline'; img-src data: 'self'"


class Api(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


class App:
    def __init__(self, ws, token, port, demo=False):
        self.ws, self.token, self.port, self.demo = ws, token, port, demo
        self.pipe = cc.Pipeline(ws)
        self.jobs = cc.Jobs()

    def owner(self):
        return postkit.owner_name(self.ws)


def make_handler(app):
    class Handler(httpserver.BaseHTTPRequestHandler):
        server_version = "LBA"
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):
            pass

        # ---- plumbing
        def _hosts_ok(self):
            allowed = ("127.0.0.1:%d" % app.port, "localhost:%d" % app.port, "[::1]:%d" % app.port)
            return self.headers.get("Host", "") in allowed

        def _send(self, status, body, ctype, extra=None):
            if isinstance(body, str):
                body = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj, status=200):
            self._send(status, json.dumps(obj), "application/json; charset=utf-8", {"Content-Security-Policy": "default-src 'none'"})

        def _cookie_ok(self):
            for part in self.headers.get("Cookie", "").split(";"):
                k, _, v = part.strip().partition("=")
                if k == "lba_session" and hmac.compare_digest(v, app.token):
                    return True
            return False

        def _body(self):
            if "application/json" not in self.headers.get("Content-Type", ""):
                raise Api("expected JSON", 415)
            n = int(self.headers.get("Content-Length", "0") or 0)
            if n > MAX_BODY:
                raise Api("request too large", 413)
            raw = self.rfile.read(n) if n else b"{}"
            try:
                data = json.loads(raw.decode("utf-8") or "{}")
            except ValueError:
                raise Api("the request was not valid JSON")
            if not isinstance(data, dict):
                raise Api("expected a JSON object")
            return data

        def _guard(self, post):
            if not self._hosts_ok():
                self._send(403, "Forbidden host", "text/plain")
                return False
            if post:
                origin = self.headers.get("Origin")
                if origin and origin not in ("http://127.0.0.1:%d" % app.port, "http://localhost:%d" % app.port):
                    self._send(403, "Forbidden origin", "text/plain")
                    return False
                if self.headers.get("X-LBA") != "1":
                    self._send(403, "Missing header", "text/plain")
                    return False
            return True

        # ---- routing
        def do_GET(self):
            self._handle(False)

        def do_POST(self):
            self._handle(True)

        def _handle(self, post):
            if not self._guard(post):
                return
            url = urllib.parse.urlparse(self.path)
            q = urllib.parse.parse_qs(url.query)
            if not post and url.path == "/" and q.get("t") and hmac.compare_digest(q["t"][0], app.token):
                self.send_response(302)
                self.send_header("Set-Cookie", "lba_session=%s; HttpOnly; SameSite=Strict; Path=/" % app.token)
                self.send_header("Location", "/")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            if not self._cookie_ok():
                self._send(403, "Open the link that the terminal printed when you started the app (it contains a secret token).", "text/plain; charset=utf-8")
                return
            try:
                if not post:
                    self._get(url.path, q)
                else:
                    self._post(url.path, self._body())
            except Api as exc:
                self._json({"error": str(exc)}, exc.status)
            except (cc.StepError, cc.AIError, postkit.PostError, approvals.ApprovalError, ve.SpecError, ValueError) as exc:
                self._json({"error": str(exc)}, 400)
            except Exception as exc:                                    # never show a stack trace to the browser
                sys.stderr.write("chat_app: unexpected error: %r\n" % (exc,))
                self._json({"error": "Something unexpected went wrong. Details are in the terminal window."}, 500)

        def _post_id(self, path):
            m = re.match(r"^/api/post/(P-\d{8}-\d{2,3})(/.*)?$", path)
            if not m:
                raise Api("unknown post", 404)
            pid = m.group(1)
            if not os.path.exists(os.path.join(postkit.post_dir(app.ws, pid), "package.json")):
                raise Api("unknown post", 404)
            return pid, m.group(2) or ""

        def _get(self, path, q):
            ws = app.ws
            if path == "/":
                return self._send(200, postkit._read(os.path.join(APP_DIR, "index.html")), TYPES[".html"], {"Content-Security-Policy": PAGE_CSP})
            m = re.match(r"^/static/(app\.js|app\.css)$", path)
            if m:
                return self._send(200, postkit._read(os.path.join(APP_DIR, m.group(1))), TYPES[os.path.splitext(m.group(1))[1]])
            if path == "/api/meta":
                s = cc.settings(ws)
                return self._json({"version": cc.version(), "workspace": os.path.basename(ws), "tool": "demo" if app.demo else (s.get("run_tool") or "claude"), "demo": app.demo,
                                   "agents": cc.agents(ws), "commands": cc.commands(ws), "browser": bool(ve.find_browser()), "setup_completed": bool(s.get("setup_completed")),
                                   "users": s.get("users") or [], "language": s.get("language") or "", "windows": list(reminders.WINDOWS),
                                   "reply_windows": list(reminders.REPLY_WINDOWS), "auto_post": bool((s.get("auto_post") or {}).get("enabled"))})
            if path == "/api/posts":
                out = []
                for p in postkit.list_posts(ws):
                    st = app.pipe.status(p["post_id"])
                    done = sum(1 for s_ in st["steps"] if s_["done"])
                    out.append(dict(p, done=done, total=len(st["steps"]), built=bool(st["built"])))
                return self._json({"posts": out})
            if path.startswith("/api/post/"):
                pid, rest = self._post_id(path)
                if rest == "":
                    return self._json(app.pipe.status(pid))
                raise Api("unknown route", 404)
            m = re.match(r"^/api/job/(job-\d+)$", path)
            if m:
                j = app.jobs.get(m.group(1))
                if not j:
                    raise Api("unknown job", 404)
                return self._json(j)
            if path == "/api/chat/history":
                return self._json({"history": cc.load_history(ws)})
            if path == "/api/runs":
                return self._json(dict(cc.runs_overview(ws), due=reminders.due(ws)))
            if path == "/api/metrics":
                reports = os.path.join(ws, "reports")
                dash = sorted((f for f in os.listdir(reports) if f.startswith("dashboard-")), reverse=True) if os.path.isdir(reports) else []
                text = postkit._read(os.path.join(reports, dash[0])) if dash else ""
                return self._json({"csv_files": cc.inbox_csvs(ws), "dashboard_name": dash[0] if dash else "", "dashboard": text})
            m = re.match(r"^/files/(P-\d{8}-\d{2,3})/(previews|final|package)/([^/]+)$", path)
            if m:
                pid, area, name = m.groups()
                if not SAFE_NAME.match(name):
                    raise Api("bad file name", 400)
                base = os.path.join(app.ws, "exports", "ready-to-paste", pid) if area == "package" else os.path.join(postkit.post_dir(app.ws, pid), area)
                full = os.path.join(base, name)
                ext = os.path.splitext(name)[1].lower()
                if ext not in TYPES or not os.path.isfile(full):
                    raise Api("not found", 404)
                with open(full, "rb") as fh:
                    data = fh.read()
                extra = {"Content-Security-Policy": FILE_CSP}
                if ext == ".pdf":
                    extra["Content-Disposition"] = 'inline; filename="%s"' % name
                return self._send(200, data, TYPES[ext], extra)
            raise Api("not found", 404)

        def _job(self, label, fn):
            return self._json({"job": app.jobs.start(label, fn)})

        def _post(self, path, body):
            ws, pipe = app.ws, app.pipe
            if path == "/api/post/new":
                return self._json({"post_id": pipe.new_post(str(body.get("title", ""))[:200], str(body.get("role", ""))[:100])})
            if path == "/api/test-ai":
                return self._job("Testing your AI tool", lambda: cc.run_ai(ws, "LBA-STAGE: chat\nReply with the single word OK.\n## Owner's message\nTest", timeout=180)[:300])
            if path == "/api/chat":
                msg = str(body.get("message", "")).strip()
                if not msg:
                    raise Api("type a message first")
                return self._job("Asking your agents", lambda: cc.chat(ws, msg))
            if path == "/api/chat/new":
                cc.new_chat(ws)
                return self._json({"ok": True})
            if path == "/api/memory/apply":
                agent = str(body.get("agent", ""))
                if agent not in [a["name"] for a in cc.agents(ws)] + ["orchestrator"]:
                    raise Api("choose which agent these entries belong to")
                ok, msg = cc.apply_entries(ws, str(body.get("text", "")), agent)
                return self._json({"ok": ok, "message": msg}, 200 if ok else 400)
            if path == "/api/metrics/run":
                return self._json({"output": cc.run_metrics(ws, str(body.get("file", "")))})
            if path == "/api/reminders/done":
                n = reminders.mark(ws, str(body.get("post_id", "")), str(body.get("window", "")) or None, "done", str(body.get("kind", "")) or None)
                return self._json({"changed": n})
            if path.startswith("/api/post/"):
                pid, rest = self._post_id(path)
                return self._post_post(pid, rest, body)
            raise Api("not found", 404)

        def _post_post(self, pid, rest, body):
            pipe, by = app.pipe, app.owner()
            fb = str(body.get("feedback", ""))
            if rest == "/step":
                step = body.get("step")
                steps = {"ideas": lambda: pipe.ideas(pid, fb), "draft": lambda: pipe.draft(pid, fb, str(body.get("support", ""))), "visuals": lambda: pipe.visuals(pid, fb),
                         "render": lambda: pipe.render(pid, str(body.get("format", "portrait"))), "carousel": lambda: pipe.carousel(pid, fb), "check": lambda: pipe.check(pid, fb)}
                if step not in steps:
                    raise Api("unknown step")
                labels = {"ideas": "Preparing 3 ideas", "draft": "Writing the post", "visuals": "Designing 3 visual previews", "render": "Rendering the visual",
                          "carousel": "Building the carousel", "check": "Running the quality checks"}
                return self._job(labels[step], steps[step])
            if rest == "/decision":
                d = int(body.get("decision", 0))
                if d == 1:
                    res = pipe.choose_idea(pid, int(body.get("choice", 0)), "app", by)
                elif d == 2:
                    res = pipe.choose_visual(pid, int(body["choice"]) if body.get("choice") else None, "app", by)
                elif d == 3:
                    res = pipe.approve_content(pid, bool(body.get("accept_findings")), "app", by)
                elif d == 4:
                    res = pipe.approve_package(pid, "app", by)
                else:
                    raise Api("decision must be 1, 2, 3 or 4")
                return self._json({"ok": True, "entry": res.get("entry")})
            if rest == "/fields":
                fields = body.get("fields") or {}
                bad = [k for k in fields if k not in EDITABLE]
                if bad:
                    raise Api("these fields cannot be edited here: %s" % ", ".join(bad))
                for k in ("hashtags", "mentions", "reply_starters", "sources"):
                    if isinstance(fields.get(k), str):
                        fields[k] = [x.strip() for x in re.split(r"[,\n]", fields[k]) if x.strip()]
                pipe.update_fields(pid, fields, body.get("post_text") if isinstance(body.get("post_text"), str) else None)
                return self._json({"ok": True})
            if rest == "/build":
                res = pipe.build(pid)
                return self._json({"ok": True, "folder": res["folder"], "files": res["files"], "warnings": res["warnings"]})
            if rest == "/autopost":
                kw = dict(mode=str(body.get("mode", "draft")), at=str(body.get("at", "")) or None, media_url=str(body.get("media_url", "")) or None, text_only=bool(body.get("text_only")))
                if body.get("action") == "send":
                    try:
                        rec = pipe.autopost_send(pid, kw["mode"], kw["at"], kw["media_url"], kw["text_only"], str(body.get("confirm", "")))
                    except publish_publora.AutopostError as exc:
                        raise Api(str(exc))
                    return self._json({"ok": True, "record": rec})
                pre = pipe.autopost_preview(pid, **kw)
                return self._json({"ok": pre["ok"], "problems": pre["problems"], "warnings": pre["warnings"], "summary": pre["summary"], "payload": pre["payload"]})
            if rest == "/live":
                windows = body.get("windows") if isinstance(body.get("windows"), list) else None
                replies = body.get("reply_windows") if isinstance(body.get("reply_windows"), list) else None
                return self._json(pipe.mark_live(pid, str(body.get("url", ""))[:500], [str(w) for w in windows] if windows else None, [str(w) for w in replies] if replies else None))
            raise Api("not found", 404)

    return Handler


class Server(socketserver.ThreadingMixIn, httpserver.HTTPServer):
    daemon_threads = True
    allow_reuse_address = False


def start(ws, port=0, demo=False):
    """Create the server (not yet serving). Returns (httpd, app, url)."""
    token = secrets.token_urlsafe(24)
    app = App(os.path.abspath(ws), token, 0, demo)
    httpd = Server(("127.0.0.1", port), make_handler(app))
    app.port = httpd.server_address[1]
    return httpd, app, "http://127.0.0.1:%d/?t=%s" % (app.port, token)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Browser app for your LinkedIn brand agents.")
    ap.add_argument("--workspace", default=os.path.dirname(HERE))
    ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--demo", action="store_true", help="use a stand-in AI so you can try everything with no account")
    a = ap.parse_args(argv)
    ws = os.path.abspath(a.workspace)
    if not os.path.isdir(os.path.join(ws, "docs")) or not os.path.isdir(os.path.join(ws, "memory")):
        print("error: %s does not look like an installed workspace (no docs/ or memory/). Run the installer first." % ws, file=sys.stderr)
        return 2
    if a.demo:
        os.environ["LBA_AI_CMD"] = json.dumps([sys.executable, os.path.join(HERE, "demo_ai.py")])
    httpd, app, url = start(ws, a.port, a.demo)
    print("LinkedIn Brand Agents is running.\n  Open this link (it stays on this computer):\n  %s\n  Stop with Ctrl+C." % url)
    if a.demo:
        print("  DEMO MODE: answers are canned samples from a stand-in, not a real AI.")
    if not a.no_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
