"""Tests for the visual engine: every type renders valid, readable SVG; warnings fire; themes; browser path (stand-in Chrome)."""
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

from tests.helpers import jdump, jlines, jload, rbytes, rtext, wtext

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "runtime"))
import visual_engine as ve  # noqa: E402

THEME = ve.load_theme()[0]
ENGINE = os.path.join(ROOT, "runtime", "visual_engine.py")


def cli(*args, env=None):
    return subprocess.run([sys.executable, ENGINE, *args], capture_output=True, text=True, env=dict(os.environ, **(env or {})))


class Types(unittest.TestCase):
    def test_every_example_renders_valid_svg_without_warnings(self):
        for name, spec in ve.EXAMPLES.items():
            if name in ve.SLIDE_ONLY:
                continue
            for fmt in ("portrait", "square"):
                r = ve.render_one(spec, fmt, THEME)
                ET.fromstring(r["svg"].split("?>", 1)[1])                        # well-formed XML
                self.assertEqual((r["width"], r["height"]), ve.FORMATS[fmt])
                self.assertEqual(r["warnings"], [], "%s/%s: %s" % (name, fmt, r["warnings"]))
                self.assertGreaterEqual(r["min_font"], ve.MIN_READABLE, "%s/%s" % (name, fmt))

    def test_svg_has_title_desc_and_exact_labels(self):
        r = ve.render_one(ve.EXAMPLES["process_flow"], "portrait", THEME)
        self.assertIn("<title", r["svg"])
        self.assertIn("<desc", r["svg"])
        for step in ve.EXAMPLES["process_flow"]["steps"]:
            self.assertIn(step["label"], r["svg"])

    def test_text_is_escaped_and_cannot_inject_markup(self):
        spec = dict(ve.EXAMPLES["checklist"], title='A <script>alert(1)</script> & "quotes"')
        svg = ve.render_one(spec, "portrait", THEME)["svg"]
        self.assertNotIn("<script", svg)
        ET.fromstring(svg.split("?>", 1)[1])

    def test_deterministic_output_and_fingerprint(self):
        a = ve.render_one(ve.EXAMPLES["funnel"], "portrait", THEME)["svg"]
        b = ve.render_one(ve.EXAMPLES["funnel"], "portrait", THEME)["svg"]
        self.assertEqual(a, b)
        self.assertEqual(ve.spec_hash(ve.EXAMPLES["funnel"]), ve.spec_hash(json.loads(json.dumps(ve.EXAMPLES["funnel"]))))
        self.assertNotEqual(ve.spec_hash(ve.EXAMPLES["funnel"]), ve.spec_hash(ve.EXAMPLES["cycle"]))

    def test_pyramid_style_and_emphasis_by_label(self):
        spec = dict(ve.EXAMPLES["funnel"], style="pyramid", emphasis="Chosen")
        self.assertEqual(ve.render_one(spec, "portrait", THEME)["warnings"], [])


class Validation(unittest.TestCase):
    def test_bad_specs_give_clear_errors(self):
        cases = [({"type": "nope", "title": "x"}, "unknown type"), ({"type": "process_flow"}, "title"),
                 ({"type": "process_flow", "title": "t"}, "steps"), ({"type": "matrix_2x2", "title": "t", "quadrants": [1, 2]}, "exactly 4"),
                 ({"type": "carousel", "title": "t", "slides": [ve.EXAMPLES["cover"]]}, "at least 2"),
                 ({"type": "stat_callout", "title": "t"}, "stat"), ("not a dict", "JSON object")]
        for spec, word in cases:
            errs = ve.validate_spec(spec)
            self.assertTrue(errs and word in " ".join(errs), (spec, errs))

    def test_overstuffed_spec_warns_instead_of_silently_shrinking(self):
        spec = {"type": "process_flow", "title": "Title " * 30, "takeaway": "Word " * 80,
                "steps": [{"label": "Long label " * 12, "detail": "Detail " * 30}] + [{"label": "S%d" % i} for i in range(6)]}
        codes = {w[0] for w in ve.render_one(spec, "portrait", THEME)["warnings"]}
        self.assertIn("text_overflow", codes)
        self.assertIn("too_many_items", codes)

    def test_statistic_without_source_is_flagged(self):
        spec = dict(ve.EXAMPLES["stat_callout"])
        del spec["source"]
        self.assertIn("stat_needs_source", {w[0] for w in ve.render_one(spec, "portrait", THEME)["warnings"]})

    def test_no_word_is_broken_when_a_smaller_size_would_fit(self):
        lines, size, over = ve.fit("Follow-through", 260, 60, 36, 28, True, 1.15, 3)
        self.assertEqual(lines, ["Follow-through"])
        self.assertFalse(over)

    def test_density_warning(self):
        spec = dict(ve.EXAMPLES["checklist"], items=[{"label": "word " * 12, "detail": "more words " * 5} for _ in range(6)])
        self.assertIn("too_many_words", {w[0] for w in ve.render_one(spec, "portrait", THEME)["warnings"]})


