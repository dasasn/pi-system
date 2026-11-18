# SKILL: report — Structured Findings + Evidence + ATT&CK Mapping

**Purpose:** Generate structured pentest reports from engagement findings. All findings → structured document → ATT&CK technique mapping → evidence打包 → report deliverable.

**Type:** report | **Version:** 1.0 | **Author:** Hephaestus v6.0

---

## EXECUTION CONTEXT

```
Role: brain orchestrator — direct Bash for evidence collection + report generation
Trigger: Engagement complete (win or blocked/exhausted)
Model: sonnet for report structuring, haiku for formatting
```

---

## PHASE STRUCTURE

### PHASE 0 — COLLECT ALL EVIDENCE

**Step 0.1: Gather from all sources**
```bash
cd ~/Hephaestus

CAMPAIGN="campaign_name"
TARGET="target.com"

# From state file
cat state/campaigns/${CAMPAIGN}.json 2>/dev/null | python3 -m json.tool

# From output directory
ls -la output/${CAMPAIGN}/ 2>/dev/null
cat output/${CAMPAIGN}/recon_summary.txt 2>/dev/null
cat output/${CAMPAIGN}/nuclei_*.txt 2>/dev/null
cat output/${CAMPAIGN}/spray_results.txt 2>/dev/null
cat output/${CAMPAIGN}/confirmed_logins.txt 2>/dev/null

# From campaign state
ls campaigns/${CAMPAIGN}/ 2>/dev/null

# Screenshot evidence
ls -la ~/Hephaestus/integrations/telegram_inbox/ | grep "${TARGET}" | head -10
```

**Step 0.2: Categorize findings by severity**
```bash
# CRITICAL (RCE, shell deployed, DB access)
# HIGH (admin access, SQLi exploitable, config exposed)
# MEDIUM (XSS, IDOR, weak creds)
# LOW (info disclosure, tech fingerprint)

# Create finding categories
mkdir -p output/${CAMPAIGN}/report_evidence/
mkdir -p output/${CAMPAIGN}/report_evidence/critical/
mkdir -p output/${CAMPAIGN}/report_evidence/high/
mkdir -p output/${CAMPAIGN}/report_evidence/medium/
mkdir -p output/${CAMPAIGN}/report_evidence/low/
```

---

### PHASE 1 — STRUCTURED FINDINGS

**Step 1.1: Generate finding template per vulnerability**
```bash
cat > output/${CAMPAIGN}/report/findings.md << 'EOF'
# PENTEST REPORT: {target.com}
Date: {YYYY-MM-DD}
Operator: Pluto (authorized pentest)

## EXECUTIVE SUMMARY
{Brief paragraph: what was found, what's at risk, what was achieved}

## SCOPE
- {target.com}
- {additional targets if any}
- Attack type: {blackbox/greybox/mixed}

## FINDINGS

### Finding #1: [CRITICAL] {Title}
**Severity:** CRITICAL
**CVSS:** 9.8 (example)
**CVEs:** CVE-XXXX-XXXXX

**Description:**
{Detailed description of the vulnerability}

**Affected Component:**
- URL: {affected URL}
- Parameter: {vulnerable parameter}
- Technology: {CMS/Server/Framework}

**Attack Chain:**
{Step-by-step reproduction}

**Evidence:**
```
{Command output, screenshots, curl commands}
```

**Impact:**
{What an attacker can achieve}

**Remediation:**
1. {Fix step 1}
2. {Fix step 2}
3. {Fix step 3}

**ATT&CK Mapping:**
- T1190: Exploitation for Privilege Escalation
- T1059: Command and Scripting Interpreter

---
EOF
```

**Step 1.2: Finding examples per type**
```bash
# CRITICAL: SQLi exploitable → RCE
cat >> output/${CAMPAIGN}/report/findings.md << 'EOF'
### [#] SQL Injection → Database Dump → Admin Access → Webshell → RCE
**Severity:** CRITICAL
**CVEs:** N/A (logic exploitation)

**Finding Chain:**
1. SQLi detected on /page.php?id=1
2. sqlmap confirmed UNION-based injection
3. Database dumped: 1,247 user records with MD5 passwords
4. 3 admin accounts cracked (rockyou.txt)
5. Admin panel accessed → plugin upload → webshell
6. GSocket deployed → persistent C2 access

**Evidence:**
```bash
sqlmap -u "https://target.com/page.php?id=1" --dbs
# Databases: target_db, information_schema

sqlmap -u "https://target.com/page.php?id=1" -D target_db -T wp_users --dump
# User: admin | Hash: 5f4dcc3b5aa765d61d8327deb882cf99 (password)

