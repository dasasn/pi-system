---
name: port-scan
description: "Nmap Automation + Optimization"
---
# SKILL: port_scan — Nmap Automation + Optimization

**Purpose:** End-to-end port scanning automation. Full port scan, service detection, OS fingerprinting, script scanning, output parsing, and UDP coverage. Optimized for pentest speed vs thoroughness trade-offs.

**Type:** recon/scan | **Version:** 1.0 | **Author:** Hephaestus v6.0

---

## EXECUTION CONTEXT

```
Role: brain orchestrator — direct Bash for all nmap operations
Model: haiku for output parsing
Trigger: Recon phase — after DNS resolution, before web enumeration
Anti-refusal: Layer 1 = direct Bash. nmap IS a scanner, not exploit.
```

---

## PHASE STRUCTURE

### PHASE 0 — NMAP SETUP + OPTIMIZATION

**Step 0.1: Verify nmap installation**
```bash
nmap --version | head -3
which nmap && nmap --help | grep "Nmap" | head -1

# NSE scripts available
ls /usr/share/nmap/scripts/ 2>/dev/null | wc -l
ls /usr/share/nmap/nselib/ 2>/dev/null | wc -l

# Check timing template
nmap --help 2>/dev/null | grep -iE "timing|-T" | head -5
```

---

### PHASE 1 — QUICK SCAN (60-SECOND TRIAGE)

**Step 1.1: Top 20 port scan (fast)**
```bash
TARGET="target.com"
OUTPUT="~/Hephaestus/output/${CAMPAIGN}/nmap_quick.txt"

mkdir -p ~/Hephaestus/output/${CAMPAIGN}/

nmap -Pn --top-ports 20 -T4 \
    --host-timeout 60s \
    -oG "$OUTPUT" \
    "$TARGET" 2>/dev/null

echo "=== QUICK SCAN (60s) ==="
grep "Ports:" "$OUTPUT" | head -5

# Parse open ports
grep "Ports:" "$OUTPUT" | cut -d" " -f4- | tr ',' '\n' | \
    grep "open" | cut -d"/" -f1 | sort -nu
```

**Step 1.2: Single port checks (parallel)**
```bash
TARGET="target.com"

# Fast parallel port checks (when nmap too slow)
for port in 22 80 443 3306 5432 6379 8080 8443 27017 9200; do
    (echo > /dev/tcp/$TARGET/$port) 2>/dev/null && echo "OPEN: $port" || echo "CLOSED: $port"
done &

# Alternative: nc check
for port in 22 80 443 3306 5432 6379; do
    nc -vn -w2 "$TARGET" "$port" 2>/dev/null | head -2 &
done
wait
```

---

### PHASE 2 — FULL PORT SCAN

**Step 2.1: All ports (TCP)**
```bash
TARGET="target.com"
OUTPUT="~/Hephaestus/output/${CAMPAIGN}/nmap_full.gnmap"

nmap -Pn -p- -T4 \
    --host-timeout 300s \
    -oG "$OUTPUT" \
    "$TARGET" 2>/dev/null

echo "=== FULL PORT SCAN ==="
OPEN_PORTS=$(grep "Ports:" "$OUTPUT" | cut -d" " -f4- | tr ',' '\n' | \
    grep "open" | cut -d"/" -f1 | sort -nu | tr '\n' ',' | sed 's/,$//')
echo "Open ports: $OPEN_PORTS"

# Save port list
grep "Ports:" "$OUTPUT" | cut -d" " -f4- | tr ',' '\n' | \
    grep "open" | cut -d"/" -f1 | sort -nu > ~/Hephaestus/output/${CAMPAIGN}/open_ports.txt

echo "Total open: $(wc -l < ~/Hephaestus/output/${CAMPAIGN}/open_ports.txt)"
```

**Step 2.2: Service + version detection**
```bash
TARGET="target.com"
OPEN_PORTS=$(cat ~/Hephaestus/output/${CAMPAIGN}/open_ports.txt | tr '\n' ',' | sed 's/,$//')
OUTPUT="~/Hephaestus/output/${CAMPAIGN}/nmap_services.txt"

nmap -Pn -sV -sC \
    -p "$OPEN_PORTS" \
    --host-timeout 180s \
    -oN "$OUTPUT" \
    "$TARGET" 2>/dev/null

echo "=== SERVICE DETECTION ==="
cat "$OUTPUT" | grep -iE "open|service|version" | head -30
```

**Step 2.3: OS fingerprinting**
```bash
TARGET="target.com"
OUTPUT="~/Hephaestus/output/${CAMPAIGN}/nmap_os.txt"

nmap -Pn -O --osscan-guess \
    --host-timeout 120s \
    -oN "$OUTPUT" \
    "$TARGET" 2>/dev/null

echo "=== OS FINGERPRINT ==="
cat "$OUTPUT" | grep -iE "os|linux|windows|ubuntu|debian|centos" | head -10
```

---

### PHASE 3 — NSE SCRIPT SCANNING

**Step 3.1: Default script scan (common vulns)**
```bash
TARGET="target.com"
OPEN_PORTS=$(cat ~/Hephaestus/output/${CAMPAIGN}/open_ports.txt | tr '\n' ',' | sed 's/,$//')
OUTPUT="~/Hephaestus/output/${CAMPAIGN}/nmap_scripts.txt"

nmap -Pn -sC \
    -p "$OPEN_PORTS" \
    --host-timeout 180s \
    -oN "$OUTPUT" \
    "$TARGET" 2>/dev/null

echo "=== SCRIPT SCAN RESULTS ==="
grep -iE "vulnerability|exploit|risk|warning|outdated|cve" "$OUTPUT" | head -30
```

