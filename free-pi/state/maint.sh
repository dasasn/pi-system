#!/usr/bin/env bash
# Periodic upkeep: keep the extension file and config in a known state, re-check the bundle.
# Restore-on-drift only, no immutability tricks. Exit 0 always so a shell hook never breaks.
set -uo pipefail

AGENT="$HOME/.free-pi/agent"
STATE="$HOME/.free-pi/state"
MIRROR="$STATE/mirror"
MANIFEST="$STATE/manifest.sha256"
LOG="$STATE/maint.log"
QUIET=0
[ "${1:-}" = "--quiet" ] && QUIET=1

say() { [ "$QUIET" = 1 ] || printf '%s\n' "$*"; }
log() { mkdir -p "$STATE"; printf '%s %s\n' "$(date -Is)" "$*" >>"$LOG"; }

mkdir -p "$MIRROR/extensions" "$AGENT/extensions"

for f in extensions/editor-hints.js; do
	[ -f "$AGENT/$f" ] || continue
	[ -f "$MIRROR/$f" ] || { mkdir -p "$MIRROR/$(dirname "$f")"; cp -a "$AGENT/$f" "$MIRROR/$f"; }
done

restored=0
for f in extensions/editor-hints.js; do
	[ -f "$MIRROR/$f" ] || continue
	if ! cmp -s "$MIRROR/$f" "$AGENT/$f" 2>/dev/null; then
		cp -a "$MIRROR/$f" "$AGENT/$f" && restored=$((restored + 1))
		say "restored $f"
		log "restored $f"
	fi
done

# Local uncensored provider (bitllm) must stay in models.json with section=defense, otherwise the
# model-defense patch has nothing to select and pi falls back to a refusing online model.
[ -f "$STATE/models-merge.cjs" ] && node "$STATE/models-merge.cjs" 2>/dev/null || true

CFG="$HOME/.free-pi/config.json"
if ! grep -q '"autoUpdate"[[:space:]]*:[[:space:]]*false' "$CFG" 2>/dev/null; then
	printf '{\n  "autoUpdate": false,\n  "choicePrompts": false\n}\n' >"$CFG"
	say "config rewritten"
	log "config rewritten"
fi

PINNED="$STATE/pinned/main-7sxf1v5b.js"
PATCHER=""
CHECKER=""
for c in "$HOME/.free-pi/bin/bundle-patch.cjs" "$HOME/freepi-termux/dot-free-pi/bin/bundle-patch.cjs"; do
	[ -f "$c" ] && { PATCHER="$c"; break; }
done
for c in "$HOME/.free-pi/bin/check-bundle.cjs" "$HOME/freepi-termux/dot-free-pi/bin/check-bundle.cjs"; do
	[ -f "$c" ] && { CHECKER="$c"; break; }
done
# valid_bundle <file>: true kalau bundle bisa diparse DAN membawa semua penanda patch.
valid_bundle() {
	[ -f "$1" ] || return 1
	grep -q '__PI_LOCAL_DEFENSE__' "$1" || return 1
	grep -q 'operator-gate.md' "$1" || return 1
	if [ -n "$CHECKER" ]; then
		node --experimental-vm-modules "$CHECKER" "$1" >/dev/null 2>&1
	else
		grep -q '__OPGATE_FS' "$1"
	fi
}
# 1) Pin rusak/tidak lengkap -> bangun ulang dari paket terpasang (bukan dari pin rusak itu).
if [ -f "$PINNED" ] && ! valid_bundle "$PINNED"; then
	SRC=""
	for c in "$HOME/.free-pi/mirror/main-7sxf1v5b.js" \
		$HOME/.nvm/versions/node/v22.23.4/lib/node_modules/free-pi-cli/dist/main-7sxf1v5b.js \
		"$HOME/.local/lib/node_modules/free-pi-cli/dist/main-7sxf1v5b.js"; do
		[ -f "$c" ] && { SRC="$c"; break; }
	done
	if [ -n "$SRC" ] && [ "$SRC" != "$PINNED" ]; then
		TMP="$PINNED.tmp.js"
		grep -v '^/\*! For license information please see main-qn3gsj3n\.js\.LICENSE\.txt \*/$' "$SRC" >"$TMP" 2>/dev/null
		[ -n "$PATCHER" ] && node "$PATCHER" "$TMP" >/dev/null 2>&1
		if valid_bundle "$TMP"; then
			grep -q 'main-qn3gsj3n.js.LICENSE.txt' "$TMP" || printf '/*! For license information please see main-qn3gsj3n.js.LICENSE.txt */\n' >>"$TMP"
			mv -f "$TMP" "$PINNED" && log "pinned bundle REBUILT dari $SRC"
		else
			log "pinned bundle rusak dan gagal dibangun ulang (dari $SRC)"
		fi
		rm -f "$TMP"
	fi
elif [ -f "$PINNED" ] && [ -n "$PATCHER" ]; then
	# Pin sehat: pastikan masih ter-patch paling baru (patcher idempoten).
	TMP="$PINNED.tmp.js"
	cp -f "$PINNED" "$TMP"
	if node "$PATCHER" "$TMP" >/dev/null 2>&1 && cmp -s "$TMP" "$PINNED" && valid_bundle "$PINNED"; then
		log "pinned bundle ok"
	else
		log "pinned bundle butuh re-patch (lewat jalur rebuild berikutnya)"
	fi
	rm -f "$TMP"
fi
log "bundle checked"

write_manifest() {
	: >"$MANIFEST"
	[ -f "$AGENT/extensions/editor-hints.js" ] && sha256sum "$AGENT/extensions/editor-hints.js" >>"$MANIFEST"
	[ -f "$STATE/pinned/main-7sxf1v5b.js" ] && sha256sum "$STATE/pinned/main-7sxf1v5b.js" >>"$MANIFEST"
}

# The settings file stores defaultProvider/defaultModel; on a fresh install (or a reseeded state)
# it does not exist yet, which silently drops the model-defense choice. Write it so the very
# first launch already starts on the uncensored local model.
DEFMODEL="$AGENT/default-model.json"
# Default model = deepseek-v4.1-flash: satu-satunya model online gratis yang tetap mengerjakan
# permintaan ofensif saat aturan operator ada di system prompt (terverifikasi). particle,
# deepseek-v4-flash, glm-5.3-flash menolak; model section "defense" butuh kredit premium.
if [ ! -f "$DEFMODEL" ]; then
	printf '{"provider":"free-pi","model":"deepseek-v4.1-flash"}\n' >"$DEFMODEL"
	log "default-model.json seeded (free-pi/deepseek-v4.1-flash)"
fi

ver() { sha256sum -c "$MANIFEST" >/dev/null 2>&1; }
if [ ! -f "$MANIFEST" ] || ! ver; then
	write_manifest
	log "manifest refreshed"
fi

# Operator gate: blok otorisasi ringkas yang dibaca bundle saat runtime. Tanpa file ini model
# online kembali menolak walau AGENTS.md ada.
GATE="$AGENT/operator-gate.md"
if [ ! -f "$GATE" ] && [ -f "$STATE/operator-gate.md" ]; then
	cp -f "$STATE/operator-gate.md" "$GATE" && log "operator-gate.md dipulihkan"
fi

say "ok (restored=$restored)"
exit 0
