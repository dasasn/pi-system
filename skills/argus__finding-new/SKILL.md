---
name: argus-finding-new
description: Create a new finding for the active engagement. Walks through finding wizard (title, severity, CVSS, target, evidence, remediation), validates against schema, writes findings/F-NNN-<slug>.md with required frontmatter and section structure. Auto-creates artifacts/F-NNN/ dir for evidence files. Args. optional --slug <slug>.
---
# Skill: /finding-new [--slug <slug>]

## Purpose
Create a single finding document with citation-enforced frontmatter (anchor principle 3). Every finding MUST include: tool used, command run, raw output excerpt, timestamp. No exceptions.

## Input Contract
- Optional `--slug <slug>` — engagement slug. If omitted: list engagements; if one active, use it; otherwise ask user.

## Preconditions
1. Engagement exists
2. `current_phase` is `recon` (done), `vuln-analysis`, `exploitation`, or `post-exploitation`
3. (Recommended) the target referenced was scanned in recon (check `recon/parsed/<target>/`)

## Output Contract
- `engagements/<slug>/findings/F-NNN-<kebab-slug>.md` — validated against schema
- `engagements/<slug>/artifacts/F-NNN/` — empty dir for evidence files
- `state.yaml`: `findings_count.<severity>` incremented
- Audit event in `exec-log.jsonl`

## Steps — EXECUTE IN ORDER

### Step 1: Determine engagement
```bash
python3 $ARGUS_ROOT/bin/argus engagement list
```
Pick or ask via AskUserQuestion.

### Step 2: Finding wizard (interactive)
Collect fields via AskUserQuestion (closed-set) or direct text (open). Group:

**Identification:**
1. Title (short, descriptive, e.g. "SQL Injection in /login parameter username")
2. Severity — AskUserQuestion: `critical`, `high`, `medium`, `low`, `info`
3. CVSS score (0.0-10.0, numeric)
4. Status — AskUserQuestion: `draft`, `needs-verification`, `confirmed`, `false-positive`, `duplicate`, `out-of-scope` (default: `needs-verification` if user has working PoC, else `draft`)

**Discovery context:**
5. Target (must be in `scope.in_scope` — recommend pulling from recon outputs)
6. Discovery phase — AskUserQuestion: `recon`, `vuln-analysis`, `exploitation`, `post-exploitation`
7. Tools used (list — must be non-empty; e.g. `["sqlmap", "burp"]`)

**Evidence (CRITICAL — anti-hallucination):**
8. Evidence files — list of relative paths from engagement root. MUST be non-empty.
   - Example: `["artifacts/F-NNN/sqlmap-output.txt", "artifacts/F-NNN/screenshot.png"]`
   - If user doesn't have evidence yet, instruct: save tool output to `artifacts/F-NNN/` first, then re-invoke.

**Optional context:**
9. References (URLs, CVE IDs, CWE numbers — list of strings)
10. CWE numbers (e.g. `["CWE-89"]`)

**Remediation:**
11. Remediation summary (one-line; e.g. "Parametrize queries; deploy WAF as compensating control")
12. (Optional) Detailed description, reproduction steps, impact analysis, full remediation

### Step 3: Create the finding
Use the CLI (validated):
```bash
python3 $ARGUS_ROOT/bin/argus finding new <slug> \
  --title "<title>" \
  --severity <severity> \
  --cvss <cvss> \
  --target "<target>" \
  --phase <phase> \
  --tool <tool1> --tool <tool2> ... \
  --evidence "<path1>" --evidence "<path2>" ... \
  --remediation "<remediation-summary>" \
  --status <status> \
  [--reference "<url1>" --reference "<url2>" ...]
```

### Step 4: Handle validation errors
If CLI exits nonzero (4 = validation, 5 = engagement error):
- Show errors verbatim
- Ask user to fix specific fields (re-prompt only the offending ones)
- Do NOT silently retry

### Step 5: Confirmation
On success:
- Print finding ID + path
- Suggest: open the finding file to fill in Description / Reproduction / Impact / Remediation sections
- Remind user to copy evidence files into `artifacts/F-NNN/`
- Show updated counts: `argus engagement status <slug>`

## Failure Handling
- Evidence list empty → STOP. Tell user to save evidence first. Do not create.
- Target not in scope → STOP. Tell user to add to scope (RoE amendment) or skip.
- Validation failure → surface errors. Do not auto-fix.

## DO NOT
- Do NOT create findings without tool + command + raw output evidence. This is the anti-hallucination guard. Without evidence, you're fabricating.
- Do NOT use generic placeholder titles ("Vulnerability in <thing>"). Be specific.
- Do NOT assign severity by feel. CVSS calculator on the actual attack vector + impact.
- Do NOT write findings in chat — always via this skill so validation + audit + counter all run.
- Do NOT skip the wizard "because user already knows the fields". Capture each field via the wizard so they end up in audit and frontmatter.

## Why this skill exists
Findings are the engagement's deliverable. A fabricated or under-documented finding poisons the report. The frontmatter schema + CLI validation guarantee every claim has machine-checkable provenance (tool used, evidence path, timestamp, discovery phase). Auditors (or future-you reviewing the report) can re-verify every finding from the evidence.
