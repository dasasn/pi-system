---
name: vps-hephaestus-recon
description: Run the scout agent workflow for comprehensive target reconnaissance. Orchestrates subdomain enumeration, co-host discovery, sensitive file probing, LeakRadar intel, tech fingerprinting, and Nuclei CVE scanning. Output to campaigns/{target}/recon/ directory.
---
# /recon

Execute comprehensive reconnaissance against a target domain using the scout
agent workflow. Combines multiple enumeration and discovery techniques into
a single orchestrated pipeline with structured output.

## Arguments

- `<target>` (required) — The target domain to scan (e.g., `example.com`).
  Must be a valid domain, not a URL.

- `--campaign <id>` (optional) — Campaign identifier. If omitted, uses the
  target domain as the campaign ID (sanitized to kebab-case).

## Procedure

### STEP 1 — Initialize Campaign Directory + Port Scan

```bash
export TARGET="{target}"
export CAMPAIGN="${campaign:-$TARGET}"
export RECON_DIR="$HOME/Hephaestus/campaigns/$CAMPAIGN/recon"
mkdir -p "$RECON_DIR"
echo "Recon output: $RECON_DIR"

# IP resolution
IP=$(dig +short $TARGET | tail -1)
echo "Primary IP: $IP"

# Background port scan — top 30 ports for service enumeration
nmap -Pn -T4 --top-ports 30 "$IP" -oN "$RECON_DIR/nmap_top30.txt" --open 2>/dev/null &
NMAP_PID=$!
```

### STEP 2 — Co-host Discovery (3 min)

```bash
# Co-hosts: 3 parallel sources — each writes to its own temp file to avoid race condition
curl -s "https://rapiddns.io/sameip/$IP?full=1" | grep -oP '[a-zA-Z0-9._-]+\.[a-zA-Z]{2,}' > "$RECON_DIR/cohosts_rapiddns.txt" &
curl -s "https://api.hackertarget.com/reverseiplookup/?q=$IP" | grep -oP '[a-zA-Z0-9._-]+\.[a-zA-Z]{2,}' > "$RECON_DIR/cohosts_hackertarget.txt" &
curl -s "https://viewdns.info/reverseip/?host=$IP&t=1" | grep -oP '[a-zA-Z0-9._-]+\.[a-zA-Z]{2,}' > "$RECON_DIR/cohosts_viewdns.txt" &
wait

# Merge after all three complete — no race condition
cat "$RECON_DIR/cohosts_rapiddns.txt" "$RECON_DIR/cohosts_hackertarget.txt" "$RECON_DIR/cohosts_viewdns.txt" | sort -u > "$RECON_DIR/cohosts_raw.txt"
cp "$RECON_DIR/cohosts_raw.txt" "$RECON_DIR/cohosts.txt"
echo "Co-hosts discovered: $(wc -l < "$RECON_DIR/cohosts.txt")"
```

### STEP 3 — Subdomain Enumeration (5 min max)

```bash
# subfinder + crt.sh in parallel
subfinder -d $TARGET -silent -o "$RECON_DIR/subs_subfinder.txt" 2>/dev/null &
curl -s "https://crt.sh/?q=%.${TARGET}&output=json" -o "$RECON_DIR/crt_raw.json" &
wait

# Merge and deduplicate
jq -r '.[].name_value' "$RECON_DIR/crt_raw.json" 2>/dev/null >> "$RECON_DIR/subs_subfinder.txt"
sort -u "$RECON_DIR/subs_subfinder.txt" -o "$RECON_DIR/subdomains.txt"
echo "Subdomains total: $(wc -l < "$RECON_DIR/subdomains.txt")"
```

### STEP 4 — Sensitive File Probe (CRITICAL: STOP on .env/.git)

```bash
SENSITIVE_FILES=".env .git/config debug.php phpinfo.php wp-config.php.bak docker-compose.yml .env.backup .env.prod adminer.php _ignition/health-check install/api.php .htpasswd configuration.php settings.php web.config web.config.bak .svn/entries .hg/hgrc server-status server-info backup.sql dump.sql composer.json .DS_Store"

> "$RECON_DIR/sensitive_hits.txt"
for f in $SENSITIVE_FILES; do
    code=$(curl -sk --max-time 3 -o "$RECON_DIR/probe_${f//\//_}" -w "%{http_code}" "https://$TARGET/$f" 2>/dev/null)
    if [ "$code" = "200" ]; then
        echo "*** HIT: $f ***"
        echo "$f" >> "$RECON_DIR/sensitive_hits.txt"
        # .env or .git = STOP immediately, write partial summary and escalate
        if [[ "$f" == ".env" || "$f" == ".git/config" ]]; then
            echo "CRITICAL_HIT: $f — writing partial summary and escalating"
            python3 -c "
import json, os
from datetime import datetime
with open('${RECON_DIR}/summary.json', 'w') as fh:
    json.dump({'phase':'recon_complete','target':'${TARGET}','timestamp':datetime.utcnow().isoformat()+'Z','scout_verdict':'critical_hit','sensitive_files':['$f'],'ip':'${IP}','cohosts_count':0,'subdomains_count':0,'leakradar':{'total':0,'weak':0,'strong':0},'nuclei_findings_count':0,'spray_targets':[]}, fh, indent=2)
"
            echo "NEXT_SKILL: finding-new"
            exit 2
        fi
    fi
done
echo "Sensitive files found: $(wc -l < "$RECON_DIR/sensitive_hits.txt")"
```

