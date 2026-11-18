#!/usr/bin/env python3
"""
cfinder.py — cPanel / WHM / Webmail port discovery + fingerprint untuk daftar domain massal.

Kenapa terpisah dari scanner port generik:
  - cPanel punya 6 port khas: 2082 (cpanel http), 2083 (cpanel https),
    2086 (whm http), 2087 (whm https), 2095 (webmail http), 2096 (webmail https)
  - "port terbuka" bukan bukti. Harus ada signature cpsrvd: header Server: cpsrvd,
    body mengandung "cPanel" / "WHM Login" / "Webmail", atau redirect ke /cpsessNNNN.
  - tiap host di-fingerprint dengan HTTP/HTTPS sesuai port, tanpa follow redirect.

Output:
  cp_hosts.jsonl  satu baris per host: domain, ip, port, scheme, kind (cpanel|whm|webmail),
                  server_header, title, status, redis_redirect, https_ok
  cp_hosts.txt    host|port|scheme|kind  → feed langsung ke CP-Bypass / cve-2026-41940

Contoh:
  python3 cfinder.py -f $HOME/hacktools/acid_domains.txt --limit 200 -o out
  python3 cfinder.py -d kampus.ac.id -o out
  python3 cfinder.py -f cp_hosts.txt --ports 2087,2086 --workers 20
"""
from __future__ import annotations

import argparse
import json
import os
import re
import socket
import ssl
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    import requests
    requests.packages.urllib3.disable_warnings()
except ImportError:
    sys.exit("pip install requests")

PORTS = {
    2082: ("http", "cpanel"),
    2083: ("https", "cpanel"),
    2086: ("http", "whm"),
    2087: ("https", "whm"),
    2095: ("http", "webmail"),
    2096: ("https", "webmail"),
}

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"

SIG = {
    "whm": re.compile(r"(WHM Login|WebHost Manager|whostmgr|WHM\s*&?\s*cPanel)", re.I),
    "cpanel": re.compile(r"(cPanel Login|cPanel\s*&?|cpanel\.|cpuser|/cpsess\d+)", re.I),
    "webmail": re.compile(r"(Webmail Login|RoundCube|Horde|SquirrelMail|cpanel\.webmail)", re.I),
}
SIG_ANY = re.compile(r"(cPanel|WHM|WebHost Manager|RoundCube|Horde|SquirrelMail)", re.I)
CPSESS = re.compile(r"/cpsess\d+")


def resolve(host: str) -> str | None:
    try:
        return socket.gethostbyname(host)
    except Exception:
        return None


def port_open(ip: str, port: int, timeout: float) -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        return s.connect_ex((ip, port)) == 0
    finally:
        s.close()


def tls_ok(ip: str, port: int, timeout: float) -> tuple[bool, str | None]:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        with socket.create_connection((ip, port), timeout=timeout) as raw:
            with ctx.wrap_socket(raw) as ss:
                cert = ss.getpeercert()
                cn = None
                for rdn in (cert or {}).get("subject", ()):  # type: ignore[union-attr]
                    for k, v in rdn:
                        if k == "commonName":
                            cn = v
                return True, cn
    except Exception:
        return False, None


def bad_ip(ip: str) -> bool:
    """Host yang resolve ke loopback/private bukan server nyata (A record salah isi).
    Ini sumber false positive nyata: mail.amikjombang.ac.id -> 127.0.0.1."""
    try:
        parts = [int(x) for x in ip.split(".")]
    except Exception:
        return True
    if len(parts) != 4:
        return True
    a, b = parts[0], parts[1]
    return (a == 127 or a == 10 or a == 0 or a >= 224
            or (a == 192 and b == 168) or (a == 172 and 16 <= b <= 31)
            or (a == 169 and b == 254))


def resolve_origin(host: str, port: int, timeout: float) -> str | None:
    """cpsrvd 307 ke hostname kanonik asli saat Host header salah.
    Ini yang membuka jalur bypass Cloudflare: request lewat domain .ac.id
    (diblok CF) menyebut origin hostname (mis. xxx.iixcp.rumahweb.net),
    dan origin itu bisa dihubungi langsung tanpa CF."""
    scheme = PORTS.get(port, ("https", ""))[0]
    url = f"{scheme}://{host}:{port}/openid_connect/cpanelid"
    try:
        r = requests.get(url, timeout=timeout, verify=False, allow_redirects=False,
                         headers={"User-Agent": UA, "Connection": "close"})
    except Exception:
        return None
    loc = r.headers.get("Location", "")
    m = re.match(r"^https?://([^:/]+)", loc)
    if not m:
        m = re.search(r"//([^:/\s]+)", r.text[:2000] or "")
    if not m:
        return None
    cand = m.group(1).strip().lower().strip(';,. ')
    if cand == host.lower() or not cand:
        return None
    # CF challenge / halaman verifikasi bukan origin asli
    if re.search(r"(cloudflare\.com|challenges\.|akamai|captcha|jsdelivr)", cand):
        return None
    if not re.match(r"^[a-z0-9.-]+\.[a-z]{2,}$", cand):
        return None
    return cand


