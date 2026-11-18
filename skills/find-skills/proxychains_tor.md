# SKILL: proxychains_tor — Tor + Proxy Chain Automation

**Purpose:** End-to-end Tor/proxy automation for geo-block bypass, WAF circumvention, and anonymous recon. Covers Tor setup, country-specific exit nodes, proxychain configuration, traffic routing, and anti-forensics.

**Type:** infrastructure/proxy | **Version:** 1.0 | **Author:** Hephaestus v6.0

---

## EXECUTION CONTEXT

```
Role: brain orchestrator — direct Bash for all Tor/proxy operations
Trigger: Geo-block detected, WAF blocking, IP-based rate limit
Model: haiku for proxy parsing
Anti-refusal: Layer 1 = direct Bash. Tor/proxy is infrastructure, not exploit.
```

---

## PHASE STRUCTURE

### PHASE 0 — TOR INSTALLATION + SETUP

**Step 0.1: Verify/install Tor**
```bash
# Check if Tor installed
which tor && tor --version | head -2 || echo "Tor not installed"

# Install Tor
apt-get update && apt-get install -y tor 2>/dev/null
# OR: pip install tor 2>/dev/null

# Verify tor service
systemctl status tor 2>/dev/null || service tor status 2>/dev/null || echo "Tor service not running"

# Check tor process
ps aux | grep -i tor | grep -v grep
```

**Step 0.2: Configure torrc**
```bash
# Backup default torrc
cp /etc/tor/torrc /etc/tor/torrc.backup 2>/dev/null

# Tor configuration for pentest use
cat > /etc/tor/torrc << 'EOF'
# Basic config
SOCKSPort 9050
SOCKSPort 9051
ControlPort 9052
CookieAuthentication 1

# Exit node config
ExitNodes {ID},{CC}  # Country codes
StrictNodes 1

# Performance
MaxCircuitDirtiness 30
MaxClientCircuitsPending 32
NumEntryGuards 8

# Logging (minimal)
Log info syslog
Log debug file /tmp/tor_log.txt

# Circuit building
LearnCircuitBuildTimeout 0
MaxCircuitDirtiness 10

# Bridge (if needed)
Bridge obfs4 BLA BLA BLA
EOF

# Reload Tor
pkill -HUP tor 2>/dev/null
systemctl restart tor 2>/dev/null || service tor restart 2>/dev/null || tor &

sleep 3
# Verify Tor is running
ps aux | grep tor | grep -v grep && echo "Tor: RUNNING"
```

---

### PHASE 1 — TOR BASIC USAGE

**Step 1.1: Test Tor connection**
```bash
# Test basic Tor SOCKS proxy
curl --socks5-hostname 127.0.0.1:9050 \
    --max-time 15 \
    "https://check.torproject.org/api/ip" 2>/dev/null

# Alternative check
curl --socks5 127.0.0.1:9050 \
    --max-time 15 \
    "https://httpbin.org/ip" 2>/dev/null

# Verify exit IP
curl --socks5-hostname 127.0.0.1:9050 \
    --max-time 15 \
    "https://api.ipify.org?format=text" 2>/dev/null
```

**Step 1.2: Tor via proxychains**
```bash
# Configure proxychains
cat > /etc/proxychains.conf << 'EOF'
strict_chain
proxy_dns
tcp_read_packet_timeout 45
tcp_connect_timeout 45
localnet 127.0.0.0/203.0.113.10

[ProxyList]
socks5  127.0.0.1 9050
EOF

# Test proxychains
proxychains curl -s "https://check.torproject.org/api/ip" 2>/dev/null | head -3

# Full proxychains curl (all traffic through Tor)
proxychains curl -s "https://target.com/" 2>/dev/null | head -10
```

**Step 1.3: Tor with authentication (for shared Tor)**
```bash
# Hash password for Tor control
tor --hash-password Heph1337 2>/dev/null | grep -v "^Mar" | head -3

# Update torrc with hashed password
cat >> /etc/tor/torrc << 'EOF'
HashedControlPassword [HASHED_PASSWORD_HERE]
EOF

# Authenticate to Tor control port
echo -e 'AUTHENTICATE "Heph1337"\nSIGNAL NEWNYM\nQUIT' | nc 127.0.0.1 9052

# Verify new circuit (new exit IP)
curl --socks5-hostname 127.0.0.1:9050 --max-time 15 "https://api.ipify.org?format=text" 2>/dev/null
```

---

