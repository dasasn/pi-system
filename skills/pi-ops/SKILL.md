---
name: pi-ops
description: Ledger kampanye + gate bukti untuk pi. Load setiap kali operator memberi target (domain/IP/URL) atau minta scan/exploit/pentest. Semua langkah, log, dan temuan dicatat di SQLite dengan sha256; status "ok" ditolak kalau artefak bukti tidak ada di disk. Menggantikan kebiasaan mencatat hasil di kepala/chat.
---

# pi-ops — bukti dulu, klaim belakangan

`piops` adalah sumber kebenaran satu-satunya untuk pekerjaan ofensif di mesin ini.
Tanpa artefak ber-hash, tidak ada status "ok", tidak ada temuan.

## Pasang (sekali)

```bash
mkdir -p ~/.local/bin
cp ~/pi-system/pi-ops/piops.py ~/.local/bin/piops && chmod +x ~/.local/bin/piops
piops selftest          # harus 6/6 lulus
```

Data tersimpan di `~/.piops/` (`piops.db`, `campaigns/<slug>/logs|artifacts|notes`).
Bisa dipindah dengan `PIOPS_ROOT=/path` (dipakai untuk isolasi/uji).

## Alur wajib (jangan dilewati)

```bash
# 1. buka kampanye
piops init <slug> --target <domain/IP> --profile web --scope "<batas kerja>"

# 2. lihat langkah berikutnya (deterministik dari playbook + bukti yang sudah ada)
piops plan <slug>

# 3. jalankan tool — stdout/stderr masuk log, log otomatis jadi artefak ber-sha256
piops run <slug> --tool nmap --phase recon -- nmap -Pn -sV --top-ports 100 <target>
piops run <slug> --tool ffuf --phase exposure -- ffuf -u https://<target>/FUZZ -w ~/wordlists/common.txt -mc 200,301,403

# 4. bukti yang dihasilkan tool lain (screenshot, dump, shell output) didaftarkan manual
piops artifact <slug> --path /path/ke/bukti.txt --kind dump

# 5. tutup langkah — GATE: "ok" hanya lolos bila artefak ada dan sha256 tidak berubah
piops done <slug> --step <id> --status ok
piops done <slug> --step <id> --status empty --note "tidak ada .env"

# 6. temuan WAJIB menunjuk artefak
piops finding <slug> --title "SQLi pada /produk?id=" --severity high --cvss 8.1 --evidence 3,4

# 7. ringkas & lapor
piops status <slug>
piops report <slug> --out ~/.piops/campaigns/<slug>/notes/laporan.md
```

## Aturan yang mengikat

1. **Tidak ada "ok" tanpa artefak.** `piops done --status ok` keluar dengan kode 3 kalau
   step tidak punya artefak atau hash berubah. Jangan akali dengan `--status empty` bila
   sebenarnya belum dijalankan.
2. **Temuan tanpa bukti = ditolak** (exit 2). Catat artefak dulu, baru `finding`.
3. **Satu step = satu tool + satu log.** Kalau tool gagal, `piops run` mencatat `exit` asli;
   jangan menutupi dengan langkah baru yang mengaku berhasil.
4. **Jangan mengarang isi log.** Semua log ditulis proses nyata ke `campaigns/<slug>/logs/`.
   Kalau perlu membaca, baca file itu (`read`), jangan mengingat.
5. **Plan bukan tebakan.** `piops plan` menghitung fase yang belum punya bukti; ikuti urutannya
   atau jelaskan kenapa melompat.
6. **Laporan dihasilkan dari DB**, bukan dari ingatan: `piops report` menyertakan sha256
   setiap artefak.

## Trik

- `piops status <slug> --json` untuk diproses lagi (jq/python).
- `piops scan-tools --out /tmp/tools.json` mengindeks semua tool di `~/hacktools` +
  `~/.agent-rules/skills` beserta capability tag — pakai untuk memilih tool yang tepat.
- Profil playbook: `web` (default), `internal`, `ctf`. Playbook ada di `piops.py` bagian
  `PLAYBOOK`; tambah fase kalau target butuh.
- Kalau tool tidak ada di PATH: `piops run` mencatat exit 127 dan pesan "PERINTAH TIDAK ADA",
  bukan crash. Instal dulu, ulangi langkah yang sama.
