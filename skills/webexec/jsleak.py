#!/usr/bin/env python3
"""
jsleak.py — harvest secrets, endpoints and wallet material from JS bundles.

Runs entirely on fetched text, so it works on sourcemaps, inline <script>,
and downloaded bundles. Never prints secret values: fingerprint + location only.

Also detects self-hosted wallet/key material served to browsers:
  - hardcoded BIP39 mnemonics / hex private keys
  - keystore JSON (encrypted, but password often in the same bundle)
  - RPC/API keys that give read (and sometimes spend) access

usage:
  python3 jsleak.py https://target.com
  python3 jsleak.py https://target.com --max 40 --json out.json
  python3 jsleak.py --file bundle.js --name app.js
"""
from __future__ import annotations

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib.webutil import (Client, fp, jsonout, norm_url, redact, save_raw,  # noqa: E402
                         save_secret, table)

PATTERNS = [  # (name, regex) — group(1) is the secret when present
    ("private_key", r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]{10,4000}?-----END [A-Z ]*PRIVATE KEY-----"),
    ("eth_privkey", r"(?i)(?:privateKey|private_key|PRIVKEY|secretKey)\s*[:=]\s*[\"']?(?:0x)?([a-f0-9]{64})"),
    ("eth_privkey_bare", r"(?i)\b0x[a-f0-9]{64}\b"),
    ("mnemonic", r"(?i)(?:mnemonic|seedPhrase|seed_phrase|recoveryPhrase)\s*[:=]\s*[\"'`]((?:[a-z]{3,8}\s){11,23}[a-z]{3,8})"),
    ("keystore", r'"crypto"\s*:\s*\{[\s\S]{40,4000}?"cipher"\s*:\s*"aes-128-ctr"'),
    ("aws_ak", r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    ("aws_secret", r"(?i)aws_?secret_?access_?key[^a-z0-9]{0,5}([A-Za-z0-9/+=]{40})"),
    ("huawei_ak", r"\bLTAI[A-Za-z0-9]{12,}\b"),
    ("gcp", r'"type"\s*:\s*"service_account"'),
    ("github_pat", r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    ("slack", r"\bxox[baprs]-[A-Za-z0-9\-]{10,}\b"),
    ("stripe_live", r"\bsk_live_[A-Za-z0-9]{10,}\b"),
    ("stripe_pub", r"\bpk_live_[A-Za-z0-9]{10,}\b"),
    ("google_api", r"\bAIza[0-9A-Za-z_\-]{35}\b"),
    ("firebase_url", r"https://[a-z0-9\-]+\.firebaseio\.com"),
    ("infura", r"https://[a-z]+\.infura\.io/v3/([a-f0-9]{32})"),
    ("alchemy", r"https://[a-z\-]+\.g\.alchemy\.com/v2/([A-Za-z0-9_\-]{20,})"),
    ("quicknode", r"https://[a-z0-9\-]+\.quiknode\.pro/[A-Za-z0-9]{20,}"),
    ("jwt", r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\b"),
    ("openai", r"\bsk-[A-Za-z0-9]{32,}\b"),
    ("sendgrid", r"\bSG\.[A-Za-z0-9_\-]{16,}\.[A-Za-z0-9_\-]{16,}\b"),
    ("telegram", r"\b\d{8,10}:AA[A-Za-z0-9_\-]{30,}\b"),
    ("db_url", r"(?i)(?:mysql|postgres|postgresql|mongodb(?:\+srv)?|redis|amqp)://[^\s\"'<>]{8,200}"),
    ("basic_auth_url", r"(?i)https?://[^\s/:@\"']+:[^\s/@\"']{4,}@[^\s\"']+"),
    ("hardcoded_pass", r"(?i)(?:password|passwd|pwd)\s*[:=]\s*[\"']([^\"'\s]{6,64})[\"']"),
    ("admin_path", r"(?i)[\"'](/(?:admin|internal|private|debug|staging|dev|_hidden)[a-z0-9_\-/]*)[\"']"),
]

ENDPOINT_RE = re.compile(r"[\"'](/(?:api|v[0-9]|graphql|rest|internal|admin|upload|user|auth)[a-zA-Z0-9_\-/.]{0,80})[\"']")


def scan_text(text: str, where: str):
    secrets, endpoints = [], set()
    for name, pat in PATTERNS:
        for m in re.finditer(pat, text, re.M):  # re.M: mnemonic spans wrapped lines
            val = m.group(1) if m.groups() else m.group(0)
            if not val or "EXAMPLE" in val or val.lower().startswith(("xxx", "your_")):
                continue
            line = text[:m.start()].count("\n") + 1
            secrets.append({"type": name, "where": f"{where}:{line}",
                            "fingerprint": fp(val), "length": len(val)})
            if name in ("eth_privkey", "eth_privkey_bare", "mnemonic", "private_key", "keystore",
                        "aws_secret", "stripe_live", "openai"):
                fn = f"{re.sub(r'[^a-z0-9.]', '_', where)}_{name}_{fp(val)}.txt"
                p = save_secret(fn, val)
                secrets[-1]["stored_at"] = p.replace(os.path.expanduser("~"), "~")
    for m in ENDPOINT_RE.finditer(text):
        endpoints.add(m.group(1))
    return secrets, endpoints


def collect_sources(client: Client, base: str, max_js: int):
    """Inline scripts + external bundles + sourcemaps."""
    sources = {}
    r = client.get(base + "/")
    html = r.body
    sources["<inline:root>"] = html
    urls = []
    for m in re.finditer(r'<script[^>]+src=["\']([^"\']+)["\']', html, re.I):
        urls.append(m.group(1))
    for m in re.finditer(r'(?:src|href)=["\']([^"\']+\.js(?:\?[^"\']*)?)["\']', html, re.I):
        urls.append(m.group(1))
    for m in re.finditer(r'["\'](/_next/static/[^"\']+\.js)["\']', html):
        urls.append(m.group(1))
    seen, queue = set(), urls[:]
    while queue and len(seen) < max_js:
        u = queue.pop(0)
        full = u if u.startswith("http") else base + ("" if u.startswith("/") else "/") + u
        if full in seen:
            continue
        seen.add(full)
        b = client.get(full)
        if not b.ok or b.size < 50:
            continue
        sources[full] = b.body
        # amazon-style chunk loader gives more bundle names
        for m in re.finditer(r'["\']([a-zA-Z0-9_\-./]+\.js)["\']', b.body[:200000]):
            cand = m.group(1)
            if cand not in seen:
                queue.append(cand)
    return sources


def run(target=None, file=None, name="local.js", max_bundles=30, proxy=None, tor=False,
        text=None, client=None):
    """Library entry point. Returns result dict; secrets carry fingerprint + stored path."""
    result = {"target": target, "sources": [], "secrets": [], "endpoints": [], "summary": {}}
    if text is not None or file:
        body = text if text is not None else open(file, "r", errors="ignore").read()
        s, e = scan_text(body, name)
        result["sources"] = [name]
        result["secrets"], result["endpoints"] = s, sorted(e)
    else:
        if not target:
            raise ValueError("give a target URL or file/text")
        base = norm_url(target)
        client = client or Client(timeout=15, proxy=proxy or ("socks5h://127.0.0.1:9050" if tor else None))
        sources = collect_sources(client, base, max_bundles)
        all_ep = set()
        for name, text in sources.items():
            save_raw(f"js_{re.sub(r'[^a-zA-Z0-9.]', '_', name)[-60:]}", text, base)
            s, e = scan_text(text, name)
            result["secrets"].extend(s)
            all_ep |= e
        result["sources"] = list(sources.keys())
        result["endpoints"] = sorted(all_ep)

    # dedupe by fingerprint+type
    seen, ded = set(), []
    for s in result["secrets"]:
        k = (s["type"], s["fingerprint"])
        if k in seen:
            continue
        seen.add(k)
        ded.append(s)
    result["secrets"] = ded
    result["summary"] = {"bundles": len(result["sources"]), "secrets": len(ded),
                         "endpoints": len(result["endpoints"]),
                         "wallet_material": sum(1 for s in ded if s["type"] in
                                                ("eth_privkey", "eth_privkey_bare", "mnemonic", "keystore"))}
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("target", nargs="?")
    ap.add_argument("--file", default=None)
    ap.add_argument("--name", default="local.js")
    ap.add_argument("--max", type=int, default=30)
    ap.add_argument("--proxy", default=None)
    ap.add_argument("--tor", action="store_true")
    ap.add_argument("--json", default=None)
    a = ap.parse_args()
    if not a.target and not a.file:
        ap.error("give a target URL or --file")
    result = run(a.target, a.file, a.name, a.max, a.proxy, a.tor)
    ded = result["secrets"]
    print(table([[s["type"], s["where"], s["fingerprint"], s.get("stored_at", "-")]
                 for s in ded], ["TYPE", "WHERE", "FP", "STORED"]), file=sys.stderr)
    out = jsonout(result)
    print(out)
    if a.json:
        open(a.json, "w").write(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
