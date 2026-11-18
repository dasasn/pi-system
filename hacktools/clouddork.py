#!/usr/bin/env python3
"""
clouddork.py — cari kredensial cloud (AWS/GCP/Azure/DO/CF/Hetzner) yang bocor di internet,
lalu VALIDASI ke API aslinya (bukan cuma regex).

Sumber:
  --bing "query"     hasil pencarian Bing HTML (tanpa API key)
  --gists "query"    pencarian gist GitHub + ambil isi mentahnya
  -u URL             scan satu URL langsung
  -d DIR / -f FILE   scan lokal (hasil git-dumper, dump VPS, dll)

Contoh:
  clouddork.py --bing '"AKIA" "aws_secret_access_key"' --pages 2
  clouddork.py --gists AKIA --max 20
  clouddork.py -d /tmp/vps_dump

Output: <out>/cloud_keys.jsonl (mode 600), ringkasan di stdout (nilai di-mask).
"""
import argparse
import base64
import hashlib
import hmac
import json
import os
import re
import sys
import time
import urllib.parse
import uuid

import requests

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/203.0.113.10 Safari/537.36"
T = 10

PATTERNS = [
    ("aws_key_id", re.compile(r"\b((?:AKIA|ASIA|AGPA|AIDA|AROA|ANPA|ANVA|AIPA)[0-9A-Z]{16})\b")),
    ("aws_secret", re.compile(r"(?i)aws[_\- ]?(?:secret|private)[_\- ]?(?:access)?[_\- ]?key\W{0,6}([A-Za-z0-9/+=]{40})")),
    ("gcp_api_key", re.compile(r"\b(AIza[0-9A-Za-z_-]{35})\b")),
    ("gcp_sa_json", re.compile(r'"type"\s*:\s*"service_account"')),
    ("gcp_private_key", re.compile(r'"private_key"\s*:\s*"-----BEGIN PRIVATE KEY-----')),
    ("azure_account_key", re.compile(r"AccountKey=([A-Za-z0-9+/=]{40,90})")),
    ("azure_conn", re.compile(r"DefaultEndpointsProtocol=https?;AccountName=([A-Za-z0-9]{3,24});AccountKey=")),
    ("do_token", re.compile(r"\b(dop_v1_[a-f0-9]{64})\b")),
    ("cf_token", re.compile(r"(?i)(?:cloudflare|CF)[_\- ]?(?:api)?[_\- ]?(?:token|key)\W{0,6}([A-Za-z0-9_-]{40})")),
    ("hetzner_token", re.compile(r"(?i)HCLOUD_TOKEN\W{0,6}([A-Za-z0-9]{64})")),
    ("linode_token", re.compile(r"(?i)LINODE_TOKEN\W{0,6}([a-f0-9]{64})")),
    ("vultr_key", re.compile(r"(?i)VULTR[_\- ]?API[_\- ]?KEY\W{0,6}([A-Za-z0-9]{20,40})")),
]


