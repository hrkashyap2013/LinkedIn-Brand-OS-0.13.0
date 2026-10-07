"""Tests for the setup wizard: validation, files written, re-runs, interactive flow, and the no-secrets rule."""
import io
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "runtime"))
import setup_wizard as w  # noqa: E402

BASH = shutil.which("bash")


def jread(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def jwrite(path, data):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh)


class Validation(unittest.TestCase):
    def test_days_times_offsets_and_lead(self):
        self.assertEqual(w.norm_day("thursday"), "Thu")
        self.assertEqual(w.norm_time("9:05"), "09:05")
        self.assertEqual(w.norm_time("17.30"), "17:30")
        self.assertEqual(w.norm_offset("+5:30"), "+05:30")
        self.assertEqual(w.norm_offset("-0800"), "-08:00")
        self.assertEqual(w.norm_offset("utc"), "+00:00")
        self.assertIsNone(w.norm_lead(""))
        self.assertEqual(w.norm_lead("12"), 12)
        self.assertEqual(w.norm_lead("1.5"), 1.5)
        for fn, bad in ((w.norm_day, "Funday"), (w.norm_time, "25:00"), (w.norm_time, "9am"), (w.norm_offset, "+25:00"),
                        (w.norm_offset, "five"), (w.norm_lead, "-1"), (w.norm_lead, "soon")):
            with self.assertRaises(w.WizardError, msg=bad):
                fn(bad)

    def test_one_slot_per_day_and_sorted(self):
        out = w.norm_slots([{"day": "Thu", "time": "9:00"}, {"day": "mon", "time": "08:30", "role": " A "}])
        self.assertEqual([s["day"] for s in out], ["Mon", "Thu"])
        self.assertEqual(out[0]["role"], "A")
        with self.assertRaises(w.WizardError):
            w.norm_slots([{"day": "Mon", "time": "09:00"}, {"day": "Monday", "time": "10:00"}])

    def test_choices_accept_numbers_names_and_other(self):
        self.assertEqual(w.norm_choice("2", w.IMAGE_PROVIDERS, "x"), "OpenAI")
        self.assertEqual(w.norm_choice("buff", w.POSTING_TOOLS, "x"), "Buffer")
        self.assertEqual(w.norm_choice("My own tool", w.POSTING_TOOLS, "x"), "My own tool")


