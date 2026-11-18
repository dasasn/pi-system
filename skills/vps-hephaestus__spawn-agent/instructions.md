# Spawn Agent - Implementation Instructions

This document provides detailed implementation guidance for the `/spawn-agent` skill.

## Execution Flow

### Step 1: Parse Arguments

```python
# Input: "scout,strike,anchor" or "scout"
raw_input = args.strip()
agent_names = [name.strip() for name in raw_input.split(',')]

# Validate against known agents
VALID_AGENTS = [
    'scout', 'strike', 'anchor', 'hunter', 'navigator', 'verifier',
    'roaster', 'ad-attacker', 'business-logic-hunter', 'cicd-redteam',
    'cloud-security'
]

for name in agent_names:
    if name not in VALID_AGENTS:
        raise ValueError(f"Unknown agent: {name}")
```

### Step 2: Load Agent Prompts

For each agent, read the prompt file:

```bash
AGENTS_DIR="~/Hephaestus/agents"

# Check file exists
if [ -f "$AGENTS_DIR/${agent_name}.md" ]; then
    agent_prompt=$(cat "$AGENTS_DIR/${agent_name}.md")
else
    echo "ERROR: Agent file not found: $AGENTS_DIR/${agent_name}.md"
    exit 1
fi
```

### Step 3: Extract Contract Sections

Agent prompts follow the SPAWN_TEMPLATE.md format with these sections:

- **Role/Mission header**: First paragraph describes agent purpose
- **INPUT**: Expected inputs (target, campaign, output path)
- **EXECUTION**: Step-by-step procedure
- **OUTPUT**: Expected output format (usually JSON to state.json)
- **CONTEXT RULES**: Output constraints (line limits, file paths)

Parse these sections to understand agent contract:

```python
import re

def parse_agent_contract(prompt_content):
    """Extract contract sections from agent prompt."""
    sections = {}
    
    # Extract role from first header
    role_match = re.search(r'^#\s+(.+?)\s*[—-]', prompt_content, re.MULTILINE)
    sections['role'] = role_match.group(1) if role_match else 'Agent'
    
    # Extract INPUT section
    input_match = re.search(r'## INPUT\s*```(.*?)```', prompt_content, re.DOTALL)
    sections['input'] = input_match.group(1).strip() if input_match else ''
    
    # Extract EXECUTION section (all steps)
    exec_match = re.search(r'## EXECUTION(.*?)(?=## OUTPUT|## CONTEXT|$)', prompt_content, re.DOTALL)
    sections['execution'] = exec_match.group(1).strip() if exec_match else ''
    
    # Extract OUTPUT section
    output_match = re.search(r'## OUTPUT.*?```(.*?)```', prompt_content, re.DOTALL)
    sections['output'] = output_match.group(1).strip() if output_match else ''
    
    return sections
```

### Step 4: Inject Runtime Context

Before spawning, inject current engagement context:

```python
def inject_context(agent_prompt, context):
    """Inject runtime context into agent prompt."""
    
    context_block = f"""
---
RUNTIME CONTEXT (injected by spawn-agent):
  target:   {context.get('target', 'NOT_SET')}
  campaign: {context.get('campaign', 'NOT_SET')}
  output:   ~/Hephaestus/campaigns/{context.get('campaign', 'unknown')}/state.json
  known:    {context.get('known', 'Starting fresh - no prior intel')}
  spawned:  {context.get('timestamp', 'unknown')}
---

"""
    return context_block + agent_prompt
```

### Step 5: Spawn via TaskCreate

Use TaskCreate tool to spawn each agent:

```python
# For each agent
TaskCreate(
    subject=f"[{agent_name.upper()}] {sections['role']}",
    description=injected_prompt,
    activeForm=f"Running {agent_name} agent",
    metadata={
        "agent": agent_name,
        "campaign": context['campaign'],
        "target": context['target'],
        "spawned_at": timestamp,
        "output_path": f"~/Hephaestus/campaigns/{context['campaign']}/state.json"
    }
)
```

### Step 6: Track and Return Results

Collect task IDs and return structured result:

