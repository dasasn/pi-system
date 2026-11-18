#!/usr/bin/env bash
# push.sh — bersihkan repo lalu push ke semua remote (origin + fork/mirror).
# Token diambil dari ~/.secrets/gh_oauth (hasil device login), tidak pernah ditulis ke repo.
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")" || exit 1
TOKF="$HOME/.secrets/gh_oauth"
[ -f "$TOKF" ] || { echo "token GitHub tidak ada: $TOKF"; echo "login: opencode/gh device flow atau git credential"; exit 1; }
T="$(head -1 "$TOKF")"
USER_NAME="$(git config user.name || echo operator)"
git config user.name "${GIT_NAME:-$USER_NAME}" >/dev/null

echo "== 1. sanitasi"
bash sanitize-public.sh >/dev/null 2>&1 || true

echo "== 2. commit bila ada perubahan"
if [ -n "$(git status --porcelain)" ]; then
  git add -A
  git -c user.name="${GIT_NAME:-operator}" -c user.email="${GIT_EMAIL:-operator@localhost}" \
      commit -q -m "${1:-sync: $(date +%F\ %H:%M)}"
  echo "   commit: $(git log --oneline -1)"
else
  echo "   tidak ada perubahan"
fi

echo "== 3. push"
for url in $(git remote -v | awk '$3=="(push)"{print $2}'); do
  clean="${url#https://github.com/}"; clean="${clean%.git}"
  echo "   -> $clean"
  for try in 1 2 3; do
    if git push "https://${clean%%/*}:$T@github.com/${clean}.git" main 2>&1 | tail -1; then break; fi
    sleep 3
  done
done
echo "selesai."
