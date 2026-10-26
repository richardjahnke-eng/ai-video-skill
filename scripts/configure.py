#!/usr/bin/env python3
"""Local settings page for the analyze-video skill.

Writes config.local.json next to config.json. Prints one localhost URL and
keeps serving until the process is stopped. A second start prints the URL
of the page that is already open.
"""

import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
import analyze_video as av  # noqa: E402

PAGE = Path(__file__).with_name("configure.html").read_text(encoding="utf-8")
URL_FILE = av.cache_dir() / "configure.url"
MODELS = [
    "large-v3-turbo",
    "large-v3",
    "large",
    "medium",
    "medium.en",
    "small",
    "small.en",
    "base",
    "base.en",
    "tiny",
    "tiny.en",
]
LANGUAGES = ["auto", "en", "es", "fr", "de", "it", "pt", "nl", "pl", "ru", "zh", "ja", "ko"]


def shipped_config():
    cfg = dict(av.DEFAULTS)
    cfg.update(av.read_config(av.DEFAULT_CONFIG_PATH))
    return av.normalize(cfg)


def effective_config():
    return av.normalize(av.load_config(av.DEFAULT_CONFIG_PATH))


def local_overrides(shipped, chosen):
    saved = {}
    for key in av.DEFAULTS:
        if chosen[key] != shipped[key]:
            saved[key] = chosen[key]
    return saved


def write_local(overrides):
    if not overrides:
        av.LOCAL_CONFIG_PATH.unlink(missing_ok=True)
        return
    text = json.dumps(overrides, indent=2) + "\n"
    av.LOCAL_CONFIG_PATH.write_text(text, encoding="utf-8")


def payload():
    shipped = shipped_config()
    values = effective_config()
    return {
        "values": values,
        "shipped": shipped,
        "models": MODELS,
        "languages": LANGUAGES,
        "path": str(av.LOCAL_CONFIG_PATH),
    }


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        return

    def send_json(self, status, body):
        raw = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            raw = PAGE.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(raw)
            return
        if path == "/api/config":
            self.send_json(200, payload())
            return
        self.send_error(404)

    def do_POST(self):
        if urlparse(self.path).path != "/api/config":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", "0"))
        try:
            incoming = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError):
            self.send_json(400, {"error": "The page sent invalid JSON."})
            return
        if not isinstance(incoming, dict):
            self.send_json(400, {"error": "Settings must be a JSON object."})
            return
        cfg = shipped_config()
        unknown = sorted(set(incoming) - set(av.DEFAULTS))
        if unknown:
            self.send_json(400, {"error": "Unknown settings: " + ", ".join(unknown)})
            return
        cfg.update(incoming)
        try:
            chosen = av.normalize(cfg)
            av.resolve_model(chosen)
        except Exception as exc:
            self.send_json(400, {"error": str(exc)})
            return
        write_local(local_overrides(shipped_config(), chosen))
        body = payload()
        body["saved"] = True
        self.send_json(200, body)

    def do_DELETE(self):
        if urlparse(self.path).path != "/api/config":
            self.send_error(404)
            return
        av.LOCAL_CONFIG_PATH.unlink(missing_ok=True)
        body = payload()
        body["saved"] = True
        self.send_json(200, body)


def existing_url():
    try:
        data = json.loads(URL_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    if av.pid_alive(int(data.get("pid") or 0)):
        return str(data.get("url") or "")
    return ""


def remember(url):
    URL_FILE.parent.mkdir(parents=True, exist_ok=True)
    URL_FILE.write_text(
        json.dumps({"pid": os.getpid(), "url": url}) + "\n",
        encoding="utf-8",
    )


def main():
    current = existing_url()
    if current:
        print(f"configure: {current}", flush=True)
        return 0
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    host, port = server.server_address
    url = f"http://{host}:{port}/"
    remember(url)
    print(f"configure: {url}", flush=True)
    try:
        server.serve_forever()
    finally:
        try:
            if existing_url() == url:
                URL_FILE.unlink(missing_ok=True)
        except OSError:
            pass
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
