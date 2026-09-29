#!/usr/bin/env python3
"""
BookPilot local print agent: lets the web app print to network (LAN/Wi-Fi)
receipt and kitchen printers.

Browsers cannot open raw TCP connections, so this tiny program runs on the
till computer and forwards print jobs to the printer's port 9100. It uses
only the Python standard library.

    python print_agent.py                                # allow any origin
    python print_agent.py --origin https://yourshop.onrender.com

Then choose "Network (LAN) printer" on the Devices page and enter the
printer's IP address. Only private-network printer addresses are accepted.
"""
import argparse
import ipaddress
import json
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MAX_JOB_BYTES = 2 * 1024 * 1024


class Handler(BaseHTTPRequestHandler):
    allowed_origins = ["*"]

    def _cors(self):
        origin = self.headers.get("Origin", "")
        if "*" in self.allowed_origins:
            self.send_header("Access-Control-Allow-Origin", origin or "*")
        elif origin in self.allowed_origins:
            self.send_header("Access-Control-Allow-Origin", origin)
        self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Printer-Host, X-Printer-Port")
        self.send_header("Access-Control-Allow-Private-Network", "true")

    def _reply(self, code, body):
        data = json.dumps(body).encode()
        self.send_response(code)
        self._cors()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _origin_ok(self):
        origin = self.headers.get("Origin", "")
        return "*" in self.allowed_origins or not origin or origin in self.allowed_origins

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        if self.path.startswith("/health"):
            return self._reply(200, {"ok": True, "agent": "bookpilot-print-agent"})
        return self._reply(404, {"error": "not found"})

    def do_POST(self):
        if not self.path.startswith("/print"):
            return self._reply(404, {"error": "not found"})
        if not self._origin_ok():
            return self._reply(403, {"error": "origin not allowed"})
        host = self.headers.get("X-Printer-Host", "").strip()
        try:
            port = int(self.headers.get("X-Printer-Port", "9100"))
            ip = ipaddress.ip_address(socket.gethostbyname(host))
        except (ValueError, OSError):
            return self._reply(400, {"error": "invalid printer address"})
        if not (ip.is_private or ip.is_loopback or ip.is_link_local):
            return self._reply(400, {"error": "only printers on the local network are allowed"})
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > MAX_JOB_BYTES:
            return self._reply(400, {"error": "empty or oversized print job"})
        job = self.rfile.read(length)
        try:
            with socket.create_connection((str(ip), port), timeout=8) as conn:
                conn.sendall(job)
        except OSError as exc:
            return self._reply(502, {"error": f"printer {ip}:{port} unreachable: {exc}"})
        return self._reply(200, {"ok": True, "bytes": len(job)})

    def log_message(self, fmt, *args):
        print("[print-agent]", fmt % args)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", type=int, default=8719)
    parser.add_argument("--origin", action="append", help="Allowed web app origin (repeatable). Default: any.")
    args = parser.parse_args()
    Handler.allowed_origins = args.origin or ["*"]
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"BookPilot print agent listening on http://127.0.0.1:{args.port} (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
