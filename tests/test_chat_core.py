"""Edge cases of the shared chat engine: JSON extraction, prompt size, missing tools, timeouts, one job at a time."""
import json
import os
import shutil
import sys
import threading
import time
import unittest

from tests.helpers import jdump, make_workspace, wtext

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "runtime"))
import chat_core as cc  # noqa: E402


class Json(unittest.TestCase):
    def test_extract_json_variants(self):
        self.assertEqual(cc.extract_json('text\n```json\n{"a": 1}\n```\nmore'), {"a": 1})
        self.assertEqual(cc.extract_json('```\n{"a": 2}\n```'), {"a": 2})
        self.assertEqual(cc.extract_json('Sure! {"a": 3, "b": {"c": [1, 2]}} hope that helps'), {"a": 3, "b": {"c": [1, 2]}})
        self.assertEqual(cc.extract_json('```json\n{"bad": }\n```\n```json\n{"ok": true}\n```'), {"ok": True})
        self.assertEqual(cc.extract_json('first ```json\n{"x": 1}\n``` then ```json\n{"x": 2}\n```'), {"x": 2})      # the last valid block wins
        with self.assertRaises(ValueError):
            cc.extract_json("no json here at all")

    def test_validators_reject_malformed_answers_with_specific_reasons(self):
        self.assertIn("exactly 3", cc.validate_ideas({"ideas": [{"title": "a"}]})[1][0])
        self.assertIn("different", cc.validate_ideas({"ideas": [{"title": "a"}, {"title": "A"}, {"title": "a"}]})[1][0])
        self.assertTrue(cc.validate_draft({"post_text": "short"})[1])
        self.assertTrue(cc.validate_draft({"evidence_status": "INSUFFICIENT EVIDENCE"})[1])             # needs the gaps listed
        self.assertEqual(cc.validate_draft({"evidence_status": "INSUFFICIENT EVIDENCE", "evidence_gaps": ["a real example"]})[1], [])
        errs = cc.validate_visuals({"previews": [{"spec": {"type": "funnel", "title": "t"}}] * 3})[1]
        self.assertTrue(any("levels" in e for e in errs))
        self.assertTrue(cc.validate_check({"qa": {"score": "high"}})[1])
        self.assertEqual(cc.validate_check({"qa": {"score": 150}, "governance": {"status": "proceed"}})[0]["qa"]["score"], 100)

    def test_mentions_only_count_real_agents(self):
        self.assertEqual(cc.parse_mentions("@governance and @writing please, @nobody and me@example.com", ["governance", "writing"]), ["governance", "writing"])


class Prompts(unittest.TestCase):
    def setUp(self):
        self.ws = make_workspace({"language": "English"})

    def tearDown(self):
        shutil.rmtree(self.ws, ignore_errors=True)

    def test_every_stage_fits_even_with_a_huge_profile_and_full_registers(self):
        with open(os.path.join(self.ws, "docs", "brand-profile.md"), "a") as fh:
            fh.write("\n## Extra\n- Voice: " + "practical and direct. " * 2000)
        for reg in ("content-memory", "visual-memory", "ideas-and-examples", "experience-bank", "evidence-library"):
            path = os.path.join(self.ws, "memory", reg + ".md")
            with open(path, "a") as fh:
                ncols = open(path).read().split("|---")[0].count("|") - 1
                for i in range(80):
                    fh.write("| " + " | ".join(["row %d " % i + "x" * 60] * ncols) + " |\n")
        for stage in cc.STAGE_AGENTS:
            text = cc.stage_prompt(self.ws, stage, "task", "{}")
            self.assertLessEqual(len(text), cc.MAX_PROMPT, stage)
            self.assertIn("LBA-STAGE: " + stage, text)
        self.assertLessEqual(len(cc.chat_prompt(self.ws, "hi", [{"role": "owner", "text": "x" * 5000}] * 9, [])), cc.MAX_PROMPT)

    def test_omitted_memory_is_declared_not_passed_off_as_empty(self):
        self.assertIn("could not be checked", cc.context_block(self.ws, 1200, 0))
        path = os.path.join(self.ws, "memory", "content-memory.md")
        with open(path, "a") as fh:
            fh.write("| row-marker |\n")
        self.assertNotIn("row-marker", cc.context_block(self.ws, 1200, 0))

    def test_shared_rules_are_sent_once_not_once_per_agent(self):
        text = cc.stage_prompt(self.ws, "ideas", "task", "{}")
        self.assertEqual(text.count("## Shared rules"), 1)

    def test_blank_profile_fields_are_not_listed_and_the_owner_is_told_not_to_guess(self):
        profile = cc.profile_text(self.ws, 9999)
        self.assertNotRegex(profile, r"- Name:\s*$")
        self.assertIn("Never guess", profile)

    def test_empty_memory_is_declared_not_hidden(self):
        self.assertIn("nothing to check against", cc.context_block(self.ws))

    def test_a_slash_command_becomes_its_instruction(self):
        text = cc.expand_command(self.ws, "/next about onboarding")
        self.assertIn("ran the command /next", text)
        self.assertIn("onboarding", text)
        self.assertEqual(cc.expand_command(self.ws, "/not-a-command x"), "/not-a-command x")


