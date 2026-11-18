#!/usr/bin/env bash
# update.sh — dipakai kalau pi sudah terpasang dan ingin naik versi.
# Urutannya penting: paket di-update, lalu PIN dibangun ulang dari bundle baru.
# Kalau pin tidak dibangun ulang, launcher lama akan menimpa bundle baru dengan versi lama.
set -euo pipefail
H="$HOME"; STATE="$H/.free-pi/state"; PIN="$STATE/pinned/main-7sxf1v5b.js"
PATCHER="$H/.free-pi/bin/bundle-patch.cjs"; GUARD="$H/.agent-rules/rules-guard.sh"
say() { printf '\n\033[1;35m==> %s\033[0m\n' "$*"; }
DRY=0; NONPM=0
for a in "$@"; do
  [ "$a" = "--dry-run" ] && DRY=1
  [ "$a" = "--no-npm" ] && NONPM=1
done
run() { if [ "$DRY" = 1 ]; then echo "DRY: $*"; else "$@"; fi; }

IS_TERMUX=0; case "${PREFIX:-}" in *com.termux*) IS_TERMUX=1;; esac
[ -d /data/data/com.termux/files/usr ] && IS_TERMUX=1

ver() { free-pi-cli --version 2>/dev/null || echo "tidak terpasang"; }
say "versi sebelum: $(ver)"

# ---------- 1. update paket ----------
say "update paket free-pi-cli"
if [ "$IS_TERMUX" -eq 1 ]; then run pkg update -y >/dev/null 2>&1 || true; fi
if [ "${NONPM:-0}" = "1" ]; then echo "lewati npm (--no-npm)"; else run npm install -g free-pi-cli@latest; fi
say "versi sesudah: $(ver)"

# ---------- 2. temukan bundle terpasang ----------
find_dist() {
  for c in "$H/.nvm/versions/node/"*/lib/node_modules/free-pi-cli/dist \
           "${PREFIX:-/nonexistent}/lib/node_modules/free-pi-cli/dist" \
           "$H/.npm-global/lib/node_modules/free-pi-cli/dist" \
           /usr/lib/node_modules/free-pi-cli/dist \
           /usr/local/lib/node_modules/free-pi-cli/dist; do
    [ -d "$c" ] && ls "$c"/main-*.js 2>/dev/null | head -1 && return 0
  done
  for c in "$H"/.npm/_npx/*/node_modules/free-pi-cli/dist; do
    [ -d "$c" ] && ls "$c"/main-*.js 2>/dev/null | head -1 && return 0
  done
  return 1
}
SRC="$(find_dist || true)"
[ -n "${SRC:-}" ] || { echo "GAGAL: bundle free-pi-cli tidak ditemukan (npm i -g free-pi-cli@latest dulu)"; exit 1; }
say "bundle sumber: $SRC"
echo "sha256 sumber: $(sha256sum "$SRC" | cut -c1-16)"

# ---------- 3. bangun ulang pin dari bundle baru ----------
say "bangun ulang pin + patch"
TMP="$PIN.tmp.js"
mkdir -p "$STATE/pinned"
run bash -c "grep -v '^/\*! For license information please see main-qn3gsj3n\.js\.LICENSE\.txt \*/$' '$SRC' > '$TMP'"
run node "$PATCHER" "$TMP"
if [ "$DRY" -eq 0 ]; then
  node --check "$TMP" >/dev/null 2>&1 || { echo "GAGAL: hasil patch bukan JS valid"; exit 1; }
  for m in __OPGATE_FS __PI_LOCAL_DEFENSE__ operator-gate.md __NOUPD:cv __NOUPD:ru 'theme: "ungu"'; do
    grep -qF "$m" "$TMP" || { echo "GAGAL: penanda '$m' hilang setelah patch"; exit 1; }
  done
  grep -q 'main-qn3gsj3n.js.LICENSE.txt' "$TMP" || printf '/*! For license information please see main-qn3gsj3n.js.LICENSE.txt */\n' >>"$TMP"
  mv -f "$TMP" "$PIN"
  DST_DIR="$(dirname "$SRC")"
  cp -f "$PIN" "$DST_DIR/main-$(basename "$PIN" | sed 's/^main-//;s/\.js$//').js" 2>/dev/null || true
  cp -f "$PIN" "$DST_DIR/$(basename "$PIN")"
  echo "pin: $(sha256sum "$PIN" | cut -c1-16)  dist: $(sha256sum "$DST_DIR/$(basename "$PIN")" | cut -c1-16)"
fi

# ---------- 4. aturan + penjadwal ----------
say "pulihkan aturan + penjadwal"
run bash "$GUARD"
if systemctl --user show-environment >/dev/null 2>&1; then
  run systemctl --user restart rules-guard.timer 2>/dev/null || true
elif [ -x "$H/.agent-rules/guard-loop.sh" ]; then
  run bash -c 'pkill -f guard-loop.sh 2>/dev/null; setsid "$HOME/.agent-rules/guard-loop.sh" >/dev/null 2>&1 &'
else
  run bash "$STATE/maint.sh" --quiet || true
fi

# ---------- 5. verifikasi ----------
say "verifikasi"
if [ "$DRY" -eq 0 ]; then
  free-pi-cli --version
  sha256sum "$PIN" "$(dirname "$SRC")/$(basename "$PIN")" "$H/.agent-rules/operator.AGENTS.md.master" "$H/.free-pi/agent/AGENTS.md" | cut -c1-16
  grep -o "__NOUPD:[a-z]*" "$PIN" | sort -u | tr '\n' ' '; echo
  grep -o 'theme: "[a-z]*"' "$PIN" | head -1
  tail -3 "$H/.agent-rules/guard.log" 2>/dev/null || true
fi
say "selesai. Jalankan ulang: free-pi-cli   (sesi lama belum memakai versi/aturan baru)"
