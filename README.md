# pi-system — instalasi pi/free-pi milik operator

Repo ini menyimpan **seluruh sistem pi**: aturan operator v3.1, launcher + patcher bundle,
konfigurasi agent, tema ungu, unit systemd, 91 skill, 65 tool ofensif, dan audit bundle.
Tujuan: bisa dipasang ulang di mesin lain (Ubuntu, WSL, **Termux Android**) dengan perilaku sama.

---

## 1. Cara install

### A. Termux (Android)

```bash
pkg update && pkg install -y git
git clone <repo-url> ~/pi-system && cd ~/pi-system
bash bootstrap.sh
free-pi-cli
```

`bootstrap.sh` mendeteksi Termux (`$PREFIX` berisi `com.termux`) lalu:
1. `pkg install nodejs-lts git python jq curl unzip ripgrep nmap termux-tools termux-api`
2. `termux-wake-lock` supaya proses tidak dibunuh Android
3. `npm install -g free-pi-cli` (tanpa sudo, ke `$PREFIX/lib/node_modules`)
4. `install.sh` — pasang aturan, launcher, patcher, 91 skill, 65 tool
5. Penjadwal: `~/.agent-rules/guard-loop.sh` (loop 60 detik) + hook `~/.termux/boot/start-guard.sh`

Tambahan agar otomatis setelah HP reboot: install app **Termux:Boot**, buka sekali.
Kalau tanpa Termux:Boot, jalankan manual tiap sesi baru:

```bash
bash ~/.agent-rules/guard-loop.sh &
```

Catatan Termux: `pkg install termux-api` + izin Termux:API untuk notifikasi; jangan pakai
storage `/sdcard` (tidak mendukung `chmod`/symlink) — pakai `$HOME`.

### B. Ubuntu / Debian / WSL

```bash
git clone <repo-url> ~/pi-system && cd ~/pi-system
bash bootstrap.sh
free-pi-cli
```

Bootstrap: `apt install curl git jq python3 build-essential ripgrep nmap` → Node 22 via nvm
(pi butuh zstd, minimal Node 22.15) → `npm i -g free-pi-cli` → `install.sh` → penjadwal
`systemd --user` (`rules-guard.timer`, `pi-maintenance.timer`). Di WSL tanpa systemd otomatis
fallback ke `guard-loop.sh` + cron `@reboot`.

### C. Sudah ada Node + free-pi-cli (install cepat)

```bash
bash install.sh
node ~/.free-pi/bin/bundle-patch.cjs --newest
bash ~/.agent-rules/rules-guard.sh
```

### D. Uji tanpa menyentuh sistem (`--dry-run`)

```bash
bash bootstrap.sh --dry-run          # tampilkan langkah, tidak mengeksekusi
PREFIX=/data/data/com.termux/files/usr bash bootstrap.sh --dry-run   # simulasi Termux
```

### Syarat minimum
Node ≥ 22.15 (butuh `zlib.createZstdDecompress`), `python3`, `git`, `npm`.
Cek: `node -e 'process.exit(typeof require("zlib").createZstdDecompress==="function"?0:1)' && echo ok`

---

## 1E. SUDAH PUNYA PI — cara update

Kalau di mesin itu pi/free-pi sudah terpasang (versi lama), **jangan** cuma `npm i -g`:
launcher menimpa bundle terpasang dengan salinan PIN, jadi versi lama akan kembali.
Urutan yang benar sudah dibungkus di `update.sh`:

```bash
cd ~/pi-system && git pull          # ambil aturan + patcher terbaru
bash update.sh                      # update paket → bangun ulang pin → patch → guard → verifikasi
free-pi-cli                         # sesi baru memakai versi + aturan baru
```

`update.sh` melakukan lima hal berurutan:
1. `npm install -g free-pi-cli@latest` (Termux: `pkg update` dulu, npm tanpa sudo)
2. cari bundle terpasang (`main-*.js`) di nvm / `$PREFIX` / `/usr/local` / cache npx
3. **bangun ulang pin** `~/.free-pi/state/pinned/main-*.js` dari bundle baru, jalankan
   `bundle-patch.cjs`, lalu tolak hasilnya kalau `node --check` gagal atau penanda
   (`__OPGATE_FS`, `__PI_LOCAL_DEFENSE__`, `operator-gate.md`, `__NOUPD:cv`, `__NOUPD:ru`,
   `theme: "ungu"`) hilang
4. salin pin ke bundle terpasang + jalankan `rules-guard.sh` (dan restart timer/loop guard)
5. cetak verifikasi: versi, sha pin vs dist, penanda no-update, tema, 3 baris `guard.log`

Varian yang berguna:

```bash
bash update.sh --dry-run     # lihat langkahnya saja
bash update.sh --no-npm      # paket tidak disentuh, hanya pin di-rebuild + patch ulang
```