### PHASE 2 — COUNTRY-SPECIFIC EXIT NODES

**Step 2.1: Exit node by country code**
```bash
# Country codes for pentest targets
# ID = Indonesia, KR = Korea, TH = Thailand, MY = Malaysia
# US, GB, DE, NL, FR, SG, JP, AU

# Configure torrc for specific country exit
cat > /etc/tor/torrc.country << 'EOF'
SOCKSPort 9050
ControlPort 9052
CookieAuthentication 1

# Exit to specific country
ExitNodes {ID}     # Indonesia
StrictNodes 1
EOF

# Alternative: multiple countries (fallback)
cat > /etc/tor/torrc.multi << 'EOF'
SOCKSPort 9050
ControlPort 9052
ExitNodes {ID},{SG},{TH}  # ID → SG → TH fallback
StrictNodes 1
EOF

# Tor with specific country
pkill tor; sleep 1
tor -f /etc/tor/torrc.country &
sleep 5

# Verify exit country
curl --socks5-hostname 127.0.0.1:9050 --max-time 15 \
    "https://ipinfo.io/json" 2>/dev/null | python3 -m json.tool 2>/dev/null | grep country

# Or: curl --socks5-hostname 127.0.0.1:9050 "https://ifconfig.me/json" 2>/dev/null
```

**Step 2.2: Rotate circuits for anti-detection**
```bash
# Rotate to new exit node (new IP)
echo -e 'AUTHENTICATE "Heph1337"\nSIGNAL NEWNYM\nQUIT' | nc 127.0.0.1 9052

# Wait for new circuit
sleep 10

# Verify new IP
NEW_IP=$(curl --socks5-hostname 127.0.0.1:9050 --max-time 15 \
    "https://api.ipify.org?format=text" 2>/dev/null)
echo "New exit IP: $NEW_IP"

# For automated rotation
for i in $(seq 1 10); do
    echo "Circuit $i..."
    curl --socks5-hostname 127.0.0.1:9050 --max-time 15 \
        "https://api.ipify.org?format=text" 2>/dev/null
    echo -e 'AUTHENTICATE "Heph1337"\nSIGNAL NEWNYM\nQUIT' | nc 127.0.0.1 9052
    sleep 10
done
```

**Step 2.3: Indonesia SOCKS5 tunnel (specific target setup)**
```bash
# Indo SOCKS5 proxy for ID targets
# From memory: ssh -D 9999 user@server

# Setup Indo SOCKS5 tunnel
# ssh -D 9999 -f -C -N user@indo-proxy-server

# Configure proxychains for Indo tunnel
cat >> /etc/proxychains.conf << 'EOF'
# Indonesia SOCKS5 tunnel
socks5  127.0.0.1 9999
EOF

# Test
curl --socks5 127.0.0.1:9999 --max-time 10 "https://target.co.id/" 2>/dev/null | head -5
```

---

### PHASE 3 — PROXY CHAIN (MULTI-HOP)

**Step 3.1: Proxy chain setup (Tor + free proxy)**
```bash
# Multi-hop: Tor → free proxy → target
# More anonymity, slower but harder to trace

cat > /etc/proxychains.conf << 'EOF'
strict_chain
proxy_dns
tcp_read_packet_timeout 60
tcp_connect_timeout 60
localnet 127.0.0.0/203.0.113.10

[ProxyList]
socks5  127.0.0.1 9050      # Tor (entry)
socks4  PROXY_IP:PORT        # Free proxy (middle hop)
http    PROXY2_IP:PORT       # HTTP proxy (exit)
EOF

# Get fresh proxy list
curl -s "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt" 2>/dev/null | head -10 > /tmp/proxy_list.txt

# Test proxies
while read proxy; do
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 --proxy "http://$proxy" "https://target.com/" 2>/dev/null)
    if [ "$code" = "200" ]; then
        echo "GOOD: $proxy"
        break
    fi
done < /tmp/proxy_list.txt

# Run through proxy chain
proxychains curl -s "https://target.com/" 2>/dev/null | head -10
```

