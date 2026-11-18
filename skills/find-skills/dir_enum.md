# SKILL: dir_enum — Web Directory + File Enumeration

**Purpose:** End-to-end web directory and file enumeration. FFUF, Gobuster, dirb, specific paths, sensitive files, admin panels, and backup discovery. Critical for finding hidden admin endpoints and upload forms.

**Type:** recon/web_enum | **Version:** 1.0 | **Author:** Hephaestus v6.0

---

## EXECUTION CONTEXT

```
Role: brain orchestrator — direct Bash for all enumeration
Model: haiku for output parsing
Trigger: Recon phase — after port scan, before attack chain
Anti-refusal: Layer 1 = direct Bash. Directory busting = recon, not exploit.
```

---

## PHASE STRUCTURE

### PHASE 0 — WORDLIST PREPARATION

**Step 0.1: Check available wordlists**
```bash
cd ~/Hephaestus/wordlists/

echo "=== DIRECTORY WORDLISTS ==="
ls -la dir_*.txt dirb_*.txt ffuf_*.txt 2>/dev/null | head -20

# Check common wordlists
ls -la common.txt 2>/dev/null
ls -la medium.txt 2>/dev/null
ls -la big.txt 2>/dev/null
ls -la subdomains.txt 2>/dev/null
ls -la admin_paths.txt 2>/dev/null

# Create custom enum wordlist
cat > /tmp/dir_enum_wordlist.txt << 'EOF'
admin
administrator
login
wp-admin
wp-login
cpanel
cp
panel
dashboard
manage
configure
settings
config
backup
backups
old
archive
archives
uploads
upload
files
media
images
img
photo
pictures
css
js
static
assets
dist
build
src
vendor
node_modules
api
v1
v2
v3
rest
graphql
swagger
docs
documentation
git
svn
.bzr
.hg
.env
config
settings
database
db
sql
dump
backup
backups
.bash_history
.sh_history
.rhosts
.htaccess
.htpasswd
web.config
web.config.bak
config.php.bak
wp-config.php.bak
database.php.bak
.ini.bak
.bak
.old
.tmp
temp
tmp
cache
proc
dev
sys
kernel
proc/self/cmdline
phpinfo
info
debug
trace
test
demo
example
sample
readme
README
changelog
CHANGELOG
license
LICENSE
robots.txt
sitemap.xml
crossdomain.xml
clientaccesspolicy.xml
.well-known
.jwt
tokens
auth
authentication
logout
signin
signup
register
forgot
password
reset
user
profile
account
portal
backend
office
owa
autodiscover
microsoft
ews
api/test
test.php
debug.php
info.php
phpinfo.php
server-status
server-info
status
health
ping
echo
shell
cmd
exec
system
admin.php
login.php
wp-config.php
configuration.php
settings.php
database.php
db.php
EOF

wc -l /tmp/dir_enum_wordlist.txt
```

---

### PHASE 1 — FFUF ENUMERATION

**Step 1.1: Fast directory scan (FFUF)**
```bash
TARGET="target.com"
OUTPUT="/tmp/ffuf_main.json"

echo "=== FFUF DIRECTORY SCAN ==="

ffuf -u "https://$TARGET/FUZZ" \
    -w /tmp/dir_enum_wordlist.txt \
    -mc 200,204,301,302,307,401,403,500 \
    -t 50 \
    -timeout 10 \
    -o "$OUTPUT" \
    -of json \
    2>/dev/null

# Parse results
cat "$OUTPUT" 2>/dev/null | python3 -c "
import sys,json
try:
    d=json.load(sys.stdin)
    results=d.get('results',[])
    for r in sorted(results, key=lambda x: x.get('status',0)):
        print(f\"[{r.get('status',0)}] {r.get('url','')} | Len: {r.get('length',0)}\")
except Exception as e:
    print(f'Error: {e}')
" 2>/dev/null | head -30

# Quick output
ffuf -u "https://$TARGET/FUZZ" \
    -w /tmp/dir_enum_wordlist.txt \
    -mc 200,204,301,302,307,401,403 \
    -t 50 \
    -timeout 10 \
    -o /tmp/ffuf_quick.txt \
    2>/dev/null

cat /tmp/ffuf_quick.txt | head -50
```

