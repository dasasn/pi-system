---
name: vps-hephaestus-hephaestus-loop-deploy
description: >-
  Long-running deploy polling for Hephaestus — GSocket, upload_rce, verify.txt.
  Use when operator asks to watch deploy, poll GSocket, or /loop strike status.
  Runs /loop pattern with evidence file checks every N minutes until channel up.
---
# Hephaestus deploy loop

## When to use

- GSocket deploy in progress (`deploy_gsocket_feedback.py`)
- `upload_rce_deliver.py` waiting on relay window
- Operator: `/loop 5m check GSocket for <target>`

## Parse

Accept `/loop [interval] <prompt>` or explicit "poll every Nm".

## Fixed loop (preferred for deploy)

```bash
while true; do
  sleep <seconds>
  echo 'AGENT_LOOP_TICK_gsocket {"prompt":"Check GS_DEPLOY_RESULTS.json and verify.txt for <target>; run next track if incomplete"}'
done
```

1. Run check **once immediately** before arming loop.
2. Background loop with `notify_on_output` on `^AGENT_LOOP_TICK_gsocket`.
3. Each tick:
   - Read `campaigns/<target>/evidence/GS_DEPLOY_RESULTS.json`
   - `gs-netcat -t` or connect line if secret present
   - `curl -sSf` verify.txt paths from summary
4. Stop loop when GSocket interactive + verify pass, or operator cancels.

## Evidence

Update `STRIKE_PROGRESS.md` only after reading JSON — never chat-only status.

## Forbidden

- Stop loop at first failure without 1 variation
- Ask permission to continue — pivot track and re-arm
