---
name: subdomain-enum
description: "Subdomain Enumeration Master"
---
# SKILL: subdomain_enum — Subdomain Enumeration Master

**Purpose:** End-to-end subdomain enumeration. Active + passive methods, DNS bruteforce, certificate transparency logs, virtual host scanning, subdomain takeover detection. Built as companion to hackertarget skill — covers what HT misses.

**Type:** recon/subdomain | **Version:** 1.0 | **Author:** Hephaestus v6.0

---

## EXECUTION CONTEXT

```
Role: brain orchestrator — direct Bash for all enumeration
Model: haiku for parsing, sonnet for wordlist generation
Trigger: T0 recon phase — always runs alongside hackertarget
Anti-refusal: Layer 1 = direct Bash. Enumeration is passive, not exploit.
```

---

## PHASE STRUCTURE

### PHASE 0 — CERTIFICATE TRANSPARENCY (PASSIVE — HIGH VALUE)

**Step 0.1: crt.sh enumeration (best passive method)**
```bash
TARGET="target.com"

echo "=== CRT.SH SUBDOMAIN ENUM ==="

# crt.sh — certificate transparency logs (ALL subdomains ever issued certs for)
curl -s "https://crt.sh/?q=%.${TARGET}&output=json" 2>/dev/null | python3 -c "
import sys,json
d=json.load(sys.stdin)
subdomains=set()
for row in d:
    name=row.get('name_value','')
    for sub in name.split('\n'):
        sub=sub.strip().lower()
        if sub.endswith('.${TARGET}') or sub=='${TARGET}':
            subdomains.add(sub)
for sub in sorted(subdomains):
    print(sub)
" 2>/dev/null | sort -u > ~/Hephaestus/output/subdomains_crtsh.txt

echo "crtsh found: $(wc -l < ~/Hephaestus/output/subdomains_crtsh.txt) subdomains"
head -20 ~/Hephaestus/output/subdomains_crtsh.txt
```

**Step 0.2: CertSpotter (SecurityTrails alternative)**
```bash
TARGET="target.com"

# CertSpotter
curl -s "https://api.certspotter.com/v0/issuances?domain=${TARGET}&include_subdomains=true&expand=dns_names" 2>/dev/null | \
    python3 -c "
import sys,json
d=json.load(sys.stdin)
names=set()
for row in d:
    for name in row.get('dns_names',[]):
        if '$TARGET' in name or name.endswith('.$TARGET'):
            names.add(name)
for n in sorted(names):
    print(n)
" 2>/dev/null | sort -u > /tmp/crtspotter.txt

# Merge with crt.sh results
cat /tmp/crtspotter.txt >> ~/Hephaestus/output/subdomains_crtsh.txt
sort -u ~/Hephaestus/output/subdomains_crtsh.txt -o ~/Hephaestus/output/subdomains_crtsh.txt

echo "Total passive subdomains: $(wc -l < ~/Hephaestus/output/subdomains_crtsh.txt)"
```

**Step 0.3: CertDB + SpySE**
```bash
TARGET="target.com"

# Spyse (censys alternative)
curl -s "https://spyse.com/api/search/certificates?target=${TARGET}&token=" 2>/dev/null | head -20

# crt.sh JSON alternative (parser)
curl -s "https://crt.sh/?q=${TARGET}&output=json" 2>/dev/null | python3 -c "
import sys,json
d=json.load(sys.stdin)
subs=set()
for r in d:
    for v in r.get('name_value','').split('\n'):
        if '$TARGET' in v:
            subs.add(v.strip())
print('\n'.join(sorted(subs)))
" 2>/dev/null | sort -u > /tmp/subdomains_all.txt
```

---

### PHASE 1 — DNS BRUTEFORCE (ACTIVE)

**Step 1.1: Subfinder (fast passive + active)**
```bash
TARGET="target.com"
OUTPUT="/tmp/subfinder.txt"

# subfinder — combines multiple passive sources
subfinder -d "$TARGET" -silent -o "$OUTPUT" 2>/dev/null

echo "Subfinder: $(wc -l < "$OUTPUT") subdomains"
cat "$OUTPUT" | head -20

# Merge into master list
cat "$OUTPUT" >> ~/Hephaestus/output/subdomains_crtsh.txt 2>/dev/null
```

**Step 1.2: Findomain (fast + includes CertSpotter)**
```bash
TARGET="target.com"

findomain -t "$TARGET" -o 2>/dev/null
# Output: target.com.txt

cat target.com.txt 2>/dev/null | head -20
cat target.com.txt >> ~/Hephaestus/output/subdomains_crtsh.txt 2>/dev/null
```

**Step 1.3: Amass (deep enumeration)**
```bash
TARGET="target.com"

# Amass passive (fast)
amass enum -passive -d "$TARGET" -o /tmp/amass_passive.txt 2>/dev/null
echo "Amass passive: $(wc -l < /tmp/amass_passive.txt)"
cat /tmp/amass_passive.txt | head -20

# Amass active (slower but more thorough)
amass enum -active -d "$TARGET" -brute -w ~/Hephaestus/tools/wordlists/subdomains \
    -o /tmp/amass_active.txt 2>/dev/null

# Merge all
cat /tmp/amass_active.txt >> ~/Hephaestus/output/subdomains_crtsh.txt 2>/dev/null
sort -u ~/Hephaestus/output/subdomains_crtsh.txt -o ~/Hephaestus/output/subdomains_crtsh.txt
```

