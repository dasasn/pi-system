#!/usr/bin/env python3
"""
piops — ledger kampanye + gate bukti untuk pi (bukan Claude).

Filosofi: status "ok" hanya boleh keluar kalau ada artefak nyata di disk dengan sha256.
Semua langkah, tool, log, dan temuan dicatat di SQLite, jadi keputusan diambil dari bukti
(bukan dari ingatan model). Tanpa dependency luar: stdlib saja.

Perintah:
  piops init <slug> --target <t> [--scope "<text>"] [--profile web|internal|ctf]
  piops plan <slug>                       # langkah berikut dari playbook + status bukti
  piops run <slug> --tool <nama> -- <argv...>   # jalankan, log, catat artefak + hash
  piops artifact <slug> --path <f> [--kind proof|dump|screenshot|log]
  piops done <slug> --step <id> --status ok|empty|fail [--note "..."]
  piops finding <slug> --title "..." --severity high [--cvss 8.1] [--evidence id,id]
  piops status <slug> [--json]
  piops report <slug> [--out file.md]
  piops scan-tools [--out file.json]
  piops selftest
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(os.environ.get("PIOPS_ROOT", Path.home() / ".piops"))
DB = ROOT / "piops.db"
CAMPAIGNS = ROOT / "campaigns"

SCHEMA = """
CREATE TABLE IF NOT EXISTS campaign(
  id INTEGER PRIMARY KEY, slug TEXT UNIQUE, target TEXT, scope TEXT,
  profile TEXT DEFAULT 'web', created TEXT, phase TEXT DEFAULT 'recon');
CREATE TABLE IF NOT EXISTS step(
  id INTEGER PRIMARY KEY, campaign_id INTEGER, seq INTEGER, tool TEXT, argv TEXT,
  phase TEXT, status TEXT DEFAULT 'pending', exit_code INTEGER, log TEXT,
  artifact TEXT, note TEXT, started TEXT, ended TEXT);
CREATE TABLE IF NOT EXISTS artifact(
  id INTEGER PRIMARY KEY, campaign_id INTEGER, step_id INTEGER, path TEXT,
  sha256 TEXT, bytes INTEGER, kind TEXT DEFAULT 'proof', created TEXT);
CREATE TABLE IF NOT EXISTS finding(
  id INTEGER PRIMARY KEY, campaign_id INTEGER, title TEXT, severity TEXT, cvss REAL,
  target TEXT, status TEXT DEFAULT 'needs-verification', evidence TEXT, created TEXT);
