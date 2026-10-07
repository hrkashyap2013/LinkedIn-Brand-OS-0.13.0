"""Small file helpers shared by the tests (they close every file they open)."""
import json


def rtext(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def rbytes(path):
    with open(path, "rb") as fh:
        return fh.read()


def wtext(path, text):
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def jload(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def jdump(obj, path):
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(obj, fh)


def jlines(path):
    with open(path, encoding="utf-8") as fh:
        return [json.loads(x) for x in fh if x.strip()]


def make_workspace(settings=None):
    """A fresh workspace built from the repo templates (no shell needed, so it works on every system)."""
    import os
    import shutil
    import tempfile
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ws = tempfile.mkdtemp(prefix="lba-ws-")
    for d in ("docs", "memory", "scripts", "runs", "drafts", "inbox", "reports"):
        os.makedirs(os.path.join(ws, d), exist_ok=True)
    for f in os.listdir(os.path.join(root, "memory")):
        shutil.copy(os.path.join(root, "memory", f), os.path.join(ws, "memory", f))
    for f in ("brand-profile.md", "schedule.json", "settings.json", "metrics-columns.json"):
        shutil.copy(os.path.join(root, "docs", f), os.path.join(ws, "docs", f))
    for dirpath, _dirs, files in os.walk(os.path.join(root, "runtime")):
        if "__pycache__" in dirpath:
            continue
        rel = os.path.relpath(dirpath, os.path.join(root, "runtime"))
        for f in files:
            dst = os.path.join(ws, "scripts", rel) if rel != "." else os.path.join(ws, "scripts")
            os.makedirs(dst, exist_ok=True)
            shutil.copy(os.path.join(dirpath, f), os.path.join(dst, f))
    for src, dst in (("prompts", "prompts"), (".claude", ".claude")):
        shutil.copytree(os.path.join(root, src), os.path.join(ws, dst))
    if settings:
        jdump(settings, os.path.join(ws, "docs", "settings.json"))
    return ws


def _build():
    import os
    import sys
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, os.path.join(root, "scripts"))
    import build
    return build


_B = _build()
AGENT_COUNT = len(_B.ORDER)                                                                       # specialist agents
SKILL_COUNT = AGENT_COUNT + 1                                                                     # plus the orchestrator
COMMAND_COUNT = len(_B.COMMANDS) + len([n for n in _B.ORDER if n not in _B.COMMANDS]) + 3        # explicit + one per remaining agent + auto, orchestrator, scheduled