class Files(unittest.TestCase):
    def setUp(self):
        self.ws = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.ws, "docs"))
        for name in ("schedule.json", "settings.json"):
            shutil.copy(os.path.join(ROOT, "docs", name), os.path.join(self.ws, "docs", name))

    def tearDown(self):
        shutil.rmtree(self.ws, ignore_errors=True)

    ANS = {"language": "French", "posting_languages": "French, English", "users": "Asha, Ben", "run_tool": "codex",
           "image_provider": "OpenAI", "posting_tool": "Buffer", "utc_offset": "+01:00", "prep_lead_hours": 12,
           "slots": [{"day": "Tue", "time": "08:00", "role": "Education"}, {"day": "Fri", "time": "17:30"}],
           "desktop": True, "phone": True}

    def test_answers_are_written_to_the_right_files(self):
        res = w.apply_answers(self.ws, self.ANS)
        s = jread(os.path.join(self.ws, "docs", "settings.json"))
        sc = jread(os.path.join(self.ws, "docs", "schedule.json"))
        self.assertTrue(s["setup_completed"])
        self.assertEqual((s["language"], s["posting_languages"], s["users"], s["run_tool"]), ("French", ["French", "English"], ["Asha", "Ben"], "codex"))
        self.assertEqual((s["image_provider"], s["posting_tool"]), ("OpenAI", "Buffer"))
        self.assertEqual(s["notifications"], {"desktop": True, "phone": True, "phone_server": "https://ntfy.sh"})
        self.assertEqual((sc["publish_utc_offset"], sc["prep_lead_hours"]), ("+01:00", 12))
        self.assertEqual([x["day"] for x in sc["slots"]], ["Tue", "Fri"])
        self.assertFalse(sc["paused"])
        # the phone topic is private: local file only, never in settings or schedule
        topic = jread(os.path.join(self.ws, "config.local.json"))["ntfy_topic"]
        self.assertTrue(topic.startswith("lba-") and len(topic) > 20)
        self.assertEqual(topic, res["topic"])
        for f in ("settings.json", "schedule.json"):
            with open(os.path.join(self.ws, "docs", f)) as fh:
                self.assertNotIn(topic, fh.read())
        if os.name != "nt":
            self.assertEqual(stat.S_IMODE(os.stat(os.path.join(self.ws, "config.local.json")).st_mode), 0o600)

    def test_rerun_keeps_topic_and_earlier_answers_and_makes_backups(self):
        first = w.apply_answers(self.ws, self.ANS)["topic"]
        second = w.apply_answers(self.ws, {"language": "German"})
        self.assertEqual(second["topic"], first)
        self.assertFalse(second["new_topic"])
        s = jread(os.path.join(self.ws, "docs", "settings.json"))
        sc = jread(os.path.join(self.ws, "docs", "schedule.json"))
        self.assertEqual((s["language"], s["users"], s["run_tool"]), ("German", ["Asha", "Ben"], "codex"))   # untouched answers survive
        self.assertEqual(len(sc["slots"]), 2)
        self.assertTrue([f for f in os.listdir(os.path.join(self.ws, "docs")) if f.startswith("settings.json.bak.")])

    def test_blank_lead_time_stays_blank_and_is_never_guessed(self):
        w.apply_answers(self.ws, dict(self.ANS, prep_lead_hours=""))
        self.assertIsNone(jread(os.path.join(self.ws, "docs", "schedule.json"))["prep_lead_hours"])

    def test_bad_answers_change_nothing(self):
        before = jread(os.path.join(self.ws, "docs", "schedule.json"))
        for bad in ({"slots": [{"day": "Mon", "time": "99:00"}]}, {"utc_offset": "nope"}, {"run_tool": "chatbot"},
                    {"phone": True, "phone_server": "http://example.com"}):
            with self.assertRaises(w.WizardError):
                w.apply_answers(self.ws, bad)
        self.assertEqual(jread(os.path.join(self.ws, "docs", "schedule.json")), before)
        self.assertFalse(os.path.exists(os.path.join(self.ws, "config.local.json")))

    def test_phone_off_creates_no_topic(self):
        w.apply_answers(self.ws, dict(self.ANS, phone=False))
        self.assertFalse(os.path.exists(os.path.join(self.ws, "config.local.json")))

    def test_custom_server_is_kept_in_the_local_file(self):
        w.apply_answers(self.ws, dict(self.ANS, phone_server="https://ntfy.example.org/"))
        self.assertEqual(jread(os.path.join(self.ws, "config.local.json"))["ntfy_server"], "https://ntfy.example.org")

    def test_humanizer_strength_defaults_to_strict_and_auto_post_to_off(self):
        w.apply_answers(self.ws, {"language": "English"})
        s = jread(os.path.join(self.ws, "docs", "settings.json"))
        self.assertEqual(s["humanizer_tier"], "strict")
        self.assertEqual(s["auto_post"], {"provider": "publora", "enabled": False})

    def test_auto_post_is_only_on_when_asked_and_a_bad_tier_is_refused(self):
        w.apply_answers(self.ws, {"auto_post": True, "humanizer_tier": "Forensic"})
        s = jread(os.path.join(self.ws, "docs", "settings.json"))
        self.assertEqual((s["humanizer_tier"], s["auto_post"]["enabled"]), ("forensic", True))
        w.apply_answers(self.ws, {"language": "French"})                                    # a later run keeps both choices
        s = jread(os.path.join(self.ws, "docs", "settings.json"))
        self.assertEqual((s["humanizer_tier"], s["auto_post"]["enabled"]), ("forensic", True))
        with self.assertRaises(w.WizardError):
            w.apply_answers(self.ws, {"humanizer_tier": "maximum"})

    def test_no_api_key_or_password_field_exists_anywhere(self):
        w.apply_answers(self.ws, self.ANS)
        text = json.dumps(jread(os.path.join(self.ws, "docs", "settings.json"))).lower()
        for word in ("api_key", "apikey", "password", "token", "secret"):
            self.assertNotIn(word, text.replace("no secrets", "").replace("never stored", ""), word)


