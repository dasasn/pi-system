#!/usr/bin/env python3
"""
ytfarm.py — panen data YouTube pakai banyak API key + rotasi otomatis saat kuota habis.
Output JSONL siap dijual/diolah: channel, video, komentar, statistik.

Pakai:
  ytfarm.py search "ai automation" --max 50 -o data/ai.jsonl
  ytfarm.py channel UCxxxx --max 200 -o data/ch.jsonl      # semua video channel
  ytfarm.py comments VIDEOID --max 100 -o data/cm.jsonl
  ytfarm.py stats                                    # sisa kuota per key (perkiraan lokal)

Key dibaca dari ~/hacktools/keys_vault.jsonl (field "value"), atau --keys file.
Kuota dihitung lokal: search=100 unit, videos=1, commentThreads=1, channels=1 (default YouTube).
Key yang kena 403 quotaExceeded / 429 otomatis dilewati.
"""
import argparse
import json
import os
import sys
import time

import requests

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/203.0.113.10 Safari/537.36"
API = "https://www.googleapis.com/youtube/v3/{}"
COST = {"search": 100, "videos": 1, "channels": 1, "playlistItems": 1, "commentThreads": 1}
DAILY = 10000


class Farm:
    def __init__(self, keys):
        self.keys = [{"key": k, "used": 0, "dead": False} for k in keys]
        self.i = 0

    def alive(self):
        return [k for k in self.keys if not k["dead"] and k["used"] < DAILY]

    def call(self, ep, **params):
        cost = COST.get(ep, 1)
        tries = 0
        while tries < len(self.keys):
            cand = [k for k in self.keys if not k["dead"] and k["used"] + cost <= DAILY]
            if not cand:
                raise RuntimeError("semua key habis/diblokir")
            k = min(cand, key=lambda x: x["used"])
            params["key"] = k["key"]
            r = requests.get(API.format(ep), params=params, headers={"User-Agent": UA}, timeout=20)
            if r.status_code == 200:
                k["used"] += cost
                return r.json()
            body = r.text[:200]
            if r.status_code in (403, 429):
                # quota habis, API diblokir untuk key ini, atau key invalid → buang, rotasi
                k["dead"] = True
                k["why"] = body[:60].replace("\n", " ")
                tries += 1
                print(f"    key {k['key'][:10]}… mati: {k.get('why','')}", flush=True)
                continue
            if r.status_code == 400 and "API key not valid" in body:
                k["dead"] = True
                tries += 1
                continue
            raise RuntimeError(f"{ep} HTTP {r.status_code}: {body}")
        raise RuntimeError("tidak ada key yang bisa dipakai")

    def quota(self):
        return sum(DAILY - k["used"] for k in self.alive())


def save(fh, objs):
    for o in objs:
        fh.write(json.dumps(o, ensure_ascii=False) + "\n")
    fh.flush()


def cmd_search(f, q, maxn, out, order):
    got, token = 0, None
    with open(out, "a") as fh:
        while got < maxn:
            p = {"part": "snippet", "q": q, "maxResults": min(50, maxn - got), "type": "video", "order": order}
            if token:
                p["pageToken"] = token
            d = f.call("search", **p)
            items = d.get("items", [])
            if not items:
                break
            ids = [i["id"]["videoId"] for i in items if i.get("id", {}).get("videoId")]
            det = f.call("videos", part="snippet,statistics,contentDetails", id=",".join(ids)) if ids else {"items": []}
            stats = {v["id"]: v for v in det.get("items", [])}
            rows = []
            for i in items:
                vid = i.get("id", {}).get("videoId")
                if not vid:
                    continue
                s = stats.get(vid, {})
                rows.append({"query": q, "video_id": vid,
                             "title": i["snippet"].get("title"),
                             "channel": i["snippet"].get("channelTitle"),
                             "channel_id": i["snippet"].get("channelId"),
                             "published": i["snippet"].get("publishedAt"),
                             "views": s.get("statistics", {}).get("viewCount"),
                             "likes": s.get("statistics", {}).get("likeCount"),
                             "comments": s.get("statistics", {}).get("commentCount"),
                             "duration": s.get("contentDetails", {}).get("duration"),
                             "tags": s.get("snippet", {}).get("tags", [])})
            save(fh, rows)
            got += len(rows)
            token = d.get("nextPageToken")
            print(f"  {got}/{maxn} video (kuota sisa {f.quota()})", flush=True)
            if not token:
                break
    return got


def cmd_channel(f, cid, maxn, out):
    got, token = 0, None
    with open(out, "a") as fh:
        while got < maxn:
            p = {"part": "snippet,contentDetails", "channelId": cid, "maxResults": min(50, maxn - got)}
            if token:
                p["pageToken"] = token
            d = f.call("playlistItems", **p)
            items = d.get("items", [])
            if not items:
                break
            rows = [{"channel_id": cid, "video_id": i["contentDetails"]["videoId"],
                     "title": i["snippet"].get("title"), "published": i["contentDetails"].get("videoPublishedAt")}
                    for i in items]
            save(fh, rows)
            got += len(rows)
            token = d.get("nextPageToken")
            print(f"  {got}/{maxn} item (kuota sisa {f.quota()})", flush=True)
            if not token:
                break
    return got


def cmd_comments(f, vid, maxn, out):
    got, token = 0, None
    with open(out, "a") as fh:
        while got < maxn:
            p = {"part": "snippet", "videoId": vid, "maxResults": min(100, maxn - got), "textFormat": "plainText"}
            if token:
                p["pageToken"] = token
            d = f.call("commentThreads", **p)
            items = d.get("items", [])
            if not items:
                break
            rows = []
            for it in items:
                s = it["snippet"]["topLevelComment"]["snippet"]
                rows.append({"video_id": vid, "author": s.get("authorDisplayName"),
                             "text": s.get("textDisplay"), "likes": s.get("likeCount"),
                             "published": s.get("publishedAt")})
            save(fh, rows)
            got += len(rows)
            token = d.get("nextPageToken")
            print(f"  {got}/{maxn} komentar", flush=True)
            if not token:
                break
    return got


def load_keys(path):
    ks = []
    for line in open(path):
        line = line.strip()
        if not line:
            continue
        try:
            o = json.loads(line)
            k = o.get("value") or o.get("key")
        except Exception:
            k = line
        if k and k.startswith("AIza") and "youtube" in str(json.loads(line).get("detail", "youtube")):
            ks.append(k)
    return ks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["search", "channel", "comments", "stats"])
    ap.add_argument("arg", nargs="?")
    ap.add_argument("--max", type=int, default=50)
    ap.add_argument("--order", default="viewCount")
    ap.add_argument("--keys", default=os.path.expanduser("~/hacktools/keys_vault.jsonl"))
    ap.add_argument("-o", "--out", default="ytdata.jsonl")
    a = ap.parse_args()
    keys = load_keys(a.keys)
    if not keys:
        sys.exit("tidak ada key YouTube di vault")
    f = Farm(keys)
    if a.cmd == "stats":
        print(f"key hidup: {len(f.alive())} | kuota harian tersisa: {f.quota()} unit")
        return
    n = {"search": cmd_search, "channel": cmd_channel, "comments": cmd_comments}[a.cmd]
    if a.cmd == "search":
        got = n(f, a.arg, a.max, a.out, a.order)
    else:
        got = n(f, a.arg, a.max, a.out)
    print(f"selesai: {got} baris -> {a.out} | kuota sisa {f.quota()}")


if __name__ == "__main__":
    main()
