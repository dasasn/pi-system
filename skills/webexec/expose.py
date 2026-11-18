#!/usr/bin/env python3
"""
expose.py — sensitive-file sweep with soft-404 defence and secret classification.

Every hit is validated by CONTENT, not by status code: a 200 that is the SPA
fallback is discarded, and a claimed `.env` must contain `KEY=`.

Secret values are written to ~/loot/secrets (600) and never printed. Only
fingerprint + location is shown.

usage:
  python3 expose.py https://target.com
  python3 expose.py https://target.com --paths custom.txt --json out.json
  python3 expose.py https://target.com --dump        # save full bodies to ~/loot/raw
"""
from __future__ import annotations

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib.webutil import (Baseline, Client, detect_waf, fp, jsonout, norm_url,  # noqa: E402
                         redact, save_raw, save_secret, table)

HERE = os.path.dirname(os.path.abspath(__file__))

# path -> (validator regex, kind, severity)
CHECKS = {
    r"^/\.env":                     (r"(?m)^[A-Z0-9_]{2,}=.{0,}", "env", "critical"),
    r"^/\.git/config$":             (r"\[core\]|\[remote", "git", "critical"),
    r"^/\.git/HEAD$":               (r"ref:\s+refs/", "git", "high"),
    r"^/\.svn/":                    (r"svn://|dir", "svn", "high"),
    r"^/\.hg/":                     (r"\[paths\]|revlog", "hg", "high"),
    r"wp-config\.php":              (r"DB_PASSWORD|DB_NAME", "php-config", "critical"),
    r"(^|/)(config|configuration|settings|local_settings)(\.php|\.py|\.json|\.yml|\.yaml)?(\.bak|\.old|\.save|\.swp|~)?$":
                                    (r"password|passwd|db_|host|user", "config", "critical"),
    r"composer\.(json|lock)$":      (r'"require"|"packages"', "deps", "low"),
    r"package(-lock)?\.json$":      (r'"dependencies"|"name"', "deps", "low"),
    r"\.sql$":                      (r"CREATE TABLE|INSERT INTO|-- MySQL", "sqldump", "critical"),
    r"\.(zip|tar\.gz|tgz|7z|rar)$": (r"^PK\x03\x04|^\x1f\x8b", "archive", "high"),
    r"(id_rsa|id_ed25519|id_dsa)$": (r"PRIVATE KEY", "sshkey", "critical"),
    r"\.(pem|key|p12|pfx|jks)$":    (r"PRIVATE KEY|BEGIN CERTIFICATE|MIIC|MIIE", "tlskey", "critical"),
    r"(credentials|secrets)\.(json|yml|yaml)?$": (r"key|secret|token|password|access", "cloudcred", "critical"),
    r"serviceAccount(Key)?\.json$": (r"private_key_id|client_email", "gcpkey", "critical"),
    r"(wallet\.dat|keystore|eth-wallet)": (r"[a-f0-9]{64}|eth|mnemonic|iv|cipher", "wallet", "critical"),
    r"\.log$":                      (r"\d{4}-\d{2}-\d{2}|GET /|ERROR|Warning", "log", "medium"),
    r"phpinfo\.php$|/info\.php$":   (r"PHP Version|php\.ini", "phpinfo", "medium"),
    r"/server-status$":             (r"Apache Server Status|requests currently", "server-status", "medium"),
    r"/actuator/(env|heapdump|configprops)$": (r"propertySources|ACTUATOR|java\.", "spring-actuator", "critical"),
    r"\.DS_Store$":                 (r"Bud1|\x00\x00\x00\x01Bud1", "dsstore", "low"),
    r"sftp\.json$":                 (r"host|username|password|privateKey", "vscode-creds", "high"),
    r"\.npmrc$":                    (r"_authToken|//registry", "npm-token", "high"),
    r"\.netrc$":                    (r"machine\s+\S+\s+login", "netrc", "high"),
    r"docker-compose\.ya?ml$":      (r"services:|image:", "docker", "medium"),
    r"security\.txt$":              (r"Contact|Policy", "infra", "info"),
    r"swagger|openapi":             (r"swagger|openapi|\"paths\"", "api-spec", "low"),
}

