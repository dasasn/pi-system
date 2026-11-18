#!/usr/bin/env python3
"""
webutil.py — shared HTTP layer for the webexec skill package.

Why this exists: every tool below needs the same four things
  1. a client that survives WAF / IP-block / TLS-termination gaps
  2. a soft-404 baseline so "HTTP 200" never lies
  3. differential proof (baseline vs payload) instead of vibes
  4. one place that redacts secrets before anything hits stdout

Pure stdlib + optional requests. No network calls at import time.

Author: Particle-1 (webexec)
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

UA_POOL = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/203.0.113.10 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/203.0.113.10 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
    "Mozilla/5.0 (compatible; bingbot/2.0; +http://www.bing.com/bingbot.htm)",
]

LOOT = os.path.expanduser("~/loot")


def ensure_loot() -> None:
    for d in ("raw", "secrets", "validated", "reports", "tools"):
        os.makedirs(os.path.join(LOOT, d), exist_ok=True)
    for d in ("secrets", "validated"):
        try:
            os.chmod(os.path.join(LOOT, d), 0o700)
        except OSError:
            pass


# --------------------------------------------------------------------------- #
# redaction — nothing secret is ever printed
# --------------------------------------------------------------------------- #
_SECRET_PATTERNS = [
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S), "[REDACTED_PRIVKEY]"),
    (re.compile(r"\b(AKIA|ASIA)[0-9A-Z]{16}\b"), r"\1[REDACTED]"),
    (re.compile(r"\bLTAI[A-Za-z0-9]{12,}\b"), "LTAI[REDACTED]"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"), "gh[REDACTED]"),
    (re.compile(r"\bxox[baprs]-[A-Za-z0-9\-]{10,}\b"), "xox[REDACTED]"),
    (re.compile(r"\bsk_live_[A-Za-z0-9]{10,}\b"), "sk_live_[REDACTED]"),
    (re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b"), "AIza[REDACTED]"),
    (re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\b"), "[REDACTED_JWT]"),
    (re.compile(r"(?i)\b(0x)?[a-f0-9]{64}\b"), "[REDACTED_64HEX]"),
    (re.compile(r"(?i)((?:password|passwd|pwd|secret|token|api[_-]?key|private[_-]?key)\s*[:=]\s*)(['\"]?)[^'\"\s,;]{6,}"), r"\1\2[REDACTED]"),
]


def redact(text: str) -> str:
    """Scrub secret-looking strings. Use on everything before printing/reporting."""
    if not text:
        return text
    out = text
    for pat, rep in _SECRET_PATTERNS:
        out = pat.sub(rep, out)
    return out


def fp(value: str) -> str:
    """Fingerprint for a secret: sha256 first 12 hex. Safe to print."""
    return hashlib.sha256(value.strip().encode()).hexdigest()[:12]


# --------------------------------------------------------------------------- #
# response
# --------------------------------------------------------------------------- #
class Resp:
    __slots__ = ("url", "status", "headers", "body", "elapsed", "error", "via", "_raw")

    def __init__(self, url, status=0, headers=None, body="", elapsed=0.0, error=None, via="direct"):
        self.url = url
        self.status = status
        self.headers = headers or {}
        self._raw = body if isinstance(body, (bytes, bytearray)) else None
        self.body = body if isinstance(body, str) else (body or b"").decode("utf-8", "replace")
        self.elapsed = elapsed
        self.error = error
        self.via = via

    @property
    def raw_bytes(self) -> bytes:
        """Original body bytes. resp.body is decoded utf-8-replace, which is lossy
        for binary content — keep the bytes for zlib/object parsing."""
        return self._raw if self._raw is not None else self.body.encode("utf-8", "replace")

    def header(self, name, default=""):
        for k, v in self.headers.items():
            if k.lower() == name.lower():
                return v
        return default

    @property
    def size(self):
        return len(self.body)

    @property
    def ok(self):
        return self.status not in (0,) and self.error is None

    def json(self):
        try:
            return json.loads(self.body)
        except Exception:
            return None

    def text(self, limit=None):
        return self.body[:limit] if limit else self.body

    def __repr__(self):
        e = f" err={self.error}" if self.error else ""
        return f"<Resp {self.status} {self.size}B {self.elapsed*1000:.0f}ms via={self.via}{e}>"


# --------------------------------------------------------------------------- #
# proxy chain
# --------------------------------------------------------------------------- #
def _proxy_from_env(kind="direct"):
    """kind: direct | http | tor. Env: WEXEC_PROXY (http://user:pass@host:port), WEXEC_TOR."""
    if kind == "direct":
        return None
    if kind == "tor":
        return os.environ.get("WEXEC_TOR", "socks5h://127.0.0.1:9050")
    return os.environ.get("WEXEC_PROXY") or None


class Client:
    """Tiny HTTP client with UA rotation, retry, proxy and raw-socket fallbacks.

    Never trusts a single transport: if urllib gives 000 (IP drop / TLS gap),
    it retries with raw HTTP/1.1 over socket, then plain HTTP if url is HTTPS.
    """

    def __init__(self, timeout=12, proxy=None, verify=False, follow=True, ua=None, delay=0.0):
        self.timeout = timeout
        self.proxy = proxy
        self.verify = verify
        self.follow = follow
        self.ua = ua
        self.delay = delay
        self.domain = ""  # set by caller for header lookups
        self._ssl = ssl.create_default_context()
        if not verify:
            self._ssl.check_hostname = False
            self._ssl.verify_mode = ssl.CERT_NONE

    # ---- header sets -------------------------------------------------------
    def headers(self, extra=None, ua=None):
        h = {
            "User-Agent": ua or self.ua or random.choice(UA_POOL),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,id;q=0.8",
            "Accept-Encoding": "identity",
            "Connection": "close",
        }
        if self.domain:
            h.setdefault("Host", self.domain.split("://")[-1].split("/")[0])
        if extra:
            h.update(extra)
        return h

    def _urlopen(self, req, timeout, via):
        t0 = time.time()
        try:
            opener_args = {}
            if self.proxy and self.proxy.startswith(("http://", "https://")):
                opener_args["proxies"] = {"http": self.proxy, "https": self.proxy}
            if opener_args:
                op = urllib.request.build_opener(urllib.request.ProxyHandler(opener_args["proxies"]))
            else:
                op = urllib.request.build_opener()
            r = op.open(req, timeout=timeout)
            body = r.read()
            return Resp(req.full_url, r.status, dict(r.headers), body, time.time() - t0, via=via)
        except urllib.error.HTTPError as e:
            body = e.read() if e.fp else b""
            return Resp(req.full_url, e.code, dict(e.headers or {}), body, time.time() - t0, via=via)
        except Exception as e:  # noqa: BLE001
            return Resp(req.full_url, 0, {}, "", time.time() - t0, error=f"{type(e).__name__}: {e}", via=via)

    # ---- raw socket HTTP/1.1 ----------------------------------------------
    def raw(self, url, method="GET", data=None, headers=None, timeout=None):
        """Minimal raw HTTP/1.1. Bypasses urllib quirks, header mangling, some WAF rules."""
        timeout = timeout or self.timeout
        u = urllib.parse.urlsplit(url)
        host = u.hostname or ""
        port = u.port or (443 if u.scheme == "https" else 80)
        path = u.path or "/"
        if u.query:
            path += "?" + u.query
        hdrs = self.headers(headers)
        hdrs["Host"] = u.netloc
        if data is not None and not isinstance(data, (bytes, bytearray)):
            data = str(data).encode()
        if data is not None:
            hdrs["Content-Length"] = str(len(data))
        req_bytes = f"{method} {path} HTTP/1.1\r\n".encode()
        for k, v in hdrs.items():
            req_bytes += f"{k}: {v}\r\n".encode()
        req_bytes += b"\r\n" + (data or b"")
        t0 = time.time()
        try:
            if u.scheme == "https":
                s = self._ssl.wrap_socket(__import__("socket").create_connection((host, port), timeout=timeout), server_hostname=host)
            else:
                s = __import__("socket").create_connection((host, port), timeout=timeout)
            s.sendall(req_bytes)
            chunks = []
            while True:
                c = s.recv(65536)
                if not c:
                    break
                chunks.append(c)
            s.close()
            raw = b"".join(chunks)
            head, _, body = raw.partition(b"\r\n\r\n")
            lines = head.decode("iso-8859-1", "replace").split("\r\n")
            status = 0
            m = re.match(r"HTTP/\d(?:\.\d)? (\d{3})", lines[0] if lines else "")
            if m:
                status = int(m.group(1))
            hh = {}
            for ln in lines[1:]:
                if ":" in ln:
                    k, v = ln.split(":", 1)
                    hh[k.strip()] = v.strip()
            if hh.get("Transfer-Encoding", "").lower() == "chunked":
                body = _dechunk(body)
            if "gzip" in hh.get("Content-Encoding", "").lower():
                try:
                    import gzip
                    body = gzip.decompress(body)
                except Exception:
                    pass
            return Resp(url, status, hh, body, time.time() - t0, via="raw")
        except Exception as e:  # noqa: BLE001
            return Resp(url, 0, {}, "", time.time() - t0, error=f"raw {type(e).__name__}: {e}", via="raw")

    # ---- public ------------------------------------------------------------
    def req(self, url, method="GET", data=None, headers=None, timeout=None, allow_raw_fallback=True):
        if self.delay:
            time.sleep(self.delay)
        hdrs = self.headers(headers)
        if data is not None and not isinstance(data, (bytes, bytearray)):
            data = str(data).encode()
        req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
        resp = self._urlopen(req, timeout or self.timeout, "direct" if not self.proxy else "proxy")
        if resp.status == 0 and allow_raw_fallback:
            resp = self.raw(url, method, data, headers, timeout)
        return resp

    def get(self, url, **kw):
        return self.req(url, "GET", **kw)

    def post(self, url, data=None, headers=None, **kw):
        h = {"Content-Type": "application/x-www-form-urlencoded"}
        h.update(headers or {})
        return self.req(url, "POST", data, h, **kw)

    def post_json(self, url, obj, **kw):
        return self.req(url, "POST", json.dumps(obj), {"Content-Type": "application/json"}, **kw)


def _dechunk(body: bytes) -> bytes:
    out, rest = b"", body
    while rest:
        line, _, rest = rest.partition(b"\r\n")
        try:
            n = int(line.split(b";")[0].strip() or b"0", 16)
        except ValueError:
            break
        if n == 0:
            break
        out += rest[:n]
        rest = rest[n + 2:]
    return out


# --------------------------------------------------------------------------- #
# soft-404 baseline + differential proof
# --------------------------------------------------------------------------- #
class Baseline:
    """Establishes what a *non-existent* resource looks like on this host.

    Any finding must differ from this baseline in a measurable way. This is the
    single defence against reporting SPA soft-404s as vulnerabilities.
    """

    def __init__(self, client: Client, base_url: str, samples=4):
        self.client = client
        self.base = base_url.rstrip("/")
        self.samples = []
        rnd = "".join(random.choice("abcdefghijklmnopqrstuvwxyz0123456789") for _ in range(12))
        for p in (f"/{rnd}", f"/{rnd}.php", f"/{rnd}-{rnd[:4]}.txt", f"/__nope_{rnd}/", f"/{rnd}/index.html"):
            r = client.get(self.base + p)
            self.samples.append(r)
        self.statuses = {r.status for r in self.samples}
        self.sizes = [r.size for r in self.samples if r.status]
        self.sigs = {_shingle(r.body) for r in self.samples}

    @property
    def status(self):
        return max(self.statuses) if self.statuses else 0

    @property
    def size_median(self):
        if not self.sizes:
            return 0
        s = sorted(self.sizes)
        return s[len(s) // 2]

    def is_soft404(self, resp: Resp) -> bool:
        """True when this response is indistinguishable from a missing resource."""
        if not resp.ok:
            return True
        if resp.status in self.statuses and resp.size and self.size_median:
            if abs(resp.size - self.size_median) / max(self.size_median, 1) < 0.02:
                if _shingle(resp.body) in self.sigs:
                    return True
                # same size, high similarity to any baseline sample
                for s in self.samples:
                    if s.body and _similarity(s.body, resp.body) > 0.97:
                        return True
        return False

    def is_real_hit(self, resp: Resp, markers=()) -> bool:
        if not resp.ok or resp.status in (0, 404, 410):
            return False
        if any(m in resp.body for m in markers):
            return True
        return not self.is_soft404(resp)


def _shingle(text: str, n=8):
    text = re.sub(r"\s+", " ", text or "").strip()
    return hash(text[:4000]) if len(text) < 4000 else hash(text[:4000])


def _similarity(a: str, b: str) -> float:
    import difflib
    return difflib.SequenceMatcher(None, a[:6000], b[:6000]).ratio()


class Differ:
    """Differential prover: send baseline request, then payload request, compare.

    Used for SQLi/LFI/SSTI/XXE/SSRF/command-injection: a finding only exists when
    the payload response is measurably different from the matched control.
    """

    def __init__(self, client: Client):
        self.client = client

    def prove(self, url_a, url_b=None, params_diff=True, control_kw=None):
        control_kw = control_kw or {}
        ra = self.client.get(url_a, **control_kw)
        rb = self.client.get(url_b, **control_kw) if url_b else None
        return self.compare(ra, rb)

    @staticmethod
    def compare(ra: Resp, rb: Resp):
        return {
            "control_status": ra.status,
            "payload_status": rb.status if rb else None,
            "status_diff": (ra.status != (rb.status if rb else ra.status)),
            "size_diff": (ra.size != (rb.size if rb else ra.size)),
            "control_size": ra.size,
            "payload_size": rb.size if rb else None,
            "ratio": round(((rb.size if rb else 0) / max(ra.size, 1)), 3) if rb else None,
            "similarity": round(_similarity(ra.body, rb.body), 3) if rb else None,
            "delta_ms": round(((rb.elapsed if rb else 0) - ra.elapsed) * 1000),
        }

    @staticmethod
    def verdict(d: dict, time_threshold_ms=1500, ratio_threshold=0.25, sim_threshold=0.92) -> str:
        """STRONG | WEAK | NONE — never call WEAK a vulnerability."""
        if d.get("delta_ms", 0) >= time_threshold_ms:
            return "STRONG"
        if d.get("ratio") is not None:
            r = abs((d.get("ratio") or 1) - 1)
            if r >= ratio_threshold and (d.get("similarity") or 1) < sim_threshold:
                return "STRONG"
            if r >= ratio_threshold * 0.4 or (d.get("similarity") or 1) < 0.98:
                return "WEAK"
        if d.get("status_diff"):
            return "WEAK"
        return "NONE"


# --------------------------------------------------------------------------- #
# waf helpers
# --------------------------------------------------------------------------- #
WAF_SIGNS = {
    "cloudflare": ["cf-ray", "cf-cache-status", "__cf_bm", "cloudflare"],
    "sucuri": ["x-sucuri", "sucuri"],
    "imperva": ["incap_ses", "visid_incap", "x-iinfo"],
    "akamai": ["akamai", "x-akamai", "akamaighost"],
    "aws": ["x-amzn-requestid", "awselb"],
    "modsec": ["mod_security", "modsecurity", "not acceptable"],
    "f5": ["bigip", "f5-"],
    "wordfence": ["wordfence"],
    "fastly": ["fastly", "x-fastly"],
    "barracuda": ["barra_counter"],
}


def detect_waf(resp: Resp) -> list:
    blob = (" ".join(f"{k}:{v}" for k, v in resp.headers.items()) + " " + resp.body[:3000]).lower()
    return [name for name, sigs in WAF_SIGNS.items() if any(s in blob for s in sigs)]


def evasion_headers() -> list:
    """Header permutations used against keyword/UA based WAF rules."""
    return [
        {},
        {"X-Forwarded-For": "127.0.0.1"},
        {"X-Originating-IP": "127.0.0.1", "X-Remote-IP": "127.0.0.1"},
        {"X-Client-IP": "127.0.0.1", "X-Real-IP": "127.0.0.1"},
        {"Accept-Encoding": "gzip, deflate, br"},
        {"Content-Type": "application/json"},
        {"X-Requested-With": "XMLHttpRequest"},
        {"Referer": "https://www.google.com/"},
        {"X-HTTP-Method-Override": "GET"},
    ]


def neutralise(payload: str) -> str:
    """Build the CONTROL for a timing/boolean test.

    Must preserve the payload's shape (length, operators, comment syntax) while
    removing only the semantic trigger words. Replacing whole characters would
    change the request fingerprint and make the control useless.
    """
    control = re.sub(r"(?i)\b(SLEEP|PG_SLEEP)\s*\(", "coalesce(", payload)
    control = re.sub(r"(?i)(WAITFOR\s+DELAY)\s*", r"print \1 ", control)
    control = re.sub(r"(?i)\b(UNION|SELECT)\.?", "selectx", control)
    control = control.replace("0:0:5", "0:0:0")
    if control == payload:
        control = payload + " "
    return control


def mutate_payload(payload: str, level: int = 1) -> str:
    """Keyword-evasion mutations for ModSecurity-class filters. level 1..4."""
    p = payload
    if level <= 1:
        return p
    # inline comments break naive regexes, MySQL still parses them
    if level >= 2:
        for kw in ("UNION", "SELECT", "FROM", "WHERE", "AND", "OR", "ORDER", "BY", "SLEEP"):
            p = re.sub(rf"\b{kw}\b", f"/**/{kw}/**/", p)
    if level >= 3:
        p = p.replace(" ", "%09").replace("/**/", "+")
    if level >= 4:
        # version-comment obfuscation
        p = re.sub(r"\b(UNION|SELECT)\b", lambda m: f"/*!50000{m.group(1)}*/", p)
    return p


# --------------------------------------------------------------------------- #
# small utils
# --------------------------------------------------------------------------- #
def norm_url(u: str) -> str:
    if not u.startswith(("http://", "https://")):
        u = "https://" + u
    return u.rstrip("/")


def host_of(u: str) -> str:
    return urllib.parse.urlsplit(u).netloc


def save_raw(name: str, data, target: str = "unknown") -> str:
    """Persist evidence under ~/loot/raw/<target>_<date>/<name>."""
    ensure_loot()
    d = os.path.join(LOOT, "raw", f"{re.sub(r'[^a-zA-Z0-9._-]', '_', target)}_{time.strftime('%Y%m%d')}")
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, name)
    mode = "wb" if isinstance(data, (bytes, bytearray)) else "w"
    with open(path, mode) as f:
        f.write(data)
    return path


def save_secret(name: str, value: str) -> str:
    """Secret values land in ~/loot/secrets, 600. Never returned as content."""
    ensure_loot()
    path = os.path.join(LOOT, "secrets", name)
    old = os.umask(0o077)
    try:
        with open(path, "w") as f:
            f.write(value if value.endswith("\n") else value + "\n")
        os.chmod(path, 0o600)
    finally:
        os.umask(old)
    return path


def log(msg: str) -> None:
    sys.stderr.write(redact(msg) + "\n")
    sys.stderr.flush()


def table(rows, headers) -> str:
    """Plain aligned table for CLI output."""
    if not rows:
        return ""
    cols = list(zip(*([headers] + [list(map(str, r)) for r in rows])))
    w = [max(len(x) for x in c) for c in cols]
    out = "  ".join(h.ljust(w[i]) for i, h in enumerate(headers)) + "\n"
    out += "  ".join("-" * w[i] for i in range(len(headers))) + "\n"
    for r in rows:
        out += "  ".join(str(r[i]).ljust(w[i]) for i in range(len(headers))) + "\n"
    return out


def jsonout(obj) -> str:
    return json.dumps(obj, indent=2, default=str)
