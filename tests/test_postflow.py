"""Tests for the post lifecycle: package fields, fingerprints, the four decisions, and the ready-to-paste package."""
import json
import os
import shutil
import subprocess
import sys
import unittest

from tests.helpers import jdump, jload, make_workspace, rtext, wtext

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "runtime"))
import approvals  # noqa: E402
import package_builder as pb  # noqa: E402
import postkit  # noqa: E402
import visual_engine as ve  # noqa: E402

TEXT = "Most weekly reviews fail in week 3.\n\nBecause nobody decided what the review is for.\n"
FIELDS = {"idea": {"title": "Reviews need a purpose", "angle": "Give the review one job"}, "suggested_time": "Tue 08:00 (UTC+05:30)",
          "first_comment": "What decision should your review end with?", "pin_comment": "Template in my profile.",
          "hashtags": ["productivity", "#leadership"], "mentions": ["@someone"], "reply_starters": ["Good point."], "cta_type": "Conversation"}


class Base(unittest.TestCase):
    def setUp(self):
        self.ws = make_workspace({"users": ["Asha"], "posting_tool": "Buffer", "setup_completed": True})
        self.id = postkit.new_post(self.ws, "Why reviews stick", "Utility")

    def tearDown(self):
        shutil.rmtree(self.ws, ignore_errors=True)

    def ready(self, approve_all=False):
        postkit.save_text(self.ws, self.id, TEXT)
        postkit.set_fields(self.ws, self.id, FIELDS)
        postkit.save_visual_spec(self.ws, self.id, ve.EXAMPLES["process_flow"])
        postkit.render_final(self.ws, self.id, png=False)
        if approve_all:
            for d, w in ((1, "idea"), (2, "visual"), (3, "content"), (4, "package")):
                approvals.record(self.ws, self.id, d, w, "app")


class Fields(Base):
    def test_new_post_ids_increment_and_are_validated(self):
        second = postkit.new_post(self.ws, "Another")
        self.assertNotEqual(self.id, second)
        self.assertRegex(self.id, r"^P-\d{8}-01$")
        for bad in ("../x", "P-1", "post", ""):
            with self.assertRaises(postkit.PostError):
                postkit.check_id(bad)

    def test_unknown_or_malformed_fields_are_rejected_not_dropped(self):
        for bad in ({"nonsense": "x"}, {"hashtags": "not a list"}, {"first_comment": 5}, {"measurement_windows": ["5h"]}, {"idea": "text"}):
            with self.assertRaises((postkit.PostError, ValueError), msg=bad):
                postkit.set_fields(self.ws, self.id, bad)

    def test_text_is_normalised_and_empty_text_refused(self):
        postkit.save_text(self.ws, self.id, "Line one   \r\nLine two\r\n\r\n\r\n")
        self.assertEqual(postkit.read_text(self.ws, self.id), "Line one\nLine two\n")
        with self.assertRaises(postkit.PostError):
            postkit.save_text(self.ws, self.id, "   \n")

    def test_invalid_visual_spec_is_refused(self):
        with self.assertRaises(postkit.PostError):
            postkit.save_visual_spec(self.ws, self.id, {"type": "funnel", "title": "x"})


class Fingerprints(Base):
    def test_every_change_to_approved_content_changes_a_fingerprint(self):
        self.ready()
        base = postkit.fingerprints(self.ws, self.id)
        self.assertTrue(all(base.values()), base)
        postkit.save_text(self.ws, self.id, TEXT.replace("week 3", "week 4"))
        after_text = postkit.fingerprints(self.ws, self.id)
        self.assertNotEqual(base["content"], after_text["content"])
        self.assertNotEqual(base["package"], after_text["package"])
        self.assertEqual(base["visual"], after_text["visual"])
        postkit.save_text(self.ws, self.id, TEXT)
        postkit.set_fields(self.ws, self.id, {"first_comment": "changed"})
        after_field = postkit.fingerprints(self.ws, self.id)
        self.assertEqual(base["content"], after_field["content"])       # a comment is not "content" (decision 3)...
        self.assertNotEqual(base["package"], after_field["package"])    # ...but it is part of the package (decision 4)

    def test_notes_do_not_invalidate_approvals(self):
        self.ready()
        before = postkit.fingerprints(self.ws, self.id)["package"]
        postkit.set_fields(self.ws, self.id, {"notes": "private reminder to self"})
        self.assertEqual(before, postkit.fingerprints(self.ws, self.id)["package"])

    def test_changing_the_picked_visual_makes_the_render_stale(self):
        self.ready()
        postkit.save_visual_spec(self.ws, self.id, ve.EXAMPLES["checklist"])
        st = postkit.status(self.ws, self.id)
        self.assertIsNone(st["fingerprints"]["content"])
        self.assertTrue(any("out of date" in m for m in st["missing"]))
        postkit.render_final(self.ws, self.id, png=False)
        self.assertIsNotNone(postkit.fingerprints(self.ws, self.id)["content"])

    def test_re_render_removes_old_files(self):
        self.ready()
        stale = os.path.join(postkit.post_dir(self.ws, self.id), "final", "visual-old.png")
        wtext(stale, "x")
        postkit.render_final(self.ws, self.id, png=False)
        self.assertFalse(os.path.exists(stale))


