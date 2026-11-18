---
name: argus-engagement-start
description: Initialize a new pentest engagement with scoping wizard. Walks through Rules of Engagement (RoE), scope, contacts, dates; validates inputs; creates engagement folder at $ARGUS_ENGAGEMENTS/<slug>/ with scope.yaml, state.yaml, README.md, subdirs, and per-engagement git repo. Args. <client-slug> (kebab-case, required).
---
# Skill: /engagement-start &lt;client-slug&gt;

## Purpose
Phase 0 of every engagement — scoping + Rules of Engagement (RoE) capture. Must complete successfully before any other phase can start.

## Input Contract
- **Required**: `<client-slug>` — kebab-case identifier matching regex `^[a-z0-9][a-z0-9-]+[a-z0-9]$`, 3-64 chars (e.g., `acme-corp`).

## Output Contract (skill SUCCEEDS only when ALL of these exist)
- `$ARGUS_ENGAGEMENTS/<slug>/scope.yaml` — validated against schema
- `$ARGUS_ENGAGEMENTS/<slug>/state.yaml` — initialized to `current_phase=pre-engagement, status=in-progress`
- `$ARGUS_ENGAGEMENTS/<slug>/README.md` — from template
- `$ARGUS_ENGAGEMENTS/<slug>/findings/`, `recon/raw/`, `recon/parsed/`, `artifacts/`, `reports/` — empty dirs
- `$ARGUS_ENGAGEMENTS/<slug>/exec-log.jsonl` — empty file (touch)
- `$ARGUS_ENGAGEMENTS/<slug>/.git/` — initialized + initial commit

## Steps — EXECUTE IN ORDER, DO NOT SKIP

### Step 1: Verify slug is available
```bash
python3 $ARGUS_ROOT/bin/argus engagement check-new <slug>
```
If exit code != 0, **STOP** and report the error to the user. Do NOT proceed.

### Step 2: Scoping wizard (interactive)
Collect the following fields from the user. Use `AskUserQuestion` for closed-set options; direct questions for free text. Group related questions to minimize friction.

**Group 1 — Client identity:**
1. Client legal name (free text)
2. Primary contact: name, email, phone (optional)
3. Technical contact: name, email (optional — may be same as primary)

**Group 2 — Engagement parameters:**
4. Engagement type — `AskUserQuestion` with options:
   `external-pentest`, `internal-pentest`, `webapp`, `mobile`, `cloud`, `redteam`, `adversary-sim`
5. Start date (YYYY-MM-DD)
6. End date (YYYY-MM-DD)
7. Estimated hours (integer)

**Group 3 — Authorization (CRITICAL):**
8. Signed RoE? (Yes / No / Pending)
   - If "No": **WARN** that engagement cannot proceed past pre-engagement. Offer to abort.
   - If "Pending": proceed but set `signed_roe: false`; remind user to update later.
9. If signed: RoE document path (relative to engagement folder, e.g. `artifacts/roe-signed.pdf`)
10. Authorized by (name + role)
11. Signed date (YYYY-MM-DD)

**Group 4 — Scope:**
12. In-scope domains (list)
13. In-scope IP ranges (CIDR list)
14. In-scope web apps (full URLs)
15. In-scope API endpoints (optional)
16. Out-of-scope domains/IPs/notes (**explicit exclusions — IMPORTANT to capture verbatim**)

**Group 5 — Rules of engagement:**
17. Allowed techniques (multiselect):
    `vulnerability-scanning`, `manual-exploitation`, `password-spraying`, `phishing`, `social-engineering`, `physical`
18. Forbidden techniques (default: `destructive-actions`, `dos-attacks`, `data-exfiltration-beyond-poc`; user can add)
19. Testing hours window (default `"24x7"`; otherwise specify timezone + hours)
20. Emergency stop contact (phone or Slack handle)
21. Notification-required actions (list — actions needing client heads-up before doing)

**Group 6 — Deliverables:**
22. Output formats (multiselect: `pdf`, `docx`, `html`, `json`, `markdown` — default `[pdf, docx]`)
23. Language (`en`, `id`, `bilingual`)
24. Components (default all true): `exec-summary`, `technical-report`, `remediation-guide`, `debrief-call`

**Group 7 — Constraints:**
25. Data retention days (default 90)
26. Encryption-at-rest required? (default false)
27. Any other constraints (free text)

### Step 3: Generate scope.yaml and create engagement
Build a YAML document from the template at `$ARGUS_ROOT/templates/scope.yaml`, substituting values from Step 2. Pipe to the CLI:

```bash
cat <<'EOF' | python3 $ARGUS_ROOT/bin/argus engagement create <slug>
<YAML content>
EOF
```

The CLI will:
- Validate scope against schema
- Create folder structure (mkdir all subdirs)
- Write scope.yaml, state.yaml, README.md, .gitignore, exec-log.jsonl
- Initialize per-engagement git repo with initial commit

### Step 4: Handle validation errors
If `argus engagement create` exits nonzero (4 = validation, 5 = engagement error), parse stderr for the specific errors. Show them to the user in a clear list. Offer to:
- Fix specific fields (ask which, re-prompt)
- Abort (the create call is atomic; failure means nothing was written)

Do NOT silently retry. Do NOT mutate user inputs without confirmation.

### Step 5: Confirmation report
On success, print:
- Engagement path
- Current phase: `pre-engagement` (in-progress)
- Scope summary (target count, type, dates)
- Next action: when ready, run `/phase-gate pre-engagement` to validate (v0.6+), then `/recon` (MVP-2+)

## Failure Handling
- If user aborts mid-wizard: save partial answers as draft in chat. Offer to resume. Do NOT write any files.
- If validation fails after CLI call: surface specific errors verbatim. Do not retry blindly.
- If git init fails: engagement folder still exists with files; user can manually `git init` later. Report and continue.

## DO NOT
- Do NOT proceed if `authorization.signed_roe == false` without explicit user override (log the override in exec-log).
- Do NOT overwrite an existing engagement folder. The CLI prevents this; do not work around it.
- Do NOT commit secrets to the per-engagement git. The engagement `.gitignore` blocks common patterns; review staged files before commit.
- Do NOT bypass `argus engagement create` and write files directly — atomicity + validation depend on it.
- Do NOT proceed to other phases (recon, vuln-analysis, etc.) from within this skill — user must explicitly invoke those.

## Why this skill exists
Pre-engagement is where most pentest disasters originate: ambiguous scope, missing RoE, unclear emergency contacts. By enforcing structured capture at Phase 0, every downstream phase has a single source of truth to validate against (anchor principle 1: explicit over inference).
