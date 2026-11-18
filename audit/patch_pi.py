#!/usr/bin/env python3
"""Matikan auto-update + version check + /update di free-pi-cli (patch bundle)."""
import hashlib
import os
import shutil
import sys
import time

DIST = "$HOME/.nvm/versions/node/v22.23.4/lib/node_modules/free-pi-cli/dist"
MAIN = os.path.join(DIST, "main-7sxf1v5b.js")
GRAV = os.path.join(DIST, "index-xkn61g24.js")
BAK = "$HOME/pi-audit/backup"

PATCHES = [
    # 1. version check -> selalu "ok", tidak ada request /client-version
    (
        'async function checkClientVersion(baseUrl, cliVersion, fetchImpl = fetch, jwt) {\n  try {',
        'async function checkClientVersion(baseUrl, cliVersion, fetchImpl = fetch, jwt) {\n'
        '  return { action: "ok" }; // PATCHED: version check dimatikan\n  try {',
    ),
    # 2. self-update global (npm install -g) -> langsung fallback
    (
        'async function maybeSelfUpdate(action, latest, deps) {\n'
        '  const fallback = () => action === "notice" ? "notice" : "blocked";\n  try {',
        'async function maybeSelfUpdate(action, latest, deps) {\n'
        '  const fallback = () => action === "notice" ? "notice" : "blocked";\n'
        '  return fallback(); // PATCHED: self-update dimatikan\n  try {',
    ),
    # 3. relaunch via npx @latest -> tidak pernah jalan
    (
        'async function relaunchViaNpx(latest, deps) {\n  const { env } = deps;',
        'async function relaunchViaNpx(latest, deps) {\n'
        '  return; // PATCHED: relaunch @latest dimatikan\n  const { env } = deps;',
    ),
    # 4. slash command /update -> tolak install
    (
        '  ctx.ui.notify("Updating free-pi-cli\u2026 (npm install -g free-pi-cli@latest)", "info");',
        '  ctx.ui.notify("Auto-update dimatikan oleh operator.", "info");\n  return;',
    ),
    # 5. gravity pixel (tracker iklan) -> hard off
    (
        'function startGravityPixel(jwt, storageDir, env = process.env, load = () => import("./index-xkn61g24.js")) {\n  return;',
        'function startGravityPixel(jwt, storageDir, env = process.env, load = () => import("./index-xkn61g24.js")) {\n  return; // PATCHED: gravity pixel off',
    ),
]


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def main():
    os.makedirs(BAK, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    for f in (MAIN, GRAV):
        dst = os.path.join(BAK, os.path.basename(f) + "." + stamp)
        if not os.path.exists(dst):
            shutil.copy2(f, dst)

    src = open(MAIN, encoding="utf-8").read()
    before = sha(MAIN)
    for old, new in PATCHES:
        n = src.count(old)
        if n != 1:
            print(f"SKIP/FAIL ({n} match): {old.splitlines()[0][:70]}")
            continue
        src = src.replace(old, new, 1)
        print(f"PATCH ok: {old.splitlines()[0][:70]}")
    open(MAIN, "w", encoding="utf-8").write(src)
    after = sha(MAIN)
    print(f"\nsha256 before: {before}")
    print(f"sha256 after : {after}")
    print("sisa freepi_no_auto_update guard:", src.count("FREEPI_NO_AUTO_UPDATE"))
    print("sisa /client-version fetch:", src.count('new URL("/client-version"'))
    print("sisa npm install -g:", src.count("npm install -g"))


if __name__ == "__main__":
    sys.exit(main())