class Interactive(unittest.TestCase):
    def setUp(self):
        self.ws = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.ws, "docs"))
        for name in ("schedule.json", "settings.json"):
            shutil.copy(os.path.join(ROOT, "docs", name), os.path.join(self.ws, "docs", name))

    def tearDown(self):
        shutil.rmtree(self.ws, ignore_errors=True)

    def test_full_question_flow_with_typos_corrected(self):
        typed = iter([
            "English",            # language
            "",                   # posting language: default (English)
            "Sam, Kim",           # users
            "claude",             # run tool
            "2",                  # image provider -> OpenAI
            "Hootsuite",          # posting tool
            "Funday", "mon",      # day: bad, then good
            "25:00", "9:00",      # time: bad, then good
            "Education",          # role
            "y",                  # add another
            "mon", "thu",         # duplicate day, then new one
            "17:30", "",          # time, no role
            "n",                  # no more
            "+5:30",              # offset
            "12",                 # lead
            "y",                  # desktop
            "y",                  # phone
            "",                   # server default
            "",                   # humanizer strength: default (strict)
            "n",                  # optional auto-post add-on: no
        ])
        shown = []
        ask = w.Asker(inp=lambda prompt: next(typed), out=shown.append)
        answers = w.interview(self.ws, ask)
        self.assertEqual(answers["image_provider"], "OpenAI")
        self.assertEqual(answers["slots"], [{"day": "Mon", "time": "09:00", "role": "Education"}, {"day": "Thu", "time": "17:30", "role": ""}])
        text = "\n".join(shown)
        self.assertIn("is not a day", text)
        self.assertIn("is not a time", text)
        self.assertIn("already added", text)
        self.assertNotRegex(text.lower(), r"api key:|password:")
        self.assertEqual((answers["humanizer_tier"], answers["auto_post"]), ("strict", False))
        w.apply_answers(self.ws, answers)
        sc = jread(os.path.join(self.ws, "docs", "schedule.json"))
        self.assertEqual((sc["publish_utc_offset"], sc["prep_lead_hours"], len(sc["slots"])), ("+05:30", 12, 2))

    def test_end_of_input_aborts_without_writing(self):
        def eof(_):
            raise EOFError
        with self.assertRaises(w.WizardError):
            w.interview(self.ws, w.Asker(inp=eof, out=lambda *_: None))
        self.assertFalse(jread(os.path.join(self.ws, "docs", "settings.json"))["setup_completed"])


class Cli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.ws = os.path.join(self.tmp, "ws")
        self.env = dict(os.environ, HOME=self.tmp, PYTHONDONTWRITEBYTECODE="1")
        if BASH and os.name != "nt":
            subprocess.run([BASH, os.path.join(ROOT, "install.sh"), "--project", self.ws], capture_output=True, env=self.env, check=True)
        self.answers = os.path.join(self.tmp, "answers.json")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_wizard(self, *args, stdin=None):
        return subprocess.run([sys.executable, os.path.join(self.ws, "scripts", "setup_wizard.py"), "--workspace", self.ws, *args],
                              capture_output=True, text=True, env=self.env, input=stdin)

    @unittest.skipUnless(BASH and os.name != "nt", "needs bash")
    def test_answers_file_end_to_end_with_register_and_show(self):
        store = os.path.join(self.tmp, "cron.store")
        fake = os.path.join(self.tmp, "fakecron")
        with open(fake, "w") as fh:
            fh.write('#!/usr/bin/env bash\ncase "$1" in -l) cat "%s" 2>/dev/null ;; -) cat > "%s" ;; esac\n' % (store, store))
        os.chmod(fake, os.stat(fake).st_mode | stat.S_IEXEC)
        self.env["CRONTAB_CMD"] = fake
        jwrite(self.answers, dict(Files.ANS, phone=False, desktop=False))
        r = self.run_wizard("--answers", self.answers, "--register")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("Saved. Your setup", r.stdout)
        with open(store) as fh:
            cron = fh.read()
        self.assertEqual(cron.count("run-scheduled"), 2)
        self.assertIn("--tool codex", cron)
        shown = self.run_wizard("--show")
        self.assertEqual(shown.returncode, 0)
        self.assertIn("French", shown.stdout)

    @unittest.skipUnless(BASH and os.name != "nt", "needs bash")
    def test_register_is_skipped_when_lead_time_is_missing(self):
        jwrite(self.answers, dict(Files.ANS, phone=False, desktop=False, prep_lead_hours=""))
        r = self.run_wizard("--answers", self.answers, "--register")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("Skipped", r.stdout)

    @unittest.skipUnless(BASH and os.name != "nt", "needs bash")
    def test_no_terminal_and_no_answers_file_is_a_clear_error(self):
        r = self.run_wizard(stdin="")
        self.assertEqual(r.returncode, 1)
        self.assertIn("needs a terminal", r.stderr)

    @unittest.skipUnless(BASH and os.name != "nt", "needs bash")
    def test_show_before_setup_says_so(self):
        r = self.run_wizard("--show")
        self.assertEqual(r.returncode, 1)
        self.assertIn("has not been run", r.stdout)


if __name__ == "__main__":
    unittest.main()
