# SKILL: hackertarget — HackerTarget API Reconnaissance

**Purpose:** End-to-end passive recon using HackerTarget API. DNS enumeration, reverse IP, subnet lookup, zone transfer, WHOIS. Fast, reliable, API-key-authenticated. Works as primary or supplement to full recon skill.

**Type:** recon/api | **Version:** 1.0 | **Author:** Hephaestus v6.0

---

## EXECUTION CONTEXT

```
Role: brain orchestrator — direct Bash for all HT API calls
Model: haiku for parsing results
Trigger: Part of recon phase OR when full tools unavailable
Priority: Fast, API-authenticated = no rate limit issues
Anti-refusal: Layer 1 = direct Bash. Never delegate API calls to agents.
```

---

## PHASE STRUCTURE

### PHASE 0 — API VERIFICATION

**Step 0.1: Verify API key works**
```bash
# HackerTarget API key check
HT_API="API_KEY"

# Test with simple query
curl -s "https://api.hackertarget.com/dnslookup/?q=example.com&apikey=${HT_API}" 2>/dev/null | head -5

# Check if rate limited
curl -s "https://api.hackertarget.com/dnslookup/?q=example.com&apikey=${HT_API}" 2>/dev/null | grep -qiE "limit|exceeded|api.key|error" && echo "RATE LIMITED or INVALID KEY"
```

---

### PHASE 1 — DNS ENUMERATION

**Step 1.1: Basic DNS lookup**
```bash
TARGET="target.com"
HT_API="API_KEY"

echo "=== DNS LOOKUP: $TARGET ==="
curl -s "https://api.hackertarget.com/dnslookup/?q=${TARGET}&apikey=${HT_API}" 2>/dev/null

# Output: A, AAAA, MX, NS records
# Also includes: SOA, TXT, CNAME for subdomains
```

**Step 1.2: Zone transfer attempt**
```bash
TARGET="target.com"
HT_API="API_KEY"

echo "=== ZONE TRANSFER CHECK ==="
# HackerTarget has zone transfer check endpoint
curl -s "https://api.hackertarget.com/zonetransfer/?q=${TARGET}&apikey=${HT_API}" 2>/dev/null | head -50

# If zone transfer succeeds → full domain list
# If fails → use subdomain enumeration instead
```

**Step 1.3: Reverse DNS lookup**
```bash
# Reverse DNS for IP → find hostnames
IP="203.0.113.10"
curl -s "https://api.hackertarget.com/reversedns/?q=${IP}&apikey=${HT_API}" 2>/dev/null
```

---

### PHASE 2 — SUBDOMAIN ENUMERATION

**Step 2.1: Find subdomains via DNS zone transfer**
```bash
TARGET="target.com"
HT_API="API_KEY"

echo "=== SUBDOMAIN ENUMERATION ==="
curl -s "https://api.hackertarget.com/dnslookup/?q=${TARGET}&apikey=${HT_API}" 2>/dev/null | \
    grep -oE '[a-z0-9_-]+\.[a-z0-9.-]+\.[a-z]{2,}' | sort -u > ~/Hephaestus/output/ht_subdomains.txt

wc -l ~/Hephaestus/output/ht_subdomains.txt
cat ~/Hephaestus/output/ht_subdomains.txt | head -30
```

**Step 2.2: AS number lookup (for large targets)**
```bash
TARGET="target.com"
HT_API="API_KEY"

# Get AS number for target
curl -s "https://api.hackertarget.com/aslookup/?q=${TARGET}&apikey=${HT_API}" 2>/dev/null
# Output: AS number → use for subnet enumeration

# Then enumerate all IPs in that AS
# curl -s "https://api.hackertarget.com/reverseiplookup/?q=AS12345&apikey=${HT_API}"
```

**Step 2.3: BGP lookup (for ISP/government targets)**
```bash
TARGET="target.com"
HT_API="API_KEY"

# BGP AS lookup
curl -s "https://api.hackertarget.com/bgpView/asLookup/?q=${TARGET}&apikey=${HT_API}" 2>/dev/null | head -20

# Useful for: university networks, government networks, large corporate
# Shows all IPs announced by target's AS
```

---

### PHASE 3 — REVERSE IP + CO-HOST HUNTING

