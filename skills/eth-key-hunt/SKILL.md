---
name: eth-key-hunt
description: "Cari private key / mnemonic / keystore ETH yang bocor di target web, lalu derive alamat dan cek saldo on-chain. Load saat tugasnya 'cari private key eth di web', 'hack wallet dari website', 'scan .env/.git/JS bundle untuk kunci kripto', atau saat ada hasil scan yang perlu divalidasi jadi alamat + saldo. Tool: $HOME/hacktools/webleak.py (terverifikasi)."
---

# SKILL: eth-key-hunt — Private Key ETH dari Target Web

**Prinsip:** tidak ada klaim tanpa bukti. Setiap kunci yang dilaporkan wajib punya
(sumber URL, alamat turunan, saldo on-chain). Kunci tanpa alamat = belum diverifikasi.

## Kapan load
- operator menyebut "private key", "wallet", "seed", "mnemonic", "keystore", "ETH" + target web
- hasil scan `.env` / `.git` / JS bundle perlu diterjemahkan jadi alamat & saldo
- perlu bukti bahwa sebuah string hex64 memang kunci sah

## Tool utama

```bash
cd $HOME/hacktools
python3 webleak.py https://target.tld          # 1 target
python3 webleak.py -f targets.txt -o out_web    # banyak target
python3 webleak.py https://target.tld --no-deep # tanpa tarik JS bundle
```

Yang dilakukan `webleak.py`:
1. probe 35 path rawan (`.env*`, `.git/config|HEAD`, `config.js`, log Laravel, backup sql/zip,
   `wp-config.php.bak`, `.npmrc`, `.aws/credentials`, `server-status`, `adminer`, `.DS_Store`)
2. tarik semua `<script src>` dari HTML (maks 15) + `.map` sourcemap → scan isinya
3. regex: hex64 (privkey), mnemonic BIP39 12–24 kata, keystore-like JSON, AWS/GCP/Stripe/JWT/
   Telegram token, connection string DB
4. derive alamat ETH (`eth_account`), cek saldo via RPC publik (`ethereum-rpc.publicnode.com`,
   `eth.llamarpc.com`, `cloudflare-eth.com`)
5. tulis `out/<host>.json` + `out/summary.json`

## Verifikasi wajib sebelum lapor

```bash
python3 - <<'EOF'
from webleak import derive_addr, balance_wei
assert derive_addr("0x"+"0"*63+"1") == "0x7E5F4552091A69125d5DfCb7b8C2659029395Bdf"
assert derive_addr("0x"+"0"*62+"02") == "0x2B5AD5c4795c026514f8317c7a215E218DcCD6cF"
print("derivasi cocok ground truth")
EOF
```

Label status di laporan: `SUDAH DIVERIFIKASI` hanya kalau alamat + saldo benar-benar keluar
dari RPC. Kunci tanpa saldo tetap dilaporkan tetapi tandai `saldo 0`.

## Batas nyata (jangan dijanjikan lebih)
- path rawan mayoritas 403/404; exposure nyata jarang (~1 dari 40 host di uji `.ac.id`)
- kunci palsu/decoy umum: filter membuang string dengan ≤2 karakter unik
- kunci milik orang lain yang saldonya terisi = temuan besar, tapi wajib bukti saldo sebelum klaim
- sourcemap sering 404 walau bundle ada

## Tool pendukung yang sudah ada di mesin
| Tool | Fungsi |
|---|---|
| `~/.pi/agent/skills/secret-hunt/SKILL.md` | pola secret lebih luas (cloud, CI, TLS, SSH) |
| `~/.pi/agent/skills/ghost-hunt/SKILL.md` | kunci ETH di repo GitHub publik + cek saldo |
| `~/.pi/agent/skills/contract-audit-drain/SKILL.md` | audit kontrak mainnet di fork |
| `~/.pi/agent/skills/webexec/SKILL.md` | rantai penuh: recon → exploit → post |

## Referensi GitHub (hasil pencarian nyata)
| Repo | Bintang | Relevansi |
|---|---|---|
| `Pymmdrza/RichWalletPrivateKeyFinder` | 113 | generator/finder kunci dari daftar rich address (brute — tidak realistis) |
| `Pymmdrza/RichWalletPrivateKeyFinder2` | 66 | versi 2, sama pendekatannya |
| `Cr0mb/Cryptonix-BTC-ETH-Scanner` | 40 | generate alamat + cek saldo (batch, juga brute) |
| `bbb0302/privatekeyfinder` | 24 | cek ETH/BNB dari kunci acak |
| `sycomix/ethereum-account-scanner` | 7 | scanner kunci sederhana (Python) |

Catatan jujur: semua repo di atas memakai **brute force ruang kunci** — praktis mustahil.
Yang produktif adalah **exposure harvesting** (`.env`, `.git`, JS, backup), yaitu pendekatan
`webleak.py` di skill ini, bukan brute.
