---
name: ghost-hunt
description: "GitHub ETH Key Hunter — cari private key berisi SALDO NYATA di repo publik (bukan dust)"
---
# SKILL: ghost-hunt — GitHub ETH Key Hunter dengan Filter Saldo

**Purpose:** Cari private key Ethereum yang bocor di repo publik GitHub, lalu **hanya laporkan yang punya saldo nyata**. Dust (< $1) dibuang. Ini skill khusus supaya tidak buang waktu pada 287 key yang semuanya kosong.

**Type:** recon/access/crypto | **Version:** 1.0

---

## PREREQ

| Item | Cek |
|---|---|
| `GH_TOKEN` (PAT, scope kosong) | `[ -n "$GH_TOKEN" ]` |
| `eth_account` | `python3 -c "import eth_account"` |
| RPC publik | `eth.llamarpc.com` / `rpc.mevblocker.io` / `publicnode` |
| Tools | `~/loot/tools/ethkey.py`, `~/loot/tools/gh_deep_hunt.py` |

---

## FASE 0 — SETUP TOKEN (jangan cetak nilainya)

```bash
export GH_TOKEN=$(grep "^export GH_TOKEN=" ~/.bashrc | sed 's/^export GH_TOKEN=//')
[ ${#GH_TOKEN} -gt 40 ] || { echo "TOKEN KOSONG"; exit 1; }
curl -s -m 15 -H "Authorization: Bearer $GH_TOKEN" -o /dev/null -w "auth=%{http_code}\n" https://api.github.com/user
# 200 = valid. 401 = token mati, minta operator rotate.
```

**Batasan wajib diingat:** code search = **10 req/menit**, 30 hasil/halaman untuk non-enterprise.
Kalau `403` → `sleep 60`. Jangan hammer, akun bisa di-flag.

---

## FASE 1 — QUERY PRODUKTIF (urut dari paling banyak hasil)

| Query | Total (2026-11) | Kualitas |
|---|---|---|
| `PRIVATE_KEY=0x extension:env` | 1.832 | tertinggi |
| `MNEMONIC= extension:env` | 1.394 | tinggi (mint/keypair) |
| `pk=0x extension:env` | 64 | tinggi |
| `SEED_PHRASE extension:env` | 90 | sedang |
| `"privateKey":"0x" extension:json` | 18 | tinggi |
| `WALLET_PRIVATE_KEY` | 48.768 | rendah (banyak noise) |

Cara ambil lebih banyak per query:
```bash
# GitHub code search via API: max 100/halaman, tapi hasil praktis dibatasi engine
curl -s -H "Authorization: Bearer $GH_TOKEN" \
  "https://api.github.com/search/code?q=$(python3 -c \
  "import urllib.parse;print(urllib.parse.quote('PRIVATE_KEY=0x extension:env'))")&per_page=100&page=1"
```

---

## FASE 2 — FILTER SEBELUM DOWNLOAD (hemat kuota)

```python
FP_PATH = re.compile(r"(test|spec|example|sample|mock|fixture|demo|node_modules|\.md$|README|docs?/)", re.I)
```
Buang path itu **sebelum** fetch. Menghemat ~60% request dan menghilangkan hampir semua false positive.
Setelah download, wajib ada `[a-fA-F0-9]{64}` — kalau tidak, hapus file.

---

## FASE 3 — VALIDASI ON-CHAIN (INTI SKILL)

```bash
python3 ~/loot/tools/ethkey.py <folder>
```
Pipeline: regex 64-hex → `Account.from_key()` → `eth_getBalance` (3 RPC fallback) → JSON.

### Ambang keputusan — INI YANG MEMBUANG DUST

| Saldo | Verdict | Aksi |
|---|---|---|
| `0` | mati | buang |
| `>0` tapi `< 0.005 ETH` (~$15) | **DUST** | **buang — tidak bisa diuangkan, gas lebih mahal** |
| `>= 0.005 ETH` | **FUNDED** | simpan ke validated/ |

```python
MIN_ETH = 0.005          # ~$15; di bawah ini tidak ekonomis
if bal >= MIN_ETH: status = "FUNDED"
elif bal > 0:      status = "DUST"
else:              status = "EMPTY"
```

**Bukti lapangan:** run 186 file / 287 key menemukan 1 "funded" = `2.11e-12 ETH` = **$0.0000000063**. Itu dust. Tanpa ambang, laporan akan berbohong "ada temuan".

---

## FASE 4 — KONFIRMASI & TRIAGE

Untuk setiap DUST/FUNDED, cari file sumbernya (jangan cuma address):

```python
# temukan file asal key
for f in pathlib.Path(folder).rglob('*'):
    for m in re.finditer(r"(?:0x)?([a-fA-F0-9]{64})", f.read_text('utf8','ignore')):
        if Account.from_key("0x"+m.group(1)).address.lower() == target.lower():
            print("FILE:", f, "context:", ...)
```
Klasifikasi konteks:
- `.env` bot trading → key aktif, cek saldo token juga (ERC20), bukan cuma ETH
- `.env` deploy script testnet → hampir pasti kosong
- `SK=` dengan baris `#` di atasnya → key usang/komentar

**Cek token, bukan hanya ETH:** address bisa 0 ETH tapi punya USDT/USDC.
```bash
# USDT contract: 0xdAC17F958D2ee523a2206206994597C13D831ec7
curl -s -X POST https://ethereum-rpc.publicnode.com -H "Content-Type: application/json" \
 -d '{"jsonrpc":"2.0","id":1,"method":"eth_call","params":[{"to":"0xdAC17F958D2ee523a2206206994597C13D831ec7","data":"0x70a08231000000000000000000000000ADDRESS_HERE"},"latest"]}'
```

---

## FASE 5 — OUTPUT

```
FOUND address=0x... balance=1.23 ETH status=FUNDED token_USDT=0.00 source=<repo/path>
```
- FUNDED → `~/loot/validated/`, key asli → `~/loot/secrets/` (600, jangan print)
- DUST → catat di laporan sebagai negative result, jangan dianggap temuan
- Rekap: `checked`, `rpc_errors`, `funded`, `dust`

---

## HARD RULES

1. **Jangan pernah sebut "ada saldo" tanpa nilai + nilai USD.** Dust ≠ temuan.
2. Key asli tidak dicetak ke chat/log — hanya fingerprint + lokasi.
3. Rate limit 10/menit; 403 = tunggu 60s, jangan retry cepat.
4. Token tidak pernah ditampilkan; kalau terlanjur tampil, minta operator rotate.
5. Repo publik bukan izin memakai dana. Ini untuk laporan/riset, bukan penarikan.

---

## PITFALLS (dari run nyata)

- `PRIVATE_KEY` di repo besar hampir selalu test vector anvil/hardhat (`0xac0974...`, `0x59c6995e...`). Kenali dan skip.
- `extension:env` di GitHub search **tidak** menemukan file bernama persis `.env` (dotfile) — banyak yang lolos. Coba juga `path:.env`.
- Key dengan `0` ETH sering punya token. Cek ERC20 sebelum buang.
- RPC gratis sering -1/timeout: wajib 3 fallback, kalau tidak hasil "0 funded" itu palsu.
