import sys, requests
from concurrent.futures import ThreadPoolExecutor
UA="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/203.0.113.10 Safari/537.36"
def chk(t):
    for s in ("https://","http://"):
        try:
            r=requests.get(f"{s}{t}/.git/HEAD",timeout=6,headers={"User-Agent":UA},allow_redirects=False)
            if r.status_code==200 and r.text.strip().startswith("ref:"):
                return (t, r.text.strip()[:40])
        except Exception: pass
    return None
hosts=[l.strip() for l in open(sys.argv[1]) if l.strip()]
with ThreadPoolExecutor(max_workers=56) as ex:
    res=[x for x in ex.map(chk,hosts) if x]
print(f"diperiksa: {len(hosts)} | .git terekspos: {len(res)}")
for t,h in res[:25]: print(f"  {t}  [{h}]")
OUTPATH = sys.argv[2] if len(sys.argv) > 2 else "$HOME/hacktools/git_exposed.txt"
open(OUTPATH,"w").write("\n".join(t for t,_ in res))