class Runner(unittest.TestCase):
    def setUp(self):
        self.ws = make_workspace()
        self.saved = {k: os.environ.get(k) for k in ("LBA_AI_CMD", "PATH", "CLAUDE_BIN", "CODEX_BIN", "LBA_AI_TIMEOUT")}

    def tearDown(self):
        for k, v in self.saved.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
        shutil.rmtree(self.ws, ignore_errors=True)

    def test_missing_tools_give_an_actionable_message(self):
        os.environ.pop("LBA_AI_CMD", None)
        os.environ["CLAUDE_BIN"] = "definitely-not-installed-claude"
        os.environ["CODEX_BIN"] = "definitely-not-installed-codex"
        with self.assertRaises(cc.AIError) as cm:
            cc.run_ai(self.ws, "hello")
        self.assertIn("--demo", str(cm.exception))
        jdump({"run_tool": "codex"}, os.path.join(self.ws, "docs", "settings.json"))
        with self.assertRaises(cc.AIError) as cm:
            cc.run_ai(self.ws, "hello")
        self.assertIn("codex", str(cm.exception))

    @unittest.skipIf(os.name == "nt", "uses a POSIX script as the stand-in tool")
    def test_real_tool_command_lines_are_built_the_documented_way(self):
        os.environ.pop("LBA_AI_CMD", None)
        stub = os.path.join(self.ws, "claude")
        wtext(stub, "#!/bin/sh\n")
        os.chmod(stub, 0o755)
        os.environ["CLAUDE_BIN"] = stub
        os.environ["CLAUDE_EXTRA_ARGS"] = "--model sonnet"
        argv, stdin_text = cc.ai_command(self.ws, "THE PROMPT")
        self.assertEqual(argv, [stub, "-p", "THE PROMPT", "--model", "sonnet"])
        self.assertIsNone(stdin_text)
        os.environ.pop("CLAUDE_EXTRA_ARGS")
        os.environ["CODEX_BIN"] = stub
        jdump({"run_tool": "codex"}, os.path.join(self.ws, "docs", "settings.json"))
        self.assertEqual(cc.ai_command(self.ws, "P")[0], [stub, "exec", "P"])

    def test_batch_shims_are_recognised_only_on_windows(self):
        self.assertTrue(cc.is_batch_shim("C:\\npm\\claude.cmd", "Windows"))
        self.assertTrue(cc.is_batch_shim("C:\\npm\\codex.BAT", "Windows"))
        self.assertFalse(cc.is_batch_shim("C:\\bin\\claude.exe", "Windows"))
        self.assertFalse(cc.is_batch_shim("/usr/local/bin/claude", "Linux"))
        self.assertFalse(cc.is_batch_shim("/opt/x/claude.cmd", "Darwin"))

    @unittest.skipUnless(os.name == "nt", "a .cmd shim only matters on Windows")
    def test_on_windows_a_cmd_shim_is_refused_unless_the_owner_allows_it(self):
        os.environ.pop("LBA_AI_CMD", None)
        stub = os.path.join(self.ws, "claude.cmd")
        wtext(stub, "@echo off\r\n")
        os.environ["CLAUDE_BIN"] = stub
        with self.assertRaises(cc.AIError) as cm:
            cc.ai_command(self.ws, "P & whoami")
        self.assertIn("batch shim", str(cm.exception))
        self.assertIn("LBA_ALLOW_CMD_SHIM", str(cm.exception))
        os.environ["LBA_ALLOW_CMD_SHIM"] = "1"
        try:
            self.assertEqual(cc.ai_command(self.ws, "P")[0][1:], ["-p", "P"])
        finally:
            os.environ.pop("LBA_ALLOW_CMD_SHIM", None)

    @unittest.skipIf(os.name == "nt", "uses a POSIX shell script as the stand-in tool")
    def test_the_tool_gets_the_prompt_as_an_argument_and_no_terminal_input(self):
        os.environ.pop("LBA_AI_CMD", None)
        stub = os.path.join(self.ws, "claude")
        wtext(stub, '#!/bin/sh\n[ "$1" = "-p" ] || exit 9\nread -t 1 line && echo "STDIN:$line" || true\necho "got: $2"\n')
        os.chmod(stub, 0o755)
        os.environ["CLAUDE_BIN"] = stub
        out = cc.run_ai(self.ws, "hello world")
        self.assertIn("got: hello world", out)
        self.assertNotIn("STDIN:", out)

    def test_a_failing_tool_reports_its_own_message(self):
        os.environ["LBA_AI_CMD"] = json.dumps([sys.executable, "-c", "import sys; sys.stderr.write('quota exceeded'); sys.exit(3)"])
        with self.assertRaises(cc.AIError) as cm:
            cc.run_ai(self.ws, "x")
        self.assertIn("quota exceeded", str(cm.exception))
        self.assertIn("3", str(cm.exception))

    def test_a_slow_tool_is_stopped(self):
        os.environ["LBA_AI_CMD"] = json.dumps([sys.executable, "-c", "import time; time.sleep(30)"])
        started = time.time()
        with self.assertRaises(cc.AIError) as cm:
            cc.run_ai(self.ws, "x", timeout=1)
        self.assertIn("longer than", str(cm.exception))
        self.assertLess(time.time() - started, 10)

    def test_an_oversized_request_is_refused_before_running_anything(self):
        os.environ["LBA_AI_CMD"] = json.dumps([sys.executable, "-c", "raise SystemExit('should not run')"])
        with self.assertRaises(cc.AIError) as cm:
            cc.run_ai(self.ws, "x" * (cc.MAX_PROMPT + 1))
        self.assertIn("too large", str(cm.exception))

    def test_ask_json_retries_once_then_gives_up_clearly(self):
        os.environ["LBA_AI_CMD"] = json.dumps([sys.executable, "-c", "print('{\"ideas\": []}')"])
        with self.assertRaises(cc.AIError) as cm:
            cc.ask_json(self.ws, "p", cc.validate_ideas)
        self.assertIn("could not be used after a retry", str(cm.exception))


class OneJobAtATime(unittest.TestCase):
    def test_a_second_slow_step_is_refused_while_one_runs(self):
        jobs = cc.Jobs()
        gate = threading.Event()
        first = jobs.start("slow", lambda: gate.wait(5) or "done")
        with self.assertRaises(cc.StepError):
            jobs.start("another", lambda: 1)
        gate.set()
        for _ in range(100):
            if jobs.get(first)["state"] != "running":
                break
            time.sleep(0.05)
        self.assertEqual(jobs.get(first)["state"], "done")
        self.assertEqual(jobs.get(jobs.start("third", lambda: 7))["state"] in ("running", "done"), True)

    def test_an_unexpected_crash_becomes_an_error_not_a_hang(self):
        jobs = cc.Jobs()
        jid = jobs.start("boom", lambda: 1 / 0)
        for _ in range(100):
            if jobs.get(jid)["state"] != "running":
                break
            time.sleep(0.05)
        self.assertEqual(jobs.get(jid)["state"], "error")
        self.assertIn("Unexpected", jobs.get(jid)["error"])


if __name__ == "__main__":
    unittest.main()
