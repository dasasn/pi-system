---
name: vps-hephaestus-phase-gate
description: Validate that the engagement's current phase meets its exit criteria and (optionally) advance to the next phase. Use before starting any new phase's work.
---
# /phase-gate

Check phase exit criteria and advance if they pass.

## Arguments

- `--slug <slug>` — engagement slug. If absent, ask the user.
- `--advance` — if set, transition to the next phase after the gate passes.
  Default: report only, do not advance.

## Procedure

1. **Load engagement state.**

   ```
   hephaestus engagement status <slug>
   ```

   Identify the current phase.

2. **Validate scope + state files.**

   ```
   hephaestus engagement validate <slug>
   ```

3. **Apply phase-specific gate checks.** The CLI enforces a minimum gate
   (e.g. RoE signed before leaving pre-engagement). For each phase,
   apply these additional explicit checks before recommending advance:

   - **pre-engagement → recon:**
     - `scope.yaml` valid
     - `authorization.signed_roe == true`
     - `authorization.document_ref` non-empty
     - At least one item in `in_scope`

   - **recon → triage:**
     - `<engagement>/recon/summary.yaml` exists and `ok: true`
     - At least one module ran successfully

   - **triage → analysis:**
     - At least one finding present OR a `findings/.no-findings`
       marker file exists

   - **analysis → exploitation:**
     - All findings with severity ≥ high have `status` set to
       `confirmed` or `false-positive` (no `draft` or `open`)

   - **exploitation → post-exploitation:**
     - For each finding with `status: confirmed`, at least one evidence
       item references an artifact under `artifacts/<finding_id>/`

   - **post-exploitation → reporting:**
     - (no additional gate beyond validate)

   - **reporting → handover:**
     - At least one report file exists under `<engagement>/reports/`

   - **handover → closed:**
     - All findings have a terminal status (`fixed`, `accepted-risk`, or
       `false-positive`) OR an explicit `<engagement>/HANDOVER.md`
       documents outstanding items

4. **Report the gate result.**
   - If all checks pass: print "gate OK" and the next phase.
   - If any fail: list every failed check verbatim. Do not paraphrase.

5. **Advance (only if `--advance` set AND gate passed).**

   ```
   hephaestus engagement advance <slug> <next-phase>
   ```

## Constraints

- **DO NOT** advance if any gate check failed, even if the user insists.
  If they want to override, they must fix the underlying issue or
  explicitly document the deviation in a note.
- **DO NOT** invent new gate criteria. Use this skill's list verbatim;
  changes are made by editing this file, not by ad-hoc reasoning.
