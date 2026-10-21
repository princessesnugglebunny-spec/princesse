"""Minimal web UI with bearer-token authentication and CSRF protection."""

from __future__ import annotations

import hmac
import json
import secrets
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

from ..config import load_config
from ..tools import ToolRegistry


def _html(token: str, csrf: str) -> str:
    safe_token = token.replace('"', "&quot;")
    return f"""<!doctype html><html><head><title>Princesse</title></head><body>
<h1>Princesse</h1>
<p>Minimal web UI. All API calls require the token. Use <code>/api/tools</code> to list tools.</p>
<form action="/api/run" method="get">
<input name="token" type="hidden" value="{safe_token}"/>
<input name="csrf" type="hidden" value="{csrf}"/>
<input name="goal" size="60" placeholder="goal"/>
<button type="submit">Run</button>
</form>
</body></html>"""


class Handler(BaseHTTPRequestHandler):
    token = ""
    csrf_token = ""
    server_version = "princesse"

    def _authorized(self, query: dict[str, list[str]]) -> bool:
        if not self.token:
            return True
        supplied = ""
        header = self.headers.get("Authorization", "")
        if header.lower().startswith("bearer "):
            supplied = header[7:].strip()
        if not supplied:
            supplied = self.headers.get("X-Princesse-Token", "")
        if not supplied and query:
            supplied = (query.get("token") or [""])[0]
        return bool(supplied) and hmac.compare_digest(supplied, self.token)

    def _csrf_ok(self, query: dict[str, list[str]]) -> bool:
        if not self.token:
            return True
        supplied = self.headers.get("X-CSRF-Token", "")
        if not supplied and query:
            supplied = (query.get("csrf") or [""])[0]
        return bool(supplied) and hmac.compare_digest(supplied, self.csrf_token)

    def _json(self, payload, status: int = 200):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        if not self._authorized(query):
            self._json({"error": "unauthorized"}, status=401)
            return
        if parsed.path == "/":
            body = _html(self.token, self.csrf_token).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)
            return
        if parsed.path == "/api/tools":
            from ..bootstrap import register_default_tools
            reg = ToolRegistry.get_instance()
            register_default_tools(reg)
            self._json([t.name for t in reg.list_all()])
            return
        if parsed.path == "/api/run":
            if not self._csrf_ok(query):
                self._json({"error": "csrf token required"}, status=403)
                return
            goal = (query.get("goal") or [""])[0]
            self._json({"goal": goal, "status": "accepted"})
            return
        self._json({"error": "not found"}, status=404)

    def do_POST(self):
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        if not self._authorized(query):
            self._json({"error": "unauthorized"}, status=401)
            return
        if not self._csrf_ok(query):
            self._json({"error": "csrf token required"}, status=403)
            return
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            self._json({"error": "invalid json"}, status=400)
            return
        self._json({"status": "accepted", "received": payload})

    def log_message(self, format, *args):
        pass


def serve(port: int = 8765, host: str | None = None, token: str | None = None) -> None:
    cfg = load_config()
    bind_host = host or cfg.web_host
    auth_token = token if token is not None else cfg.web_token
    if not auth_token:
        auth_token = secrets.token_urlsafe(24)
    Handler.token = auth_token
    Handler.csrf_token = secrets.token_urlsafe(24)
    httpd = HTTPServer((bind_host, port), Handler)
    print(f"Princesse web UI on http://{bind_host}:{port}")
    print(f"Token: {auth_token}")
    if bind_host not in ("127.0.0.1", "localhost", "::1"):
        print("WARNING: bound to a non-loopback address; anyone who can reach this port "
              "and knows the token can drive the agent.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        httpd.server_close()
