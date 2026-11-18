#!/usr/bin/env bash
# Pasang hacktools ke PATH + skill ke direktori pi.
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
BIN="$HOME/.local/bin"; SK="$HOME/.agent-rules/skills"
mkdir -p "$BIN" "$SK"
python3 -m pip install -q --user -r "$DIR/requirements.txt" 2>/dev/null || \
  python3 -m pip install -q --break-system-packages --user -r "$DIR/requirements.txt"
for t in webleak acidhunt keyharvest apppatch clouddork ytfarm ytpack; do
  printf '#!/usr/bin/env bash\nexec python3 %s/%s.py "$@"\n' "$DIR" "$t" > "$BIN/$t"
  chmod +x "$BIN/$t"
done
chmod +x "$DIR"/*.py
for s in eth-key-hunt ac-id-recon; do
  [ -d "$DIR/../skill-$s" ] && cp -r "$DIR/../skill-$s" "$SK/$s"
done
grep -q '.local/bin' "$HOME/.bashrc" || echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.bashrc"
echo "terpasang: $(ls "$BIN" | grep -E 'webleak|acidhunt|keyharvest|apppatch' | tr '\n' ' ')"
python3 -c "import eth_account, requests; print('deps: eth_account + requests OK')"
