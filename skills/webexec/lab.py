#!/usr/bin/env python3
"""
lab.py — local intentionally-vulnerable HTTP server used to VERIFY the webexec
tools actually detect things. Not for targets; this is the test harness.

Endpoints:
  /echo?id=       reflects parameter raw  -> XSS + SSTI + SQLi-error simulation
  /file?f=        joins param onto /tmp/wexec_lab and reads it -> LFI
  /login?u=       returns SQL error on quote -> SQLi error-based
  /blind?id=      sleeps 1s when 'SLEEP' in value -> time-based SQLi check
  /redir?url=     302 to param when it starts with http -> open redirect
  /space/         SPA soft-404: every path returns the same 200 page

usage: python3 lab.py [--port 8089]
"""
import argparse
import os
import re
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SPA = b"<html><body><div id=app>loading</div><script src=/app.js></script></body></html>"


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, code, body, extra=None):
        if isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urllib.parse.urlsplit(self.path)
        q = dict(urllib.parse.parse_qsl(u.query))
        p = u.path

        if p == "/echo":
            val = q.get("id", "")
            return self.send(200, f"<html><body><p>You searched: {val}</p></body></html>")

        if p == "/login":
            val = q.get("u", "")
            if "'" in val:
                return self.send(500, "You have an error in your SQL syntax; check the manual "
                                      "that corresponds to your MySQL server version near '%s'" % val)
            return self.send(200, f"<html>user {val} ok</html>")

        if p == "/blind":
            v = q.get("id", "")
            if "SLEEP" in v.upper():
                time.sleep(5)
            return self.send(200, "<html>ok</html>")

        if p == "/file":
            f = q.get("f", "")
            target = os.path.normpath("/tmp/wexlab/" + f.lstrip("/"))
            if "/etc/passwd" in f or f.endswith("etc/passwd"):
                target = "/etc/passwd"
            try:
                with open(target, "rb") as fh:
                    return self.send(200, fh.read())
            except Exception:
                return self.send(404, "not found")

        if p == "/redir":
            return self.send(302, "", {"Location": q.get("url", "/")})

        if p == "/.env":
            return self.send(200, "APP_NAME=Lab\nAPP_KEY=base64:Zm9vYmFyYmF6cXV4MTIzNDU2Nzg5MA==\n"
                                  "DB_HOST=127.0.0.1\nDB_PASSWORD=Sup3rS3cret\nAWS_ACCESS_KEY_ID=AKIAIOSFODNN7REAL0001\n")
        if p == "/.git/config":
            return self.send(200, "[core]\n\trepositoryformatversion = 0\n[remote \"origin\"]\n\turl = https://x/y.git\n")
        if p == "/.env.production":
            return self.send(200, "<html><body>not found</body></html>")
        if p == "/admin/login":
            return self.send(200, "<html><form method=post action=/admin/login><input name=user>"
                                  "<input type=password name=pass><button>Log in</button></form></html>")
        if p == "/api/users":
            return self.send(200, '[{"id":1,"user":"admin"}]')
        if p == "/debug":
            return self.send(500, "Traceback (most recent call last): File x.py line 3 in <module>")
        if p.startswith("/space"):
            return self.send(200, SPA)
            return self.send(200, SPA)

        return self.send(200, "<html><body>lab home <form action=/echo><input name=id></form></body></html>")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8089)
    a = ap.parse_args()
    os.makedirs("/tmp/wexlab", exist_ok=True)
    with open("/tmp/wexlab/secret.txt", "w") as f:
        f.write("nothing-secret-here\n")
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), H)
    print(f"lab listening on http://127.0.0.1:{a.port}")
    srv.serve_forever()


if __name__ == "__main__":
    main()
