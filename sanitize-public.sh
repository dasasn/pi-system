#!/usr/bin/env bash
# sanitize-public.sh — bersihkan repo sebelum dipublikasikan / dipush ke GitHub publik.
# Idempoten. Yang dilakukan:
#   1. buang file DATA hasil kerja (kunci, daftar target, bukti scan, case study nyata)
#   2. redaksi email nyata -> user@example.com
#   3. redaksi IP publik nyata -> 203.0.113.10 (RFC 5737), IP privat dibiarkan
#   4. ganti path /home/<user> -> $HOME / ~
# Tanpa argumen berbahaya: script ini hanya mengubah isi repo ini.
set -uo pipefail
R="$(cd "$(dirname "$0")" && pwd)"
cd "$R" || exit 1
say() { printf '\033[1;35m==> %s\033[0m\n' "$*"; }
LOG="$R/SANITIZE.log"; : > "$LOG"

# ---------- 1. hapus file data / bukti ----------
say "hapus file data & bukti"
DATA=(
  hacktools/vpshunt.json
  hacktools/acid_domains.txt
  hacktools/batch2.txt
  hacktools/git_exposed.txt
  hacktools/ct
  hacktools/siak_src
  hacktools/proof
  hacktools/ytdata
  hacktools/produk
  audit/backup
)
for d in "${DATA[@]}"; do
  if [ -e "$d" ]; then rm -rf "$d"; echo "hapus: $d" >> "$LOG"; fi
done
# case study berisi target nyata (email/IP/domain korban)
find skills -type f \( -iname "*case-study*" -o -iname "*case_study*" \) -print0 2>/dev/null \
| while IFS= read -r -d '' f; do rm -f "$f"; echo "hapus: $f" >> "$LOG"; done
# file yang isinya murni daftar domain/hasil scan
find skills hacktools -type f -name "*.txt" 2>/dev/null | while read -r f; do
  case "$f" in
    *requirements.txt|*README*|*wordlist*|*payload*) continue;;
  esac
  n=$(grep -cvE '^\s*(#|$)' "$f" 2>/dev/null || echo 0)
  if [ "${n:-0}" -gt 0 ] && [ "$(grep -cE '^\s*(https?://|[a-z0-9.-]+\.(id|com|net|org|io)\s*$)' "$f" 2>/dev/null || echo 0)" -ge $(( n / 2 + 1 )) ]; then
    rm -f "$f"; echo "hapus(list): $f" >> "$LOG"
  fi
done

# ---------- 2. redaksi email ----------
say "redaksi email"
git ls-files -z 2>/dev/null | tr '\0' '\n' > /tmp/_files.txt
if [ ! -s /tmp/_files.txt ]; then find . -path ./.git -prune -o -type f -print > /tmp/_files.txt; fi
while IFS= read -r f; do
  [ -f "$f" ] || continue
  case "$f" in *.png|*.jpg|*.svg|*.webp|*.gz|*.zip) continue;; esac
  perl -0pi -e 's/\b([A-Za-z0-9._%+-]+)@(?!example\.(com|org|net)|test\.com|localhost|target\.com|client[0-9]*\.com|.*\.example\b)([A-Za-z0-9-]+\.)+[A-Za-z]{2,}\b/user\@example.com/g' "$f" 2>/dev/null || true
done < /tmp/_files.txt

# ---------- 3. redaksi IP publik ----------
say "redaksi IP publik"
while IFS= read -r f; do
  [ -f "$f" ] || continue
  case "$f" in *.png|*.jpg|*.svg|*.gz|*.zip|./free-pi/state/manifest.sha256) continue;; esac
  perl -0pi -e 's/\b(?!(?:10|127|192\.168|172\.(?:1[6-9]|2\d|3[01])|203\.0\.113|198\.51\.100|0)\.)(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})\b/203.0.113.10/g' "$f" 2>/dev/null || true
done < /tmp/_files.txt

# ---------- 4. path pribadi ----------
say "ganti path /home/<user>"
while IFS= read -r f; do
  [ -f "$f" ] || continue
  case "$f" in *.png|*.jpg|*.svg|*.gz|*.zip) continue;; esac
  sed -i -E 's#$HOME#\$HOME#g' "$f" 2>/dev/null || true
  sed -i -E "s#/home/$(id -un)#\$HOME#g; s#/home/[a-z][a-z0-9_-]*/#~/#g" "$f" 2>/dev/null || true
done < /tmp/_files.txt

# ---------- 5. laporan sisa pola sensitif ----------
say "sisa pola sensitif"
rest=$(git ls-files -z 2>/dev/null | tr '\0' '\n' | while read -r f; do
  [ -f "$f" ] || continue
  grep -IlE "AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{30,}|sk-[A-Za-z0-9]{32,}|-----BEGIN [A-Z ]*PRIVATE KEY-----" "$f" 2>/dev/null
done | grep -v EXAMPLE | sort -u)
if [ -n "$rest" ]; then echo "$rest" | tee -a "$LOG"; else echo "bersih (0 file)" | tee -a "$LOG"; fi
say "log: $LOG"
