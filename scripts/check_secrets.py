#!/usr/bin/env python3
"""Scans the repository for things that look like real keys, tokens or private keys. Used by the tests and by CI.

    python3 scripts/check_secrets.py              # scans the repository this file lives in
    python3 scripts/check_secrets.py --root DIR

Exit code 1 means something suspicious was found (the file and line are shown, never the secret itself).
The tests folder is skipped because it deliberately contains fake keys to prove that nothing leaks.
"""
import argparse
import os
import re
import sys

PATTERNS = [
    ("private key block", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY")),
    ("service key (sk_ / sk-)", re.compile(r"\bsk[_-](?:live|test)?[_-]?[A-Za-z0-9]{20,}")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}")),
    ("AWS access key id", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("Slack token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}")),
    ("live token (pf_live_ / pk_live_)", re.compile(r"\b(?:pf|pk|rk)_live_[A-Za-z0-9]{10,}")),
    ("key assigned in code", re.compile(r"(?i)\b(?:api[_-]?key|secret|token|password)\s*[:=]\s*[\"'][A-Za-z0-9_\-]{20,}[\"']")),
]
SKIP_DIRS = {".git", "tests", "__pycache__", "node_modules"}
TEXT_EXT = {".py", ".md", ".json", ".sh", ".ps1", ".yml", ".yaml", ".txt", ".js", ".css", ".html", ".toml", ".cfg", ".ini", ".env", ""}


def scan(root):
    hits = []
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in files:
            if os.path.splitext(f)[1].lower() not in TEXT_EXT:
                continue
            path = os.path.join(dirpath, f)
            try:
                with open(path, encoding="utf-8") as fh:
                    for n, line in enumerate(fh, 1):
                        for label, rx in PATTERNS:
                            if rx.search(line):
                                hits.append((os.path.relpath(path, root), n, label))
            except (OSError, UnicodeDecodeError):
                continue
    return hits


def main(argv=None):
    ap = argparse.ArgumentParser(description="Look for keys and tokens in the repository.")
    ap.add_argument("--root", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    a = ap.parse_args(argv)
    hits = scan(os.path.abspath(a.root))
    for rel, n, label in hits:
        print("%s:%d: looks like a %s" % (rel, n, label))
    print("No secrets found." if not hits else "%d suspicious line(s). Remove them and rotate any real key." % len(hits))
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
