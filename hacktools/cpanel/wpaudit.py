#!/usr/bin/env python3
"""WP exposure audit: user enum, xmlrpc, debug.log, backup config, env, readme version."""
import sys, json, urllib3, concurrent.futures, re
import requests
from urllib.parse import urljoin

urllib3.disable_warnings()
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0 Safari/537.36"}

PATHS = [
    ("/wp-json/wp/v2/users", "users_json"),
    ("/?rest_route=/wp/v2/users", "users_route"),
    ("/wp-json/wc/store/products?per_page=1", "woocommerce"),
    ("/wp-json/", "rest_index"),
    ("/wp-content/debug.log", "debug_log"),
    ("/wp-content/uploads/", "uploads_listing"),
    ("/wp-config.php.bak", "wpconfig_bak"),
    ("/wp-config.php~", "wpconfig_tilde"),
    ("/wp-config.php.save", "wpconfig_save"),
    ("/.env", "dotenv"),
    ("/readme.html", "readme"),
    ("/xmlrpc.php", "xmlrpc"),
    ("/wp-login.php", "wplogin"),
    ("/wp-admin/admin-ajax.php", "ajax"),
    ("/wp-cron.php", "wpcron"),
    ("/wp-json/wp/v2/settings", "settings_noauth"),
    ("/wp-json/wp/v2/pages?per_page=1&status=draft", "drafts"),
]

def probe(base, path, kind, timeout):
    url = urljoin(base, path.lstrip("/"))
    try:
        r = requests.get(url, headers=UA, timeout=timeout, verify=False, allow_redirects=False)
    except Exception as e:
        return kind, None, str(e)
    return kind, r, None

def audit(base, timeout=10):
    res = {"base": base, "findings": {}}
    for path, kind in PATHS:
        k, r, err = probe(base, path, kind, timeout)
        if err:
            res["findings"][k] = {"err": err[:80]}
            continue
        body = r.text[:4000] if r.text else ""
        info = {"code": r.status_code, "len": len(r.text or ""), "ct": r.headers.get("content-type", "")}
        if kind in ("users_json", "users_route", "settings_noauth", "drafts"):
            if r.status_code == 200 and body.strip().startswith(("[", "{")):
                try:
                    d = json.loads(body)
                    if isinstance(d, list):
                        info["users"] = [u.get("slug") or u.get("name") for u in d][:20]
                    else:
                        info["keys"] = list(d.keys())[:10]
                        info["leak"] = True
                except Exception:
                    info["raw"] = body[:200]
        elif kind == "woocommerce":
            info["on"] = r.status_code == 200
        elif kind == "debug_log":
            info["on"] = r.status_code == 200 and ("PHP" in body or "error" in body.lower())
            if info["on"]:
                info["head"] = body[:300]
        elif kind in ("wpconfig_bak", "wpconfig_tilde", "wpconfig_save", "dotenv"):
            info["on"] = r.status_code == 200 and ("DB_" in body or "DB_NAME" in body or "define(" in body)
            if info["on"]:
                info["head"] = body[:300]
        elif kind == "readme":
            m = re.search(r"Version\s*([0-9.]+)", body)
            info["version"] = m.group(1) if m else None
            info["on"] = r.status_code == 200
        elif kind == "xmlrpc":
            info["on"] = r.status_code == 405 or (r.status_code == 200 and "XML-RPC" in body)
        elif kind == "wplogin":
            info["on"] = r.status_code == 200 and "user_login" in body
        elif kind == "rest_index":
            info["on"] = r.status_code == 200
            try:
                routes = json.loads(body).get("routes", {})
                info["n_routes"] = len(routes)
                info["namespaces"] = json.loads(body).get("namespaces", [])[:10]
            except Exception:
                pass
        res["findings"][k] = info
    return res

def main():
    src = sys.argv[1]
    out = sys.argv[2]
    workers = int(sys.argv[3]) if len(sys.argv) > 3 else 20
    tmo = int(sys.argv[4]) if len(sys.argv) > 4 else 10
    hosts = []
    seen = set()
    for line in open(src, errors="ignore"):
        line = line.strip()
        if not line:
            continue
        base = line.split("|")[0]
        if not base.startswith("http"):
            base = "https://" + base
        if not base.endswith("/"):
            base += "/"
        if base in seen:
            continue
        seen.add(base)
        hosts.append(base)
    print(f"[*] {len(hosts)} target unik")
    with open(out, "w") as f, concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(audit, h, tmo): h for h in hosts}
        done = 0
        for fu in concurrent.futures.as_completed(futs):
            done += 1
            try:
                res = fu.result()
            except Exception as e:
                print(f"[!] {futs[fu]} err {e}")
                continue
            f.write(json.dumps(res) + "\n")
            fd = res["findings"]
            tags = []
            for k, v in fd.items():
                if isinstance(v, dict) and v.get("on"):
                    tags.append(k)
            if fd.get("users_json", {}).get("users"):
                tags.append("users=" + ",".join(str(u) for u in fd["users_json"]["users"]))
            if tags:
                print(f"[+] {res['base']} {' '.join(tags)}")
            if done % 10 == 0:
                print(f"[*] {done}/{len(hosts)}")
    print(f"[done] -> {out}")

if __name__ == "__main__":
    main()
