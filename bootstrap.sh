#!/usr/bin/env bash
# bootstrap.sh — pasang pi-system dari nol di Ubuntu / Debian / WSL.
# Pakai: bash bootstrap.sh            (butuh sudo untuk apt; nvm tidak butuh sudo)
set -euo pipefail
R="$(cd "$(dirname "$0")" && pwd)"
say() { printf '\n\033[1;35m==> %s\033[0m\n' "$*"; }

IS_WSL=0; IS_TERMUX=0
grep -qi microsoft /proc/version 2>/dev/null && IS_WSL=1
[ -n "${PREFIX:-}" ] && case "$PREFIX" in *com.termux*) IS_TERMUX=1;; esac
[ -d /data/data/com.termux/files/usr ] && IS_TERMUX=1
DRY=0; [ "${1:-}" = "--dry-run" ] && DRY=1
run() { if [ "$DRY" = 1 ]; then echo "DRY: $*"; else "$@"; fi; }
echo "mode: termux=$IS_TERMUX wsl=$IS_WSL dry=$DRY"
say "target: $( . /etc/os-release 2>/dev/null && echo "$PRETTY_NAME" )  WSL=$IS_WSL"

# 1. paket dasar
SUDO=""; [ "$(id -u)" -ne 0 ] && [ "$IS_TERMUX" -eq 0 ] && SUDO="sudo"
if [ "$IS_TERMUX" -eq 1 ]; then
  say "paket Termux (pkg)"
  run pkg update -y >/dev/null 2>&1 || true
  run pkg install -y nodejs-lts git python jq curl unzip ripgrep nmap termux-tools termux-api >/dev/null 2>&1 \
    || run pkg install -y nodejs git python jq curl unzip ripgrep nmap termux-tools
  run termux-wake-lock 2>/dev/null || true
else
  say "paket dasar (apt)"
  run $SUDO apt-get update -qq
  run $SUDO apt-get install -y -qq curl git jq python3 python3-pip unzip ca-certificates build-essential \
    ripgrep nmap
fi

# 2. Node >= 22.15 (butuh zstd) lewat nvm
need_node=1
if command -v node >/dev/null 2>&1; then
  v=$(node -p 'process.versions.node')
  major=${v%%.*}; rest=${v#*.}; minor=${rest%%.*}
  if [ "$major" -gt 22 ] || { [ "$major" -eq 22 ] && [ "$minor" -ge 15 ]; }; then
    node -e 'process.exit(typeof require("zlib").createZstdDecompress==="function"?0:1)' && need_node=0
  fi
fi
if [ "$need_node" -eq 1 ] && [ "$IS_TERMUX" -eq 1 ]; then
  say "install Node via pkg (Termux)"
  run pkg install -y nodejs-lts >/dev/null 2>&1 || run pkg install -y nodejs
elif [ "$need_node" -eq 1 ]; then
  say "install Node 22 via nvm"
  export NVM_DIR="$HOME/.nvm"
  [ -s "$NVM_DIR/nvm.sh" ] || run bash -c 'curl -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash'
  . "$NVM_DIR/nvm.sh"
  run nvm install 22
  run nvm alias default 22
else
  say "node $(node -v) sudah memadai"
fi
export PATH="$HOME/.nvm/versions/node/$( . "$HOME/.nvm/nvm.sh" 2>/dev/null; nvm current )/bin:$PATH" 2>/dev/null || true

# 3. free-pi-cli
if ! command -v free-pi-cli >/dev/null 2>&1; then
  say "npm i -g free-pi-cli"
  run npm install -g free-pi-cli
fi

# 4. sistem pi (aturan, launcher, patch, theme, skills, tools)
say "install.sh"
run bash "$R/install.sh"

# 5. penjadwal: systemd kalau ada, kalau tidak pakai cron/loop (WSL sering tanpa systemd)
if [ "$IS_TERMUX" -eq 1 ]; then
  say "Termux: loop guard via ~/.termux/boot + nohup"
  cat > "$HOME/.agent-rules/guard-loop.sh" <<'LOOP'
#!/usr/bin/env bash
# guard-loop.sh — pengganti systemd timer di Termux. Loop 60 detik.
termux-wake-lock 2>/dev/null || true
while true; do
  bash "$HOME/.agent-rules/rules-guard.sh" >/dev/null 2>&1 || true
  [ -x "$HOME/.free-pi/state/maint.sh" ] && bash "$HOME/.free-pi/state/maint.sh" --quiet >/dev/null 2>&1
  sleep 60
done
LOOP
  chmod +x "$HOME/.agent-rules/guard-loop.sh"
  mkdir -p "$HOME/.termux/boot"
  cat > "$HOME/.termux/boot/start-guard.sh" <<'BOOT'
#!/data/data/com.termux/files/usr/bin/sh
termux-wake-lock
setsid "$HOME/.agent-rules/guard-loop.sh" >/dev/null 2>&1 &
BOOT
  chmod +x "$HOME/.termux/boot/start-guard.sh"
  pkill -f guard-loop.sh 2>/dev/null || true
  run bash -c 'setsid "$HOME/.agent-rules/guard-loop.sh" >/dev/null 2>&1 &'
  echo "kalau ingin otomatis saat HP reboot: install app Termux:Boot"
elif systemctl --user show-environment >/dev/null 2>&1; then
  say "systemd user tersedia"
  run systemctl --user daemon-reload
  run systemctl --user enable --now rules-guard.timer pi-maintenance.timer
else
  say "tanpa systemd: pasang loop guard + cron"
  cat > "$HOME/.agent-rules/guard-loop.sh" <<'LOOP'
#!/usr/bin/env bash
# guard-loop.sh — pengganti systemd timer di WSL/tanpa systemd. Jalan tiap 60 detik.
while true; do
  bash "$HOME/.agent-rules/rules-guard.sh" >/dev/null 2>&1 || true
  [ -x "$HOME/.free-pi/state/maint.sh" ] && bash "$HOME/.free-pi/state/maint.sh" --quiet >/dev/null 2>&1
  sleep 60
done
LOOP
  chmod +x "$HOME/.agent-rules/guard-loop.sh"
  pkill -f guard-loop.sh 2>/dev/null || true
  nohup setsid "$HOME/.agent-rules/guard-loop.sh" >/dev/null 2>&1 &
  ( crontab -l 2>/dev/null | grep -v guard-loop.sh; \
    echo "@reboot setsid $HOME/.agent-rules/guard-loop.sh >/dev/null 2>&1" ) | crontab - 2>/dev/null || \
    echo "cron tidak tersedia; jalankan manual: bash ~/.agent-rules/guard-loop.sh &"
fi

say "verifikasi"
sha256sum "$HOME/.agent-rules/operator.AGENTS.md.master" "$HOME/.free-pi/agent/AGENTS.md" 2>/dev/null || true
node "$HOME/.free-pi/bin/bundle-patch.cjs" --newest || true
echo
say "selesai. Jalankan: free-pi-cli  (pertama: sign in GitHub)"
[ "$IS_WSL" -eq 1 ] && echo "WSL: untuk browser gunakan wslview/xdg-open; GPU tidak diperlukan."
[ "$IS_TERMUX" -eq 1 ] && cat <<'T'
Termux catatan:
  - 'pkg install termux-api' + izin Termux:API untuk notifikasi; 'termux-wake-lock' agar tidak dibunuh.
  - Tanpa Termux:Boot, jalankan manual setelah buka sesi: bash ~/.agent-rules/guard-loop.sh &
  - Bundle vendor tetap di $PREFIX/lib/node_modules/free-pi-cli; patcher mengenali prefix Termux.
T