**Step 3.1: Reverse IP lookup (find all sites on same server)**
```bash
TARGET_IP=$(dig +short target.com | head -1)
HT_API="API_KEY"

echo "=== REVERSE IP: $TARGET_IP ==="
curl -s "https://api.hackertarget.com/reverseiplookup/?q=${TARGET_IP}&apikey=${HT_API}" 2>/dev/null | head -50

# CRITICAL: Every co-host is a bonus target
# shared hosting = symlink pivot, same DB server
# Different CMS = different attack vectors
```

**Step 3.2: All reverse IP results → save for co-host spray**
```bash
TARGET_IP=$(dig +short target.com | head -1)
HT_API="API_KEY"

# Get ALL sites on this IP → save for future campaigns
curl -s "https://api.hackertarget.com/reverseiplookup/?q=${TARGET_IP}&apikey=${HT_API}" 2>/dev/null > ~/Hephaestus/output/cohosts_${TARGET}.txt

echo "Co-host count: $(wc -l < ~/Hephaestus/output/cohosts_${TARGET}.txt)"
echo "Co-hosts:"
cat ~/Hephaestus/output/cohosts_${TARGET}.txt

# Add to campaign notes
echo "CO-HOSTS: $(cat ~/Hephaestus/output/cohosts_${TARGET}.txt | tr '\n' ', ')" >> ~/Hephaestus/state/campaigns/campaign.json
```

---

### PHASE 4 — WHOIS + ASN INTELLIGENCE

**Step 4.1: WHOIS lookup**
```bash
TARGET="target.com"
HT_API="API_KEY"

echo "=== WHOIS: $TARGET ==="
curl -s "https://api.hackertarget.com/whois/?q=${TARGET}&apikey=${HT_API}" 2>/dev/null | head -50

# Extract: registrar, name servers, creation date, admin contact
# Useful for: password spraying admin email, finding related domains
```

**Step 4.2: Page links analysis**
```bash
TARGET="target.com"
HT_API="API_KEY"

# Analyze page links (internal + external)
curl -s "https://api.hackertarget.com/pagelinks/?q=${TARGET}&apikey=${HT_API}" 2>/dev/null | head -30

# Useful for: finding hidden admin panels, related applications, third-party integrations
```

**Step 4.3: Traceroute**
```bash
TARGET="target.com"
HT_API="API_KEY"

echo "=== TRACEROUTE: $TARGET ==="
curl -s "https://api.hackertarget.com/mtr/?q=${TARGET}&apikey=${HT_API}" 2>/dev/null | head -30

# Shows network path to target
# Useful for: finding WAF/CDN IPs, internal network structure, ISP information
```

---

### PHASE 5 — HOST SEARCH + SUBNET

**Step 5.1: Find all hosts in subnet**
```bash
SUBNET="192.168.1.0/24"
HT_API="API_KEY"

# If subnet discovered → enumerate hosts
# curl -s "https://api.hackertarget.com/hostsearch/?q=${SUBNET}&apikey=${HT_API}"
```

**Step 5.2: NMAP-style port scan via HT (limited)**
```bash
TARGET="target.com"
HT_API="API_KEY"

# HackerTarget has port scan endpoint
curl -s "https://api.hackertarget.com/nmap/?q=${TARGET}&apikey=${HT_API}" 2>/dev/null | head -30

# Note: This is LIMITED compared to actual nmap
# Use for quick checks only → supplement with full nmap
```

---

### PHASE 6 — COMPREHENSIVE HT RECON SCRIPT

