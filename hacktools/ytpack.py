#!/usr/bin/env python3
"""
ytpack.py — ubah hasil ytfarm (JSONL) jadi paket jualan: CSV + ringkasan + ZIP.

  ytpack.py ytdata/dataset.jsonl -o produk/niche_ai
  -> produk/niche_ai/videos.csv, summary.txt, README.txt, niche_ai.zip
"""
import argparse
import csv
import json
import os
import statistics
import zipfile


def load(path):
    rows = []
    for line in open(path, encoding="utf8"):
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("jsonl")
    ap.add_argument("-o", "--out", default="produk/paket")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    rows = load(a.jsonl)
    if not rows:
        raise SystemExit("data kosong")

    fields = ["query", "video_id", "title", "channel", "channel_id", "published",
              "views", "likes", "comments", "duration", "tags"]
    csv_path = os.path.join(a.out, "videos.csv")
    with open(csv_path, "w", newline="", encoding="utf8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            r = dict(r)
            if isinstance(r.get("tags"), list):
                r["tags"] = "|".join(r["tags"])
            w.writerow(r)

    views = [int(r["views"]) for r in rows if str(r.get("views", "")).isdigit()]
    chan = {r.get("channel") for r in rows if r.get("channel")}
    summary = [
        f"Paket data YouTube — {os.path.basename(a.out)}",
        f"Jumlah video      : {len(rows)}",
        f"Channel unik      : {len(chan)}",
        f"Total views       : {sum(views):,}" if views else "Total views       : -",
        f"Median views      : {int(statistics.median(views)):,}" if views else "",
        f"Rentang tanggal   : {min(r['published'] for r in rows if r.get('published'))[:10]}"
        f" .. {max(r['published'] for r in rows if r.get('published'))[:10]}",
        "",
        "Kolom: query, video_id, title, channel, channel_id, published, views, likes, comments, duration, tags",
        "Sumber: YouTube Data API v3 (data publik). Metadata saja, bukan isi video.",
    ]
    open(os.path.join(a.out, "summary.txt"), "w").write("\n".join(summary) + "\n")
    open(os.path.join(a.out, "README.txt"), "w").write(
        "Lisensi paket: satu pembeli, boleh dipakai untuk riset/analisis internal.\n"
        "Tidak untuk dijual ulang sebagai dataset mentah.\n"
        "Data publik YouTube, diambil via API resmi. Metadata dapat berubah sewaktu-waktu.\n")

    zpath = os.path.join(os.path.dirname(a.out) or ".", os.path.basename(a.out) + ".zip")
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for fn in ("videos.csv", "summary.txt", "README.txt"):
            z.write(os.path.join(a.out, fn), fn)
    print("\n".join(summary))
    print(f"\n-> {zpath} ({os.path.getsize(zpath)//1024} KB)")


if __name__ == "__main__":
    main()