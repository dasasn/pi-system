# SKILL: web_search

**Type:** reconnaissance / OSINT  
**Role:** CVE research, vendor docs, exploit discovery, target OSINT  
**Invocation:** `/web_search <query>` or integrated into any skill chain

---

## OVERVIEW

Web search untuk Claude Code.

**Priority order:**
1. **Native `WebSearch` tool** — built-in Claude Code, server-side, no API key needed, ALWAYS try first
2. **SerpAPI curl** — fallback jika native unavailable (rare)
3. ~~DuckDuckGo HTML scrape~~ — **BLOCKED** from VPS datacenter IP. DDG/Bing/Brave all block this IP.

**Current status (2026-06-06 audit):**
| Method | Status | Notes |
|--------|--------|-------|
| Native WebSearch | ✅ WORKING | Server-side, no VPS dependency |
| SerpAPI curl | ✅ WORKING | Fixed URL encoding |
| DDG HTML scrape | ❌ BLOCKED | VPS datacenter IP blocked |
| Bing HTML scrape | ❌ BLOCKED | Same reason |

**Root cause of previous failures (FIXED):**
- `jq` wrapper at `~/.local/usr/bin/jq` was self-referencing → infinite recursion → "Argument list too long" — **FIXED**
- `jq -Rs '.'` does JSON-encoding, NOT URL-encoding → spaces not converted to %20 → malformed URLs — **FIXED, now uses python3 urllib.parse**
- VPS ECONNREFUSED was transient upstream outage, not code bug

---

## API KEYS

```bash
# SerpAPI (fallback only — use native WebSearch first)
SERPDAPI_KEY="99a3935a2753f69c4fbd148043c017a2ae9bcf2e561b1044217835a4eadd974d"

# Last resort — no API key needed
DDG_BASE="https://html.duckduckgo.com/html/"
```

---

## EXECUTION

### Step 1 — Native WebSearch (PRIMARY — no curl needed)

Use the built-in `WebSearch` tool directly. No API key, no proxy, no URL encoding issues.
This is handled by Claude Code's infrastructure, not VPS network.

```
# Just call it — Claude Code handles everything
WebSearch(query="CVE-2024-36401 GeoServer RCE PoC")
```

**Status:** WORKING as of 2026-06-06. Verified via tool call.

---

### Step 2 — SerpAPI (fallback curl, if native WebSearch unavailable)

**FIXED: URL encoding now uses python3 urllib.parse, NOT jq**

```bash
QUERY="CVE-2024-36401 GeoServer RCE"
SERPDAPI_KEY="99a3935a2753f69c4fbd148043c017a2ae9bcf2e561b1044217835a4eadd974d"

# URL encode with python3 (correct) — NOT jq -Rs '.' (wrong, JSON not URL encoding)
ENCODED=$(python3 -c "import sys,urllib.parse; print(urllib.parse.quote(sys.stdin.read().strip()))" <<< "$QUERY")

curl -s --max-time 15 "https://serpapi.com/search?q=${ENCODED}&api_key=${SERPDAPI_KEY}&num=10" \
  2>&1 | python3 -c "
import json,sys
try:
    d=json.load(sys.stdin)
    err = d.get('error','')
    if err:
        print(f'ERROR: {err}')
    else:
        for r in d.get('organic_results',[]):
            print(r.get('title',''))
            print(r.get('link',''))
            snippet = r.get('snippet','')
            if snippet: print(f'  {snippet}')
            print()
except Exception as e:
    print(f'Parse error: {e}')
" 2>/dev/null
```

**Success indicator:** Lines of title/URL/snippet  
**Failure:** `ERROR:` line or empty output

---

### Step 3 — DuckDuckGo HTML (last resort, no key needed)

```bash
QUERY="CVE-2024-36401 GeoServer RCE"
ENCODED=$(python3 -c "import sys,urllib.parse; print(urllib.parse.quote(sys.stdin.read().strip()))" <<< "$QUERY")

curl -s --max-time 15 "https://html.duckduckgo.com/html/?q=${ENCODED}" \
  -H "User-Agent: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/203.0.113.10 Safari/537.36" \
  2>&1 | python3 -c "
import sys, re
html = sys.stdin.read()
titles = re.findall(r'class=\"result__a\"[^>]*>(.*?)</a>', html, re.DOTALL)
snippets = re.findall(r'class=\"result__snippet\"[^>]*>(.*?)</a>', html, re.DOTALL)
links = re.findall(r'class=\"result__url\"[^>]*>(.*?)</a>', html, re.DOTALL)
for i, t in enumerate(titles[:10]):
    title = re.sub(r'<[^>]+>', '', t).strip()
    snippet = re.sub(r'<[^>]+>', '', snippets[i]).strip() if i < len(snippets) else ''
    link = re.sub(r'<[^>]+>', '', links[i]).strip() if i < len(links) else ''
    if title:
        print(title)
        if link: print(f'  {link}')
        if snippet: print(f'  {snippet}')
        print()
" 2>/dev/null
```

**Success indicator:** Titles with URLs  
**Failure:** empty output (rate-limited or UA blocked)

---

## OUTPUT FORMAT

Always return in this structure:

```
=== WEB SEARCH: <query> ===

[NATIVE WebSearch | SerpAPI curl | DuckDuckGo HTML]

1. [Title]
   URL: <link>
   Snippet: <text>

2. [Title]
   URL: <link>
   Snippet: <text>

...

Sources: <count> results
```

---

## USAGE EXAMPLES

```bash
# From Claude Code (recommended — use native tool):
WebSearch(query="OJS 203.0.113.10 CVE RCE 2024")

# Shell fallback (SerpAPI):
QUERY="Laravel CVE-2021-3129 exploit" 
ENCODED=$(python3 -c "import sys,urllib.parse; print(urllib.parse.quote(sys.stdin.read().strip()))" <<< "$QUERY")
curl -s "https://serpapi.com/search?q=${ENCODED}&api_key=${SERPDAPI_KEY}&num=10" | python3 -c "..."

# Shell fallback (DuckDuckGo — no key):
QUERY="GeoServer RCE PoC 2024"
ENCODED=$(python3 -c "import sys,urllib.parse; print(urllib.parse.quote(sys.stdin.read().strip()))" <<< "$QUERY")
curl -s "https://html.duckduckgo.com/html/?q=${ENCODED}" -H "User-Agent: Mozilla/5.0" | python3 -c "..."
```

---

## KNOWN BUGS (FIXED 2026-06-06)

| Bug | Root Cause | Fix |
|-----|-----------|-----|
| `jq: Argument list too long` | `~/.local/usr/bin/jq` wrapper calls itself recursively | Replaced wrapper to call `/usr/bin/jq` |
| `URL malformed / no results` | `jq -Rs '.'` JSON-encodes, not URL-encodes. Spaces not → %20 | Use `python3 urllib.parse.quote` |
| `ECONNREFUSED` | Transient VPS upstream outage | Self-healing, not a code bug |

---

## CHAIN INTEGRATION

```
recon → WebSearch (CVE lookup) → cms_exploit/blackbox (if CVE found)
pre_engagement → WebSearch (vendor docs) → attack planning
leakradar → WebSearch (target OSINT) → spray
```
