#!/usr/bin/env python3
"""Turn one local video into timestamped contact sheets and a transcript.

Writes <video parent>/_video/<recording name>/. Whisper runs on this machine
through whisper.cpp. The video and its audio are not sent anywhere.

Settings come from config.json next to this skill, then from command-line
flags. A flag wins over the file.
"""

import argparse
import atexit
import json
import os
import re
import signal
import subprocess
import sys
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# Image.Resampling arrived in Pillow 9.1. Older Pillow keeps the names on Image.
LANCZOS = getattr(Image, "Resampling", Image).LANCZOS
SKILL_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = SKILL_ROOT / "config.json"
MODEL_URL_BASE = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/"
MODEL_FILES = {
    "tiny": "ggml-tiny.bin",
    "tiny.en": "ggml-tiny.en.bin",
    "base": "ggml-base.bin",
    "base.en": "ggml-base.en.bin",
    "small": "ggml-small.bin",
    "small.en": "ggml-small.en.bin",
    "medium": "ggml-medium.bin",
    "medium.en": "ggml-medium.en.bin",
    "large": "ggml-large-v3.bin",
    "large-v3": "ggml-large-v3.bin",
}
MIN_MODEL_BYTES = {
    "tiny": 70_000_000,
    "base": 140_000_000,
    "small": 450_000_000,
    "medium": 1_400_000_000,
    "large": 2_800_000_000,
}
FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/Library/Fonts/Arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "C:/Windows/Fonts/arial.ttf",
]
DEFAULTS = {
    "interval_sec": 5,
    "scene_threshold": 0.2,
    "min_scene_gap_sec": 1,
    "scene_detection": True,
    "frame_width": 1280,
    "sheet_cols": 4,
    "sheet_rows": 3,
    "cell_width": 480,
    "cell_height": 270,
    "label_height": 36,
    "jpeg_quality": 85,
    "ffmpeg_q": 3,
    "model": "medium",
    "language": "auto",
    "threads": 0,
    "keep_audio": False,
    "font": "",
    "model_dir": "",
    "initial_prompt": "",
    "max_frames": 0,
    "extract_frames": True,
}
SETTING_KEYS = (
    "interval_sec",
    "scene_threshold",
    "min_scene_gap_sec",
    "scene_detection",
    "frame_width",
    "sheet_cols",
    "sheet_rows",
    "cell_width",
    "cell_height",
    "model",
    "language",
    "keep_audio",
    "initial_prompt",
    "max_frames",
    "extract_frames",
)
PTS_RE = re.compile(r"pts_time:([0-9]+(?:\.[0-9]+)?)")
# A lock with no PID yet is normal for a moment after it is created.
EMPTY_LOCK_GRACE_SEC = 60
TOOL_PATHS = {}


def log(message):
    print(message, file=sys.stderr, flush=True)


def cache_dir():
    base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "analyze-video"


