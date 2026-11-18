#!/usr/bin/env bash
# install-opencode.sh — samakan opencode dengan pi:
#   - aturan operator (AGENTS.md) -> dipakai opencode sebagai instruksi
#   - skills -> ~/.config/opencode/skill_h (symlink ke master)
#   - tema ungu
#   - provider freepi memakai token pi yang sudah ada (~/.free-pi/agent/credentials.json)
# Idempoten: aman dijalankan berulang. Butuh: opencode terpasang, python3.
set -uo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CFG="${XDG_CONFIG_HOME:-$HOME/.config}/opencode"
HOME_DIR="$HOME"
STAMP="$(date +%Y%m%d-%H%M%S)"
DRY=0
[ "${1:-}" = "--dry-run" ] && DRY=1

say() { printf '%s\n' "$*"; }
run() { if [ "$DRY" = 1 ]; then say "  [dry] $*"; else eval "$@"; fi; }

say "== 1. direktori config opencode"
run "mkdir -p '$CFG/themes'"

say "== 2. aturan operator"
RULES="$HOME/.agent-rules/operator.AGENTS.md.master"
if [ ! -f "$RULES" ]; then
  say "  !! master aturan tidak ada ($RULES) — jalankan install.sh pi dulu"
else
  if [ -f "$CFG/AGENTS.md" ] && [ ! -L "$CFG/AGENTS.md" ]; then
    run "cp -a '$CFG/AGENTS.md' '$CFG/AGENTS.md.bak-$STAMP'"
    say "  backup: $CFG/AGENTS.md.bak-$STAMP"
  fi
  run "ln -sfn '$HOME/AGENTS.md' '$CFG/AGENTS.md'"
  say "  AGENTS.md -> $HOME/AGENTS.md ($(sha256sum "$RULES" | cut -c1-16))"
fi

say "== 3. skills"
if [ -d "$HOME/.agent-rules/skills" ]; then
  run "ln -sfn '$HOME/.agent-rules/skills' '$CFG/skill_h'"
  say "  skill_h -> $HOME/.agent-rules/skills ($(find "$HOME/.agent-rules/skills" -name SKILL.md | wc -l) SKILL.md)"
else
  say "  !! ~/.agent-rules/skills tidak ada"
fi

say "== 4. tema ungu"
run "cp -f '$SRC/opencode/themes/ungu.json' '$CFG/themes/ungu.json'"
if [ -f "$CFG/tui.json" ]; then
  run "cp -a '$CFG/tui.json' '$CFG/tui.json.bak-$STAMP'"
fi
run "cp -f '$SRC/opencode/tui.json' '$CFG/tui.json'"
say "  theme=$(python3 -c "import json;print(json.load(open('$SRC/opencode/tui.json'))['theme'])" 2>/dev/null)"

say "== 5. provider freepi (token pi)"
TOKEN_SRC="$HOME/.free-pi/agent/credentials.json"
if [ -f "$TOKEN_SRC" ]; then
  if [ "$DRY" = 0 ]; then
    python3 -c "import json;print(json.load(open('$TOKEN_SRC'))['token'])" > "$CFG/.freepi-token"
    chmod 600 "$CFG/.freepi-token"
  fi
  say "  token disalin ke $CFG/.freepi-token (600, $(wc -c < "$CFG/.freepi-token" 2>/dev/null || echo '?') byte)"
else
  say "  !! credentials pi belum ada — login pi sekali dulu (free-pi-cli --device-login)"
fi

say "== 6. opencode.json"
if [ -f "$CFG/opencode.json" ]; then
  run "cp -a '$CFG/opencode.json' '$CFG/opencode.json.bak-$STAMP'"
  if [ "$DRY" = 0 ]; then
    python3 - "$CFG/opencode.json" "$SRC/opencode/opencode.json" <<'PY'
import json,sys
cur,src=sys.argv[1],sys.argv[2]
c=json.load(open(cur)); s=json.load(open(src))
c.setdefault('provider',{})['freepi']=s['provider']['freepi']     # timpa hanya provider freepi
c.setdefault('model','freepi/deepseek-v4.1-flash')
c.setdefault('small_model','freepi/glm-5.3-flash')
ins=c.get('instructions') or []
if 'AGENTS.md' not in ins: ins.append('AGENTS.md')
c['instructions']=ins
json.dump(c,open(cur,'w'),indent=2,ensure_ascii=False); open(cur,'a').write('\n')
print('  provider:',','.join(c['provider'].keys()))
print('  model default:',c['model'])
PY
  fi
else
  run "cp -f '$SRC/opencode/opencode.json' '$CFG/opencode.json'"
  say "  config baru dari repo"
fi

say "== 7. verifikasi"
if command -v opencode >/dev/null 2>&1 && [ "$DRY" = 0 ]; then
  say "  model freepi terdaftar: $(timeout 90 opencode models 2>/dev/null | grep -c '^freepi/')"
  say "  jalankan: opencode run -m freepi/deepseek-v4.1-flash 'balas: ok'"
else
  say "  (lewati verifikasi: opencode tidak ada / dry-run)"
fi
say "selesai."
