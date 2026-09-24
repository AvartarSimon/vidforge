"""Face tracking maths — no OpenCV, no video: track() is where the flicker is dealt with."""

from __future__ import annotations

import unittest
from pathlib import Path

from vidforge.video.heads import Box, track


def box(frame, x, y, size=100):
    return Box(frame, float(x), float(y), float(size), float(size))


class Track(unittest.TestCase):
    def test_a_face_moving_across_frames_is_one_track(self):
        boxes = [box(i, 100 + i * 2, 100) for i in range(10)]
        tracks = track(boxes, frames=10)
        self.assertEqual(len(tracks), 1)
        self.assertEqual(sorted(tracks[0].boxes), list(range(10)))

    def test_a_short_gap_is_filled_in_so_the_cover_does_not_flash_off(self):
        boxes = [box(i, 100, 100) for i in (0, 1, 2, 7, 8, 9)]      # detector lost it for 4 frames
        tracks = track(boxes, frames=10)
        self.assertEqual(len(tracks), 1)
        self.assertEqual(sorted(tracks[0].boxes), list(range(10)))  # 3..6 interpolated

    def test_a_long_gap_starts_a_new_track(self):
        boxes = [box(i, 100, 100) for i in (0, 1, 2)] + [box(i, 100, 100) for i in (40, 41, 42)]
        self.assertEqual(len(track(boxes, frames=50, max_gap=12)), 2)

    def test_two_faces_far_apart_stay_separate(self):
        boxes = [box(i, 100, 100) for i in range(6)] + [box(i, 900, 120) for i in range(6)]
        tracks = track(boxes, frames=6)
        self.assertEqual(len(tracks), 2)
        centres = sorted(round(t.boxes[5].cx) for t in tracks)
        self.assertLess(centres[0], 300)
        self.assertGreater(centres[1], 800)

    def test_one_or_two_stray_detections_are_dropped(self):
        self.assertEqual(track([box(3, 500, 500), box(9, 20, 20)], frames=20), [])

    def test_jitter_is_smoothed(self):
        """A box that twitches by 40 px between frames must not make the cover twitch as much."""
        boxes = [box(i, 100 + (40 if i % 2 else 0), 100) for i in range(12)]
        t = track(boxes, frames=12)[0]
        xs = [t.boxes[i].x for i in range(2, 10)]
        jumps = [abs(b - a) for a, b in zip(xs, xs[1:])]
        self.assertLess(max(jumps), 25)



class Mask(unittest.TestCase):
    def test_oval_mask_is_opaque_in_the_middle_and_clear_at_the_corners(self):
        """A talking head is a rectangle; pasted as one it reads as a sticker, so it gets an oval."""
        from vidforge.video.heads import _oval_mask
        m = _oval_mask((120, 120))
        self.assertGreater(m.getpixel((60, 60)), 250)
        self.assertLess(m.getpixel((2, 2)), 5)
        self.assertLess(m.getpixel((117, 117)), 5)


class Face(unittest.TestCase):
    def test_talk_rejects_an_unknown_engine_and_missing_files(self):
        from vidforge.video import VideoToolError, face
        with self.assertRaises(VideoToolError):
            face.talk(__file__, __file__, "out.mp4", provider="nope")
        with self.assertRaises(VideoToolError):
            face.talk("no-such-photo.png", __file__, "out.mp4")

    def test_cmd_engine_explains_how_to_set_it_up_when_unconfigured(self):
        from unittest import mock
        from vidforge.video import VideoToolError, face
        with mock.patch.dict("os.environ", {face.CMD_ENV: ""}):
            self.assertFalse(face.available()["cmd"])
            with self.assertRaises(VideoToolError) as cm:
                face._cmd(Path(__file__), Path(__file__), Path("out.mp4"), log=lambda *_: None)
        self.assertIn(face.CMD_ENV, str(cm.exception))

if __name__ == "__main__":
    unittest.main()
