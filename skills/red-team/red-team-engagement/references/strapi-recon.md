# Strapi Headless CMS — Reconnaissance

Strapi is an open-source headless CMS with a React admin panel.
Discovered on sumtv.org at `api.sumtv.org` after subdomain enumeration.

## Detection

Strapi announces itself via response headers:
```
x-powered-by: Strapi <strapi.io>
```

Default welcome page at root:
```html
<title>Welcome to your Strapi app</title>
```

Admin panel typically at `/admin/`.

## Unauthenticated Endpoints

| Endpoint | Auth Required | Returns |
|----------|--------------|---------|
| `/admin/` | No | React admin SPA (login form rendered client-side) |
| `/admin/init` | No | `{"data":{"uuid":"...","hasAdmin":true/false,...}}` |
| `/admin/login` | No (POST) | `{"data":{"token":"..."}}` on success, `{"error":{"message":"Invalid credentials"}}` on failure |
| `/admin/forgot-password` | No (POST) | 204 No Content (does NOT reveal if email exists) |
| `/api/` | Content-type dependent | 404 if no public content types, 403 if gated |
| `/api/users` | Yes (403) | User data |
| `/api/upload/files` | Yes (403) | Uploaded files |

## `/admin/init` — Critical Pre-Login Check

This endpoint reveals whether the Strapi admin has been initialized.
If `hasAdmin: false`, you can create the FIRST admin user without any
credentials — this gives full administrative access.

```bash
curl -sk 'https://api.TARGET/admin/init'
# {"data":{"uuid":"...","hasAdmin":true}} => admin exists, need creds
# {"data":{"hasAdmin":false}} => CAN CREATE ADMIN!
```

If `hasAdmin: false`, POST to `/admin/register-admin`:
```bash
curl -sk -X POST 'https://api.TARGET/admin/register-admin' \
  -H 'Content-Type: application/json' \
  -d '{"email":"attacker@test.com","password":"StrongPass123!","firstname":"Admin","lastname":"User"}'
```

## Admin Login

```bash
curl -sk -X POST 'https://api.TARGET/admin/login' \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@TARGET","password":"PASSWORD"}'
```

- 200: `{"data":{"token":"eyJ..."}}` — JWT token for `Authorization: Bearer`
- 400: `{"error":{"message":"Invalid credentials"}}`

## Forgot Password

Returns 204 regardless of whether email exists — designed to prevent
user enumeration. Different from MODX which may leak user existence.

```bash
curl -sk -X POST 'https://api.TARGET/admin/forgot-password' \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@TARGET"}'
# Always returns: 204 No Content
```

## Content API Behavior

Strapi v4+ has granular API permissions. By default, no content types
are publicly accessible unless explicitly enabled in the Roles settings.

```bash
curl -sk 'https://api.TARGET/api/'          # Usually 404
curl -sk 'https://api.TARGET/api/articles'  # 404 unless content type exists + public
```

403 on `/api/users` or `/api/upload/files` confirms the API is active
but properly permissioned.

## sumtv.org Case Study (2026-06-04)

- api.sumtv.org discovered via subdomain enumeration
- `/admin/` accessible, React SPA loads
- `/admin/init` revealed `hasAdmin: true` — admin already set up
- Login attempts: user@example.com, admin — all returned "Invalid credentials"
- Forgot password: 204 (no user enum possible)
- Content API: 404 — no public endpoints
- Users/Uploads API: 403 — properly gated
- Default creds exhausted, auth barrier not breached

## Key Differences from Other CMS

| Feature | Strapi | MODX | EasyForms/Yii2 |
|---------|--------|------|----------------|
| Admin path | `/admin/` (React SPA) | `/manager/` | `/` (server-rendered) |
| Auth style | JWT token via JSON API | Form POST + PHP session | Form POST + PHP session |
| Init check | `/admin/init` (unauth) | Already installed | `/index.php?r=user/registration` |
| Config leak | No public config files | `/core/config/config.inc.php` | `/composer.json`, `/runtime/logs/app.log` |
| User enum | No (204 for all forgot) | Possible via forgot form | Possible via forgot form |
| Admin creation | Via `/admin/register-admin` if uninit | Via `/setup/` if uninstalled | Via `/user/registration` if open |
