---
name: vps-hephaestus-engagement-start
description: Initialize a new engagement with a scoping wizard. Walks through Rules of Engagement, client info, scope, timeline, constraints. Validates each input and creates the engagement folder via `hephaestus engagement create`.
---
# /engagement-start

Start a new engagement. Drive the user through a structured scoping wizard,
build a `scope.yaml`, and create the engagement via the CLI.

## Arguments

- `<client-slug>` (kebab-case, 3-64 chars matching `^[a-z0-9][a-z0-9-]{1,62}[a-z0-9]$`).
  If the user omits it, ask for it as the first step.

## Procedure

1. **Validate slug.** If the supplied slug fails the regex, stop and ask
   for a valid one. Do NOT silently fix it for the user.

2. **Check uniqueness.** Run `hephaestus engagement list` to confirm the slug
   is not already in use. If it is, surface the existing engagement and
   ask the user whether to pick a different slug.

3. **Drive the scoping wizard.** Capture each section as a separate
   conversation turn. Do NOT batch all questions into one mega-prompt.
   Sections:

   1. **Client identity** — name, legal entity, primary contacts (name,
      email, role, phone), emergency contact.
   2. **Timeline** — start date, end date, any named milestones (kickoff,
      interim review, final readout).
   3. **In-scope assets** — one or more items of `kind` ∈
      {host, network, web_app, api, mobile, user_account, other} with
      target identifier and optional notes.
   4. **Out-of-scope assets** — same shape; optional.
   5. **Authorization** — is the RoE signed? if yes, capture signed_at,
      signed_by, document_ref. If no, warn the user that engagement
      cannot leave `pre-engagement` until RoE is signed (phase gate).
   6. **Operational constraints** — time window, allowed local hours,
      rate limits, prohibited actions, and permitted-action flags
      (data exfiltration, credential capture, persistence).
   7. **Methodology** — default `PTES`; user may pick another (OWASP-WSTG,
      OSSTMM, custom).
   8. **Notes** — free-form, optional.

4. **Build the scope YAML.** Use `templates/scope.example.yaml` as the
   structural reference. Write the assembled scope to a temporary file
   (e.g. `/tmp/<slug>-scope.yaml`) and validate it against the schema
   before invoking the CLI.

5. **Create the engagement.** Run:

   ```
   hephaestus engagement create --from-file /tmp/<slug>-scope.yaml
   ```

   On success, report the engagement folder path back to the user. On
   failure, surface the exact error message — do not invent fixes.

6. **Show status.** Run `hephaestus engagement status <slug>` and present
   the result to the user.

## Constraints (DO and DO NOT)

- **DO** ask the user when anything is ambiguous; never invent scope, RoE
  provisions, or contact details.
- **DO** record `authorization.signed_roe=false` if the RoE is not signed
  yet — do not flip it to `true` to "be helpful".
- **DO NOT** create folders by hand. Use the CLI.
- **DO NOT** skip any section even if the user says "just defaults" — the
  RoE and timeline are non-optional for compliance.

## Failure modes

If the CLI rejects the scope, present the validation errors verbatim and
loop back to the relevant wizard section. Do not retry with synthetic
inputs.