class Decisions(Base):
    def test_all_four_are_required_and_missing_ones_are_named(self):
        self.ready()
        ok, problems = approvals.verify(self.ws, self.id)
        self.assertFalse(ok)
        self.assertEqual(len(problems), 4)
        approvals.record(self.ws, self.id, 1, "idea", "app")
        approvals.record(self.ws, self.id, 2, "visual", "app")
        ok, problems = approvals.verify(self.ws, self.id)
        self.assertEqual([p.split(":")[0] for p in problems], ["Decision 3 is missing", "Decision 4 is missing"])

    def test_decision_four_needs_decision_three_first(self):
        self.ready()
        with self.assertRaises(approvals.ApprovalError):
            approvals.record(self.ws, self.id, 4, "package", "app")

    def test_cannot_approve_what_does_not_exist_yet(self):
        with self.assertRaises(approvals.ApprovalError):
            approvals.record(self.ws, self.id, 3, "content", "app")
        with self.assertRaises(approvals.ApprovalError):
            approvals.record(self.ws, self.id, 2, "visual", "app")

    def test_all_four_pass_then_any_edit_breaks_them(self):
        self.ready(approve_all=True)
        self.assertEqual(approvals.verify(self.ws, self.id), (True, []))
        postkit.save_text(self.ws, self.id, TEXT + "One more line.\n")
        ok, problems = approvals.verify(self.ws, self.id)
        self.assertFalse(ok)
        self.assertTrue(any(p.startswith("Decision 3") for p in problems) and any(p.startswith("Decision 4") for p in problems))
        self.assertFalse(any(p.startswith("Decision 1") or p.startswith("Decision 2") for p in problems))
        postkit.save_text(self.ws, self.id, TEXT)                       # revert: the old approvals apply again
        self.assertTrue(approvals.verify(self.ws, self.id)[0])

    def test_approval_of_one_post_never_covers_another(self):
        self.ready(approve_all=True)
        other = postkit.new_post(self.ws, "Other")
        postkit.save_text(self.ws, other, TEXT)
        postkit.set_fields(self.ws, other, FIELDS)
        postkit.save_visual_spec(self.ws, other, ve.EXAMPLES["process_flow"])
        postkit.render_final(self.ws, other, png=False)
        self.assertFalse(approvals.verify(self.ws, other)[0])

    def test_a_chat_approval_must_carry_the_owners_words(self):
        self.ready()
        with self.assertRaises(approvals.ApprovalError):
            approvals.record(self.ws, self.id, 1, "idea", "chat")
        approvals.record(self.ws, self.id, 1, "idea", "chat", quote="yes, go with that one")
        row = approvals.decisions_for(self.ws, self.id)[1]
        self.assertIn("yes, go with that one", row["Notes"])
        self.assertIn("AI assistant", row["Notes"])
        self.assertEqual(row["Approved by"], "Asha")

    def test_the_command_line_refuses_terminal_approval_without_a_keyboard(self):
        self.ready()
        r = subprocess.run([sys.executable, os.path.join(self.ws, "scripts", "approvals.py"), "--workspace", self.ws, "record", "--post-id", self.id,
                            "--decision", "1", "--what", "idea", "--via", "terminal"], capture_output=True, text=True, stdin=subprocess.DEVNULL)
        self.assertEqual(r.returncode, 2)
        self.assertEqual(approvals.decisions_for(self.ws, self.id), {})

    def test_app_is_not_available_from_the_command_line(self):
        r = subprocess.run([sys.executable, os.path.join(self.ws, "scripts", "approvals.py"), "--workspace", self.ws, "record", "--post-id", self.id,
                            "--decision", "1", "--what", "x", "--via", "app"], capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)        # argparse rejects it: only a program in-process can claim 'app'

    def test_rows_go_through_the_write_guard_with_backup(self):
        self.ready()
        approvals.record(self.ws, self.id, 1, "idea", "app")
        self.assertTrue(os.listdir(os.path.join(self.ws, "memory", ".history")))
        log = rtext(os.path.join(self.ws, "memory", "approval-log.md"))
        self.assertIn("idea:" + postkit.fingerprints(self.ws, self.id)["idea"], log)