### STEP 5 — LeakRadar Integration (3 min)

```bash
source ~/Hephaestus/.env
curl -s -H "Authorization: Bearer $LR_KEY" \
    "https://api.leakradar.io/search/domain/$TARGET" -o "$RECON_DIR/leakradar_main.json"

python3 -c "
import json, sys
try:
    d = json.load(open('$RECON_DIR/leakradar_main.json'))
    print(f'LeakRadar: Total={d.get(\"total\",0)} | Weak={d.get(\"weak\",0)} | Strong={d.get(\"strong\",0)}')
except json.JSONDecodeError as e:
    print(f'LeakRadar: JSON decode error — possible API rate limit or error response: {e}', file=sys.stderr)
except Exception as e:
    print(f'LeakRadar: error reading response: {e}', file=sys.stderr)
" 2>/dev/null

# Path verification — check LeakRadar URLs for live login forms (35% stale rate)
> "$RECON_DIR/spray_targets.txt"
for url in $(python3 -c "import json, sys
try:
    d=json.load(open('$RECON_DIR/leakradar_main.json'))
    [print(x) for x in d.get('urls',[])]
except: pass
" 2>/dev/null); do
    code=$(curl -sk --max-time 8 -o /dev/null -w "%{http_code}" "$url")
    forms=$(curl -sk --max-time 8 "$url" 2>/dev/null | grep -icE 'input.*name.*(password|pass|pwd)')
    [ "$code" = "200" ] && [ "$forms" -ge "1" ] && echo "$url" >> "$RECON_DIR/spray_targets.txt" && echo "LIVE SPRAY TARGET: $url"
done
echo "Verified spray targets: $(wc -l < "$RECON_DIR/spray_targets.txt")"

# Check top 3 co-hosts
for cohost in $(head -3 "$RECON_DIR/cohosts.txt"); do
    curl -s -H "Authorization: Bearer $LR_KEY" \
        "https://api.leakradar.io/search/domain/$cohost" -o "$RECON_DIR/leakradar_cohost_$cohost.json" &
done; wait
```

### STEP 6 — Co-host Triage Scoring

```bash
# Score each co-host by attack surface: CMS detection + open port scoring
triage_host() {
    host=$1; score=0
    tech=$(curl -sk --max-time 8 -I "https://$host" 2>/dev/null)
    echo "$tech" | grep -iqE "wordpress|wp-" && score=$((score+3))
    echo "$tech" | grep -iqE "joomla|drupal|laravel|slims|moodle|ojs|geoserver|odoo" && score=$((score+3))
    echo "$tech" | grep -iqE "php|python|ruby|node" && score=$((score+1))
    curl -sk --max-time 5 "https://$host" 2>/dev/null | grep -iqE "input.*type.*file" && score=$((score+2))
    timeout 3 bash -c "echo >/dev/tcp/$host/22" 2>/dev/null && score=$((score+2))
    timeout 3 bash -c "echo >/dev/tcp/$host/2083" 2>/dev/null && score=$((score+2))
    echo "$score|$host"
}
export -f triage_host
cat "$RECON_DIR/cohosts.txt" | xargs -P 15 -I{} bash -c 'triage_host {}' | sort -t'|' -k1 -nr > "$RECON_DIR/triage_cohosts.txt"
echo "=== TOP CO-HOST TARGETS ==="
head -10 "$RECON_DIR/triage_cohosts.txt"
```

### STEP 7 — Tech Fingerprinting

```bash
# whatweb or httpx tech detection
if command -v httpx &>/dev/null; then
    echo "$TARGET" | httpx -silent -tech-detect -json -o "$RECON_DIR/tech_httpx.json" 2>/dev/null
    echo "Tech fingerprint (httpx): $(jq -r '.technologies[]?' "$RECON_DIR/tech_httpx.json" 2>/dev/null | head -10 | tr '\n' ', ')"
elif command -v whatweb &>/dev/null; then
    whatweb -q --log-json="$RECON_DIR/tech_whatweb.json" "https://$TARGET" 2>/dev/null
    echo "Tech fingerprint (whatweb) saved to $RECON_DIR/tech_whatweb.json"
else
    # Fallback: header-based detection
    curl -sk -I "https://$TARGET" -o "$RECON_DIR/headers.txt"
    echo "Headers saved (no httpx/whatweb available)"
fi

# JS source analysis — scan for hardcoded secrets / API keys
curl -sk "https://$TARGET" -o "$RECON_DIR/html_main.html"
for jsurl in $(grep -oE 'https?://[^"]+\.js' "$RECON_DIR/html_main.html" | head -10); do
    curl -sk "$jsurl" | grep -iE 'password|secret|apikey|token|api_key|firebase|credential' | head -5
done
```

