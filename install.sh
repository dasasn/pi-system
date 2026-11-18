#!/usr/bin/env bash
# Pasang pi-system ke lokasi yang benar. Jalankan dari root repo.
set -euo pipefail
R="$(cd "$(dirname "$0")" && pwd)"
H="$HOME"

mkdir -p "$H/.agent-rules/skills" "$H/.free-pi/bin" "$H/.free-pi/state" "$H/.free-pi/agent/themes" \
         "$H/.free-pi/agent/extensions" "$H/.config/systemd/user" "$H/hacktools"

# 1. aturan operator
chmod u+w "$H/.agent-rules/operator.AGENTS.md.master" 2>/dev/null || true
cp -f "$R/rules/AGENTS.md" "$H/.agent-rules/operator.AGENTS.md.master"
chmod 444 "$H/.agent-rules/operator.AGENTS.md.master"
cp -f "$R/rules/rules-guard.sh" "$H/.agent-rules/rules-guard.sh"; chmod +x "$H/.agent-rules/rules-guard.sh"

# 2. launcher + patcher
cp -f "$R/free-pi/bin/"* "$H/.free-pi/bin/"; chmod +x "$H/.free-pi/bin/free-pi"
cp -f "$R/free-pi/state/maint.sh" "$H/.free-pi/state/"; chmod +x "$H/.free-pi/state/maint.sh"
cp -f "$R/free-pi/state/manifest.sha256" "$H/.free-pi/state/" 2>/dev/null || true

# 3. konfigurasi agent (tanpa kredensial)
cp -f "$R/agent/settings.json" "$R/agent/default-model.json" "$R/agent/models.json" \
      "$R/agent/operator-gate.md" "$H/.free-pi/agent/" 2>/dev/null || true
cp -f "$R/agent/themes/"*.json "$H/.free-pi/agent/themes/" 2>/dev/null || true
cp -f "$R/agent/extensions/"*.js "$H/.free-pi/agent/extensions/" 2>/dev/null || true

# 3b. jalur aturan yang dibaca pi/claude/codex (dibuat kalau belum ada)
for d in "$H/.free-pi/agent" "$H/.pi/agent" "$H/.agents"; do
  mkdir -p "$d"
  cp -f "$H/.agent-rules/operator.AGENTS.md.master" "$d/AGENTS.md"
  chmod 444 "$d/AGENTS.md"
done
cp -f "$H/.agent-rules/operator.AGENTS.md.master" "$H/.free-pi/agent/APPEND_SYSTEM.md"
chmod 444 "$H/.free-pi/agent/APPEND_SYSTEM.md"

# 4. skills + toolkit
cp -a "$R/skills/." "$H/.agent-rules/skills/"
cp -a "$R/hacktools/." "$H/hacktools/"

# 4b. pi-ops (ledger kampanye + gate bukti)
mkdir -p "$H/.local/bin"
cp -f "$R/pi-ops/piops.py" "$H/.local/bin/piops" && chmod +x "$H/.local/bin/piops"
mkdir -p "$H/.agent-rules/skills/pi-ops"
cp -f "$R/pi-ops/SKILL.md" "$H/.agent-rules/skills/pi-ops/SKILL.md"
cp -f "$R/pi-ops/piops.py" "$H/.agent-rules/skills/pi-ops/piops.py"

# 5. systemd
cp -f "$R/systemd/"* "$H/.config/systemd/user/" 2>/dev/null || true
systemctl --user daemon-reload 2>/dev/null || true
systemctl --user enable --now rules-guard.timer 2>/dev/null || true
systemctl --user enable --now pi-maintenance.timer 2>/dev/null || true

# 6. patch bundle yang terpasang
node "$H/.free-pi/bin/bundle-patch.cjs" --newest || true

# 6b. buat pin dari bundle yang sudah dipatch (sumber kebenaran wrapper)
PKGDIR=""
for cand in \
  "$(npm root -g 2>/dev/null || true)/free-pi-cli" \
  "$H/.local/lib/node_modules/free-pi-cli" \
  /usr/local/lib/node_modules/free-pi-cli \
  /usr/lib/node_modules/free-pi-cli; do
  if [ -n "$cand" ] && [ -f "$cand/dist/main-7sxf1v5b.js" ]; then PKGDIR="$cand"; break; fi
done
if [ -z "$PKGDIR" ] && [ -d "$H/.nvm/versions/node" ]; then
  cand="$(find "$H/.nvm/versions/node" -maxdepth 6 -type d -name free-pi-cli -path "*/lib/node_modules/*" 2>/dev/null | head -1 || true)"
  [ -n "$cand" ] && [ -f "$cand/dist/main-7sxf1v5b.js" ] && PKGDIR="$cand"
fi
if [ -n "$PKGDIR" ] && [ -f "$PKGDIR/dist/main-7sxf1v5b.js" ]; then
  mkdir -p "$H/.free-pi/state/pinned"
  cp -f "$PKGDIR/dist/main-7sxf1v5b.js" "$H/.free-pi/state/pinned/main-7sxf1v5b.js"
  if ! grep -q 'main-qn3gsj3n.js.LICENSE.txt' "$H/.free-pi/state/pinned/main-7sxf1v5b.js"; then
    printf '/*! For license information please see main-qn3gsj3n.js.LICENSE.txt */\n' >>"$H/.free-pi/state/pinned/main-7sxf1v5b.js"
  fi
  ( cd "$H/.free-pi/state" && sha256sum pinned/main-7sxf1v5b.js >manifest.sha256 ) || true
  echo "pin dibuat: $(sha256sum "$H/.free-pi/state/pinned/main-7sxf1v5b.js" | cut -c1-16) dari $PKGDIR"
else
  echo "peringatan: paket free-pi-cli tidak ditemukan; pin belum dibuat (jalankan free-pi sekali lalu maint.sh)"
fi

bash "$H/.agent-rules/rules-guard.sh" || true

echo "selesai. Verifikasi: sha256sum ~/.agent-rules/operator.AGENTS.md.master ~/.free-pi/agent/AGENTS.md"