class Theme(unittest.TestCase):
    def setUp(self):
        self.ws = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.ws, "docs"))
        os.makedirs(os.path.join(self.ws, "brand"))

    def tearDown(self):
        shutil.rmtree(self.ws, ignore_errors=True)

    def profile(self, text):
        with open(os.path.join(self.ws, "docs", "brand-profile.md"), "w") as fh:
            fh.write(text)

    def test_default_theme_meets_contrast(self):
        theme, warns = ve.load_theme()
        self.assertEqual([w for w in warns if w[0] == "contrast"], [])

    def test_the_shipped_profile_template_gives_the_default_theme(self):
        shutil.copy(os.path.join(ROOT, "docs", "brand-profile.md"), os.path.join(self.ws, "docs", "brand-profile.md"))
        theme, warns = ve.load_theme(self.ws)
        self.assertEqual(theme["primary"], ve.DEFAULT_THEME["primary"])
        self.assertEqual(warns, [])

    def test_profile_colors_fonts_footer_and_logo_are_used(self):
        with open(os.path.join(self.ws, "brand", "logo.png"), "wb") as fh:
            fh.write(b"\x89PNG\r\n\x1a\n" + b"0" * 50)
        self.profile("- Primary color for visuals (hex): #112233\n- Heading font for visuals (x): Georgia\n"
                     "- Footer text on every visual (x): @sample\n- Logo file for visuals (x): brand/logo.png\n")
        theme, warns = ve.load_theme(self.ws)
        self.assertEqual((theme["primary"], theme["heading_font"], theme["footer"]), ("#112233", "Georgia", "@sample"))
        self.assertTrue(theme["logo"].startswith("data:image/png;base64,"))
        svg = ve.render_one(ve.EXAMPLES["checklist"], "portrait", theme)["svg"]
        self.assertIn("@sample", svg)
        self.assertIn("data:image/png", svg)
        self.assertIn("Georgia", svg)

    def test_bad_values_are_ignored_with_a_warning(self):
        self.profile("- Primary color for visuals (x): red\n- Heading font for visuals (x): Arial;}<script>\n- Logo file for visuals (x): ../../etc/passwd\n")
        theme, warns = ve.load_theme(self.ws)
        self.assertEqual(theme["primary"], ve.DEFAULT_THEME["primary"])
        self.assertEqual(theme["heading_font"], "")
        self.assertEqual(theme["logo"], "")
        self.assertTrue({"theme_color", "theme_font", "theme_logo"} <= {w[0] for w in warns})

    def test_low_contrast_palette_is_reported(self):
        self.profile("- Primary color for visuals (x): #FFFF99\n- Background color for visuals (x): #FFFFFF\n")
        self.assertIn("contrast", {w[0] for w in ve.load_theme(self.ws)[1]})

    def test_dark_theme_renders_without_warnings(self):
        self.profile("- Primary color for visuals (x): #FFC400\n- Background color for visuals (x): #101826\n- Text color for visuals (x): #F2F5FA\n"
                     "- Accent color for visuals (x): #FF7A59\n- Secondary color for visuals (x): #4FD1C5\n")
        theme, warns = ve.load_theme(self.ws)
        self.assertEqual([w for w in warns if w[0] == "contrast"], [])
        for name in ("process_flow", "before_after", "stat_callout"):
            self.assertEqual(ve.render_one(ve.EXAMPLES[name], "portrait", theme)["warnings"], [], name)


