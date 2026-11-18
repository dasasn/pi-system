---
name: vps-hephaestus-spawn-agent
description: Spawn offensive security subagents by loading their prompts and invoking TaskCreate. Supports parallel spawning of multiple agents.
---
# /spawn-agent

Spawn one or more specialized offensive security subagents. Each agent has a
defined contract (OBJECTIVE, TOOLS, OUTPUT) loaded from `~/Hephaestus/agents/{name}.md`.

## Arguments

- `<agent-names>` - Comma-separated list of agent names to spawn.
  Single: `/spawn-agent scout`
  Multiple: `/spawn-agent scout,strike,anchor`

## Available Agents

| Agent | Role |
|-------|------|
| scout | Recon + intel: subdomains, co-hosts, tech fingerprint, LR intel |
| strike | Access agent: credential spraying, default creds, WAF bypass |
| anchor | Post-access: persistence, lateral movement, privilege escalation |
| hunter | Vulnerability hunter: SQLi, XSS, SSRF, path traversal chains |
| navigator | Directory/path discovery, hidden endpoints, API mapping |
| verifier | Finding verification: confirm vulns, generate PoC evidence |
| roaster | Code review agent: identify security flaws in source |
| ad-attacker | Active Directory assessment specialist |
| business-logic-hunter | Business logic flaw discovery |
| cicd-redteam | CI/CD pipeline security assessment |
| cloud-security | Cloud infrastructure security (AWS/GCP/Azure) |

## Procedure

1. **Parse agent names.** Split input on comma, trim whitespace, validate each
   name exists in `~/Hephaestus/agents/`.

2. **Load agent prompts.** For each agent:
   - Read `~/Hephaestus/agents/{name}.md`
   - Extract contract sections: INPUT, EXECUTION, OUTPUT, CONTEXT RULES
   - Inject current campaign context (target, campaign_id, output paths)

3. **Spawn via TaskCreate.** For each agent, invoke TaskCreate with:
   - `subject`: `[{agent-name}] {role description}`
   - `description`: Full agent prompt with injected context
   - `metadata`: `{agent: name, campaign: campaign_id, spawned_at: timestamp}`

4. **Return task IDs.** Report spawned task IDs for monitoring via TaskGet/TaskList.

## Context Injection

Before spawning, the skill injects runtime context into the agent prompt:

```
RUNTIME CONTEXT:
  target:   {from current engagement or user-provided}
  campaign: {campaign_id from state.json or engagement slug}
  output:   ~/Hephaestus/campaigns/{campaign_id}/state.json
  known:    {summary from previous phase output}
```

## Parallel Spawning

When multiple agents are specified, they spawn in parallel. Each agent receives
the same base context but operates independently. Use for:

- Concurrent recon phases: `/spawn-agent scout,navigator`
- Full attack chain: `/spawn-agent scout,strike,anchor`
- Specialized hunting: `/spawn-agent hunter,business-logic-hunter,verifier`

## Output

Returns structured result:

```json
{
  "spawned": [
    {"agent": "scout", "task_id": "task-xxx", "status": "pending"},
    {"agent": "strike", "task_id": "task-yyy", "status": "pending"}
  ],
  "errors": [],
  "monitor_command": "Use TaskList or TaskGet to monitor progress"
}
```

## Constraints

- **DO** verify agent file exists before attempting to spawn.
- **DO** inject current campaign context into the prompt.
- **DO** return task IDs for monitoring.
- **DO NOT** spawn agents for campaigns without defined targets.
- **DO NOT** modify agent prompt files during spawn.
- **DO NOT** spawn duplicate agents for the same target in the same session.

## Error Handling

- Agent file not found: Report error, continue with remaining agents.
- No target defined: Prompt user for target before spawning.
- TaskCreate fails: Report error with details, do not retry automatically.