"""

PLAYBOOK = {
    "web": [
        ("recon", "fingerprint", "Identifikasi web server, framework, versi, header"),
        ("recon", "dns-subdomain", "Enumerasi subdomain + resolve origin di balik CDN"),
        ("recon", "port-scan", "Port terbuka + service banner"),
        ("exposure", "path-sweep", "Sweep path rawan: .env, .git, backup, phpinfo, adminer"),
        ("exposure", "git-dump", "Rekonstruksi .git bila ada"),
        ("exploit", "sqli", "Uji SQLi diferensial (bukan pola error saja)"),
        ("exploit", "upload", "Bypass upload -> webshell"),
        ("exploit", "rce", "Eksekusi perintah / shell interaktif"),
        ("post", "enum-host", "Enum user, sudo, cron, SUID, config rahasia"),
        ("post", "creds", "Kumpulkan kredensial: .env, wp-config, ssh key, db dump"),
        ("report", "writeup", "Susun laporan dengan hash bukti"),
    ],
    "internal": [
        ("recon", "host-discovery", "Temukan host hidup"),
        ("recon", "port-scan", "Port + service per host"),
        ("exploit", "service-exploit", "Cocokkan versi service ke CVE/vektor"),
        ("post", "creds", "Dump kredensial lokal"),
        ("post", "lateral", "Pivot ke host berikut"),
        ("report", "writeup", "Laporan + hash bukti"),
    ],
    "ctf": [
        ("recon", "fingerprint", "Kenali target"),
        ("exploit", "vuln-hunt", "Cari primitive exploit"),
        ("exploit", "get-shell", "Dapat eksekusi"),
        ("post", "get-flag", "Ambil flag/bukti"),
        ("report", "writeup", "Writeup"),
    ],
}


# ---------------------------------------------------------------- util
def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def conn() -> sqlite3.Connection:
    ROOT.mkdir(parents=True, exist_ok=True)
    CAMPAIGNS.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA)
    return c


def fail(msg: str, code: int = 2) -> "NoReturn":
    print(f"piops: {msg}", file=sys.stderr)
    sys.exit(code)


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def campaign(c: sqlite3.Connection, slug: str) -> sqlite3.Row:
    row = c.execute("SELECT * FROM campaign WHERE slug=?", (slug,)).fetchone()
    if not row:
        fail(f"kampanye '{slug}' tidak ada (piops init dulu)")
    return row


def cdir(slug: str) -> Path:
    return CAMPAIGNS / slug


# ---------------------------------------------------------------- init
def cmd_init(a) -> int:
    c = conn()
    slug = a.slug
    if c.execute("SELECT 1 FROM campaign WHERE slug=?", (slug,)).fetchone():
        fail(f"kampanye '{slug}' sudah ada")
    d = cdir(slug)
    for sub in ("logs", "artifacts", "notes"):
        (d / sub).mkdir(parents=True, exist_ok=True)
    c.execute(
        "INSERT INTO campaign(slug,target,scope,profile,created) VALUES(?,?,?,?,?)",
        (slug, a.target, a.scope or "", a.profile, now()),
    )
    c.commit()
    (d / "notes" / "log.md").write_text(
        f"# {slug}\n\ntarget: {a.target}\nprofile: {a.profile}\nmulai: {now()}\n", encoding="utf-8"
    )
    print(f"kampanye dibuat: {d}")
    print(f"target={a.target} profile={a.profile} scope={a.scope or '-'}")
    return 0


# ---------------------------------------------------------------- plan
def cmd_plan(a) -> int:
    c = conn()
    camp = campaign(c, a.slug)
    play = PLAYBOOK.get(camp["profile"], PLAYBOOK["web"])
    done = {r["phase"] for r in c.execute(
        "SELECT DISTINCT phase FROM step WHERE campaign_id=? AND status='ok'", (camp["id"],))}
    started = {(r["phase"], r["tool"]) for r in c.execute(
        "SELECT phase,tool FROM step WHERE campaign_id=?", (camp["id"],))}
    print(f"# {camp['slug']}  target={camp['target']}  profile={camp['profile']}")
    print(f"# fase selesai (ada bukti): {', '.join(sorted(done)) or '-'}")
    n = 0
    for phase, tool, desc in play:
        if phase in done:
            continue
        state = "ulang" if (phase, tool) in started else "belum"
        n += 1
        print(f"{n:2d}. [{phase:8s}] {tool:16s} {state:6s}  {desc}")
    arts = c.execute("SELECT COUNT(*) FROM artifact WHERE campaign_id=?", (camp["id"],)).fetchone()[0]
    print(f"\nartefak tercatat: {arts}")
    if n == 0:
        print("semua fase punya bukti -> lanjut 'piops report'")
    return 0


# ---------------------------------------------------------------- run
def cmd_run(a) -> int:
    c = conn()
    camp = campaign(c, a.slug)
    argv = a.argv or []
    if not argv:
        fail("tidak ada perintah: piops run <slug> --tool x -- /path/tool -flag")
    d = cdir(a.slug)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", a.tool)[:40]
    logp = d / "logs" / f"{stamp}-{safe}.log"
    seq = (c.execute("SELECT COALESCE(MAX(seq),0)+1 FROM step WHERE campaign_id=?",
                     (camp["id"],)).fetchone()[0])
    cur = c.execute(
        "INSERT INTO step(campaign_id,seq,tool,argv,phase,status,log,started)"
        " VALUES(?,?,?,?,?,'running',?,?)",
        (camp["id"], seq, a.tool, " ".join(argv), a.phase, str(logp), now()),
    )
    step_id = cur.lastrowid
    c.commit()
    print(f"[step {step_id}] {a.tool}: {' '.join(argv)}")
    t0 = time.time()
    with logp.open("wb") as fh:
        fh.write(f"# piops step {step_id}  {now()}\n# cwd={os.getcwd()}\n# argv={' '.join(argv)}\n".encode())
        try:
            p = subprocess.run(argv, stdout=fh, stderr=subprocess.STDOUT,
                               stdin=subprocess.DEVNULL, timeout=a.timeout)
            rc = p.returncode
        except subprocess.TimeoutExpired:
            fh.write(f"\n# TIMEOUT setelah {a.timeout}s\n".encode())
            rc = 124
        except FileNotFoundError:
            fh.write(f"\n# PERINTAH TIDAK ADA: {argv[0]}\n".encode())
            rc = 127
    dur = round(time.time() - t0, 1)
    art = register_artifact(c, camp["id"], step_id, logp, "log")
    c.execute("UPDATE step SET status=?, exit_code=?, ended=?, artifact=? WHERE id=?",
              ("ok" if rc == 0 else "fail", rc, now(), art, step_id))
    c.commit()
    print(f"  exit={rc} durasi={dur}s log={logp} sha256={(art and 'tercatat') or '-'}")
    if rc != 0:
        print(f"  GAGAL (exit {rc}) — baca {logp}")
    return 0 if rc == 0 else 1


def register_artifact(c, camp_id: int, step_id, path: Path, kind: str) -> str:
    path = path.resolve()
    h = sha256_file(path)
    cur = c.execute(
        "INSERT INTO artifact(campaign_id,step_id,path,sha256,bytes,kind,created)"
        " VALUES(?,?,?,?,?,?,?)",
        (camp_id, step_id, str(path), h, path.stat().st_size, kind, now()),
    )
    c.commit()
    return f"{cur.lastrowid}:{h[:16]}"


# ---------------------------------------------------------------- artifact
def cmd_artifact(a) -> int:
    c = conn()
    camp = campaign(c, a.slug)
    p = Path(a.path).expanduser()
    if not p.exists():
        fail(f"file tidak ada: {p}")
    ref = register_artifact(c, camp["id"], None, p, a.kind)
    print(f"artefak #{ref.split(':')[0]} {a.kind} {p} sha256={ref.split(':')[1]}…")
    return 0


# ---------------------------------------------------------------- done (GATE)
def cmd_done(a) -> int:
    c = conn()
    camp = campaign(c, a.slug)
    st = c.execute("SELECT * FROM step WHERE id=? AND campaign_id=?",
                   (a.step, camp["id"])).fetchone()
    if not st:
        fail(f"step {a.step} tidak ada di kampanye {a.slug}")
    if a.status == "ok":
        arts = c.execute("SELECT * FROM artifact WHERE step_id=?", (a.step,)).fetchall()
        if not arts:
            fail(f"GATE: step {a.step} tidak punya artefak — status 'ok' ditolak. "
                 f"Jalankan ulang dengan 'piops run' atau daftarkan bukti: piops artifact", 3)
        for art in arts:
            if not Path(art["path"]).exists():
                fail(f"GATE: artefak hilang dari disk: {art['path']}", 3)
            if sha256_file(Path(art["path"])) != art["sha256"]:
                fail(f"GATE: hash artefak berubah (bukti dimodifikasi): {art['path']}", 3)
        print(f"GATE lolos: step {a.step} punya {len(arts)} artefak terverifikasi")
    c.execute("UPDATE step SET status=?, note=COALESCE(?,note), ended=? WHERE id=?",
              (a.status, a.note, now(), a.step))
    c.commit()
    print(f"step {a.step} -> {a.status}")
    return 0


# ---------------------------------------------------------------- finding
def cmd_finding(a) -> int:
    c = conn()
    camp = campaign(c, a.slug)
    ev_ids = [int(x) for x in (a.evidence or "").replace(",", " ").split() if x.strip()]
    if not ev_ids:
        fail("GATE: temuan butuh --evidence <id artefak> (buktikan dulu, baru catat)")
    for eid in ev_ids:
        art = c.execute("SELECT * FROM artifact WHERE id=? AND campaign_id=?",
                        (eid, camp["id"])).fetchone()
        if not art:
            fail(f"GATE: artefak #{eid} tidak ada di kampanye ini")
        if not Path(art["path"]).exists():
            fail(f"GATE: artefak #{eid} hilang dari disk")
    c.execute(
        "INSERT INTO finding(campaign_id,title,severity,cvss,target,evidence,created)"
        " VALUES(?,?,?,?,?,?,?)",
        (camp["id"], a.title, a.severity, a.cvss, a.target or camp["target"],
         ",".join(map(str, ev_ids)), now()),
    )
    c.commit()
    print(f"temuan dicatat: {a.title} [{a.severity}] bukti={ev_ids}")
    return 0


# ---------------------------------------------------------------- status / report
def cmd_status(a) -> int:
    c = conn()
    camp = campaign(c, a.slug)
    steps = c.execute("SELECT * FROM step WHERE campaign_id=? ORDER BY seq", (camp["id"],)).fetchall()
    arts = c.execute("SELECT * FROM artifact WHERE campaign_id=? ORDER BY id", (camp["id"],)).fetchall()
    finds = c.execute("SELECT * FROM finding WHERE campaign_id=?", (camp["id"],)).fetchall()
    if a.json:
        print(json.dumps({
            "campaign": dict(camp),
            "steps": [dict(s) for s in steps],
            "artifacts": [dict(x) for x in arts],
            "findings": [dict(f) for f in finds],
        }, indent=2))
        return 0
    print(f"# {camp['slug']} target={camp['target']} profile={camp['profile']} phase={camp['phase']}")
    print("\nLANGKAH")
    for s in steps:
        print(f"  {s['id']:3d} [{s['status']:7s}] {s['tool'][:18]:18s} exit={s['exit_code']} {s['started'] or ''}")
    print("\nARTEFAK")
    for x in arts:
        ok = "ADA" if Path(x["path"]).exists() else "HILANG"
        print(f"  {x['id']:3d} {x['kind']:10s} {ok:6s} {x['bytes']:>9d}B {x['sha256'][:16]}… {x['path']}")
    print("\nTEMUAN")
    for f in finds:
        print(f"  {f['id']:3d} [{f['severity']:8s}] cvss={f['cvss']} {f['title'][:60]}")
    if not finds:
        print("  -")
    return 0


def cmd_report(a) -> int:
    c = conn()
    camp = campaign(c, a.slug)
    steps = c.execute("SELECT * FROM step WHERE campaign_id=? ORDER BY seq", (camp["id"],)).fetchall()
    arts = c.execute("SELECT * FROM artifact WHERE campaign_id=?", (camp["id"],)).fetchall()
    finds = c.execute("SELECT * FROM finding WHERE campaign_id=?", (camp["id"],)).fetchall()
    L = [f"# Laporan: {camp['slug']}", "",
         f"- target: `{camp['target']}`", f"- profile: {camp['profile']}",
         f"- scope: {camp['scope'] or '-'}", f"- mulai: {camp['created']}", "",
         "## Ringkasan langkah", "", "| # | fase | tool | status | exit | log |", "|---|---|---|---|---|---|"]
    for s in steps:
        L.append(f"| {s['id']} | {s['phase']} | `{s['tool']}` | {s['status']} | {s['exit_code']} | `{s['log']}` |")
    L += ["", "## Temuan", ""]
    if not finds:
        L.append("_belum ada temuan tercatat._")
    for f in finds:
        L += [f"### {f['title']}", f"- severity: **{f['severity']}** | cvss: {f['cvss']}",
              f"- target: `{f['target']}` | status: {f['status']}",
              f"- bukti artefak: {f['evidence']}", ""]
    L += ["", "## Bukti (sha256)", "", "| id | jenis | byte | sha256 | path |", "|---|---|---|---|---|"]
    for x in arts:
        exist = "" if Path(x["path"]).exists() else " **(HILANG)**"
        L.append(f"| {x['id']} | {x['kind']} | {x['bytes']} | `{x['sha256']}` | `{x['path']}`{exist} |")
    out = "\n".join(L) + "\n"
    if a.out:
        Path(a.out).write_text(out, encoding="utf-8")
        print(f"laporan: {a.out} ({len(out)} byte)")
    else:
        print(out)
    return 0


# ---------------------------------------------------------------- registry
CAPS = {
    "autohack": ["web", "chain"], "autopilot": ["ops", "ledger"], "acidhunt": ["recon", "web"],
    "webleak": ["secret", "crypto"], "keyharvest": ["secret", "post"], "clouddork": ["osint"],
    "nmap": ["recon", "port"], "masscan": ["recon", "port"], "httpx": ["recon", "web"],
    "nuclei": ["scan", "cve"], "ffuf": ["fuzz"], "gobuster": ["fuzz"], "sqlmap": ["exploit", "sqli"],
    "nikto": ["scan"], "hydra": ["creds"], "subfinder": ["recon", "subdomain"],
}


def cmd_scan_tools(a) -> int:
    idx = {"generated": now(), "tools": {}}
    for base in (Path.home() / "hacktools", Path.home() / ".agent-rules" / "skills"):
        if not base.exists():
            continue
        for p in base.rglob("*"):
            if p.is_dir() or p.suffix not in (".py", ".sh", ".cjs", ".js"):
                continue
            if "/node_modules/" in str(p) or "__pycache__" in str(p):
                continue
            name = p.stem
            idx["tools"].setdefault(name, {"paths": [], "caps": CAPS.get(name, [])})
            idx["tools"][name]["paths"].append(str(p))
    total = len(idx["tools"])
    if a.out:
        Path(a.out).write_text(json.dumps(idx, indent=2), encoding="utf-8")
        print(f"registry: {a.out} ({total} tool)")
    else:
        for name in sorted(idx["tools"]):
            caps = ",".join(idx["tools"][name]["caps"]) or "-"
            print(f"{name:22s} {caps:16s} {idx['tools'][name]['paths'][0]}")
        print(f"\ntotal: {total}")
    return 0


# ---------------------------------------------------------------- selftest
def cmd_selftest(a) -> int:
    """Uji gate tanpa menyentuh kampanye nyata (pakai root sementara)."""
    if a.root:
        os.environ["PIOPS_ROOT"] = a.root
    global ROOT, DB, CAMPAIGNS
    ROOT = Path(os.environ["PIOPS_ROOT"])
    DB = ROOT / "piops.db"
    CAMPAIGNS = ROOT / "campaigns"
    shutil.rmtree(ROOT, ignore_errors=True)
    ok = 0
    total = 0

    def check(name, cond):
        nonlocal ok, total
        total += 1
        if cond:
            ok += 1
            print(f"  ok   {name}")
        else:
            print(f"  GAGAL {name}")

    c = conn()
    c.execute("INSERT INTO campaign(slug,target,profile,created) VALUES('t','x','web',?)", (now(),))
    c.commit()
    camp = c.execute("SELECT * FROM campaign WHERE slug='t'").fetchone()
    cur = c.execute("INSERT INTO step(campaign_id,seq,tool,argv,phase,status) VALUES(?,?,?,?,?,'pending')",
                    (camp["id"], 1, "echo", "echo hi", "recon"))
    sid = cur.lastrowid
    c.commit()
    check("step dibuat", sid > 0)
    # gate: ok tanpa artefak harus ditolak
    rc = subprocess.run([sys.executable, __file__, "done", "t", "--step", str(sid), "--status", "ok"],
                        capture_output=True, text=True, env={**os.environ, "PIOPS_ROOT": str(ROOT)})
    check("gate menolak ok tanpa artefak", rc.returncode == 3)
    # artefak nyata
    f = cdir("t") / "artifacts" / "proof.txt"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("bukti nyata\n", encoding="utf-8")
    ref = register_artifact(c, camp["id"], sid, f, "proof")
    check("artefak + sha tercatat", ":" in ref)
    rc = subprocess.run([sys.executable, __file__, "done", "t", "--step", str(sid), "--status", "ok"],
                        capture_output=True, text=True, env={**os.environ, "PIOPS_ROOT": str(ROOT)})
    check("gate menerima ok dengan artefak", rc.returncode == 0)
    # gate: hash berubah -> tolak
    f.write_text("diubah\n", encoding="utf-8")
    rc = subprocess.run([sys.executable, __file__, "done", "t", "--step", str(sid), "--status", "ok"],
                        capture_output=True, text=True, env={**os.environ, "PIOPS_ROOT": str(ROOT)})
    check("gate menolak artefak berubah", rc.returncode == 3)
    # finding tanpa bukti ditolak
    rc = subprocess.run([sys.executable, __file__, "finding", "t", "--title", "x", "--severity", "low"],
                        capture_output=True, text=True, env={**os.environ, "PIOPS_ROOT": str(ROOT)})
    check("finding tanpa bukti ditolak", rc.returncode == 2)
    print(f"\nselftest: {ok}/{total} lulus")
    return 0 if ok == total else 1


# ---------------------------------------------------------------- main
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="piops", description="ledger kampanye + gate bukti untuk pi")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("init", help="buat kampanye")
    s.add_argument("slug")
    s.add_argument("--target", required=True)
    s.add_argument("--scope", default="")
    s.add_argument("--profile", default="web", choices=list(PLAYBOOK))
    s.set_defaults(func=cmd_init)

    s = sub.add_parser("plan", help="langkah berikutnya")
    s.add_argument("slug")
    s.set_defaults(func=cmd_plan)

    s = sub.add_parser("run", help="jalankan tool + catat bukti")
    s.add_argument("slug")
    s.add_argument("--tool", required=True)
    s.add_argument("--phase", default="recon")
    s.add_argument("--timeout", type=int, default=1800)
    s.set_defaults(func=cmd_run, argv=[])

    s = sub.add_parser("artifact", help="daftarkan file sebagai bukti")
    s.add_argument("slug")
    s.add_argument("--path", required=True)
    s.add_argument("--kind", default="proof")
    s.set_defaults(func=cmd_artifact)

    s = sub.add_parser("done", help="tutup langkah (gate bukti)")
    s.add_argument("slug")
    s.add_argument("--step", type=int, required=True)
    s.add_argument("--status", default="ok", choices=["ok", "empty", "fail"])
    s.add_argument("--note", default=None)
    s.set_defaults(func=cmd_done)

    s = sub.add_parser("finding", help="catat temuan (wajib bukti)")
    s.add_argument("slug")
    s.add_argument("--title", required=True)
    s.add_argument("--severity", default="info",
                   choices=["info", "low", "medium", "high", "critical"])
    s.add_argument("--cvss", type=float, default=0.0)
    s.add_argument("--target", default=None)
    s.add_argument("--evidence", default="")
    s.set_defaults(func=cmd_finding)

    s = sub.add_parser("status", help="ringkas kampanye")
    s.add_argument("slug")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_status)

    s = sub.add_parser("report", help="laporan markdown + hash")
    s.add_argument("slug")
    s.add_argument("--out", default=None)
    s.set_defaults(func=cmd_report)

    s = sub.add_parser("scan-tools", help="indeks tool lokal")
    s.add_argument("--out", default=None)
    s.set_defaults(func=cmd_scan_tools)

    s = sub.add_parser("selftest", help="uji gate (root sementara)")
    s.add_argument("--root", default="/tmp/piops-selftest")
    s.set_defaults(func=cmd_selftest)
    return p


def main() -> int:
    # perintah setelah "--" diambil manual: argparse REMAINDER tidak bisa dipakai bersama opsi
    raw = sys.argv[1:]
    extra = []
    if "--" in raw:
        i = raw.index("--")
        raw, extra = raw[:i], raw[i + 1:]
    a = build_parser().parse_args(raw)
    if extra:
        a.argv = extra
    return a.func(a)


if __name__ == "__main__":
    sys.exit(main())