class AltAndPrompt(unittest.TestCase):
    def test_alt_text_uses_only_the_specs_words(self):
        short, long_ = ve.describe(ve.EXAMPLES["matrix_2x2"])
        self.assertLessEqual(len(short), 120)
        for word in ("Quick wins", "Big bets", "Effort", "Impact", "Top left"):
            self.assertIn(word, long_)
        self.assertNotIn("None", long_)

    def test_every_type_has_alt_text_and_prompt(self):
        for name in ve.DIAGRAM_TYPES:
            short, long_ = ve.describe(ve.EXAMPLES[name])
            self.assertTrue(short and len(long_) > len(short), name)
            p = ve.visual_prompt(ve.EXAMPLES[name], THEME)
            self.assertIn("exactly", p)
            self.assertIn("1080 x 1350", p)


class Cli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def spec(self, name="process_flow"):
        p = os.path.join(self.tmp, name + ".json")
        with open(p, "w") as fh:
            json.dump(ve.EXAMPLES[name], fh)
        return p

    def test_render_writes_svg_alt_prompt_and_meta(self):
        r = cli("--workspace", self.tmp, "render", "--spec", self.spec(), "--out", os.path.join(self.tmp, "o"), "--name", "v")
        self.assertEqual(r.returncode, 0, r.stderr)
        out = os.path.join(self.tmp, "o")
        for f in ("v.svg", "v.alt.txt", "v.prompt.txt", "v.meta.json"):
            self.assertTrue(os.path.exists(os.path.join(out, f)), f)
        meta = jload(os.path.join(out, "v.meta.json"))
        self.assertEqual(meta["spec_fingerprint"], ve.spec_hash(ve.EXAMPLES["process_flow"]))
        self.assertEqual(meta["files"][0]["file"], "v.svg")

    def test_carousel_makes_one_svg_per_slide(self):
        r = cli("example", "carousel")
        p = os.path.join(self.tmp, "c.json")
        wtext(p, r.stdout)
        r = cli("--workspace", self.tmp, "render", "--spec", p, "--out", self.tmp + "/c", "--name", "car")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(sorted(f for f in os.listdir(self.tmp + "/c") if f.endswith(".svg")), ["car-slide-%02d.svg" % i for i in range(1, 5)])
        self.assertIn("1 / 4", rtext(self.tmp + "/c/car-slide-01.svg"))

    def test_previews_need_three_different_types(self):
        same = os.path.join(self.tmp, "same.json")
        jdump([ve.EXAMPLES["cycle"]] * 3, same)
        r = cli("--workspace", self.tmp, "previews", "--specs", same, "--out", self.tmp + "/p")
        self.assertEqual(r.returncode, 2)
        self.assertIn("3 different", r.stderr)
        ok = os.path.join(self.tmp, "ok.json")
        jdump({"previews": [{"spec": ve.EXAMPLES[t], "reason": "because " + t} for t in ("cycle", "funnel", "timeline")]}, ok)
        r = cli("--workspace", self.tmp, "previews", "--specs", ok, "--out", self.tmp + "/p")
        self.assertEqual(r.returncode, 0, r.stderr)
        index = jload(self.tmp + "/p/previews.json")["previews"]
        self.assertEqual([x["type"] for x in index], ["cycle", "funnel", "timeline"])
        self.assertTrue(os.path.exists(self.tmp + "/p/previews.html"))

    def test_check_reports_errors_with_nonzero_exit(self):
        bad = os.path.join(self.tmp, "bad.json")
        jdump({"type": "funnel", "title": "x"}, bad)
        r = cli("--workspace", self.tmp, "check", "--spec", bad)
        self.assertEqual(r.returncode, 1)
        self.assertIn("levels", r.stdout)

    def test_no_browser_still_gives_svg_and_a_clear_note(self):
        r = cli("--workspace", self.tmp, "render", "--spec", self.spec(), "--out", self.tmp + "/o", "--png", "--pdf",
                env={"PATH": "/nonexistent", "LBA_BROWSER": ""})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("No Chrome or Edge", r.stdout)
        self.assertTrue(os.path.exists(self.tmp + "/o/process_flow.svg"))
        self.assertTrue(os.path.exists(self.tmp + "/o/process_flow.html"))


