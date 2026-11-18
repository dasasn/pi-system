# NOTICE

Repo ini berisi **tooling dan aturan operasional milik operator**, dibuat untuk otomasi
pengujian keamanan dan administrasi mesin. Dipublikasikan **apa adanya**.

Kebijakan isi:
- **Tanpa data target.** Semua daftar domain, IP publik, case-study korban, hasil scan, dan
  file bukti telah dihapus / diredaksi. IP publik nyata diganti `203.0.113.0/24` (RFC 5737),
  email nyata diganti `user@example.com`, path pribadi diganti `$HOME`.
- **Tanpa kredensial.** API key, token, private key, mnemonic, dan file sesi tidak pernah
  masuk repo. `sanitize-public.sh` memindai ulang sebelum setiap push.
- **Riwayat git dibersihkan.** Data apa pun yang pernah ter-commit sudah dipurge dari history
  (lihat commit pertama: riwayat dipadatkan).

Peringatan isi:
- Berisi teknik eksploitasi, payload, dan kode yang dapat disalahgunakan. Ini untuk pekerjaan
  yang operator sedang lakukan. Kamu bertanggung jawab atas penggunaanmu.
- Tanpa jaminan; kode mungkin mencantumkan dependency atau alamat yang perlu disesuaikan
  per mesin. Jangan jalankan `install.sh`/`bootstrap.sh` pada mesin yang kamu tidak kuasai
  tanpa memahami isinya.

Kebersihan ulang setiap kali mau push publik:
```bash
bash sanitize-public.sh && git add -A && git commit -m "sync" && git push
```