SECRET_RES = [
    ("private_key", r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    ("aws_ak", r"\bAKIA[0-9A-Z]{16}\b"),
    ("huawei_ak", r"\bLTAI[A-Za-z0-9]{12,}\b"),
    ("github_pat", r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    ("slack", r"\bxox[baprs]-[A-Za-z0-9\-]{10,}\b"),
    ("stripe", r"\bsk_live_[A-Za-z0-9]{10,}\b"),
    ("google_api", r"\bAIza[0-9A-Za-z_\-]{35}\b"),
    ("jwt", r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\b"),
    ("hex64_privkey", r"\b(0x)?[a-fA-F0-9]{64}\b"),
    ("app_key", r"(?i)APP_KEY\s*=\s*base64:[A-Za-z0-9+/=]+"),
    ("db_pass", r"(?i)(DB_PASSWORD|DATABASE_PASSWORD|MYSQL_PWD)\s*=\s*\S+"),
    ("sendgrid", r"\bSG\.[A-Za-z0-9_\-]{16,}\.[A-Za-z0-9_\-]{16,}\b"),
    ("telegram_bot", r"\b\d{8,10}:AA[A-Za-z0-9_\-]{30,}\b"),
    ("openai", r"\bsk-[A-Za-z0-9]{32,}\b"),
    ("infura", r"https://[a-z]+\.infura\.io/v3/[a-f0-9]{32}"),
]


def kind_of(path: str):
    for pat, (v, kind, sev) in CHECKS.items():
        if re.search(pat, path, re.I):
            return v, kind, sev
    return (r".", "unknown", "info")


def run(target, paths_file=None, proxy=None, tor=False, dump=False, timeout=10,
        delay=0.0, client=None):
    """Library entry point (also used by the MCP server). Returns the result dict."""
    base = norm_url(target)
    client = client or Client(timeout=timeout, delay=delay,
                              proxy=proxy or ("socks5h://127.0.0.1:9050" if tor else None))
    root = client.get(base + "/")
    waf = detect_waf(root)
    baseline = Baseline(client, base)

    pf = paths_file or os.path.join(HERE, "payloads", "secret-paths.txt")
    with open(pf) as f:
        paths = [l.strip() for l in f if l.strip() and not l.startswith("#")]

    hits, secrets, result = [], [], {"target": base, "waf": waf,
                                     "baseline": {"status": baseline.status,
                                                  "size": baseline.size_median},
                                     "hits": [], "secrets": []}

    for p in paths:
        r = client.get(base + p)
        if not r.ok or r.status in (301, 302, 303, 307, 308):
            # a redirect to a body-less location is not a hit unless it leaks
            if r.status in (301, 302) and "location" in {k.lower() for k in r.headers}:
                continue
        if r.status == 0:
            continue
        validate, kind, sev = kind_of(p)
        if not re.search(validate, r.body[:200000], re.I | re.S):
            continue
        if baseline.is_soft404(r):
            continue
        hit = {"path": p, "status": r.status, "size": r.size, "kind": kind, "severity": sev,
               "snippet": redact(re.sub(r"\s+", " ", r.body[:220]))}
        hits.append(hit)
        if dump:
            hit["saved"] = save_raw(p.strip("/").replace("/", "_") or "root", r.body, base)

        for name, pat in SECRET_RES:
            for m in re.finditer(pat, r.body):
                val = m.group(0)
                if val.startswith("[REDACTED") or "EXAMPLE" in val:
                    continue
                fn = f"{re.sub(r'[^a-zA-Z0-9._-]', '_', base)}_{name}_{fp(val)}.txt"
                path = save_secret(fn, val)
                secrets.append({"type": name, "path": p, "fingerprint": fp(val),
                                "stored_at": path.replace(os.path.expanduser("~"), "~"),
                                "status": "SUSPECT"})
                break

    result["hits"] = hits
    result["secrets"] = secrets
    result["summary"] = {"tested": len(paths), "hits": len(hits),
                         "critical": sum(1 for h in hits if h["severity"] == "critical"),
                         "secrets": len(secrets)}
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("target")
    ap.add_argument("--paths", default=os.path.join(HERE, "payloads", "secret-paths.txt"))
    ap.add_argument("--proxy", default=None)
    ap.add_argument("--tor", action="store_true")
    ap.add_argument("--json", default=None)
    ap.add_argument("--dump", action="store_true")
    ap.add_argument("--timeout", type=int, default=10)
    ap.add_argument("--delay", type=float, default=0.0)
    a = ap.parse_args()

    result = run(a.target, a.paths, a.proxy, a.tor, a.dump, a.timeout, a.delay)
    hits, secrets = result["hits"], result["secrets"]

    print(table([[h["severity"], h["kind"], h["path"], h["status"], h["size"]] for h in hits],
                ["SEV", "KIND", "PATH", "CODE", "SIZE"]), file=sys.stderr)
    for s in secrets:
        print(f"[SECRET] {s['type']} at {s['path']} fp={s['fingerprint']} -> {s['stored_at']}",
              file=sys.stderr)
    out = jsonout(result)
    print(out)
    if a.json:
        with open(a.json, "w") as f:
            f.write(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