Kalau langkah 3 menolak ("penanda ... hilang"), artinya rilis baru mengubah kode dan anchor
patcher perlu disesuaikan: baca changelog/rilis upstream, perbarui anchor di
`free-pi/bin/bundle-patch.cjs`, lalu jalankan `bash update.sh --no-npm` lagi.

Cara manual tanpa script (kalau `update.sh` tidak ada):

```bash
npm install -g free-pi-cli@latest
node ~/.free-pi/bin/bundle-patch.cjs --newest        # patch bundle yang baru
cp ~/.nvm/versions/node/*/lib/node_modules/free-pi-cli/dist/main-*.js ~/.free-pi/state/pinned/ 2>/dev/null
bash ~/.agent-rules/rules-guard.sh
free-pi-cli --version
```

## 2. Verifikasi setelah install

```bash
sha256sum ~/.agent-rules/operator.AGENTS.md.master ~/.free-pi/agent/AGENTS.md ~/AGENTS.md
ls -l ~/.claude/CLAUDE.md ~/.codex/AGENTS.md ~/.pi/agent/AGENTS.md
find ~/.agent-rules/skills -name SKILL.md | wc -l      # harus 91
ls ~/hacktools | head                                   # harus ada autohack.py, autopilot.py
tail -5 ~/.agent-rules/guard.log                        # tidak boleh ada CRITICAL
```

Semua jalur aturan harus punya sha256 **sama**. Kalau beda: `bash ~/.agent-rules/rules-guard.sh`.

---

## 3. Aturan ikut terpasang (bukan cuma tool)

`install.sh` menaruh aturan v3.1 ke **sembilan jalur**:

| Jalur | Peran |
|---|---|
| `~/.agent-rules/operator.AGENTS.md.master` | master, sumber kebenaran (perm 444) |
| `~/AGENTS.md` | live root |
| `~/.free-pi/agent/AGENTS.md` + `APPEND_SYSTEM.md` | dibaca free-pi, ditempel ke system prompt oleh patcher |
| `~/.pi/agent/AGENTS.md`, `~/.agents/AGENTS.md` | agent lain |
| `~/.claude/CLAUDE.md`, `~/.codex/AGENTS.md`, `~/.config/opencode/AGENTS.md` | symlink ke `~/AGENTS.md` |
| `~/.free-pi/agent/skills`, `~/.claude/skills`, `~/.pi/agent/skills`, `~/.agents/skills` | symlink ke 91 skill |

`rules-guard.sh` memulihkan semuanya tiap 60 detik kalau sebuah update menimpanya.
Batas jujur: aturan mengikat agent yang membaca file di mesin itu (pi/free-pi, Claude Code,
Codex, opencode). Layanan web di luar mesin tidak membaca file ini.

---

## 4. Isi repo

| Path | Isi |
|---|---|
| `rules/AGENTS.md` | Aturan operator v3.1 (master) |
| `rules/rules-guard.sh` | Penjaga aturan: restore + sinkron tiap 60 dtk |
| `rules/README.agent-rules.md` | Cara kerja lapisan proteksi aturan |
| `free-pi/bin/free-pi` | Launcher: restore pinned bundle → patch → maint → exec |
| `free-pi/bin/bundle-patch.cjs` | Patcher idempoten (operator gate, telemetri off, no-update, tema ungu) |
| `free-pi/state/maint.sh` | Maintenance: manifest, pin rebuild, config rewrite |
| `agent/` | `settings.json`, `default-model.json`, `models.json`, `operator-gate.md`, `themes/*`, `extensions/*` |
| `systemd/` | `rules-guard.*`, `pi-maintenance.*`, `operator-guard.*`, `freepi-shim.service` |
| `skills/` | 468 file, 91 SKILL.md (red-team, webexec, cpanel, kripto, autohack, …) |
| `hacktools/` | 65 file: autohack, autopilot, acidhunt, keyharvest, webleak, clouddork, cpanel chain |
| `audit/` | `LAPORAN.md`, `patch_pi.py`, `source/*.ts` hasil carve, draft aturan |
| `bootstrap.sh` `install.sh` `export.sh` `update.sh` `sanitize-public.sh` | pemasangan (Termux/WSL/Ubuntu), ekspor ulang, segarkan repo, **update versi** |

---

## 5. Patch yang diterapkan ke bundle free-pi

Lewat `free-pi/bin/bundle-patch.cjs`, idempoten, berbasis anchor:

