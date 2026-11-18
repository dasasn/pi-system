---
name: argus-recon
description: Phase 1 — Run reconnaissance on all in-scope targets for the active engagement. Uses the nmap wrapper, scans each target serially (parallel comes in MVP-4), saves raw + parsed outputs to engagements/<slug>/recon/, aggregates into recon/summary.yaml, and transitions phase state. Args. optional --slug <slug>; --scan-type {quick,full,udp-top,discovery} (default quick).
---
# Skill: /recon [--slug <slug>] [--scan-type <type>]

## Purpose
Phase 1 — enumerate hosts and services on all in-scope targets. Outputs go to `engagements/<slug>/recon/` (raw nmap XML + structured YAML + per-target markdown summary + aggregated summary).

## Input Contract
- Optional `--slug <slug>` — engagement slug. If omitted: list engagements; if one candidate (current_phase ∈ {pre-engagement done, recon}), use it; if multiple, ask user via AskUserQuestion.
- Optional `--scan-type` — `quick` (default), `full`, `udp-top`, or `discovery`. WARN user if they request `full` (multi-hour on large scopes).
- Optional `--parallel N` — dispatch N concurrent scans (default 0 = serial; max 8). Use parallel mode when the scope has many independent targets (e.g., several /24s or many domains). Each parallel scan still respects scope + auth checks and is fully isolated (separate output dirs per target — no race conditions).

## Preconditions
1. Engagement exists
2. `authorization.signed_roe == true` in scope.yaml (CLI enforces; do not bypass)
3. `current_phase` is `recon` OR pre-engagement is `done`
4. `nmap` binary available (`which nmap`)

## Output Contract
Per target T in scope:
- `engagements/<slug>/recon/raw/<T>/nmap-<scan-type>.xml`
- `engagements/<slug>/recon/parsed/<T>/nmap-<scan-type>.yaml`
- `engagements/<slug>/recon/parsed/<T>/services.yaml`
- `engagements/<slug>/recon/parsed/<T>/summary.md`

Plus:
- `engagements/<slug>/recon/summary.yaml` (aggregated)
- `state.yaml`: `phases.recon.status = done` (after all targets scanned, no errors)
- Audit events appended to `exec-log.jsonl`

## Steps — EXECUTE IN ORDER

### Step 1: Determine engagement
```bash
python3 $ARGUS_ROOT/bin/argus engagement list
```
If `--slug` not provided and multiple engagements eligible, use `AskUserQuestion` to choose.

### Step 2: Verify preconditions
```bash
python3 $ARGUS_ROOT/bin/argus engagement status <slug>
```
Check current_phase. If pre-engagement not done and recon not in-progress, STOP and tell user to complete pre-engagement first.

### Step 3: Transition phase to recon in-progress (idempotent)
```bash
python3 $ARGUS_ROOT/bin/argus engagement update-phase <slug> recon in-progress
```

### Step 4: Run recon
```bash
# Serial (one target at a time):
python3 $ARGUS_ROOT/bin/argus recon run <slug> --scan-type <type>

# Parallel (N concurrent — use when scope has many targets):
python3 $ARGUS_ROOT/bin/argus recon run <slug> --scan-type <type> --parallel 4
```

This single command:
- Reads scope, collects all in-scope targets (domains + ip_ranges + hosts of web_apps + api_endpoints)
- Validates authorization.signed_roe (CLI hard-stop if false)
- Scans each target via the wrapper (serial by default, threaded with --parallel)
- Saves raw + parsed outputs (per-target isolated dirs — no race conditions in parallel)
- Aggregates into recon/summary.yaml
- Returns nonzero if any target failed

Print progress lines as they appear; do NOT swallow output. In parallel mode the order
is completion order (not scope order) — this is expected.

### Step 5: Inspect results
```bash
cat ~/engagements/<slug>/recon/summary.yaml
```
Show user: total targets scanned, hosts up, open ports, top services.

### Step 6: Handle failures
If any target failed (Step 4 exit was 1):
- Show per-target errors verbatim
- Ask user: retry failed targets, mark as scan-failed and continue, or abort?
- Do NOT mark phase done until either: all targets succeed, or user explicitly accepts partial.

### Step 7: Mark phase done
Only after Step 6 resolved cleanly:
```bash
python3 $ARGUS_ROOT/bin/argus engagement update-phase <slug> recon done
```

### Step 8: Confirmation report
Print:
- Engagement path
- Aggregated counts (hosts up, ports open)
- Top services discovered
- Next step: when ready, `/triage <target>` (v0.2+) or `/finding-new` (MVP-3+)

## Failure Handling
- `nmap` not installed: STOP with `sudo apt install -y nmap` instruction.
- Authorization not signed: CLI hard-stops. STOP the skill; do not retry with --force unless user explicitly requests AND signs a written override (log it).
- Target not in scope: CLI rejects; skip and log. Continue.
- Nmap timeout on one target: log; mark target as scan-timeout in aggregated summary; ask user.
- User aborts mid-phase: leave state in `recon.in-progress`. Resume by re-running this skill.

## DO NOT
- Do NOT scan targets that aren't in scope.in_scope. Never use --force without explicit user authorization (log it).
- Do NOT delete raw XML — required for audit and re-parse.
- Do NOT use `--scan-type full` without explicit user opt-in. It can take hours on large scopes.
- Do NOT mark recon as done if any target failed without user acknowledgement.
- Do NOT proceed to vuln-analysis from within this skill. That's `/triage` or `/finding-new`.

## Why this skill exists
Recon is the foundation of everything downstream. Inaccurate or incomplete recon → missed findings, fabricated findings, wrong remediation. By enforcing structured output (services.yaml schema) and an audit trail (every scan logged with start/end/duration/commands), the rest of the engagement can rely on a single source of truth.