```python
results = {
    "spawned": [],
    "errors": [],
    "monitor_command": "Use TaskList to see all running agents"
}

for agent_name, task_id in spawned_tasks:
    results["spawned"].append({
        "agent": agent_name,
        "task_id": task_id,
        "status": "pending"
    })
```

## Autonomous Blocker Resolution

All agents inherit the standard blocker resolution from SPAWN_TEMPLATE.md:

```
SELF-RESOLVE (never ask user, never stop):
- Blocked on vector A (>3 min) -> switch to vector B automatically
- Rate-limited -> wait 30s -> retry ONCE -> pivot if still blocked
- WAF block -> switch to Playwright path
- 403/401 -> try headers bypass, path fuzzing, different subdomain
- Timeout -> try different subdomain or co-host on same server
- All vectors for THIS target exhausted -> move to co-host
- All co-hosts exhausted -> report "ALL VECTORS EXHAUSTED"

ESCALATE TO ORCHESTRATOR ONLY:
- Ethical boundary or destructive action outside scope
- Scope expansion: new domain/target discovered
- Access gained -> STOP ALL -> report immediately
```

## Agent Coordination Patterns

### Sequential Chain
```
/spawn-agent scout
# Wait for scout to complete
/spawn-agent strike
# Wait for strike to complete
/spawn-agent anchor
```

### Parallel Recon
```
/spawn-agent scout,navigator,hunter
# All three run concurrently
```

### Full Auto-Strike
```
/spawn-agent scout,strike,anchor
# Orchestrator monitors state.json for phase transitions
```

## State File Integration

Agents write results to `state.json` in the campaign directory:

```json
{
  "phase": "scout_complete",
  "ip": "x.x.x.x",
  "cohosts_total": 15,
  "cohosts_high": ["vuln-site.com", "legacy.target.com"],
  "subdomains_count": 42,
  "lr_total": 128,
  "lr_weak": 23,
  "spray_targets": ["https://target.com/login", "https://admin.target.com"],
  "sensitive_files": [".env", ".git/config"],
  "nuclei_findings": ["CVE-2024-1234"],
  "scout_verdict": "proceed",
  "next_agent": "strike"
}
```

The orchestrator reads this file to determine next steps.

## Error Handling

### Agent File Not Found
```python
if not os.path.exists(f"{AGENTS_DIR}/{agent_name}.md"):
    results["errors"].append({
        "agent": agent_name,
        "error": "Agent prompt file not found",
        "path": f"{AGENTS_DIR}/{agent_name}.md"
    })
    continue  # Skip this agent, continue with others
```

### No Target Defined
```python
if not context.get('target'):
    # Prompt user for target
    print("No target defined. Please provide target domain/IP:")
    # Or check for active engagement
    engagement = get_active_engagement()
    if engagement:
        context['target'] = engagement.primary_target
```

### TaskCreate Failure
```python
try:
    task = TaskCreate(...)
except Exception as e:
    results["errors"].append({
        "agent": agent_name,
        "error": f"TaskCreate failed: {str(e)}"
    })
```

## Monitoring Spawned Agents

After spawning, use these commands to monitor:

```bash
# List all tasks
TaskList

# Get specific task status
TaskGet task_id="task-xxx"

# Check campaign state file
cat ~/Hephaestus/campaigns/{campaign}/state.json | jq .
```

## Example Usage

### Single Agent
```
User: /spawn-agent scout
Claude: Spawning scout agent for target example.com...

[TaskCreate: subject="[SCOUT] Recon + Intel Agent", ...]

Spawned 1 agent:
- scout: task-abc123 (pending)

Monitor with TaskList or check campaigns/example-com/state.json
```

### Multiple Agents
```
User: /spawn-agent scout,strike,anchor
Claude: Spawning 3 agents for target example.com...

[TaskCreate: scout]
[TaskCreate: strike]
[TaskCreate: anchor]

Spawned 3 agents:
- scout: task-abc123 (pending)
- strike: task-def456 (pending)  
- anchor: task-ghi789 (pending)

All agents running in parallel. Monitor with TaskList.
```
