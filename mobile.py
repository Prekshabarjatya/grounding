"""Phone app: an installable web app served from your own computer over home Wi-Fi.

Photos go phone → this machine → local models. Nothing touches the cloud.
Pairing: scan the QR in the dashboard (URL carries a secret token, swapped for an HttpOnly cookie).
"""
import hmac, json, secrets, socket
from email import policy
from email.parser import BytesParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import agents
import grounding as g

MAX_UPLOAD = 20 * 1024 * 1024
PORT = 8766


def token():
    con = g.db()
    t = g.kv(con, "phone_token")
    if not t:
        t = secrets.token_urlsafe(24)
        g.set_kv(con, "phone_token", t)
    return t


def lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))  # no packet is sent; just picks the LAN interface
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def phone_url(port=PORT):
    return f"http://{lan_ip()}:{port}/?t={token()}"


def parse_upload(ctype, body):
    """First file in a multipart/form-data body (the cgi module is gone since 3.13)."""
    msg = BytesParser(policy=policy.HTTP).parsebytes(b"Content-Type: " + ctype.encode() + b"\r\n\r\n" + body)
    for part in msg.iter_parts() if msg.is_multipart() else []:
        if part.get_filename():
            return part.get_filename(), part.get_payload(decode=True)
    return "", b""


ICON = ("<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><rect width='100' height='100' rx='22' "
        "fill='#3E6B48'/><path d='M50 78V44M50 56c-14 0-22-9-22-22 14 0 22 9 22 22zm0-6c0-13 8-22 22-22 0 13-8 22-22 22z' "
        "stroke='#fff' stroke-width='6' fill='none' stroke-linecap='round'/></svg>")

MANIFEST = json.dumps({"name": "Grounding", "short_name": "Grounding", "start_url": "/", "display": "standalone",
                       "background_color": "#F3EFE6", "theme_color": "#3E6B48",
                       "icons": [{"src": "/icon.svg", "sizes": "any", "type": "image/svg+xml"}]})

PAGE = (Path(__file__).parent / "mobile.html").read_text()


class Phone(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, code, body, ctype="application/json", headers=()):
        body = body if isinstance(body, bytes) else (body if isinstance(body, str) else json.dumps(body)).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in headers:
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def authed(self):
        cookie = dict(c.strip().split("=", 1) for c in self.headers.get("Cookie", "").split(";") if "=" in c)
        return hmac.compare_digest(cookie.get("gt", ""), token())

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/manifest.webmanifest":
            return self.send(200, MANIFEST, "application/manifest+json")
        if u.path == "/icon.svg":
            return self.send(200, ICON, "image/svg+xml")
        if u.path == "/":
            t = parse_qs(u.query).get("t", [""])[0]
            if t and hmac.compare_digest(t, token()):  # pairing link → cookie, drop token from URL
                return self.send(303, b"", "text/plain", [("Location", "/"), (
                    "Set-Cookie", f"gt={t}; HttpOnly; SameSite=Strict; Path=/; Max-Age=31536000")])
            if not self.authed():
                return self.send(401, "<h2 style='font-family:system-ui'>Scan the QR code in the Grounding "
                                      "dashboard on your computer to pair this phone.</h2>", "text/html; charset=utf-8")
            return self.send(200, PAGE, "text/html; charset=utf-8")
        if not self.authed():
            return self.send(401, {"error": "not paired"})
        if u.path == "/api/status":
            return self.send(200, g.status())
        if u.path == "/api/journal":
            rows = g.db().execute("SELECT at,mission,photo,entry FROM journal ORDER BY id DESC LIMIT 50")
            return self.send(200, [dict(r) for r in rows])
        if u.path.startswith("/photos/"):
            f = g.HOME / "photos" / Path(u.path).name  # .name blocks path traversal
            ctype = "image/png" if f.suffix == ".png" else "image/webp" if f.suffix == ".webp" else "image/jpeg"
            return self.send(200, f.read_bytes(), ctype) if f.is_file() else self.send(404, {"error": "not found"})
        self.send(404, {"error": "not found"})

    def do_POST(self):
        if not self.authed():
            return self.send(401, {"error": "not paired"})
        try:
            if self.path == "/api/mission":
                return self.send(200, {"mission": agents.run_mission(force=True)["mission"]})
            if self.path == "/api/reflect":
                n = int(self.headers.get("Content-Length", 0))
                if n > MAX_UPLOAD:
                    return self.send(413, {"error": "Photo too large (20 MB max)."})
                name, data = parse_upload(self.headers.get("Content-Type", ""), self.rfile.read(n))
                if not data:
                    return self.send(400, {"error": "No photo received."})
                return self.send(200, {"entry": agents.run_reflect(data, name)["entry"]})
        except RuntimeError as e:
            return self.send(503, {"error": str(e)})
        self.send(404, {"error": "not found"})


def serve(port=PORT):
    print(f"Phone app: open {phone_url(port)} on your phone (same Wi-Fi), or scan the QR in the dashboard.")
    ThreadingHTTPServer(("0.0.0.0", port), Phone).serve_forever()
