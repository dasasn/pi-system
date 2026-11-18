#!/usr/bin/env python3
"""
install_beam.py — pasang Beam.md sebagai instructions opencode.

Default DRY-RUN: hanya menampilkan apa yang akan berubah.
--apply baru menulis, dan selalu membuat backup bertimestamp lebih dulu.

Pemakaian:
  python3 install_beam.py                 # lihat rencana
  python3 install_beam.py --apply         # tulis (backup otomatis)
  python3 install_beam.py --revert <bak>  # kembalikan dari backup
"""
import argparse
import json
import os
import shutil
import time

CFG = os.path.expanduser("~/.config/opencode/opencode.json")
BEAM = os.path.expanduser("~/.free-pi/agent/skills/godmode/Beam.md")


def load():
    with open(CFG) as f:
        return json.load(f)


def plan(d):
    """kembalikan (aksi, detail) tanpa mengubah d"""
    instr = d.get("instructions") or []
    if isinstance(instr, str):
        instr = [instr]
    if BEAM in instr:
        return "skip", "Beam.md sudah terpasang di instructions"
    return "add", f"instructions: {len(instr)} -> {len(instr)+1} entri (+{BEAM})"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert")
    a = ap.parse_args()

    if a.revert:
        if not os.path.exists(a.revert):
            raise SystemExit(f"[!] backup tidak ada: {a.revert}")
        shutil.copy2(a.revert, CFG)
        print(f"[+] dipulihkan dari {a.revert}")
        return

    if not os.path.exists(BEAM):
        raise SystemExit(f"[!] {BEAM} tidak ada")
    if not os.path.exists(CFG):
        raise SystemExit(f"[!] {CFG} tidak ada")

    d = load()
    action, detail = plan(d)
    print(f"[*] config : {CFG}")
    print(f"[*] sumber : {BEAM} ({os.path.getsize(BEAM)} bytes)")
    print(f"[*] rencana: {action} — {detail}")

    if action == "skip":
        print("[=] tidak ada perubahan")
        return

    if not a.apply:
        print("\n[DRY-RUN] tidak ada yang ditulis. Tambahkan --apply untuk menerapkan.")
        return

    bak = f"{CFG}.beam-bak.{int(time.time())}"
    shutil.copy2(CFG, bak)
    print(f"[+] backup: {bak}")

    instr = d.get("instructions") or []
    if isinstance(instr, str):
        instr = [instr]
    instr.append(BEAM)
    d["instructions"] = instr

    tmp = CFG + ".tmp"
    with open(tmp, "w") as f:
        json.dump(d, f, indent=2)
        f.write("\n")
    try:
        load_check = json.load(open(tmp))
        assert BEAM in load_check["instructions"]
    except Exception as e:
        os.unlink(tmp)
        raise SystemExit(f"[!] validasi gagal, config TIDAK diubah: {e}")
    os.replace(tmp, CFG)
    print(f"[+] terpasang. revert: python3 {sys.argv[0]} --revert {bak}")


if __name__ == "__main__":
    import sys
    main()
