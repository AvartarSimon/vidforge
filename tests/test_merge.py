"""Saving project.json without losing what someone else wrote meanwhile (merge.py, State.write_raw)."""
from __future__ import annotations

import copy
import json
import shutil
import tempfile
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

from vidforge import ui

ui.State.WARM = False      # no background Whisper outliving a temp project; tested on its own
from vidforge.merge import merge3

BASE = {"title": "四十岁", "voice": "zh-CN-YunxiNeural", "segments": [
    {"id": "seg1", "text": "第一段", "clips": []},
    {"id": "seg2", "text": "第二段", "clips": []}]}


class Rules(unittest.TestCase):
    def test_the_servers_take_survives_the_pages_older_copy(self):
        # the studio saved a take as seg1's narration and picture; the page then autosaved what it had
        theirs = copy.deepcopy(BASE)
        theirs["segments"][0].update(narration="assets/takes/seg1.mp4", clips=[{"video": "assets/takes/seg1.mp4"}])
        mine = copy.deepcopy(BASE)
        mine["title"] = "四十岁，我决定重启人生"
        out = merge3(BASE, mine, theirs)
        self.assertEqual(out["title"], "四十岁，我决定重启人生", "the page's edit")
        self.assertEqual(out["segments"][0]["narration"], "assets/takes/seg1.mp4", "the server's take")
        self.assertEqual(out["segments"][0]["clips"], [{"video": "assets/takes/seg1.mp4"}])

    def test_unchanged_page_takes_the_disk_and_unchanged_disk_takes_the_page(self):
        other = copy.deepcopy(BASE)
        other["voice"] = "x"
        self.assertEqual(merge3(BASE, BASE, other), other)
        self.assertEqual(merge3(BASE, other, BASE), other)

    def test_segments_merge_by_id_with_adds_deletes_and_order(self):
        mine = copy.deepcopy(BASE)
        mine["segments"].reverse()                                   # the page reordered
        mine["segments"].append({"id": "seg3", "text": "新", "clips": []})
        theirs = copy.deepcopy(BASE)
        theirs["segments"][1]["narration"] = "assets/narration/seg2.webm"
        out = merge3(BASE, mine, theirs)
        self.assertEqual([s["id"] for s in out["segments"]], ["seg2", "seg1", "seg3"])
        self.assertEqual(out["segments"][0]["narration"], "assets/narration/seg2.webm")
        mine = copy.deepcopy(BASE)
        del mine["segments"][1]                                      # the page deleted seg2
        self.assertEqual([s["id"] for s in merge3(BASE, mine, BASE)["segments"]], ["seg1"])

    def test_a_key_the_page_removed_stays_removed_and_one_the_disk_added_arrives(self):
        base = {"a": 1, "b": 2, "segments": []}
        mine = {"a": 1, "segments": []}
        theirs = {"a": 1, "b": 2, "c": 3, "segments": []}
        self.assertEqual(merge3(base, mine, theirs), {"a": 1, "c": 3, "segments": []})

    def test_both_changed_one_field_the_page_wins(self):
        mine, theirs = dict(BASE, title="页面"), dict(BASE, title="磁盘")
        self.assertEqual(merge3(BASE, mine, theirs)["title"], "页面")