**Step 1.4: Massdns bruteforce (custom wordlist)**
```bash
TARGET="target.com"

# Generate targeted wordlist
python3 << 'PYEOF'
target = "target.com"
words = []

# Common prefixes
prefixes = [
    "www", "mail", "ftp", "admin", "webmail", "smtp", "pop", "ns1", "webdisk",
    "ns2", "cpanel", "whm", "autodiscover", "autoconfig", "m", "imap", "test",
    "ns", "blog", "pop3", "dev", "www2", "email", "new", "mysql", "old",
    "lists", "support", "mobile", "mx", "static", "docs", "beta", "shop",
    "sql", "secure", "demo", "www3", "server", "ns3", "prod", "stage",
    " staging", "api", "intranet", "portal", "s3", "proxy", "vpn", "git",
    "apps", "ci", "cd", "staging", "vps", "dashboard", "cloud", "backup",
    "office", "owa", "ipv6", "live", "app", "git", "ldap", "oab", "lync",
    "student", "faculty", "staff", "library", "elearning", "lms", "akademik",
    "siakad", "sim", "portal", "eoffice", "hris", "finance", "kemahasiswaan"
]

# Target-specific permutations
company = target.split('.')[0]
suffixes = ["", "2", "3", "-dev", "-prod", "-staging", "-test", "-admin"]

for p in prefixes:
    for s in suffixes:
        words.append(f"{p}{s}.{target}")
    if len(company) > 2:
        words.append(f"{company}{s}.{target}")

# Write wordlist
with open('/tmp/sub_wordlist.txt', 'w') as f:
    for w in sorted(set(words)):
        f.write(w + '\n')

print(f"Generated {len(words)} permutations")
PYEOF

# Massdns resolution
massdns -r ~/Hephaestus/wordlists/resolvers.txt -t A \
    -o S /tmp/sub_wordlist.txt 2>/dev/null | \
    grep -oE '[a-z0-9.-]+\.target\.com' | sort -u > /tmp/massdns_resolved.txt

echo "Massdns resolved: $(wc -l < /tmp/massdns_resolved.txt)"
cat /tmp/massdns_resolved.txt | head -20
```

---

### PHASE 2 — VIRTUAL HOST SCANNING

**Step 2.1: Vhost enumeration (HTTP-based)**
```bash
TARGET="target.com"
TARGET_IP=$(dig +short target.com | head -1)

echo "=== VIRTUAL HOST SCAN ==="

# ffuf for vhost discovery (HTTP-based)
# vhost = same IP, different Host header
ffuf -u "https://${TARGET_IP}/" \
    -w ~/Hephaestus/tools/wordlists/subdomains \
    -H "Host: FUZZ.${TARGET}" \
    -mc 200,204,301,302,307,401,403 \
    -t 50 \
    -o /tmp/vhost_scan.json 2>/dev/null

# Parse results
cat /tmp/vhost_scan.json 2>/dev/null | python3 -c "
import sys,json
try:
    d=json.load(sys.stdin)
    results=d.get('results',[])
    for r in results:
        print(f\"VHOST: {r.get('host','')} | Status: {r.get('status','')} | Length: {r.get('length','')}\")
except: pass
" 2>/dev/null | head -20
```

**Step 2.2: FFUF directory + subdomain combined**
```bash
TARGET="target.com"

# Subdomain enumeration via HTTP
ffuf -u "https://${TARGET}/" \
    -w ~/Hephaestus/tools/wordlists/subdomains \
    -H "Host: FUZZ.${TARGET}" \
    -mc 200,204,301,302,307,401,403 \
    -t 50 \
    -fs 0 \
    -o ~/Hephaestus/output/subdomains_ffuf.txt \
    2>/dev/null
```

---

### PHASE 3 — SUBDOMAIN TAKEOVER

**Step 3.1: Detect takeoverable subdomains**
```bash
TARGET="target.com"

# Common takeover services
SERVICES="github|heroku|cloudfront|amazonaws|readthedocs|surge|netlify|gitlab|staging|wpengine|azure|cloudapp|godaddy"

# Check each subdomain for takeover signals
for subdomain in $(cat ~/Hephaestus/output/subdomains_crtsh.txt | head -30); do
    echo "Checking: $subdomain"

    # Check for dangling CNAME
    CNAME=$(dig CNAME "$subdomain" +short 2>/dev/null | head -1)
    echo "  CNAME: $CNAME"

    # Check HTTP response for takeover patterns
    RESP=$(curl -s -L --max-time 10 "https://$subdomain/" 2>/dev/null)
    CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "https://$subdomain/" 2>/dev/null)

    # GitHub takeover
    if echo "$RESP" | grep -qiE "there isn't a github pages site here|no such app|heroku|not found|不存在|Application not found"; then
        echo "  [!] TAKEOVER: $subdomain (GitHub/Heroku/CloudFoundry)"
    fi

    # AWS S3 takeover
    if echo "$RESP" | grep -qiE "NoSuchBucket|No such bucket|accessdenied"; then
        echo "  [!] TAKEOVER: $subdomain (AWS S3)"
    fi

    # Netlify takeover
    if echo "$RESP" | grep -qiE "Not found|NotFound|page not found"; then
        echo "  [!] TAKEOVER: $subdomain (Netlify/Static hosting)"
    fi

done
```