# ---------- validasi ----------
def aws_sts(ak, sk, region="us-east-1", token=None):
    host = "sts.amazonaws.com"
    amzdate = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    datestamp = amzdate[:8]
    body = "Action=GetCallerIdentity&Version=2011-06-15"
    ph = hashlib.sha256(body.encode()).hexdigest()
    hdrs = f"content-type:application/x-www-form-urlencoded\nhost:{host}\nx-amz-date:{amzdate}\n"
    if token:
        hdrs += f"x-amz-security-token:{token}\n"
    sh = hashlib.sha256(hdrs.encode()).hexdigest()
    creq = f"POST\n/\n\n{hdrs}\n{hdrs.split(chr(10))[0].split(':')[1]}\n{ph}"
    # canonical request sederhana: host + content-type + x-amz-date
    creq = ("POST\n/\n\n"
            "content-type:application/x-www-form-urlencoded\nhost:" + host +
            "\nx-amz-date:" + amzdate + "\n\n"
            "content-type;host;x-amz-date\n" + ph)
    creq = ("POST\n/\n\n"
            "content-type:application/x-www-form-urlencoded\nhost:" + host + "\nx-amz-date:" + amzdate + "\n\n"
            "content-type;host;x-amz-date\n" + ph)
    sc = hashlib.sha256(creq.encode()).hexdigest()
    scope = f"{datestamp}/{region}/sts/aws4_request"
    sts = f"AWS4-HMAC-SHA256\n{amzdate}\n{scope}\n{sc}"
    k = ("AWS4" + sk).encode()
    for part in (datestamp, region, "sts", "aws4_request"):
        k = hmac.new(k, part.encode(), hashlib.sha256).digest()
    sig = hmac.new(k, sts.encode(), hashlib.sha256).hexdigest()
    auth = (f"AWS4-HMAC-SHA256 Credential={ak}/{scope}, "
            f"SignedHeaders=content-type;host;x-amz-date, Signature={sig}")
    try:
        r = requests.post(f"https://{host}/", data=body, timeout=T, headers={
            "Content-Type": "application/x-www-form-urlencoded", "Host": host,
            "x-amz-date": amzdate, "Authorization": auth,
            **({"x-amz-security-token": token} if token else {})})
        if r.status_code == 200 and "GetCallerIdentityResult" in r.text:
            who = re.search(r"<Arn>([^<]+)</Arn>", r.text)
            return "VALID", (who.group(1) if who else "sts ok")
        if "InvalidClientTokenId" in r.text:
            return "INVALID", "InvalidClientTokenId"
        return f"HTTP {r.status_code}", r.text[:100]
    except Exception as e:
        return "ERROR", str(e)[:100]


GCP_SERVICES = [
    ("maps_geocode", "GET", "https://maps.googleapis.com/maps/api/geocode/json", {"address": "Jakarta"}),
    ("youtube_v3", "GET", "https://www.googleapis.com/youtube/v3/search",
     {"part": "snippet", "q": "test", "maxResults": "1"}),
    ("translate_v2", "GET", "https://translation.googleapis.com/language/translate/v2",
     {"q": "hi", "target": "id"}),
    ("identitytoolkit", "GET", "https://identitytoolkit.googleapis.com/v1/projects", {}),
    ("safe_browsing", "POST", "https://safebrowsing.googleapis.com/v4/threatMatches:find", None),
]


def gcp_probe(key):
    """Cek key GCP ke banyak layanan. Google sering balas HTTP 200 walau isinya
    REQUEST_DENIED, jadi status WAJIB dibaca dari body."""
    live, denied, invalid = [], 0, 0
    for name, method, url, params in GCP_SERVICES:
        p = dict(params or {})
        p["key"] = key
        try:
            if name == "safe_browsing":
                r = requests.post(url, params=p, json={"client": {"clientId": "probe", "clientVersion": "1"},
                                                       "threatInfo": {"threatTypes": ["MALWARE"],
                                                                       "platformTypes": ["ANY_PLATFORM"],
                                                                       "threatEntryTypes": ["URL"],
                                                                       "threatEntries": [{"url": "http://example.com"}]}},
                                  headers={"User-Agent": UA}, timeout=T)
                if r.status_code == 200:
                    live.append(name)
                continue
            r = requests.request(method, url, params=p, headers={"User-Agent": UA}, timeout=T)
            body = r.text
            try:
                j = r.json()
            except Exception:
                j = {}
            if r.status_code == 200:
                if name == "maps_geocode":
                    if j.get("status") == "OK" and j.get("results"):
                        live.append(name)
                    elif j.get("status") == "REQUEST_DENIED" or "not authorized" in body:
                        denied += 1
                    elif "API key not valid" in body or j.get("error", {}).get("status") == "INVALID_ARGUMENT":
                        invalid += 1
                elif name == "youtube_v3":
                    (live if "items" in j else denied).__class__  # noop
                    if "items" in j:
                        live.append(name)
                    else:
                        denied += 1
                elif name == "translate_v2":
                    if j.get("data"):
                        live.append(name)
                    else:
                        denied += 1
                elif name == "identitytoolkit":
                    if j.get("projectId"):
                        live.append(name)
                    else:
                        denied += 1
            elif r.status_code in (401, 403):
                if "API key not valid" in body or "API_KEY_INVALID" in body:
                    invalid += 1
                else:
                    denied += 1
            elif r.status_code == 400 and ("API key not valid" in body or "API_KEY_INVALID" in body):
                invalid += 1
        except Exception:
            pass
    if live:
        return "VALID", "layanan aktif: " + ",".join(live)
    if invalid and not denied:
        return "HTTP 400", "API key not valid"
    if denied:
        return "RESTRICTED", f"key ada, {denied} layanan menolak"
    return "HTTP 400", "API key not valid"


