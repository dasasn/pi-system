---
name: argus-triage
description: Phase 2 — Dispatch registered analysis modules against the active engagement. Validates phase preconditions, calls modules via the plugin contract (implementations live in sibling argus-modules repo), surfaces duplicate findings, runs schema validation. This skill is phase-shape only and contains no technique-specific logic. Args. optional --slug; --module <name>; --target <t> (repeatable).
---
# Skill: /triage [--slug <slug>] [--module <name>] [--target <t>...]

## Purpose
Phase 2 orchestration. Read recon outputs, dispatch registered analysis modules, collect structured results, validate the resulting findings against schema, surface duplicates. **Phase-shape only** — implementation of any specific analysis technique lives in sibling repo ``argus-modules`` (registered via Python entry points).

## Input Contract
- Optional `--slug <slug>` — engagement slug
- Optional `--module <name>` — specific module to dispatch (default: list available and ask)
- Optional `--target <t>` (repeatable) — narrow to subset of in-scope targets (default: all)

## Preconditions
1. Engagement exists
2. `current_phase` ∈ {`recon` (done), `vuln-analysis`}
3. `recon/summary.yaml` exists
4. At least one module registered for phase `vuln-analysis` (else: tell user to install argus-modules)

## Output Contract
Per dispatched module:
- `engagements/<slug>/triage/<module-name>/` — module's output artifacts
- Findings auto-created via plugin contract (modules call `lib.findings.create_finding`)
- Audit events in `exec-log.jsonl` (`triage.dispatch.start`, `.done`, `.fail`)

Plus:
- Duplicate-candidate report (informational; operator resolves)
- Phase state advanced (vuln-analysis: in-progress → done) only after operator confirms

## Steps — EXECUTE IN ORDER

### Step 1: Determine engagement
```bash
python3 $ARGUS_ROOT/bin/argus engagement list
```

### Step 2: Verify preconditions
```bash
python3 $ARGUS_ROOT/bin/argus engagement status <slug>
```
If recon not done, STOP and tell user to complete recon first.

### Step 3: List available modules
```bash
python3 $ARGUS_ROOT/bin/argus triage list-modules
```
If empty: tell user that no analysis modules are registered. Suggest installing the sibling repo:
```bash
pip install -e ~/argus-modules
```
Then STOP — no point dispatching nothing.

### Step 4: Transition phase
```bash
python3 $ARGUS_ROOT/bin/argus engagement update-phase <slug> vuln-analysis in-progress
```

### Step 5: Dispatch
For each module the operator selected:
```bash
python3 $ARGUS_ROOT/bin/argus triage run <slug> --module <module-name>
```
The CLI:
- Validates module is registered
- Builds `ModuleContext` from engagement + targets
- Calls `module.run(ctx)`
- Persists artifacts to `triage/<module-name>/`
- Emits audit event with status

### Step 6: Check for duplicate candidates
```bash
python3 $ARGUS_ROOT/bin/argus triage dedupe-check <slug>
```
If candidates surfaced, show pairs and ask operator how to resolve:
- Mark one as `duplicate` (edit its frontmatter `status`)
- Merge content (manual)
- Confirm they are NOT duplicates (no action needed)

### Step 7: Validate findings
```bash
python3 $ARGUS_ROOT/bin/argus finding validate <slug>
```
Every finding must pass schema validation.

### Step 8: Advance phase (operator confirms)
Only after Steps 5–7 are clean:
```bash
python3 $ARGUS_ROOT/bin/argus engagement update-phase <slug> vuln-analysis done
```

## DO NOT
- Do NOT implement analysis techniques in this skill, in `argus/lib/`, or in subagent prompts. Implementations belong in `argus-modules`.
- Do NOT bypass the plugin contract. If a module isn't registered, install it; do not inline.
- Do NOT mark phase done while duplicates are unresolved or schema validation fails.
- Do NOT proceed to phase 3 within this skill.

## Why this skill exists
Keeping the orchestration in `argus/` while pushing implementations to `argus-modules` gives us: (a) a CC-safe core that's freely refactorable; (b) module portability across operators; (c) a clean separation of *what to do* (orchestrator) vs *how to do it* (module). See ``docs/workflow-architecture.md`` for the full rationale.
