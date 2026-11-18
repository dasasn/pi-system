---
name: vps-hephaestus-finding-new
description: Capture a new finding (vulnerability or issue) for the active engagement. Walks the user through structured fields, validates, and creates the finding via `hephaestus finding new`. This is the ONLY way to record findings — never write them freeform in chat (anti-hallucination guard).
---
# /finding-new

Create a new finding. Drive the user through structured capture, build
a finding draft YAML, and invoke the CLI to persist it.

## Arguments

- `--slug <slug>` — engagement slug. If absent, ask the user which
  engagement is active. Do NOT guess.

## Procedure

1. **Confirm engagement.** Run `hephaestus engagement status <slug>` to load
   context. Confirm the engagement exists and what phase it's in. The
   finding will be tagged with the current phase.

2. **Capture fields.** Ask separately, one focused turn each:

   1. **Title** — concise, specific, 3-200 chars.
   2. **Severity** — one of: critical, high, medium, low, info.
   3. **Target** — affected target identifier. SHOULD match an in-scope
      item from `scope.yaml`; if it does not, warn the user and confirm.
   4. **Tools used** — list of tool identifiers used to discover or
      validate the finding.
   5. **Evidence** — at least one Evidence item is required. For each:
      - `kind`: command_output | request_response | screenshot |
        raw_file | log_excerpt | observation
      - `source`: module name or `manual`
      - `description`: one-line summary
      - `excerpt` (optional, for short inline content) OR
      - `artifact_path` (relative path to a fuller artifact under the
        engagement folder)
   6. **Remediation summary** — one or two sentences. Concrete action.
   7. **References** — list of URLs / CVE IDs / OWASP refs. Optional.
   8. **CVSS** (optional but recommended for severity ≥ medium) — vector
      string + numeric score. The CVSS-derived severity must match the
      `severity` field, or the user must explicitly state the contextual
      reason for the divergence.
   9. **Description** and **Impact** — the narrative body. Description
      is the technical writeup; Impact is what an attacker can achieve.
      Both can be multi-paragraph.

3. **Assemble draft.** Build a YAML file with all captured fields except
   `id` (the CLI will allocate it). Status defaults to `draft`.
   `discovered_by_phase` defaults to the engagement's current phase
   (read from state).

4. **Validate locally.** Sanity-check before invoking the CLI:
   - At least one evidence item present.
   - Remediation summary non-empty.
   - If severity = critical/high, at least one of: tools_used OR a CVSS
     score is recorded (encourages strong citation on high-impact items).

5. **Persist via CLI.**

   ```
   hephaestus finding new --slug <slug> --from-file /tmp/<slug>-finding-draft.yaml
   ```

   On success, report the assigned ID and file path back to the user.

6. **List findings.** Run `hephaestus finding list --slug <slug>` so the user
   sees the new finding alongside the rest.

## Constraints

- **DO NOT** write the finding to the engagement folder by hand — use
  the CLI. The CLI also updates `state.yaml` counters atomically.
- **DO NOT** ever claim a finding in chat without writing it through
  this skill. If the user reports a vulnerability mid-conversation,
  capture it through this skill or explicitly mark it as "informal note,
  not yet a finding" and ask whether to formalize.
- **DO** preserve verbatim output and request/response pairs in the
  `excerpt` field. Truncate only if necessary, and mark truncation with
  `[...truncated...]`.
- **DO** assign severity conservatively. When unsure between two levels,
  pick the lower and note the higher as a possibility in the
  description.

## Failure modes

If the CLI rejects the draft, surface the exact validation errors and
loop back to fix only the offending field(s). Do not re-prompt the user
for fields that were already accepted.
