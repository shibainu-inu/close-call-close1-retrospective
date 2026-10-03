#!/usr/bin/env python3
"""archive.py — close-1 の公開データを保存するだけ（送信・投稿・変更は一切しない）。

保存先: ~/close1/archive/<UTC時刻>/rooms/<部屋>.jsonl と summary.json
対象:   審判の5部屋 + close1 + 審判の flow に載った登録済みの全部屋
"""
import json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tc

BASE_ROOMS = ["d-close1-price", "d-close1-flow", "d-close1-positions", "d-close1-pnl", "d-close1-state", "close1"]
WAIT = 2.0  # 部屋ごとの間隔（秒）。技術的な制限ではなく、相手に負荷をかけないための余裕

stamp = time.strftime("%Y%m%d-%H%M%SZ", time.gmtime())
OUT = os.path.join(tc.HOME, "archive", stamp)
os.makedirs(os.path.join(OUT, "rooms"))
summary = {"started": stamp, "rooms": {}, "room_item_samples": []}


def save_summary():
    with open(os.path.join(OUT, "summary.json"), "w") as f:
        json.dump(summary, f, ensure_ascii=False, indent=1)


def fetch(room):
    t0 = time.time()
    try:
        st, body = tc.get(f"/r/{room}/export", timeout=120)
    except Exception as e:
        summary["rooms"][room] = {"error": repr(e)[:200]}
        print(room, "取得失敗", repr(e)[:120], flush=True)
        return
    body = body or b""
    with open(os.path.join(OUT, "rooms", room.replace("/", "_") + ".jsonl"), "wb") as f:
        f.write(body)
    ts, n = [], 0
    for line in body.split(b"\n"):
        try:
            m = json.loads(line); n += 1
            if m.get("ts"): ts.append(m["ts"])
        except (ValueError, AttributeError):
            pass
    summary["rooms"][room] = {"status": st, "bytes": len(body), "lines": n,
                              "first": min(ts) if ts else None, "last": max(ts) if ts else None,
                              "sec": round(time.time() - t0, 1)}
    print(room, summary["rooms"][room], flush=True)
    save_summary()


for r in BASE_ROOMS:
    fetch(r); time.sleep(WAIT)

# 登録された部屋の一覧（flow の投稿の rooms から集める。形式が分からないので見本も残す）
rooms = set()
flow_path = os.path.join(OUT, "rooms", "d-close1-flow.jsonl")
if os.path.exists(flow_path):
    for line in open(flow_path, "rb"):
        try:
            t = json.loads(json.loads(line)["text"])
        except (ValueError, KeyError, TypeError):
            continue
        for x in t.get("rooms") or []:
            if len(summary["room_item_samples"]) < 5: summary["room_item_samples"].append(x)
            if isinstance(x, str): name = x
            elif isinstance(x, dict): name = x.get("room") or x.get("name")
            elif isinstance(x, list) and x and isinstance(x[0], str): name = x[0]
            else: name = None
            if name: rooms.add(name)
rooms -= set(BASE_ROOMS)
summary["registered_rooms_found"] = len(rooms)
print(f"登録済みの部屋 {len(rooms)} 室を取得します（約 {len(rooms) * (WAIT + 1) / 60:.0f}分〜）", flush=True)
save_summary()

for i, r in enumerate(sorted(rooms), 1):
    print(f"[{i}/{len(rooms)}]", end=" ")
    fetch(r); time.sleep(WAIT)

summary["finished"] = time.strftime("%Y%m%d-%H%M%SZ", time.gmtime())
save_summary()
ok = sum(1 for v in summary["rooms"].values() if v.get("status") == 200)
print(f"完了: {OUT}  成功 {ok}/{len(summary['rooms'])} 室")
