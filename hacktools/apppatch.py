#!/usr/bin/env python3
"""
apppatch.py — patch aplikasi lokal supaya gate lisensi/trial/limit tidak menghalangi.

Modus:
  scan   : tampilkan lokasi gate yang terdeteksi (tanpa mengubah file)
  patch  : tulis ulang gate jadi netral, simpan backup <file>.bak
  diff   : scan + tampilkan baris sebelum/sesudah

Target: file JS/TS/Python (source), plus hasil `strings` dari binary via -f.

Contoh:
  python3 apppatch.py scan -f app.js
  python3 apppatch.py patch -f app.js
  python3 apppatch.py patch -f app.js -f license.py
"""
import argparse
import json
import os
import re
import shutil
import time

# (nama rule, regex, pengganti, bahasa)
RULES = [
    # ---- JS / TS: gate lisensi ----
    ("js_gate_license",
     re.compile(r"if\s*\(\s*!?\s*(?:this\.)?(?:props\.)?(licenseValid|isLicensed|checkLicense|verifyLicense|hasValidLicense)\s*\([^)]*\)\s*\)"),
     "if (false)", "js"),
    ("js_gate_trial",
     re.compile(r"if\s*\(\s*!?\s*(?:this\.)?(isTrial|trialExpired|isTrialExpired|trialActive)\s*\(?[^)]*\)?\s*\)"),
     "if (false)", "js"),
    ("js_flag_pro_false", re.compile(r"\b(isPro|isPremium|isLicensed|pro|premium)\s*:\s*false\b"), r"\1: true", "js"),
    ("js_plan_free", re.compile(r"""(["']?(?:plan|tier|edition)["']?\s*[:=]\s*["'])free(["'])"""), r"\1pro\2", "js"),
    ("js_limit_const",
     re.compile(r"\b(const|let|var)\s+(MAX_[A-Z_]*(?:FREE|TRIAL|LIMIT)[A-Z_]*|FREE_LIMIT|TRIAL_DAYS|MAX_REQUESTS)\s*=\s*\d+"),
     r"\1 \2 = 999999", "js"),
    ("js_trial_days",
     re.compile(r"\b(trialDaysLeft|freeTrialDays|creditsRemaining|usageRemaining)\s*=\s*0\b"),
     r"\1 = 999999", "js"),
    ("js_expiry_check",
     re.compile(r"if\s*\(\s*(?:Date\.now\(\)|new Date\(\)\.getTime\(\))\s*>\s*[A-Za-z0-9_.]+(?:\(\))?\s*\)"),
     "if (false)", "js"),
    ("js_throw_license",
     re.compile(r"throw\s+new\s+(?:Error|Exception)\(\s*[\"'][^\"']*(?:licen[cs]e|trial|expired|unauthori[sz]ed|forbidden)[^\"']*[\"']\s*\)"),
     'console.warn("[patched] license gate skipped")', "js"),
    # ---- Python ----
    ("py_gate_license",
     re.compile(r"^([ \t]*)if\s+not\s+(?:self\.)?(?:is_licensed|license_valid|check_license|verify_license)\s*\([^)]*\)\s*:", re.M),
     r"\1if False:", "py"),
    ("py_gate_trial",
     re.compile(r"^([ \t]*)if\s+(?:self\.)?(?:trial_expired|is_trial_expired|expired)\s*\(?[^)]*\)?\s*:", re.M),
     r"\1if False:", "py"),
    ("py_raise_license",
     re.compile(r"^([ \t]*)raise\s+(?:LicenseError|TrialExpired|PermissionError)\([^\n]*\)\s*$", re.M),
     r"\1pass  # [patched]", "py"),
    ("py_flag", re.compile(r"^([ \t]*)(is_pro|is_licensed|pro|premium)\s*=\s*False\s*$", re.M), r"\1\2 = True", "py"),
    ("py_limit", re.compile(r"^([ \t]*)(MAX_[A-Z_]*(?:FREE|TRIAL|LIMIT)[A-Z_]*|FREE_LIMIT|TRIAL_DAYS)\s*=\s*\d+\s*$", re.M),
     r"\1\2 = 999999", "py"),
    ("py_expiry", re.compile(r"^\s*if\s+datetime\.now\(\)\s*>\s*[A-Za-z0-9_.]+(?:\(\))?\s*:", re.M), "    if False:", "py"),
]


def detect(path, text):
    hits = []
    for name, rx, repl, lang in RULES:
        for m in rx.finditer(text):
            line = text[: m.start()].count("\n") + 1
            hits.append({"rule": name, "line": line, "lang": lang,
                         "before": m.group(0)[:120],
                         "after": rx.sub(repl, m.group(0))[:120]})
    return hits


def apply_patches(text, lang):
    changes = []
    for name, rx, repl, rlang in RULES:
        if rlang != lang:
            continue

        def sub(m, name=name, rx=rx, repl=repl):
            new = rx.sub(repl, m.group(0))
            if new != m.group(0):
                changes.append({"rule": name, "before": m.group(0)[:120], "after": new[:120]})
            return new

        text = rx.sub(sub, text)
    return text, changes


def lang_of(path, text):
    if path.endswith((".py",)):
        return "py"
    if path.endswith((".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx")):
        return "js"
    # tebak dari isi
    if re.search(r"^\s*(?:def |import |from \w+ import )", text, re.M):
        return "py"
    return "js"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["scan", "patch"])
    ap.add_argument("-f", "--file", action="append", required=True)
    ap.add_argument("-o", "--out", help="tulis hasil patch ke path lain (default: overwrite + .bak)")
    ap.add_argument("--json", help="simpan laporan perubahan ke file JSON")
    a = ap.parse_args()

    report = []
    for path in a.file:
        text = open(path, errors="replace").read()
        lang = lang_of(path, text)
        hits = detect(path, text)
        print(f"\n=== {path} ({lang}) — {len(hits)} gate terdeteksi")
        for h in hits[:40]:
            print(f"  L{h['line']:<5} {h['rule']:<20} {h['before']}")
        if a.mode == "scan":
            report.append({"file": path, "mode": "scan", "hits": hits})
            continue

        new_text, changes = apply_patches(text, lang)
        if not changes:
            print("  (tidak ada yang bisa dipatch otomatis)")
            report.append({"file": path, "mode": "patch", "changes": []})
            continue
        dest = a.out or path
        if not a.out:
            shutil.copy2(path, path + f".bak.{int(time.time())}")
        open(dest, "w").write(new_text)
        print(f"  -> {len(changes)} patch diterapkan ke {dest}"
              + ("" if a.out else f" (backup: {path}.bak.*)"))
        report.append({"file": path, "dest": dest, "mode": "patch", "changes": changes})

    if a.json:
        json.dump(report, open(a.json, "w"), indent=1)
        print(f"\n-> {a.json}")
    total = sum(len(r.get("changes", r.get("hits", []))) for r in report)
    print(f"total gate: {total}")


if __name__ == "__main__":
    main()
