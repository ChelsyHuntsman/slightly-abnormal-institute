# -*- coding: utf-8 -*-
"""端到端的育种流程：只用玩家能用的指令，从种子库一路做到 F2 分离比。

    python3 tests/walkthrough.py         # 打印全过程的关键输出
"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import engine as E  # noqa: E402

VERBOSE = False


def c(text):
    out = E.cmd(text)
    if VERBOSE:
        print(f"> {text}\n{out}\n")
    return out


def S():
    return E._game().s


def alive(pred=lambda p: True):
    return [p for p in S()["plants"].values() if p["alive"] and p["stage"] not in ("gone", "lent") and pred(p)]


def care():
    s = S()
    while s["pending"]:
        c(f"choose {len(s['pending']['opts'])}")
    for z in ("A", "B", "C", "N"):
        ps = [p for p in alive(lambda p: p["zone"] == z and p["stage"] != "seed")]
        if ps and min(p["water"] for p in ps) < 45:
            c(f"water {z}")
        if ps and sum(p["food"] for p in ps) / len(ps) < 45:
            c(f"feed {z}")
    for it, n in (("nutrient", 10), ("bags", 30), ("soil", 20), ("pot_s", 40), ("pot_m", 10)):
        if s["supplies"][it] < 5:
            c(f"buy {it} {n}")
    for p in alive(lambda p: p["pests"]):
        c(f"treat {p['id']} {'fungicide' if 'mildew' in p['pests'] else 'soap'}")
    for p in alive(lambda p: p["zone"] == "N" and p["stage"] in ("juvenile", "mature")):
        c(f"move {p['id']} A")
    for p in alive(lambda p: p["size"] > E.POT_CAP[p["pot"]] * 0.9 and p["pot"] == "S"):
        c(f"repot {p['id']} M")


def flowering_with(color_kw, pred=lambda p: True):
    res = []
    for p in alive(lambda p: p["stage"] == "flowering" and p["flower"] and p["flower"]["open"] and not p["fruit"] and pred(p)):
        out = c(f"observe {p['id']}")
        if color_kw in p["obs"].get("flower", ["", ""])[1]:
            res.append(p)
    return res


def run_f2(seed=5, path=None, max_days=140):
    """深红 × 纯白 → F1 → 自交 → F2，返回 (ratio 输出, 观察株数)。按花色挑亲本，不信标签。"""
    path = path or os.path.join(tempfile.mkdtemp(), "wt.json")
    E.set_save_path(path)
    E.new_game(seed=seed, force=True)
    c("talk wen")
    c("sow S001 4; sow S002 4")
    stage = "parents"
    f1_lot = None
    f2_lots = []
    x1 = None
    x2s, x2_day0 = [], 0
    for _ in range(max_days):
        care()
        s = S()
        if stage == "parents":
            reds = flowering_with("深红", lambda p: p.get("line") in ("RUB-WT", "RUB-W"))
            whites = flowering_with("纯白", lambda p: p.get("line") in ("RUB-WT", "RUB-W"))
            if reds and whites:
                c(f"cross {reds[0]['id']} {whites[0]['id']}")
                x1 = max(s["crosses"])
                stage = "wait1"
        elif stage == "wait1":
            x = s["crosses"][x1]
            m = s["plants"][x["mother"]]
            if "失败" in x["status"]:
                stage = "parents"
            elif m["fruit"] and m["fruit"]["ok"] and s["day"] >= m["fruit"]["ready"]:
                c(f"harvest {m['id']}")
                f1_lot = s["crosses"][x1]["lot"]
                c(f"sow {f1_lot} 4")
                stage = "f1"
        elif stage == "f1":
            if not alive(lambda p: p.get("lot") == f1_lot) and s["lots"][f1_lot]["seeds"]:
                c(f"sow {f1_lot} 4")  # 一盘都没出苗：再播一盘
            for p in alive(lambda p: p.get("lot") == f1_lot and p["stage"] == "flowering" and p["flower"]["open"] and not p["fruit"]):
                c(f"self {p['id']}")
                x2s.append(max(s["crosses"]))
            if len(x2s) >= 2 or (x2s and s["day"] > x2_day0 + 12):
                stage = "wait2"
            if x2s and not x2_day0:
                x2_day0 = s["day"]
        elif stage == "wait2":
            pending = 0
            for xid in x2s:
                x = s["crosses"][xid]
                m = s["plants"][x["mother"]]
                if x.get("lot") or "失败" in x["status"]:
                    continue
                if m["fruit"] and m["fruit"]["ok"] and s["day"] >= m["fruit"]["ready"]:
                    c(f"harvest {m['id']}")
                else:
                    pending += 1
            if not pending:
                f2_lots = [s["crosses"][x]["lot"] for x in x2s if s["crosses"][x].get("lot")]
                if not f2_lots:
                    x2s, x2_day0, stage = [], 0, "f1"
                    continue
                for p in alive(lambda p: p["zone"] == "A" and p.get("lot") not in f2_lots and p["id"] not in ("P0001", "P0002", "P0003")):
                    c(f"discard {p['id']}")
                for lot in f2_lots:
                    c(f"sow {lot} {min(len(s['lots'][lot]['seeds']), 40 // len(f2_lots))}")
                stage = "f2"
        elif stage == "f2":
            kids = alive(lambda p: p.get("lot") in f2_lots)
            for p in kids:
                if p["stage"] == "flowering" and "flower" not in p["obs"]:
                    c(f"observe {p['id']}")
            done = [p for p in S()["plants"].values() if p.get("lot") in f2_lots and "flower" in p["obs"]]
            if done and all(p["stage"] not in ("juvenile", "seedling", "seed", "mature") for p in kids):
                ref = "+".join(x for x in x2s if s["crosses"][x].get("lot"))
                return c(f"ratio {ref} 花色"), len(done), ref
        c("end")
    return None, 0, None


if __name__ == "__main__":
    VERBOSE = "-v" in sys.argv
    out, n, x = run_f2()
    print(out)
    print("F2 观察株数：", n, "第", S()["day"], "天")