def azure_blob(account, key, version="2021-08-06"):
    """Validasi storage account key lewat SharedKey signature ke blob endpoint."""
    import email.utils
    date = email.utils.formatdate(usegmt=True)
    canon_hdr = f"x-ms-date:{date}\nx-ms-version:{version}\n"
    canon_res = f"/{account}/\ncomp:list"
    sts = ("GET\n\n\n\n\n\n\n\n\n\n\n" + canon_hdr + canon_res)
    try:
        sig = base64.b64encode(hmac.new(base64.b64decode(key), sts.encode(), hashlib.sha256).digest()).decode()
    except Exception:
        return "ERROR", "key bukan base64"
    url = f"https://{account}.blob.core.windows.net/?comp=list"
    try:
        r = requests.get(url, timeout=T, headers={
            "x-ms-date": date, "x-ms-version": version,
            "Authorization": f"SharedKey {account}:{sig}"})
        if r.status_code == 200 and "<EnumerationResults" in r.text:
            return "VALID", "blob list ok"
        if r.status_code == 403 and "AuthenticationFailed" in r.text:
            return "INVALID", "AuthenticationFailed"
        return f"HTTP {r.status_code}", r.text[:110]
    except Exception as e:
        return "ERROR", str(e)[:110]


def validate(kind, val, extra=None):
    if kind == "azure_account_key" and extra:
        return azure_blob(extra, val)
    if kind == "gcp_api_key":
        return gcp_probe(val)
    if kind == "do_token":
        try:
            r = requests.get("https://api.digitalocean.com/v2/account",
                             headers={"Authorization": f"Bearer {val}"}, timeout=T)
            return ("VALID" if r.status_code == 200 else f"HTTP {r.status_code}"), r.text[:120]
        except Exception as e:
            return "ERROR", str(e)[:100]
    if kind == "cf_token":
        try:
            r = requests.get("https://api.cloudflare.com/client/v4/user",
                             headers={"Authorization": f"Bearer {val}"}, timeout=T)
            ok = r.status_code == 200 and '"success":true' in r.text.replace(" ", "")
            return ("VALID" if ok else f"HTTP {r.status_code}"), r.text[:120]
        except Exception as e:
            return "ERROR", str(e)[:100]
    if kind == "hetzner_token":
        try:
            r = requests.get("https://api.hetzner.cloud/v1/servers", headers={"Authorization": f"Bearer {val}"}, timeout=T)
            return ("VALID" if r.status_code == 200 else f"HTTP {r.status_code}"), r.text[:100]
        except Exception as e:
            return "ERROR", str(e)[:100]
    if kind == "vultr_key":
        try:
            r = requests.get("https://api.vultr.com/v2/account", headers={"Authorization": f"Bearer {val}"}, timeout=T)
            return ("VALID" if r.status_code == 200 else f"HTTP {r.status_code}"), r.text[:100]
        except Exception as e:
            return "ERROR", str(e)[:100]
    if kind == "linode_token":
        try:
            r = requests.get("https://api.linode.com/v4/account", headers={"Authorization": f"Bearer {val}"}, timeout=T)
            return ("VALID" if r.status_code == 200 else f"HTTP {r.status_code}"), r.text[:100]
        except Exception as e:
            return "ERROR", str(e)[:100]
    return "SKIP", "tanpa validator"