def probe(host: str, ip: str, port: int, timeout: float) -> dict | None:
    scheme, kind = PORTS[port]
    url = f"{scheme}://{host}:{port}/"
    try:
        r = requests.get(url, timeout=timeout, verify=False, allow_redirects=False,
                         headers={"User-Agent": UA, "Connection": "close"})
    except Exception as e:
        return {"domain": host, "ip": ip, "port": port, "scheme": scheme, "kind": kind,
                "status": 0, "error": type(e).__name__, "hit": False}

    body = r.text[:200000] if r.text else ""
    srv = r.headers.get("Server", "")
    loc = r.headers.get("Location", "")
    title = ""
    m = re.search(r"<title[^>]*>(.*?)</title>", body, re.I | re.S)
    if m:
        title = re.sub(r"\s+", " ", m.group(1)).strip()[:120]

    sig_hit = bool(SIG[kind].search(body) or SIG_ANY.search(body) or SIG_ANY.search(title))
    cpsrvd = "cpsrvd" in srv.lower()
    cpsess = bool(CPSESS.search(loc)) or bool(CPSESS.search(body[:5000]))
    hit = bool(sig_hit or cpsrvd or cpsess)

    return {
        "domain": host, "ip": ip, "port": port, "scheme": scheme, "kind": kind,
        "status": r.status_code, "server": srv, "title": title,
        "location": loc[:200], "cpsess": cpsess, "sig": sig_hit, "cpsrvd": cpsrvd,
        "hit": hit,
    }


def scan_host(host: str, ports: list[int], timeout: float) -> list[dict]:
    ip = resolve(host)
    if not ip:
        return [{"domain": host, "ip": None, "hit": False, "error": "dns_fail"}]
    if bad_ip(ip):
        return [{"domain": host, "ip": ip, "hit": False, "error": "ip_private_or_loopback"}]
    out = []
    for port in ports:
        if not port_open(ip, port, max(1.5, timeout / 2)):
            out.append({"domain": host, "ip": ip, "port": port,
                        "scheme": PORTS[port][0], "kind": PORTS[port][1],
                        "hit": False, "error": "closed"})
            continue
        res = probe(host, ip, port, timeout)
        if res is None:
            continue
        if PORTS[port][0] == "https" and res.get("status"):
            ok, cn = tls_ok(ip, port, timeout)
            res["tls_ok"], res["tls_cn"] = ok, cn
            if cn and cn != host and res.get("status") in (0, None):
                pass
        out.append(res)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("-f", "--file", help="file daftar domain (satu per baris)")
    ap.add_argument("-d", "--domain", action="append", default=[], help="domain tunggal (bisa diulang)")
    ap.add_argument("-o", "--out", default="cp_out", help="direktori output")
    ap.add_argument("--ports", default="2082,2083,2086,2087,2095,2096")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--timeout", type=float, default=6.0)
    ap.add_argument("--all", action="store_true", help="tulis semua hasil probe, bukan hanya hit")
    ap.add_argument("--origin", action="store_true",
                    help="resolve hostname kanonik cpsrvd (bypass Cloudflare) untuk tiap hit")
    args = ap.parse_args()

    hosts: list[str] = list(args.domain)
    if args.file:
        for line in open(args.file, encoding="utf-8", errors="ignore"):
            line = line.strip().lower()
            if not line or line.startswith("#"):
                continue
            line = re.sub(r"^https?://", "", line).split("/")[0].split(":")[0]
            hosts.append(line)
    hosts = list(dict.fromkeys(hosts))
    if args.limit:
        hosts = hosts[:args.limit]
    if not hosts:
        ap.error("tidak ada target; pakai -f atau -d")

    ports = [int(p) for p in args.ports.split(",") if p.strip()]
    for p in ports:
        if p not in PORTS:
            print(f"[!] port {p} tidak dikenal cPanel set; tetap diprobe sebagai http/https? -> dilewati", file=sys.stderr)
    ports = [p for p in ports if p in PORTS]

    os.makedirs(args.out, exist_ok=True)
    jsonl = open(os.path.join(args.out, "cp_hosts.jsonl"), "w", encoding="utf-8")
    txt = open(os.path.join(args.out, "cp_hosts.txt"), "w", encoding="utf-8")

    hits, alive, done = 0, 0, 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(scan_host, h, ports, args.timeout): h for h in hosts}
        for fut in as_completed(futs):
            host = futs[fut]
            done += 1
            try:
                results = fut.result()
            except Exception as e:
                print(f"[x] {host}: {type(e).__name__}", file=sys.stderr)
                continue
            host_alive = any(r.get("status") for r in results)
            if host_alive:
                alive += 1
            for r in results:
                if r.get("hit") or args.all:
                    jsonl.write(json.dumps(r) + "\n")
                    jsonl.flush()
                if r.get("hit"):
                    hits += 1
                    origin = resolve_origin(r["domain"], r["port"], args.timeout) if args.origin else None
                    if origin:
                        r["origin"] = origin
                        jsonl.write(json.dumps(r) + "\n")
                    line = f"{r['domain']}|{r['port']}|{r['scheme']}|{r['kind']}"
                    txt.write(line + "\n")
                    if origin:
                        txt.write(f"{origin}|{r['port']}|{r['scheme']}|{r['kind']}|origin\n")
                        txt.flush()
                    jsonl.flush()
                    print(f"[+] {r['domain']:<40} :{r['port']} {r['kind']:<8} {r.get('status')} "
                          f"{(r.get('server') or '')[:20]} {r.get('title','')[:50]}"
                          + (f"  origin={origin}" if origin else ""))
            if done % 25 == 0:
                print(f"[*] {done}/{len(hosts)} host, alive={alive}, cpanel_hits={hits}", file=sys.stderr)

    jsonl.close()
    txt.close()
    summary = {"hosts_scanned": len(hosts), "alive": alive, "cpanel_found": hits,
               "ports": ports, "out": os.path.abspath(args.out)}
    with open(os.path.join(args.out, "summary.json"), "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2)
    print(f"\n[done] scanned={len(hosts)} alive={alive} cpanel={hits} -> {args.out}/cp_hosts.txt")
    return 0


if __name__ == "__main__":
    sys.exit(main())