**Step 1.2: FFUF with extensions**
```bash
TARGET="target.com"

# PHP files
ffuf -u "https://$TARGET/FUZZ.php" \
    -w /tmp/dir_enum_wordlist.txt \
    -mc 200,204,302,403 \
    -t 50 -timeout 10 \
    -o /tmp/ffuf_php.txt \
    2>/dev/null

# Common extensions
for ext in "php" "asp" "aspx" "jsp" "jspx" "html" "htm" "txt" "xml" "json" "bak" "old" "zip" "tar" "gz"; do
    echo "Scanning .$ext files..."
    ffuf -u "https://$TARGET/FUZZ.$ext" \
        -w /tmp/dir_enum_wordlist.txt \
        -mc 200,204,302,403 \
        -t 30 -timeout 10 \
        2>/dev/null | head -10
done
```

**Step 1.3: FFUF subdomain fuzzing (virtual host)**
```bash
TARGET="target.com"
TARGET_IP=$(dig +short target.com | head -1)

# Virtual host enumeration
ffuf -u "https://$TARGET_IP/" \
    -H "Host: FUZZ.$TARGET" \
    -w ~/Hephaestus/tools/wordlists/subdomains \
    -mc 200,204,302,403 \
    -t 50 -timeout 10 \
    -o /tmp/ffuf_vhost.txt \
    2>/dev/null

cat /tmp/ffuf_vhost.txt | head -30
```

---

### PHASE 2 — GOBUSTER ENUMERATION

**Step 2.1: Gobuster directory scan**
```bash
TARGET="target.com"

# Directory mode
gobuster dir -u "https://$TARGET/" \
    -w /tmp/dir_enum_wordlist.txt \
    -t 50 -timeout 10s \
    -k \
    -o /tmp/gobuster_dir.txt \
    2>/dev/null

cat /tmp/gobuster_dir.txt | head -30

# DNS mode (subdomains)
gobuster dns -d "$TARGET" \
    -w ~/Hephaestus/tools/wordlists/subdomains \
    -t 50 \
    -o /tmp/gobuster_dns.txt \
    2>/dev/null

cat /tmp/gobuster_dns.txt | head -20
```

---

### PHASE 3 — SENSITIVE FILE DISCOVERY

**Step 3.1: Critical files (parallel)**
```bash
TARGET="https://target.com"

echo "=== CRITICAL FILE CHECK ==="

# The 20 most valuable files
CRITICAL_FILES=(
    ".env" ".env.bak" ".env.old" ".env.dev" ".env.local"
    ".git/config" ".git/HEAD" ".git/index" ".git/objects"
    "wp-config.php" "wp-config.php.bak"
    "configuration.php" "config.php" "config.php.bak"
    "settings.php" "database.php" "db.php"
    "docker-compose.yml" "docker-compose.yaml"
    "phpinfo.php" "info.php"
    ".htaccess" ".htpasswd"
    "web.config" "web.config.bak"
    "robots.txt" "sitemap.xml"
    "readme.md" "README.md" "CHANGELOG.md"
    "debug.log" "error.log" "access.log"
    ".DS_Store" ".directory"
    "id_rsa" "id_dsa" "id_ed25519" "*.pem"
    "backup.sql" "database.sql" "dump.sql"
)

for file in "${CRITICAL_FILES[@]}"; do
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 3 "$TARGET/$file" 2>/dev/null)
    if [ "$code" = "200" ]; then
        echo "[FOUND] $file (HTTP $code)"
    fi
done &

# Wait for all checks
wait

echo "=== DONE ==="
```

**Step 3.2: Backup file discovery**
```bash
TARGET="https://target.com"

# Common backup extensions
BACKUP_PATTERNS=(
    "*.bak" "*.backup" "*.back" "*.old" "*.orig" "*.tmp"
    "*.swp" "*.swo" "*~" "*.save"
    "*.sql.gz" "*.sql.bak" "*.database.bak"
    "*.zip" "*.tar.gz" "*.tgz" "*.tar"
    "*.rar" "*.7z"
)

echo "=== BACKUP FILE DISCOVERY ==="
for pattern in "${BACKUP_PATTERNS[@]}"; do
    echo "Checking: $pattern"
    # ffuf with extension
    FFUF_EXT=$(echo "$pattern" | sed 's/\*/FUZZ/')
    ffuf -u "https://$TARGET/$FFUF_EXT" \
        -w /tmp/dir_enum_wordlist.txt \
        -mc 200,204,302,403 \
        -t 20 -timeout 5 \
        2>/dev/null | grep -iE "200|found" | head -5
done
```

