# .htaccess Bypass via Alternative Upload Directories

**Discovered:** nactvet.go.tz, 2026-06-03
**Severity:** HIGH — converts "upload works but blocked" to "RCE"

## The Problem

Many Laravel/CMS applications use defense-in-depth:
1. File upload validation (MIME type, extension checking)
2. Apache `.htaccess` in `/storage/` directories blocking script execution

The `.htaccess` typically contains:
```apache
<FilesMatch "\.(php|phtml|phar|pht|inc)$">
    Deny from all
</FilesMatch>
```

This blocks ALL PHP execution in `/storage/public/files/`, `/storage/public/photos/`,
etc. Even if you bypass upload validation (polyglot, double ext), the shell won't execute.

## The Discovery

**Not all upload directories have `.htaccess` protection.** CMS-specific asset
directories often live outside `/storage/` and lack the restriction:

| Directory | .htaccess? | PHP executes? |
|-----------|-----------|---------------|
| `/storage/public/files/` | YES (403 on .php) | NO |
| `/storage/public/photos/` | YES (403 on .php) | NO |
| `/public/assets/images/upload/` | NO (Laravel 404 on .php) | YES |
| `/public/assets/uploads/` | Usually NO | Likely YES |
| Theme asset directories | Usually NO | Likely YES |

**How to test:** Request a `.php` file in the directory:
- **Apache 403** → `.htaccess` blocks execution → can't use
- **Laravel 404 HTML** → PHP processes the request → shell WILL execute
- **500 error** → PHP processes but errors → shell WILL execute

## The Attack Pattern

1. **Login to CMS** with valid credentials
2. **Identify all upload forms** — not just the main file manager:
   - Profile picture upload → often saves to `/public/assets/images/`
   - Logo/favicon upload (web-setup, theme settings)
   - Slider/banner image upload
   - User avatar upload
   - CKEditor/TinyMCE image upload (may use LFM but different config)
3. **Upload PHP shell** via the form that saves to unprotected directory
4. **Access shell** at the unprotected path

## Real-World Example: nactvet.go.tz

```
Target: nactvet.go.tz (Laravel CMS, 203.0.113.10)
Upload forms found:
  - LFM at /laravel-filemanager → /storage/public/files/ (.htaccess BLOCKS)
  - Slider at /insert_sliders → /storage/public/photos/ (.htaccess BLOCKS)
  - Profile picture at /upload_profile_picture → target dir unknown
  - Web-setup logo → likely /public/assets/images/upload/

Existing files revealed:
  - Logo: /public/assets/images/upload/NACTVET-web-logo.png (accessible!)
  - Slider photos: /storage/public/photos/*.jpg (accessible!)

Test results:
  - /public/assets/images/upload/test.php → Laravel 404 HTML → PHP EXECUTES
  - /storage/public/photos/test.php → Apache 403 → PHP BLOCKED

Conclusion: Upload to /public/assets/images/upload/ = RCE
```

## Key Insights

1. **Look at existing images in page source** — their paths reveal where different
   upload forms save files
2. **Each upload form may save to a different directory** — the file manager is
   often the MOST protected; profile/logo/slider forms may be less protected
3. **Test .php extension directly** — if directory returns Apache 403, move on;
   if it returns app-level HTML, you have execution
4. **Even if extension validation blocks .php**, try `.pht`, `.php5`, `.phar`
   in the unprotected directory — different forms may have different validation
5. **Profile/avatar picture uploads often have ZERO extension validation** — when
   the main file manager (LFM) strictly blocks all script extensions, the profile
   picture form may accept `.php`, `.user.ini`, `.htaccess`, and any other
   extension. The validation logic is often completely separate from the file
   manager. On nactvet.go.tz, LFM blocked 10+ extensions but `/update_profile`
   accepted every extension tested, including `.php`, `.phtml`, `.phar`,
   `.user.ini`, and `.htaccess`.
6. **`.user.ini` upload works even when `.htaccess` override doesn't** — if the
   server's `<Directory>` config overrides per-directory `.htaccess` files, try
   `.user.ini` with `auto_prepend_file`. Even if it fails on the current target,
   the technique is worth attempting on every PHP target with upload access.
7. **Identify the file input field name** — profile forms use field names like
   `image`, `avatar`, `photo`, `profile_pic`. LFM/Dropzone uses `upload[0]`
   (with brackets and index, NOT `upload[]` or `upload`). Getting the field
   name wrong produces misleading errors ("Invalid upload request", CSRF mismatch)

## When to Use

- You have CMS login but file manager uploads are blocked by .htaccess
- You've successfully uploaded a shell but it returns 403
- You're looking for an upload form that saves outside `/storage/`
