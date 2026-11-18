---
name: argus-report-draft
description: Assemble a draft pentest report from the engagement's findings + scope + state into reports/draft-vN.md. Optionally export to PDF/DOCX/HTML via pandoc, and optionally dispatch the report-reviewer subagent for QA. CC-safe (pure data assembly, no tool wrappers). Args. --slug (required); --version N (default next); --export {pdf,docx,html} (optional); --review (optional flag).
---
# Skill: /report-draft --slug <slug> [--version N] [--export <fmt>] [--review]

## Purpose
Phase 5 — produce a structured draft report from collected findings, engagement scope, and phase state. Single source of truth for the report becomes `reports/draft-v<N>.md`; exports are derived.

## Input Contract
- **Required**: `--slug <slug>` — engagement slug
- Optional: `--version <int>` — draft version (default: next unused, starting at 1)
- Optional: `--export <fmt>` — also export to PDF/DOCX/HTML
- Optional: `--review` — dispatch the `report-reviewer` subagent after assembly

## Preconditions
1. Engagement exists
2. At least one finding file present (or empty-report acceptance from user)
3. For `--export pdf`: pandoc + texlive-xetex installed
4. For `--review`: report-reviewer subagent definition exists in `.claude/agents/`

## Output Contract
- `engagements/<slug>/reports/draft-v<N>.md` — assembled draft (always)
- `engagements/<slug>/reports/draft-v<N>.<fmt>` — if `--export` used
- `engagements/<slug>/reports/review-v<N>.md` — if `--review` used (produced by subagent)
- Audit events: `report.assemble`, `report.export`, `report.review` in exec-log.jsonl

## Steps — EXECUTE IN ORDER

### Step 1: Verify engagement and findings
```bash
python3 $ARGUS_ROOT/bin/argus engagement status <slug>
python3 $ARGUS_ROOT/bin/argus finding list <slug>
```
If no findings, ask the user: produce an empty-report (covers methodology + scope only) or abort?

### Step 2: Validate findings before assembly
```bash
python3 $ARGUS_ROOT/bin/argus finding validate <slug>
```
If validation errors, list them and ask user: fix first (recommended) or proceed anyway?
Document choice in exec-log via the assembler's audit event.

### Step 3: Assemble draft
```bash
python3 $ARGUS_ROOT/bin/argus report assemble <slug> [--version <N>]
```
Returns path to `draft-v<N>.md`. Print path.

### Step 4: (Optional) Export
If `--export <fmt>` requested:
```bash
python3 $ARGUS_ROOT/bin/argus report export <slug> --format <fmt> [--version <N>]
```
PDF requires xelatex; if missing, suggest install command and continue with MD/DOCX/HTML.

### Step 5: (Optional) Review via subagent
If `--review` requested:
- Spawn the `report-reviewer` subagent via the Agent tool
- Pass: slug, draft_version, full paths to scope/findings/report
- Subagent writes `reports/review-v<N>.md`
- Show user a summary of issues found

### Step 6: Confirmation
Print:
- Path to draft
- Paths to exports (if any)
- Path to review (if any)
- Next steps: review the draft manually, address review issues, bump version with another assemble cycle, then `/handover` (v0.6+)

## Failure Handling
- pandoc missing: state CLI error → suggest install; assembly still succeeded.
- xelatex missing: PDF only; DOCX/HTML still work. Suggest install.
- Subagent failure: report assembled OK; review separate. Report subagent error verbatim.
- Validation errors in findings: do NOT auto-fix. Surface to user.

## DO NOT
- Do NOT modify or generate findings here — only consume existing ones.
- Do NOT manually write the draft in chat — use the CLI assembler so audit + version handling is consistent.
- Do NOT bump phase to "reporting=done" from this skill; that's `/phase-gate reporting` (v0.6+) or manual.
- Do NOT export raw client data outside the engagement folder.

## Why this skill exists
Reports are deliverables — they need consistent structure, deterministic regeneration, and audit trail. By assembling from validated structured data (findings + scope + state) rather than freeform writing, the report is reproducible, easy to update (re-assemble after fixing a finding), and CC-safe (just data → markdown).