# ---------- sumber ----------
def brave(query, pages=1):
    """search.brave.com — sering 429; coba beberapa kali dengan jeda."""
    out = []
    for p in range(pages):
        for attempt in range(3):
            try:
                r = requests.get("https://search.brave.com/search",
                                 params={"q": query, "offset": p},
                                 headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"}, timeout=T)
                if r.status_code == 200:
                    out += [u for u in re.findall(r'href="(https?://[^"]+)"', r.text)
                            if "brave.com" not in u]
                    break
            except Exception:
                pass
            time.sleep(3 + attempt * 4)
        time.sleep(1)
    return list(dict.fromkeys(out))[:40]


def gitlab_snippets(query, maxn=20):
    """Snippet GitLab publik (HTML, tanpa token)."""
    urls, raws = [], []
    try:
        r = requests.get("https://gitlab.com/explore/snippets", params={"search": query},
                         headers={"User-Agent": UA}, timeout=T)
        for sid in dict.fromkeys(re.findall(r'/snippets/(\d+)', r.text))[:maxn]:
            urls.append(f"https://gitlab.com/snippets/{sid}")
    except Exception:
        pass
    for u in urls:
        try:
            page = requests.get(u, headers={"User-Agent": UA}, timeout=T).text
            for sid, fid in re.findall(r'/snippets/(\d+)/raw/(\d+)', page):
                raws.append(f"https://gitlab.com/snippets/{sid}/raw/{fid}")
        except Exception:
            pass
    return list(dict.fromkeys(raws))[:maxn]


def bing(query, pages=1):
    out = []
    for p in range(pages):
        first = p * 10 + 1
        try:
            r = requests.get("https://www.bing.com/search",
                             params={"q": query, "first": first}, headers={"User-Agent": UA}, timeout=T)
            urls = re.findall(r'href="(https?://[^"]+)"', r.text)
            for u in urls:
                if "bing.com/ck/" in u:
                    q = urllib.parse.parse_qs(urllib.parse.urlparse(u).query).get("u", [""])[0]
                    if q.startswith("a1"):
                        raw = q[2:] + "=" * (-len(q[2:]) % 4)
                        try:
                            u = base64.urlsafe_b64decode(raw).decode("utf8", "ignore")
                            if not u.startswith("http"):
                                continue
                        except Exception:
                            continue
                if any(x in u for x in ("bing.com", "microsoft.com", "msn.com")):
                    continue
                out.append(u)
        except Exception:
            pass
        time.sleep(1)
    return list(dict.fromkeys(out))[:40]


def gists(query, maxn=20):
    urls = []
    try:
        r = requests.get("https://gist.github.com/search", params={"q": query},
                         headers={"User-Agent": UA}, timeout=T)
        pats = re.findall(r'/gist/[A-Za-z0-9]+/[a-f0-9]{20,}', r.text) or \
               re.findall(r'href="(/[A-Za-z0-9._-]+/[a-f0-9]{20,})"', r.text)
        for gid in dict.fromkeys(pats):
            urls.append("https://gist.github.com" + gid)
    except Exception:
        pass
    raws = []
    for u in urls[:maxn]:
        try:
            page = requests.get(u, headers={"User-Agent": UA}, timeout=T).text
            raws += ["https://gist.githubusercontent.com" + x for x in re.findall(r'(/[^"\']+/raw/[^"\']+)', page)]
        except Exception:
            pass
    return list(dict.fromkeys(raws))[:maxn]


def fetch(u):
    try:
        r = requests.get(u, headers={"User-Agent": UA}, timeout=T, allow_redirects=True)
        if r.status_code == 200 and len(r.content) < 3_000_000:
            return r.text
    except Exception:
        pass
    return ""


def scan(text, src):
    hits = []
    for kind, rx in PATTERNS:
        for m in rx.finditer(text):
            val = m.group(1) if m.groups() else m.group(0)
            hits.append({"kind": kind, "value": val, "source": src,
                         "ctx": text[max(0, m.start() - 70):m.end() + 30].replace("\n", " ")[:170]})
    return hits


def mask(v):
    return v[:6] + "…" + v[-4:] if len(v) > 12 else v


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bing")
    ap.add_argument("--brave")
    ap.add_argument("--snippets")
    ap.add_argument("--gists")
    ap.add_argument("--pages", type=int, default=1)
    ap.add_argument("--max", type=int, default=20)
    ap.add_argument("-u", action="append", default=[])
    ap.add_argument("-d", action="append", default=[])
    ap.add_argument("-f", action="append", default=[])
    ap.add_argument("-o", "--out", default="clouddork_out")
    ap.add_argument("--no-validate", action="store_true")
    a = ap.parse_args()

    docs = []  # (text, src)
    if a.bing:
        for u in bing(a.bing, a.pages):
            t = fetch(u)
            if t:
                docs.append((t, u))
    if a.gists:
        for u in gists(a.gists, a.max):
            t = fetch(u)
            if t:
                docs.append((t, u))
    if a.brave:
        for u in brave(a.brave, a.pages):
            t = fetch(u)
            if t:
                docs.append((t, u))
    if a.snippets:
        for u in gitlab_snippets(a.snippets, a.max):
            t = fetch(u)
            if t:
                docs.append((t, u))
    for u in a.u:
        t = fetch(u)
        if t:
            docs.append((t, u))
    for d in a.d:
        for root, _, files in os.walk(d):
            for fn in files:
                p = os.path.join(root, fn)
                try:
                    if os.path.getsize(p) < 3_000_000:
                        docs.append((open(p, errors="replace").read(), p))
                except Exception:
                    pass
    for f in a.f:
        docs.append((open(f, errors="replace").read(), f))
    if not docs:
        print("tidak ada dokumen (sumber kosong/diblokir). Coba --gists atau -u/-d.")
        return

    print(f"dokumen dipindai: {len(docs)}")
    hits, seen = [], set()
    for text, src in docs:
        for h in scan(text, src):
            k = (h["kind"], h["value"])
            if k in seen:
                continue
            seen.add(k)
            hits.append(h)

    # validasi AWS: pasangkan key id + secret dari dokumen yang sama bila ada
    aws = {}
    for h in hits:
        if h["kind"] == "aws_key_id":
            aws.setdefault(h["source"], {})["id"] = h["value"]
        if h["kind"] == "aws_secret":
            aws.setdefault(h["source"], {})["secret"] = h["value"]
    for src, pair in aws.items():
        if "id" in pair and "secret" in pair and not a.no_validate:
            st, detail = aws_sts(pair["id"], pair["secret"])
            hits.append({"kind": "aws_pair", "value": pair["id"], "source": src,
                         "status": st, "detail": detail})

    # validasi Azure: pasangkan account name + key dari dokumen yang sama
    az = {}
    for h in hits:
        if h["kind"] == "azure_conn":
            az.setdefault(h["source"], {})["acct"] = h["value"]
        if h["kind"] == "azure_account_key":
            az.setdefault(h["source"], {})["key"] = h["value"]
    for src, pair in az.items():
        if "acct" in pair and "key" in pair and not a.no_validate:
            st, detail = azure_blob(pair["acct"], pair["key"])
            hits.append({"kind": "azure_pair", "value": pair["acct"], "source": src,
                         "status": st, "detail": detail})

    for h in hits:
        if h["kind"] in ("aws_pair", "azure_pair"):
            continue
        if not a.no_validate and h["kind"] in ("gcp_api_key", "do_token", "cf_token", "hetzner_token",
                                               "vultr_key", "linode_token"):
            h["status"], h["detail"] = validate(h["kind"], h["value"])

    os.makedirs(a.out, exist_ok=True)
    jl = open(f"{a.out}/cloud_keys.jsonl", "w")
    for h in hits:
        jl.write(json.dumps(h) + "\n")
    jl.close()
    os.chmod(f"{a.out}/cloud_keys.jsonl", 0o600)

    for h in hits:
        st = h.get("status", "")
        print(f"  {h['kind']:<18} {mask(h['value']):<24} {st:<10} {h['source'][:55]}")
    valid = [h for h in hits if h.get("status") == "VALID"]
    print(f"\ntotal kandidat: {len(hits)} | VALID: {len(valid)} -> {a.out}/cloud_keys.jsonl (600)")


if __name__ == "__main__":
    main()