STAND_IN = '''#!/usr/bin/env python3
import sys, struct, zlib, json, os
args = sys.argv[1:]
log = os.environ.get("STAND_IN_LOG")
if log:
    open(log, "a").write(json.dumps(args) + "\\n")
def png(w, h):
    raw = b"".join(b"\\x00" + b"\\xff\\xff\\xff" * w for _ in range(h))
    def chunk(t, d):
        c = struct.pack(">I", len(d)) + t + d
        return c + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    return b"\\x89PNG\\r\\n\\x1a\\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")
for a in args:
    if a.startswith("--screenshot="):
        size = [x for x in args if x.startswith("--window-size=")][0].split("=")[1].split(",")
        open(a.split("=", 1)[1], "wb").write(png(int(size[0]), int(size[1])))
    if a.startswith("--print-to-pdf="):
        open(a.split("=", 1)[1], "wb").write(b"%PDF-1.4\\n" + b"x" * 200)
'''


@unittest.skipIf(os.name == "nt", "the stand-in browser is a POSIX script")
class StandInBrowser(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.browser = os.path.join(self.tmp, "fake-chrome")
        with open(self.browser, "w") as fh:
            fh.write(STAND_IN)
        os.chmod(self.browser, os.stat(self.browser).st_mode | stat.S_IEXEC)
        self.log = os.path.join(self.tmp, "calls.log")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_png_and_pdf_are_requested_with_the_right_browser_arguments(self):
        spec = os.path.join(self.tmp, "s.json")
        jdump(ve.EXAMPLES["checklist"], spec)
        r = cli("--workspace", self.tmp, "render", "--spec", spec, "--out", self.tmp + "/o", "--name", "v", "--png", "--pdf",
                env={"LBA_BROWSER": self.browser, "STAND_IN_LOG": self.log})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(ve.png_size(self.tmp + "/o/v.png"), (1080, 1350))
        self.assertTrue(rbytes(self.tmp + "/o/v.pdf").startswith(b"%PDF"))
        calls = jlines(self.log)
        self.assertEqual(len(calls), 2)
        shot = next(c for c in calls if any(a.startswith("--screenshot=") for a in c))
        pdf = next(c for c in calls if any(a.startswith("--print-to-pdf=") for a in c))
        self.assertIn("--headless=new", shot)
        self.assertIn("--window-size=1080,1350", shot)
        self.assertIn("--no-pdf-header-footer", pdf)
        self.assertTrue(shot[-1].startswith("file:///"))
        files = {f["file"]: f for f in jload(self.tmp + "/o/v.meta.json")["files"]}
        self.assertTrue(files["v.png"]["derived"] and files["v.pdf"]["derived"] and "derived" not in files["v.svg"])

    def test_carousel_pdf_gets_one_page_per_slide(self):
        spec = os.path.join(self.tmp, "c.json")
        wtext(spec, cli("example", "carousel").stdout)
        cli("--workspace", self.tmp, "render", "--spec", spec, "--out", self.tmp + "/o", "--name", "car", "--pdf", env={"LBA_BROWSER": self.browser})
        self.assertTrue(os.path.exists(self.tmp + "/o/car.pdf"))

    def test_a_browser_that_makes_no_file_is_reported_not_trusted(self):
        broken = os.path.join(self.tmp, "broken")
        with open(broken, "w") as fh:
            fh.write("#!/bin/sh\nexit 0\n")
        os.chmod(broken, 0o755)
        spec = os.path.join(self.tmp, "s.json")
        jdump(ve.EXAMPLES["checklist"], spec)
        r = cli("--workspace", self.tmp, "render", "--spec", spec, "--out", self.tmp + "/o", "--png", env={"LBA_BROWSER": broken})
        self.assertEqual(r.returncode, 0)
        self.assertIn("PNG was not made", r.stdout)
        self.assertFalse(os.path.exists(self.tmp + "/o/s.png"))


if __name__ == "__main__":
    unittest.main()
