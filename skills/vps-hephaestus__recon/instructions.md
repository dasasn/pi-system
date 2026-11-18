# Recon Skill Instructions

This document provides detailed operational guidance for the `/recon` skill.

## Quick Reference

```bash
# Basic usage
/recon example.com

# With campaign ID
/recon target.gov.id --campaign gov-assessment-2026
```

## Workflow Overview

The recon skill orchestrates the complete scout agent workflow in sequence:

```
1. Initialize Campaign Directory + Port Scan (background)
   |
2. IP Resolution + Co-host Discovery (3 min)
   |
3. Subdomain Enumeration (5 min)
   |
4. Sensitive File Probe (STOP on critical — exit 2, write summary.json)
   |
5. LeakRadar Integration + Path Verification (3 min)
   |
6. Co-host Triage Scoring
   |
7. Tech Fingerprinting + JS Source Analysis
   |
8. Nuclei CVE Scan (10 min)
   |
9. Summary Generation
```

## Tool Dependencies

Required tools (must be in PATH):

| Tool | Purpose | Install |
|------|---------|---------|
| `dig` | DNS resolution | `apt install dnsutils` |
| `curl` | HTTP requests | Usually pre-installed |
| `jq` | JSON parsing | `apt install jq` |
| `nmap` | Port scanning | `apt install nmap` |
| `subfinder` | Subdomain enum | `go install github.com/projectdiscovery/subfinder/v2/cmd/subfinder@latest` |
| `nuclei` | CVE scanning | `go install github.com/projectdiscovery/nuclei/v3/cmd/nuclei@latest` |
| `httpx` or `whatweb` | Tech fingerprint | `go install github.com/projectdiscovery/httpx/cmd/httpx@latest` |

Optional:
- `LR_KEY` in `~/Hephaestus/.env` for LeakRadar API access

## Step-by-Step Breakdown

### Step 1: Initialize + Port Scan

Sets and exports the three required environment variables used throughout
the skill:

```bash
export TARGET="{target}"
export CAMPAIGN="${campaign:-$TARGET}"
export RECON_DIR="$HOME/Hephaestus/campaigns/$CAMPAIGN/recon"
```

**CRITICAL**: These must be `export`ed so that the Python heredoc in Step 9
can read them via `os.environ.get()`. An unquoted heredoc (`<< PYEOF`, not
`<< 'PYEOF'`) is used so bash expands any embedded variable references.

Also launches `nmap -Pn -T4 --top-ports 30` in the background for service
enumeration. Results in `nmap_top30.txt`.

### Step 2: Co-host Discovery

Resolves the target domain to its primary IP, then queries three reverse-IP
services in parallel:

- rapiddns.io/sameip
- api.hackertarget.com/reverseiplookup
- viewdns.info/reverseip

**Race condition fix**: Each source writes to its own dedicated temp file
(`cohosts_rapiddns.txt`, `cohosts_hackertarget.txt`, `cohosts_viewdns.txt`).
After `wait`, the three files are cat-merged and sort-deduped into `cohosts.txt`.
This avoids the race condition where parallel `>>` appends and `>` overwrites
can corrupt a shared output file.

**API error filtering**: All three sources use `grep -oP '[a-zA-Z0-9._-]+\.[a-zA-Z]{2,}'`
to extract only valid domain strings. This prevents API error messages (e.g.,
hackertarget.com "API count exceeded. Increase Quota with API Key.") from
polluting `cohosts.txt` and being fed to nuclei as scan targets.

Output: `cohosts.txt` (deduplicated list of all domains on the same IP)

### Step 3: Subdomain Enumeration

Runs two sources in parallel:
- **subfinder**: Active subdomain enumeration
- **crt.sh**: Certificate transparency logs

Merges and deduplicates results into `subdomains.txt`.

### Step 4: Sensitive File Probe

Probes for common sensitive files including Indonesian government/enterprise
high-value targets:

```
.env                   .git/config
debug.php              phpinfo.php
wp-config.php.bak      docker-compose.yml
.env.backup            .env.prod
adminer.php            _ignition/health-check
install/api.php        .htpasswd
configuration.php      settings.php
web.config             web.config.bak
.svn/entries           .hg/hgrc
server-status          server-info
backup.sql             dump.sql
composer.json          .DS_Store
```