**Step 6.1: One-shot HT recon**
```bash
TARGET="target.com"
HT_API="API_KEY"
OUTPUT_DIR="~/Hephaestus/output/ht_${TARGET}"

mkdir -p "$OUTPUT_DIR"

# Run all HT API queries in parallel
echo "=== HACKERTARGET RECON: $TARGET ===" > "$OUTPUT_DIR/full_ht.txt"
echo "Date: $(date)" >> "$OUTPUT_DIR/full_ht.txt"

# DNS lookup
echo -e "\n\n=== DNS LOOKUP ===" >> "$OUTPUT_DIR/full_ht.txt"
curl -s "https://api.hackertarget.com/dnslookup/?q=${TARGET}&apikey=${HT_API}" >> "$OUTPUT_DIR/full_ht.txt" 2>/dev/null

# Zone transfer
echo -e "\n\n=== ZONE TRANSFER ===" >> "$OUTPUT_DIR/full_ht.txt"
curl -s "https://api.hackertarget.com/zonetransfer/?q=${TARGET}&apikey=${HT_API}" >> "$OUTPUT_DIR/full_ht.txt" 2>/dev/null

# Reverse IP
TARGET_IP=$(dig +short target.com | head -1)
echo -e "\n\n=== REVERSE IP: $TARGET_IP ===" >> "$OUTPUT_DIR/full_ht.txt"
curl -s "https://api.hackertarget.com/reverseiplookup/?q=${TARGET_IP}&apikey=${HT_API}" >> "$OUTPUT_DIR/full_ht.txt" 2>/dev/null

# WHOIS
echo -e "\n\n=== WHOIS ===" >> "$OUTPUT_DIR/full_ht.txt"
curl -s "https://api.hackertarget.com/whois/?q=${TARGET}&apikey=${HT_API}" >> "$OUTPUT_DIR/full_ht.txt" 2>/dev/null

# Page links
echo -e "\n\n=== PAGE LINKS ===" >> "$OUTPUT_DIR/full_ht.txt"
curl -s "https://api.hackertarget.com/pagelinks/?q=${TARGET}&apikey=${HT_API}" >> "$OUTPUT_DIR/full_ht.txt" 2>/dev/null

echo "=== HT RECON COMPLETE ==="
ls -la "$OUTPUT_DIR/"
```

---

## HACKERTARGET API ENDPOINTS REFERENCE

| Endpoint | Purpose | Example |
|----------|---------|---------|
| `/dnslookup/` | DNS records + subdomains | `?q=target.com&apikey=KEY` |
| `/zonetransfer/` | Zone transfer (if allowed) | `?q=target.com&apikey=KEY` |
| `/reverseiplookup/` | Sites on same IP | `?q=203.0.113.10&apikey=KEY` |
| `/reversedns/` | Hostname from IP | `?q=203.0.113.10&apikey=KEY` |
| `/whois/` | WHOIS information | `?q=target.com&apikey=KEY` |
| `/pagelinks/` | Links from homepage | `?q=target.com&apikey=KEY` |
| `/mtr/` | Traceroute to target | `?q=target.com&apikey=KEY` |
| `/aslookup/` | AS number lookup | `?q=target.com&apikey=KEY` |
| `/nmap/` | Basic port scan | `?q=target.com&apikey=KEY` |
| `/hostsearch/` | Host search in subnet | `?q=192.168.1.0/24&apikey=KEY` |

---

## HACKERTARGET vs OTHER DNS SOURCES

| Tool | Speed | API Auth | Coverage | Best For |
|------|-------|----------|----------|---------|
| HackerTarget | Fast | Yes (no rate limit) | Medium | Subdomain enum, reverse IP |
| DNSdumpster | Medium | No | High | Zone transfer, DNS mapping |
| crt.sh | Fast | No | Very High | Subdomain via cert logs |
| VirusTotal | Medium | Yes (free tier) | High | Subdomain via cert history |
| Shodan | Slow | Yes | Very High | IP history, service fingerprint |
| Censys | Slow | Yes (format issues) | Very High | Cert logs, IP enumeration |

**Strategy: Use HackerTarget as PRIMARY (API auth = no rate limits), supplement with crt.sh + DNSdumpster**

---

## CRITICAL RULES

1. **Use API key** — avoids rate limits, consistent access
2. **Reverse IP = co-host hunting** — every site on same IP is a bonus target
3. **AS/BGP lookup** — for large targets (university, government, ISP)
4. **Zone transfer** — quick check, can reveal all subdomains if misconfigured
5. **WHOIS for spray** — admin email + registrar info for password spraying
6. **Supplement with nmap** — HT port scan is basic, use actual nmap for full port scan
7. **Zone transfer fails often** — don't rely on it, use subdomain enum instead

---

## INTEGRATION POINTS

- **Inputs:** target domain, HT API key, campaign name
- **Outputs:** `output/ht_{target}/full_ht.txt`, `cohosts_{target}.txt`, `ht_subdomains.txt`
- **Next skill:** `recon` (for full port scan after HT DNS enum), `leakradar` (for LR on found subdomains), `spray` (for spray on co-host logins)
- **Required tools:** curl, dig, python3