### STEP 8 — Nuclei CVE Scan (10 min max)

```bash
# Wait for nmap to finish before building target list
wait $NMAP_PID 2>/dev/null

# Build target list: main domain + high-scoring co-hosts (score >= 5)
awk -F'|' '$1>=5 {print $2}' "$RECON_DIR/triage_cohosts.txt" > "$RECON_DIR/nuclei_targets.txt"
echo "$TARGET" >> "$RECON_DIR/nuclei_targets.txt"
head -5 "$RECON_DIR/cohosts.txt" >> "$RECON_DIR/nuclei_targets.txt" 2>/dev/null
sort -u "$RECON_DIR/nuclei_targets.txt" -o "$RECON_DIR/nuclei_targets.txt"

# Run nuclei with cve, exposed-panels, misconfigs templates
nuclei -l "$RECON_DIR/nuclei_targets.txt" \
    -t cves/ -t exposed-panels/ -t misconfiguration/ \
    -severity critical,high,medium \
    -c 20 -silent \
    -o "$RECON_DIR/nuclei_findings.txt" 2>/dev/null

echo "Nuclei findings: $(wc -l < "$RECON_DIR/nuclei_findings.txt" 2>/dev/null || echo 0)"
```

### STEP 9 — Generate Recon Summary

```bash
# RECON_DIR, TARGET must be exported (set in STEP 1)
python3 << PYEOF
import json
import os
import sys
from datetime import datetime

recon_dir = os.environ.get('RECON_DIR')
target = os.environ.get('TARGET')
if not recon_dir or not target:
    raise RuntimeError('RECON_DIR and TARGET must be exported before running this step')

summary = {
    "phase": "recon_complete",
    "target": target,
    "timestamp": datetime.utcnow().isoformat() + "Z",
    "ip": "",
    "cohosts_count": 0,
    "subdomains_count": 0,
    "sensitive_files": [],
    "leakradar": {"total": 0, "weak": 0, "strong": 0},
    "nuclei_findings_count": 0,
    "spray_targets": [],
    "scout_verdict": "proceed"
}

# Read IP
try:
    import subprocess
    summary["ip"] = subprocess.check_output(f"dig +short {target} | tail -1", shell=True).decode().strip()
except Exception as e:
    print(f'[WARN] could not resolve IP for {target}: {e}', flush=True)

# Count cohosts
try:
    with open(f"{recon_dir}/cohosts.txt") as f:
        summary["cohosts_count"] = len(f.readlines())
except FileNotFoundError:
    print(f'[WARN] cohosts.txt not found at {recon_dir}', flush=True)
except Exception as e:
    print(f'[ERROR] reading cohosts.txt: {e}', flush=True)

# Count subdomains
try:
    with open(f"{recon_dir}/subdomains.txt") as f:
        summary["subdomains_count"] = len(f.readlines())
except FileNotFoundError:
    print(f'[WARN] subdomains.txt not found at {recon_dir}', flush=True)
except Exception as e:
    print(f'[ERROR] reading subdomains.txt: {e}', flush=True)

# Sensitive files
try:
    with open(f"{recon_dir}/sensitive_hits.txt") as f:
        summary["sensitive_files"] = [l.strip() for l in f if l.strip()]
except FileNotFoundError:
    print(f'[WARN] sensitive_hits.txt not found at {recon_dir}', flush=True)
except Exception as e:
    print(f'[ERROR] reading sensitive_hits.txt: {e}', flush=True)

# LeakRadar
try:
    with open(f"{recon_dir}/leakradar_main.json") as f:
        lr = json.load(f)
        summary["leakradar"] = {"total": lr.get("total", 0), "weak": lr.get("weak", 0), "strong": lr.get("strong", 0)}
except FileNotFoundError:
    print(f'[WARN] leakradar_main.json not found at {recon_dir}', flush=True)
except json.JSONDecodeError as e:
    print(f'[ERROR] leakradar_main.json JSON decode error (possible API error response): {e}', flush=True)
except Exception as e:
    print(f'[ERROR] reading leakradar_main.json: {e}', flush=True)

# Spray targets
try:
    with open(f"{recon_dir}/spray_targets.txt") as f:
        summary["spray_targets"] = [l.strip() for l in f if l.strip()]
except FileNotFoundError:
    print(f'[WARN] spray_targets.txt not found at {recon_dir}', flush=True)
except Exception as e:
    print(f'[ERROR] reading spray_targets.txt: {e}', flush=True)

# Nuclei count
try:
    with open(f"{recon_dir}/nuclei_findings.txt") as f:
        summary["nuclei_findings_count"] = len([l for l in f if l.strip()])
except FileNotFoundError:
    print(f'[WARN] nuclei_findings.txt not found at {recon_dir}', flush=True)
except Exception as e:
    print(f'[ERROR] reading nuclei_findings.txt: {e}', flush=True)

# Verdict — aligned with canonical scout.md enum: proceed|critical_hit|queue|skip
if summary["sensitive_files"]:
    summary["scout_verdict"] = "critical_hit"
elif summary["nuclei_findings_count"] > 0 or summary["leakradar"]["weak"] > 0 or summary["spray_targets"]:
    summary["scout_verdict"] = "proceed"
elif summary["cohosts_count"] > 0 or summary["subdomains_count"] > 5:
    summary["scout_verdict"] = "queue"
else:
    summary["scout_verdict"] = "skip"

with open(f"{recon_dir}/summary.json", "w") as f:
    json.dump(summary, f, indent=2)

print(json.dumps(summary, indent=2))
PYEOF
```

