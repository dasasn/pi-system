---
name: hexbrain-knowledge
description: Payload + bypass library hasil scrape hexbrainai.com (64 topik payload/teknik, 18 kategori bypass dari 2.170 laporan bug bounty disclosed). Load saat butuh payload siap pakai, teknik bypass WAF/authz/2FA/upload, atau referensi kelas kerentanan saat menyerang target web.
---

# HexBrain Knowledge Base — payload & bypass library

Sumber: `https://hexbrainai.com` (di-scrape 2026-11-14). 405.486 CVE terdaftar, 1.123 passage payload
dalam 64 topik, 2.170 kasus bypass dalam 18 kategori, 15.244 laporan bug bounty disclosed.

## Struktur
```
skills/
  payloads/   # 64 topik — apa yang dikirim untuk tiap jenis bug (termasuk varian bypass filter)
  bypasses/   # 18 kategori — bagaimana peneliti lain lolos dari proteksi nyata
```

## Payload (`skills/payloads/*.txt`) — pilih sesuai temuan
| Kebutuhan | File |
|---|---|
| Ambil alih akun | `Account_Takeover.txt` |
| Kebocoran kunci/secret | `API_Key_Leaks.txt` |
| RCE lewat perintah shell | `Command_Injection.txt` |
| Injection SQL / NoSQL | `SQL_Injection.txt`, `NoSQL_Injection.txt` |
| Template injection (SSTI) | `SSTI_Server_Side_Template_Injection.txt` |
| Deserialization | `Insecure_Deserialization.txt` |
| Baca file sembarang | `File_Inclusion.txt`, `Directory_Traversal.txt` |
| Bypass upload | `Upload_Insecure_Files.txt` |
| SSRF | `SSRF_Server_Side_Request_Forgery.txt` |
| XXE | `XXE_Injection.txt` |
| XSS | `XSS_Injection.txt` |
| GraphQL | `GraphQL_Injection.txt` |
| Race condition | `Race_Conditions.txt` |
| Auth/JWT | `JWT.txt`, `Authentication.txt` |
| Cache poisoning | `Web_Cache_Deception.txt`, `HTTP_Request_Smuggling.txt` |
| Kerentanan browser | `DOM_Clobbering.txt`, `XS-Leak.txt`, `Clickjacking.txt` |

Lihat nama lengkap: `ls skills/payloads/`

## Bypass (`skills/bypasses/*.txt`) — pilih sesuai hambatan
| Hambatan | File |
|---|---|
| WAF memblokir payload | `waf.txt`, `filter.txt` |
| 403 karena role/izin | `access.txt` |
| Login/SSO/session menolak | `login.txt`, `token.txt` |
| 2FA/OTP | `2fa.txt`, `verify.txt` |
| Path traversal difilter | `path.txt` |
| Upload ditolak | `upload.txt` |
| SSRF diblokir | `ssrf.txt` |
| Rate limit | `rate.txt` |
| CSP memblokir XSS | `csp.txt` |
| CORS diblokir | `cors.txt` |
| CSRF token | `csrf.txt` |
| Sandbox lolos | `sandbox.txt` |
| Redirect dicek | `redirect.txt` |
| Perbaikan sudah dipasang | `fix.txt` |

## Cara pakai
1. Recon dulu: stack, versi, WAF, titik input.
2. Buka file payload yang cocok, ambil varian, sesuaikan konteks (encoding, quote, parameter).
3. Kalau diblokir: buka file bypass yang cocok, jangan mengulang payload yang sama.
4. Verifikasi hasil dengan bukti nyata (output perintah, isi record), bukan status code.

## Catatan
- Semua isi adalah referensi teknis dari laporan publik; penerapan pada target tetap tanggung jawab operator.
- File sudah plain-text, siap di-`grep`:
  `grep -ril "bypass" skills/payloads/*.txt | head`
