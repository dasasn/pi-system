#!/usr/bin/env python3
"""
acidhunt.py — discovery + exposure scan untuk domain .ac.id (dan domain apa pun).

Tahap:
  1. discovery  : crt.sh certificate transparency (%.ac.id) atau file/argumen
  2. alive      : resolusi DNS + probe HTTP/HTTPS
  3. exposure   : path rawan, soft-404 aware (.env, .git, log, backup, sourcemap, debug)
  4. fingerprint: framework/CMS + tanda debug aktif
  5. output     : JSONL per host + summary.json

Pakai:
  python3 acidhunt.py --tld ac.id --limit 60 -o out
  python3 acidhunt.py -f domains.txt -o out --workers 12
"""
import argparse
import concurrent.futures as cf
import hashlib
import json
import os
import re
import socket
import ssl
import time
import warnings
from urllib.parse import urlparse

import requests

warnings.filterwarnings("ignore")

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/203.0.113.10 Safari/537.36"
PATHS = [
    "/.env", "/.env.local", "/.env.production", "/.env.bak",
    "/.git/config", "/.git/HEAD", "/.git/index",
    "/storage/logs/laravel.log", "/laravel.log", "/debug.log",
    "/wp-config.php.bak", "/wp-config.php~", "/configuration.php.bak",
    "/backup.zip", "/db.sql", "/dump.sql",
    "/phpinfo.php", "/info.php", "/server-status", "/adminer.php", "/_ignition/health-check",
    "/package.json", "/composer.json", "/package-lock.json", "/.DS_Store",
]
FP = [
    ("laravel", re.compile(r"laravel|Laravel", re.I)),
    ("wordpress", re.compile(r"wp-content|wp-includes", re.I)),
    ("codeigniter", re.compile(r"CodeIgniter|ci_session", re.I)),
    ("ignition_debug", re.compile(r"Ignition|Whoops|SQLSTATE\[|Stack trace:", re.I)),
    ("spring", re.compile(r"Whitelabel Error Page|X-Application-Context", re.I)),
    ("drupal", re.compile(r"Drupal\.settings|sites/default/files", re.I)),
    ("php", re.compile(r"PHPSESSID|\.php", re.I)),
]
SEV = {"/.env": "critical", "/.git/config": "critical", "/.git/index": "high",
       "/storage/logs/laravel.log": "high", "/laravel.log": "high", "/debug.log": "medium",
       "/wp-config.php.bak": "critical", "/configuration.php.bak": "critical",
       "/backup.zip": "high", "/db.sql": "high", "/dump.sql": "high",
       "/phpinfo.php": "medium", "/info.php": "medium", "/server-status": "medium",
       "/adminer.php": "medium", "/_ignition/health-check": "high",
       "/package.json": "low", "/composer.json": "low", "/package-lock.json": "low",
       "/.DS_Store": "low", "/.env.local": "critical", "/.env.production": "critical",
       "/.env.bak": "critical", "/.git/HEAD": "high"}



MAGIC = {"/backup.zip": b"PK\x03\x04", "/db.sql": b"--", "/dump.sql": b"--", "/.DS_Store": b"\x00\x00\x00\x01Bud1",
         "/.git/index": b"DIRC"}
TEXT_OK = [
    ("/.env", re.compile(r"(?m)^[A-Z0-9_]{2,40}\s*=")),
    ("/.git/config", re.compile(r"\[core\]")),
    ("/.git/HEAD", re.compile(r"^(ref:\s|\n)?[0-9a-f]{40}")),
    ("laravel.log", re.compile(r"production\.(ERROR|WARNING|INFO)|\[\d{4}-\d{2}-\d{2}")),
    ("debug.log", re.compile(r"\[\d{4}-\d{2}-\d{2}|ERROR|Exception")),
    ("wp-config.php", re.compile(r"DB_PASSWORD|DB_NAME")),
    ("configuration.php", re.compile(r"\$password|\$host")),
    ("phpinfo", re.compile(r"PHP Version|phpinfo\(\)")),
    ("info.php", re.compile(r"PHP Version|phpinfo\(\)")),
    ("server-status", re.compile(r"Apache Server Status|Server Version:")),
    ("adminer", re.compile(r"Adminer|loginForm|db\(\)")),
    ("_ignition", re.compile(r"can_execute_commands|Ignition")),
    ("package.json", re.compile(r'"name"\s*:')),
    ("composer.json", re.compile(r'"require"|"name"\s*:')),
]
ERROR_PAGE = re.compile(r"403 Forbidden|404 Not Found|Not Found<|Access denied|Forbidden<", re.I)


def looks_real(path, body):
    """True hanya jika isi respons benar-benar artefak yang diklaim path-nya."""
    for m, magic in MAGIC.items():
        if path.startswith(m):
            return body.startswith(magic)
    try:
        t = body[:20000].decode("utf-8", "replace")
    except Exception:
        return False
    if ERROR_PAGE.search(t[:4000]):
        return False
    for key, rx in TEXT_OK:
        if key in path:
            return bool(rx.search(t))
    return False


