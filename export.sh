#!/usr/bin/env bash
# export.sh — segarkan repo ini dari sistem pi yang sedang jalan di mesin ini.
# Pakai: bash export.sh   (dari root repo). Idempoten: aman dijalankan berulang.
set -euo pipefail
R="$(cd "$(dirname "$0")" && pwd)"
H="$HOME"
AR="$H/.agent-rules"; FP="$H/.free-pi"; AG="$FP/agent"

say() { printf '\033[1;35m==> %s\033[0m\n' "$*"; }

# ---------- 1. aturan operator ----------
say "aturan"
mkdir -p "$R/rules"
cp -f "$AR/operator.AGENTS.md.master" "$R/rules/AGENTS.md"
cp -f "$AR/rules-guard.sh" "$R/rules/"
cp -f "$AR/README.md" "$R/rules/README.agent-rules.md" 2>/dev/null || true

# ---------- 2. launcher + patcher + state ----------
say "launcher/patcher"
mkdir -p "$R/free-pi/bin" "$R/free-pi/state"
for f in free-pi bundle-patch.cjs check-bundle.cjs find-pkg.cjs; do
  cp -f "$FP/bin/$f" "$R/free-pi/bin/" 2>/dev/null || true
done
cp -f "$FP/state/maint.sh" "$FP/state/manifest.sha256" "$R/free-pi/state/" 2>/dev/null || true

# ---------- 3. config agent (tanpa kredensial) ----------
say "agent config"
mkdir -p "$R/agent/themes" "$R/agent/extensions"
for f in settings.json default-model.json models.json operator-gate.md; do
  cp -f "$AG/$f" "$R/agent/" 2>/dev/null || true
done
cp -f "$AG/themes/"*.json "$R/agent/themes/" 2>/dev/null || true
cp -f "$AG/extensions/"*.js "$R/agent/extensions/" 2>/dev/null || true

# ---------- 4. systemd (hanya unit pi, bukan tunnel/proxy bertoken) ----------
say "systemd"
mkdir -p "$R/systemd"
for u in rules-guard.service rules-guard.timer pi-maintenance.service pi-maintenance.timer \
         operator-guard.service operator-guard.timer freepi-shim.service; do
  cp -f "$H/.config/systemd/user/$u" "$R/systemd/" 2>/dev/null || true
done

# ---------- 5. skills (semua, minus artefak Windows/junk) ----------
say "skills"
rm -rf "$R/skills"; mkdir -p "$R/skills"
( cd "$AR/skills" && find -L . -type f \
    ! -name "*Zone.Identifier" ! -name "*.pyc" ! -name "*.so" ! -size +5M -print0 ) \
| while IFS= read -r -d '' f; do
    out="$R/skills/${f#./}"
    mkdir -p "$(dirname "$out")"
    cp -f "$AR/skills/$f" "$out" 2>/dev/null || true
  done

# ---------- 6. hacktools (kode saja, bukan data hasil scan) ----------
say "hacktools"
rm -rf "$R/hacktools"; mkdir -p "$R/hacktools"
( cd "$H/hacktools" && find . -type f \
    \( -name "*.py" -o -name "*.sh" -o -name "*.js" -o -name "*.cjs" -o -name "*.mjs" \
       -o -name "*.go" -o -name "*.c" -o -name "*.h" -o -name "*.md" \) \
    ! -path "./loot*" ! -path "./out*" ! -path "./evidence*" ! -path "./runs/*" \
    ! -path "./ct/*" ! -path "./siak_src/*" ! -path "./ytdata/*" ! -path "./produk/*" \
    ! -path "./proof/*" ! -name "*.bin" ! -size +2M -print0 ) \
| while IFS= read -r -d '' f; do
    out="$R/hacktools/${f#./}"
    mkdir -p "$(dirname "$out")"
    cp -f "$H/hacktools/$f" "$out" 2>/dev/null || true
  done

# ---------- 7. audit ----------
say "audit"
mkdir -p "$R/audit"
cp -f "$H/pi-audit/LAPORAN.md" "$H/pi-audit/patch_pi.py" "$R/audit/" 2>/dev/null || true
cp -f "$H/pi-audit/AGENTS.v3.1.DRAFT.md" "$R/audit/" 2>/dev/null || true
cp -r "$H/pi-audit/source" "$R/audit/" 2>/dev/null || true

# ---------- 8. pembersihan rahasia + sanity ----------
say "pemindaian rahasia"
bad=$(grep -rIlE "-----BEGIN (RSA|EC|OPENSSH|PGP) PRIVATE KEY-----|ghp_[A-Za-z0-9]{30,}|sk-[A-Za-z0-9]{32,}" "$R" 2>/dev/null \
      | grep -v "EXAMPLE" || true)
if [ -n "$bad" ]; then
  echo "PERINGATAN: file berikut memuat pola kunci nyata, periksa manual:"; echo "$bad"
else
  echo "tidak ada pola kunci nyata"
fi
for s in credentials.json auth.json mcp.json models-store.json; do
  [ -e "$R/agent/$s" ] && { rm -f "$R/agent/$s"; echo "dihapus: agent/$s"; }
done

say "ringkasan: $(find "$R" -path "$R/.git" -prune -o -type f -print | wc -l) file, $(du -sh --exclude=.git "$R" | cut -f1)"
say "commit: git add -A && git commit -m 'sync'"
