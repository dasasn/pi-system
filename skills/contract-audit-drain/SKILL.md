---
name: contract-audit-drain
description: "Audit kontrak MAINNET nyata (bukan testnet) untuk celah access control/reentrancy/arbitrary-call, lalu tarik saldo di fork mainnet. Load saat operator memberi address kontrak mainnet atau menanyakan audit+drain kontrak."
---

# SKILL: contract-audit-drain — Mainnet Contract Audit + Drain

**Type:** smartcontract/exploit | **Version:** 1.0 | **Tool:** `tools/contract_audit.py`

**Prinsip:** angka saldo yang dilaporkan HARUS dari RPC mainnet sungguhan. Profit PoC diukur di fork mainnet pada blok nyata. Tidak ada testnet, tidak ada kontrak dummy.

---

## HARD RULES (baca dulu, jangan dilanggar)

| # | Aturan | Kenapa |
|---|---|---|
| 1 | **Mainnet only.** Testnet, anvil lokal tanpa fork, dan kontrak yang kita deploy sendiri = tidak dihitung. | Angka di testnet bukan aset nyata. |
| 2 | **Chain id harus salah satu** dari `MAINNET_CHAIN_IDS` (1, 56, 137, 42161, 8453, 10, 1776). | Guard di `assert_mainnet()`. |
| 3 | **Fork block harus blok mainnet terkini**, bukan `block 0`. | State saldo harus real. |
| 4 | **Tidak ada laporan "bisa drain" tanpa PoC yang PASS di fork mainnet** dan profit terukur di baris `attacker native after`. | Klaim tanpa PoC = THEORY, bukan finding. |
| 5 | **Eksekusi tx ke mainnet hanya dengan izin tertulis** dari pemilik kontrak atau program bounty (Immunefi). Kalau tidak ada izin: PoC di fork, hasil dilaporkan, tidak dikirim. | Kontrak orang lain di mainnet. Eksekusi tanpa izin = tindak pidana. |
| 6 | **Jangan pernah pakai `--chain ""` atau nama testnet.** | Ditolak tool. |

---

## PREREQ

```bash
export PATH=$PATH:$HOME/.foundry/bin
cast --version        # 1.9.0
anvil --version
solc --version        # 0.8.26
python3 -c "from eth_hash.auto import keccak; print('keccak ok')"
```

RPC mainnet dipakai dengan fallback otomatis (curl + UA browser, karena publicnode kena 403 dari urllib):

| Chain | Endpoint fallback |
|---|---|
| ethereum | publicnode → llamarpc → ankr → cloudflare-eth |
| bsc | bsc-dataseed1/2.bnbchain.org → blockrazor → publicnode |
| polygon | publicnode → polygon-rpc → ankr |
| arbitrum | publicnode → arb1.arbitrum.io |
| base | publicnode → mainnet.base.org |
| optimism | publicnode → mainnet.optimism.io |
| injective-evm | sentry.evm-rpc.injective.network |

---

## PIPELINE

```
TRIAGE  -> code, native balance, ERC20 balance (mainnet)
STATIC  -> 17 rule (AC/UP/RE/SG/TK/RD/OR/IN)
ONCHAIN -> owner(), initialized(), proxy slots EIP-1967
POC     -> Foundry test digenerate dari finding
DRAIN   -> forge test --fork-url <mainnet RPC> pada blok terkini
```

### FASE 1 — Triage (mainnet)

```bash
cd /mnt/d/hephaestus/tools
python3 contract_audit.py --address 0xTARGET --chain bsc
```

Output wajib menunjukkan `code=` > 0 dan `native=` / `token` dari RPC nyata.
Kalau `code=0B` → alamat EOA atau belum deploy → **stop**, bukan target.

Contoh hasil nyata (BSC USDT):
```
[*] 0x55d398326f99059Ff775485246999027B3197955 @ bsc
    code=4413B native=0.0
    token USDT: 10828951.04549011
    TVL est ~$10,843,157.87
```

### FASE 2 — Source

Ambil source dulu. Tanpa source, audit statis tidak jalan.
```bash
# Sourcify (gratis, tanpa key)
curl -s "https://sourcify.dev/server/files/any/<chainId>/<address>"

# Blockscout (BSC/polygon base)
curl -s "https://bscscan.com/address/<addr>#code"

# Etherscan API kalau operator punya key
curl -s "https://api.etherscan.io/api?module=contract&action=getsourcecode&address=<addr>&apikey=$ETHERSCAN_KEY"
```

### FASE 3 — Audit statis + on-chain state

```bash
python3 contract_audit.py --address 0xTARGET --chain bsc --source Target.sol --mode audit
```

Rule yang dicek (17):

