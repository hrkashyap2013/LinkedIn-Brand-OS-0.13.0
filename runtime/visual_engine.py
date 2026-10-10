#!/usr/bin/env python3
"""Visual engine: turns a visual spec (JSON) into an exact, editable SVG, plus PNG and PDF.

    python3 scripts/visual_engine.py types                       # the 10 diagram types and their fields
    python3 scripts/visual_engine.py example process_flow        # print a starter spec
    python3 scripts/visual_engine.py check --spec spec.json      # quality checks only
    python3 scripts/visual_engine.py previews --specs three.json --out drafts/P-001/previews
    python3 scripts/visual_engine.py render --spec spec.json --out drafts/P-001/final [--format portrait|square|carousel] [--png] [--pdf]
    python3 scripts/visual_engine.py browser                     # which Chrome / Edge was found

What it does
  * Every label is drawn exactly as written in the spec. Nothing is invented, and numbers are never made up.
  * Text is measured and wrapped to fit. Long text shrinks to a readable size; if it still does not fit
    it is shortened and a warning is reported. Warnings feed Visual QA.
  * Formats: portrait 1080x1350 (default), square 1080x1080, carousel (a PDF of portrait pages).
  * Brand look comes from the "Visual rules" section of docs/brand-profile.md (colors, fonts, logo, footer).
    Blank fields give a clean, accessible neutral theme.
  * PNG and PDF are made with a browser already on your computer (Chrome or Edge). With none found you
    still get the SVG, and a note says how to get the rest.
  * Every render writes alt text (short and long), a "visual prompt" for design tools, and a meta file with
    fingerprints, so the approved visual can be checked later.

Needs Python 3.8+ and nothing else.
"""
import argparse
import base64
import copy
import hashlib
import html
import json
import math
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import threading

FORMATS = {"portrait": (1080, 1350), "square": (1080, 1080)}
TYPE_NAMES = {
    "process_flow": "process flow", "matrix_2x2": "2x2 matrix", "comparison_table": "comparison table",
    "cycle": "cycle", "funnel": "funnel or pyramid", "timeline": "timeline", "before_after": "before and after",
    "hub_spoke": "hub-and-spoke map", "stat_callout": "statistic callout", "checklist": "checklist",
    "cover": "cover slide", "closing": "closing slide",
}
DIAGRAM_TYPES = ["process_flow", "matrix_2x2", "comparison_table", "cycle", "funnel", "timeline",
                 "before_after", "hub_spoke", "stat_callout", "checklist"]
SLIDE_ONLY = ["cover", "closing"]
MIN_READABLE = 28          # px on a 1080 px wide image: below this, text is hard to read in a phone feed
MAX_WORDS_SINGLE = 100
MAX_WORDS_SLIDE = 70

DEFAULT_THEME = {
    "primary": "#1F3A5F", "secondary": "#1B7F73", "accent": "#C2410C", "background": "#FFFFFF", "text": "#1A1A1A",
    "muted": "#505B6A", "heading_font": "", "body_font": "", "logo": "", "footer": "",
}
FALLBACK_FONTS = "Helvetica Neue, Helvetica, Arial, sans-serif"

# Helvetica / Arial advance widths per 1000 em. Used to wrap and fit text without a font engine.
_W = {" ": 278, "!": 278, '"': 355, "#": 556, "$": 556, "%": 889, "&": 667, "'": 191, "(": 333, ")": 333, "*": 389,
      "+": 584, ",": 278, "-": 333, ".": 278, "/": 278, ":": 278, ";": 278, "<": 584, "=": 584, ">": 584, "?": 556,
      "@": 1015, "[": 278, "\\": 278, "]": 278, "^": 469, "_": 556, "`": 333, "{": 334, "|": 260, "}": 334, "~": 584,
      "\u2014": 1000, "\u2013": 556, "\u2018": 222, "\u2019": 222, "\u201c": 333, "\u201d": 333, "\u2022": 350,
      "\u2026": 1000, "\u00d7": 584, "\u2192": 1000, "\u2713": 800, "\u2717": 800}
for _c in "0123456789":
    _W[_c] = 556
for _c, _v in zip("ABCDEFGHIJKLMNOPQRSTUVWXYZ",
                  (667, 667, 722, 722, 667, 611, 778, 722, 278, 500, 667, 556, 833, 722, 778, 667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611)):
    _W[_c] = _v
for _c, _v in zip("abcdefghijklmnopqrstuvwxyz",
                  (556, 556, 500, 556, 556, 278, 556, 556, 222, 222, 500, 222, 833, 556, 556, 556, 556, 333, 500, 278, 556, 500, 722, 500, 500, 500)):
    _W[_c] = _v

_CTRL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


class SpecError(ValueError):
    pass


# ------------------------------------------------------------------ colour

def hex_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def rgb_hex(rgb):
    return "#%02X%02X%02X" % tuple(max(0, min(255, int(round(v)))) for v in rgb)


def luminance(h):
    def lin(v):
        v /= 255.0
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = hex_rgb(h)
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def contrast(a, b):
    la, lb = luminance(a), luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def mix(a, b, t):
    ra, rb = hex_rgb(a), hex_rgb(b)
    return rgb_hex(tuple(ra[i] * (1 - t) + rb[i] * t for i in range(3)))


def on_color(bg, theme=None):
    """White or near-black text, whichever reads better on bg."""
    dark = "#111111"
    return "#FFFFFF" if contrast("#FFFFFF", bg) >= contrast(dark, bg) else dark


# -------------------------------------------------------------------- text

def esc(s):
    return html.escape(_CTRL.sub(" ", str(s)), quote=True)


def clean_text(s):
    return re.sub(r"\s+", " ", _CTRL.sub(" ", str(s if s is not None else ""))).strip()


_WIDTH_EXTRA = 1.0          # raised to 1.14 while rendering with a custom brand font, whose widths are unknown
_RENDER_LOCK = threading.RLock()


def text_width(s, size, bold=False):
    w = sum(_W.get(ch, 600 if ord(ch) > 127 else 556) for ch in s) / 1000.0 * size
    return w * (1.07 if bold else 1.0) * 1.10 * _WIDTH_EXTRA     # generous margin so wider fonts (DejaVu, Segoe) still fit


def wrap(text, size, max_w, bold=False):
    return wrap2(text, size, max_w, bold)[0]


def wrap2(text, size, max_w, bold=False):
    """Greedy word wrap. Returns (lines, broke) where broke is True if a single word had to be split."""
    lines, cur, broke = [], "", False
    for word in text.split(" "):
        if not word:
            continue
        trial = word if not cur else cur + " " + word
        if text_width(trial, size, bold) <= max_w:
            cur = trial
            continue
        if cur:
            lines.append(cur)
            cur = ""
        while text_width(word, size, bold) > max_w and len(word) > 1:   # a single very long word
            broke = True
            k = len(word)
            while k > 1 and text_width(word[:k] + "-", size, bold) > max_w:
                k -= 1
            lines.append(word[:k] + "-")
            word = word[k:]
        cur = word
    if cur:
        lines.append(cur)
    return (lines or [""]), broke


