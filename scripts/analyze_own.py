#!/usr/bin/env python3
"""analyze_own.py — 自分の木の全候補鍵を、tree.py と同じ公式 fold（rebuild）で再計算する。読むだけ。
パスフレーズ不要（DID の一覧は tc.index() から）。tree_closes.json などの状態ファイルは保存しない。
比べる価格は、保存した審判の最後の pnl 投稿の mark（審判の点数と同じ条件）。
"""
import glob, json, os, sys
from decimal import Decimal as D
sys.path.insert(0, os.path.expanduser("~/close1/v2"))
import tc
import tree as T

idx = tc.index(); dids = idx
reg = tc.load_json("bulkreg.json", {"next": 1, "fail": []})
failed = {s for s, *_ in reg["fail"]}
owners = [dids[s] for s in range(0, reg["next"]) if s not in failed]
closes = tc.load_json(T.CLOSES, {})
fold = T.rebuild(owners, closes)          # closes は保存しない

d = sorted(glob.glob(os.path.expanduser("~/close1/archive/*/")))[-1]
last = [json.loads(json.loads(l)["text"]) for l in open(d + "rooms/d-close1-pnl.jsonl", "rb")][-1]
mark = D(str(last["mark"])); n_last = last["n"]
ref_score = {k: float(v) for k, v in last["top"]}
sp = tc.load_json(T.SPLITS, [])
J = len(sp)
pr = tc.load_json(T.PRUNE, {})

rows = []
for i in range(T.NCAND):
    k = dids[T.CAND0 + i]; a = fold.accounts[k]
    bits = format(i, f"0{T.K}b")[:J]          # 区間 j の向き（1=買い、0=売り）
    rows.append((float(a.value_at(mark)) - 10000, bits, float(a.position), k))
rows.sort(key=lambda r: -r[0])

print(f"審判の最後の投稿 n={n_last} の mark={mark} で計算。区間 {J}個、候補鍵 {T.NCAND}本")
print("区間の始まり: " + ", ".join(f"{x['j']+1}={x['n']}" for x in sp))
print("■ 点数の高い候補鍵（道筋は区間1から順に 1=買い 0=売り）")
for v, b, p, k in rows[:8]:
    print(f"  {v:+9.2f} 道筋 {b} 枚数 {p:+.2f} 審判の点数 {ref_score.get(k, '25位の外')}")
# 上位の木の道筋（analyze_a の結果から、区間6〜12 = 9/30 05:00 以降に対応する部分だけ）
for name, target in (("上位1位と同じ道筋（区間6〜12 = 1001111）", "1001111"),
                     ("上位2位と同じ道筋（区間6〜12 = 1001100）", "1001100")):
    m = [r for r in rows if r[1][5:12] == target]
    print(f"■ {name}: {len(m)}本")
    for v, b, p, k in m[:4]:
        print(f"  {v:+9.2f} 道筋 {b} 枚数 {p:+.2f}")
print("■ 刈り込みで残した束（区間: 束の番号 → 道筋）")
for j in sorted(pr, key=int):
    print(f"  区間{int(j)+1}: " + ", ".join(f"{p}={p:0{int(j)}b}" for p in pr[j]))
