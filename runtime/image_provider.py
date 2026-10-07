#!/usr/bin/env python3
"""A ready-made socket for an AI image provider. No provider is connected today.

Your visuals are drawn by the diagram generator (exact words, no AI image). If you later want AI-made illustrations,
a provider plugs in here without changing anything else:

    python3 scripts/image_provider.py status
    python3 scripts/image_provider.py generate --prompt-file drafts/P-.../final/visual.prompt.txt --out picture.png

To add a provider, write one function and register it in this file (or in a file you import here):

    @register("MyProvider")                       # the name you chose in the setup wizard ("Image provider")
    def my_provider(prompt, out_path, settings):
        key = os.environ["MY_PROVIDER_API_KEY"]   # keys are read from environment variables ONLY, never stored in a file
        ...                                       # call the provider, save the image to out_path
        return out_path

Rules for any provider you add: read the key from an environment variable; send only the visual prompt (never the post text
or your brand profile); tell the owner that AI-made images can contain wrong text, so the visual still needs Visual QA and
the owner's approval (decisions 2 and 3) before anything is used.

Needs Python 3.8+ and nothing else.
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROVIDERS = {}


class NotConfigured(RuntimeError):
    """No image provider is connected (or the chosen one has no code here yet)."""


def register(name):
    def deco(fn):
        PROVIDERS[name.lower()] = fn
        return fn
    return deco


def load_settings(workspace):
    try:
        with open(os.path.join(workspace, "docs", "settings.json"), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def chosen(workspace):
    return str(load_settings(workspace).get("image_provider") or "").strip()


def generate_image(prompt, out_path, workspace):
    name = chosen(workspace)
    if not name or name.lower().startswith("none"):
        raise NotConfigured("No image provider is chosen. Your visuals are drawn by the diagram generator, which needs none.")
    fn = PROVIDERS.get(name.lower())
    if fn is None:
        raise NotConfigured("The image provider %r is recorded in your settings, but this install has no code for it yet. See the top of scripts/image_provider.py to add one." % name)
    return fn(prompt, out_path, load_settings(workspace))


def main(argv=None):
    ap = argparse.ArgumentParser(description="AI image provider socket (nothing connected by default).")
    ap.add_argument("--workspace", default=os.path.dirname(HERE))
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    g = sub.add_parser("generate")
    g.add_argument("--prompt-file", required=True)
    g.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    ws = os.path.abspath(a.workspace)
    if a.cmd == "status":
        name = chosen(ws)
        print("Image provider in your settings: %s" % (name or "(none)"))
        print("Code available for it here: %s" % ("yes" if name.lower() in PROVIDERS else "no"))
        return 0
    try:
        with open(a.prompt_file, encoding="utf-8") as fh:
            prompt = fh.read()
        print(generate_image(prompt, a.out, ws))
        return 0
    except NotConfigured as exc:
        print("image_provider: %s" % exc, file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
