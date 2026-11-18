---
name: contract-hunt
description: "Smart Contract Vulnerability Hunter — scan kontrak on-chain & sumber untuk bug yang bisa menahan dana (pola Polygon/Binance bridge)"
---
# SKILL: contract-hunt — Smart Contract Vulnerability Hunter

**Purpose:** Cari kontrak yang punya dana nyata dan bug yang bisa membocorkannya. Fokus pada pola yang terbukti dibayar di bug bounty dan yang dipakai di hack besar (access control, proxy storage, reentrancy, accounting drift, arbitrary call).

**Type:** exploit/smartcontract | **Version:** 1.0

---

## PREREQ (sudah terpasang)

| Tool | Path | Cek |
|---|---|---|
| forge / cast / anvil | `~/.foundry/bin` | `cast --version` → 1.9.0 |
| slither | `~/.local/bin/slither` | `slither --version` → 0.11.6 |
| RPC publik | publicnode / mevblocker | `cast block-number` |
| solc | `solc-select install 0.8.24` | untuk compile source |

```bash
export PATH=$PATH:~/.foundry/bin
export RPC=https://ethereum-rpc.publicnode.com
```

---

## KELAS BUG YANG DIBURU (urut nilai bounty)

| # | Kelas | Ciri di kontrak | Dampak |
|---|---|---|---|
| 1 | **Access control terbuka** | `initialize()` tanpa guard, `setOwner` publik, `transferOwnership` tanpa onlyOwner | ambil alih kontrak → drain |
| 2 | **Proxy storage collision** | slot `implementation`/`admin` tak terisi, UUPS tanpa `_authorizeUpgrade` | upgrade ke implementasi jahat |
| 3 | **Arbitrary external call** | `call(target, data)` dengan target dari parameter user | panggil transfer atas nama kontrak |
| 4 | **Reentrancy** | state update setelah `.call{value:}` | tarik dana berulang |
| 5 | **Accounting drift** | `totalAssets` dihitung dari `balanceOf(this)` + donation attack | inflate share, curi vault |
| 6 | **Signature replay / no nonce** | `ecrecover` tanpa nonce/chainId | ulang withdraw |
| 7 | **Unchecked return** | `token.transfer()` diabaikan (USDT-like) | saldo tidak sinkron |
| 8 | **Rounding/dust** | share rounding ke bawah pada deposit kecil | profit berulang |

---

## FASE 1 — TRIAGE KONTRAK (cari yang PUNYA DANA)

```bash
CAST(){ cast "$@" --rpc-url $RPC; }
# saldo ETH
CAST balance $ADDR
# kandidat baru: ambil dari Sourcify / Etherscan API (butuh ETHERSCAN_KEY) atau 4byte
```
**Aturan:** jangan buang waktu pada kontrak saldo 0. Skor target = `ETH balance + token balance`. Prioritaskan > $10k.

Ambil source (Sourcify, tanpa API key):
```bash
curl -s "https://sourcify.dev/server/files/any/1/$ADDR" | head -c 300
# atau repo verified-contracts publik
```

---

## FASE 2 — STATIC ANALYSIS

```bash
# slither pada project lokal
slither . --print human-summary
slither . --detect reentrancy-eth,arbitrary-send-erc20,unprotected-upgrade,suicidal,controlled-delegatecall

# kalau hanya bytecode (tanpa source) — decompile dulu
cast disassemble $(cast code $ADDR --rpc-url $RPC) | head -50
```

## FASE 3 — PEMERIKSAAN MANUAL (yang slither TIDAK tangkap)

```bash
# 1. siapa owner?
CAST call $ADDR "owner()(address)"
# 2. sudah di-initialize?
CAST call $ADDR "initialized()(bool)"
# 3. slot proxy (EIP-1967)
CAST storage $ADDR 0xb53127684a568b3173ae13b9f8a6016e243e63b6e8ee1178d6a717850b5d6103  # admin
CAST storage $ADDR 0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc  # impl
# 4. fungsi publik yang mengubah state
CAST selectors $(cast code $ADDR --rpc-url $RPC) | head
```

## FASE 4 — PoC DI FORK (wajib, jangan klaim tanpa PoC)

```bash
# fork mainnet di blok terkini
anvil --fork-url $RPC --fork-block-number $(CAST block-number) &
# PoC forge test yang membuktikan drain / takeover
forge test --fork-url http://127.0.0.1:8545 -vvv
```
Struktur test minimal:
```solidity
function testExploit() public {
    uint256 before = address(victim).balance;
    vm.startPrank(attacker);
    victim.drain();                      // panggil fungsi rentan
    vm.stopPrank();
    assertGt(address(attacker).balance, before, "no profit");
}
```

## FASE 5 — VALIDASI DAMPAK

| Cek | Perintah |
|---|---|
| Ada dana? | `CAST balance $ADDR` + `CAST call token "balanceOf(address)(uint256)" $ADDR` |
| Bisa dieksekusi tanpa izin? | PoC di fork, `assert` profit |
| Butuh kondisi khusus? | tulis prasyaratnya, kalau tidak terpenuhi → THEORY, bukan finding |

---

## CARA MENEMUKAN TARGET (tanpa API berbayar)

1. **Verified source repo publik** — GitHub search: `path:contracts extension:sol`, `proxy`/`vault`, lalu cocokkan alamat.
2. **Sourcify** — `https://sourcify.dev/server/files/any/1/<addr>` (gratis, no key).
3. **Kontrak baru berdana** — pantau `eth_getBlockByNumber` → ambil `to` address dengan transfer besar.
4. **Etherscan API** kalau operator punya key: `?module=contract&action=getsourcecode&address=`.
5. **Program bounty** (Immunefi) — kontraknya sudah diberi izin + hadiah nyata.

```bash
# contoh: temukan kontrak dengan transfer besar di blok baru
CAST block $(CAST block-number) --json | python3 -c "
import sys,json
b=json.load(sys.stdin)
for t in b['transactions'][:50]:
    print(t['to'], int(t['value'],16)/1e18)"
```

---

## FASE 6 — OUTPUT

```
CONTRACT addr=0x... tvl=12.4 ETH
BUG class=access-control fn=initialize() severity=HIGH
POC fork-block=26388911 result=PROFIT +12.4 ETH status=REPRODUCED
```
Simpan: source → `~/loot/raw/`, PoC → `~/loot/raw/`, temuan → `~/loot/reports/`.

## HARD RULES

- **Tidak ada laporan tanpa PoC fork yang membuktikan profit/drain.** `THEORY` tidak dihitung uang.
- Jangan kirim transaksi on-chain sungguhan. Semua di fork lokal.
- Kontrak target di mainnet = orang lain. Lawful path: **Immunefi / bug bounty**, bukan eksekusi.
- Jangan sentuh kontrak yang bukan scope program bounty tanpa izin tertulis.