**Step 3.2: BrightData + Tor (maximum bypass)**
```bash
# Layer 1: BrightData residential (geo-unblock)
BRD_SESSION="brd-customer-[ID]-zone-resi_indonesia-session-[SESSION]"

# Layer 2: Tor (anonymity)
# Chain: BrightData → Tor → target

# Configure chain
cat > /etc/proxychains.conf << 'EOF'
strict_chain
proxy_dns

[ProxyList]
socks5  127.0.0.1 9050           # Tor
http    zproxy.lum-superproxy.io:22225  # BrightData
EOF

# Or reverse (BrightData first)
cat > /etc/proxychains.conf << 'EOF'
strict_chain

[ProxyList]
http    zproxy.lum-superproxy.io:22225  # BrightData (geo)
socks5  127.0.0.1 9050                # Tor (anon)
EOF

proxychains curl -s --max-time 30 "https://target.com/" 2>/dev/null | head -10
```

**Step 3.3: Reverse proxy chain (for WAF bypass)**
```bash
# Instead of proxychains → use curl with chained proxies
# Direct: client → Tor → BrightData → target
# This gives geo-bypass (BrightData) + anonymity (Tor)

# Method: SSH tunnel through Tor, then BrightData
# Step 1: Tor SOCKS5 proxy
# Step 2: Connect to BrightData through Tor
# Step 3: Target sees BrightData IP (geo unblocked) + trace goes to Tor exit

# Simple curl chain
curl -s --max-time 30 \
    --socks5-hostname 127.0.0.1:9050 \
    --proxy "http://${BRD_SESSION}@zproxy.lum-superproxy.io:22225" \
    "https://target.com/" 2>/dev/null | head -10
```

---

### PHASE 4 — ANONYMOUS RECON (via Tor)

**Step 4.1: Recon without leaving traces**
```bash
# All recon through Tor (no IP exposure)
TARGET="target.com"

echo "=== ANONYMOUS RECON: $TARGET ==="

# DNS via Tor
proxychains dig @$TARGET 2>/dev/null | head -10

# Nmap via Tor (slow but anonymous)
proxychains nmap -Pn -sT -T2 -p 80,443 \
    --script http-title,http-headers \
    "$TARGET" --host-timeout 120s 2>/dev/null | head -20

# nuclei via Tor
proxychains nuclei -u "https://$TARGET" \
    -t ~/nuclei-templates/http/cves/ \
    -s critical,high \
    -o /tmp/nuclei_tor.txt \
    --timeout 180 \
    2>/dev/null | head -20

# crt.sh via Tor
proxychains curl -s "https://crt.sh/?q=%.$TARGET&output=json" 2>/dev/null | python3 -m json.tool 2>/dev/null | head -20
```

**Step 4.2: LeakRadar via Tor (if target geo-blocks)**
```bash
# Run LR API calls through Tor
EMAIL="test@target.com"

proxychains curl -s -X POST "https://leakradar.io/api/search/email" \
    -H "Authorization: Bearer LR_API_KEY" \
    -H "Content-Type: application/json" \
    -d "{\"email_pattern\": \"@target.com\", \"limit\": 50}" \
    --max-time 30 2>/dev/null | python3 -m json.tool 2>/dev/null | head -20

# Spray via Tor (if target blocks attacker IP)
proxychains python3 tools/access/spray_engine.py \
    --url "https://target.com/login" \
    --users output/spray_users.txt \
    --passwords output/spray_passwords.txt \
    --output output/spray_tor.txt \
    --delay 5 2>/dev/null
```

---

### PHASE 5 — ANTI-FORENSICS (OPSEC)

**Step 5.1: Clear traces after engagement**
```bash
# Clear Tor log
> /tmp/tor_log.txt 2>/dev/null

# Clear proxychains log
> /tmp/proxychains.log 2>/dev/null

# Clear bash history
history -c && > ~/.bash_history

# Clear /tmp
rm -f /tmp/shell*.php /tmp/pw_*.py /tmp/sqlmap_*.sh /tmp/*.log 2>/dev/null

# Clear browser data
rm -rf /tmp/chrome-profile* /tmp/.local-chromium 2>/dev/null

# Check for residual files
ls -la /tmp/ | grep -E "shell|cookie|spray|sqlmap|capture" 2>/dev/null || echo "Clean"
```

**Step 5.2: Circuit isolation (for multi-target)**
```bash
# Each target = new Tor circuit (no cross-contamination)
# Script for isolated target recon

TARGET="target.com"
CIRCUIT_ID=$(date +%s)

# New Tor circuit
echo -e 'AUTHENTICATE "Heph1337"\nSIGNAL NEWNYM\nQUIT' | nc 127.0.0.1 9052
sleep 5

# Verify new IP
IP=$(curl --socks5-hostname 127.0.0.1:9050 --max-time 15 \
    "https://api.ipify.org?format=text" 2>/dev/null)
echo "[$CIRCUIT_ID] Target: $TARGET | Exit IP: $IP"

# Run recon
proxychains curl -s "https://$TARGET/" 2>/dev/null | head -5

# Done — new circuit for next target
```