curl -s "https://target.com/shell.php?cmd=id"
# uid=33(www-data) gid=33(www-data)
```
EOF

# CRITICAL: .env exposed → DB/SSH access
cat >> output/${CAMPAIGN}/report/findings.md << 'EOF'
### [#] .env File Exposed → Database + SSH Credentials
**Severity:** CRITICAL

**Finding:**
.env file accessible at https://target.com/.env (HTTP 200)
Contains: APP_KEY, DB credentials, AWS keys, Mail credentials

**Evidence:**
```bash
curl -s "https://target.com/.env"
# APP_KEY=base64:XXXXXXXXXXXXXX
# DB_HOST=target.com
# DB_PASSWORD=P@ssw0rd123!
# SSH_KEY=-----BEGIN RSA PRIVATE KEY-----
```
EOF

# HIGH: Admin panel accessible with weak creds
# MEDIUM: IDOR in user profile endpoint
# LOW: Server version disclosure in headers
```

---

### PHASE 2 — ATT&CK MAPPING

**Step 2.1: Map every finding to ATT&CK technique**
```bash
# ATT&CK Framework v13 — common techniques for web pentest

ATTACK_MATRIX="
| Finding Type | Tactic | Technique | ID |
|--------------|--------|-----------|-----|
| SQLi | Initial Access | Exploitation for Privilege Escalation | T1190 |
| SQLi → dump | Collection | Unstructured Data Collection | T1213 |
| Admin login | Initial Access | Valid Accounts | T1078 |
| Upload RCE | Initial Access | Exploitation for Privilege Escalation | T1190 |
| .env exposed | Discovery | Container API Discovery | T1613 |
| GSocket shell | Command and Control | Non-Application Layer Protocol | T1095 |
| SSH key added | Persistence | SSH Authorized Keys | T1098.004 |
| Internal pivot | Lateral Movement | Remote Services | T1021 |
| .git exposed | Discovery | Cloud Infrastructure Discovery | T1530 |
| API key in JS | Discovery | Cloud Service Dashboard | T1538 |
| PMA spray | Initial Access | Valid Accounts | T1078.001 |
| Log poisoning | Initial Access | Exploitation for Privilege Escalation | T1190 |
| Cloudflare bypass | Initial Access | Exploitation for Privilege Escalation | T1190 |
| Webshell | Execution | Command and Scripting Interpreter | T1059 |
| Cron persistence | Persistence | Scheduled Transfer | T1053 |
"
```

**Step 2.2: Generate ATT&CK heatmap**
```bash
cat >> output/${CAMPAIGN}/report/attack_matrix.md << 'EOF'
## ATT&CK Technique Coverage

| Technique | Finding | Evidence |
|-----------|---------|---------|
| T1190 (Exploit for Privesc) | SQLi, Upload RCE, CVE-XXXX | SQLMap output, shell URL |
| T1078 (Valid Accounts) | Admin access, LR creds spray | confirmed_logins.txt |
| T1059 (Command Injection) | Webshell, GSocket deploy | shell.php, verify.txt |
| T1098.004 (SSH Auth Keys) | Persistence via SSH key | ssh_key file |
| T1021 (Lateral Movement) | Symlink pivot, internal scan | internal_hosts.txt |
| T1053 (Scheduled Task) | Cron job for shell persistence | crontab -l output |
| T1213 (Data from DB) | User table dump | users_dump.csv |
| T1538 (Cloud Dashboard) | AWS keys in .env | .env file |
EOF
```

---

### PHASE 3 — EVIDENCE PACKAGE

**Step 3.1: Organize evidence files**
```bash
cd ~/Hephaestus/output/${CAMPAIGN}/report_evidence/

# Screenshot evidence
# Copy from telegram_inbox or save new
# Format: {target}_{finding}_{date}.png

# Command output evidence
# Save all curl commands, sqlmap output, nuclei output

# Credential evidence (sanitized — no full passwords in report)
cat > credentials.txt << 'EOF'
# Credentials used (sanitized for report)
# Full credentials in: output/{campaign}/confirmed_logins.txt (encrypted)

user: admin@target.com | hash: 5f4dcc3b5aa765d61d8327deb882cf99
# Password: password123 (cracked from MD5)

user: webuser@target.com | hash: 098f6bcd4621d373cade4e832627b4f6
# Password: test (cracked from MD5)
EOF

# Request/response logs
cat > http_requests.txt << 'EOF'
# All HTTP requests with responses (for evidence)
# Sanitized — IPs and sensitive data redacted
EOF
```

---

### PHASE 4 — GENERATE FINAL REPORT

