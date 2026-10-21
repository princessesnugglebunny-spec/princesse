"""Minimal web UI using stdlib http.server."""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse


def _html() -> str:
    return """<!doctype html><html><head><title>Princesse</title></head><body>
<h1>Princesse</h1>
<p>Minimal web UI. Use /api/tools to list tools, /api/run?goal=... to run.</p>
<form action="/api/run" method="get">
<input name="goal" size="60" placeholder="goal"/>
<button type="submit">Run</button>
</form>
</body></html>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/":
            body = _html().encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if parsed.path == "/api/tools":
            from ..tools import ToolRegistry
            from ..capabilities import register_capability_tools
            reg = ToolRegistry.get_instance()
            register_capability_tools(reg)
            data = [t.name for t in reg.list_all()]
            body = json.dumps(data).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if parsed.path == "/api/run":
            qs = parse_qs(parsed.query)
            goal = qs.get("goal", [""])[0]
            body = json.dumps({"goal": goal, "status": "accepted"}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(404)
        self.end_headers()

    def log_message(self, format, *args):
        pass


def serve(port: int = 8765, host: str = "127.0.0.1"):
    httpd = HTTPServer((host, port), Handler)
    print(f"Princesse web UI on http://{host}:{port}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        httpd.server_close()
