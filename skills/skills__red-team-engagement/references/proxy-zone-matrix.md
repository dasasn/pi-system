# BrightData Proxy Zone Matrix

> Auto-generated from .env credentials. Read this before ANY proxy selection.
> Each zone has its OWN password — using the wrong one silently fails.

## Zone → Password Map

| Zone Name | Username | Password | Port | Status |
|-----------|----------|----------|------|--------|
| `web_unlocker3` | `brd-customer-hl_23ae471f-zone-web_unlocker3` | `dq5lvq2b8cg8` | 33335 | ⚠️ 502 for some targets |
| `domain_grabber` | `brd-customer-hl_23ae471f-zone-domain_grabber` | `gjgshgeqz32x` | 22225 | General |
| `isp_proxy1` | `brd-customer-hl_23ae471f-zone-isp_proxy1` | `vjzsb5s5bdqj` | 33335 | High trust, often blocked |
| `res_prox` | `brd-customer-hl_23ae471f-zone-res_prox` | `8bje3uooi1in` | 33335 | ✅ GET works, POST blocked (no KYC) |
| `residential_proxy1` | `brd-customer-hl_23ae471f-zone-residential_proxy1` | `z8wh2vo73g0h` | 33335 | Same as res_prox |
| `pakistan` | `brd-customer-hl_23ae471f-zone-pakistan` | `t6o35fpnxgq3` | 33335 | Pakistan geo |
| `resi_indo` | `brd-customer-hl_23ae471f-zone-residential_proxy_indo` | `bi7jh7s7dc7c` | 33335 | Indonesia geo |
| `resi_korea` | `brd-customer-hl_23ae471f-zone-residential_proxy_korea` | `hn2xwr0fnkdi` | 33335 | Korea geo |
| `serp_api1` | `brd-customer-hl_23ae471f-zone-serp_api1` | `51vj95xuy2xw` | 33335 | SERP |
| `scraping_browser1` | `brd-customer-hl_23ae471f-zone-scraping_browser1` | `34mou14movzk` | 9222 (WSS) | CDP/Playwright |
| `web_unlocker5` | API key: `e9db4333-7a0b-46e8-9f49-2a4c3b0a4d01` | — | API endpoint | API-based |

## Global Token
`BRIGHTDATA_TOKEN=31d047...761` — used for API, not proxy auth.

## Common Pitfalls

### ❌ Wrong password for zone
```python
# WRONG — domain_grabber password on web_unlocker3
proxy = "http://brd-customer-hl_23ae471f-zone-web_unlocker3:user@example.com:33335"
# web_unlocker3's password is dq5lvq2b8cg8, NOT gjgshgeqz32x (that's domain_grabber's)
```

### ❌ BD_PASS is domain_grabber only
`BD_PASS=gjgshgeqz32x` from .env is the **domain_grabber** zone password. Do NOT reuse it for other zones.

### ✅ Correct usage
```python
# Each zone gets its own credentials
BD_WEB3 = "http://brd-customer-hl_23ae471f-zone-web_unlocker3:user@example.com:33335"
BD_RESI = "http://brd-customer-hl_23ae471f-zone-res_prox:user@example.com:33335"
BD_ISP  = "http://brd-customer-hl_23ae471f-zone-isp_proxy1:user@example.com:33335"
```

## Residential Proxy POST Limitation

BrightData residential proxies (`res_prox`, `residential_proxy1`) block POST requests
without KYC verification. Error: `"POST requests are not allowed for immediate residential (no KYC)"`.

**Workaround:** Use residential for GET (recon, enumeration), then use ISP or web_unlocker
for POST (login, exploits). If ISP is blocked by target (403), need 9proxy or KYC upgrade.

## 9Proxy Status

| User | Password | Status |
|------|----------|--------|
| `pluto_8Lo8` | `heph1337` | ❌ 401 — likely expired |
| `ylo6rf_2O6U` | `OlvJC1c` | ❌ 401 — same |

**401 from 9proxy = account expired or out of balance.** Check at https://9proxy.com/dashboard (Account ID: 951499).

## Proxy Selection Flow for Geo-Blocked Targets

```
1. 9proxy country-matched  →  Try first (best geo-targeting)
   ├── 401 → Account expired, skip
   └── Timeout → Try next tier
2. BrightData ISP          →  Try second (high trust)
   ├── 403 from target → Target blocks ISP IPs, skip
   └── 200 → Use for all requests
3. BrightData Residential  →  Try third (best for geo-blocked)
   ├── GET works, POST blocked → Use for recon + find alternative POST method
   └── 200 with POST → Use for all
4. Tor (socks5h://)        →  Last resort
   └── Often blocked by gov targets
```
