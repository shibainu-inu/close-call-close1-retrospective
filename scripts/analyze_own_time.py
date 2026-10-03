import glob, json, os, sys
from decimal import Decimal as D
sys.path.insert(0, os.path.expanduser("~/close1/v2"))
import tc, tree as T
idx = tc.index(); dids = idx
reg = tc.load_json("bulkreg.json", {"next": 1, "fail": []}); failed = {s for s, *_ in reg["fail"]}
owners = [dids[s] for s in range(0, reg["next"]) if s not in failed]
closes = tc.load_json(T.CLOSES, {})
d = sorted(glob.glob(os.path.expanduser("~/close1/archive/*/")))[-1]
pnl = {}
for l in open(d + "rooms/d-close1-pnl.jsonl", "rb"):
    try: t = json.loads(json.loads(l)["text"]); pnl[int(t["n"])] = t
    except Exception: pass
lines = open(T.POSTED).read().splitlines()
print("こちらの最初の取引の精算 n =", min(json.loads(x)["n"] for x in lines))
for N in (120, 300, 674, 818, 866, 890, 902, 938, 962, 1190):
    tmp = "/tmp/posted_upto.jsonl"
    sel = [x for x in lines if json.loads(x)["n"] <= N]
    if not sel: print(f"n={N} 取引なし"); continue
    open(tmp, "w").write("\n".join(sel) + "\n")
    T.POSTED = tmp
    fold = T.rebuild(owners, closes)
    mk = D(str(pnl[N]["mark"]))
    best = max(range(T.NCAND), key=lambda i: fold.accounts[dids[T.CAND0 + i]].value_at(mk))
    a = fold.accounts[dids[T.CAND0 + best]]
    print(f"n={N} mark={mk} こちらの最良 {float(a.value_at(mk)) - 10000:+.2f} 道筋 {format(best, '012b')[:4]} 枚数 {float(a.position):+.2f} 首位 {pnl[N]['top'][0][1]}")
