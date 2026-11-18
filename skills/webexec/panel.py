#!/usr/bin/env python3
"""
panel.py — admin panel / endpoint discovery with soft-404 suppression.

Uses baselined responses so a SPA that returns 200 for everything cannot
manufacture fake results. Every hit is scored: a real admin login has a form
with a password field, a real API endpoint returns JSON.

usage:
  python3 panel.py https://target.com
  python3 panel.py https://target.com --wordlist custom.txt --threads 20
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib.webutil import (Baseline, Client, detect_waf, jsonout, norm_url,  # noqa: E402
                         redact, table)

DEFAULT_PATHS = """\
/admin /admin/ /admin/login /admin/login.php /admin/index.php /admin/dashboard /administrator
/administrator/ /administrator/index.php /wp-admin /wp-login.php /wp-json/wp/v2/users
/user/login /users/sign_in /login /login.php /login.html /signin /sign_in /auth/login
/manager/html /manager/ /host-manager/html /jmx-console /web-console
/phpmyadmin /phpMyAdmin /pma /mysql /adminer /adminer.php /db /sql
/cpanel /whm /webmail /plesk /vesta /hestia /cloudpanel /portainer
/console /dashboard /panel /backend /manage /management /cms /adminpanel /controlpanel
/api /api/ /api/v1 /api/v2 /api/admin /api/users /api/login /api/token /api/graphql
/graphql /graphiql /swagger /swagger-ui.html /swagger/index.html /api-docs /openapi.json
/v2/api-docs /redoc /docs /internal /staging /dev /test /debug
/actuator /actuator/env /actuator/health /actuator/mappings /actuator/heapdump
/.well-known/openid-configuration /oauth/token /sso /auth /idp
/server-status /server-info /.DS_Store /robots.txt /sitemap.xml
/filemanager /file-manager /elfinder /elfinder.html /ckfinder /kcfinder /tinymce
/upload /uploads /files /media /assets /backup /backups /tmp /temp /cache
/setup /install /installer /config /configuration /settings /system
/telescope /horizon /_debugbar /_ignition/health-check /debug/default/view
/soap /ws /webservice /services /rpc /jsonrpc
/jolokia /jolokia/list /solr /elasticsearch /_cluster/health /kibana /grafana
/jenkins /nexus /harbor /registry /rancher /k8s /kubernetes
/health /healthz /status /metrics /version /info /ping
""".split()

INTERESTING = {
    "login_form": re.compile(r'<input[^>]+type=["\']?password', re.I),
    "admin_words": re.compile(r"(admin|dashboard|sign in|log in|control panel|management)", re.I),
    "json_api": re.compile(r'^\s*[\{\[]'),
    "graphql": re.compile(r"(graphql|__schema|query\s*\{)", re.I),
    "stack_trace": re.compile(r"(Exception|Traceback|stack trace|Whoops|at [a-zA-Z.]+\(.*\.java:\d+\))", re.I),
    "env_leak": re.compile(r"(DB_|APP_KEY|SECRET|PASSWORD)\s*=", re.I),
    "listing": re.compile(r"Index of /<|Directory listing for", re.I),
    "swagger": re.compile(r'("swagger"|"openapi"|swagger-ui)', re.I),
}

SEVERITY = {
    "login_form": "info", "admin_words": "info", "json_api": "low", "graphql": "medium",
    "stack_trace": "medium", "env_leak": "critical", "listing": "medium", "swagger": "low",
}


def classify(resp) -> list:
    tags = []
    body = resp.body[:40000]
    for name, pat in INTERESTING.items():
        if pat.search(body):
            tags.append(name)
    return tags


def probe(client, base, baseline, path):
    r = client.get(base + path)
    if not r.ok or r.status in (0, 404, 410):
        return None
    if baseline.is_soft404(r):
        return None
    tags = classify(r)
    if not tags and r.status not in (401, 403):
        return None
    sev = max((SEVERITY[t] for t in tags), key=lambda s: ["info", "low", "medium", "critical"].index(s), default="info")
    return {"path": path, "status": r.status, "size": r.size, "tags": tags, "severity": sev,
            "snippet": redact(re.sub(r"\s+", " ", r.body[:180]))}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("target")
    ap.add_argument("--wordlist", default=None)
    ap.add_argument("--threads", type=int, default=12)
    ap.add_argument("--proxy", default=None)
    ap.add_argument("--tor", action="store_true")
    ap.add_argument("--json", default=None)
    ap.add_argument("--timeout", type=int, default=10)
    a = ap.parse_args()

    base = norm_url(a.target)
    client = Client(timeout=a.timeout, proxy=a.proxy or ("socks5h://127.0.0.1:9050" if a.tor else None))
    root = client.get(base + "/")
    waf = detect_waf(root)
    baseline = Baseline(client, base)

    paths = DEFAULT_PATHS
    if a.wordlist:
        with open(a.wordlist) as f:
            paths = [l.strip() for l in f if l.strip() and not l.startswith("#")]

    hits = []
    with ThreadPoolExecutor(max_workers=a.threads) as ex:
        futs = [ex.submit(probe, client, base, baseline, p) for p in paths]
        for fu in futs:
            try:
                r = fu.result()
            except Exception:
                r = None
            if r:
                hits.append(r)

    hits.sort(key=lambda h: (["critical", "medium", "low", "info"].index(h["severity"]), h["path"]))
    result = {"target": base, "waf": waf, "baseline": {"status": baseline.status, "size": baseline.size_median},
              "tested": len(paths), "hits": hits,
              "summary": {"hits": len(hits),
                          "critical": sum(1 for h in hits if h["severity"] == "critical"),
                          "has_login": any("login_form" in h["tags"] for h in hits)}}
    print(table([[h["severity"], h["status"], h["path"], ",".join(h["tags"])] for h in hits],
                ["SEV", "CODE", "PATH", "TAGS"]), file=sys.stderr)
    out = jsonout(result)
    print(out)
    if a.json:
        open(a.json, "w").write(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
