"""Tests for the terminal chat app, driven line by line with typed input."""
import json
import os
import shutil
import sys
import unittest

from tests.helpers import AGENT_COUNT, COMMAND_COUNT, SKILL_COUNT, make_workspace, rtext

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "runtime"))
import approvals  # noqa: E402
import chat_cli  # noqa: E402
import postkit  # noqa: E402


class Cli(unittest.TestCase):
    def setUp(self):
        self.ws = make_workspace({"users": ["Priya"], "setup_completed": True, "language": "English"})
        self.saved = {k: os.environ.get(k) for k in ("LBA_AI_CMD", "LBA_BROWSER")}
        os.environ["LBA_AI_CMD"] = json.dumps([sys.executable, os.path.join(ROOT, "runtime", "demo_ai.py")])
        os.environ["LBA_BROWSER"] = ""
        self.typed, self.lines = [], []
        self.sh = chat_cli.Shell(self.ws, inp=lambda prompt: self.typed.pop(0), out=self.lines.append)

    def tearDown(self):
        for k, v in self.saved.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
        shutil.rmtree(self.ws, ignore_errors=True)

    def run_line(self, line, typed=()):
        self.typed = list(typed)
        self.lines.clear()
        self.sh.handle(line)
        return "\n".join(self.lines)

    def test_full_journey_with_typed_approvals(self):
        self.assertIn("Started P-", self.run_line(":new"))
        self.assertIn("Weekly reviews fail", self.run_line(":ideas"))
        self.assertIn("Decision 1 recorded", self.run_line(":pick 1", ["APPROVE"]))
        self.assertIn("Most weekly reviews", self.run_line(":draft"))
        self.assertIn("process flow", self.run_line(":previews"))
        self.assertIn("Decision 2 recorded", self.run_line(":pickvisual 1", ["APPROVE"]))
        self.assertIn("visual.svg", self.run_line(":render"))
        self.assertIn("92/100", self.run_line(":check"))
        self.assertIn("Decision 3 recorded", self.run_line(":approve content", ["APPROVE"]))
        self.assertIn("Decision 4 recorded", self.run_line(":approve package", ["APPROVE"]))
        self.assertIn("Package built", self.run_line(":build"))
        status = self.run_line(":status")
        self.assertEqual(status.count("approved"), 4)
        self.assertIn("Marked live", self.run_line(":live https://example.com/p 24h,7d"))
        rows = approvals.decisions_for(self.ws, self.sh.post)
        self.assertEqual({d: r["Notes"] for d, r in rows.items()}.values().__len__(), 4)
        self.assertTrue(all("typing APPROVE" in r["Notes"] for r in rows.values()))

    def test_anything_but_approve_records_nothing(self):
        self.run_line(":new"); self.run_line(":ideas")
        for typed in ("approve", "yes", "", "APPROVE please"):
            out = self.run_line(":pick 1", [typed])
            self.assertIn("Not confirmed", out)
        self.assertEqual(approvals.decisions_for(self.ws, self.sh.post), {})

    def test_content_approval_asks_even_when_nothing_is_open_and_blocks_on_findings(self):
        for line, typed in ((":new", []), (":ideas", []), (":pick 1", ["APPROVE"]), (":draft", []), (":previews", []), (":pickvisual 1", ["APPROVE"]), (":render", []), (":check", [])):
            self.run_line(line, typed)
        self.assertIn("Not confirmed", self.run_line(":approve content", ["nope"]))
        self.assertNotIn(3, approvals.decisions_for(self.ws, self.sh.post))
        state = os.path.join(self.ws, "drafts", self.sh.post, "state.json")
        data = json.loads(rtext(state)); data["check"]["qa"]["defects"] = ["labels too small"]
        with open(state, "w") as fh:
            json.dump(data, fh)
        out = self.run_line(":approve content", ["no", ])
        self.assertIn("Open findings", out)
        self.assertNotIn(3, approvals.decisions_for(self.ws, self.sh.post))
        self.assertIn("Decision 3 recorded", self.run_line(":approve content", ["ACCEPT", "APPROVE"]))

    def test_steps_out_of_order_explain_what_to_do(self):
        self.run_line(":new")
        self.assertIn("Choose one of the 3 ideas", self.run_line(":draft"))
        self.assertIn("Say which idea", self.run_line(":pick"))
        self.assertIn("Start a post first", chat_cli.Shell(make_workspace(), out=self.lines.append).handle(":ideas") and "\n".join(self.lines))

    def test_chat_with_agent_and_menus(self):
        self.assertIn("Demo stand-in", self.run_line("@governance check this"))
        out = self.run_line("@")
        self.assertEqual(out.count("\n") + 1, AGENT_COUNT)
        self.assertIn("/next", self.run_line("/"))
        self.assertIn("Unknown action", self.run_line(":bogus"))
        self.assertFalse(self.sh.handle(":quit"))

    def test_the_command_line_entry_point_runs_and_quits(self):
        import builtins
        import contextlib
        import io
        feed = iter([":help", ":quit"])
        real = builtins.input
        builtins.input = lambda prompt="": next(feed)
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                code = chat_cli.main(["--workspace", self.ws])
        finally:
            builtins.input = real
        self.assertEqual(code, 0)
        self.assertIn(":approve", buf.getvalue())
        self.assertIn("Type :help", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