class Package(Base):
    def test_build_is_refused_until_everything_matches(self):
        self.ready()
        with self.assertRaises(pb.BuildError) as cm:
            pb.build(self.ws, self.id)
        self.assertIn("Decision 1 is missing", str(cm.exception))
        self.assertFalse(os.path.exists(os.path.join(self.ws, "exports")))

    def test_build_makes_every_part_and_a_manifest(self):
        self.ready(approve_all=True)
        res = pb.build(self.ws, self.id)
        folder = res["folder"]
        for f in ("PACKAGE.md", "post.txt", "first-comment.txt", "pin-comment.txt", "suggested-time.txt", "alt-text.txt", "visual-prompt.txt", "visual.svg", "MANIFEST.json"):
            self.assertTrue(os.path.exists(os.path.join(folder, f)), f)
        md = rtext(os.path.join(folder, "PACKAGE.md"))
        for part in ("Suggested time", "Post text", "First comment", "Comment to pin", "#productivity #leadership", "@someone", "Visual prompt", "Posting checklist", "Nothing has been posted"):
            self.assertIn(part, md)
        self.assertEqual(rtext(os.path.join(folder, "post.txt")).strip(), TEXT.strip())
        man = jload(os.path.join(folder, "MANIFEST.json"))
        self.assertEqual(man["fingerprints"], postkit.fingerprints(self.ws, self.id))
        self.assertIn("package ready", rtext(os.path.join(self.ws, "memory", "post-tracker.md")))

    def test_hashtags_get_a_hash_and_missing_png_is_flagged(self):
        self.ready(approve_all=True)
        res = pb.build(self.ws, self.id, track=False)
        self.assertTrue(any("PNG or PDF" in w for w in res["warnings"]))
        self.assertNotIn("##leadership", rtext(os.path.join(res["folder"], "PACKAGE.md")))
        self.assertNotIn("package ready", rtext(os.path.join(self.ws, "memory", "post-tracker.md")))

    def test_too_long_text_only_warns(self):
        postkit.save_text(self.ws, self.id, "word " * 700)
        postkit.set_fields(self.ws, self.id, FIELDS)
        postkit.save_visual_spec(self.ws, self.id, ve.EXAMPLES["process_flow"])
        postkit.render_final(self.ws, self.id, png=False)
        ok, errors, warnings = pb.check(self.ws, self.id)
        self.assertTrue(any("characters" in w for w in warnings))

    def test_edit_after_approval_blocks_the_build_and_leaves_no_folder(self):
        self.ready(approve_all=True)
        postkit.set_fields(self.ws, self.id, {"first_comment": "a sneaky late change"})
        with self.assertRaises(pb.BuildError):
            pb.build(self.ws, self.id)
        self.assertFalse(os.path.exists(os.path.join(self.ws, "exports", "ready-to-paste", self.id)))

    def test_rebuild_replaces_the_folder(self):
        self.ready(approve_all=True)
        pb.build(self.ws, self.id, track=False)
        extra = os.path.join(self.ws, "exports", "ready-to-paste", self.id, "leftover.txt")
        wtext(extra, "x")
        pb.build(self.ws, self.id, track=False)
        self.assertFalse(os.path.exists(extra))


class Live(Base):
    def test_mark_live_starts_reminders_and_updates_the_tracker(self):
        self.ready()
        res = postkit.mark_live(self.ws, self.id, "https://example.com/post", ["24h", "7d"])
        self.assertEqual(res["reminders_added"], 2)
        self.assertTrue(res["tracker_written"], res["tracker_message"])
        self.assertIn("live", rtext(os.path.join(self.ws, "memory", "post-tracker.md")))
        self.assertEqual(len(jload(os.path.join(self.ws, "runs", "reminders.json"))["items"]), 2)


class Cli(Base):
    def test_cli_round_trip(self):
        run = lambda *a, **k: subprocess.run([sys.executable, os.path.join(self.ws, "scripts", a[0]), "--workspace", self.ws, *a[1:]], capture_output=True, text=True, **k)
        pid = run("postkit.py", "new", "--title", "CLI post").stdout.strip()
        self.assertRegex(pid, r"^P-\d{8}-\d{2}$")
        self.assertEqual(run("postkit.py", "text", "--id", pid, input=TEXT).returncode, 0)
        self.assertEqual(run("postkit.py", "set", "--id", pid, input=json.dumps(FIELDS)).returncode, 0)
        spec = json.dumps(ve.EXAMPLES["checklist"])
        self.assertEqual(run("postkit.py", "visual-spec", "--id", pid, input=spec).returncode, 0)
        self.assertEqual(run("postkit.py", "render", "--id", pid, "--no-png").returncode, 0)
        st = json.loads(run("postkit.py", "status", "--id", pid).stdout)
        self.assertEqual(st["missing"], [])
        self.assertEqual(run("package_builder.py", "check", "--id", pid).returncode, 1)
        bad = run("postkit.py", "set", "--id", pid, input='{"bogus": 1}')
        self.assertEqual(bad.returncode, 2)
        self.assertIn("unknown field", bad.stderr)


if __name__ == "__main__":
    unittest.main()
