---
name: vps-hephaestus-report-draft
description: Assemble the engagement report by running the hephaestus reporter. Validates all findings, renders the Markdown report, writes it under reports/, and shows the user a preview.
---
# /report-draft

Generate the engagement report.

## Arguments

- `--slug <slug>` — engagement slug. If absent, ask the user.
- `--version <version-tag>` — defaults to `v1.0-draft`.
- `--classification <label>` — defaults to `CONFIDENTIAL`.

## Procedure

1. **Confirm engagement.** Run `hephaestus engagement status <slug>`. Confirm
   the current phase is at or past `reporting` (or the user has
   explicitly asked for an interim draft).

2. **Validate scope and state.**

   ```
   hephaestus engagement validate <slug>
   ```

   If errors, surface them and stop. Reports must not be generated from
   invalid state.

3. **Validate every finding.** For each file under
   `<engagement>/findings/F-*.md`:

   ```
   hephaestus finding validate <path>
   ```

   Aggregate any errors. If any finding fails validation, do NOT render
   the report. Show the user which findings need to be fixed first.

4. **Render the report.**

   ```
   hephaestus report write --slug <slug> --version <version> --classification <label>
   ```

   The output file lands at `<engagement>/reports/report-<version>.md`.

5. **Show summary.** Report to the user:
   - Number of findings included (by severity)
   - Output file path
   - Word count or section count of the rendered file
   - Suggestion to review the executive summary and remediation table
     before sharing externally

6. **Offer next steps.**
   - Convert to PDF via the user's preferred toolchain (pandoc,
     weasyprint, etc.).
   - Iterate: if the user wants additional content, point them to the
     specific section template under `templates/report/`.

## Constraints

- **DO NOT** modify finding files during report generation. The report
  is a read-only aggregation.
- **DO NOT** synthesize findings or summary statements that are not
  backed by an actual finding file (anti-hallucination guard).
- **DO** record the report version in the file path and inside the
  cover page. Multiple drafts coexist for traceability.

## Failure modes

If templates fail to render due to a missing field, the error message
will name the offending template. Fix the underlying scope/state/finding
data — do not patch templates to be lenient about missing data.