**Step 3.2: CVE detection scripts**
```bash
TARGET="target.com"

# HTTP CVE scripts
nmap -Pn -p 80,443,8080,8443 \
    --script http-vuln-cve2017-5638.nse \
    --script http-vuln-cve2019-1010.nse \
    --script http-vuln-cve2021-41773.nse \
    --script http-vuln-cve2022-28693.nse \
    --host-timeout 60s \
    -oN /tmp/nmap_http_cve.txt \
    "$TARGET" 2>/dev/null

# SMTP CVE scripts
nmap -Pn -p 25,465,587 \
    --script smtp-vuln-cve2020-16846.nse \
    --script smtp-vuln-cve2021-26808.nse \
    --host-timeout 60s \
    -oN /tmp/nmap_smtp_cve.txt \
    "$TARGET" 2>/dev/null

# MySQL CVE scripts
nmap -Pn -p 3306 \
    --script mysql-vuln-cve2012-2122.nse \
    --host-timeout 60s \
    -oN /tmp/nmap_mysql_cve.txt \
    "$TARGET" 2>/dev/null
```

**Step 3.3: Common vulnerability scripts**
```bash
TARGET="target.com"
OUTPUT="~/Hephaestus/output/${CAMPAIGN}/nmap_vulns.txt"

# Vuln scan scripts
nmap -Pn -sV \
    --script vuln \
    -p 80,443,3306,5432,27017 \
    --host-timeout 180s \
    -oN "$OUTPUT" \
    "$TARGET" 2>/dev/null

# Specific vuln scripts
nmap -Pn \
    --script "auth,brute,discovery,exploit,vuln" \
    -p 22,80,443,3306,5432,8080 \
    --host-timeout 180s \
    -oN /tmp/nmap_full_scripts.txt \
    "$TARGET" 2>/dev/null

echo "=== VULNERABILITY SCAN ==="
cat "$OUTPUT" | head -50
```

---

### PHASE 4 — UDP SCANNING

**Step 4.1: Top 100 UDP ports**
```bash
TARGET="target.com"
OUTPUT="~/Hephaestus/output/${CAMPAIGN}/nmap_udp.txt"

nmap -Pn -sU --top-ports 100 \
    -T4 \
    --host-timeout 180s \
    -oN "$OUTPUT" \
    "$TARGET" 2>/dev/null

echo "=== UDP SCAN ==="
grep "Ports:" "$OUTPUT" | head -5
grep "open" "$OUTPUT" | head -20
```

---

### PHASE 5 — PARSE + CONSOLIDATE

**Step 5.1: Build port summary**
```bash
cd ~/Hephaestus/output/${CAMPAIGN}/

echo "=== NMAP SCAN SUMMARY: target.com ===" > nmap_summary.txt
echo "Date: $(date)" >> nmap_summary.txt
echo "" >> nmap_summary.txt

echo "=== OPEN PORTS ===" >> nmap_summary.txt
cat open_ports.txt >> nmap_summary.txt
echo "" >> nmap_summary.txt

echo "=== SERVICES ===" >> nmap_summary.txt
grep -E "^[0-9]+/tcp" nmap_services.txt >> nmap_summary.txt
echo "" >> nmap_summary.txt

echo "=== VULNERABILITIES ===" >> nmap_summary.txt
grep -iE "CVE|vuln|risk|exploit" nmap_vulns.txt >> nmap_summary.txt 2>/dev/null

cat nmap_summary.txt
```

---

## NMAP OPTIMIZATION REFERENCE

| Timing | Speed | Stealth | Use Case |
|--------|-------|---------|---------|
| `-T5` | Fastest | Very loud | Local network, time-critical |
| `-T4` | Fast | Loud | Most pentest use |
| `-T3` | Normal | Moderate | Default |
| `-T2` | Slow | Quiet |IDS detection |
| `-T1` | Very slow | Stealthy | High-security environments |

| Scan Type | Flags | Use For |
|-----------|-------|---------|
| SYN | `-sS` (needs root) | Fast, stealthy |
| Connect | `-sT` | No root needed |
| UDP | `-sU` | UDP services |
| Version | `-sV` | Service detection |
| OS | `-O` | OS fingerprint |

---

## CRITICAL RULES

1. **Quick scan FIRST** — 20 ports in 60s, get immediate intel
2. **Full scan after** — all 65535 ports, run in parallel with other ops
3. **Service detection** — identify exact service + version for CVE matching
4. **NSE scripts** — vuln scripts find issues nmap -sV misses
5. **UDP scan** — DNS, SNMP, NTP often open, missed by TCP-only scan
6. **Save to campaign output** — every scan result → state + output directory

---

## INTEGRATION POINTS

- **Inputs:** target IP/hostname, campaign name, scan type (quick/full)
- **Outputs:** `output/{campaign}/nmap_quick.txt`, `nmap_full.gnmap`, `nmap_services.txt`, `open_ports.txt`
- **Next skill:** `recon` (web enumeration on open ports), `cms_exploit` (service-specific CVE), `sqli` (if web port found), `blackbox` (web attack on port 80/443)
- **Required tools:** nmap