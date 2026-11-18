# Audit: lapisan auto-update diam-diam free-pi-cli

Tanggal: 2026-11-18 · Mesin: instabox (user `zia`)
Status: SELESAI — patch persisten, terverifikasi lintas-launch.

## 1. Rantai eksekusi sebenarnya

`free-pi-cli` di PATH bukan binary npm langsung:

```
~/.local/bin/free-pi-cli      (symlink/shim)
  └─ ~/.free-pi/bin/free-pi   (wrapper bash, 3.5 KB)
       ├─ 1. cari paket terpasang (npm -g / npx cache)
       ├─ 2. BYTE-RESTORE  $STATE/pinned/main-7sxf1v5b.js  →  <pkg>/dist/main-7sxf1v5b.js
       ├─ 3. kalau marker LICENSE.txt hilang → jalankan ~/.free-pi/bin/bundle-patch.cjs
       ├─ 4. jalankan ~/.free-pi/state/maint.sh --quiet
       └─ 5. exec node <pkg>/dist/index.js "$@"
```

Poin penting: file `dist/main-*.js` di node_modules **bukan** sumber kebenaran.
Sumber kebenaran = `~/.free-pi/state/pinned/main-7sxf1v5b.js` (sha tercatat di
`~/.free-pi/state/manifest.sha256`). Setiap launch, wrapper menimpa bundle terpasang
dengan salinan pinned. Inilah sebabnya patch manual di `node_modules` hilang sendiri
(terbukti: sha 6631c8cc… → kembali ke 31ef8f1a… dalam <60 detik, log
`~/.free-pi/state/maint.log`: "pinned bundle ok").

## 2. Mekanisme update yang ada di bundle

| Fungsi | Perilaku | Endpoint / aksi |
|---|---|---|
| `checkClientVersion()` | POST/GET cek versi tiap start, kirim JWT | `GET /client-version` (api.freepi.ai) |
| `maybeSelfUpdate()` | `npm root -g` lalu `npm install -g free-pi-cli@latest` (timeout 60 s) | proses npm lokal |
| `relaunchViaNpx()` | spawn `npx --yes free-pi-cli@<latest>` dengan env FREEPI_AUTO_UPDATED | proses npx lokal |
| `runUpdate()` | handler slash `/update` → `npm install -g free-pi-cli@latest` | npm |
| `readAutoUpdate()` | baca `~/.free-pi/config.json` → `autoUpdate !== false` | file lokal |
| `startGravityPixel()` | tracker iklan Gravity, kirim hash userId | SDK `index-xkn61g24.js` |

Konfigurasi `~/.free-pi/config.json` sudah `{"autoUpdate": false, "choicePrompts": false}`,
tapi itu hanya mematikan jalur `maybeSelfUpdate/relaunchViaNpx` — **cek versi
`/client-version` tetap jalan** dan tetap membawa Bearer JWT. Itu yang ditutup sekarang.

Sisa endpoint keluar di bundle (masih aktif, tidak dimatikan): `/me`, `/me/consent`,
`/me/redeem`, `/session/reset`, `/remote/ws`, `/hive/ws`. Telemetri sudah mati:
`/telemetry/experiment`, `/telemetry/funnel` (fungsi reporter di-return lebih awal).

## 3. Yang dieksekusi

Patch ditambahkan sebagai langkah 8 di `~/.free-pi/bin/bundle-patch.cjs` (idempoten,
anchor-based) sehingga ikut ter-reapply saat pin dibangun ulang:

- `checkClientVersion` → `return { action: "ok" };` (request `/client-version` tidak pernah terjadi)
- `maybeSelfUpdate` → `return;`
- `relaunchViaNpx` → `return;`
- `runUpdate` (`/update`) → notify "Auto-update dimatikan." + `return;`
- `startGravityPixel` → `return;` (sudah ada sebelumnya, dipertahankan)

Diterapkan ke pin lalu disinkronkan ke paket terpasang.

Verifikasi (bukti eksekusi):

```
sha256 pinned  = 89682c620afad558208caba7463d07903be0d1e2bc7505f7f76a52976f61991d
sha256 dist    = 89682c620afad558208caba7463d07903be0d1e2bc7505f7f76a52976f61991d
free-pi-cli --version → free-pi-cli 0.6.21   (exit 0)
setelah launch ulang: sha TETAP 89682c6…, marker __NOUPD:cv / __NOUPD:ru masih ada
maint.log: "pinned bundle ok" / "manifest refreshed"
node --check pada hasil patch: SYNTAX OK
```

Cek fungsi benar-benar mati (substring setelah signature):

```
OK checkClientVersion dead   OK maybeSelfUpdate dead   OK relaunchViaNpx dead
OK runUpdate dead            OK gravity dead           OK resumeExposure dead
```

## 4. File hasil

- `~/pi-audit/LAPORAN.md` — dokumen ini
- `~/pi-audit/patch_pi.py` — patch sekali pakai (dipakai untuk eksperimen awal, sudah di-rollback oleh pin)
- `~/pi-audit/source/{self-update,relaunch,update-check,cli-config,run-update,gravity}.ts` — hasil carve fungsi asli dari bundle
- `~/pi-audit/backup/` — salinan bundle sebelum patch
- `~/.free-pi/bin/bundle-patch.cjs` — langkah 8 "no-update" (permanen, idempoten)
- `~/.free-pi/state/pinned/main-7sxf1v5b.js` — pin ter-patch (sumber kebenaran)

## 5. Undo

```
cp ~/.free-pi/state/pinned/main-7sxf1v5b.js /tmp/x.js   # backup pin sekarang
# hapus blok "// 8. No auto-update" dari ~/.free-pi/bin/bundle-patch.cjs
# lalu bangun ulang pin dari paket npm:
node ~/.free-pi/bin/bundle-patch.cjs $HOME/.nvm/versions/node/v22.23.4/lib/node_modules/free-pi-cli/dist/main-7sxf1v5b.js
cp $HOME/.nvm/versions/node/v22.23.4/lib/node_modules/free-pi-cli/dist/main-7sxf1v5b.js ~/.free-pi/state/pinned/main-7sxf1v5b.js
```

---

## Koreksi patch (2026-11-18): /client-version tetap dipanggil

Versi pertama patch no-update mematikan seluruh `checkClientVersion()` dengan
`return { action: "ok" }` di baris pertama. Itu salah: katalog model picker berasal dari
respons `/client-version` (`versionCheck.models` → `catalogModelsFor(opts)` →
`buildRuntimeOptions`). Dengan early-return, sesi berikutnya hanya punya 1 model fallback
(`MODEL_ID`).

Patch sekarang (`bundle-patch.cjs` langkah 8a):
- early-return `/* __NOUPD:cv */` dicabut (idempoten, `cv-early-return-removed`);
- `/client-version` tetap dipanggil dengan JWT;
- blok `compareVersions(...)` (aksi `block` / `notice`) diganti `return { action: "ok", ...extra }`
  (langkah 3), jadi `min`/`latest` tidak pernah memaksa update atau memunculkan tawaran;
- self-update, `/update`, dan Gravity pixel tetap mati (`__NOUPD:ru`, early-return, telem off).

Bukti: bundle pin = dist = `3451151f0f4d5760…`, `grep -c 'action: "block"'` = 0,
`grep -c __NOUPD:cv` = 0, dan `/client-version` mengembalikan 18 model.
