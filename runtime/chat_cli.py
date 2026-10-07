#!/usr/bin/env python3
"""Terminal chat: talk to your agents and walk a post through your four decisions, without a browser.

    python3 scripts/chat_cli.py            # chat; press Tab after @ for the agent menu, after / for commands, after : for actions
    python3 scripts/chat_cli.py --demo     # try it with a stand-in AI (no account, no cost)

Type normal text to chat. Examples:
    @governance is this idea safe to post?        (talk to one agent)
    /next                                          (run a command)
    :new   :ideas   :pick 2   :draft   :previews   :pickvisual 1   :render   :check
    :approve content   :approve package   :build   :live https://...   :status   :help

Every decision (:pick, :pickvisual, :approve) makes you type APPROVE yourself, so an AI can never approve for you.
The browser app (scripts/chat_app.py) shows the same things with buttons and pictures.

Needs Python 3.8+ and nothing else (Tab completion uses readline where the system has it).
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import approvals  # noqa: E402
import chat_core as cc  # noqa: E402
import package_builder  # noqa: E402
import postkit  # noqa: E402
import publish_publora  # noqa: E402
import reminders  # noqa: E402
import visual_engine as ve  # noqa: E402

ACTIONS = {":help": "show this list", ":posts": "list your posts", ":new": "start a new post", ":open": "switch to a post (:open P-...)", ":status": "where this post is",
           ":ideas": "get 3 ideas", ":pick": "Decision 1: choose idea 1, 2 or 3", ":draft": "write the post (:draft support: your real example)", ":previews": "get 3 visual previews",
           ":pickvisual": "Decision 2: pick preview 1, 2 or 3 (no number = approve the current visual)", ":render": "render the final visual (:render square)", ":carousel": "turn the visual into a carousel",
           ":check": "run the quality checks", ":approve": "Decision 3 or 4: :approve content | :approve package", ":build": "build the ready-to-paste package", ":live": "mark as live (:live URL [24h,72h,7d] [reply:1h,6h])",
           ":autopost": "optional Publora add-on: :autopost preview|send [draft|schedule <time>] [text-only] [media <https link>]",
           ":due": "results and reply checks waiting for you", ":done": "mark a results check done (:done P-... 24h)", ":quit": "leave"}


class Shell:
    def __init__(self, ws, inp=input, out=print):
        self.ws, self.inp, self.out = os.path.abspath(ws), inp, out
        self.pipe = cc.Pipeline(self.ws)
        self.post = None
        posts = postkit.list_posts(self.ws)
        if posts:
            self.post = posts[-1]["post_id"]

    # ---- helpers
    def say(self, *lines):
        for ln in lines:
            self.out(ln)

    def need_post(self):
        if not self.post:
            raise cc.StepError("Start a post first with :new")
        return self.post

    def confirm(self, what):
        typed = self.inp("Type APPROVE to confirm %s (anything else cancels): " % what).strip()
        if typed != "APPROVE":
            raise cc.StepError("Not confirmed. Nothing was recorded.")

    def by(self):
        return postkit.owner_name(self.ws)

    # ---- actions
    def handle(self, line):
        """Run one input line. Returns False when the user wants to leave."""
        line = line.strip()
        if not line:
            return True
        try:
            if line.startswith(":"):
                return self.action(line)
            if line == "@":
                self.say(*["  @%-20s %s" % (a["name"], a["description"][:70]) for a in cc.agents(self.ws)])
                return True
            if line == "/":
                self.say(*["  /%-14s %s" % (c["name"], c["description"][:70]) for c in cc.commands(self.ws)])
                return True
            self.say("(asking your AI tool; this can take a minute...)")
            res = cc.chat(self.ws, line)
            self.say("", res["reply"], "")
            if res["has_entries"]:
                self.say("(This reply proposes memory entries. To save them use the browser app, or run scripts/memory_guard.py yourself; nothing was saved.)")
        except (cc.StepError, cc.AIError, postkit.PostError, approvals.ApprovalError, package_builder.BuildError, ve.SpecError, publish_publora.AutopostError, ValueError, RuntimeError, OSError) as exc:
            self.say("! " + str(exc))
        return True

    def action(self, line):
        cmd, _, rest = line.partition(" ")
        rest = rest.strip()
        if cmd in (":quit", ":exit", ":q"):
            return False
        if cmd == ":help":
            self.say(*["  %-12s %s" % (k, v) for k, v in ACTIONS.items()])
        elif cmd == ":posts":
            for p in postkit.list_posts(self.ws):
                self.say("%s %s  %s" % ("*" if p["post_id"] == self.post else " ", p["post_id"], p["title"]))
        elif cmd == ":new":
            self.post = self.pipe.new_post(rest)
            self.say("Started %s. Next: :ideas" % self.post)
        elif cmd == ":open":
            postkit.load_package(self.ws, rest)
            self.post = rest
            self.say("Switched to %s" % rest)
        elif cmd == ":status":
            self.show_status()
        elif cmd == ":ideas":
            self.say("(asking your AI tool...)")
            res = self.pipe.ideas(self.need_post(), rest)
            self.say(res["freshness_note"], "")
            for i, it in enumerate(res["ideas"], 1):
                self.say("%d. %s" % (i, it["title"]), "   " + it["angle"], "   Proof you will need: " + (it["proof_needed"] or "none"))
            self.say("", "Choose one with :pick 1, :pick 2 or :pick 3 (that is Decision 1).")
        elif cmd == ":pick":
            n = int(rest or 0)
            ideas = self.pipe.state(self.need_post()).get("ideas") or []
            if not 1 <= n <= len(ideas):
                raise cc.StepError("Say which idea: :pick 1, :pick 2 or :pick 3")
            self.confirm("Decision 1: the idea \"%s\"" % ideas[n - 1]["title"])
            self.pipe.choose_idea(self.post, n, "terminal", self.by())
            self.say("Decision 1 recorded. Next: :draft")
        elif cmd == ":draft":
            support = rest[len("support:"):].strip() if rest.lower().startswith("support:") else ""
            self.say("(asking your AI tool...)")
            res = self.pipe.draft(self.need_post(), "" if support else rest, support)
            if res["evidence_status"] != "OK":
                self.say("The agents need real support first:", *["  - " + g for g in res["evidence_gaps"]], "Give it with:  :draft support: <your real example or source>")
            else:
                self.say("", res["post_text"], "", "Next: :previews")
        elif cmd == ":previews":
            self.say("(asking your AI tool, then drawing the visuals...)")
            res = self.pipe.visuals(self.need_post(), rest)
            d = postkit.post_dir(self.ws, self.post)
            for p in res["previews"]:
                self.say("%d. %s: %s" % (p["number"], p["type"].replace("_", " "), p["title"]), "   " + p["reason"], "   file: " + os.path.join(d, "previews", p["png"] or p["svg"]),
                         *["   warning: " + w["message"] for w in p["warnings"]])
            self.say("Open the files to look, then :pickvisual 1, 2 or 3 (that is Decision 2).")
        elif cmd == ":pickvisual":
            n = int(rest) if rest else None
            self.confirm("Decision 2: the visual%s" % (" (preview %d)" % n if n else ""))
            self.pipe.choose_visual(self.need_post(), n, "terminal", self.by())
            self.say("Decision 2 recorded. Next: :render")
        elif cmd == ":render":
            meta = self.pipe.render(self.need_post(), rest or "portrait")
            self.say("Rendered: " + ", ".join(f["file"] for f in meta["files"]), "Folder: " + os.path.join(postkit.post_dir(self.ws, self.post), "final"), *meta["messages"],
                     *["warning: " + w["message"] for w in meta["warnings"]], "Next: :check")
        elif cmd == ":carousel":
            self.say("(asking your AI tool...)")
            self.pipe.carousel(self.need_post(), rest)
            self.say("Carousel made and rendered. Because the visual changed, approve it again with :pickvisual (Decision 2). Then :check")
        elif cmd == ":check":
            self.say("(asking your AI tool...)")
            res = self.pipe.check(self.need_post(), rest)
            self.say("Visual quality %d/100 (%s). Governance: %s." % (res["qa"]["score"], "passes" if res["qa"]["pass"] else "below the gate", res["governance"]["status"]),
                     *["  - " + x for x in res["qa"]["defects"] + res["governance"]["notes"]], *["  warning: " + w["message"] for w in res["engine"]["warnings"]],
                     "Next: :approve content")
        elif cmd == ":approve":
            what = rest.split()[0] if rest else ""
            if what == "content":
                gate = self.pipe.content_gate(self.need_post())          # records nothing; raises if governance or the visual blocks it
                self.say("You are approving exactly this post text and rendered visual:", "", postkit.read_text(self.ws, self.post))
                if gate["findings"]:
                    self.say("! Open findings: " + gate["summary"])
                    if self.inp("Type ACCEPT to approve despite those findings (anything else cancels): ").strip() != "ACCEPT":
                        raise cc.StepError("Not approved. Fix the findings (:check) or revise.")
                self.confirm("Decision 3: the post text and visual")
                self.pipe.approve_content(self.post, True, "terminal", self.by())
                self.say("Decision 3 recorded. Next: :approve package")
            elif what == "package":
                self.confirm("Decision 4: the complete package")
                self.pipe.approve_package(self.need_post(), "terminal", self.by())
                self.say("Decision 4 recorded. Next: :build")
            else:
                raise cc.StepError("Say :approve content or :approve package")
        elif cmd == ":build":
            res = self.pipe.build(self.need_post())
            self.say("Package built: " + res["folder"], "Open PACKAGE.md there and copy each part. Nothing was posted.", *["note: " + w for w in res["warnings"]])
        elif cmd == ":live":
            parts = rest.split()
            wins = parts[1].split(",") if len(parts) > 1 and not parts[1].startswith("reply:") else None
            replies = next((x[len("reply:"):].split(",") for x in parts[1:] if x.startswith("reply:")), None)
            r = self.pipe.mark_live(self.need_post(), parts[0] if parts else "", wins, replies)
            self.say("Marked live. %d reminder(s) set." % r["reminders_added"])
        elif cmd == ":autopost":
            tok = rest.split()
            action = tok[0] if tok else "preview"
            mode = "schedule" if "schedule" in tok else "draft"
            at = tok[tok.index("schedule") + 1] if mode == "schedule" and tok.index("schedule") + 1 < len(tok) else None
            media = tok[tok.index("media") + 1] if "media" in tok and tok.index("media") + 1 < len(tok) else None
            text_only = "text-only" in tok
            pre = self.pipe.autopost_preview(self.need_post(), mode, at, media, text_only)
            self.say(pre["summary"], *["note: " + w for w in pre["warnings"]], *["BLOCKED: " + p for p in pre["problems"]])
            if action == "send":
                if not pre["ok"]:
                    return True
                typed = self.inp("Type PUBLISH to create this in Publora (anything else cancels): ").strip()
                rec = self.pipe.autopost_send(self.post, mode, at, media, text_only, typed)
                self.say("Done: %s (Publora id: %s). Post the first comment by hand from PACKAGE.md." % (rec["status"], rec.get("remote_id") or "not returned"))
            else:
                self.say("Nothing was sent. To send: :autopost send ...")
        elif cmd == ":due":
            items = reminders.due(self.ws)
            self.say(*(["%s %s check was due %s" % (i["post_id"], i["window"], i["due_at"]) for i in items] or ["No results checks are waiting."]))
        elif cmd == ":done":
            a = rest.split()
            self.say("%d reminder(s) marked done" % reminders.mark(self.ws, a[0], a[1] if len(a) > 1 else None, "done"))
        else:
            self.say("Unknown action %s. Type :help" % cmd)
        return True

    def show_status(self):
        st = self.pipe.status(self.need_post())
        self.say("%s  %s" % (st["post_id"], st["title"]))
        for s in st["steps"]:
            self.say("  [%s] %s%s" % ("x" if s["done"] else (" " if s["available"] else "-"), s["label"], "" if s["done"] or s["available"] else "   (" + s["why_not"] + ")"))
        for n in (1, 2, 3, 4):
            d = st["decisions"][n]
            self.say("  Decision %d: %s" % (n, "approved" if d["current"] else ("CHANGED since approval: approve again" if d["approved"] else "not yet")))


def setup_completion(shell):
    try:
        import readline
    except ImportError:
        return
    names = [("@" + a["name"]) for a in cc.agents(shell.ws)] + [("/" + c["name"]) for c in cc.commands(shell.ws)] + list(ACTIONS)

    def completer(text, state):
        matches = [n for n in names if n.startswith(text)] if text[:1] in "@/:" else []
        return matches[state] if state < len(matches) else None
    readline.set_completer_delims(" \t\n")
    readline.set_completer(completer)
    readline.parse_and_bind("tab: complete")
    readline.parse_and_bind("bind ^I rl_complete")            # macOS libedit


def main(argv=None):
    ap = argparse.ArgumentParser(description="Terminal chat for your LinkedIn brand agents.")
    ap.add_argument("--workspace", default=os.path.dirname(HERE))
    ap.add_argument("--demo", action="store_true")
    a = ap.parse_args(argv)
    ws = os.path.abspath(a.workspace)
    if not os.path.isdir(os.path.join(ws, "docs")):
        print("error: %s does not look like an installed workspace." % ws, file=sys.stderr)
        return 2
    if a.demo:
        os.environ["LBA_AI_CMD"] = json.dumps([sys.executable, os.path.join(HERE, "demo_ai.py")])
        print("DEMO MODE: answers are canned samples from a stand-in, not a real AI.")
    sh = Shell(ws)
    setup_completion(sh)
    print("LinkedIn Brand Agents (terminal). Type :help. Press Tab after @ / or : for menus. Ctrl+D or :quit to leave.")
    while True:
        try:
            line = input("\n[%s] > " % (sh.post or "no post"))
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not sh.handle(line):
            break
    return 0


if __name__ == "__main__":
    sys.exit(main())