| ID | Kelas | Severity |
|---|---|---|
| AC-01 | `initialize()` tanpa guard | CRITICAL |
| AC-02 | `setOwner`/`transferOwnership` publik | CRITICAL |
| AC-03 | `selfdestruct` tanpa guard | CRITICAL |
| OR-02 | `.call(addressDariParameter, data)` | CRITICAL |
| UP-01 | `delegatecall` ke alamat parameter | CRITICAL |
| UP-02 | UUPS tanpa `_authorizeUpgrade` | HIGH |
| UP-03 | Proxy admin slot | HIGH |
| RE-01 | State update setelah `.call{value:}` | HIGH |
| RE-02 | Zeroing setelah transfer | HIGH |
| AC-04 | `totalAssets` dari `balanceOf(this)` | HIGH |
| SG-01 | `ecrecover` tanpa nonce/chainId | HIGH |
| OR-01 | `tx.origin` auth | HIGH |
| SG-02 | Signature tanpa deadline | MEDIUM |
| TK-01 | `transfer()` return diabaikan | MEDIUM |
| RD-01 | Pembagian tanpa ceil | MEDIUM |
| IN-01 | Loop tanpa batas | MEDIUM |
| TK-02 | `approve` race | LOW |

State probe on-chain (jalan otomatis kalau `--source` dipakai):
```
owner        -> owner()(address)
admin        -> admin()(address)
initialized  -> initialized()(bool)
proxy_admin  -> slot 0xb53127684...
proxy_impl   -> slot 0x360894a1...
```

Interpretasi:
- `owner` = `0x0000...` → belum di-set → cek AC-01/AC-02
- `initialized` = `false` → initialize() bisa dipanggil siapa pun → **CRITICAL**
- `proxy_impl` terisi tapi `proxy_admin` kosong → proxy tanpa admin → UP-03

### FASE 4 — PoC + Drain di fork mainnet

```bash
python3 contract_audit.py --address 0xTARGET --chain bsc --source Target.sol --mode drain
```

Yang terjadi:
1. `anvil --fork-url <RPC mainnet> --fork-block-number <blok terkini>` → state mainnet nyata
2. `forge test --fork-url http://127.0.0.1:<port> -vv` → PoC dijalankan
3. Profit diukur dari `attacker native after` vs sebelum

Status yang valid:
```
poc_status = reproduced  -> PROFIT <n> native (di fork mainnet)
poc_status = failed      -> PoC jalan, tidak ada profit (aman / butuh param)
poc_status = timeout     -> naikkan timeout / ganti RPC
```

**Kriteria "ADA CELAH":** `poc_status == reproduced` DAN `poc_profit_native > 0`.

Kalau tidak keduanya → bukan celah yang bisa dipakai. Jangan dilaporkan sebagai profit.

### FASE 5 — Eksekusi nyata (HANYA dengan izin)

Syarat mutlak sebelum kirim tx mainnet:
1. Izin tertulis dari pemilik kontrak ATAU kontrak masuk scope bug bounty (Immunefi/Code4rena)
2. Private key milik operator (bukan key target)
3. PoC sudah `reproduced` di fork pada blok terkini
4. Saldo gas cukup di akun operator

Kalau satu saja tidak terpenuhi → **berhenti di fork**. Laporkan PoC + profit simulasi, jangan broadcast.

---

## TEMPLATE LAPORAN

```
CONTRACT 0x... chain=bsc block=<n> code=4413B
BALANCE  native=0.0 USDT=10,828,951 tvl~$10.8M
RULES    AC-01 initialize() unprotected
         RE-01 withdrawAll state-after-call
ONCHAIN  owner=0x0000..0 initialized=false
POC      fork-block=<n> status=reproduced profit=+12.4 native
VERDICT  DRAINABLE (fork-verified)
ACTION   menunggu izin tertulis / kontrak bounty
```

---

## ANTI-POLA (jangan lakukan)

| Salah | Benar |
|---|---|
| Lapor "vulnerable" karena regex cocok | Lapor setelah PoC PASS di fork |
| Pakai anvil tanpa `--fork-url` | `--fork-url <mainnet RPC> --fork-block-number <n>` |
| Harga saldo diambil dari kalkulasi sendiri | `eth_getBalance` + `balanceOf` dari RPC mainnet |
| "TVL $10M bisa diambil" tanpa PoC | Tulis `poc_status=failed` kalau tidak lolos |
| Broadcast tx ke mainnet karena "sudah yakin" | Broadcast hanya dengan izin tertulis |
| Uji di Sepolia/BSCT lalu klaim mainnet | Semua pengukuran di chain id mainnet |

---

## COMMAND REFERENCE

```bash
cd /mnt/d/hephaestus/tools

# 1 kontrak, auto RPC fallback
python3 contract_audit.py --address 0xABC --chain bsc

# dengan source -> static + onchain + poc
python3 contract_audit.py --address 0xABC --chain ethereum --source T.sol --mode drain

# batch
python3 contract_audit.py --file targets.txt --chain polygon --mode audit

# output
#   contract_audit.json    -> semua hasil
#   /tmp/contract_audit/   -> project foundry + poc_output.txt
```

`targets.txt`:
```
0xABC...|label
0xDEF...|label2
```
