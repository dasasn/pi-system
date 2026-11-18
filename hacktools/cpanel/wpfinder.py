#!/usr/bin/env python3
"""
wpfinder.py — deteksi WordPress nyata pada daftar domain massal.

Aturan bukti (bukan asal "200 OK"):
  - butuh >= 2 sinyal independen: wp-content/wp-includes di HTML,
    <meta name="generator" content="WordPress X">, /wp-login.php dengan form
    user_login/wp-submit, /wp-json/ memuat "namespaces"/"wp/v2".
  - halaman 404/soft-404 yang menyebut kata "wordpress" TIDAK dihitung.

Yang dicatat per target: versi WP, URL final (setelah redirect), status
wp-login, XML-RPC aktif/tidak, user yang bocor lewat /wp-json/wp/v2/users
atau ?author=N, plugin yang terlihat di path /wp-content/plugins/<slug>/.

Output:
  wp_hosts.jsonl   satu objek per target WP
  wp_hosts.txt     url|version|users|xmlrpc  (feed ke wpscan / wpstorm)

Contoh:
  python3 wpfinder.py -f $HOME/hacktools/acid_domains.txt --limit 300 -o wp_out
  python3 wpfinder.py -f domains.txt --workers 32
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    import requests
    requests.packages.urllib3.disable_warnings()
except ImportError:
    sys.exit("pip install requests")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

RE_GEN = re.compile(r'<meta[^>]+name=["\']generator["\'][^>]+content=["\']WordPress\s*([\d.]+)?', re.I)
RE_GEN2 = re.compile(r'content=["\']WordPress\s*([\d.]+)?["\'][^>]+name=["\']generator', re.I)
RE_WPC = re.compile(r"/wp-content/|/wp-includes/", re.I)
RE_PLUGIN = re.compile(r"/wp-content/plugins/([a-z0-9._-]{3,40})/", re.I)
RE_LOGIN = re.compile(r'(user_login|wp-submit|name=["\']log["\'])', re.I)
RE_README_VER = re.compile(r"Version\s+([\d.]+)", re.I)


def get(sess, url, timeout, allow_redirects=True, **kw):
    try:
        return sess.get(url, timeout=timeout, verify=False,
                        allow_redirects=allow_redirects,
                        headers={"User-Agent": UA, "Connection": "close"}, **kw)
    except Exception:
        return None


def check_site(host: str, timeout: float) -> dict:
    sess = requests.Session()
    rec = {"domain": host, "wp": False, "signals": [], "version": None,
           "final_url": None, "wp_login": None, "xmlrpc": None,
           "users": [], "plugins": [], "status": None}

    root = None
    for scheme in ("https", "http"):
        base = f"{scheme}://{host}/"
        r = get(sess, base, timeout)
        if r is not None and r.status_code:
            root, rec["final_url"] = r, r.url
            rec["status"] = r.status_code
            break
    if root is None:
        rec["error"] = "unreachable"
        return rec

    body = root.text[:300000] if root.text else ""
    if RE_WPC.search(body):
        rec["signals"].append("wp-content")
    m = RE_GEN.search(body) or RE_GEN2.search(body)
    if m:
        rec["signals"].append("generator")
        if m.group(1):
            rec["version"] = m.group(1)
    pl = {x.lower() for x in RE_PLUGIN.findall(body)}
    if pl:
        rec["plugins"] = sorted(pl)[:25]

    # wp-login.php: harus ada form login sungguhan
    base = rec["final_url"].rstrip("/")
    r = get(sess, base + "/wp-login.php", timeout)
    if r is not None and r.status_code == 200 and RE_LOGIN.search(r.text[:20000]):
        rec["signals"].append("wp-login")
        rec["wp_login"] = base + "/wp-login.php"

    # wp-json: REST API khas WP
    r = get(sess, base + "/wp-json/", timeout)
    if r is not None and r.status_code == 200:
        t = r.text[:20000]
        if '"namespaces"' in t or 'wp/v2' in t:
            rec["signals"].append("wp-json")
            try:
                j = r.json()
                rec["wp_name"] = (j.get("name") or "")[:80]
                rec["wp_desc"] = (j.get("description") or "")[:120]
            except Exception:
                pass

    # user enumeration (bukti nyata, bukan tebakan)
    r = get(sess, base + "/wp-json/wp/v2/users?per_page=20", timeout)
    if r is not None and r.status_code == 200:
        try:
            j = r.json()
            if isinstance(j, list):
                rec["users"] = [u.get("slug") for u in j if isinstance(u, dict) and u.get("slug")][:20]
        except Exception:
            pass
    if not rec["users"]:
        for n in (1, 2):
            r = get(sess, f"{base}/?author={n}", timeout)
            if r is not None and r.history:
                m = re.search(r"/author/([a-z0-9._-]+)/", r.url, re.I)
                if m:
                    rec["users"].append(m.group(1))

    # XML-RPC (sering jadi jalur bruteforce/amplifikasi)
    r = get(sess, base + "/xmlrpc.php", timeout)
    if r is not None:
        if r.status_code == 405 or "XML-RPC server accepts POST requests only" in (r.text or ""):
            rec["xmlrpc"] = True
        elif r.status_code == 200 and "xml" in r.headers.get("Content-Type", "").lower():
            rec["xmlrpc"] = True
        else:
            rec["xmlrpc"] = False

    # versi cadangan dari readme.html
    if not rec["version"]:
        r = get(sess, base + "/readme.html", timeout)
        if r is not None and r.status_code == 200:
            mm = RE_README_VER.search(r.text[:20000])
            if mm and mm.group(1).startswith(("4.", "5.", "6.")):
                rec["version"] = mm.group(1)
                rec["signals"].append("readme")

    rec["wp"] = len([s for s in rec["signals"] if s in
                     ("wp-content", "generator", "wp-login", "wp-json")]) >= 2
    return rec


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("-f", "--file")
    ap.add_argument("-d", "--domain", action="append", default=[])
    ap.add_argument("-o", "--out", default="wp_out")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=24)
    ap.add_argument("--timeout", type=float, default=10.0)
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()

    hosts = [h.strip().lower() for h in args.domain if h.strip()]
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
        ap.error("butuh -f atau -d")

    os.makedirs(args.out, exist_ok=True)
    jl = open(os.path.join(args.out, "wp_hosts.jsonl"), "w", encoding="utf-8")
    tx = open(os.path.join(args.out, "wp_hosts.txt"), "w", encoding="utf-8")

    found, done = 0, 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(check_site, h, args.timeout): h for h in hosts}
        for fut in as_completed(futs):
            h = futs[fut]
            done += 1
            try:
                r = fut.result()
            except Exception as e:
                print(f"[x] {h}: {type(e).__name__}", file=sys.stderr)
                continue
            if r.get("wp") or args.all:
                jl.write(json.dumps(r) + "\n")
                jl.flush()
            if r.get("wp"):
                found += 1
                ver = r.get("version") or "?"
                users = ",".join(r.get("users") or []) or "-"
                line = f"{r.get('final_url') or h}|{ver}|{users}|xmlrpc={r.get('xmlrpc')}"
                tx.write(line + "\n")
                tx.flush()
                print(f"[+] {h:<42} wp={ver:<8} users={users[:40]:<40} "
                      f"xmlrpc={r.get('xmlrpc')} sig={','.join(r['signals'])}")
            if done % 50 == 0:
                print(f"[*] {done}/{len(hosts)} wp={found}", file=sys.stderr)

    jl.close()
    tx.close()
    with open(os.path.join(args.out, "summary.json"), "w", encoding="utf-8") as fh:
        json.dump({"scanned": len(hosts), "wordpress": found,
                   "out": os.path.abspath(args.out)}, fh, indent=2)
    print(f"\n[done] scanned={len(hosts)} wordpress={found} -> {args.out}/wp_hosts.txt")
    return 0


if __name__ == "__main__":
    sys.exit(main())