def sessions():
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept": "*/*"})
    return s


def crtsh(pattern):
    try:
        r = requests.get(f"https://crt.sh/?q={pattern}&output=json", timeout=90,
                         headers={"User-Agent": UA})
        data = r.json()
    except Exception as e:
        print(f"[!] crt.sh gagal: {e}")
        return []
    out = set()
    for e in data:
        for n in str(e.get("name_value", "")).split("\n"):
            n = n.strip().lower().lstrip("*.")
            if n and " " not in n and "@" not in n:
                out.add(n)
    return sorted(out)


def bare_host(host):
    """Buang port supaya DNS resolution jalan (127.0.0.1:8099 -> 127.0.0.1)."""
    if host.startswith("["):
        return host.split("]")[0].lstrip("[")
    if host.count(":") == 1:
        return host.rsplit(":", 1)[0]
    return host


def resolve(host):
    try:
        return socket.gethostbyname(bare_host(host))
    except Exception:
        return None


def fingerprint(sess, url):
    try:
        r = sess.get(url, timeout=10, verify=False)
        body = r.text[:20000]
        tags = [name for name, rx in FP if rx.search(body)]
        srv = r.headers.get("Server", "")
        xp = r.headers.get("X-Powered-By", "")
        return {"status": r.status_code, "server": srv, "powered": xp, "tags": tags,
                "len": len(r.content), "title": (re.search(r"<title>(.*?)</title>", body, re.I | re.S).group(1).strip()[:60]
                                                 if re.search(r"<title>(.*?)</title>", body, re.I | re.S) else "")}
    except Exception as e:
        return {"error": str(e)[:80]}


def scan_host(host, deep_paths=True):
    ip = resolve(host)
    rec = {"host": host, "ip": ip, "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "exposures": [], "fp": None}
    if not ip:
        rec["dead"] = True
        return rec
    sess = sessions()
    base = None
    for scheme in ("https", "http"):
        u = f"{scheme}://{host}"
        fp = fingerprint(sess, u)
        if "error" not in fp:
            base, rec["fp"] = u, fp
            break
    if not base:
        rec["dead"] = True
        return rec
    rec["base"] = base

    st, body = None, b""
    try:
        r0 = sess.get(base + "/__absent_" + hashlib.md5(host.encode()).hexdigest()[:6], timeout=10, verify=False, allow_redirects=False)
        base404 = (r0.status_code, hashlib.md5(r0.content).hexdigest())
    except Exception:
        base404 = (404, "")

    for p in (PATHS if deep_paths else PATHS[:12]):
        try:
            r = sess.get(base + p, timeout=10, verify=False, allow_redirects=False)
        except Exception:
            continue
        sig = hashlib.md5(r.content).hexdigest()
        soft = (r.status_code == base404[0] and sig == base404[1]) or (base404[1] == sig)
        if r.status_code in (200, 206) and not soft and len(r.content) > 16 and looks_real(p, r.content):
            head = r.text[:400].replace("\n", " ")
            rec["exposures"].append({"path": p, "status": r.status_code, "bytes": len(r.content),
                                     "severity": SEV.get(p, "info"), "sample": head})
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-f", "--file")
    ap.add_argument("--tld", default="ac.id", help="domain induk untuk crt.sh (default ac.id)")
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("-o", "--out", default="acid_out")
    ap.add_argument("--workers", type=int, default=10)
    ap.add_argument("--no-deep", action="store_true")
    a = ap.parse_args()

    hosts = []
    if a.file:
        hosts = [l.strip().lower() for l in open(a.file) if l.strip() and not l.startswith("#")]
    if not hosts:
        print(f"[*] discovery crt.sh %.{a.tld} ...")
        hosts = crtsh(f"%.{a.tld}")
        hosts = [h for h in hosts if h.endswith(a.tld)]
        print(f"[*] {len(hosts)} host unik dari CT")
    hosts = hosts[: a.limit]
    os.makedirs(a.out, exist_ok=True)
    jl = open(f"{a.out}/results.jsonl", "w")
    summary = {"tld": a.tld, "scanned": 0, "alive": 0, "with_exposure": 0, "by_sev": {}, "top": []}

    def work(h):
        return scan_host(h, deep_paths=not a.no_deep)

    with cf.ThreadPoolExecutor(max_workers=a.workers) as ex:
        for rec in ex.map(work, hosts):
            summary["scanned"] += 1
            jl.write(json.dumps(rec) + "\n")
            jl.flush()
            if rec.get("base"):
                summary["alive"] += 1
            if rec["exposures"]:
                summary["with_exposure"] += 1
                for e in rec["exposures"]:
                    summary["by_sev"][e["severity"]] = summary["by_sev"].get(e["severity"], 0) + 1
                summary["top"].append({"host": rec["host"], "paths": [e["path"] for e in rec["exposures"]],
                                       "sev": [e["severity"] for e in rec["exposures"]]})
                print(f"[!] {rec['host']} -> " + ", ".join(f"{e['path']}({e['severity']})" for e in rec["exposures"]))
            else:
                print(f"[.] {rec['host']} {'alive' if rec.get('base') else 'dead'}")
    jl.close()
    json.dump(summary, open(f"{a.out}/summary.json", "w"), indent=1)
    print(json.dumps({k: v for k, v in summary.items() if k != "top"}, indent=1))
    print(f"-> {a.out}/results.jsonl  {a.out}/summary.json")


if __name__ == "__main__":
    main()