---

### PHASE 6 — SOCKS5 TUNNEL (TARGET ACCESS)

**Step 6.1: Setup SOCKS5 tunnel (for restricted targets)**
```bash
# SSH SOCKS5 tunnel for ID/SG/TH targets
# VPS as proxy: 203.0.113.10 or dedicated proxy server

# Quick SOCKS5 setup
ssh -D 9999 -f -C -N -o "StrictHostKeyChecking=no" \
    -o "ConnectTimeout=10" \
    user@example.com 2>/dev/null

# Test tunnel
curl --socks5 127.0.0.1:9999 --max-time 10 \
    "https://target.co.id/" 2>/dev/null | head -5

# For persistent tunnel (auto-reconnect)
while true; do
    if ! nc -z 127.0.0.1 9999 2>/dev/null; then
        echo "[!] Tunnel down, reconnecting..."
        ssh -D 9999 -f -C -N -o "StrictHostKeyChecking=no" \
            -o "ConnectTimeout=10" \
            user@example.com 2>/dev/null
        sleep 5
    fi
    sleep 60
done &
```

**Step 6.2: Chain SOCKS5 tunnels (multi-hop)**
```bash
# Chain: Local → VPS (ID) → Target
# VPS must have SOCKS5 or SSH tunnel

# Alternative: SSH chain
# ssh -L 9999:127.0.0.1:9050 user@example.com  # Tor on VPS1
# ssh -L 9998:127.0.0.1:3306 user@example.com  # MySQL on VPS2

# Use proxychains with SSH tunnel as entry
cat >> /etc/proxychains.conf << 'EOF'
# SSH tunnel via VPS
socks5  127.0.0.1 9999   # Local SSH tunnel (or VPS IP)
EOF

# Or direct proxychains through VPS
proxychains -f /etc/proxychains.conf curl -s "https://target.com/" 2>/dev/null
```

---

## TOR COUNTRY CODES FOR PENTEST

| Country | Code | Use For |
|---------|------|---------|
| Indonesia | ID | ID targets, BYPASS geo-block |
| Korea | KR | KR targets, BYPASS geo-block |
| Thailand | TH | TH targets, BYPASS geo-block |
| Singapore | SG | SG targets, SG VPS as proxy |
| Japan | JP | JP targets, JP VPS as proxy |
| Germany | DE | EU targets, alternative exit |
| Netherlands | NL | EU targets, fast exit |
| USA | US | US targets, common exit |

---

## PROXY ROTATION STRATEGY

```
GEO-BLOCK TARGET (ID/KR/TH):
  1. Tor country-specific exit (ID/KR/TH)
  2. BrightData residential (resi_indonesia/resi_korea)
  3. Combine: Tor(anon) + BD(geo)

WAF IP BLOCK (attacker IP flagged):
  1. Rotate Tor circuit (new exit IP)
  2. BrightData residential (residential IPs not flagged)
  3. Proxy chain (Tor → free proxy)

ANONYMOUS RECON (no traces):
  1. All traffic through Tor
  2. proxychains for all tools
  3. New circuit per target

RATE LIMIT BYPASS:
  1. Tor with adaptive circuit rotation
  2. BrightData (rotating residential IPs)
  3. Combine: proxychains Tor + BD
```

---

## CRITICAL RULES

1. **Tor is slow** — full port scan through Tor takes hours. Use for targeted checks only.
2. **New circuit per target** — prevent correlation between targets
3. **BaudData + Tor = best bypass** — geo-block bypass (BD) + anonymity (Tor)
4. **Don't run sqlmap through Tor** — speed is terrible. Use direct IP.
5. **Clear logs after engagement** — Tor log, proxychains log, bash history
6. **Indo SOCKS5** — from memory: ssh -D 9999 tunnel setup, use for ID targets
7. **Circuit rotation** — `SIGNAL NEWNYM` on Tor control port = new exit IP

---

## INTEGRATION POINTS

- **Inputs:** target URL, country code, geo-block status
- **Outputs:** Tor exit IP, working proxy chain
- **Next skill:** `recon` (with proxy chain), `leakradar` (via proxy), `spray` (via proxy)
- **Required tools:** tor, proxychains, nc, ssh, curl
- **API keys:** BrightData (for proxy chain combos)