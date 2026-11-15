# -*- coding: utf-8 -*-
"""自动玩家：育种狂热型（breeder）/ 收藏癖型（collector）/ 经营稳健型（manager）。

机器人通过 engine.cmd() 下指令；只在「决定做什么」时读内部状态（测试用）。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import engine as E  # noqa: E402
import genetics as GN  # noqa: E402
from content import GENERA, LINES, NPCS, TALK, ASK, PESTS  # noqa: E402

# 育种计划：(母本品系, 父本品系)。F1 出来以后自交到 F2。
PLANS = [("RUB-WT", "RUB-W"), ("RUB-L", "RUB-Y"), ("MAC-CHI", "MAC-G"), ("MAC-G", "MAC-CHI"),
         ("CUP-LIN", "CUP-1"), ("AER-1", "AER-0"), ("RUB-PM", "RUB-PM")]
SOW_FIRST = {"breeder": ["RUB-WT", "RUB-W", "RUB-L", "RUB-Y", "MAC-G", "AER-0", "RUB-PM", "RUB-SD"],
             "collector": ["RUB-PM", "MAC-VS", "SPI-D", "MAC-CH", "ODO-0", "SPI-1"],
             "manager": ["RUB-WT", "RUB-W"]}


class Bot:
    def __init__(self, style, seed, path, log=None, max_cmds=40000):
        self.style = style
        for p in (path, path + ".bak"):
            if os.path.exists(p):
                os.remove(p)
        E.set_save_path(path)
        E.new_game(seed=seed, force=True)
        self.cmds = 0
        self.max_cmds = max_cmds
        self.errors = []
        self.log = log
        self.done = set()
        self.sown_lots = set()

    @property
    def g(self):
        return E._game()

    @property
    def s(self):
        return E._game().s

    def c(self, text):
        self.cmds += 1
        out = E.cmd(text)
        if "⚠️ 这条指令出错了" in out:
            self.errors.append((self.s["day"], text, out[-400:]))
        if self.log is not None:
            self.log.append(f"> {text}\n{out}")
        return out

    def once(self, key):
        if key in self.done:
            return False
        self.done.add(key)
        return True

    # ── 每天的流程 ──
    def day(self):
        s = self.s
        g = self.g
        if s["pending"]:
            want = {"breeder": 1, "collector": 1, "manager": len(s["pending"]["opts"])}[self.style]
            self.c(f"choose {min(want, len(s['pending']['opts']))}")
            return
        acts = self.plan()
        for a in acts:
            if g.left() < 5 or s["pending"]:
                break
            self.c(a)
        self.c("end")

    def alive(self):
        return [p for p in self.s["plants"].values() if p["alive"] and p["stage"] not in ("gone", "lent")]

    def plan(self):
        s = self.s
        g = self.g
        st = self.style
        day = s["day"]
        A = []
        # 物资
        for it, low, n in (("soil", 6, 20), ("pot_s", 15, 40), ("pot_m", 4, 10), ("nutrient", 4, 10), ("bags", 10, 40),
                           ("soap", 2, 4), ("fungicide", 1, 2), ("marker", 1, 2), ("agar", 1, 2)):
            if s["supplies"][it] < low and s["funds"] > 600:
                A.append(f"buy {it} {n}")
        wish = {"breeder": ["nblamp", "lamp", "radio", "freezer"], "collector": ["radio", "nblamp", "drip"],
                "manager": ["drip"]}[st]
        for u in wish:
            if not g.up(u) and s["funds"] > E.UPGRADES[u][1] + 900:
                A.append(f"upgrade {u}")
                break
        if g.up("nblamp") and not s["zones"]["B"]["nb"] and st != "manager":
            A.append("set B nightbreak on")
        # 照料
        zones = {}
        for p in self.alive():
            if p["stage"] == "seed" or p["zone"] == "K":
                continue
            zones.setdefault(p["zone"], []).append(p)
        for z, ps in zones.items():
            if min(p["water"] for p in ps) < 35 and max(p["water"] for p in ps) < 80:
                A.append(f"water {z}")
            elif any(p["water"] < 30 for p in ps):
                A += [f"water {p['id']}" for p in ps if p["water"] < 30][:6]
            if sum(p["food"] for p in ps) / len(ps) < 35:
                A.append(f"feed {z}")
            for p in ps:
                for k in p["pests"]:
                    m = "fungicide" if k == "mildew" else "soap"
                    A.append(f"treat {p['id']} {m}")
                if p["size"] > E.POT_CAP[p["pot"]] * 0.95 and p["pot"] != "L":
                    A.append(f"repot {p['id']} {'M' if p['pot'] == 'S' else 'L'}")
        # 移苗
        for p in self.alive():
            if p["zone"] == "N" and p["stage"] in ("juvenile", "mature") and p["age"] >= 9:
                gen = GENERA[p["genome"]["genus"].split("×")[0]]
                z = "C" if gen["temp"][1] <= 22 else "B" if gen["temp"][0] >= 17 else "A"
                for zz in (z, "A", "B", "C"):
                    if g.zone_count(zz) < g.zcap(zz) - 1:
                        A.append(f"move {p['id']} {zz}")
                        break
                else:
                    if st != "collector":
                        A.append(f"discard {p['id']}")
        # 采种
        for p in self.alive():
            if p["fruit"] and p["fruit"]["ok"] and day >= p["fruit"]["ready"] and day >= p["fruit"]["set"] + 3:
                A.append(f"harvest {p['id']}")
        # 人
        for nid in NPCS:
            if g.present(nid):
                n = g.npc(nid)
                if any(e["id"] not in n["said"] and g.ok(e["need"]) for e in TALK.get(nid, [])):
                    A.append(f"talk {nid}")
                    break
        if st != "manager" and day % 3 == 0:
            for nid in NPCS:
                if g.present(nid):
                    for e in ASK.get(nid, []):
                        key = f"ask:{nid}:{e['about']}"
                        if g.ok(e["need"]) and key not in self.done:
                            self.done.add(key)
                            A.append(f"ask {nid} {e['about']}")
                            break
        if g.flag("d_key") and s["zones"]["D"]["locked"]:
            A.append("open D")
        if not s["zones"]["D"]["locked"] and s["searched"].get("D", 0) < 4 and st != "manager":
            A.append("search D")
        if g.flag("lin_addr") and not g.flag("letter_sent"):
            A.append("write lin")
        for d in s["docs"]:
            if self.once("read:" + d):
                A.append(f"read {d}")
        # 播种
        first = {l["line"]: l["id"] for l in sorted(s["lots"].values(), key=lambda l: l["id"]) if not l.get("xid")}
        sow = [first[x] for x in SOW_FIRST[st] if x in first and first[x] not in self.sown_lots]
        if day in (1, 2) or (st == "breeder" and day % 7 == 3):
            for sid in sow[:3]:
                self.sown_lots.add(sid)
                A.append(f"sow {sid} {8 if st != 'manager' else 10}")
        for l in s["lots"].values():
            if l.get("xid") and l["seeds"] and l["id"] not in self.sown_lots and st != "manager":
                n = 6 if l["label"] in ("F1", "远缘 F1") else 24
                if g.zone_count("N") + n <= g.zcap("N"):
                    self.sown_lots.add(l["id"])
                    A.append(f"sow {l['id']} {min(n, len(l['seeds']))}")
            if l["line"] in ("CUP-LIN", "WILD-NOC", "WILD-RUB") and l["seeds"] and l["id"] not in self.sown_lots and st != "manager":
                self.sown_lots.add(l["id"])
                A.append(f"sow {l['id']} 8")
        # 杂交
        if st != "manager" or day % 4 == 0:
            A += self.crosses()
        # 观察（开花的优先）
        obs = sorted((p for p in self.alive() if p["stage"] != "seed"),
                     key=lambda p: (p["stage"] != "flowering", max([o[2] for o in p["obs"].values()] or [0])))
        k = {"breeder": 25, "collector": 14, "manager": 6}[st]
        A += [f"observe {p['id']}" for p in obs[:k] if max([o[2] for o in p["obs"].values()] or [0]) < day - 2 or p["stage"] == "flowering"]
        # 寒冷观察：把一株淡紫朱点放冷室
        if st != "manager":
            for p in self.alive():
                if p.get("line") == "RUB-L" and p["zone"] == "A" and p["stage"] in ("juvenile", "mature") and g.zone_count("C") < 14 and self.once("cold:" + p["id"]):
                    A.append(f"move {p['id']} C")
                    break
            for p in self.alive():
                if g.flag("luo_asks") and not g.flag("luo_helped") and p["obs"].get("cold") and "淡紫" in p["obs"].get("flower", ["", ""])[1]:
                    A.append(f"give {p['id']} luo")
                    break
        # 报告
        for x in s["crosses"].values():
            if not x["report"] and x.get("lot"):
                kids = [p for p in s["plants"].values() if p.get("xid") == x["id"]]
                if max([sum(1 for p in kids if t in p["obs"]) for t in ("leaf", "flower", "height")] or [0]) >= 12:
                    A.append(f"report {x['id']}")
                    for t in ("flower", "leaf"):
                        A.insert(0, f"ratio {x['id']} {t}")
        for aid, v in s["catalog"]["anomalies"].items():
            if v >= 2 and not any(r[1] == "anomaly:" + aid for r in s["reports"]):
                A.append(f"report anomaly {aid}")
        # 测试 & 标记
        if st == "breeder" and day % 5 == 0:
            for p in self.alive():
                if "Odorina" in p["genome"]["genus"] and p["obs"].get("scent", [""])[0] == "none" and "O" not in p["tests"]:
                    A.append(f"test {p['id']} O")
                    break
        # 收藏
        if st == "collector":
            for p in self.alive():
                if p["id"] in s["collection"] or len(s["collection"]) >= s["kcap"]:
                    continue
                o = p["obs"]
                odd = (o.get("stem", [""])[0] == "twisted" and o.get("height", [""])[0] in ("h_xs", "h_s")) or \
                      "+streak" in o.get("flower", [""])[0] or "sector" in o.get("leaf", [""])[0] or p["health"] < 40
                if odd and self.once("keep:" + p["id"]):
                    A.append(f"keep {p['id']}")
                    A.append(f"tag {p['id']} 丑但特别")
                    A.append(f"diary {p['id']} 第{day}天收进来。{o.get('leaf', ['', '说不上来'])[1]}")
            for p in s["plants"].values():
                if not p["alive"] and p["death"] and p["death"][0] == day - 1 and p.get("gen", 0) >= 1 and self.once("press:" + p["id"]):
                    A.append(f"press {p['id']}")
                    break
        if st == "manager":
            for p in self.alive():
                if p["zone"] == "N" and p["age"] > 13:
                    A.append(f"discard {p['id']}")
        return A

    def crosses(self):
        s = self.s
        g = self.g
        out = []
        fl = [p for p in self.alive() if p["stage"] == "flowering" and p["flower"] and p["flower"]["open"] and not p["fruit"]]
        used = set()
        for ml, fl_ in PLANS:
            ms = [p for p in fl if p.get("line") == ml and p.get("gen", 0) == 0 and p["id"] not in used]
            fs = [p for p in fl if p.get("line") == fl_ and p.get("gen", 0) == 0 and p["id"] not in used]
            if ml == fl_:
                for m in ms[:1]:
                    if self.once(f"plan:{ml}:{fl_}:{s['day'] // 20}"):
                        out.append(f"self {m['id']}")
                        used.add(m["id"])
                continue
            for m in ms:
                f = next((x for x in fs if x is not m), None)
                if f and self.once(f"plan:{ml}:{fl_}:{s['day'] // 20}"):
                    out.append(f"cross {m['id']} {f['id']}")
                    used.add(m["id"])
                    break
        # F1 和其他后代自交，推进世代
        for p in fl:
            if p["id"] in used:
                continue
            if p.get("gen", 0) >= 1 and p.get("gen", 0) < 4 and self.once(f"self:{p['id']}:{p['blooms']}"):
                out.append(f"self {p['id']}")
            elif self.style == "breeder" and not p["bag"] and self.once(f"bag:{p['id']}:{p['blooms']}") and g.s["supplies"]["bags"] > 20:
                out.append(f"bag {p['id']}")
        return out

    def play(self, days):
        stop = self.s["day"] + days
        while self.s["day"] < stop and self.cmds < self.max_cmds:
            self.day()
        return self.s