def fit(text, w, h, max_size, min_size, bold=False, lh=1.25, max_lines=None):
    """Largest size in [min_size, max_size] where the wrapped text fits w x h. Returns (lines, size, overflow)."""
    text = clean_text(text)
    size = int(max_size)
    while size >= min_size:
        lines, broke = wrap2(text, size, w, bold)
        if not broke and (max_lines is None or len(lines) <= max_lines) and len(lines) * size * lh <= h + 0.5:
            return lines, size, False
        size -= 2
    size = int(min_size)
    lines = wrap(text, size, w, bold)
    cap = max(1, int(h // (size * lh)))
    if max_lines:
        cap = min(cap, max_lines)
    if len(lines) > cap:
        kept = lines[:cap]
        last = kept[-1]
        while last and text_width(last + "\u2026", size, bold) > w:
            last = last[:-1]
        kept[-1] = last.rstrip() + "\u2026"
        return kept, size, True
    return lines, size, False


# ------------------------------------------------------------------- theme

def _safe_font(name):
    name = clean_text(name)
    if not name or not re.fullmatch(r"[A-Za-z0-9 ,\-]{1,60}", name):
        return ""
    return name


def _profile_values(profile_text):
    keys = {"primary": r"Primary color", "secondary": r"Secondary color", "accent": r"Accent color",
            "background": r"Background color", "text": r"Text color", "heading_font": r"Heading font",
            "body_font": r"Body font", "logo": r"Logo file for visuals", "footer": r"Footer text on every visual"}
    out = {}
    for k, label in keys.items():
        m = re.search(r"^\s*-\s*%s[^:\n]*:[ \t]*(.*?)[ \t]*$" % label, profile_text, re.M | re.I)
        if m and m.group(1).strip():
            out[k] = m.group(1).strip()
    return out


def load_theme(workspace=None, theme_file=None):
    """Return (theme, warnings). Order: defaults, the brand profile, then an explicit theme file."""
    theme, warnings = dict(DEFAULT_THEME), []
    values = {}
    if workspace:
        p = os.path.join(workspace, "docs", "brand-profile.md")
        if os.path.exists(p):
            with open(p, encoding="utf-8") as fh:
                values.update(_profile_values(fh.read()))
    if theme_file:
        with open(theme_file, encoding="utf-8") as fh:
            values.update({k: str(v) for k, v in json.load(fh).items() if k in DEFAULT_THEME})
    for k in ("primary", "secondary", "accent", "background", "text", "muted"):
        if k in values:
            if _HEX.match(values[k]):
                theme[k] = values[k].upper()
            else:
                warnings.append(("theme_color", "%s color %r is not a hex value like #1F3A5F; the default was used" % (k, values[k])))
    for k in ("heading_font", "body_font"):
        if k in values:
            safe = _safe_font(values[k])
            if safe:
                theme[k] = safe
            else:
                warnings.append(("theme_font", "%s %r was ignored (use letters, digits and spaces only)" % (k, values[k])))
    theme["footer"] = clean_text(values.get("footer", ""))[:60]
    if values.get("logo") and workspace:
        path = os.path.normpath(os.path.join(workspace, values["logo"]))
        ext = os.path.splitext(path)[1].lower()
        mime = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".svg": "image/svg+xml"}.get(ext)
        root = os.path.abspath(workspace)
        if not os.path.abspath(path).startswith(root + os.sep):
            warnings.append(("theme_logo", "the logo must be inside your workspace folder; it was ignored"))
        elif not mime:
            warnings.append(("theme_logo", "the logo must be PNG, JPG or SVG; it was ignored"))
        elif not os.path.isfile(path):
            warnings.append(("theme_logo", "logo file %s was not found; it was ignored" % values["logo"]))
        elif os.path.getsize(path) > 400 * 1024:
            warnings.append(("theme_logo", "the logo is over 400 KB; it was ignored"))
        else:
            with open(path, "rb") as fh:
                theme["logo"] = "data:%s;base64,%s" % (mime, base64.b64encode(fh.read()).decode("ascii"))
    # derived colours
    theme["surface"] = mix(theme["background"], theme["text"], 0.06)
    theme["border"] = mix(theme["background"], theme["text"], 0.16)
    if "muted" not in values:
        theme["muted"] = mix(theme["background"], theme["text"], 0.72)
    # accessibility of the palette
    checks = [("text on background", theme["text"], theme["background"]),
              ("muted text on background", theme["muted"], theme["background"]),
              ("title color (primary) on background", theme["primary"], theme["background"]),
              ("text on primary", on_color(theme["primary"]), theme["primary"]),
              ("text on secondary", on_color(theme["secondary"]), theme["secondary"]),
              ("text on accent", on_color(theme["accent"]), theme["accent"]),
              ("accent text on background", theme["accent"], theme["background"])]
    for label, fg, bg in checks:
        ratio = contrast(fg, bg)
        if ratio < 4.5:
            warnings.append(("contrast", "%s has contrast %.1f:1 (4.5:1 is the readable minimum); pick a darker or lighter color" % (label, ratio)))
    return theme, warnings


def font_stack(theme, kind):
    name = theme.get(kind + "_font") or theme.get("body_font") or ""
    return ("'%s', %s" % (name, FALLBACK_FONTS)) if name else FALLBACK_FONTS


# ------------------------------------------------------------------ canvas

class Canvas:
    def __init__(self, w, h, theme):
        self.w, self.h, self.t = w, h, theme
        self.parts, self.warnings = [], []
        self.min_font, self.words = 999, 0

    def warn(self, code, msg):
        if (code, msg) not in self.warnings:
            self.warnings.append((code, msg))

    def add(self, s):
        self.parts.append(s)

    def rect(self, x, y, w, h, fill="none", r=0, stroke=None, sw=0, opacity=None):
        a = ' rx="%g" ry="%g"' % (r, r) if r else ""
        s = ' stroke="%s" stroke-width="%g"' % (stroke, sw) if stroke else ""
        o = ' opacity="%g"' % opacity if opacity is not None else ""
        self.add('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="%s"%s%s%s/>' % (x, y, max(w, 0), max(h, 0), fill, a, s, o))

    def circle(self, cx, cy, r, fill="none", stroke=None, sw=0):
        s = ' stroke="%s" stroke-width="%g"' % (stroke, sw) if stroke else ""
        self.add('<circle cx="%.1f" cy="%.1f" r="%.1f" fill="%s"%s/>' % (cx, cy, r, fill, s))

    def ellipse(self, cx, cy, rx, ry, stroke, sw, dash=None):
        d = ' stroke-dasharray="%s"' % dash if dash else ""
        self.add('<ellipse cx="%.1f" cy="%.1f" rx="%.1f" ry="%.1f" fill="none" stroke="%s" stroke-width="%g"%s/>' % (cx, cy, rx, ry, stroke, sw, d))

    def line(self, x1, y1, x2, y2, stroke, sw, dash=None):
        d = ' stroke-dasharray="%s"' % dash if dash else ""
        self.add('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="%s" stroke-width="%g" stroke-linecap="round"%s/>' % (x1, y1, x2, y2, stroke, sw, d))

    def poly(self, pts, fill, extra=""):
        self.add('<polygon points="%s" fill="%s"%s/>' % (" ".join("%.1f,%.1f" % p for p in pts), fill, extra))

    def polyline(self, pts, stroke, sw):
        self.add('<polyline points="%s" fill="none" stroke="%s" stroke-width="%g" stroke-linecap="round" stroke-linejoin="round"/>'
                 % (" ".join("%.1f,%.1f" % p for p in pts), stroke, sw))

    def lines(self, lines, x, y, size, fill, bold=False, anchor="start", lh=1.25, kind="body", rotate=None, track=True):
        """Draw already-wrapped lines starting at top y. Returns the height used."""
        if track:
            self.min_font = min(self.min_font, size)
        fam = esc(font_stack(self.t, "heading" if kind == "heading" else "body"))
        for i, ln in enumerate(lines):
            base = y + size * lh * i + size * (0.5 * (lh - 1) + 0.8)
            rot = ' transform="rotate(%g %.1f %.1f)"' % (rotate[0], rotate[1], rotate[2]) if rotate else ""
            self.add('<text x="%.1f" y="%.1f" font-family="%s" font-size="%d" font-weight="%s" fill="%s" text-anchor="%s"%s>%s</text>'
                     % (x, base, fam, size, "700" if bold else "400", fill, anchor, rot, esc(ln)))
        return len(lines) * size * lh

    def box(self, text, x, y, w, h, max_size, min_size, fill, bold=False, anchor="start", valign="top", lh=1.25,
            max_lines=None, kind="body", track=True, count=True, rotate_about=None):
        """Fit text into a w x h box and draw it. Returns (size, used_height)."""
        text = clean_text(text)
        if not text:
            return min_size, 0
        lines, size, over = fit(text, w, h, max_size, min_size, bold, lh, max_lines)
        if over:
            self.warn("text_overflow", 'the text "%s" did not fit and was shortened; use fewer words' % (text[:40] + ("..." if len(text) > 40 else "")))
        if track and size < MIN_READABLE:
            self.warn("small_text", 'the text "%s" is %dpx, below the %dpx phone-readable minimum; use fewer words' % (text[:40], size, MIN_READABLE))
        used = len(lines) * size * lh
        top = y + (max(h - used, 0) / 2.0 if valign == "middle" else 0)
        ax = x if anchor == "start" else (x + w / 2.0 if anchor == "middle" else x + w)
        self.lines(lines, ax, top, size, fill, bold, anchor, lh, kind, track=track)
        if count:
            self.words += len(text.split())
        return size, used

    def pair(self, label, detail, x, y, w, h, fill, muted, max_label=48, min_label=30, align="start", valign="middle"):
        """A bold label with an optional smaller detail underneath, sized together to fit w x h."""
        label, detail = clean_text(label), clean_text(detail)
        chosen = None
        for ls in range(int(max_label), int(min_label) - 1, -2):
            l_lines, l_broke = wrap2(label, ls, w, True)
            if len(l_lines) > 3 or l_broke:
                continue
            ds = max(MIN_READABLE, int(round(ls * 0.75)))
            d_lines, d_broke = wrap2(detail, ds, w) if detail else ([], False)
            if d_broke:
                continue
            total = len(l_lines) * ls * 1.2 + (10 + len(d_lines) * ds * 1.25 if d_lines else 0)
            if total <= h + 0.5:
                chosen = (ls, ds)
                break
        if chosen is None:
            ls = int(min_label)
            ds = MIN_READABLE
            avail_l = max(h * (0.62 if detail else 1.0), ls * 1.2)
            l_size, l_used = self.box(label, x, y, w, avail_l, ls, ls, fill, True, align, "top", 1.2)
            if detail:
                self.box(detail, x, y + l_used + 10, w, max(h - l_used - 10, ds * 1.25), ds, ds, muted, False, align, "top", 1.25)
            return
        ls, ds = chosen
        l_lines = wrap(label, ls, w, True)
        d_lines = wrap(detail, ds, w) if detail else []
        total = len(l_lines) * ls * 1.2 + (10 + len(d_lines) * ds * 1.25 if d_lines else 0)
        top = y + (max(h - total, 0) / 2.0 if valign == "middle" else 0)
        ax = x if align == "start" else (x + w / 2.0 if align == "middle" else x + w)
        used = self.lines(l_lines, ax, top, ls, fill, True, align, 1.2)
        self.words += len(label.split())
        if d_lines:
            self.lines(d_lines, ax, top + used + 10, ds, muted, False, align, 1.25)
            self.words += len(detail.split())


# ------------------------------------------------------------------ frame

def _str(v, cap):
    return clean_text(v)[:cap]


def frame(c, spec, fmt, page=None, total=None):
    """Draw background, header, takeaway and footer. Returns the body rectangle (x, y, w, h)."""
    t = c.t
    W, H = c.w, c.h
    pad = 72 if fmt == "portrait" else 64
    c.rect(0, 0, W, H, t["background"])
    c.rect(0, 0, W, 14, t["primary"])
    y = pad
    title_max = 66 if fmt == "portrait" else 56
    title = _str(spec.get("title", ""), 160)
    size, used = c.box(title, pad, y, W - 2 * pad, title_max * 1.15 * 3, title_max, 40, t["primary"], True, "start", "top", 1.15, 3, "heading")
    y += used + 18
    c.rect(pad, y, 120, 8, t["accent"], r=4)
    y += 8 + 24
    if spec.get("subtitle"):
        size, used = c.box(_str(spec["subtitle"], 200), pad, y, W - 2 * pad, 34 * 1.25 * 2, 34, MIN_READABLE, t["muted"], False, "start", "top", 1.25, 2)
        y += used + 12
    top = y + 8
    footer_h = 100
    footer_top = H - footer_h
    bottom = footer_top - 16
    if spec.get("takeaway"):
        text = _str(spec["takeaway"], 200)
        lines, tsz, over = fit(text, W - 2 * pad - 64, 38 * 1.25 * 2, 38, 30, True, 1.25, 2)
        th = len(lines) * tsz * 1.25 + 44
        ty = bottom - th
        c.rect(pad, ty, W - 2 * pad, th, t["primary"], r=22)
        c.box(text, pad + 32, ty + 22, W - 2 * pad - 64, th - 44, 38, 30, on_color(t["primary"]), True, "start", "middle", 1.25, 2)
        bottom = ty - 24
    # footer
    c.line(pad, footer_top, W - pad, footer_top, t["border"], 2)
    x = pad
    if t.get("logo"):
        c.add('<image href="%s" xlink:href="%s" x="%d" y="%d" width="220" height="56" preserveAspectRatio="xMinYMid meet"/>'
              % (t["logo"], t["logo"], pad, footer_top + (footer_h - 56) // 2))
        x += 236
    if t.get("footer"):
        c.box(t["footer"], x, footer_top + 28, W / 2.0 - x, 44, 26, 22, t["muted"], False, "start", "middle", 1.2, 1, track=False, count=False)
    right = ""
    if page and total:
        right = "%d / %d" % (page, total)
    elif spec.get("source"):
        right = "Source: " + _str(spec["source"], 80)
    if right:
        c.box(right, W / 2.0, footer_top + 28, W / 2.0 - pad, 44, 24, 20, t["muted"], False, "end", "middle", 1.2, 1, track=False, count=False)
    bx, by = pad, top
    bw, bh = W - 2 * pad, bottom - top
    if bh < 320:
        c.warn("header_too_tall", "the title, subtitle and takeaway leave too little room for the diagram; shorten them")
    return bx, by, bw, bh


# --------------------------------------------------------------- layouts

def _items(spec, key, lo, hi, what):
    items = spec.get(key)
    if not isinstance(items, list) or not items:
        raise SpecError("%s needs a non-empty list called %r" % (what, key))
    if len(items) < lo:
        raise SpecError("%s needs at least %d entries in %r" % (what, lo, key))
    return items


def _label_detail(item):
    if isinstance(item, str):
        return clean_text(item)[:90], ""
    return clean_text(item.get("label", ""))[:90], clean_text(item.get("detail", ""))[:160]


def _emph(spec, i, label=""):
    e = spec.get("emphasis")
    if e is None:
        return False
    if isinstance(e, int):
        return e == i
    return clean_text(e).lower() == clean_text(label).lower()


def _badge(c, cx, cy, r, num, fill, color):
    c.circle(cx, cy, r, fill)
    c.box(str(num), cx - r, cy - r, 2 * r, 2 * r, int(r * 1.15), int(r * 0.7), color, True, "middle", "middle", 1.0, 1, track=False, count=False)


def layout_process_flow(c, spec, body):
    t = c.t
    steps = _items(spec, "steps", 2, 9, "process_flow")
    n = len(steps)
    bx, by, bw, bh = body
    gap = 40 if n <= 5 else 30
    ch = min(230.0, (bh - gap * (n - 1)) / n)
    if ch < 96:
        c.warn("too_many_items", "process_flow has %d steps; at most 6 stay readable on a phone" % n)
    elif n > 6:
        c.warn("too_many_items", "process_flow has %d steps; at most 6 stay readable on a phone" % n)
    r = min(34.0, ch * 0.28)
    for i, s in enumerate(steps):
        label, detail = _label_detail(s)
        y = by + i * (ch + gap)
        emph = _emph(spec, i, label)
        fill = t["primary"] if emph else t["surface"]
        fg = on_color(fill)
        mut = fg if emph else t["muted"]
        c.rect(bx, y, bw, ch, fill, r=22)
        badge_fill = t["accent"] if emph else t["primary"]
        _badge(c, bx + 28 + r, y + ch / 2.0, r, i + 1, badge_fill, on_color(badge_fill))
        tx = bx + 28 + 2 * r + 28
        c.pair(label, detail, tx, y + 12, bx + bw - 28 - tx, ch - 24, fg, mut, 50, 30)
        if i < n - 1:
            ax = bx + 28 + r
            c.poly([(ax - 14, y + ch + 8), (ax + 14, y + ch + 8), (ax, y + ch + gap - 8)], t["accent"])


def layout_matrix_2x2(c, spec, body):
    t = c.t
    q = spec.get("quadrants")
    if not isinstance(q, list) or len(q) != 4:
        raise SpecError("matrix_2x2 needs exactly 4 entries in 'quadrants' (top-left, top-right, bottom-left, bottom-right)")
    xa, ya = spec.get("x_axis") or {}, spec.get("y_axis") or {}
    bx, by, bw, bh = body
    left, bottom_pad, gap = 90, 96, 20
    gx, gy, gw, gh = bx + left, by, bw - left, bh - bottom_pad
    cw, chh = (gw - gap) / 2.0, (gh - gap) / 2.0
    for i, item in enumerate(q):
        label, detail = _label_detail(item)
        col, row = i % 2, i // 2
        x, y = gx + col * (cw + gap), gy + row * (chh + gap)
        emph = _emph(spec, i, label)
        fill = t["primary"] if emph else t["surface"]
        fg = on_color(fill)
        c.rect(x, y, cw, chh, fill, r=22)
        c.pair(label, detail, x + 24, y + 16, cw - 48, chh - 32, fg, fg if emph else t["muted"], 46, 30)
    # axes
    ay = gy + gh + 22
    c.line(gx, ay, gx + gw, ay, t["muted"], 4)
    c.poly([(gx + gw, ay), (gx + gw - 18, ay - 10), (gx + gw - 18, ay + 10)], t["muted"])
    c.box(clean_text(xa.get("label", "")), gx + gw * 0.25, ay + 10, gw * 0.5, 44, 32, 28, t["text"], True, "middle", "top", 1.2, 1)
    c.box(clean_text(xa.get("low", "")), gx, ay + 10, gw * 0.25, 44, 30, 28, t["muted"], False, "start", "top", 1.2, 1)
    c.box(clean_text(xa.get("high", "")), gx + gw * 0.75, ay + 10, gw * 0.25, 44, 30, 28, t["muted"], False, "end", "top", 1.2, 1)
    axx = bx + 50
    c.line(axx, gy + gh, axx, gy, t["muted"], 4)
    c.poly([(axx, gy), (axx - 10, gy + 18), (axx + 10, gy + 18)], t["muted"])
    # rotated y-axis labels: draw horizontally in a box, then rotate about its centre
    for text, frac_a, frac_b, bold, size, color in ((ya.get("label", ""), 0.25, 0.5, True, 32, t["text"]),
                                                    (ya.get("low", ""), 0.0, 0.25, False, 30, t["muted"]),
                                                    (ya.get("high", ""), 0.75, 0.25, False, 30, t["muted"])):
        text = clean_text(text)
        if not text:
            continue
        seg_w = gh * frac_b
        along = gy + gh - gh * frac_a - seg_w         # bottom-to-top: low at the bottom
        cx, cy = axx - 28, along + seg_w / 2.0
        lines, sz, over = fit(text, seg_w, 44, size, 28, bold, 1.2, 1)
        if over:
            c.warn("text_overflow", 'the axis text "%s" did not fit and was shortened' % text[:30])
        anchor = "middle" if frac_b == 0.5 else ("start" if frac_a == 0.0 else "end")
        px = cy - seg_w / 2.0 if anchor == "start" else (cy + seg_w / 2.0 if anchor == "end" else cy)
        # place by transforming: translate to (cx, px) and rotate -90 so the text runs upward
        fam = esc(font_stack(t, "body"))
        c.add('<text transform="translate(%.1f %.1f) rotate(-90)" font-family="%s" font-size="%d" font-weight="%s" fill="%s" text-anchor="%s">%s</text>'
              % (cx + sz * 0.3, px, fam, sz, "700" if bold else "400", color,
                 "start" if anchor == "end" else ("end" if anchor == "start" else "middle"), esc(lines[0])))
        c.min_font = min(c.min_font, sz)
        c.words += len(text.split())


def layout_comparison_table(c, spec, body):
    t = c.t
    cols = spec.get("columns")
    rows = spec.get("rows")
    if not isinstance(cols, list) or len(cols) < 2 or len(cols) > 4:
        raise SpecError("comparison_table needs 'columns' with 2 to 4 names")
    if not isinstance(rows, list) or not rows:
        raise SpecError("comparison_table needs a non-empty list called 'rows' (each with 'label' and 'values')")
    if len(rows) > 7:
        c.warn("too_many_items", "comparison_table has %d rows; at most 6 stay readable on a phone" % len(rows))
    bx, by, bw, bh = body
    first = bw * (0.34 if len(cols) <= 3 else 0.28)
    cw = (bw - first) / float(len(cols))
    head = 104
    rh = min(200.0, (bh - head) / len(rows))
    emph = spec.get("emphasis")
    for j, name in enumerate(cols):
        x = bx + first + j * cw
        hl = isinstance(emph, int) and emph == j
        fill = t["accent"] if hl else t["primary"]
        c.rect(x + 4, by, cw - 8, head, fill, r=18)
        c.box(clean_text(name)[:40], x + 14, by + 8, cw - 28, head - 16, 38, 28, on_color(fill), True, "middle", "middle", 1.15, 2)
    for i, row in enumerate(rows):
        y = by + head + i * rh
        if i % 2 == 0:
            c.rect(bx, y + 4, bw, rh - 8, t["surface"], r=14)
        c.box(clean_text(row.get("label", ""))[:60], bx + 16, y + 8, first - 28, rh - 16, 36, 28, t["text"], True, "start", "middle", 1.15, 3)
        vals = row.get("values") or []
        for j in range(len(cols)):
            v = clean_text(vals[j]) if j < len(vals) else ""
            c.box(v[:80], bx + first + j * cw + 14, y + 8, cw - 28, rh - 16, 36, 28, t["text"], False, "middle", "middle", 1.15, 4)


def _ellipse_positions(n, body, cw, ch):
    bx, by, bw, bh = body
    cx, cy = bx + bw / 2.0, by + bh / 2.0
    rx, ry = bw / 2.0 - cw / 2.0 - 6, bh / 2.0 - ch / 2.0 - 6
    pos = []
    for i in range(n):
        th = -math.pi / 2 + 2 * math.pi * i / n
        pos.append((cx + rx * math.cos(th), cy + ry * math.sin(th), th))
    return (cx, cy, rx, ry), pos


def _clear_radius(pos, cx, cy, cw, ch):
    """Largest circle around the centre that touches none of the cards."""
    best = 1e9
    for (px, py, _th) in pos:
        dx, dy = max(abs(px - cx) - cw / 2.0, 0), max(abs(py - cy) - ch / 2.0, 0)
        best = min(best, math.hypot(dx, dy))
    return best


def _overlaps(pos, cw, ch):
    for i in range(len(pos)):
        for j in range(i + 1, len(pos)):
            if abs(pos[i][0] - pos[j][0]) < cw and abs(pos[i][1] - pos[j][1]) < ch:
                return True
    return False


def _ring_cards(c, spec, body, key, numbered, need_lo, need_hi, what, width_frac=None):
    items = _items(spec, key, need_lo, need_hi, what)
    n = len(items)
    if n > 6:
        c.warn("too_many_items", "%s has %d entries; at most 6 stay readable on a phone" % (what, n))
    bx, by, bw, bh = body
    cw, ch = min(bw * (width_frac or (0.38 if n <= 4 else 0.42)), 400.0), min(bh * (0.17 if n <= 6 else 0.14), 170.0)
    for _ in range(8):
        geom, pos = _ellipse_positions(n, body, cw, ch)
        if not _overlaps(pos, cw, ch):
            break
        cw, ch = cw * 0.92, ch * 0.92
    else:
        c.warn("layout_tight", "%s cards are crowded; use fewer entries" % what)
    return items, geom, pos, cw, ch


def layout_cycle(c, spec, body):
    t = c.t
    items, (cx, cy, rx, ry), pos, cw, ch = _ring_cards(c, spec, body, "steps", True, 3, 8, "cycle")
    n = len(items)
    c.ellipse(cx, cy, rx, ry, t["muted"], 5, "4 14")
    for i in range(n):                                   # arrowheads midway between nodes, clockwise
        th = pos[i][2] + math.pi / n
        px, py = cx + rx * math.cos(th), cy + ry * math.sin(th)
        ang = math.degrees(math.atan2(ry * math.cos(th), -rx * math.sin(th)))
        c.add('<polygon points="16,0 -12,-13 -12,13" fill="%s" transform="translate(%.1f %.1f) rotate(%.1f)"/>' % (t["accent"], px, py, ang))
    center = clean_text(spec.get("center", ""))[:60]
    if center:
        r = min(_clear_radius(pos, cx, cy, cw, ch) - 14, 170.0)
        if r >= 70:
            c.circle(cx, cy, r, t["primary"])
            c.box(center, cx - r * 0.78, cy - r * 0.78, r * 1.56, r * 1.56, 40, 28, on_color(t["primary"]), True, "middle", "middle", 1.15, 4)
    for i, s in enumerate(items):
        label, detail = _label_detail(s)
        x, y = pos[i][0] - cw / 2.0, pos[i][1] - ch / 2.0
        emph = _emph(spec, i, label)
        fill = t["primary"] if emph else t["surface"]
        fg = on_color(fill)
        c.rect(x, y, cw, ch, fill, r=20, stroke=t["border"] if not emph else None, sw=2)
        r = min(24.0, ch * 0.22)
        _badge(c, x + 16 + r, y + 16 + r, r, i + 1, t["accent"], on_color(t["accent"]))
        c.pair(label, detail, x + 24 + 2 * r, y + 8, cw - 40 - 2 * r, ch - 16, fg, fg if emph else t["muted"], 38, 28)


def layout_hub_spoke(c, spec, body):
    t = c.t
    hub = spec.get("hub")
    if not isinstance(hub, (dict, str)):
        raise SpecError("hub_spoke needs 'hub' (a label or {label, detail})")
    items, (cx, cy, rx, ry), pos, cw, ch = _ring_cards(c, spec, body, "spokes", False, 3, 8, "hub_spoke", 0.33)
    for (px, py, _th) in pos:
        c.line(cx, cy, px, py, t["border"], 6)
    hr = max(80.0, min(_clear_radius(pos, cx, cy, cw, ch) - 12, 180.0))
    hl, hd = _label_detail(hub)
    c.circle(cx, cy, hr, t["primary"])
    c.pair(hl, hd, cx - hr * 0.78, cy - hr * 0.78, hr * 1.56, hr * 1.56, on_color(t["primary"]), on_color(t["primary"]), 42, 28, "middle")
    for i, s in enumerate(items):
        label, detail = _label_detail(s)
        x, y = pos[i][0] - cw / 2.0, pos[i][1] - ch / 2.0
        emph = _emph(spec, i, label)
        fill = t["accent"] if emph else t["surface"]
        fg = on_color(fill)
        c.rect(x, y, cw, ch, fill, r=20, stroke=t["border"], sw=2)
        c.pair(label, detail, x + 18, y + 8, cw - 36, ch - 16, fg, fg if emph else t["muted"], 38, 28, "middle")


def layout_funnel(c, spec, body):
    t = c.t
    levels = _items(spec, "levels", 3, 8, "funnel")
    n = len(levels)
    if n > 6:
        c.warn("too_many_items", "funnel has %d levels; at most 6 stay readable on a phone" % n)
    pyramid = str(spec.get("style", "funnel")).lower() == "pyramid"
    bx, by, bw, bh = body
    gap = 10
    lh = min(190.0, (bh - gap * (n - 1)) / n)
    total_h = lh * n + gap * (n - 1)
    y0 = by + (bh - total_h) / 2.0
    cx = bx + bw / 2.0
    lo, hi = (0.30, 1.0) if pyramid else (0.40, 1.0)

    def width(k):                      # funnel narrows downwards; pyramid widens downwards
        f = k / float(n)
        return bw * ((lo + (hi - lo) * f) if pyramid else (hi - (hi - lo) * f))
    for i, lv in enumerate(levels):
        label, detail = _label_detail(lv)
        val = clean_text(lv.get("value", "")) if isinstance(lv, dict) else ""
        if val:
            detail = (val + " - " + detail) if detail else val
        wt, wb = width(i), width(i + 1)
        y = y0 + i * (lh + gap)
        fill = mix(t["primary"], t["secondary"], i / float(max(n - 1, 1)))
        if _emph(spec, i, label):
            fill = t["accent"]
        c.poly([(cx - wt / 2.0, y), (cx + wt / 2.0, y), (cx + wb / 2.0, y + lh), (cx - wb / 2.0, y + lh)], fill)
        tw = (min(wt, wb)) * 0.86
        fg = on_color(fill)
        c.pair(label, detail, cx - tw / 2.0, y + 6, tw, lh - 12, fg, fg, 42, 28, "middle")


def layout_timeline(c, spec, body):
    t = c.t
    events = _items(spec, "events", 2, 9, "timeline")
    n = len(events)
    if n > 6:
        c.warn("too_many_items", "timeline has %d events; at most 6 stay readable on a phone" % n)
    bx, by, bw, bh = body
    seg = bh / float(n)
    lx = bx + 300
    ys = [by + seg * i + seg / 2.0 for i in range(n)]
    c.line(lx, ys[0], lx, ys[-1], t["primary"], 6)
    for i, ev in enumerate(events):
        label, detail = _label_detail(ev)
        when = clean_text(ev.get("when", ""))[:30] if isinstance(ev, dict) else ""
        emph = _emph(spec, i, label)
        c.circle(lx, ys[i], 20 if emph else 15, t["accent"] if emph else t["primary"], stroke=t["background"], sw=5)
        c.box(when, bx, ys[i] - seg / 2.0 + 6, 272, seg - 12, 38, 28, t["accent"], True, "end", "middle", 1.15, 3)
        c.pair(label, detail, lx + 40, ys[i] - seg / 2.0 + 6, bx + bw - lx - 40, seg - 12, t["text"], t["muted"], 46, 30)


def _bullets(c, points, x, y, w, h, good, color_fill, fg):
    n = max(len(points), 1)
    rh = min(120.0, h / n)
    for i, p in enumerate(points):
        yy = y + i * rh
        r = 20
        cx, cy = x + r, yy + rh / 2.0
        c.circle(cx, cy, r, color_fill)
        if good:
            c.polyline([(cx - 9, cy + 1), (cx - 2, cy + 8), (cx + 10, cy - 7)], fg, 4)
        else:
            c.line(cx - 8, cy - 8, cx + 8, cy + 8, fg, 4)
            c.line(cx - 8, cy + 8, cx + 8, cy - 8, fg, 4)
        c.box(clean_text(p)[:110], x + 2 * r + 18, yy + 4, w - 2 * r - 18, rh - 8, 38, 28, c.t["text"], False, "start", "middle", 1.2, 3)


def layout_before_after(c, spec, body):
    t = c.t
    b, a = spec.get("before"), spec.get("after")
    if not isinstance(b, dict) or not isinstance(a, dict) or not b.get("points") or not a.get("points"):
        raise SpecError("before_after needs 'before' and 'after', each with 'heading' and a non-empty 'points' list")
    for side in (b, a):
        if len(side["points"]) > 5:
            c.warn("too_many_items", "before_after has more than 5 points on one side; at most 5 stay readable")
    bx, by, bw, bh = body
    bad_fill, good_fill = mix(t["muted"], t["text"], 0.2), t["secondary"]
    portrait = c.h > c.w
    head = 84
    if portrait:
        arrow = 70
        hh = (bh - arrow) / 2.0
        cols = [(bx, by, bw, hh, b, bad_fill, False), (bx, by + hh + arrow, bw, hh, a, good_fill, True)]
        c.poly([(bx + bw / 2.0 - 30, by + hh + 12), (bx + bw / 2.0 + 30, by + hh + 12), (bx + bw / 2.0, by + hh + arrow - 12)], t["accent"])
    else:
        gap = 90
        cwid = (bw - gap) / 2.0
        cols = [(bx, by, cwid, bh, b, bad_fill, False), (bx + cwid + gap, by, cwid, bh, a, good_fill, True)]
        mx, my = bx + cwid + gap / 2.0, by + bh / 2.0
        c.poly([(mx - 24, my - 30), (mx + 24, my), (mx - 24, my + 30)], t["accent"])
    for x, y, w, h, side, fill, good in cols:
        c.rect(x, y, w, h, t["surface"], r=22)
        c.rect(x, y, w, head, fill, r=22)
        c.rect(x, y + head - 22, w, 22, fill)
        c.box(clean_text(side.get("heading", "Before" if not good else "After"))[:40], x + 24, y + 6, w - 48, head - 12, 42, 30, on_color(fill), True, "start", "middle", 1.1, 1)
        _bullets(c, side["points"], x + 24, y + head + 14, w - 48, h - head - 28, good, fill, on_color(fill))


def layout_stat_callout(c, spec, body):
    t = c.t
    st = spec.get("stat")
    if not isinstance(st, dict) or not clean_text(st.get("value", "")):
        raise SpecError("stat_callout needs 'stat' with a 'value' (for example '3x') and a 'label'")
    bx, by, bw, bh = body
    sup = (spec.get("supporting") or [])[:3]
    sup_h = 170 if sup else 0
    main_h = bh - sup_h - (30 if sup else 0)
    vh = main_h * 0.5
    size, used = c.box(clean_text(st["value"])[:14], bx, by + main_h * 0.04, bw, vh, 300, 100, t["accent"], True, "middle", "middle", 1.0, 1, "heading")
    y = by + main_h * 0.04 + vh + 12
    _, u1 = c.box(clean_text(st.get("label", ""))[:120], bx + 20, y, bw - 40, main_h * 0.26, 54, 32, t["text"], True, "middle", "top", 1.2, 3)
    if st.get("context"):
        c.box(clean_text(st["context"])[:160], bx + 40, y + u1 + 10, bw - 80, main_h * 0.2, 38, 28, t["muted"], False, "middle", "top", 1.25, 3)
    if not str(spec.get("source", "")).strip():
        c.warn("stat_needs_source", "a statistic needs a source (add 'source', or write 'My own data' / 'My experience' if it is yours)")
    if sup:
        gap = 20
        cw = (bw - gap * (len(sup) - 1)) / len(sup)
        for i, s in enumerate(sup):
            x, y2 = bx + i * (cw + gap), by + bh - sup_h
            c.rect(x, y2, cw, sup_h, t["surface"], r=20)
            c.box(clean_text(s.get("value", ""))[:12], x + 12, y2 + 12, cw - 24, 80, 56, 32, t["primary"], True, "middle", "middle", 1.0, 1, "heading")
            c.box(clean_text(s.get("label", ""))[:60], x + 14, y2 + 96, cw - 28, sup_h - 106, 30, 28, t["muted"], False, "middle", "top", 1.2, 2)


def layout_checklist(c, spec, body):
    t = c.t
    items = _items(spec, "items", 2, 10, "checklist")
    n = len(items)
    if n > 7:
        c.warn("too_many_items", "checklist has %d items; at most 7 stay readable on a phone" % n)
    bx, by, bw, bh = body
    rh = min(190.0, bh / n)
    for i, it in enumerate(items):
        label, detail = _label_detail(it)
        done = it.get("done", True) if isinstance(it, dict) else True
        y = by + i * rh
        if i:
            c.line(bx, y, bx + bw, y, t["border"], 2)
        bs = min(54.0, rh * 0.5)
        bxx, byy = bx + 8, y + (rh - bs) / 2.0
        if done:
            c.rect(bxx, byy, bs, bs, t["secondary"], r=12)
            c.polyline([(bxx + bs * 0.24, byy + bs * 0.52), (bxx + bs * 0.43, byy + bs * 0.72), (bxx + bs * 0.78, byy + bs * 0.30)], on_color(t["secondary"]), 6)
        else:
            c.rect(bxx, byy, bs, bs, t["background"], r=12, stroke=t["muted"], sw=4)
        tx = bx + 8 + bs + 28
        c.pair(label, detail, tx, y + 8, bx + bw - tx - 8, rh - 16, t["text"], t["muted"], 48, 30)


LAYOUTS = {
    "process_flow": layout_process_flow, "matrix_2x2": layout_matrix_2x2, "comparison_table": layout_comparison_table,
    "cycle": layout_cycle, "funnel": layout_funnel, "timeline": layout_timeline, "before_after": layout_before_after,
    "hub_spoke": layout_hub_spoke, "stat_callout": layout_stat_callout, "checklist": layout_checklist,
}


def _full_bleed(c, spec, kind, page, total):
    t = c.t
    W, H, pad = c.w, c.h, 84
    c.rect(0, 0, W, H, t["primary"])
    fg = on_color(t["primary"])
    c.rect(pad, pad, 140, 10, t["accent"], r=5)
    if kind == "cover":
        c.box(clean_text(spec.get("title", ""))[:140], pad, H * 0.22, W - 2 * pad, H * 0.44, 104, 56, fg, True, "start", "middle", 1.1, 6, "heading")
        if spec.get("subtitle"):
            c.box(clean_text(spec["subtitle"])[:160], pad, H * 0.68, W - 2 * pad, 150, 38, 26, mix(fg, t["primary"], 0.25), False, "start", "top", 1.3, 3)
        c.box("Swipe", pad, H - 150, 300, 50, 36, 26, fg, True, "start", "middle", 1.1, 1, track=False, count=False)
        c.poly([(pad + 170, H - 142), (pad + 214, H - 125), (pad + 170, H - 108)], t["accent"])
    else:
        c.box(clean_text(spec.get("title", ""))[:140], pad, H * 0.2, W - 2 * pad, H * 0.4, 88, 48, fg, True, "start", "middle", 1.12, 5, "heading")
        if spec.get("subtitle"):
            c.box(clean_text(spec["subtitle"])[:200], pad, H * 0.63, W - 2 * pad, 200, 40, 26, fg, False, "start", "top", 1.3, 4)
    if t.get("footer"):
        c.box(t["footer"], pad, H - 90, W / 2.0, 40, 28, 22, fg, False, "start", "middle", 1.1, 1, track=False, count=False)
    if page and total:
        c.box("%d / %d" % (page, total), W / 2.0, H - 90, W / 2.0 - pad, 40, 26, 20, fg, False, "end", "middle", 1.1, 1, track=False, count=False)


# --------------------------------------------------------------- validation

def validate_spec(spec):
    """Return a list of problems (empty when the spec is usable). Structural problems only; quality is in check_spec."""
    errors = []
    if not isinstance(spec, dict):
        return ["the spec must be a JSON object"]
    typ = spec.get("type")
    if typ == "carousel":
        slides = spec.get("slides")
        if not isinstance(slides, list) or len(slides) < 2:
            errors.append("a carousel needs 'slides' with at least 2 entries")
            return errors
        if len(slides) > 20:
            errors.append("a carousel can have at most 20 slides")
        for i, s in enumerate(slides, 1):
            for e in validate_spec(s if isinstance(s, dict) and s.get("type") != "carousel" else {"type": "?"}):
                errors.append("slide %d: %s" % (i, e))
        return errors
    if typ not in DIAGRAM_TYPES + SLIDE_ONLY:
        errors.append("unknown type %r. Use one of: %s (or 'carousel')" % (typ, ", ".join(DIAGRAM_TYPES)))
        return errors
    if not clean_text(spec.get("title", "")):
        errors.append("'title' is required: write the one-sentence takeaway of the visual")
    probe = Canvas(1080, 1350, dict(DEFAULT_THEME, surface="#EEEEEE", border="#CCCCCC"))
    try:
        if typ in LAYOUTS:
            LAYOUTS[typ](probe, spec, (72, 300, 936, 700))
    except SpecError as e:
        errors.append(str(e))
    except (AttributeError, TypeError, ValueError, KeyError) as e:
        errors.append("the fields for %s are not in the expected shape (%s). Run: visual_engine.py example %s" % (typ, e, typ))
    return errors


# ------------------------------------------------------------------ render

def _svg_doc(c, title, alt):
    body = "\n".join(c.parts)
    return ('<?xml version="1.0" encoding="UTF-8"?>\n<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
            'width="%d" height="%d" viewBox="0 0 %d %d" role="img" aria-labelledby="t d">\n<title id="t">%s</title>\n<desc id="d">%s</desc>\n%s\n</svg>\n'
            % (c.w, c.h, c.w, c.h, esc(title), esc(alt), body))


def render_one(spec, fmt, theme, page=None, total=None):
    """Render one image. Returns dict(svg, width, height, warnings, min_font, words)."""
    global _WIDTH_EXTRA
    errs = validate_spec(spec)
    if errs:
        raise SpecError("; ".join(errs))
    W, H = FORMATS[fmt]
    c = Canvas(W, H, dict(theme))
    typ = spec["type"]
    with _RENDER_LOCK:
        _WIDTH_EXTRA = 1.14 if (theme.get("heading_font") or theme.get("body_font")) else 1.0
        try:
            if typ in SLIDE_ONLY:
                _full_bleed(c, spec, typ, page, total)
            else:
                body = frame(c, spec, fmt, page, total)
                LAYOUTS[typ](c, spec, body)
        finally:
            _WIDTH_EXTRA = 1.0
    limit = MAX_WORDS_SLIDE if total else MAX_WORDS_SINGLE
    if typ not in SLIDE_ONLY and c.words > limit:
        c.warn("too_many_words", "the visual has about %d words (aim for %d or fewer); reduce words before shrinking type" % (c.words, limit))
    short, long_ = describe(spec)
    return {"svg": _svg_doc(c, spec.get("title", ""), short), "width": W, "height": H, "warnings": list(c.warnings),
            "min_font": (None if c.min_font == 999 else c.min_font), "words": c.words}


def describe(spec):
    """Alt text: (short, long). Built only from the spec's own words."""
    typ = spec.get("type")
    title = clean_text(spec.get("title", ""))
    name = TYPE_NAMES.get(typ, typ)
    parts = []

    def ld(i):
        return _label_detail(i)

    def seq(items, prefix):
        out = []
        for k, it in enumerate(items, 1):
            lab, det = ld(it)
            out.append("%s %d: %s%s." % (prefix, k, lab, (" - " + det) if det else ""))
        return out
    if typ == "process_flow":
        parts = ["A %d-step process." % len(spec["steps"])] + seq(spec["steps"], "Step")
    elif typ == "cycle":
        parts = ["A repeating cycle of %d stages." % len(spec["steps"])] + seq(spec["steps"], "Stage")
    elif typ == "matrix_2x2":
        xa, ya = spec.get("x_axis") or {}, spec.get("y_axis") or {}
        parts = ["A two-by-two matrix. Horizontal axis: %s, from %s to %s. Vertical axis: %s, from %s to %s." % (
            xa.get("label", ""), xa.get("low", ""), xa.get("high", ""), ya.get("label", ""), ya.get("low", ""), ya.get("high", ""))]
        for k, nm in enumerate(("Top left", "Top right", "Bottom left", "Bottom right")):
            lab, det = ld(spec["quadrants"][k])
            parts.append("%s: %s%s." % (nm, lab, (" - " + det) if det else ""))
    elif typ == "comparison_table":
        parts = ["A table comparing %s." % ", ".join(clean_text(x) for x in spec["columns"])]
        for r in spec["rows"]:
            parts.append("%s: %s." % (clean_text(r.get("label", "")), "; ".join(clean_text(v) for v in (r.get("values") or []))))
    elif typ == "funnel":
        parts = ["A %s with %d levels from top to bottom." % ("pyramid" if str(spec.get("style", "")).lower() == "pyramid" else "funnel", len(spec["levels"]))] + seq(spec["levels"], "Level")
    elif typ == "timeline":
        parts = ["A timeline of %d events." % len(spec["events"])]
        for k, ev in enumerate(spec["events"], 1):
            lab, det = ld(ev)
            parts.append("%s: %s%s." % (clean_text(ev.get("when", "")) if isinstance(ev, dict) else "Event %d" % k, lab, (" - " + det) if det else ""))
    elif typ == "before_after":
        b, a = spec["before"], spec["after"]
        parts = ["%s: %s." % (clean_text(b.get("heading", "Before")), "; ".join(clean_text(p) for p in b["points"])),
                 "%s: %s." % (clean_text(a.get("heading", "After")), "; ".join(clean_text(p) for p in a["points"]))]
    elif typ == "hub_spoke":
        hl, hd = ld(spec["hub"])
        parts = ["A hub-and-spoke map. Centre: %s." % hl] + ["Connected: %s." % ld(sp)[0] for sp in spec["spokes"]]
    elif typ == "stat_callout":
        st = spec["stat"]
        parts = ["Key figure: %s %s." % (clean_text(st.get("value", "")), clean_text(st.get("label", "")))]
        if st.get("context"):
            parts.append(clean_text(st["context"]) + ".")
        for s in spec.get("supporting") or []:
            parts.append("Also: %s %s." % (clean_text(s.get("value", "")), clean_text(s.get("label", ""))))
    elif typ == "checklist":
        parts = ["A checklist of %d items." % len(spec["items"])]
        for k, it in enumerate(spec["items"], 1):
            lab, det = ld(it)
            done = it.get("done", True) if isinstance(it, dict) else True
            parts.append("%s %s%s." % ("Done:" if done else "To do:", lab, (" - " + det) if det else ""))
    elif typ in SLIDE_ONLY:
        parts = [clean_text(spec.get("subtitle", ""))] if spec.get("subtitle") else []
    if spec.get("takeaway"):
        parts.append("Takeaway: " + clean_text(spec["takeaway"]))
    long_ = ("%s: %s. " % (name.capitalize(), title) + " ".join(p for p in parts if p)).strip()
    if spec.get("alt"):
        long_ = clean_text(spec["alt"])
    short = ("%s: %s" % (name.capitalize(), title)) if title else name.capitalize()
    if len(short) > 120:
        short = short[:117].rstrip() + "..."
    return short, long_


def visual_prompt(spec, theme, fmt="portrait"):
    """A plain-language brief an owner can paste into any design tool to recreate the visual with the exact words."""
    W, H = FORMATS.get(fmt, FORMATS["portrait"])
    typ = spec.get("type")
    name = TYPE_NAMES.get(typ, typ)
    short, long_ = describe(spec)
    lines = ["Create a clean %d x %d px (%s) social-media graphic: a %s." % (W, H, fmt, name),
             "Title (largest text, exactly as written): %s" % clean_text(spec.get("title", "")),
             "Content, using exactly these words and no others:", long_,
             "Style: flat vector look, generous white space, one idea per image, no photographs, no 3D, no decorative charts, no invented statistics or logos.",
             "Colors: primary %s, secondary %s, accent %s, background %s, text %s." % (theme["primary"], theme["secondary"], theme["accent"], theme["background"], theme["text"]),
             "Type: bold sans-serif headings, regular body text; every line at least %d px so it reads on a phone; contrast at least 4.5:1." % MIN_READABLE]
    if theme.get("footer"):
        lines.append("Footer text: %s" % theme["footer"])
    return "\n".join(lines)


def canonical(spec):
    return json.dumps(spec, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def spec_hash(spec):
    return hashlib.sha256(canonical(spec).encode("utf-8")).hexdigest()[:16]


def file_hash(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def check_spec(spec, fmt="portrait", theme=None):
    """Quality report for Visual QA: structural errors, layout warnings, font floor, density, palette."""
    theme = theme or load_theme()[0]
    report = {"errors": validate_spec(spec), "warnings": [], "min_font_px": None, "words": 0, "alt_short": "", "alt_long": ""}
    if report["errors"]:
        return report
    pages = spec["slides"] if spec.get("type") == "carousel" else [spec]
    total = len(pages) if spec.get("type") == "carousel" else None
    f = "portrait" if spec.get("type") == "carousel" else fmt
    mins, words = [], 0
    for i, pg in enumerate(pages, 1):
        r = render_one(pg, f, theme, i if total else None, total)
        for code, msg in r["warnings"]:
            report["warnings"].append({"code": code, "message": ("slide %d: " % i if total else "") + msg})
        if r["min_font"]:
            mins.append(r["min_font"])
        words += r["words"]
    report["min_font_px"] = min(mins) if mins else None
    report["words"] = words
    if spec.get("type") != "carousel":
        report["alt_short"], report["alt_long"] = describe(spec)
    return report


# ------------------------------------------------------------ rasterising

def find_browser():
    env = os.environ.get("LBA_BROWSER")
    if env is not None and not env.strip():
        return None                                  # set to empty on purpose: do not look for a browser at all
    if env and os.path.exists(env):
        return env
    system = platform.system()
    cands = []
    if system == "Darwin":
        cands = ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
                 "/Applications/Chromium.app/Contents/MacOS/Chromium", "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"]
    elif system == "Windows" or "microsoft" in platform.release().lower():
        roots = [os.environ.get(k) for k in ("ProgramFiles", "ProgramFiles(x86)", "LocalAppData")] + ["/mnt/c/Program Files", "/mnt/c/Program Files (x86)"]
        for r in [x for x in roots if x]:
            cands += [os.path.join(r, "Google", "Chrome", "Application", "chrome.exe"), os.path.join(r, "Microsoft", "Edge", "Application", "msedge.exe"),
                      os.path.join(r, "Chromium", "Application", "chrome.exe")]
    for c in cands:
        if os.path.exists(c):
            return c
    for name in ("google-chrome", "google-chrome-stable", "microsoft-edge", "microsoft-edge-stable", "chromium", "chromium-browser", "chrome", "msedge"):
        p = shutil.which(name)
        if p:
            return p
    return None


def _browser_cmd(browser, extra):
    cmd = [browser, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run", "--no-default-browser-check",
           "--disable-extensions", "--force-device-scale-factor=1", "--allow-file-access-from-files"]
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        cmd.append("--no-sandbox")                 # Chrome refuses to run as root otherwise (containers, CI)
    return cmd + extra


def _page_html(svgs, w, h):
    pages = "".join('<div class="p">%s</div>' % re.sub(r"^<\?xml[^>]*\?>\s*", "", s) for s in svgs)
    return ('<!doctype html><html><head><meta charset="utf-8"><style>@page{size:%dpx %dpx;margin:0}html,body{margin:0;padding:0;background:#fff}'
            '.p{width:%dpx;height:%dpx;overflow:hidden;page-break-after:always;break-after:page}.p:last-child{page-break-after:auto;break-after:auto}'
            'svg{display:block}</style></head><body>%s</body></html>' % (w, h, w, h, pages))


def png_size(path):
    with open(path, "rb") as fh:
        head = fh.read(24)
    if head[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    import struct
    return struct.unpack(">II", head[16:24])


def rasterize(svgs, w, h, png=None, pdf=None, timeout=90):
    """Make PNG (first svg) and/or PDF (all svgs, one page each) with Chrome or Edge. Returns dict of results/messages."""
    out = {"png": None, "pdf": None, "messages": []}
    browser = find_browser()
    if not browser:
        out["messages"].append("No Chrome or Edge was found, so only the SVG was made. Install Chrome or Edge (or set LBA_BROWSER to its full path) "
                               "and run the same command again. Meanwhile you can open the .html file in any browser and use Print > Save as PDF.")
        return out
    tmp = tempfile.mkdtemp(prefix="lba-render-")
    try:
        profile = os.path.join(tmp, "profile")
        for kind, target, subset in (("png", png, svgs[:1]), ("pdf", pdf, svgs)):
            if not target:
                continue
            page = os.path.join(tmp, kind + ".html")
            with open(page, "w", encoding="utf-8") as fh:
                fh.write(_page_html(subset, w, h))
            uri = "file:///" + page.replace("\\", "/").lstrip("/")
            tmp_out = os.path.join(tmp, "out." + kind)
            if kind == "png":
                extra = ["--user-data-dir=" + profile, "--window-size=%d,%d" % (w, h), "--screenshot=" + tmp_out, uri]
            else:
                extra = ["--user-data-dir=" + profile, "--no-pdf-header-footer", "--print-to-pdf=" + tmp_out, uri]
            try:
                r = subprocess.run(_browser_cmd(browser, extra), capture_output=True, text=True, timeout=timeout)
            except (OSError, subprocess.SubprocessError) as exc:
                out["messages"].append("%s was not made: %s" % (kind.upper(), exc))
                continue
            if not os.path.exists(tmp_out) or os.path.getsize(tmp_out) < 100:
                out["messages"].append("%s was not made: the browser produced no file (%s)" % (kind.upper(), (r.stderr or r.stdout or "no message").strip()[:160]))
                continue
            os.makedirs(os.path.dirname(os.path.abspath(target)), exist_ok=True)
            shutil.copyfile(tmp_out, target)
            out[kind] = target
            if kind == "png":
                size = png_size(target)
                if size and size != (w, h):
                    out["messages"].append("PNG is %dx%d instead of %dx%d; the browser changed the window size. SVG is exact." % (size[0], size[1], w, h))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return out


# --------------------------------------------------------------- examples

EXAMPLES = {
    "process_flow": {"type": "process_flow", "title": "From vague goal to a plan you can start Monday",
                     "steps": [{"label": "Name the outcome", "detail": "One sentence, measurable"}, {"label": "List the blockers", "detail": "Only the real ones"},
                               {"label": "Pick one lever", "detail": "The change that unlocks the rest"}, {"label": "Schedule the first step", "detail": "Put it on the calendar"}],
                     "emphasis": 2, "takeaway": "Small plans get done."},
    "matrix_2x2": {"type": "matrix_2x2", "title": "Where to spend your next hour",
                   "x_axis": {"label": "Effort", "low": "Low", "high": "High"}, "y_axis": {"label": "Impact", "low": "Low", "high": "High"},
                   "quadrants": [{"label": "Quick wins", "detail": "Do first"}, {"label": "Big bets", "detail": "Plan carefully"},
                                 {"label": "Fill-ins", "detail": "Only if free"}, {"label": "Time sinks", "detail": "Avoid"}], "emphasis": 0},
    "comparison_table": {"type": "comparison_table", "title": "Two ways to run a weekly review", "columns": ["Ad hoc", "Structured"],
                         "rows": [{"label": "Prep time", "values": ["None", "10 minutes"]}, {"label": "Consistency", "values": ["Varies", "Same every week"]},
                                  {"label": "Follow-through", "values": ["Often missed", "Tracked"]}], "emphasis": 1},
    "cycle": {"type": "cycle", "title": "The learning loop that keeps teams improving", "center": "Learn",
              "steps": [{"label": "Try"}, {"label": "Measure"}, {"label": "Reflect"}, {"label": "Adjust"}], "emphasis": 2},
    "funnel": {"type": "funnel", "title": "How a good idea becomes a shipped result",
               "levels": [{"label": "Ideas", "detail": "Everything on the table"}, {"label": "Tested", "detail": "Small, cheap trials"},
                          {"label": "Chosen", "detail": "Evidence says yes"}, {"label": "Shipped", "detail": "Owned by one person"}]},
    "timeline": {"type": "timeline", "title": "A 90-day rollout in four moves",
                 "events": [{"when": "Days 1-14", "label": "Listen", "detail": "Interview the team"}, {"when": "Days 15-45", "label": "Pilot", "detail": "One team, one process"},
                            {"when": "Days 46-75", "label": "Adjust", "detail": "Fix what hurt"}, {"when": "Days 76-90", "label": "Scale", "detail": "Roll out with owners"}], "emphasis": 1},
    "before_after": {"type": "before_after", "title": "What changes when meetings have owners",
                     "before": {"heading": "Before", "points": ["No clear decision", "Notes nobody reads", "Same topic again next week"]},
                     "after": {"heading": "After", "points": ["One decision per meeting", "Actions with names and dates", "Topic closed or escalated"]}},
    "hub_spoke": {"type": "hub_spoke", "title": "One clear message, five places it shows up", "hub": {"label": "Core message"},
                  "spokes": [{"label": "Posts"}, {"label": "Comments"}, {"label": "Talks"}, {"label": "Profile"}, {"label": "Newsletter"}]},
    "stat_callout": {"type": "stat_callout", "title": "Why the first five minutes matter",
                     "stat": {"value": "3x", "label": "more follow-through", "context": "in teams that agree the next step before leaving"},
                     "supporting": [{"value": "5 min", "label": "to agree the step"}, {"value": "1", "label": "named owner"}], "source": "My own team data, 2025"},
    "checklist": {"type": "checklist", "title": "Before you hit send on a hard message",
                  "items": [{"label": "One clear ask"}, {"label": "Facts, not labels", "detail": "What happened, not what it means"}, {"label": "A way for them to reply"}, {"label": "Read it out loud"}]},
    "cover": {"type": "cover", "title": "Five habits that make meetings shorter", "subtitle": "A quick guide for team leads"},
    "closing": {"type": "closing", "title": "Which habit will you try first?", "subtitle": "Tell me in the comments."},
}

TYPE_HELP = {
    "process_flow": "steps: [{label, detail?}] (3-6); emphasis: step number starting at 0 (optional)",
    "matrix_2x2": "x_axis & y_axis: {label, low, high}; quadrants: 4 x {label, detail?} in the order top-left, top-right, bottom-left, bottom-right; emphasis: 0-3",
    "comparison_table": "columns: 2-4 names; rows: [{label, values: [one per column]}] (up to 6); emphasis: column number starting at 0",
    "cycle": "steps: [{label, detail?}] (3-6, drawn clockwise from the top); center: short text (optional); emphasis: step number",
    "funnel": "levels: [{label, detail?, value?}] (3-6, top to bottom); style: 'funnel' (default) or 'pyramid'; emphasis: level number",
    "timeline": "events: [{when, label, detail?}] (3-6); emphasis: event number",
    "before_after": "before & after: {heading, points: [up to 5 short strings]}",
    "hub_spoke": "hub: {label, detail?}; spokes: [{label, detail?}] (3-8); emphasis: spoke number",
    "stat_callout": "stat: {value, label, context?}; supporting: up to 3 x {value, label}; source: REQUIRED (where the number comes from, or 'My own data')",
    "checklist": "items: [{label, detail?, done?}] (3-7); done defaults to true",
    "cover": "title, subtitle? (carousel only)", "closing": "title, subtitle? (carousel only)",
}
COMMON_HELP = ("Every spec: type, title (the one-sentence takeaway), subtitle?, takeaway? (one bottom line), source?, alt? (override alt text). "
               "Use the owner's approved words only; never invent numbers. A carousel is {type: 'carousel', title, slides: [cover, ...diagram specs..., closing]}.")


def types_text():
    out = [COMMON_HELP, ""]
    for t in DIAGRAM_TYPES + SLIDE_ONLY:
        out.append("%s (%s): %s" % (t, TYPE_NAMES[t], TYPE_HELP[t]))
    return "\n".join(out)


# --------------------------------------------------------------------- CLI

def _read_json(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError) as exc:
        raise SpecError("could not read %s: %s" % (path, exc))


def _slug(s):
    return re.sub(r"[^A-Za-z0-9._-]+", "-", s).strip("-")[:60] or "visual"


def render_files(spec, out_dir, name, fmt, theme, want_png, want_pdf, workspace_warnings=()):
    """Render a spec to files. Returns the meta dict that is also saved as <name>.meta.json."""
    os.makedirs(out_dir, exist_ok=True)
    is_carousel = spec.get("type") == "carousel"
    if is_carousel:
        fmt = "portrait"
        pages = [dict(p) for p in spec["slides"]]
    else:
        pages = [spec]
    total = len(pages) if is_carousel else None
    results, files, warnings = [], [], [{"code": c_, "message": m} for c_, m in workspace_warnings]
    svg_paths = []
    for i, pg in enumerate(pages, 1):
        r = render_one(pg, fmt, theme, i if total else None, total)
        results.append(r)
        fn = "%s-slide-%02d.svg" % (name, i) if is_carousel else "%s.svg" % name
        path = os.path.join(out_dir, fn)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(r["svg"])
        svg_paths.append(path)
        files.append({"file": fn, "sha256": file_hash(path)})
        for code, msg in r["warnings"]:
            warnings.append({"code": code, "message": ("slide %d: " % i if total else "") + msg})
    w, h = FORMATS[fmt]
    messages = []
    png_path = pdf_path = None
    if want_png or want_pdf:
        want_png_path = None
        if want_png:
            want_png_path = os.path.join(out_dir, "%s-slide-01.png" % name if is_carousel else "%s.png" % name)
        pdf_target = os.path.join(out_dir, name + ".pdf") if (want_pdf or is_carousel) and want_pdf else None
        res = rasterize([r["svg"] for r in results], w, h, want_png_path, pdf_target)
        messages += res["messages"]
        png_path, pdf_path = res["png"], res["pdf"]
        for kind, pth in (("png", png_path), ("pdf", pdf_path)):
            if pth:
                files.append({"file": os.path.basename(pth), "sha256": file_hash(pth), "derived": True})
        if not find_browser():
            html_path = os.path.join(out_dir, name + ".html")
            with open(html_path, "w", encoding="utf-8") as fh:
                fh.write(_page_html([r["svg"] for r in results], w, h))
            files.append({"file": os.path.basename(html_path), "sha256": file_hash(html_path), "derived": True})
    short, long_ = describe(spec if not is_carousel else {"type": "carousel", "title": spec.get("title", "")})
    if is_carousel:
        short = "Carousel: %s" % clean_text(spec.get("title", ""))
        long_ = "Carousel of %d slides: %s. " % (len(pages), clean_text(spec.get("title", ""))) + " ".join(
            "Slide %d. %s" % (i, describe(p)[1]) for i, p in enumerate(pages, 1))
    first = pages[0] if not is_carousel else next((p for p in pages if p.get("type") in DIAGRAM_TYPES), pages[0])
    with open(os.path.join(out_dir, name + ".alt.txt"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write("SHORT (up to 120 characters)\n%s\n\nFULL DESCRIPTION\n%s\n" % (short[:120], long_))
    with open(os.path.join(out_dir, name + ".prompt.txt"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(visual_prompt(first if not is_carousel else {"type": "carousel", "title": spec.get("title", "")}, theme, fmt) + "\n")
    meta = {"name": name, "format": "carousel" if is_carousel else fmt, "width": w, "height": h, "spec_fingerprint": spec_hash(spec),
            "files": files, "warnings": warnings, "min_font_px": min([r["min_font"] for r in results if r["min_font"]] or [0]) or None,
            "alt_short": short[:120], "alt_long": long_, "messages": messages}
    with open(os.path.join(out_dir, name + ".meta.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(meta, fh, indent=2)
        fh.write("\n")
    return meta


def cmd_render(a):
    spec = _read_json(a.spec)
    theme, tw = load_theme(a.workspace, a.theme)
    fmt = a.format
    if fmt == "carousel" and spec.get("type") != "carousel":
        raise SpecError("--format carousel needs a spec of type 'carousel' (with 'slides')")
    if spec.get("type") == "carousel":
        fmt = "carousel"
    name = _slug(a.name or os.path.splitext(os.path.basename(a.spec))[0])
    meta = render_files(spec, a.out, name, "portrait" if fmt == "carousel" else fmt, theme, a.png, a.pdf, tw)
    print("Rendered %s (%s) -> %s" % (name, meta["format"], a.out))
    for f in meta["files"]:
        print("  " + f["file"])
    print("  %s.alt.txt, %s.prompt.txt, %s.meta.json" % (name, name, name))
    for m in meta["messages"]:
        print("note: " + m)
    for w in meta["warnings"]:
        print("warning [%s]: %s" % (w["code"], w["message"]))
    return 0


def make_previews(items, out_dir, fmt, theme, png=False, theme_warnings=()):
    """Render exactly 3 previews of 3 different diagram types. Returns the index list (also saved as previews.json)."""
    if not isinstance(items, list) or len(items) != 3:
        raise SpecError("previews needs exactly 3 specs (a list, or {\"previews\": [...]})")
    specs = [(i.get("spec") if isinstance(i, dict) and "spec" in i else i) for i in items]
    types = [s.get("type") if isinstance(s, dict) else None for s in specs]
    if len(set(types)) != 3:
        raise SpecError("the 3 previews must be 3 different diagram types (got: %s)" % ", ".join(str(t) for t in types))
    if any(t in SLIDE_ONLY + ["carousel"] for t in types):
        raise SpecError("previews must be diagram types, not cover, closing or carousel")
    os.makedirs(out_dir, exist_ok=True)
    index = []
    for i, (spec, raw) in enumerate(zip(specs, items), 1):
        meta = render_files(spec, out_dir, "preview-%d" % i, fmt, theme, png, False, theme_warnings)
        index.append({"number": i, "type": spec["type"], "title": clean_text(spec.get("title", "")),
                      "reason": clean_text(raw.get("reason", "")) if isinstance(raw, dict) else "", "spec_fingerprint": meta["spec_fingerprint"],
                      "svg": "preview-%d.svg" % i, "png": ("preview-%d.png" % i) if os.path.exists(os.path.join(out_dir, "preview-%d.png" % i)) else None,
                      "warnings": meta["warnings"], "alt_short": meta["alt_short"]})
        with open(os.path.join(out_dir, "preview-%d.spec.json" % i), "w", encoding="utf-8", newline="\n") as fh:
            json.dump(spec, fh, indent=2)
            fh.write("\n")
    with open(os.path.join(out_dir, "previews.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump({"previews": index}, fh, indent=2)
        fh.write("\n")
    cells = "".join('<figure><img src="%s" alt="%s"><figcaption><b>%d. %s</b><br>%s</figcaption></figure>'
                    % (esc(x["png"] or x["svg"]), esc(x["alt_short"]), x["number"], esc(TYPE_NAMES.get(x["type"], x["type"]).title()), esc(x["reason"])) for x in index)
    with open(os.path.join(out_dir, "previews.html"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write('<!doctype html><meta charset="utf-8"><title>Visual previews</title><style>body{font-family:sans-serif;margin:24px}'
                 'div{display:flex;gap:20px;flex-wrap:wrap}figure{margin:0;width:31%%;min-width:260px}img{width:100%%;border:1px solid #ccc}</style>'
                 '<h1>Pick one of 3 visuals</h1><div>%s</div>' % cells)
    return index


def cmd_previews(a):
    data = _read_json(a.specs)
    items = data.get("previews") if isinstance(data, dict) else data
    theme, tw = load_theme(a.workspace, a.theme)
    index = make_previews(items, a.out, a.format, theme, a.png, tw)
    print("3 previews written to %s" % a.out)
    for x in index:
        print("  %d. %s: %s" % (x["number"], x["type"], x["title"]))
        for w in x["warnings"]:
            print("     warning [%s]: %s" % (w["code"], w["message"]))
    return 0


def cmd_check(a):
    spec = _read_json(a.spec)
    theme, tw = load_theme(a.workspace, a.theme)
    rep = check_spec(spec, a.format, theme)
    rep["warnings"] = [{"code": c_, "message": m} for c_, m in tw] + rep["warnings"]
    print(json.dumps(rep, indent=2))
    return 1 if rep["errors"] else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Render visual specs to SVG, PNG and PDF.")
    ap.add_argument("--workspace", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("types", help="list the diagram types")
    e = sub.add_parser("example", help="print a starter spec")
    e.add_argument("type", choices=sorted(EXAMPLES) + ["carousel"])
    for nm in ("render", "check", "previews"):
        p = sub.add_parser(nm)
        p.add_argument("--spec" if nm != "previews" else "--specs", required=True)
        p.add_argument("--theme", help="JSON file with colors, fonts, logo and footer (overrides the brand profile)")
        p.add_argument("--format", choices=["portrait", "square", "carousel"], default="portrait")
        if nm != "check":
            p.add_argument("--out", required=True)
            p.add_argument("--png", action="store_true", help="also make a PNG with Chrome or Edge")
        if nm == "render":
            p.add_argument("--pdf", action="store_true", help="also make a PDF (a carousel is always a PDF)")
            p.add_argument("--name")
    sub.add_parser("browser", help="show the Chrome or Edge that was found")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "types":
            print(types_text())
            return 0
        if a.cmd == "example":
            if a.type == "carousel":
                spec = {"type": "carousel", "title": "Five habits that make meetings shorter",
                        "slides": [EXAMPLES["cover"], EXAMPLES["process_flow"], EXAMPLES["checklist"], EXAMPLES["closing"]]}
            else:
                spec = EXAMPLES[a.type]
            print(json.dumps(spec, indent=2))
            return 0
        if a.cmd == "browser":
            b = find_browser()
            print(b if b else "no Chrome or Edge found (set LBA_BROWSER to its full path to use another browser)")
            return 0 if b else 1
        if a.cmd == "render":
            return cmd_render(a)
        if a.cmd == "previews":
            return cmd_previews(a)
        return cmd_check(a)
    except SpecError as exc:
        print("visual_engine: %s" % exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
