"""Pure parts of the browser-backed sources (no network, no browser)."""

from __future__ import annotations

import unittest
from unittest import mock

from vidforge.assets import get_provider
from vidforge.assets.baidu import BaiduImagesProvider, _TABLE, decode_url

_REV = {v: k for k, v in _TABLE.items()}


def obfuscate(url: str) -> str:
    """Inverse of decode_url, for building test vectors."""
    body = "".join(chr(_REV.get(ord(ch), ord(ch))) for ch in url)
    return body.replace(":", "_z2C$q").replace(".", "_z&e3B").replace("/", "AzdH3F")
from vidforge.browser.chat import SITES


class Baidu(unittest.TestCase):
    def test_objurl_decode(self):
        for url in ("http://www.abc.com/1.jpg", "https://img.example.cn/a-b_c/9.png"):
            self.assertEqual(decode_url(obfuscate(url)), url)

    def test_registry_and_labels(self):
        self.assertEqual(get_provider("baidu").name, "baidu")
        self.assertEqual(get_provider("google").name, "google")
        self.assertEqual(get_provider("google_all").name, "google_all")
        self.assertEqual(BaiduImagesProvider().search("x", "video"), [], "images only")

    def test_search_parses_repaired_json(self):
        body = ('{"data":[{"thumbURL":"https://t/1.jpg","middleURL":"https://m/1.jpg","objURL":"' + obfuscate("http://www.abc.com/1") + '",'
                '"fromURL":"","fromPageTitleEnc":"<strong>盘</strong>古 \\\'quoted\\\'","width":800,"height":600},{}]}').encode()
        class R:
            status = 200
            def read(self): return body
            def __enter__(self): return self
            def __exit__(self, *a): return False
        with mock.patch("urllib.request.urlopen", return_value=R()):
            cands = BaiduImagesProvider().search("盘古", "image")
        self.assertEqual(len(cands), 1)
        self.assertEqual(cands[0].download_url, "http://www.abc.com/1")
        self.assertIn("版权未知", cands[0].license)
        self.assertEqual(cands[0].title, "盘古 'quoted'")


class ChatSites(unittest.TestCase):
    def test_sites_have_required_keys(self):
        for k, v in SITES.items():
            for key in ("label", "url", "input", "answer", "stop"):
                self.assertIn(key, v, f"{k} missing {key}")
            self.assertTrue(v["url"].startswith("https://"))


if __name__ == "__main__":
    unittest.main()
