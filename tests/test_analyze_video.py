"""Tests for scripts/analyze_video.py.

Run from the skill folder:  python3 -m unittest discover -s tests -v

The tests that make videos need ffmpeg and ffprobe on PATH and skip without them.
Whisper is replaced by a stand-in that writes whisper.cpp's JSON shape, so no model
is downloaded and no real transcription runs.
"""

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location("analyze_video", ROOT / "scripts" / "analyze_video.py")
av = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(av)

HAVE_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))
needs_ffmpeg = unittest.skipUnless(HAVE_FFMPEG, "ffmpeg and ffprobe are not on PATH")

FAKE_WHISPER = r'''
import json, sys
args = sys.argv[1:]
out = args[args.index("-of") + 1]
payload = {
    "result": {"language": "en"},
    "transcription": [
        {"timestamps": {"from": "00:00:00,000", "to": "00:00:02,500"}, "text": " Hello there."},
        {"timestamps": {"from": "00:00:02,500", "to": "00:00:04,000"}, "text": " Second line."},
    ],
}
with open(out + ".json", "w", encoding="utf-8") as handle:
    json.dump(payload, handle)
'''


def ffmpeg(*args):
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args], check=True)


def make_fake_whisper(folder):
    script = folder / "fake_whisper.py"
    script.write_text(FAKE_WHISPER, encoding="utf-8")
    if os.name == "nt":
        exe = folder / "whisper-cli.cmd"
        exe.write_text(f'@"{sys.executable}" "{script}" %*\r\n', encoding="utf-8")
    else:
        exe = folder / "whisper-cli"
        exe.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{script}" "$@"\n', encoding="utf-8")
        exe.chmod(0o755)
    return exe


class NameTests(unittest.TestCase):
    def test_narrow_no_break_space_matches_plain_space(self):
        with tempfile.TemporaryDirectory() as tmp:
            real = Path(tmp) / "Screen Recording 2026-10-22 at 10.15.32 AM.mov"
            real.write_bytes(b"x")
            typed = Path(tmp) / "Screen Recording 2026-10-22 at 10.15.32 AM.mov"
            self.assertEqual(av.find_video(typed), real.resolve())

    def test_missing_file_still_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(RuntimeError):
                av.find_video(Path(tmp) / "nope.mp4")


class LockTests(unittest.TestCase):
    def test_lock_of_a_dead_process_is_taken_over(self):
        with tempfile.TemporaryDirectory() as tmp:
            done = subprocess.run([sys.executable, "-c", "import os; print(os.getpid())"],
                                  capture_output=True, text=True, check=True)
            lock = Path(tmp) / ".lock"
            lock.write_text(done.stdout.strip(), encoding="utf-8")
            av.acquire_lock(lock, Path("clip.mp4"))
            self.assertEqual(lock.read_text(encoding="utf-8"), str(os.getpid()))

    def test_lock_of_a_live_process_is_respected(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock = Path(tmp) / ".lock"
            lock.write_text(str(os.getpid()), encoding="utf-8")
            with self.assertRaises(RuntimeError) as caught:
                av.acquire_lock(lock, Path("clip.mp4"))
            self.assertIn(str(lock), str(caught.exception))

    def test_fresh_empty_lock_is_respected_and_old_one_is_not(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock = Path(tmp) / ".lock"
            lock.write_text("", encoding="utf-8")
            self.assertFalse(av.lock_is_stale(lock))
            old = time.time() - av.EMPTY_LOCK_GRACE_SEC - 5
            os.utime(lock, (old, old))
            self.assertTrue(av.lock_is_stale(lock))


@needs_ffmpeg
class MediaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.dir = Path(cls.tmp.name)
        cls.clip = cls.dir / "clip.mp4"
        ffmpeg("-f", "lavfi", "-i", "testsrc2=size=640x360:rate=25:duration=12",
               "-f", "lavfi", "-i", "sine=frequency=440:duration=12",
               "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(cls.clip))
        # Written to a pipe, like a browser recording: the file stores no duration.
        cls.webm = cls.dir / "browser.webm"
        with open(cls.webm, "wb") as handle:
            subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(cls.clip),
                            "-c:v", "libvpx", "-deadline", "realtime", "-c:a", "libopus",
                            "-f", "webm", "pipe:1"], stdout=handle, check=True)
        cls.m4a = cls.dir / "audio_only.m4a"
        ffmpeg("-i", str(cls.clip), "-vn", "-c:a", "aac", str(cls.m4a))
        cls.fake = make_fake_whisper(cls.dir)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        av.TOOL_PATHS.clear()
        av.TOOL_PATHS["whisper-cli"] = str(self.fake)
        self.model_dir = Path(tempfile.mkdtemp(dir=self.dir))
        # A placeholder big enough to pass the size check, so nothing is downloaded.
        with open(self.model_dir / "ggml-tiny.bin", "wb") as handle:
            handle.truncate(av.MIN_MODEL_BYTES["tiny"])

    def config(self, **overrides):
        cfg = dict(av.DEFAULTS)
        cfg.update(model="tiny", model_dir=str(self.model_dir))
        cfg.update(overrides)
        return av.normalize(cfg)

    def test_duration_without_stored_duration(self):
        probed = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                 "-of", "csv=p=0", str(self.webm)], capture_output=True, text=True)
        self.assertEqual(probed.stdout.strip(), "N/A")
        self.assertAlmostEqual(av.duration_seconds(self.webm), 12.0, delta=0.5)

    def test_audio_only_file_has_no_video_track(self):
        self.assertFalse(av.has_video(self.m4a))
        self.assertTrue(av.has_video(self.clip))

    def output_of(self, video):
        return video.parent / "_video" / video.stem

    def test_full_run_on_mp4(self):
        av.process(self.clip, self.config())
        out = self.output_of(self.clip)
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        self.assertTrue(manifest["complete"])
        self.assertGreater(manifest["frame_count"], 1)
        self.assertTrue((out / "sheets" / "sheet_001.jpg").is_file())
        self.assertIn("Hello there.", (out / "transcript.md").read_text(encoding="utf-8"))
        self.assertFalse((out / ".lock").exists())

    def test_full_run_on_streamed_webm(self):
        av.process(self.webm, self.config())
        index = (self.output_of(self.webm) / "index.md").read_text(encoding="utf-8")
        self.assertIn("Duration: 00:00:1", index)

    def test_audio_only_run_skips_frames(self):
        av.process(self.m4a, self.config())
        index = (self.output_of(self.m4a) / "index.md").read_text(encoding="utf-8")
        self.assertIn("Frames: skipped (no video track)", index)
        self.assertIn("Read transcript.md.", index)


if __name__ == "__main__":
    unittest.main()