**CRITICAL BEHAVIOR — exit code semantics**:

If `.env` or `.git/config` returns HTTP 200:
1. A **partial `summary.json`** is written immediately to `$RECON_DIR/summary.json`
   with `scout_verdict: "critical_hit"` and the found file listed.
2. `NEXT_SKILL: finding-new` is emitted to stdout for the orchestrator.
3. The skill exits with **exit code 2** (not 0).

Exit code 2 signals to any calling wrapper, orchestrator subprocess check,
or CI runner that an escalation condition was found — not normal completion.
A caller using `if recon_skill.sh; then continue_pipeline; fi` will NOT
continue the pipeline, as intended.

**Exit 0 is reserved for clean, normal completion only.**

### Step 5: LeakRadar Integration + Path Verification

Queries the LeakRadar API for breach credentials associated with:
- Main target domain
- Top 3 co-hosted domains

Requires `LR_KEY` environment variable. If missing or if the API returns
a non-JSON error response, logs a warning to stderr and continues.

**Path verification sub-step**: Iterates over URLs from the LeakRadar
response, performs a live HTTP check, and tests for login form presence
(`input[name=password]`). Only URLs that return HTTP 200 AND have a
password form are written to `spray_targets.txt`. This accounts for the
~35% stale rate in LeakRadar URL data.

Verified spray targets are included in `summary.json` as `spray_targets[]`
for downstream consumption by the strike agent.

### Step 6: Co-host Triage Scoring

Scores each co-host by attack surface. Scoring weights:

| Signal | Score |
|--------|-------|
| WordPress / wp- in headers | +3 |
| Joomla/Drupal/Laravel/SLiMS/Moodle/OJS/GeoServer/Odoo | +3 |
| PHP/Python/Ruby/Node in headers | +1 |
| File upload input in page source | +2 |
| Port 22 (SSH) open | +2 |
| Port 2083 (cPanel SSL) open | +2 |

Results written to `triage_cohosts.txt` as `score|hostname` (sorted descending).
The nuclei step uses score >= 5 as the threshold for inclusion.

### Step 7: Tech Fingerprinting + JS Source Analysis

Attempts tech detection in order of preference:
1. **httpx** with `-tech-detect` — uses `technologies[]` field (httpx v2+ schema)
2. **whatweb** with JSON output
3. **curl headers** (fallback)

**JS source analysis**: Fetches the main page HTML, extracts up to 10 JS
URLs, and scans each for hardcoded secrets (`password`, `secret`, `apikey`,
`token`, `api_key`, `firebase`, `credential`). Any matches are printed to
stdout (max 5 lines per JS file).

### Step 8: Nuclei CVE Scan

Waits for the background nmap (from Step 1) to complete, then builds the
target list from:
- Main target domain
- Co-hosts scoring >= 5 (from triage)
- Top 5 co-hosts by count (fallback)

Uses template categories:
- `cves/` — Known CVEs
- `exposed-panels/` — Admin panels, dashboards
- `misconfiguration/` — Security misconfigs

Severity filter: critical, high, medium

### Step 9: Summary Generation

**Environment requirement**: `RECON_DIR` and `TARGET` must be exported
(Step 1 does this). The heredoc is unquoted (`<< PYEOF`) so bash expands
variables. If either variable is missing, the Python script raises
`RuntimeError` rather than silently writing to the wrong path.

**Error handling**: Every file-read block catches `FileNotFoundError`
separately from other exceptions, logging `[WARN]` or `[ERROR]` messages
with `flush=True`. A missing file is a warning; a JSON decode error (which
may indicate an API error HTML response was saved) is an error. Neither
silently produces zero counts without operator visibility.

**Verdict enum** — aligned with canonical `agents/scout.md` schema:

| Verdict | Condition |
|---------|-----------|
| `critical_hit` | Any sensitive file found (also set in Step 4 partial summary) |
| `proceed` | Nuclei findings > 0, or LeakRadar weak > 0, or spray_targets present |
| `queue` | No immediate hits but cohosts > 0 or subdomains > 5 (worth manual review) |
| `skip` | No significant findings |

## Output Directory Structure

