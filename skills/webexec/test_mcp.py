#!/usr/bin/env python3
"""test_mcp.py — end-to-end test of wexec-mcp over real JSON-RPC stdio.

Spawns the server the way pi does, calls each tool, asserts the expected
detection is present. Run: python3 test_mcp.py
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SERVER = [sys.executable, os.path.join(HERE, "wexec-mcp.py")]
LAB_PORT = int(os.environ.get("WEXEC_LAB_PORT", "8089"))
LAB = f"http://127.0.0.1:{LAB_PORT}"


def lab_up(timeout=15):
    """True kalau sudah ada yang melayani port lab."""
    import socket
    s = socket.socket()
    s.settimeout(1)
    try:
        s.connect(("127.0.0.1", LAB_PORT))
        return True
    except OSError:
        return False
    finally:
        s.close()


def start_lab():
    """Nyalakan lab.py kalau belum jalan. Test harus self-contained:
    tanpa ini, oracle detection tidak punya target dan semua assert gagal
    padahal kit-nya sehat."""
    if lab_up():
        return None
    p = subprocess.Popen([sys.executable, os.path.join(HERE, "lab.py"),
                          "--port", str(LAB_PORT)],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    import time
    for _ in range(40):
        if lab_up():
            return p
        time.sleep(0.25)
    p.terminate()
    raise RuntimeError(f"lab gagal start di port {LAB_PORT}")


class MCP:
    def __init__(self):
        self.p = subprocess.Popen(SERVER, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, text=True, bufsize=1)
        self.id = 0
        self.call("initialize", {})

    def call(self, method, params):
        self.id += 1
        msg = {"jsonrpc": "2.0", "id": self.id, "method": method, "params": params}
        self.p.stdin.write(json.dumps(msg) + "\n")
        self.p.stdin.flush()
        while True:
            line = self.p.stdout.readline()
            if not line:
                raise RuntimeError("server closed: " + self.p.stderr.read()[-800:])
            d = json.loads(line)
            if d.get("id") == self.id:
                return d

    def tool(self, name, args=None):
        r = self.call("tools/call", {"name": name, "arguments": args or {}})
        if "error" in r:
            return {"_rpc_error": r["error"]}
        txt = r["result"]["content"][0]["text"]
        try:
            return json.loads(txt)
        except Exception:
            return {"_raw": txt, "_is_error": r["result"].get("isError")}

    def close(self):
        try:
            self.p.stdin.close()
            self.p.wait(timeout=5)
        except Exception:
            self.p.kill()


FAILED = []


def check(label, cond, detail=""):
    ok = "PASS" if cond else "FAIL"
    if not cond:
        FAILED.append(label)
    print(f"[{ok}] {label}" + (f"  {detail}" if detail else ""))


def main():
    m = MCP()
    try:
        tools = m.call("tools/list", {})["result"]["tools"]
        check("tools/list", len(tools) == 14, f"{len(tools)} tools")

        r = m.tool("wexec_fingerprint", {"target": LAB})
        check("fingerprint status 200", r.get("root", {}).get("status") == 200, str(r.get("root")))
        check("fingerprint baseline", r.get("baseline", {}).get("size_median", 0) > 0)

        r = m.tool("wexec_http", {"url": LAB + "/echo?id=hi", "max_chars": 200})
        check("http returns body", "You searched" in (r.get("body") or ""), r.get("status"))

        r = m.tool("wexec_expose", {"target": LAB})
        check("expose finds .env", r.get("summary", {}).get("hits", 0) >= 2, str(r.get("summary")))
        check("expose stores secrets", r.get("summary", {}).get("secrets", 0) >= 2)
        leaked = json.dumps(r)
        check("expose output redacted", "Sup3rS3cret" not in leaked and "QUJDREVG" not in leaked)

        r = m.tool("wexec_inject", {"target": LAB + "/login", "params": ["u"], "types": "sqli"})
        check("inject sqli error-based", r.get("summary", {}).get("strong", 0) == 1)

        r = m.tool("wexec_inject", {"target": LAB + "/file", "params": ["f"], "types": "lfi"})
        check("inject lfi", r.get("summary", {}).get("strong", 0) == 1)

        r = m.tool("wexec_inject", {"target": LAB + "/echo", "params": ["id"], "types": "xss"})
        check("inject xss", r.get("summary", {}).get("strong", 0) == 1)

        r = m.tool("wexec_panel", {"target": LAB})
        check("panel finds admin login", r.get("summary", {}).get("has_login") is True)
        check("panel no soft404 noise", r.get("summary", {}).get("hits", 99) <= 5, str(r.get("summary")))

        r = m.tool("wexec_differential",
                   {"control_url": LAB + "/echo?id=1", "payload_url": LAB + "/echo?id=2"})
        check("differential verdict present", r.get("verdict") in ("NONE", "WEAK", "STRONG"), r.get("verdict"))

        r = m.tool("wexec_payload", {"kind": "sqli"})
        check("payload sqli list", r.get("count", 0) > 30, str(r.get("count")))

        r = m.tool("wexec_payload", {"kind": "sqli", "mutate_level": 2})
        mutated = " | ".join(r.get("payloads", []))
        check("payload mutation inserts inline comments (UNION/SELECT only)",
              "UNION/**/" in mutated and "'" in mutated)

        r = m.tool("wexec_redact", {"text": "DB_PASSWORD=hunter2\nAKIAABCDEFGHIJKLMNOP"})
        check("redact hides password", "hunter2" not in r.get("redacted", ""))
        check("redact hides aws key", "AKIAABCDEFGHIJKLMNOP" not in r.get("redacted", ""))

        r = m.tool("wexec_shellgen", {"mode": "php", "out": "/tmp/mcp_shells"})
        check("shellgen produces files", len(r.get("files", [])) > 10, str(len(r.get("files", []))))
        lint_ok = all(v == "ok" for v in (r.get("php_lint") or {}).values())
        check("shellgen php lint clean", lint_ok)

        r = m.tool("wexec_js_leak", {"text": "const w={privateKey:'0x4c0883a69102937d6231471b5dbb6204fe5129617082792ae468d01a3f362318'}"})
        check("jsleak finds key", r.get("summary", {}).get("wallet_material", 0) >= 1)
        check("jsleak key not printed", "4c0883a69102937d" not in json.dumps(r))

        r = m.tool("wexec_keyhunt", {"hex": "0x4c0883a69102937d6231471b5dbb6204fe5129617082792ae468d01a3f362318",
                                     "chains": "ethereum"})
        check("keyhunt derives address", r.get("results", [{}])[0].get("address", "").startswith("0x2c7536"))
        check("keyhunt reads balance", r["results"][0].get("balances", {}).get("ethereum", {}).get("rpc_error") is None)

        r = m.tool("wexec_waf_bypass", {"target": LAB})
        check("wafbypass runs", bool(r.get("tests")), str(len(r.get("tests") or [])))

    finally:
        m.close()

    print()
    if FAILED:
        print(f"FAILED: {len(FAILED)} -> {FAILED}")
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    _lab = None
    try:
        _lab = start_lab()
    except Exception as e:
        print(f"[!] {e}")
        sys.exit(1)
    try:
        rc = main()
    finally:
        if _lab is not None:
            _lab.terminate()
    sys.exit(rc)
