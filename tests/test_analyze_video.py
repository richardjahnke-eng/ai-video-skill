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


ZOOM_VTT = """WEBVTT

1
00:00:01.000 --> 00:00:04.500
Jane Doe: Welcome, everyone.

2
00:00:05.000 --> 00:00:07.250
Unknown Speaker: Thanks &amp; hi.
"""

TEAMS_VTT = """\ufeffWEBVTT

NOTE produced by Teams

0a1b/12-0
00:01:02.345 --> 00:01:05.000
<v Sam Lee>Can everyone see my screen?</v>

00:06.000 --> 00:07.000
No speaker tag here.
"""


class TranscriptFileTests(unittest.TestCase):
    def test_zoom_vtt(self):
        self.assertEqual(av.parse_vtt(ZOOM_VTT), [
            ("00:00:01.000", "00:00:04.500", "Jane Doe: Welcome, everyone."),
            ("00:00:05.000", "00:00:07.250", "Unknown Speaker: Thanks & hi."),
        ])

    def test_teams_vtt_voice_tags_and_short_times(self):
        self.assertEqual(av.parse_vtt(TEAMS_VTT), [
            ("00:01:02.345", "00:01:05.000", "Sam Lee: Can everyone see my screen?"),
            ("00:00:06.000", "00:00:07.000", "No speaker tag here."),
        ])

    def test_sidecar_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            plain = folder / "meeting.mp4"
            plain.write_bytes(b"x")
            self.assertIsNone(av.find_sidecar_transcript(plain))
            (folder / "meeting.vtt").write_text(ZOOM_VTT, encoding="utf-8")
            self.assertEqual(av.find_sidecar_transcript(plain).name, "meeting.vtt")
            zoom = folder / "GMT20261022-150000_Recording_gallery_1280x720.mp4"
            zoom.write_bytes(b"x")
            (folder / "GMT20261022-150000_Recording.transcript.vtt").write_text(ZOOM_VTT, encoding="utf-8")
            self.assertEqual(av.find_sidecar_transcript(zoom).name,
                             "GMT20261022-150000_Recording.transcript.vtt")


class ConfigTests(unittest.TestCase):
    def test_turbo_model_size_floor(self):
        self.assertEqual(av.min_model_bytes(Path("ggml-large-v3-turbo.bin")), av.MIN_MODEL_BYTES["turbo"])
        self.assertEqual(av.min_model_bytes(Path("ggml-large-v3.bin")), av.MIN_MODEL_BYTES["large"])

    def test_config_json_matches_defaults(self):
        data = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
        self.assertEqual(data, av.DEFAULTS)

    def test_local_config_overrides_and_is_checked(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "config.json"
            local = Path(tmp) / "config.local.json"
            base.write_text(json.dumps({"interval_sec": 30}), encoding="utf-8")
            local.write_text(json.dumps({"interval_sec": 10}), encoding="utf-8")
            saved = av.DEFAULT_CONFIG_PATH, av.LOCAL_CONFIG_PATH
            av.DEFAULT_CONFIG_PATH, av.LOCAL_CONFIG_PATH = base, local
            try:
                self.assertEqual(av.load_config(base)["interval_sec"], 10)
                local.write_text(json.dumps({"intervl_sec": 10}), encoding="utf-8")
                with self.assertRaises(RuntimeError):
                    av.load_config(base)
            finally:
                av.DEFAULT_CONFIG_PATH, av.LOCAL_CONFIG_PATH = saved

    def test_output_goes_to_current_directory_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            cwd = os.getcwd()
            os.chdir(tmp)
            try:
                cfg = av.normalize(dict(av.DEFAULTS))
                out = av.output_dir(Path("/meetings/Weekly sync/zoom_0.mp4"), cfg)
            finally:
                os.chdir(cwd)
            self.assertEqual(out.parent, Path(tmp).resolve() / "_video")
            self.assertEqual(out.name, "Weekly-sync--zoom_0-mp4")
            beside = av.output_dir(Path("/meetings/a/rec.mov"), dict(cfg, output_root="beside"))
            self.assertEqual(beside, Path("/meetings/a/_video/rec-mov"))


@unittest.skipUnless(shutil.which("git"), "git is not on PATH")
class GitTests(unittest.TestCase):
    def test_video_folder_is_excluded_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            video_root = repo / "_video"
            video_root.mkdir()
            av.keep_out_of_git(video_root)
            av.keep_out_of_git(video_root)
            exclude = (repo / ".git" / "info" / "exclude").read_text(encoding="utf-8")
            self.assertEqual(exclude.count("_video/"), 1)
            ignored = subprocess.run(["git", "-C", str(repo), "check-ignore", "-q", "_video"])
            self.assertEqual(ignored.returncode, 0)


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
        cfg.update(model="tiny", model_dir=str(self.model_dir), output_root=str(self.dir / "project"))
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

    def output_of(self, video, cfg=None):
        return av.output_dir(video.resolve(), cfg or self.config())

    def test_full_run_on_mp4(self):
        cfg = self.config(interval_sec=5)
        av.process(self.clip, cfg)
        out = self.output_of(self.clip, cfg)
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

    def test_zoom_cloud_vtt_is_used_instead_of_whisper(self):
        folder = self.dir / "zoom-cloud"
        folder.mkdir(exist_ok=True)
        video = folder / "GMT20261022-150000_Recording_1920x1080.mp4"
        shutil.copy(self.clip, video)
        (folder / "GMT20261022-150000_Recording.transcript.vtt").write_text(ZOOM_VTT, encoding="utf-8")
        cfg = self.config()
        av.process(video, cfg)
        out = self.output_of(video, cfg)
        transcript = (out / "transcript.md").read_text(encoding="utf-8")
        self.assertIn("[00:00:01.000 --> 00:00:04.500] Jane Doe: Welcome, everyone.", transcript)
        self.assertNotIn("Hello there.", transcript)
        index = (out / "index.md").read_text(encoding="utf-8")
        self.assertIn("vtt:GMT20261022-150000_Recording.transcript.vtt", index)
        av.process(video, self.config(sidecar_transcript=False))
        self.assertIn("Hello there.", (out / "transcript.md").read_text(encoding="utf-8"))

    def test_same_file_name_in_two_meeting_folders_gets_two_outputs(self):
        cfg = self.config()
        outs = []
        for meeting in ("2026-10-21 10.00.00 Standup", "2026-10-22 10.00.00 Standup"):
            folder = self.dir / meeting
            folder.mkdir(exist_ok=True)
            video = folder / "zoom_0.mp4"
            shutil.copy(self.clip, video)
            av.process(video, cfg)
            outs.append(self.output_of(video, cfg))
        self.assertNotEqual(outs[0], outs[1])
        self.assertEqual(outs[0].name, "2026-10-21-10.00.00-Standup--zoom_0-mp4")
        self.assertTrue(all((out / "index.md").is_file() for out in outs))

    def test_audio_only_run_skips_frames(self):
        av.process(self.m4a, self.config())
        index = (self.output_of(self.m4a) / "index.md").read_text(encoding="utf-8")
        self.assertIn("Frames: skipped (no video track)", index)
        self.assertIn("Read transcript.md.", index)


if __name__ == "__main__":
    unittest.main()
