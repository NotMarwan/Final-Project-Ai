from __future__ import annotations

import json
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


ROOT_DIR = Path(__file__).resolve().parent.parent
DIST_DIR = ROOT_DIR / ".runlogs" / "colab_bridge"
MANIFEST_PATH = DIST_DIR / "manifest.json"


def load_manifest() -> dict:
    with open(MANIFEST_PATH, "r", encoding="utf-8") as handle:
        return json.load(handle)


class ColabBridgeHandler(BaseHTTPRequestHandler):
    server_version = "ColabBridge/1.0"

    def _send_json(self, payload: dict, status: int = 200) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data)

    def _send_file(self, path: Path, head_only: bool = False) -> None:
        if not path.exists():
            self.send_error(HTTPStatus.NOT_FOUND, "File not found")
            return
        size = path.stat().st_size
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(size))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        if head_only:
            return
        with open(path, "rb") as handle:
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                self.wfile.write(chunk)

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:
        manifest = load_manifest()
        parsed = urlparse(self.path)

        if parsed.path == "/manifest":
            self._send_json(manifest)
            return

        if parsed.path.startswith("/download/"):
            name = parsed.path.split("/", 2)[-1]
            if name == manifest["bundle"]["filename"]:
                self._send_file(Path(manifest["bundle"]["path"]))
                return
            if name == manifest["dataset"]["filename"]:
                self._send_file(Path(manifest["dataset"]["path"]))
                return
            if name == manifest["weights"]["filename"]:
                self._send_file(Path(manifest["weights"]["path"]))
                return

        self.send_error(HTTPStatus.NOT_FOUND, "Unknown endpoint")

    def do_HEAD(self) -> None:
        manifest = load_manifest()
        parsed = urlparse(self.path)

        if parsed.path == "/manifest":
            data = json.dumps(manifest).encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            return

        if parsed.path.startswith("/download/"):
            name = parsed.path.split("/", 2)[-1]
            if name == manifest["bundle"]["filename"]:
                self._send_file(Path(manifest["bundle"]["path"]), head_only=True)
                return
            if name == manifest["dataset"]["filename"]:
                self._send_file(Path(manifest["dataset"]["path"]), head_only=True)
                return
            if name == manifest["weights"]["filename"]:
                self._send_file(Path(manifest["weights"]["path"]), head_only=True)
                return

        self.send_error(HTTPStatus.NOT_FOUND, "Unknown endpoint")

    def do_POST(self) -> None:
        manifest = load_manifest()
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        token = query.get("token", [""])[0]
        if token != manifest["token"]:
            self.send_error(HTTPStatus.FORBIDDEN, "Invalid token")
            return

        if not parsed.path.startswith("/upload/"):
            self.send_error(HTTPStatus.NOT_FOUND, "Unknown endpoint")
            return

        name = parsed.path.split("/", 2)[-1]
        uploads = manifest.get("uploads", {})
        target = uploads.get(name)
        if not target:
            self.send_error(HTTPStatus.NOT_FOUND, "Upload target not configured")
            return

        length = int(self.headers.get("Content-Length", "0"))
        data = self.rfile.read(length)
        target_path = Path(target)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with open(target_path, "wb") as handle:
            handle.write(data)

        self._send_json({"status": "ok", "saved": str(target_path)})


def main() -> None:
    host = os.getenv("COLAB_BRIDGE_HOST", "127.0.0.1")
    port = int(os.getenv("COLAB_BRIDGE_PORT", "8765"))
    server = ThreadingHTTPServer((host, port), ColabBridgeHandler)
    print(f"[ColabBridge] Serving on http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