1. **operator-gate** — `operator-gate.md` + `AGENTS.md` jadi blok terakhir system prompt.
2. **model** — `PI_LOCAL_DEFENSE` / `PI_LOCAL_MODEL` (opsional).
3. **version floor** — tidak pernah force-exit karena versi.
4. **tools** — approval tool lokal tanpa round-trip (`PI_LOCAL_ALLOW`).
5. **telemetry** — semua reporter (`/telemetry/*`, funnel, refill, starter, resume) dimatikan.
6. **choice-telemetry** — posting counter dimatikan.
7. **theme ungu** — default tema `ungu` (violet), warna di `agent/themes/ungu.json`.
8. **no-update** — `/client-version` tidak dipanggil; `npm install -g` & `npx @latest` mati; `/update` mati.

Bukti audit: `audit/LAPORAN.md`.

---

## 6. Tema

`ungu` = violet (`okhsl(285 …)`), diset di `agent/settings.json` dan dipaksa di bundle oleh
patcher langkah 7. Tema lain: taruh `<nama>.json` di `~/.free-pi/agent/themes/`.

---

## 7. Segarkan repo dari mesin yang sedang jalan

```bash
cd ~/pi-system && bash export.sh
git add -A && git commit -m "sync $(date +%F)" && git push
```

`export.sh` menarik ulang rules, bin, agent, skills, hacktools, audit; memindai pola kunci
nyata; dan menghapus file kredensial kalau ikut tersalin.

---

## 8. Push ke GitHub

```bash
cd ~/pi-system
git remote add origin user@example.com:<user>/<repo>.git     # atau https://…
git branch -M main
git push -u origin main
```

Repo berisi toolkit ofensif + aturan operator: set **private** kecuali memang ingin publik.

---

## 8B. Repo publik — kebersihan wajib

Repo ini aman untuk **public** karena data target & kredensial sudah dibuang:

```bash
bash sanitize-public.sh          # hapus data/bukti, redaksi email+IP nyata, path pribadi
git add -A && git commit -m "sync"
git push
```

Yang dilakukan `sanitize-public.sh`:
1. hapus file data hasil kerja (`vpshunt.json`, daftar domain target, `*.jsonl`, `ct/`,
   `siak_src/`, `proof/`, `ytdata/`, `produk/`, semua `*case-study*`)
2. redaksi email nyata → `user@example.com` (placeholder `@example/@test/@target` dibiarkan)
3. redaksi IP publik nyata → `203.0.113.10` (RFC 5737); IP privat & dokumentasi tidak diubah
4. ganti `/home/<user>/` → `$HOME` / `~/`
5. pindai ulang pola kunci (`AKIA…`, `ghp_…`, `sk-…`, `BEGIN PRIVATE KEY`) dan laporkan sisanya

Tambahan:
- `free-pi/state/manifest.sha256` **tidak** disertakan (machine-specific, dibuat ulang `maint.sh`).
- Riwayat git pernah memuat data kerja → history dipadatkan jadi satu commit bersih.
- Baca `NOTICE.md` untuk kebijakan isi.

## 9. Yang TIDAK disimpan di repo

`credentials.json`, `auth.json`, `mcp.json`, `models-store.json`, `~/.free-pi/agent/sessions/`,
`~/.free-pi/state/pinned/` (bundle vendor), data hasil scan/evidence target, dan unit systemd
tunnel/proxy yang menyimpan token. `install.sh` meng-patch paket `free-pi-cli` yang terpasang,
jadi bundle vendor tidak perlu ikut.

---

## 11. OpenCode — aturan + provider sama seperti pi

`install-opencode.sh` menyamakan opencode dengan pi dalam satu perintah:

```bash
bash install-opencode.sh            # pasang
bash install-opencode.sh --dry-run  # lihat rencananya saja
```

Yang dipasang:

| Bagian | Hasil |
|---|---|
| aturan operator | `~/.config/opencode/AGENTS.md` → symlink ke `~/AGENTS.md` (aturan v3.1, sha `70b34bf0…`) |
| skills | `~/.config/opencode/skill_h` → `~/.agent-rules/skills` (91 `SKILL.md`) |
| tema | `~/.config/opencode/themes/ungu.json` + `tui.json` → `"theme": "ungu"` (violet `#a97ce0`) |
| provider | `freepi` → `https://api.freepi.ai/v1` (`@ai-sdk/openai-compatible`), 18 model |
| token | disalin dari `~/.free-pi/agent/credentials.json` ke `~/.config/opencode/.freepi-token` (600), config memakai `{file:…}` — token tidak pernah masuk config/repo |
| default model | `freepi/deepseek-v4.1-flash`, small `freepi/glm-5.3-flash` |

Config lama tidak ditimpa: hanya provider `freepi` yang ditambahkan/diperbarui, sisanya
(`wusrouter`, `ds-unfiltered`, `perch`, permission, mcp) tetap, dan tiap perubahan membuat
backup `*.bak-<timestamp>`.

Verifikasi:

```bash
opencode models | grep '^freepi/' | wc -l     # 18
opencode run -m freepi/deepseek-v4.1-flash "Balas: ok"
```