class Server(unittest.TestCase):
    def setUp(self):
        self.td = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.td, True)
        patcher = mock.patch.object(ui, "RECENT", self.td / "recent.json")
        patcher.start()
        self.addCleanup(patcher.stop)
        (self.td / "p").mkdir()
        self.path = self.td / "p" / "project.json"
        self.path.write_text(json.dumps(BASE, ensure_ascii=False), encoding="utf-8")
        (self.td / "p" / "assets" / "takes").mkdir(parents=True)
        (self.td / "p" / "assets" / "takes" / "seg1.mp4").write_bytes(b"take")   # the project checks it exists
        self.state = ui.State(self.path)
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), ui.make_handler(self.state))
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.addCleanup(lambda: (self.httpd.shutdown(), self.httpd.server_close()))

    def save(self, raw, base):
        req = urllib.request.Request(f"http://127.0.0.1:{self.httpd.server_address[1]}/api/project",
                                     data=json.dumps({"raw": raw, "base": base}).encode(), headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())

    def disk(self):
        return json.loads(self.path.read_text(encoding="utf-8"))

    def test_a_take_saved_while_the_page_is_open_is_not_overwritten_by_its_autosave(self):
        loaded = self.disk()                                         # what the page has
        server = self.state.read_raw()                               # the studio saves a take
        server["segments"][0]["narration"] = "assets/takes/seg1.mp4"
        self.state.write_raw(server, snapshot=True)
        page = copy.deepcopy(loaded)
        page["segments"][1]["text"] = "第二段，改过"                  # an unrelated edit, then autosave
        j = self.save(page, loaded)
        self.assertTrue(j["merged"])
        self.assertEqual(j["raw"]["segments"][0]["narration"], "assets/takes/seg1.mp4", "the page is told")
        on_disk = self.disk()
        self.assertEqual(on_disk["segments"][0]["narration"], "assets/takes/seg1.mp4")
        self.assertEqual(on_disk["segments"][1]["text"], "第二段，改过")

    def test_a_slow_server_write_keeps_what_the_page_saved_meanwhile(self):
        server = self.state.read_raw()                               # e.g. the studio starts transcoding
        loaded = self.disk()
        page = copy.deepcopy(loaded)
        page["title"] = "改了标题"
        self.save(page, loaded)                                      # the page saves during it
        server["segments"][0]["narration"] = "assets/takes/seg1.mp4"
        self.state.write_raw(server)                                 # the take lands afterwards
        on_disk = self.disk()
        self.assertEqual(on_disk["title"], "改了标题", "the page's save survives the late write")
        self.assertEqual(on_disk["segments"][0]["narration"], "assets/takes/seg1.mp4")

    def call(self, path, body=None):
        req = urllib.request.Request(f"http://127.0.0.1:{self.httpd.server_address[1]}{path}",
                                     data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_every_recording_is_listed_and_one_the_project_lost_goes_back(self):
        import subprocess
        from vidforge import ffmpeg
        ff = ffmpeg.find_binary("ffmpeg")
        take = self.td / "p" / "assets" / "takes" / "seg2_20261117-201620_cut.mp4"
        subprocess.run([ff, "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=s=160x90:r=10:d=2", "-f", "lavfi", "-i", "sine=d=2",
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(take)], check=True)
        voice = self.td / "p" / "assets" / "narration" / "seg2_20261117-201620.m4a"
        voice.parent.mkdir(parents=True)
        subprocess.run([ff, "-v", "error", "-y", "-f", "lavfi", "-i", "sine=d=2", str(voice)], check=True)
        code, j = self.call("/api/takes")
        listed = {t["name"]: t for t in j["takes"]}
        self.assertEqual(listed[take.name]["used_by"], [], "on disk, not in the project: the case to recover")
        self.assertTrue(listed[take.name]["video"])
        self.assertFalse(listed[voice.name]["video"])
        self.assertEqual(listed[voice.name].get("source_of"), take.name, "the raw upload is paired, not 「没被用上」")
        code, j = self.call("/api/takes/use", {"path": f"assets/takes/{take.name}", "segment": "seg2", "as": "window"})
        self.assertEqual(code, 200, j)
        seg = self.disk()["segments"][1]
        self.assertEqual((seg["narration"], seg["overlays"][0]["video"]), (f"assets/takes/{take.name}",) * 2)
        self.assertEqual({t["name"]: t["used_by"] for t in self.call("/api/takes")[1]["takes"]}[take.name], ["seg2"])
        self.assertEqual(self.call("/api/takes/use", {"path": f"assets/narration/{voice.name}", "segment": "seg2", "as": "visual"})[0], 400,
                         "a voice recording has no picture")
        self.assertEqual(self.call("/api/takes/use", {"path": "../../etc/passwd", "segment": "seg2"})[0], 400)

    def test_a_take_moved_on_from_is_kept_without_touching_the_project(self):
        import base64
        import subprocess
        from vidforge import ffmpeg
        clip = self.td / "c.webm"
        subprocess.run([ffmpeg.find_binary("ffmpeg"), "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=s=160x90:r=10:d=1",
                        "-f", "lavfi", "-i", "sine=d=1", "-c:v", "libvpx", "-c:a", "libopus", "-shortest", str(clip)], check=True)
        before = self.path.read_bytes()
        code, j = self.call("/api/record/save", {"segment": "seg2", "data": base64.b64encode(clip.read_bytes()).decode(),
                                                 "ext": "webm", "keep_only": True, "as_narration": False})
        self.assertEqual(code, 200, j)
        self.assertTrue((self.td / "p" / j["kept"]).is_file())
        self.assertEqual(self.path.read_bytes(), before, "kept, not used")
        listed = {t["path"]: t for t in self.call("/api/takes")[1]["takes"]}
        self.assertEqual(listed[j["kept"]]["used_by"], [])

    def test_an_old_page_without_a_base_still_saves(self):
        page = self.disk()
        page["title"] = "旧页面"
        req = urllib.request.Request(f"http://127.0.0.1:{self.httpd.server_address[1]}/api/project",
                                     data=json.dumps({"raw": page}).encode(), headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as r:
            self.assertFalse(json.loads(r.read())["merged"])
        self.assertEqual(self.disk()["title"], "旧页面")


if __name__ == "__main__":
    unittest.main()
