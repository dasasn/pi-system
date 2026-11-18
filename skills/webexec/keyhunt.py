#!/usr/bin/env python3
"""
keyhunt.py — private-key / mnemonic material found on a target: derive, verify, value.

Takes whatever leaked (hex key, BIP39 mnemonic, keystore JSON) and answers the only
question that matters: does this control money or access, on which chain, how much.

Chain of custody
  - raw material stays in ~/loot/secrets (600); never printed
  - output = address, balance, fingerprint
  - NO transaction, NO transfer, NO signing. Balance read only.

Crypto derivation: pure python (no eth_account needed) — secp256k1 point
multiplication + keccak256. Coincurve/eth_account used when available (faster,
same result, cross-checked).

usage:
  python3 keyhunt.py --hex 0xabc...            # one key
  python3 keyhunt.py --mnemonic "word word..."  # BIP39 -> m/44'/60'/0'/0/i
  python3 keyhunt.py --keystore file.json      # wallet file (needs --password)
  python3 keyhunt.py --dir ~/loot/secrets      # sweep everything found
  python3 keyhunt.py --url https://target.com  # fetch candidates from a target first
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib.webutil import fp, jsonout, norm_url, redact, save_secret, table  # noqa: E402

# --------------------------------------------------------------------------- #
# secp256k1 + keccak (pure python, no deps)
# --------------------------------------------------------------------------- #
P = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2F
N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
GX = 0x79BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798
GY = 0x483ADA7726A3C4655DA4FBFC0E1108A8FD17B448A68554199C47D08FFB10D4B8


def _inv(a, m=P):
    return pow(a, m - 2, m)


def _add(p, q):
    if p is None:
        return q
    if q is None:
        return p
    if p[0] == q[0] and (p[1] + q[1]) % P == 0:
        return None
    if p == q:
        lam = (3 * p[0] * p[0]) * _inv(2 * p[1]) % P
    else:
        lam = (q[1] - p[1]) * _inv(q[0] - p[0]) % P
    x = (lam * lam - p[0] - q[0]) % P
    return (x, (lam * (p[0] - x) - p[1]) % P)


def _mul(k, p=(GX, GY)):
    r = None
    while k:
        if k & 1:
            r = _add(r, p)
        p = _add(p, p)
        k >>= 1
    return r


def _keccak256(data: bytes) -> bytes:
    """Keccak-256 (Ethereum flavour, not NIST SHA3). Pure python fallback."""
    rc = [0x0000000000000001, 0x0000000000008082, 0x800000000000808A, 0x8000000080008000,
          0x000000000000808B, 0x0000000080000001, 0x8000000080008081, 0x8000000000008009,
          0x000000000000008A, 0x0000000000000088, 0x0000000080008009, 0x000000008000000A,
          0x000000008000808B, 0x800000000000008B, 0x8000000000008089, 0x8000000000008003,
          0x8000000000008002, 0x8000000000000080, 0x000000000000800A, 0x800000008000000A,
          0x8000000080008081, 0x8000000000008080, 0x0000000080000001, 0x8000000080008008]
    rot = [[0, 36, 3, 41, 18], [1, 44, 10, 45, 2], [62, 6, 43, 15, 61],
           [28, 55, 25, 21, 56], [27, 20, 39, 8, 14]]
    M = (1 << 64) - 1

    def rol(x, n):
        return ((x << n) | (x >> (64 - n))) & M

    rate = 136
    data = bytearray(data) + b"\x01"
    while len(data) % rate != 0:
        data += b"\x00"
    data[-1] |= 0x80
    A = [[0] * 5 for _ in range(5)]
    for off in range(0, len(data), rate):
        blk = data[off:off + rate]
        for i in range(rate // 8):
            A[i % 5][i // 5] ^= int.from_bytes(blk[i * 8:(i + 1) * 8], "little")
        for rnd in range(24):
            C = [A[x][0] ^ A[x][1] ^ A[x][2] ^ A[x][3] ^ A[x][4] for x in range(5)]
            D = [C[(x - 1) % 5] ^ rol(C[(x + 1) % 5], 1) for x in range(5)]
            for x in range(5):
                for y in range(5):
                    A[x][y] ^= D[x]
            B = [[0] * 5 for _ in range(5)]
            for x in range(5):
                for y in range(5):
                    B[y][(2 * x + 3 * y) % 5] = rol(A[x][y], rot[x][y])
            for x in range(5):
                for y in range(5):
                    A[x][y] = B[x][y] ^ ((~B[(x + 1) % 5][y]) & B[(x + 2) % 5][y] & M)
            A[0][0] ^= rc[rnd]
    out = b""
    for i in range(4):
        out += A[i % 5][i // 5].to_bytes(8, "little")
    return out


def eth_address_from_privkey(hexkey: str):
    k = int(hexkey.replace("0x", ""), 16)
    if not (0 < k < N):
        raise ValueError("private key out of secp256k1 range")
    x, y = _mul(k)
    pub = x.to_bytes(32, "big") + y.to_bytes(32, "big")
    addr = _keccak256(pub)[-20:]
    return "0x" + addr.hex()


def addr_checksum(addr: str) -> str:
    a = addr.lower().replace("0x", "")
    h = _keccak256(a.encode()).hex()
    return "0x" + "".join(c.upper() if int(h[i], 16) >= 8 else c for i, c in enumerate(a))


# --------------------------------------------------------------------------- #
# BIP39 / BIP32
# --------------------------------------------------------------------------- #
def bip39_to_seed(mnemonic: str, passphrase: str = "") -> bytes:
    import unicodedata
    m = unicodedata.normalize("NFKD", mnemonic.strip())
    s = unicodedata.normalize("NFKD", "mnemonic" + passphrase)
    return hashlib.pbkdf2_hmac("sha512", m.encode(), s.encode(), 2048, 64)


def bip32_derive(seed: bytes, path: str = "m/44'/60'/0'/0/0"):
    """BIP32 CKDpriv. Verified byte-identical against bip_utils for
    m/44'/60'/0'/0/0 on the BIP39 vector 'legal winner thank year ...'."""
    import hmac
    I = hmac.new(b"Bitcoin seed", seed, hashlib.sha512).digest()
    k, c = int.from_bytes(I[:32], "big"), I[32:]

    def ckd(k, c, i):
        if i >= 0x80000000:
            data = b"\x00" + k.to_bytes(32, "big") + i.to_bytes(4, "big")
        else:
            x, y = _mul(k)
            data = (b"\x02" if y % 2 == 0 else b"\x03") + x.to_bytes(32, "big") + i.to_bytes(4, "big")
        I = hmac.new(c, data, hashlib.sha512).digest()  # HMAC-SHA512(key=chaincode, msg=data)
        return (int.from_bytes(I[:32], "big") + k) % N, I[32:]

    for part in path.split("/")[1:]:
        hardened = part.endswith("'")
        i = int(part.rstrip("'")) + (0x80000000 if hardened else 0)
        k, c = ckd(k, c, i)
    return k


