"""campusMate local prototype server (standard library only).

The shipping backend is FastAPI + uvicorn + Windows-only services. This file is
the P0 cut of "run on the phone": it serves the real ``web/`` directory from the
app bundle and answers the framework endpoints the shell needs at startup.
Everything else under ``/api/v1`` returns a clear 503 until the real backend is
cross-compiled for iOS (see docs/IOS_LOCAL.md).

Layout inside the app bundle::

    campusMateLocal.app/
      boot.py            this file
      web/               copy of the repository web/ directory
      python/lib/python3.13/   CPython standard library
"""

import json
import mimetypes
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parent
WEB = ROOT / "web"
VERSION = "0.2.0"
APPEARANCE = {"theme": "default", "companions": {}, "reduceMotion": False, "options": {}}
STATIC_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".woff2": "font/woff2",
    ".ico": "image/x-icon",
}


def themes():
    """Mirror backend/core/themes.py::catalog for the bundled themes."""
    root = (WEB / "themes").resolve()
    items, errors = [], []
    for path in sorted(root.glob("*/theme.json")):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            if value.get("id") != path.parent.name:
                raise ValueError("theme id must match its directory")
            base = "/assets/themes/" + path.parent.name + "/"
            item = {
                "id": value["id"],
                "name": value["name"],
                "description": value.get("description", ""),
                "api_version": 1,
                "styles": [base + name for name in value.get("styles", [])],
                "preview": base + value["preview"] if value.get("preview") else None,
                "entry": base + value["entry"] if value.get("entry") else None,
                "views": {key: base + name for key, name in value.get("views", {}).items()},
                "backgrounds": {key: base + name for key, name in value.get("backgrounds", {}).items()},
            }
            items.append(item)
        except (OSError, ValueError, KeyError):
            errors.append({"id": path.parent.name, "message": "主题清单或资源无效，请检查 theme.json。"})
    items.sort(key=lambda item: (item["id"] != "default", item["id"]))
    return {"api_version": 1, "default": "default", "items": items, "errors": errors}


def settings(port):
    return {
        "port": port,
        "active_port": port,
        "restart_required": False,
        "appearance": APPEARANCE,
        "storage": {"directory": "app", "encryption": "iOS file protection"},
    }


def bootstrap(port):
    return {
        "version": VERSION,
        "csrf_token": "local-preview",
        "settings": settings(port),
        "modules": [],
        "categories": [
            {"id": "settings", "label": "设置", "icon": "⚙",
             "description": "本地原型：业务模块尚未移植到 iOS。", "order": 10001}
        ],
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "campusMateLocal/" + VERSION
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # keep the device console readable
        pass

    def do_GET(self):
        self.route(head=False)

    def do_HEAD(self):
        self.route(head=True)

    def do_POST(self):
        self.send_json(503, {"detail": "本地原型暂不支持写操作。"})

    do_PUT = do_POST
    do_DELETE = do_POST
    do_PATCH = do_POST

    def route(self, head):
        path = urlsplit(self.path).path
        port = self.server.server_address[1]
        if path == "/api/v1/bootstrap":
            self.send_json(200, bootstrap(port), head)
        elif path == "/api/v1/settings":
            self.send_json(200, settings(port), head)
        elif path == "/api/v1/settings/appearance":
            self.send_json(200, APPEARANCE, head)
        elif path == "/api/v1/themes":
            self.send_json(200, themes(), head)
        elif path == "/api/v1/health":
            self.send_json(200, {"application": "campus-framework", "version": VERSION,
                                 "local": True, "time": datetime.now(timezone.utc).isoformat()}, head)
        elif path.startswith("/api/"):
            self.send_json(503, {"detail": "本地原型未包含该接口；完整后端需要先完成 iOS 依赖交叉编译。"}, head)
        else:
            self.send_static(path, head)

    def send_static(self, path, head):
        relative = path.lstrip("/")
        if relative.startswith("assets/"):
            relative = relative[len("assets/"):]
        target = (WEB / unquote(relative)).resolve() if relative else WEB / "index.html"
        if not relative:
            target = WEB / "index.html"
        try:
            inside = target.is_relative_to(WEB.resolve())
        except ValueError:
            inside = False
        if not inside or not target.is_file():
            if path == "/" or "." not in path.rsplit("/", 1)[-1]:
                target = WEB / "index.html"
            else:
                self.send_json(404, {"detail": "文件不存在。"}, head)
                return
        body = target.read_bytes()
        kind = STATIC_TYPES.get(target.suffix.lower()) or mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store" if target.suffix in {".html", ".json"} else "max-age=300")
        self.end_headers()
        if not head:
            self.wfile.write(body)

    def send_json(self, status, payload, head=False):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if not head:
            self.wfile.write(body)


def main():
    port_file = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    if port_file:
        port_file.write_text(str(server.server_address[1]), encoding="utf-8")
    try:
        server.serve_forever(poll_interval=0.2)
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
