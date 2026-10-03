#!/usr/bin/env python3
"""analyze_a.py — 方法A（PREREG.md）。審判の pnl・positions・price の記録から、
上位25件に入った鍵の枚数・向き替え・段差を逆算する。読むだけ（ネットワークも使わない）。

使い方: ~/close1/.venv/bin/python analyze_a.py [archive のフォルダ]
出力:   ~/close1/analysis/a/ に keys.csv, segments.csv, events.csv, summary.txt
"""
import csv, glob, json, os, sys
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta

JST = timezone(timedelta(hours=9))
HOME = os.path.expanduser("~/close1")
SRC = sys.argv[1] if len(sys.argv) > 1 else sorted(glob.glob(f"{HOME}/archive/*/"))[-1]
OUT = f"{HOME}/analysis/a"
os.makedirs(OUT, exist_ok=True)

# 合格ライン（PREREG.md 変更1）: |点数の変化 − 枚数×mark の変化| ≤ |枚数|×0.01 + 0.01
# mark は 0.01 単位で公開（前後2回の丸めで 1枚あたり最大 0.01）、点数も 0.01 単位（最大 0.01）
def tol(q): return abs(q) * 0.01 + 0.01 + 1e-6
MIN_DM = 0.20       # mark の変化がこれ未満の組は枚数の推定に使わない（丸めの影響が大きい）
NEED = 5            # 枚数を推定するのに使う組の数（正確な枚数が positions にあればそれを優先）


def load(room):
    rows, senders = {}, Counter()
    for l in open(os.path.join(SRC, "rooms", room + ".jsonl"), "rb"):
        try:
            m = json.loads(l); t = json.loads(m["text"])
        except (ValueError, KeyError, TypeError):
            continue
        if isinstance(t, dict) and "n" in t:
            senders[m.get("from")] += 1
            rows.setdefault(m.get("from"), {})[int(t["n"])] = (m["ts"], t)
    ref, cnt = senders.most_common(1)[0]   # 最も多く投稿した DID を審判とみなす（他の投稿者がいれば summary に出す）
    return rows[ref], {k: v for k, v in senders.items() if k != ref}


pnl, other_pnl = load("d-close1-pnl")
posr, _ = load("d-close1-positions")
price, _ = load("d-close1-price")

ns = sorted(n for n in pnl if pnl[n][1].get("top"))
mark = {n: float(pnl[n][1]["mark"]) for n in ns}
when = {n: datetime.fromisoformat(pnl[n][0].replace("Z", "+00:00")).astimezone(JST).strftime("%m-%d %H:%M") for n in ns}
score = defaultdict(dict)
for n in ns:
    for k, v in pnl[n][1]["top"]:
        score[k][n] = float(v)
exact = defaultdict(dict)
for n, (_, t) in posr.items():
    for k, q in t.get("top") or []:
        exact[k][n] = float(q)
ref = {}
for n, (_, t) in price.items():
    try: ref[n] = float(t["ref"]["px"])
    except (KeyError, TypeError, ValueError): pass


def analyze(k):
    s = score[k]; ex = exact.get(k, {})
    segs, events = [], []
    stat = {"pass": 0, "fail": 0, "unknown": 0, "cmp": 0, "agree": 0}
    cur = {"pairs": [], "pos": None, "start": None}

    def close(end_n):
        if cur["start"] is not None:
            segs.append({"start": cur["start"], "end": end_n, "pos": cur["pos"], "pairs": len(cur["pairs"])})
        cur.update(pairs=[], pos=None, start=None)

    prev = None
    for n in sorted(s):
        if n - 1 not in s or n not in mark or n - 1 not in mark:
            close(prev); prev = n; continue          # 上位25件から外れていた（見えない区間）
        dv, dm = s[n] - s[n - 1], mark[n] - mark[n - 1]
        if cur["start"] is None: cur["start"] = n - 1
        q = ex.get(n - 1, cur["pos"])   # 区間 (n-1, n) の枚数 = 精算 n-1 の後の枚数（正確な値を優先）
        if q is None:
            trial = cur["pairs"] + [(n, dv, dm)]
            big = [x for x in trial if abs(x[2]) >= MIN_DM]
            if len(big) < NEED:
                cur["pairs"].append((n, dv, dm)); prev = n; continue
            q = round(sum(a * b for _, a, b in big) / sum(b * b for _, _, b in big), 2)
            if all(abs(a - q * b) <= tol(q) for _, a, b in trial):
                cur["pos"] = q; cur["pairs"] = trial; stat["pass"] += len(trial); prev = n; continue
            # 枚数が決まる前に段差があった → 場所を特定できない。この組から数え直す
            stat["unknown"] += len(cur["pairs"])
            events.append({"n": n, "kind": "位置不明", "pos_before": None, "resid": None, "dm": dm})
            close(n - 1); cur["start"] = n - 1; cur["pairs"] = [(n, dv, dm)]; prev = n; continue
        r = dv - q * dm
        if abs(r) <= tol(q):
            cur["pairs"].append((n, dv, dm)); cur["pos"] = q; stat["pass"] += 1
            if n in ex:   # 取引のない区間だけで、逆算した枚数と positions の正確な枚数を比べる
                stat["cmp"] += 1; stat["agree"] += abs(ex[n] - q) <= 0.5   # 推定は丸めの影響で ±0.5枚程度の幅がある
        else:
            stat["fail"] += 1
            events.append({"n": n, "kind": "段差", "pos_before": q, "resid": round(r, 2), "dm": round(dm, 4)})
            close(n - 1); cur["start"] = n
        prev = n
    close(prev)
    stat["unknown"] += len(cur["pairs"])
    # 段差の後の枚数を埋める
    for e in events:
        nxt = [g for g in segs if g["start"] >= e["n"] - 1 and g["pos"] is not None]
        e["pos_after"] = nxt[0]["pos"] if nxt else None
    return segs, events, stat