def load_tool_paths():
    """Use the programs preflight checked, not whatever is first on PATH now."""
    try:
        data = json.loads((cache_dir() / "preflight.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    for name, path in (data.get("tools") or {}).items():
        if path and os.access(path, os.X_OK):
            TOOL_PATHS[name] = path


def tool(name):
    return TOOL_PATHS.get(name, name)


CHILDREN = []


def stop_children():
    for proc in list(CHILDREN):
        if proc.poll() is not None:
            continue
        proc.kill()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            pass


def handle_stop(signum, _frame):
    stop_children()
    raise SystemExit(128 + signum)


def install_stop_handlers():
    signal.signal(signal.SIGINT, handle_stop)
    signal.signal(signal.SIGTERM, handle_stop)
    atexit.register(stop_children)


def run(cmd, cwd=None):
    proc = subprocess.Popen(
        cmd,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    CHILDREN.append(proc)
    try:
        stdout, stderr = proc.communicate()
    finally:
        if proc in CHILDREN:
            CHILDREN.remove(proc)
    if proc.returncode != 0:
        tail = "\n".join((stderr or "").splitlines()[-40:])
        program = Path(str(cmd[0])).name
        raise RuntimeError(f"{program} failed\n{tail}".rstrip())
    return subprocess.CompletedProcess(cmd, proc.returncode, stdout, stderr)


def whisper_threads(configured):
    if configured > 0:
        return configured
    total = os.cpu_count() or 2
    return max(1, total // 2)


def fingerprint(path):
    stat = path.stat()
    return {
        "source": str(path.resolve()),
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
    }


def fmt_time(seconds):
    seconds = max(0.0, float(seconds))
    whole = int(seconds)
    hours, rem = divmod(whole, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def as_bool(value, key):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ("true", "yes", "1"):
            return True
        if lowered in ("false", "no", "0"):
            return False
    raise RuntimeError(f"{key} must be true or false")


def as_number(value, key, kind):
    try:
        return kind(value)
    except (TypeError, ValueError):
        raise RuntimeError(f"{key} must be a number")


def load_config(path):
    cfg = dict(DEFAULTS)
    if path is None:
        return cfg
    if not path.is_file():
        raise RuntimeError(f"config not found: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"config is not valid JSON: {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise RuntimeError(f"config must be a JSON object: {path}")
    unknown = sorted(set(data) - set(DEFAULTS))
    if unknown:
        raise RuntimeError(
            "unknown config keys: " + ", ".join(unknown)
        )
    cfg.update(data)
    return cfg


def apply_cli(cfg, args):
    mapping = {
        "interval": ("interval_sec", float),
        "scene_threshold": ("scene_threshold", float),
        "min_scene_gap": ("min_scene_gap_sec", float),
        "language": ("language", str),
        "model": ("model", str),
        "sheet_cols": ("sheet_cols", int),
        "sheet_rows": ("sheet_rows", int),
        "frame_width": ("frame_width", int),
    }
    for arg_name, (key, kind) in mapping.items():
        value = getattr(args, arg_name)
        if value is not None:
            cfg[key] = kind(value)
    if args.scene_detection is not None:
        cfg["scene_detection"] = args.scene_detection
    if args.keep_audio is not None:
        cfg["keep_audio"] = args.keep_audio
    if args.prompt is not None:
        cfg["initial_prompt"] = args.prompt
    if args.max_frames is not None:
        cfg["max_frames"] = args.max_frames
    if args.skip_frames:
        cfg["extract_frames"] = False
    return cfg


def normalize(cfg):
    cfg["interval_sec"] = as_number(cfg["interval_sec"], "interval_sec", float)
    cfg["scene_threshold"] = as_number(cfg["scene_threshold"], "scene_threshold", float)
    cfg["min_scene_gap_sec"] = as_number(
        cfg["min_scene_gap_sec"], "min_scene_gap_sec", float
    )
    cfg["scene_detection"] = as_bool(cfg["scene_detection"], "scene_detection")
    cfg["keep_audio"] = as_bool(cfg["keep_audio"], "keep_audio")
    for key, kind in (
        ("frame_width", int),
        ("sheet_cols", int),
        ("sheet_rows", int),
        ("cell_width", int),
        ("cell_height", int),
        ("label_height", int),
        ("jpeg_quality", int),
        ("ffmpeg_q", int),
        ("threads", int),
    ):
        cfg[key] = as_number(cfg[key], key, kind)
    cfg["model"] = str(cfg["model"]).strip()
    cfg["language"] = str(cfg["language"]).strip().lower() or "auto"
    cfg["font"] = str(cfg["font"]).strip()
    cfg["model_dir"] = str(cfg["model_dir"]).strip()
    cfg["initial_prompt"] = str(cfg["initial_prompt"]).strip()
    cfg["max_frames"] = as_number(cfg["max_frames"], "max_frames", int)
    cfg["extract_frames"] = as_bool(cfg["extract_frames"], "extract_frames")
    if cfg["interval_sec"] <= 0:
        raise RuntimeError("interval_sec must be greater than 0")
    if not 0 <= cfg["scene_threshold"] <= 1:
        raise RuntimeError("scene_threshold must be between 0 and 1")
    if cfg["min_scene_gap_sec"] < 0:
        raise RuntimeError("min_scene_gap_sec must be 0 or greater")
    if cfg["frame_width"] < 160:
        raise RuntimeError("frame_width must be at least 160")
    cfg["frame_width"] = cfg["frame_width"] - (cfg["frame_width"] % 2)
    for key in ("sheet_cols", "sheet_rows", "cell_width", "cell_height"):
        if cfg[key] < 1:
            raise RuntimeError(f"{key} must be at least 1")
    if not 1 <= cfg["jpeg_quality"] <= 95:
        raise RuntimeError("jpeg_quality must be between 1 and 95")
    if cfg["threads"] < 0:
        raise RuntimeError("threads must be 0 or greater")
    if cfg["max_frames"] < 0:
        raise RuntimeError("max_frames must be 0 or greater")
    if cfg["language"] != "auto" and not re.fullmatch(r"[a-z]{2,3}", cfg["language"]):
        raise RuntimeError("language must be 'auto' or a language code such as en")
    return cfg


def settings_snapshot(cfg):
    return {key: cfg[key] for key in SETTING_KEYS}


def model_family(name):
    base = name[:-3] if name.endswith(".en") else name
    if base.startswith("large"):
        return "large"
    return base


def english_only(model):
    text = str(model).lower()
    return text.endswith(".en") or ".en.bin" in text


def resolve_model(cfg):
    name = cfg["model"]
    path = Path(name).expanduser()
    looks_like_file = path.suffix == ".bin" and (
        path.is_absolute() or "/" in name or path.exists()
    )
    if looks_like_file:
        if cfg["language"] == "auto" and english_only(path.name):
            raise RuntimeError(
                f"{path.name} is English-only and cannot auto-detect language. "
                "Set language to en, or set model to medium."
            )
        return path
    if name not in MODEL_FILES:
        known = ", ".join(sorted(MODEL_FILES))
        raise RuntimeError(f"unknown model '{name}'. Use one of: {known}")
    if cfg["language"] == "auto" and english_only(name):
        raise RuntimeError(
            f"model '{name}' is English-only and cannot auto-detect language. "
            "Set language to en, or set model to medium."
        )
    directory = (
        Path(cfg["model_dir"]).expanduser()
        if cfg["model_dir"]
        else Path.home() / ".cache" / "whisper"
    )
    return directory / MODEL_FILES[name]


def min_model_bytes(path):
    stem = path.name
    if stem.startswith("ggml-"):
        stem = stem[len("ggml-") :]
    if stem.endswith(".bin"):
        stem = stem[: -len(".bin")]
    return MIN_MODEL_BYTES.get(model_family(stem), 1_000_000)


def ensure_model(path):
    minimum = min_model_bytes(path)
    if path.is_file() and path.stat().st_size >= minimum:
        return
    if path.is_file():
        raise RuntimeError(
            f"Whisper model looks incomplete: {path} ({path.stat().st_size} bytes)"
        )
    filename = path.name
    if filename not in MODEL_FILES.values():
        raise RuntimeError(f"Whisper model not found: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(".bin.partial")
    log(f"downloading Whisper model to {path}")
    run(
        [
            tool("curl"),
            "-L",
            "--fail",
            "--continue-at",
            "-",
            "-o",
            str(partial),
            MODEL_URL_BASE + filename,
        ]
    )
    partial.replace(path)


def resolve_font(cfg):
    if cfg["font"]:
        path = Path(cfg["font"]).expanduser()
        if not path.is_file():
            raise RuntimeError(f"font not found: {path}")
        return str(path)
    for candidate in FONT_CANDIDATES:
        if Path(candidate).is_file():
            return candidate
    return ""


def load_font(path, size):
    if path:
        return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def select_filter(cfg):
    # Commas inside select options are escaped so ffmpeg does not split the filter.
    # Timestamps are drawn later with Pillow. Some ffmpeg builds have no drawtext.
    interval = cfg["interval_sec"]
    parts = [
        "isnan(prev_selected_t)",
        f"gte(t-prev_selected_t\\,{interval})",
    ]
    if cfg["scene_detection"]:
        scene = cfg["scene_threshold"]
        gap = cfg["min_scene_gap_sec"]
        parts.append(f"gt(scene\\,{scene})*gte(t-prev_selected_t\\,{gap})")
    expression = "+".join(parts)
    return f"select='{expression}',scale={cfg['frame_width']}:-2,showinfo"


def stamp_frame(path, seconds, font_path, quality):
    font = load_font(font_path, 28)
    with Image.open(path) as image:
        frame = image.convert("RGB")
        draw = ImageDraw.Draw(frame)
        label = fmt_time(seconds)
        left, top, right, bottom = draw.textbbox((0, 0), label, font=font)
        pad = 8
        box = [12, 12, 12 + (right - left) + pad * 2, 12 + (bottom - top) + pad * 2]
        draw.rectangle(box, fill=(0, 0, 0))
        draw.text((box[0] + pad, box[1] + pad), label, fill="white", font=font)
        frame.save(path, quality=quality)


def extract_frames(video, frames_dir, cfg, font_path):
    frames_dir.mkdir(parents=True, exist_ok=True)
    for old in frames_dir.glob("f_*.jpg"):
        old.unlink()
    if cfg["scene_detection"]:
        log(
            f"selecting scene changes and {cfg['interval_sec']:g}-second frames"
        )
    else:
        log(f"selecting {cfg['interval_sec']:g}-second frames")

    def select(sync_option):
        return run(
            [
                tool("ffmpeg"),
                "-hide_banner",
                "-y",
                "-i",
                str(video),
                "-vf",
                select_filter(cfg),
                sync_option,
                "vfr",
                "-q:v",
                str(cfg["ffmpeg_q"]),
                "-start_number",
                "1",
                str(frames_dir / "f_%04d.jpg"),
            ]
        )

    try:
        result = select("-fps_mode")
    except RuntimeError as exc:
        # ffmpeg before 5.1 has no -fps_mode. -vsync is the older name.
        if "fps_mode" not in str(exc):
            raise
        result = select("-vsync")
    times = []
    for line in result.stderr.splitlines():
        if "showinfo" not in line:
            continue
        match = PTS_RE.search(line)
        if match:
            times.append(float(match.group(1)))
    frames = sorted(frames_dir.glob("f_*.jpg"))
    if not frames:
        raise RuntimeError("ffmpeg produced no frames")
    if len(times) != len(frames):
        raise RuntimeError(
            f"frame timestamps ({len(times)}) do not match files ({len(frames)})"
        )
    for path, stamp in zip(frames, times):
        stamp_frame(path, stamp, font_path, cfg["jpeg_quality"])
    return [
        {"file": f"frames/{path.name}", "t": stamp}
        for path, stamp in zip(frames, times)
    ]


def build_sheets(out_dir, frames, cfg, font_path):
    sheets_dir = out_dir / "sheets"
    sheets_dir.mkdir(parents=True, exist_ok=True)
    for old in sheets_dir.glob("sheet_*.jpg"):
        old.unlink()
    font = load_font(font_path, 20)
    cols = cfg["sheet_cols"]
    rows = cfg["sheet_rows"]
    cell_w = cfg["cell_width"]
    cell_h = cfg["cell_height"]
    label_h = cfg["label_height"]
    per_sheet = cols * rows
    sheets = []
    for index in range(0, len(frames), per_sheet):
        chunk = frames[index : index + per_sheet]
        sheet_no = index // per_sheet + 1
        name = f"sheet_{sheet_no:03d}.jpg"
        canvas = Image.new("RGB", (cols * cell_w, rows * (cell_h + label_h)), "white")
        draw = ImageDraw.Draw(canvas)
        for cell, frame in enumerate(chunk):
            col = cell % cols
            row = cell // cols
            x = col * cell_w
            y = row * (cell_h + label_h)
            with Image.open(out_dir / frame["file"]) as image:
                fitted = image.convert("RGB")
                fitted.thumbnail((cell_w, cell_h), LANCZOS)
                pad_x = x + (cell_w - fitted.width) // 2
                pad_y = y + (cell_h - fitted.height) // 2
                canvas.paste(fitted, (pad_x, pad_y))
            label = fmt_time(frame["t"])
            draw.rectangle(
                [x, y + cell_h, x + cell_w, y + cell_h + label_h],
                fill=(20, 20, 20),
            )
            draw.text((x + 8, y + cell_h + 6), label, fill="white", font=font)
        canvas.save(sheets_dir / name, quality=cfg["jpeg_quality"])
        sheets.append(
            {
                "file": f"sheets/{name}",
                "start": fmt_time(chunk[0]["t"]),
                "end": fmt_time(chunk[-1]["t"]),
                "frames": [
                    {"file": frame["file"], "t": fmt_time(frame["t"])}
                    for frame in chunk
                ],
            }
        )
    return sheets


def probe(video, *args):
    result = run(
        [tool("ffprobe"), "-v", "error", *args, "-of", "csv=p=0", str(video)]
    )
    return result.stdout


def has_audio(video):
    return bool(probe(video, "-select_streams", "a", "-show_entries", "stream=index").strip())


def has_video(video):
    # V (capital) skips cover art, which audio files such as .m4a carry as a picture stream.
    return bool(probe(video, "-select_streams", "V", "-show_entries", "stream=index").strip())


def positive_floats(text):
    values = []
    for field in text.replace(",", "\n").split():
        try:
            value = float(field)
        except ValueError:
            continue
        if value > 0:
            values.append(value)
    return values


def duration_seconds(video):
    # Recordings written as a stream, such as a browser's MediaRecorder .webm,
    # often store no duration at all. ffprobe prints N/A for those.
    for entry in ("format=duration", "stream=duration"):
        values = positive_floats(probe(video, "-show_entries", entry))
        if values:
            return max(values)
    log("the file stores no duration; reading packet times instead")
    end = 0.0
    for line in probe(video, "-show_entries", "packet=pts_time,duration_time").splitlines():
        fields = line.split(",")
        try:
            pts = float(fields[0])
        except (IndexError, ValueError):
            continue
        try:
            pts += float(fields[1])
        except (IndexError, ValueError):
            pass
        end = max(end, pts)
    if end > 0:
        return end
    raise RuntimeError(f"could not read the duration of {video.name}")


def parse_transcript(payload):
    segments = payload.get("transcription") or []
    rows = []
    for segment in segments:
        text = (segment.get("text") or "").strip()
        if not text:
            continue
        stamps = segment.get("timestamps") or {}
        start = str(stamps.get("from") or "").replace(",", ".")
        end = str(stamps.get("to") or "").replace(",", ".")
        rows.append((start, end, text))
    detected = ""
    result = payload.get("result") or {}
    if isinstance(result, dict):
        detected = str(result.get("language") or "").strip()
    return rows, detected


def transcribe(video, out_dir, cfg):
    transcript_md = out_dir / "transcript.md"
    if not has_audio(video):
        transcript_md.write_text(
            "This recording has no audio track.\n", encoding="utf-8"
        )
        return "no-audio", ""
    model_path = resolve_model(cfg)
    wav = out_dir / "audio.wav"
    try:
        log("extracting audio")
        run(
            [
                tool("ffmpeg"),
                "-hide_banner",
                "-y",
                "-i",
                str(video),
                "-vn",
                "-ac",
                "1",
                "-ar",
                "16000",
                "-c:a",
                "pcm_s16le",
                str(wav),
            ]
        )
        ensure_model(model_path)
        log(f"transcribing with local Whisper ({model_path.name}, {cfg['language']})")
        threads = whisper_threads(cfg["threads"])
        cmd = [
            tool("whisper-cli"),
            "-m",
            str(model_path),
            "-f",
            str(wav),
            "-l",
            cfg["language"],
            "-oj",
            "-of",
            str(out_dir / "transcript"),
            "-np",
            "-t",
            str(threads),
        ]
        if cfg["initial_prompt"]:
            cmd.extend(["--prompt", cfg["initial_prompt"]])
        run(cmd)
    finally:
        if not cfg["keep_audio"]:
            wav.unlink(missing_ok=True)
    raw_path = out_dir / "transcript.json"
    payload = json.loads(raw_path.read_text(encoding="utf-8"))
    rows, detected = parse_transcript(payload)
    if cfg["language"] == "auto" and detected:
        language_line = f"Language: {detected} (auto-detected)."
    elif cfg["language"] == "auto":
        language_line = "Language: auto."
    else:
        language_line = f"Language: {cfg['language']}."
    lines = [
        "# Transcript",
        "",
        f"Local whisper.cpp, model {model_path.name}.",
        language_line,
        "",
    ]
    if not rows:
        lines.append("Whisper returned no speech.")
    else:
        for start, end, text in rows:
            lines.append(f"[{start} --> {end}] {text}")
    lines.append("")
    transcript_md.write_text("\n".join(lines), encoding="utf-8")
    kind = model_path.name
    if detected:
        kind = f"{kind}:{detected}"
    return kind, detected


def apply_frame_cap(cfg, duration):
    """Widen the interval and scene gap so the frame count can stay under max_frames.

    The returned config is a copy. max_frames 0 leaves the requested settings alone.
    """
    run = dict(cfg)
    cap = run["max_frames"]
    if cap <= 0 or duration <= 0:
        return run
    step = run["interval_sec"]
    if run["scene_detection"]:
        step = min(step, run["min_scene_gap_sec"])
    if step <= 0 or (1 + duration / step) <= cap:
        return run
    widened = duration / max(cap - 1, 1)
    notes = []
    if run["interval_sec"] < widened:
        notes.append(f"interval {run['interval_sec']:g}s -> {widened:.1f}s")
        run["interval_sec"] = widened
    if run["scene_detection"] and run["min_scene_gap_sec"] < widened:
        notes.append(f"scene gap {cfg['min_scene_gap_sec']:g}s -> {widened:.1f}s")
        run["min_scene_gap_sec"] = widened
    if notes:
        log(f"max_frames {cap}: " + ", ".join(notes))
    return run


def write_index(
    out_dir, video, duration, frames, sheets, transcript_kind, cfg, requested, skip_reason
):
    scene = "on" if cfg["scene_detection"] else "off"
    interval = f"Frame interval: {cfg['interval_sec']:g}s"
    if cfg["interval_sec"] != requested["interval_sec"]:
        interval += (
            f" (widened from {requested['interval_sec']:g}s "
            f"for max_frames {requested['max_frames']})"
        )
    gap = (
        f"Scene detection: {scene} (threshold {cfg['scene_threshold']:g}, "
        f"minimum gap {cfg['min_scene_gap_sec']:g}s)"
    )
    if (
        cfg["scene_detection"]
        and cfg["min_scene_gap_sec"] != requested["min_scene_gap_sec"]
    ):
        gap += f" (widened from {requested['min_scene_gap_sec']:g}s)"
    if not skip_reason:
        frame_line = f"Frames: {len(frames)}"
        sheet_line = f"Contact sheets: {len(sheets)}"
        read_line = (
            "Read transcript.md, then every contact sheet. Open an individual\n"
            "frame only when a cell is unreadable."
        )
    else:
        frame_line = f"Frames: skipped ({skip_reason})"
        sheet_line = "Contact sheets: none"
        read_line = "Read transcript.md. Frames were not extracted."
    lines = [
        f"# {video.name}",
        "",
        f"Duration: {fmt_time(duration)}",
        interval,
        gap,
        frame_line,
        sheet_line,
        f"Transcript: transcript.md ({transcript_kind})",
        "",
        read_line,
        "",
        "## Sheets",
        "",
    ]
    for sheet in sheets:
        lines.append(f"- {sheet['file']}  {sheet['start']} – {sheet['end']}")
    lines.append("")
    (out_dir / "index.md").write_text("\n".join(lines), encoding="utf-8")


def already_done(manifest_path, source_fp, settings):
    if not manifest_path.is_file():
        return False
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    return (
        manifest.get("complete") is True
        and manifest.get("source") == source_fp
        and manifest.get("settings") == settings
    )


def loose_name(name):
    # macOS puts U+202F (narrow no-break space) before AM/PM in screen-recording
    # names. An agent that retypes the path types a plain space instead.
    name = unicodedata.normalize("NFC", name)
    return " ".join(name.split())


def find_video(path):
    path = path.expanduser()
    if path.is_file():
        return path.resolve()
    parent = path.parent
    if parent.is_dir():
        wanted = loose_name(path.name)
        matches = [
            entry
            for entry in parent.iterdir()
            if entry.is_file() and loose_name(entry.name) == wanted
        ]
        if len(matches) == 1:
            log(f"using {matches[0].name!r}; the name differs only in spacing")
            return matches[0].resolve()
    raise RuntimeError(f"video not found: {path}")


def pid_alive(pid):
    if pid <= 0:
        return False
    if os.name == "nt":
        # On Windows, signal 0 is CTRL_C_EVENT, so os.kill(pid, 0) would interrupt
        # the other run instead of checking it. Ask the kernel instead.
        import ctypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return ctypes.get_last_error() == 5  # access denied: it exists
        code = ctypes.c_ulong()
        ok = kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
        kernel32.CloseHandle(handle)
        return bool(ok) and code.value == 259  # STILL_ACTIVE
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def lock_is_stale(lock_path):
    try:
        text = lock_path.read_text(encoding="utf-8").strip()
        age = time.time() - lock_path.stat().st_mtime
    except OSError:
        return False
    if not text:
        return age > EMPTY_LOCK_GRACE_SEC
    if not text.isdigit():
        return True
    return not pid_alive(int(text))


def acquire_lock(lock_path, video):
    """A run that was killed (agent timeout, closed terminal) leaves its lock behind."""
    for _attempt in range(2):
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            if lock_is_stale(lock_path):
                log("removing the lock left by a run that stopped")
                lock_path.unlink(missing_ok=True)
                continue
            raise RuntimeError(
                f"processing already running for {video.name}. "
                f"If no run is active, delete {lock_path}"
            )
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        return
    raise RuntimeError(f"could not take the lock {lock_path}")


def process(video, cfg):
    video = find_video(video)
    if video.parent.name == "_video":
        raise RuntimeError(f"refusing to process a file already under _video: {video}")
    out_dir = video.parent / "_video" / video.stem
    out_dir.mkdir(parents=True, exist_ok=True)
    source_fp = fingerprint(video)
    settings = settings_snapshot(cfg)
    manifest_path = out_dir / "manifest.json"
    if already_done(manifest_path, source_fp, settings):
        print(f"already processed: {out_dir / 'index.md'}")
        return
    lock_path = out_dir / ".lock"
    acquire_lock(lock_path, video)
    try:
        resolve_model(cfg)
        duration = duration_seconds(video)
        skip_reason = ""
        if not cfg["extract_frames"]:
            skip_reason = "not requested"
        elif not has_video(video):
            if not has_audio(video):
                raise RuntimeError(f"{video.name} has no video or audio track")
            skip_reason = "no video track"
        if skip_reason:
            run_cfg = cfg
            log(f"skipping frames ({skip_reason})")
            frames = []
            sheets = []
        else:
            run_cfg = apply_frame_cap(cfg, duration)
            font_path = resolve_font(run_cfg)
            frames = extract_frames(video, out_dir / "frames", run_cfg, font_path)
            sheets = build_sheets(out_dir, frames, run_cfg, font_path)
        transcript_kind, _detected = transcribe(video, out_dir, cfg)
        write_index(
            out_dir,
            video,
            duration,
            frames,
            sheets,
            transcript_kind,
            run_cfg,
            cfg,
            skip_reason,
        )
        manifest = {
            "complete": True,
            "source": source_fp,
            "settings": settings,
            "duration_sec": duration,
            "frame_count": len(frames),
            "sheet_count": len(sheets),
            "transcript": transcript_kind,
            "model": str(resolve_model(cfg)) if transcript_kind != "no-audio" else "",
            "processed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "frames": [
                {"file": frame["file"], "t": fmt_time(frame["t"])} for frame in frames
            ],
            "sheets": sheets,
        }
        manifest_path.write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
        print(f"processed: {out_dir / 'index.md'}")
    finally:
        lock_path.unlink(missing_ok=True)


def build_parser():
    parser = argparse.ArgumentParser(
        description="Create contact sheets and a local transcript for one video."
    )
    parser.add_argument("video", type=Path, help="path to the video file")
    parser.add_argument(
        "--config",
        type=Path,
        help="JSON config file (default: config.json in the skill folder)",
    )
    parser.add_argument("--interval", type=float, help="seconds between frames")
    parser.add_argument("--scene-threshold", type=float)
    parser.add_argument("--min-scene-gap", type=float)
    parser.add_argument(
        "--scene",
        dest="scene_detection",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="turn scene-change frames on or off",
    )
    parser.add_argument("--language", help="spoken language, or auto")
    parser.add_argument(
        "--model",
        help="whisper.cpp model name (medium, medium.en, small, ...) or a .bin path",
    )
    parser.add_argument("--sheet-cols", type=int)
    parser.add_argument("--sheet-rows", type=int)
    parser.add_argument("--frame-width", type=int)
    parser.add_argument(
        "--prompt",
        help="Whisper initial prompt for names and terms already known for this video",
    )
    parser.add_argument(
        "--max-frames",
        type=int,
        help="cap frames by widening the interval and scene gap; 0 means no cap",
    )
    parser.add_argument(
        "--skip-frames",
        action="store_true",
        help="write the transcript only and do not extract frames",
    )
    parser.add_argument(
        "--keep-audio",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="keep or delete the extracted WAV",
    )
    return parser


def resolve_config_path(arg):
    if arg is not None:
        return arg
    if DEFAULT_CONFIG_PATH.is_file():
        return DEFAULT_CONFIG_PATH
    return None


def preflight_command():
    scripts = SKILL_ROOT / "scripts"
    if os.name == "nt":
        return [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(scripts / "preflight.ps1"),
        ]
    return [str(scripts / "preflight")]


def main(argv=None):
    # A console that is not UTF-8 (Windows, piped output) cannot print every file
    # name. Escape what it cannot show instead of failing after the work is done.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="backslashreplace")
        except AttributeError:
            pass
    install_stop_handlers()
    args = build_parser().parse_args(argv)
    # The entry scripts run preflight before starting Python and say so.
    if os.environ.get("ANALYZE_VIDEO_PREFLIGHT") != "done":
        check = subprocess.run(preflight_command(), stderr=subprocess.PIPE, text=True)
        if check.returncode != 0:
            sys.stderr.write(check.stderr)
            return check.returncode
    load_tool_paths()
    try:
        cfg = normalize(apply_cli(load_config(resolve_config_path(args.config)), args))
        process(args.video, cfg)
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