**Step 4.1: Report structure**
```bash
mkdir -p output/${CAMPAIGN}/report/
TARGET="target.com"

cat > output/${CAMPAIGN}/report/PENTEST_REPORT_${TARGET}_$(date +%Y%m%d).md << 'EOF'
---
# PENTEST REPORT
**Target:** {TARGET}
**Date:** {YYYY-MM-DD}
**Scope:** {scope description}
**Authorization:** {auth reference}
---

## EXECUTIVE SUMMARY
{2-3 paragraph overview: scope, what was tested, what was found, critical risks}

## METHODOLOGY
{Attack phases executed: T-1 → T0 → T1 → T2 → T3 → T4 → T5 → T6}

## FINDINGS SUMMARY
| # | Severity | Finding | CVEs | ATT&CK |
|---|----------|---------|------|--------|
| 1 | CRITICAL | SQLi → RCE | - | T1190 |
| 2 | CRITICAL | .env exposed → DB/SSH | - | T1530 |
| 3 | HIGH | Admin panel with weak creds | - | T1078 |
| 4 | MEDIUM | IDOR in user profile | - | T0826 |
| 5 | LOW | Server version disclosure | - | T1008 |

## DETAILED FINDINGS

{DETAILED SECTION FROM PHASE 1}

## ATT&CK HEATMAP
{ATT&CK coverage table from PHASE 2}

## EVIDENCE REFERENCES
- Screenshots: evidence/screenshots/
- Command output: evidence/commands/
- Credentials: evidence/credentials.txt

## REMEDIATION PRIORITY
| Priority | Finding | Effort | Timeline |
|----------|---------|--------|---------|
| P1 | SQLi mitigation | Medium | 1 week |
| P1 | .env removal from web root | Low | 1 day |
| P2 | Admin panel MFA | Medium | 2 weeks |
| P3 | IDOR fix | Medium | 1 week |
| P4 | Server header removal | Low | 1 day |

## CONCLUSION
{Summary paragraph: overall security posture, key risks, recommended next steps}

---
Report Generated: {YYYY-MM-DD HH:mm UTC}
Operator: Pluto
Infrastructure: Hephaestus v6.0
EOF
```

---

### PHASE 5 — DELIVERY

**Step 5.1: Package report**
```bash
cd ~/Hephaestus/output/${CAMPAIGN}/

# Create delivery package
mkdir -p report_delivery_${TARGET}/
cp report/*.md report_delivery_${TARGET}/ 2>/dev/null
cp -r report_evidence/ report_delivery_${TARGET}/ 2>/dev/null

# Encrypt sensitive evidence
gpg -- symmetric --cipher-algo AES256 -o report_delivery_${TARGET}/credentials.gpg \
    -c output/${CAMPAIGN}/confirmed_logins.txt 2>/dev/null

# Create summary for bot report
cat > report_delivery_${TARGET}/SUMMARY.txt << 'EOF'
TARGET: target.com
DATE: YYYY-MM-DD
PHASE REACHED: T6 (report)
SHELL DEPLOYED: YES/NO
INTERNAL ACCESS: YES/NO

CRITICAL FINDINGS: N
HIGH FINDINGS: N
MEDIUM FINDINGS: N
LOW FINDINGS: N

ATT&CK TECHNIQUES: N
CVEs EXPLOITED: N
CREDENTIALS FOUND: N
PERSISTENCE ACTIVE: YES/NO

NEXT STEPS:
- Send encrypted credentials to client
- Schedule remediation review
- Plan follow-up engagement
EOF

# Update campaign state
echo "Report generated: $(date)" >> state/campaigns/${CAMPAIGN}.log
git -C ~/Hephaestus add output/${CAMPAIGN}/report/ state/campaigns/${CAMPAIGN}.json 2>/dev/null
git -C ~/Hephaestus commit -m "Report: ${TARGET} - $(date +%Y%m%d)" 2>/dev/null
```

---

## ATT&CK TECHNIQUE REFERENCE (Web Pentest)

| Technique | ID | Trigger |
|-----------|-----|---------|
| Exploitation for Privilege Escalation | T1190 | SQLi, Upload RCE, CVE, LFI |
| Valid Accounts (Credentials) | T1078.001 | LR spray, default creds |
| Valid Accounts (Default) | T1078.002 | Tomcat manager, WP admin |
| Command and Scripting Interpreter | T1059 | Webshell, GSocket |
| Non-Application Layer Protocol | T1095 | GSocket C2 |
| Scheduled Transfer | T1053 | Cron persistence |
| SSH Authorized Keys | T1098.004 | SSH key persistence |
| Remote Services | T1021 | Lateral movement |
| Unstructured Data Collection | T1213 | Database dump |
| Cloud Infrastructure Discovery | T1530 | .env, AWS keys |
| Cloud Service Dashboard | T1538 | API keys in JS |
| Server Error Disclosure | T1008 | Server version in headers |

---

## CRITICAL RULES

1. **Every finding needs evidence** — curl output, screenshot, command log
2. **Sanitize credentials in report** — full creds in encrypted file, report has hashes
3. **ATT&CK mapping for every finding** — report must show coverage
4. **Remediation priorities** — P1/P2/P3 with timeline
5. **Save to 3 places** — findings.db + state JSON + campaign output
6. **Git commit after report** — preserve evidence immutably

---

## INTEGRATION POINTS

- **Inputs:** all campaign data (state, output, evidence, credentials)
- **Outputs:** `output/{campaign}/report/PENTEST_REPORT_{target}_{date}.md`, evidence package
- **Required tools:** gpg (for encrypting credentials), git, python3