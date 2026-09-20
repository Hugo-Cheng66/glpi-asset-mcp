from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from .server import McpServer


class HttpMcpHandler(BaseHTTPRequestHandler):
    server_version = "glpi-asset-mcp/0.1.0"

    def do_GET(self) -> None:
        if self.path == "/healthz":
            self._send_json({"status": "ok"})
            return
        if self.path == "/readyz":
            self._send_json({"status": "ready"})
            return
        self._send_json({"error": "not found"}, status=404)

    def do_POST(self) -> None:
        if self.path != "/mcp":
            self._send_json({"error": "not found"}, status=404)
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length).decode("utf-8")
            message = json.loads(raw)
            response = self.server.mcp.handle(message)  # type: ignore[attr-defined]
            self._send_json(response or {"jsonrpc": "2.0", "result": None})
        except Exception as exc:
            self._send_json({
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32603, "message": str(exc)},
            }, status=500)

    def log_message(self, format: str, *args: Any) -> None:
        if os.environ.get("GLPI_MCP_HTTP_ACCESS_LOG", "false").lower() == "true":
            super().log_message(format, *args)

    def _send_json(self, payload: Any, *, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    host = os.environ.get("GLPI_MCP_HTTP_HOST", "0.0.0.0")
    port = int(os.environ.get("GLPI_MCP_HTTP_PORT", "8000"))
    httpd = ThreadingHTTPServer((host, port), HttpMcpHandler)
    httpd.mcp = McpServer()  # type: ignore[attr-defined]
    print(f"glpi-asset-mcp HTTP server listening on {host}:{port}", flush=True)
    httpd.serve_forever()


if __name__ == "__main__":
    main()

