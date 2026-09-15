"""零依赖 Web 服务: 仅用标准库 http.server 提供静态页面与 /api/plan。

启动: python -m astro_planner.server  (默认 http://127.0.0.1:8000)
"""
from __future__ import annotations

import argparse
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import numpy as np

from .coordinates import Observer
from .planner import SITES, generate_plan, DEFAULT_CATALOG

_STATIC = Path(__file__).resolve().parent.parent / "webapp" / "static"


def _json_default(o):
    if isinstance(o, (np.floating, np.integer)):
        return o.item()
    if isinstance(o, np.ndarray):
        return o.tolist()
    raise TypeError(f"not serializable: {type(o)}")


def build_payload(req: dict) -> dict:
    """把前端请求转成计划结果。"""
    site = req.get("site")
    if isinstance(site, dict):
        obs = Observer(site.get("name", "自定义"),
                       float(site["lat"]), float(site["lon"]),
                       float(site.get("elev", 0.0)))
    elif site in SITES:
        obs = SITES[site]
    else:
        # 容错: 给名字匹配不到时用第一个预设
        obs = next(iter(SITES.values()))

    targets = req.get("targets")
    tz = float(req.get("utc_offset", 8.0))
    date_str = str(req.get("date"))
    settings = req.get("settings") or None
    order = req.get("order")

    horizon_points = req.get("horizon_points")
    horizon_key = req.get("horizon", "mountain")

    return generate_plan(obs, date_str, tz, targets, settings,
                         horizon_key, horizon_points, order)


class Handler(BaseHTTPRequestHandler):
    server_version = "AstroPlanner/0.1"

    def _send(self, code, body: bytes, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            return self._serve("index.html", "text/html; charset=utf-8")
        if path in ("/app.js",):
            return self._serve("app.js", "application/javascript; charset=utf-8")
        if path in ("/style.css",):
            return self._serve("style.css", "text/css; charset=utf-8")
        if path == "/api/sites":
            body = json.dumps({
                "sites": [k for k in SITES],
                "catalog": [t.to_dict() for t in DEFAULT_CATALOG],
            }, default=_json_default).encode()
            return self._send(200, body, "application/json")
        self._send(404, b"not found", "text/plain")

    def _serve(self, name, ctype):
        f = _STATIC / name
        if not f.exists():
            return self._send(404, b"missing static file", "text/plain")
        self._send(200, f.read_bytes(), ctype)

    def do_POST(self):
        if self.path.split("?", 1)[0] != "/api/plan":
            return self._send(404, b"not found", "text/plain")
        length = int(self.headers.get("Content-Length", 0))
        try:
            req = json.loads(self.rfile.read(length) or b"{}")
            payload = build_payload(req)
        except KeyError as e:
            return self._send(400, f"缺少字段: {e}".encode(), "text/plain")
        except Exception as e:  # noqa: BLE001 - 直接把错误返给前端
            import traceback
            traceback.print_exc()
            return self._send(500, f"计算失败: {e}".encode(), "text/plain")
        body = json.dumps(payload, default=_json_default).encode()
        self._send(200, body, "application/json")

    def log_message(self, fmt, *args):
        sys.stderr.write("[server] " + fmt % args + "\n")


def main(argv=None):
    ap = argparse.ArgumentParser(description="天文观测计划生成器 Web 服务")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args(argv)
    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"天文观测计划生成器已启动: http://{args.host}:{args.port}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")


if __name__ == "__main__":
    main()
