#!/usr/bin/env bash
# scan-secrets.sh — gate sebelum push: tolak kredensial, private key, token nyata, IP publik di dokumen.
# Exit 1 = push dibatalkan. Nilai rahasia TIDAK pernah dicetak (hanya potongan 8 karakter).
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")" || exit 1
FAIL=0
PH='XXXX|EXAMPLE|ABCDEFGH|REAL000|your[-_]|<[a-z-]+>|PLACEHOLDER|dummy|contoh|redacted'

say() { printf '%s\n' "$*"; }
bad() { printf '  !! %s\n' "$*"; FAIL=1; }

say "== 1. file kredensial"
n=$(git ls-files | grep -E '(^|/)(credentials\.json|auth\.json|mcp\.json|models-store\.json|\.freepi-token|\.netrc|\.git-credentials|id_rsa.*|id_ed25519.*)$' || true)
[ -n "$n" ] && bad "file kredensial ter-track: $(echo "$n" | tr '\n' ' ')"
[ -z "$n" ] && say "  ok"

say "== 2. private key"
# private key nyata = header + blok base64 >= 60 karakter (pola/regex di dokumentasi tidak dihitung)
n=$(python3 - <<'PY2'
import os,re
pat=re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH |PGP )?PRIVATE KEY-----\s*(?:[A-Za-z0-9+/=]{20,}\s*){2,}')
hits=[]
for root,dirs,files in os.walk('.'):
    dirs[:]=[d for d in dirs if d not in ('.git','node_modules','__pycache__')]
    for f in files:
        fp=os.path.join(root,f)
        try: t=open(fp,encoding='utf-8',errors='ignore').read()
        except Exception: continue
        if pat.search(t): hits.append(fp)
print(' '.join(hits))
PY2
)
[ -n "$n" ] && bad "private key di: $(echo "$n" | tr '\n' ' ')"
[ -z "$n" ] && say "  ok"

say "== 3. token berpola nyata"
n=$(grep -rIhoE 'sk-[A-Za-z0-9_-]{32,}|gh[pousr]_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{40,}|AKIA[0-9A-Z]{16}|xox[baprs]-[A-Za-z0-9-]{10,}|eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.' . \
      --exclude-dir=.git --exclude-dir=hacktools 2>/dev/null | sort -u | grep -vE "$PH" || true)
if [ -n "$n" ]; then bad "token nyata terdeteksi: $(echo "$n" | sed -E 's/^(.{8}).*/\1…/' | tr '\n' ' ')"; else say "  ok"; fi

say "== 4. IP publik di dokumentasi"
n=$(grep -rIhoE '\b([0-9]{1,3}\.){3}[0-9]{1,3}\b' --include='*.md' . --exclude-dir=.git 2>/dev/null \
     | grep -vE '^(0\.|10\.|127\.|192\.168\.|172\.(1[6-9]|2[0-9]|3[01])\.|169\.254\.|203\.0\.113\.|198\.51\.100\.|255\.)' | sort -u || true)
[ -n "$n" ] && bad "IP publik: $(echo "$n" | head -5 | tr '\n' ' ')"
[ -z "$n" ] && say "  ok"

say "== 5. sintaks"
for f in $(git ls-files '*.sh'); do bash -n "$f" 2>/dev/null || bad "bash -n $f"; done
for f in $(git ls-files '*.py'); do python3 -m py_compile "$f" >/dev/null 2>&1 || bad "py_compile $f"; done
for f in $(git ls-files '*.cjs'); do node --check "$f" >/dev/null 2>&1 || bad "node --check $f"; done
[ "$FAIL" = 0 ] && say "  ok"

if [ "$FAIL" = 1 ]; then say "HASIL: GAGAL — perbaiki dulu sebelum push"; exit 1; fi
say "HASIL: BERSIH — aman dipush"
