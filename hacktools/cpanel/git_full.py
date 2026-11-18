#!/usr/bin/env python3
"""Ambil semua blob dari .git target (index lokal) -> rekonstruksi source lengkap."""
import os, sys, zlib, subprocess, concurrent.futures as cf, requests

BASE = "https://siak.husadagemilang.ac.id"
OUT = "$HOME/hacktools/siak_src"
REPO = "/tmp/siakrepo"
os.makedirs(OUT, exist_ok=True)

entries = []
out = subprocess.run(["git", "-C", REPO, "ls-files", "-s"], capture_output=True, text=True).stdout
for line in out.splitlines():
    meta, path = line.split("\t", 1)
    mode, sha, stage = meta.split()
    entries.append((sha, path))


def fetch(sha):
    dest = os.path.join(OUT, sha)
    if os.path.exists(dest):
        return "cached"
    try:
        r = requests.get(f"{BASE}/.git/objects/{sha[:2]}/{sha[2:]}", timeout=25)
        if r.status_code != 200:
            return "miss"
        raw = zlib.decompress(r.content)
        body = raw.split(b"\x00", 1)[1]
        open(dest, "wb").write(body)
        return "ok"
    except Exception as e:
        return f"err:{type(e).__name__}"


stats = {}
with cf.ThreadPoolExecutor(24) as ex:
    for res in ex.map(fetch, [s for s, _ in entries]):
        stats[res] = stats.get(res, 0) + 1
print(stats)

# susun tree
for sha, path in entries:
    src = os.path.join(OUT, sha)
    if not os.path.exists(src):
        continue
    dst = os.path.join(OUT, "tree", path)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if not os.path.exists(dst):
        os.link(src, dst)
print("tree ready:", len(entries))