```
~/Hephaestus/campaigns/{campaign}/recon/
  |
  +-- cohosts_rapiddns.txt       # Raw rapiddns source
  +-- cohosts_hackertarget.txt   # Raw hackertarget source
  +-- cohosts_viewdns.txt        # Raw viewdns source
  +-- cohosts_raw.txt            # Merged (pre-dedup)
  +-- cohosts.txt                # Deduplicated co-hosted domains
  +-- triage_cohosts.txt         # Scored co-hosts (score|hostname)
  +-- subdomains.txt             # Merged subdomains
  +-- subs_subfinder.txt         # Raw subfinder output
  +-- crt_raw.json               # Raw crt.sh response
  +-- nmap_top30.txt             # Nmap top-30 port results
  +-- sensitive_hits.txt         # Sensitive files found
  +-- probe_*                    # Individual probe responses
  +-- spray_targets.txt          # Verified live login targets
  +-- leakradar_main.json        # LeakRadar for target
  +-- leakradar_cohost_*.json    # LeakRadar for co-hosts
  +-- html_main.html             # Main page (for JS analysis)
  +-- tech_httpx.json            # Tech fingerprint
  +-- nuclei_targets.txt         # Nuclei input list
  +-- nuclei_findings.txt        # Nuclei raw output
  +-- summary.json               # Structured summary (orchestrator reads this)
```

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Clean completion — summary.json written, verdict is proceed/queue/skip |
| 1 | Error — a required step failed |
| 2 | Critical escalation — .env or .git/config found; partial summary.json written; NEXT_SKILL: finding-new emitted |

## Context Management

To avoid context window overflow:

1. **File lists**: Write to files, report only counts
2. **Nuclei output**: Only show critical findings, rest in file
3. **Co-hosts**: Show top 10 only, full list in file
4. **Max lines**: Pipe through `| head -25` for any verbose output

## Integration with Other Skills

The recon skill is typically the first step in an assessment workflow:

```
/engagement-start client-name
    |
/recon target.com
    |
[If exit 2 / critical_hit] /finding-new  ← MANDATORY, not optional
    |
[If proceed] Strike agent (manual or automated)
    |
[If queue] Manual triage → /recon on prioritized co-hosts
    |
/report-draft
```

**Phase gate requirement**: The orchestrator reads `summary.json` to
determine next phase. The phase gate will not advance if `summary.json`
is missing or has an unrecognized `scout_verdict`. The skill MUST write
`summary.json` before exiting — including on critical_hit (partial summary).

## Troubleshooting

### subfinder not found
```bash
go install github.com/projectdiscovery/subfinder/v2/cmd/subfinder@latest
export PATH=$PATH:~/go/bin
```

### nuclei templates missing
```bash
nuclei -update-templates
```

### LeakRadar API error
Ensure `LR_KEY` is set in `~/Hephaestus/.env`:
```bash
echo "LR_KEY=your_api_key_here" >> ~/Hephaestus/.env
```

### crt.sh timeout
The crt.sh API can be slow. If it times out, the skill continues with
subfinder results only. Manual retry:
```bash
curl -s "https://crt.sh/?q=%.example.com&output=json" | jq -r '.[].name_value' | sort -u
```

### httpx tech field empty
httpx v2+ uses the `technologies` field, not `tech`. The skill uses
`jq -r '.technologies[]?'` — verify your httpx version with `httpx -version`.

### summary.json written to wrong directory
Ensure STEP 1 runs before STEP 9 in the same shell session (or the same
script). `RECON_DIR` and `TARGET` must be exported. If running steps
individually, re-export both variables before running Step 9.

### co-hosts.txt contains API error text
This means the hackertarget grep filter was removed. Verify STEP 2 uses
`grep -oP '[a-zA-Z0-9._-]+\.[a-zA-Z]{2,}'` on the hackertarget curl output.

## Security Considerations

- All probes use `--max-time` limits to prevent hanging
- Sensitive file contents are saved locally but NOT displayed in chat
- LeakRadar credentials are not exfiltrated, only counted
- Nuclei runs with reasonable concurrency (`-c 20`) to avoid detection

## Reference

This skill implements the scout agent workflow documented in:
`/home/Pluto/Hephaestus/agents/scout.md`
