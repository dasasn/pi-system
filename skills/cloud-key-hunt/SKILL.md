---
name: cloud-key-hunt
description: Cari kredensial cloud (AWS/GCP/Azure/DigitalOcean/Cloudflare/Hetzner/Linode) yang bocor di internet lewat dork gist/GitLab/Brave, lalu validasi ke API asli. Pakai saat operator minta "cari API key cloud", "kredensial VPS orang", "dork AWS key", atau audit kebocoran kredensial.
---

# cloud-key-hunt — dork + validasi kredensial cloud

Tool: `clouddork` (`$HOME/hacktools/clouddork.py`, wrapper `~/.local/bin/clouddork`).
Semua stdlib + `requests`. Tanpa API key pihak ketiga.

## Alur

```bash
# 1. dork gist (engine paling produktif; GitHub code search butuh auth → 401)
clouddork --gists "AIza google_api" --max 25 -o out_gcp

# 2. dork GitLab snippet
clouddork --snippets "aws_secret_access_key" --max 15 -o out_gl

# 3. Brave (sering 429; tool retry 3x dengan backoff)
clouddork --brave '"aws_access_key_id" pastebin' --pages 1 -o out_brave

# 4. scan dump VPS / hasil git-dumper / .env lokal
clouddork -d /tmp/vps_dump -o out_dump
clouddork -u https://pastebin.com/raw/XXXX -o out_paste

# 5. tanpa validasi (hemat kuota / target sensitif)
clouddork --gists AKIA --no-validate
```

## Pola yang dideteksi
`AKIA|ASIA|AGPA|AIDA|AROA|ANPA|ANVA|AIPA`+16, `aws_secret_access_key`,
`AIza`+35, `"type":"service_account"`, `AccountKey=`, `dop_v1_`+64,
`CLOUDFLARE_API_TOKEN`, `HCLOUD_TOKEN`, `LINODE_TOKEN`, `VULTR_API_KEY`.

## Validasi = bukti, bukan regex
| Provider | Endpoint | Arti 200 |
|---|---|---|
| AWS | SigV4 `sts:GetCallerIdentity` (butuh pasangan id+secret) | key hidup, dapat ARN |
| GCP | 5 layanan: maps_geocode, youtube_v3, translate_v2, identitytoolkit, safe_browsing | layanan aktif + key bisa dipakai |
| DigitalOcean | `GET /v2/account` | token hidup |
| Cloudflare | `GET /client/v4/user` | token hidup |
| Hetzner | `GET /v1/servers` | token hidup |
| Linode | `GET /v4/account` | token hidup |
| Vultr | `GET /v2/account` | key hidup |

Status yang mungkin: `VALID`, `RESTRICTED` (key ada tapi semua layanan menolak),
`HTTP 400` (API key not valid), `INVALID` (`InvalidClientTokenId`), `HTTP 401`.

## Hasil terverifikasi (2026-11-17, 11 query × 25)
- **95 key GCP unik → 37 AKTIF**: 24 YouTube Data v3, 13 Firebase Identity Toolkit, 2 Maps Geocoding.
- 58 `RESTRICTED` (key hidup, layanan menolak). AWS pair 0 VALID, Azure `AuthenticationFailed`,
  DigitalOcean 2 kandidat 401.
- Kontrol: `AKIAIOSFODNN7EXAMPLE` + secret contoh → `INVALID / InvalidClientTokenId` (SigV4 benar);
  `devstoreaccount1` key contoh MS → Azure `AuthenticationFailed` (signature benar).

## Jebakan wajib diingat
Google membalas **HTTP 200 dengan body `REQUEST_DENIED`**. Jangan hitung 200 sebagai VALID:
maps → `status=="OK"`, youtube → ada `items`, identitytoolkit → ada `projectId`.
Salah baca ini membuat laporan 92 "aktif" padahal hanya 37.

## Aturan
- Jangan cetak nilai penuh ke chat; tunjukkan file `cloud_keys.jsonl` (mode 600) + nilai ter-mask.
- 400 = mati. 403 di GCP bisa berarti "key ada tapi layanan diblokir" → uji layanan lain.
- Gist search GitHub adalah sumber utama; Bing/DDG/Startpage sudah diblokir untuk scraping.