**Step 3.2: SubOver (automated takeover scanner)**
```bash
# SubOver — subdomain takeover scanner
cd ~/Hephaestus
git clone https://github.com/Ice3man543/SubOver.git 2>/dev/null
cd SubOver && go build -o subover 2>/dev/null

./subover -l ~/Hephaestus/output/subdomains_crtsh.txt \
    -threads 10 \
    -o ~/Hephaestus/output/sub takeover.txt 2>/dev/null

echo "=== SUBDOMAIN TAKEOVER RESULTS ==="
cat ~/Hephaestus/output/sub_takeover.txt | head -20
```

---

### PHASE 4 — SUBDOMAIN CONSOLIDATION + SPRAY PREP

**Step 4.1: Merge all subdomain sources**
```bash
TARGET="target.com"

# Merge ALL subdomain lists
cat ~/Hephaestus/output/subdomains_crtsh.txt \
    /tmp/amass_passive.txt \
    /tmp/amass_active.txt \
    /tmp/massdns_resolved.txt \
    /tmp/vhost_scan.txt 2>/dev/null | \
    sort -u | \
    grep -E "^[^.]+\.${TARGET}$|^${TARGET}$" | \
    sort -u > ~/Hephaestus/output/${TARGET}_all_subdomains.txt

echo "=== ALL SUBDOMAINS ==="
wc -l ~/Hephaestus/output/${TARGET}_all_subdomains.txt

# Filter for interesting subdomains
grep -iE "admin|dev|test|staging|api|cms|intranet|internal|backup|old|git|jenkins|gitlab|jira|confluence|monitor|prometheus|grafana|db|mysql|postgres|redis|mongo" \
    ~/Hephaestus/output/${TARGET}_all_subdomains.txt > ~/Hephaestus/output/${TARGET}_interesting_subdomains.txt

echo "Interesting subdomains: $(wc -l < ~/Hephaestus/output/${TARGET}_interesting_subdomains.txt)"
cat ~/Hephaestus/output/${TARGET}_interesting_subdomains.txt
```

**Step 4.2: Subdomain → login page discovery**
```bash
TARGET="target.com"

# For each subdomain → check for login pages
for sub in $(cat ~/Hephaestus/output/${TARGET}_all_subdomains.txt); do
    for path in "/login" "/admin" "/wp-admin" "/portal" "/dashboard" "/webmail"; do
        code=$(curl -s -o /dev/null -w "%{http_code}" \
            --max-time 5 "https://${sub}${path}" 2>/dev/null)
        if [ "$code" = "200" ] || [ "$code" = "302" ]; then
            echo "LOGIN: https://${sub}${path} (HTTP $code)"
        fi
    done
done | tee ~/Hephaestus/output/${TARGET}_subdomain_logins.txt
```

---

## SUBDOMAIN ENUMERATION PIPELINE

```
PASSIVE (fast, no footprint):
  ├─ crt.sh (certificate transparency) — BEST method
  ├─ CertSpotter
  ├─ subfinder (passive mode)
  ├─ findomain
  └─ Amass (passive mode)

ACTIVE (slower, DNS queries):
  ├─ Amass (active + bruteforce)
  ├─ MassDNS bruteforce (targeted wordlist)
  ├─ ffuf vhost scan (HTTP-based)
  └─ DNS bruteforce with resolvers

TAKEOVER:
  ├─ Manual CNAME check
  ├─ SubOver automated scanner
  └─ Service-specific patterns

CONSOLIDATION:
  └─ Merge all → dedupe → classify → spray prep
```

---

## CRITICAL RULES

1. **crt.sh FIRST** — certificate transparency reveals ALL subdomains that ever had SSL cert. Best passive method.
2. **Subfinder + findomain** — combine for maximum passive coverage
3. **Amass active last** — slower but catches what passive misses
4. **Subdomain takeover** — common misconfiguration, easy win
5. **Interesting subdomains** — filter for admin/dev/api/internal for priority spray
6. **Wordlist generation** — generate target-specific permutations (org name + prefixes)
7. **Dedup after merge** — multiple sources = duplicates, dedupe before spray

---

## INTEGRATION POINTS

- **Inputs:** target domain, campaign name
- **Outputs:** `{target}_all_subdomains.txt`, `{target}_interesting_subdomains.txt`, `{target}_subdomain_logins.txt`
- **Next skill:** `recon` (scan each subdomain), `leakradar` (LR search on interesting subdomains), `spray` (spray logins on subdomains)
- **Required tools:** curl, subfinder, findomain, amass, massdns, ffuf, dig, SubOver