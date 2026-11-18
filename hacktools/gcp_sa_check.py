#!/usr/bin/env python3
"""
gcp_sa_check.py — validasi GCP service-account JSON hasil harvest.
Mint access token (JWT RS256) lalu panggil API nyata untuk bukti akses.

  gcp_sa_check.py sa.json          # satu file
  gcp_sa_check.py -d dump/         # cari semua *service_account* json di folder

Output per akun: project_id, client_email, scope token, hasil list project/bucket.
Nilai rahasia tidak dicetak penuh.
"""
import argparse
import base64
import glob
import json
import os
import sys
import time

import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

SCOPE = "https://www.googleapis.com/auth/cloud-platform"


def b64u(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def mint(sa):
    now = int(time.time())
    header = {"alg": "RS256", "typ": "JWT", "kid": sa.get("private_key_id", "")}
    claims = {"iss": sa["client_email"], "scope": SCOPE, "aud": "https://oauth2.googleapis.com/token",
              "iat": now, "exp": now + 3600}
    sign_in = b64u(json.dumps(header).encode()) + "." + b64u(json.dumps(claims).encode())
    key = serialization.load_pem_private_key(sa["private_key"].encode(), password=None)
    sig = key.sign(sign_in.encode(), padding.PKCS1v15(), hashes.SHA256())
    jwt = sign_in + "." + b64u(sig)
    r = requests.post("https://oauth2.googleapis.com/token", timeout=20,
                      data={"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": jwt})
    if r.status_code != 200:
        return None, f"token HTTP {r.status_code}: {r.text[:160]}"
    return r.json().get("access_token"), "token ok"


def probe(tok):
    h = {"Authorization": f"Bearer {tok}"}
    out = {}
    for name, url in [
        ("projects", "https://cloudresourcemanager.googleapis.com/v1/projects"),
        ("buckets", "https://storage.googleapis.com/storage/v1/b?project=" ),
        ("serviceaccounts", "https://iam.googleapis.com/v1/projects/-/serviceAccounts"),
        ("functions", "https://cloudfunctions.googleapis.com/v1/projects/-/locations/-/functions"),
        ("compute", "https://compute.googleapis.com/compute/v1/projects"),
    ]:
        try:
            r = requests.get(url, headers=h, timeout=20)
            if r.status_code == 200:
                try:
                    d = r.json()
                except Exception:
                    d = {}
                n = len(d.get("projects", d.get("items", d.get("accounts", d.get("buckets", [])) or [])))
                out[name] = f"200 ({n} item)"
            else:
                out[name] = f"{r.status_code}"
        except Exception as e:
            out[name] = "ERR"
    return out


def handle(path):
    try:
        sa = json.load(open(path))
    except Exception as e:
        print(f"  {path}: bukan JSON ({e})")
        return
    if not isinstance(sa, dict) or sa.get("type") != "service_account" or "private_key" not in sa:
        print(f"  {path}: bukan service_account lengkap")
        return
    if "BEGIN PRIVATE KEY" not in sa["private_key"] or len(sa["private_key"]) < 400:
        print(f"  {path}: private_key palsu/mock → skip")
        return
    email = sa.get("client_email", "?")
    tok, msg = mint(sa)
    print(f"  {path}\n    email={email} project={sa.get('project_id')} → {msg}")
    if tok:
        for k, v in probe(tok).items():
            print(f"      {k:<16} {v}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file", nargs="?")
    ap.add_argument("-d", action="append", default=[])
    a = ap.parse_args()
    files = []
    if a.file:
        files.append(a.file)
    for d in a.d:
        files += [p for p in glob.glob(os.path.join(d, "**", "*"), recursive=True)
                  if os.path.isfile(p) and os.path.getsize(p) < 200_000]
    for f in files:
        handle(f)


if __name__ == "__main__":
    main()
