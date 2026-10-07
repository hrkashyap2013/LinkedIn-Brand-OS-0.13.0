"""The image-provider socket: nothing connected by default, and a registered provider is used only when chosen."""
import os
import shutil
import sys
import unittest

from tests.helpers import jdump, make_workspace

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "runtime"))
import image_provider as ip  # noqa: E402


class Socket(unittest.TestCase):
    def setUp(self):
        self.ws = make_workspace()

    def tearDown(self):
        ip.PROVIDERS.pop("fakeprov", None)
        shutil.rmtree(self.ws, ignore_errors=True)

    def test_default_is_not_configured_with_a_helpful_message(self):
        for name in ("", "None (I make or upload visuals myself)"):
            jdump({"image_provider": name}, os.path.join(self.ws, "docs", "settings.json"))
            with self.assertRaises(ip.NotConfigured) as cm:
                ip.generate_image("p", os.path.join(self.ws, "o.png"), self.ws)
            self.assertIn("diagram generator", str(cm.exception))

    def test_a_recorded_provider_without_code_says_so(self):
        jdump({"image_provider": "OpenAI"}, os.path.join(self.ws, "docs", "settings.json"))
        with self.assertRaises(ip.NotConfigured) as cm:
            ip.generate_image("p", "o.png", self.ws)
        self.assertIn("no code for it yet", str(cm.exception))

    def test_a_registered_provider_is_called_with_the_prompt_only(self):
        seen = {}

        @ip.register("FakeProv")
        def fake(prompt, out_path, settings):
            seen.update(prompt=prompt, out=out_path)
            return out_path
        jdump({"image_provider": "FakeProv"}, os.path.join(self.ws, "docs", "settings.json"))
        self.assertEqual(ip.generate_image("draw a funnel", "x.png", self.ws), "x.png")
        self.assertEqual(seen, {"prompt": "draw a funnel", "out": "x.png"})

    def test_the_command_line_exits_3_when_nothing_is_connected(self):
        self.assertEqual(ip.main(["--workspace", self.ws, "status"]), 0)
        p = os.path.join(self.ws, "p.txt")
        with open(p, "w") as fh:
            fh.write("x")
        self.assertEqual(ip.main(["--workspace", self.ws, "generate", "--prompt-file", p, "--out", os.path.join(self.ws, "o.png")]), 3)


if __name__ == "__main__":
    unittest.main()