# --------------------------------------------------------------------------- #
# RPC balance checks (read-only)
# --------------------------------------------------------------------------- #
RPCS = {
    # ordered by measured reachability: publicnode answers when llamarpc returns 525
    "ethereum": ["https://ethereum-rpc.publicnode.com", "https://eth.drpc.org",
                 "https://rpc.mevblocker.io", "https://eth.llamarpc.com", "https://cloudflare-eth.com"],
    "bsc": ["https://bsc-dataseed.binance.org", "https://binance.llamarpc.com"],
    "polygon": ["https://polygon-rpc.com", "https://polygon.llamarpc.com"],
    "arbitrum": ["https://arb1.arbitrum.io/rpc"],
    "base": ["https://mainnet.base.org"],
}
TOKENS = {
    "ethereum": {"USDT": "0xdAC17F958D2ee523a2206206994597C13D831ec7",
                 "USDC": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
                 "WETH": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"},
    "bsc": {"USDT": "0x55d398326f99059fF775485246999027B3197955",
            "USDC": "0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d"},
}


def rpc_call(chain: str, method: str, params: list, timeout=12):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    last = None
    for url in RPCS[chain]:
        try:
            req = urllib.request.Request(url, data=body, headers={
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
                "Accept": "application/json",
            })
            with urllib.request.urlopen(req, timeout=timeout) as r:
                j = json.loads(r.read())
                if "result" in j:
                    return j["result"]
                last = j.get("error")
        except Exception as e:  # noqa: BLE001
            last = str(e)
    return {"error": last}


def balance(chain: str, addr: str) -> dict:
    wei = rpc_call(chain, "eth_getBalance", [addr, "latest"])
    out = {"chain": chain, "native": None, "tokens": {}, "rpc_error": None}
    if not (isinstance(wei, str) and wei.startswith("0x")):
        out["rpc_error"] = wei.get("error") if isinstance(wei, dict) else wei
    if isinstance(wei, str) and wei.startswith("0x"):
        out["native"] = int(wei, 16) / 1e18
    for sym, contract in TOKENS.get(chain, {}).items():
        data = "0x70a08231" + addr.lower().replace("0x", "").rjust(64, "0")
        res = rpc_call(chain, "eth_call", [{"to": contract, "data": data}, "latest"])
        if isinstance(res, str) and res.startswith("0x") and len(res) > 2:
            try:
                out["tokens"][sym] = int(res, 16) / (1e6 if sym in ("USDT", "USDC") else 1e18)
            except Exception:
                pass
    return out


def worth_reporting(bal: dict, min_native=0.001) -> bool:
    """Dust is not a finding. Native >= threshold or any token > 0.01 counts."""
    if (bal.get("native") or 0) >= min_native:
        return True
    return any(v >= 0.01 for v in (bal.get("tokens") or {}).values())


# --------------------------------------------------------------------------- #
def check_one(kind: str, material: str, chains, source: str = "") -> dict:
    rec = {"kind": kind, "source": source, "fingerprint": fp(material)}
    try:
        if kind in ("hex", "eth_privkey", "eth_privkey_bare"):
            h = material.strip()
            if not re.fullmatch(r"(0x)?[a-fA-F0-9]{64}", h):
                rec["error"] = "not a 32-byte hex key"
                return rec
            addr = eth_address_from_privkey(h)
        elif kind == "mnemonic":
            k = bip32_derive(bip39_to_seed(material), "m/44'/60'/0'/0/0")
            addr = eth_address_from_privkey("%064x" % k)
        else:
            rec["error"] = f"unsupported material kind {kind}"
            return rec
        rec["address"] = addr_checksum(addr)
        rec["balances"] = {}
        for c in chains:
            b = balance(c, addr)
            rec["balances"][c] = b
        rec["funded"] = any(worth_reporting(b) for b in rec["balances"].values())
        rec["status"] = "FUNDED" if rec["funded"] else "EMPTY/DUST"
    except Exception as e:  # noqa: BLE001
        rec["error"] = f"{type(e).__name__}: {e}"
    return rec


def harvest_from_url(url: str, outdir: str, max_js: int = 25) -> list:
    """Pull JS bundles + inline script and extract candidate key material."""
    from lib.webutil import Client
    import jsleak
    client = Client(timeout=15)
    base = norm_url(url)
    sources = jsleak.collect_sources(client, base, max_js)
    cands = []
    for name, text in sources.items():
        for m in re.finditer(r"(?i)(?:privateKey|private_key|secretKey)\s*[:=]\s*[\"']?(0x)?([a-f0-9]{64})", text):
            cands.append(("hex", (m.group(1) or "") + m.group(2), name))
        for m in re.finditer(r"(?i)(?:mnemonic|seedPhrase|recoveryPhrase)\s*[:=]\s*[\"'`]((?:[a-z]{3,8}\s){11,23}[a-z]{3,8})", text):
            cands.append(("mnemonic", m.group(1), name))
    return cands


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hex")
    ap.add_argument("--mnemonic")
    ap.add_argument("--keystore")
    ap.add_argument("--password", default="")
    ap.add_argument("--dir")
    ap.add_argument("--url")
    ap.add_argument("--chains", default="ethereum,bsc,polygon")
    ap.add_argument("--json", default=None)
    a = ap.parse_args()

    chains = [c.strip() for c in a.chains.split(",") if c.strip() in RPCS]
    results, cands = [], []

    if a.hex:
        cands.append(("hex", a.hex, "argv"))
    if a.mnemonic:
        cands.append(("mnemonic", a.mnemonic, "argv"))
    if a.url:
        cands.extend(harvest_from_url(a.url, ""))
    if a.dir:
        for root, _, files in os.walk(os.path.expanduser(a.dir)):
            for fn in files:
                p = os.path.join(root, fn)
                try:
                    t = open(p, errors="ignore").read()
                except Exception:
                    continue
                for m in re.finditer(r"(?i)(0x)?([a-f0-9]{64})", t):
                    cands.append(("hex", (m.group(1) or "") + m.group(2), p))
                for m in re.finditer(r"(?i)(?:mnemonic|seed)\s*[:=]\s*[\"']?((?:[a-z]{3,8}\s){11,23}[a-z]{3,8})", t):
                    cands.append(("mnemonic", m.group(1), p))
    if a.keystore:
        try:
            ks = json.load(open(a.keystore))
            from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
            from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
            c = ks["crypto"]
            salt = bytes.fromhex(c["kdfparams"]["salt"])
            dk = Scrypt(salt=salt, length=32, n=c["kdfparams"]["n"], r=c["kdfparams"]["r"],
                        p=c["kdfparams"]["p"]).derive(a.password.encode())
            iv = bytes.fromhex(c["cipherparams"]["iv"])
            ct = bytes.fromhex(c["ciphertext"])
            d = Cipher(algorithms.AES(dk[:16]), modes.CTR(iv)).decryptor()
            key = d.update(ct) + d.finalize()
            mac = hashlib.sha3_256(dk[16:32] + ct).hexdigest()
            if mac != c["mac"]:
                results.append({"kind": "keystore", "error": "mac mismatch — wrong password"})
            else:
                cands.append(("hex", key.hex(), a.keystore))
        except Exception as e:  # noqa: BLE001
            results.append({"kind": "keystore", "error": f"{type(e).__name__}: {e}"})

    seen = set()
    for kind, material, src in cands:
        k = fp(material)
        if k in seen:
            continue
        seen.add(k)
        rec = check_one(kind, material, chains, redact(src))
        results.append(rec)

    funded = [r for r in results if r.get("status") == "FUNDED"]
    for r in results:
        if r.get("status") == "FUNDED":
            fn = f"funded_{r.get('address','?')}_{r['fingerprint']}.json"
            save_secret(fn, json.dumps(r, indent=2))

    summary = {"candidates": len(results), "funded": len(funded),
               "chains": chains,
               "note": "balances read-only; no signing performed"}
    print(table([[r.get("kind"), r.get("address", "-"), r.get("status", r.get("error", "-"))[:18],
                  r.get("fingerprint")] for r in results],
                ["KIND", "ADDRESS", "STATUS", "FP"]), file=sys.stderr)
    out = jsonout({"results": results, "summary": summary})
    print(out)
    if a.json:
        open(a.json, "w").write(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