Kalau token pi kedaluwarsa (login ulang), cukup jalankan ulang `install-opencode.sh` —
token di `.freepi-token` ikut diperbarui.

---

## 12. Gate rahasia sebelum push

`scan-secrets.sh` memeriksa 5 hal dan **menggagalkan push** bila ada yang lolos:

| Cek | Contoh yang ditolak |
|---|---|
| file kredensial | `credentials.json`, `.freepi-token`, `auth.json`, `id_rsa*`, `.netrc` |
| private key nyata | header `BEGIN … PRIVATE KEY` + blok base64 ≥ 60 char (pola di dokumentasi tidak dihitung) |
| token nyata | `sk-…`, `ghp_…`, `github_pat_…`, `AKIA…`, `xox…`, JWT `eyJ…` (nilai hanya dicetak 8 karakter) |
| IP publik di `*.md` | apa pun di luar privat + `203.0.113.0/24`, `198.51.100.0/24` |
| sintaks | `bash -n`, `py_compile`, `node --check` untuk semua script |

Sekali pasang sebagai hook lokal:

```bash
git config core.hooksPath hooks      # push.sh melakukan ini otomatis
bash scan-secrets.sh                 # jalankan manual kapan saja
```

`push.sh` menjalankan scan ini **sebelum** commit, jadi repo tidak bisa ter-push dalam keadaan
membawa rahasia — tanpa butuh GitHub Actions (push workflow butuh token scope `workflow`).

---

## 13. pi-ops — ledger bukti (pengganti gaya prompt-heavy Hephaestus)

`pi-ops/piops.py` = satu file Python (stdlib saja) yang mencatat setiap langkah ofensif ke
SQLite dan **menolak status "ok" kalau artefak bukti tidak ada**. Dipasang oleh `install.sh`
sebagai `/usr/local`-style `~/.local/bin/piops` + skill `~/.agent-rules/skills/pi-ops/SKILL.md`.

```bash
piops init <slug> --target <t> --profile web
piops plan <slug>                                  # langkah berikut, deterministik
piops run <slug> --tool nmap --phase recon -- nmap -Pn -sV <t>   # log + sha256 otomatis
piops artifact <slug> --path <file> --kind dump
piops done <slug> --step 1 --status ok             # GATE (exit 3 kalau tanpa bukti)
piops finding <slug> --title "..." --severity high --evidence 3
piops status <slug> | piops report <slug> --out laporan.md
piops scan-tools                                   # indeks 100 tool + capability
piops selftest                                     # 6/6 uji gate
```

### Bedanya dengan Hephaestus (Claude-oriented)

| Aspek | Hephaestus (`D:\hephaestus`) | pi-ops |
|---|---|---|
| Bentuk | 18.158 md + 3.914 py, prompt-driven (`CLAUDE.md` 51 KB, 6 agent md) | 1 file python 520 baris + 1 SKILL.md |
| Bukti | tersebar di `campaigns/*/` sebagai file lepas | SQLite: step ↔ artefak ↔ sha256 ↔ temuan |
| Gate | tidak ada pemeriksaan otomatis | `done --status ok` **ditolak** tanpa artefak/hash valid |
| Temuan | bisa ditulis bebas | wajib menunjuk id artefak yang ada di disk |
| Playbook | instruksi bahasa natural | `PLAYBOOK` terstruktur (web/internal/ctf) + `plan` dihitung dari bukti |
| Registry tool | manual | `scan-tools` (100 tool + capability tag) |
| Uji mandiri | pytest terpisah (argus/cerberus) | `piops selftest` tanpa dependency |
| Portabilitas | Claude + MCP + banyak subagent | jalan di Termux/WSL/Ubuntu, `PIOPS_ROOT` untuk isolasi |

Prinsip: Hephaestus mengandalkan model mengikuti 51 KB instruksi; pi-ops memaksa lewat kode —
kalau bukti tidak ada, perintahnya gagal.

---

## 10. Troubleshooting

| Gejala | Perbaikan |
|---|---|
| `free-pi-cli can't run on Node x` | Node < 22.15 / tanpa zstd → `nvm install 22` atau `pkg install nodejs-lts` |
| aturan berubah sendiri | `bash ~/.agent-rules/rules-guard.sh`, cek `tail ~/.agent-rules/guard.log` |
| patch hilang setelah update | `node ~/.free-pi/bin/bundle-patch.cjs --newest` |
| Termux proses mati saat layar off | `termux-wake-lock`, matikan optimasi baterai untuk Termux |
| `no bundle found` saat patch | `free-pi-cli` belum terpasang → `npm i -g free-pi-cli` |
| skill tidak muncul di agent | cek symlink: `ls -l ~/.free-pi/agent/skills` → harus ke `~/.agent-rules/skills` |
