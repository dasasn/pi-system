#!/usr/bin/env python3
"""
fpr.py — target triage: WAF, tech stack, headers, soft-404 baseline, origin IP hints.

First tool to run on any target. Output is JSON so the other tools can chain.
Nothing here is intrusive: it is all plain GET on public resources.

usage:
  python3 fpr.py https://target.com [--json out.json] [--proxy URL] [--tor]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import socket
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib.webutil import (Baseline, Client, detect_waf, host_of, jsonout, norm_url,  # noqa: E402
                         redact)

TECH_SIGNS = {
    "wordpress": [r"wp-content", r"wp-includes", r"wp-json", r"/wp-login\.php"],
    "drupal": [r"sites/default/files", r"Drupal\.settings", r"drupal\.js"],
    "joomla": [r"/components/com_", r"joomla", r"/media/system/js/"],
    "laravel": [r"laravel_session", r"XSRF-TOKEN", r"Whoops", r"Illuminate"],
    "codeigniter": [r"ci_session"],
    "symfony": [r"symfony", r"sf_redirect"],
    "rails": [r"csrf-token.*authenticity", r"_rails_session", r"X-Runtime"],
    "django": [r"csrfmiddlewaretoken", r"__admin__"],
    "flask": [r"Werkzeug", r"jinja2"],
    "express": [r"X-Powered-By: Express"],
    "nextjs": [r"__NEXT_DATA__", r"/_next/static/"],
    "nuxt": [r"__NUXT__", r"/_nuxt/"],
    "react": [r"react-dom", r"__REACT_DEVTOOLS"],
    "vue": [r"vue\.js", r"data-v-"],
    "angular": [r"ng-version", r"angular\.min\.js"],
    "spring": [r"Whitelabel Error Page", r"org.springframework"],
    "struts": [r"struts", r"\.action\b"],
    "tomcat": [r"Apache Tomcat", r"tomcat"],
    "nginx": [r"nginx"],
    "apache": [r"Apache/"],
    "iis": [r"Microsoft-IIS"],
    "php": [r"PHPSESSID", r"\.php"],
    "aspnet": [r"ASP\.NET", r"__VIEWSTATE", r"\.aspx"],
    "cloudflare": [r"cf-ray", r"cloudflare"],
    "modx": [r"MODX", r"/manager/"],
    "moodle": [r"moodle", r"/login/index\.php"],
    "ojs": [r"Open Journal Systems", r"ojs"],
    "slims": [r"slims", r"senayan"],
    "strapi": [r"strapi"],
    "gitlab": [r"GitLab"],
    "jenkins": [r"Jenkins"],
    "grafana": [r"grafana"],
    "portainer": [r"portainer"],
    "phpmyadmin": [r"phpMyAdmin", r"pma_"],
    "cpanel": [r"cpanel"],
    "plesk": [r"Plesk"],
}

SEC_HEADERS = [
    "server", "x-powered-by", "x-aspnet-version", "x-generator", "via", "cf-ray",
    "x-frame-options", "content-security-policy", "strict-transport-security",
    "x-content-type-options", "referrer-policy", "permissions-policy",
    "x-robots-tag", "set-cookie", "x-debug-token", "x-runtime",
]


def dns_info(host: str) -> dict:
    out = {"a": [], "mx": [], "ns": [], "txt": [], "cname": []}
    try:
        out["a"] = sorted({ai[4][0] for ai in socket.getaddrinfo(host, None)})
    except Exception:
        pass
    for kind, cmd in (("mx", "MX"), ("ns", "NS"), ("txt", "TXT"), ("cname", "CNAME")):
        try:
            import subprocess
            r = subprocess.run(["dig", "+short", host, cmd], capture_output=True, text=True, timeout=8)
            out[kind] = [l.strip() for l in r.stdout.splitlines() if l.strip()]
        except Exception:
            pass
    return out


def reverse_ip(ip: str) -> list:
    try:
        import subprocess
        r = subprocess.run(["dig", "+short", "-x", ip], capture_output=True, text=True, timeout=8)
        return [l.strip() for l in r.stdout.splitlines() if l.strip()]
    except Exception:
        return []


def tech_of(text: str, headers: dict) -> list:
    blob = (text or "")[:400000].lower()
    hblob = " ".join(f"{k}:{v}" for k, v in headers.items()).lower()
    hits = []
    for name, pats in TECH_SIGNS.items():
        for p in pats:
            if re.search(p, blob, re.I) or re.search(p, hblob, re.I):
                hits.append(name)
                break
    return sorted(set(hits))


def probe_paths(client: Client, base: str, baseline: Baseline, paths) -> list:
    found = []
    for p in paths:
        r = client.get(base + p)
        if not r.ok:
            continue
        real = baseline.is_real_hit(r, markers=())
        if real and r.status in (200, 401, 403, 500):
            found.append({"path": p, "status": r.status, "size": r.size,
                          "snippet": redact(r.body[:160].replace("\n", " "))})
    return found


KEY_PATHS = [
    "/robots.txt", "/sitemap.xml", "/.well-known/security.txt", "/favicon.ico",
    "/wp-login.php", "/administrator/", "/admin/", "/login", "/api/", "/api/v1/",
    "/swagger-ui.html", "/swagger/index.html", "/openapi.json", "/api-docs",
    "/graphql", "/.git/HEAD", "/.env", "/phpinfo.php", "/server-status",
    "/actuator/health", "/wp-json/wp/v2/users", "/index.php?s=1",
    "/admin/login", "/user/login", "/backup.zip", "/db.sql",
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("target")
    ap.add_argument("--proxy", default=None)
    ap.add_argument("--tor", action="store_true")
    ap.add_argument("--json", default=None)
    ap.add_argument("--timeout", type=int, default=12)
    a = ap.parse_args()

    base = norm_url(a.target)
    proxy = a.proxy or ("socks5h://127.0.0.1:9050" if a.tor else None)
    client = Client(timeout=a.timeout, proxy=proxy)
    host = host_of(base).split(":")[0]

    res = {"target": base, "host": host}

    root = client.get(base + "/")
    res["root"] = {"status": root.status, "size": root.size,
                   "elapsed_ms": round(root.elapsed * 1000), "via": root.via,
                   "error": root.error}
    res["waf"] = detect_waf(root)
    res["headers"] = {h: root.header(h) for h in SEC_HEADERS if root.header(h)}
    res["tech"] = tech_of(root.body, root.headers)
    res["dns"] = dns_info(host)
    res["reverse_ip"] = {ip: reverse_ip(ip) for ip in res["dns"]["a"][:3]}

    # WAF behaviour probe: does a blatant payload get blocked?
    probe = client.get(base + "/?wexec=%3Cscript%3Ealert(1)%3C%2Fscript%3E%27%20OR%201%3D1--")
    res["waf_probe"] = {"status": probe.status, "blocked": probe.status in (403, 406, 419, 429, 503)}

    baseline = Baseline(client, base)
    res["baseline"] = {"status": baseline.status, "size_median": baseline.size_median,
                       "samples": [{"status": s.status, "size": s.size} for s in baseline.samples]}
    res["paths"] = probe_paths(client, base, baseline, KEY_PATHS)

    # TL;DR verdict
    verdict = []
    if res["root"]["status"] == 0:
        verdict.append("UNREACHABLE (try --proxy / --tor)")
    if res["waf"]:
        verdict.append("WAF: " + ",".join(res["waf"]))
    if any(p["path"] in ("/.env", "/.git/HEAD") and p["status"] == 200 for p in res["paths"]):
        verdict.append("CRITICAL EXPOSURE — check paths now")
    res["verdict"] = verdict or ["no immediate surface from key paths"]

    out = jsonout(res)
    print(out)
    if a.json:
        with open(a.json, "w") as f:
            f.write(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