---

### PHASE 4 — ADMIN PANEL DISCOVERY

**Step 4.1: Admin panel scan**
```bash
TARGET="target.com"

echo "=== ADMIN PANEL SCAN ==="

ADMIN_PATHS=(
    "/admin" "/admin/" "/administrator" "/administrator/" "/admin/login"
    "/wp-admin" "/wp-admin/" "/wp-login.php" "/wp/wp-admin"
    "/cms" "/cms/" "/cms/admin" "/cms/login"
    "/panel" "/panel/" "/cpanel" "/cp" "/cp/"
    "/backend" "/backend/admin" "/backend/login"
    "/portal" "/portal/admin" "/portal/login"
    "/dashboard" "/dashboard/" "/manage" "/manage/"
    "/control" "/controlpanel" "/webadmin" "/webmaster"
    "/system" "/system/admin" "/intranet" "/intranet/"
    "/auth" "/auth/login" "/auth/admin" "/login" "/login/"
    "/console" "/console/" "/jconsole" "/hudson"
    "/api/admin" "/api/v1/admin" "/api/v2/admin"
)

for path in "${ADMIN_PATHS[@]}"; do
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "$TARGET$path" 2>/dev/null)
    if [ "$code" = "200" ] || [ "$code" = "302" ] || [ "$code" = "301" ]; then
        echo "[ADMIN] $path (HTTP $code)"
    fi
done &

wait
```

---

### PHASE 5 — CONSOLIDATE + SPRAY PREP

**Step 5.1: Merge all results**
```bash
TARGET="target.com"
OUTPUT_DIR="~/Hephaestus/output/${CAMPAIGN}/dir_enum"

mkdir -p "$OUTPUT_DIR"

# Merge all findings
cat /tmp/ffuf_quick.txt /tmp/gobuster_dir.txt 2>/dev/null | \
    grep -iE "\[200\]|\[302\]|\[301\]|\[403\]" | \
    grep -vE "^FFUF|Gobuster|Starting" | \
    sort -u > "$OUTPUT_DIR/all_found_paths.txt"

echo "=== ALL FOUND PATHS ==="
cat "$OUTPUT_DIR/all_found_paths.txt" | head -50

# Filter for interesting paths
grep -iE "admin|login|panel|upload|backup|config|api|dashboard" \
    "$OUTPUT_DIR/all_found_paths.txt" > "$OUTPUT_DIR/interesting_paths.txt"

echo "Interesting paths: $(wc -l < $OUTPUT_DIR/interesting_paths.txt)"
cat "$OUTPUT_DIR/interesting_paths.txt"
```

---

## DIRECTORY ENUM PRIORITY

| Priority | Path | Why |
|----------|------|-----|
| P0 | /.env | Stop everything, report immediately |
| P0 | /.git/config | High win rate, report immediately |
| P0 | /wp-config.php.bak | DB creds, report immediately |
| P1 | /admin /login /dashboard | Login forms for spray |
| P1 | /upload /files /media | Upload forms for RCE |
| P1 | /api /v1 /v2 | Internal API endpoints |
| P2 | /debug /phpinfo /server-status | Info disclosure |
| P2 | /backup /old /archive | Backup files + config |
| P3 | /js /css /images | Lower priority |

---

## CRITICAL RULES

1. **Parallel checks** — critical files checked in parallel (background &)
2. **FFUF FAST** — use medium wordlist + high threads for speed
3. **Extensions** — .php, .bak, .old, .sql, .zip = common backup patterns
4. **Admin panels** — find all login forms for spray priority
5. **robots.txt** — often contains admin paths + sensitive files
6. **Sitemap.xml** — reveals internal structure
7. **Save ALL results** — even 404 paths help map server structure

---

## INTEGRATION POINTS

- **Inputs:** target URL, campaign name
- **Outputs:** `output/{campaign}/dir_enum/all_found_paths.txt`, `interesting_paths.txt`
- **Next skill:** `spray` (login pages), `upload_bypass` (upload forms), `leakradar` (for LR on found admin paths), `cms_exploit` (CMS paths found)
- **Required tools:** ffuf, gobuster, dirb, curl