def pct(a, b):
    return None if a is None or b is None or a == 0 else round((b / a - 1) * 100, 2)


final = pnl[ns[-1]][1]["top"]
rank = {k: i + 1 for i, (k, _) in enumerate(final)}
rows_k, rows_s, rows_e = [], [], []
tot = Counter()
for k in score:
    segs, events, st = analyze(k)
    for x in st: tot[x] += st[x]
    flips = sum(1 for e in events if e["pos_before"] and e["pos_after"] and (e["pos_before"] > 0) != (e["pos_after"] > 0))
    jump = round(sum(e["resid"] for e in events if e["resid"] is not None), 2)
    rows_k.append({"key": k, "final_rank": rank.get(k, ""), "final_score": score[k].get(ns[-1], ""),
                   "first_seen": when[min(score[k])], "sweeps_in_top": len(score[k]),
                   "segments": len(segs), "events": len(events), "flips": flips, "jump_sum": jump,
                   "pass": st["pass"], "fail": st["fail"], "unknown": st["unknown"],
                   "exact_cmp": st["cmp"], "exact_agree": st["agree"]})
    for g in segs:
        rows_s.append({"key": k, "start_n": g["start"], "end_n": g["end"], "from": when.get(g["start"], ""),
                       "to": when.get(g["end"], ""), "pos": g["pos"], "pairs": g["pairs"]})
    for e in events:
        n = e["n"]
        rows_e.append({"key": k, "n": n, "jst": when.get(n, ""), "kind": e["kind"], "pos_before": e["pos_before"],
                       "pos_after": e["pos_after"], "resid": e["resid"], "mark": mark.get(n),
                       "ref_move_prev60m_pct": pct(ref.get(n - 12), ref.get(n)),
                       "ref_move_next60m_pct": pct(ref.get(n), ref.get(n + 12))})

rows_k.sort(key=lambda r: (r["final_rank"] == "", r["final_rank"] or 0, -len(str(r["final_score"]))))


def dump(name, rows):
    if not rows: return
    with open(os.path.join(OUT, name), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)


dump("keys.csv", rows_k); dump("segments.csv", rows_s); dump("events.csv", rows_e)

# Q2 の手がかり: 段差の時刻の組み合わせがまったく同じ鍵の束
sig = defaultdict(list)
for r in rows_k:
    ev = tuple(sorted(e["n"] for e in rows_e if e["key"] == r["key"] and e["kind"] == "段差"))
    if ev: sig[ev].append(r["key"])
groups = sorted((len(v), v) for v in sig.values() if len(v) > 1)[::-1]

lines = [f"方法A 逆算の結果（{SRC}）",
         f"精算 {len(ns)}回分（n={ns[0]}〜{ns[-1]}、{when[ns[0]]}〜{when[ns[-1]]} JST）、上位25件に入った鍵 {len(score)}本",
         f"審判以外の投稿者（pnl の部屋）: {dict(other_pnl) if other_pnl else 'なし'}",
         "",
         "■ 検算（PREREG 変更1 の基準: 残差 ≤ |枚数|×0.01 + 0.01点）",
         f"  合格 {tot['pass']}組 / 段差 {tot['fail']}組 / 枚数が決まらず判定できない {tot['unknown']}組",
         f"  positions の正確な枚数との一致: {tot['agree']}/{tot['cmp']}（{tot['agree']/tot['cmp']:.1%}）" if tot["cmp"] else "  positions との照合: 対象なし",
         "",
         "■ 最後の精算での上位3鍵と自分（Q1）"]
own = open(f"{HOME}/state/drooms.json").read() if os.path.exists(f"{HOME}/state/drooms.json") else ""
for r in rows_k:
    if r["final_rank"] in (1, 2, 3) or (r["key"] in own and r["final_rank"]):
        tag = "自分" if r["key"] in own else f"{r['final_rank']}位"
        lines.append(f"  {tag} {r['key'][8:20]} 点数 {r['final_score']} 上位25件に {r['sweeps_in_top']}回（初登場 {r['first_seen']}）"
                     f" 区間 {r['segments']} 段差 {r['events']} 向き替え {r['flips']} 段差の合計 {r['jump_sum']}")
        merged = []
        for g in [x for x in rows_s if x["key"] == r["key"] and x["pos"] is not None]:
            if merged and abs(merged[-1]["pos"] - g["pos"]) <= 0.5: merged[-1]["to"] = g["to"]
            else: merged.append(dict(g))
        for g in merged[:12]:
            lines.append(f"      {g['from']}〜{g['to']} 枚数 {g['pos']}")
        if len(merged) > 12: lines.append(f"      …ほか {len(merged) - 12} 区間（segments.csv）")
        ev = sorted([e for e in rows_e if e["key"] == r["key"] and e["resid"] is not None], key=lambda e: e["resid"])[:10]
        for e in ev:
            lines.append(f"      段差 {e['jst']} {e['resid']:+.2f}点 枚数 {e['pos_before']}→{e['pos_after']}")
lines += ["", "■ 段差の時刻がまったく同じ鍵の束（Q2 の手がかり、大きい順に5つ）"]
for size, ks in groups[:5]:
    lines.append(f"  {size}本: " + ", ".join(k[8:16] for k in ks[:8]) + (" …" if size > 8 else ""))
open(os.path.join(OUT, "summary.txt"), "w").write("\n".join(lines) + "\n")
print("\n".join(lines))
print(f"\n出力: {OUT}/keys.csv, segments.csv, events.csv, summary.txt")