## Output Structure

All output is written to `campaigns/{campaign}/recon/`:

```
recon/
  cohosts_rapiddns.txt     # Raw rapiddns source
  cohosts_hackertarget.txt # Raw hackertarget source
  cohosts_viewdns.txt      # Raw viewdns source
  cohosts_raw.txt          # Merged pre-dedup co-hosts
  cohosts.txt              # All co-hosted domains (deduplicated)
  subdomains.txt           # All subdomains (subfinder + crt.sh merged)
  sensitive_hits.txt       # Sensitive files found
  spray_targets.txt        # Verified live login targets from LeakRadar
  triage_cohosts.txt       # Co-hosts scored by attack surface
  nmap_top30.txt           # Nmap top-30 port scan results
  leakradar_main.json      # LeakRadar results for main target
  leakradar_cohost_*.json  # LeakRadar results for co-hosts
  html_main.html           # Main page HTML (for JS analysis)
  tech_httpx.json          # Tech fingerprint (or tech_whatweb.json)
  nuclei_targets.txt       # Targets fed to nuclei
  nuclei_findings.txt      # Raw nuclei output
  summary.json             # Structured summary for orchestrator
```

## Summary JSON Schema

```json
{
  "phase": "recon_complete",
  "target": "example.com",
  "timestamp": "2026-05-29T12:00:00Z",
  "ip": "203.0.113.10",
  "cohosts_count": 15,
  "subdomains_count": 42,
  "sensitive_files": [".env"],
  "leakradar": {"total": 100, "weak": 5, "strong": 2},
  "nuclei_findings_count": 3,
  "spray_targets": ["https://target.com/login"],
  "scout_verdict": "proceed|critical_hit|queue|skip"
}
```

## Exit Codes

- **Exit 0** — Clean completion. All steps finished normally.
- **Exit 1** — Error. A step failed or a required dependency was missing.
- **Exit 2** — Critical hit. `.env` or `.git/config` found accessible. Partial summary.json written. NEXT_SKILL: finding-new.

## Constraints (DO and DO NOT)

- **DO** run all parallel operations with `&` and `wait` for efficiency.
- **DO** deduplicate all lists before writing final output.
- **DO** export TARGET, CAMPAIGN, RECON_DIR so they are available inside Python heredocs.
- **DO** write each co-host source to its own temp file to avoid race conditions.
- **DO** write partial summary.json and exit 2 on critical hit — never exit 0 on escalation.
- **DO** pipe scan output through `| head -N` (max 25 lines) to avoid context overflow.
- **DO NOT** include raw nuclei/subfinder output in chat — report counts only.
- **DO NOT** skip LeakRadar even if API key is missing — capture the error.
- **DO NOT** run without a target domain — prompt user if missing.
- **DO NOT** use bare `except: pass` — catch specific exceptions and log warnings.

## Exit Conditions

1. **Critical hit (exit 2):** `.env` or `.git/config` accessible — write partial summary.json with scout_verdict=critical_hit, emit NEXT_SKILL: finding-new, exit 2.
2. **Normal completion (exit 0):** All steps finished — write summary.json with verdict (proceed/queue/skip), report counts.
3. **Timeout:** 30 minutes max — write partial summary.json, note incomplete steps.

## Integration

This skill wraps the scout agent workflow from `agents/scout.md`. The summary.json
output is consumed by the orchestrator to determine the next phase (typically
strike agent for exploitation).

## Example

```
/recon example.com
/recon target.gov.id --campaign gov-assessment-2026
```
