# -*- coding: utf-8 -*-
"""《不太正常的植物研究所》游戏引擎（人类开发者维护用）。

AI 玩家请用 greenhouse_lab.py：import greenhouse_lab; print(greenhouse_lab.cmd("help"))
本文件与 content.py、genetics.py 由 build.py 打包进 greenhouse_lab.py。
"""
import json
import math
import os
import re
import shutil
import time as _time

if "GENERA" not in globals():  # 打包后内容已经在全局里了
    from content import *  # noqa: F401,F403
import sys as _sys  # noqa: E402
GN = _sys.modules.get("_greenhouse_genetics")
if GN is None:
    import genetics as GN  # noqa: E402

VERSION = 1
MAX_BATCH = 10
SAVE_ENV = "GREENHOUSE_SAVE"
STAGE_CN = {"seed": "种子（已播）", "seedling": "幼苗", "juvenile": "营养生长", "mature": "成株", "flowering": "开花",
            "fruiting": "结果", "dead": "已死亡", "nogerm": "未发芽", "gone": "已离开", "lent": "借出"}
POT_CAP = {"S": 30, "M": 70, "L": 160}
POT_CN = {"S": "小盆", "M": "中盆", "L": "大盆"}


class Rng:
    def __init__(self, state):
        self.state = state & 0xFFFFFFFF

    def random(self):
        self.state = (self.state + 0x6D2B79F5) & 0xFFFFFFFF
        t = self.state
        t = ((t ^ (t >> 15)) * (t | 1)) & 0xFFFFFFFF
        t ^= (t + (((t ^ (t >> 7)) * (t | 61)) & 0xFFFFFFFF)) & 0xFFFFFFFF
        return ((t ^ (t >> 14)) & 0xFFFFFFFF) / 4294967296

    def randint(self, a, b):
        return a + int(self.random() * (b - a + 1))

    def choice(self, seq):
        return seq[int(self.random() * len(seq))]


EVENT_BY_ID = {e["id"]: e for e in EVENTS}
_NUM = re.compile(r"^(day|funds|rep|year)(>=|<=|==)(-?\d+)$")
_TRUST = re.compile(r"^trust:(\w+)(>=|<=|==)(-?\d+)$")
_ANOM = re.compile(r"^anomaly:(\w+)>=(\d)$")


def _cmp(a, op, b):
    return a >= b if op == ">=" else a <= b if op == "<=" else a == b


def hm(minutes):
    return f"{8 + minutes // 60:02d}:{minutes % 60:02d}"


def _save_path():
    p = os.environ.get(SAVE_ENV)
    if p:
        return p
    base = os.path.dirname(os.path.abspath(globals().get("__file__", "greenhouse_lab.py")))
    return os.path.join(base, "greenhouse_save.json")


def year_day(day):
    return (day - 1) % YEAR_LEN + 1


def season_of(day):
    return SEASONS[(year_day(day) - 1) // SEASON_LEN]


def outside(day):
    se = season_of(day)
    (t0, t1), (d0, d1) = SEASON_ENV[se]
    k = ((year_day(day) - 1) % SEASON_LEN) / (SEASON_LEN - 1)
    return t0 + (t1 - t0) * k, d0 + (d1 - d0) * k


def weekday(day):
    return (day - 1) % 7  # 0 = 周一


WEEK_CN = "一二三四五六日"


# ───────── 存档初始状态 ─────────
def _fresh_state(seed):
    st = {
        "v": VERSION, "seed": seed, "rng": seed, "turn": 0, "day": 1, "min": 0,
        "funds": START_FUNDS, "rep": START_REP, "bonus": 0,
        "supplies": {k: v[2] for k, v in SUPPLIES.items()},
        "zones": {z: {"temp": d["temp"], "photo": 0, "radio": z == CORRIDOR_ZONE, "nb": False,
                      "locked": bool(d.get("locked"))} for z, d in ZONES.items()},
        "plants": {}, "lots": {}, "crosses": {}, "pollen": {}, "flasks": {},
        "next": {"P": 1, "S": 1, "X": 1, "Q": 1, "F": 1},
        "catalog": {"genera": [], "lines": [], "traits": {}, "anomalies": {}},
        "collection": [], "herbarium": [], "docs": [], "facts": [], "flags": [], "npc": {},
        "edone": [], "pending": None, "notes": [], "log": [], "ups": [], "reports": [],
        "news": [], "searched": {}, "stats": {"sown": 0, "germ": 0, "crosses": 0, "harvests": 0, "died": 0,
                                               "observed": 0, "tests": 0, "reports": 0},
        "nb_tonight": {}, "kcap": ZONES["K"]["cap"],
    }
    return st


class Game:
    def __init__(self, state, path):
        self.s = state
        self.path = path
        self.rng = Rng(state["rng"])
        self.out = []
        self._newt = []

    # ───── 基础 ─────
    def say(self, *lines):
        self.out.extend(x for x in lines if x)

    def log(self, text, show=True):
        self.s["log"].append([self.s["day"], text])
        if len(self.s["log"]) > 3000:
            self.s["log"] = self.s["log"][-3000:]
        if show:
            self.say(text)

    def news(self, text):
        self.s["news"].append(text)

    def save(self):
        self.s["rng"] = self.rng.state
        data = json.dumps(self.s, ensure_ascii=False, separators=(",", ":"))
        d = os.path.dirname(os.path.abspath(self.path))
        if d and not os.path.isdir(d):
            os.makedirs(d, exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(data)
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                pass
        if os.path.exists(self.path):
            try:
                shutil.copyfile(self.path, self.path + ".bak")
            except OSError:
                pass
        os.replace(tmp, self.path)

    def flag(self, f):
        return f in self.s["flags"]

    def setflag(self, f):
        if f not in self.s["flags"]:
            self.s["flags"].append(f)

    def up(self, u):
        return u in self.s["ups"]

    def npc(self, nid):
        return self.s["npc"].setdefault(nid, {"trust": 0, "mem": [], "met": False, "said": [], "asked": [],
                                               "voiced": [], "idle": 0, "last": 0})

    def trust_word(self, nid):
        t = self.npc(nid)["trust"]
        w = TRUST_WORDS[0][1]
        for lim, word in TRUST_WORDS:
            if t >= lim:
                w = word
        return w

    def spend(self, m):
        self.s["min"] = min(DAY_MIN, self.s["min"] + max(0, m))

    def left(self):
        return DAY_MIN - self.s["min"]

    def anomaly(self, aid):
        return self.s["catalog"]["anomalies"].get(aid, 0)

    def set_anomaly(self, aid, stage):
        cur = self.anomaly(aid)
        if stage > cur:
            self.s["catalog"]["anomalies"][aid] = stage
            title, seen, why = ANOMALIES[aid]
            if stage == 1:
                self.say(f"❓ 异常记录：{title}——{seen}（catalog anomalies）")
            else:
                self.say(f"💡 你想明白了：{title}。{why}（可以写成报告：report anomaly {aid}）")

    # ───── 条件 / 效果 ─────
    def ok(self, conds):
        for c in conds or []:
            if isinstance(c, list):
                if not any(self.ok([x]) for x in c):
                    return False
            elif not self.c1(c):
                return False
        return True

    def c1(self, c):
        neg = c.startswith("!")
        r = self._c(c[1:] if neg else c)
        return (not r) if neg else r

    def _c(self, c):
        s = self.s
        m = _NUM.match(c)
        if m:
            k, op, v = m.group(1), m.group(2), int(m.group(3))
            val = {"day": s["day"], "funds": s["funds"], "rep": s["rep"], "year": (s["day"] - 1) // YEAR_LEN + 1}[k]
            return _cmp(val, op, v)
        m = _TRUST.match(c)
        if m:
            return _cmp(self.npc(m.group(1))["trust"], m.group(2), int(m.group(3)))
        m = _ANOM.match(c)
        if m:
            return self.anomaly(m.group(1)) >= int(m.group(2))
        k, _, rest = c.partition(":")
        if k == "flag":
            return self.flag(rest)
        if k == "fact":
            return rest in s["facts"]
        if k == "doc":
            return rest in s["docs"]
        if k == "met":
            return self.npc(rest)["met"]
        if k == "present":
            return self.present(rest)
        if k == "up":
            return self.up(rest)
        if k == "season":
            return season_of(s["day"]) == rest
        if k == "line_alive":
            return any(p["line"] == rest and p["alive"] for p in s["plants"].values())
        if k == "special_cond":
            return SPECIAL_COND[rest](self)
        raise ValueError(f"未知条件 {c}")

    def run_eff(self, effs):
        for e in effs or []:
            if isinstance(e, dict):
                self.run_eff(e.get("then") if self.ok(e["if"]) else e.get("else", []))
                continue
            k, _, rest = e.partition(":")
            s = self.s
            if k == "say":
                self.say(rest)
            elif k == "log":
                self.log(rest)
            elif k == "flag":
                self.setflag(rest)
            elif k == "unflag":
                if rest in s["flags"]:
                    s["flags"].remove(rest)
            elif k == "fact":
                if rest not in s["facts"]:
                    s["facts"].append(rest)
            elif k == "doc":
                if rest not in s["docs"]:
                    s["docs"].append(rest)
                    self.say(f"📄 得到文件：{DOCS[rest][0]}（read {rest}）")
            elif k == "trust":
                nid, d = rest.split(":")
                n = self.npc(nid)
                n["trust"] = max(-3, min(4, n["trust"] + int(d)))
            elif k == "mem":
                nid, tag, text = rest.split(":", 2)
                mem = self.npc(nid)["mem"]
                mem[:] = [m for m in mem if m[0] != tag]
                mem.append([tag, text, s["day"]])
            elif k == "funds":
                s["funds"] += int(rest)
            elif k == "rep":
                s["rep"] = max(0, min(100, s["rep"] + int(rest)))
            elif k == "lot":
                line, n, src = rest.split(":", 2)
                sid = self.lot_from_line(line, int(n), src)
                self.say(f"🌰 种子库新增批次 {sid}：{LINES[line]['name']} {n} 粒——{src}")
            elif k == "plant":
                line, zone, stage, src = rest.split(":", 3)
                pid = self.plant_from_line(line, zone, stage, src)
                self.say(f"🌿 新登记植株 {pid}：{LINES[line]['name']}，在{ZONES[zone]['name']}——{src}")
            elif k == "anomaly":
                aid, st = rest.split(":")
                self.set_anomaly(aid, int(st))
            elif k == "supply":
                it, n = rest.split(":")
                s["supplies"][it] = s["supplies"].get(it, 0) + int(n)
            elif k == "met":
                self.npc(rest)["met"] = True
            elif k == "choice":
                self.fire_event(rest)
            elif k == "special":
                name, _, arg = rest.partition(":")
                SPECIALS[name](self, arg)
            else:
                raise ValueError(f"未知效果 {e}")

    # ───── NPC 在不在 ─────
    def present(self, nid):
        if nid not in NPCS:
            return False
        w = NPCS[nid]["where"]
        d = self.s["day"]
        wd = weekday(d)
        if nid == "mo" and self.flag("mo_away"):
            return False
        if w == "always":
            return True
        if w == "weekday":
            return wd < 5
        if w == "mwf":
            return wd in (0, 2, 4)
        if w == "tth":
            return wd in (1, 3)
        if w == "evening":
            return self.s["min"] >= 360
        if w == "visit":
            return self.flag("lin_here")
        if w.startswith("away:"):
            yd = year_day(d)
            for rng_ in w[5:].split(","):
                a, b = rng_.split("-")
                if int(a) <= yd <= int(b):
                    return False
            return True
        return False

    # ───── 植株 / 批次 ─────
    def new_id(self, k):
        n = self.s["next"][k]
        self.s["next"][k] = n + 1
        return f"{k}{n:04d}" if k == "P" else f"{k}{n:03d}"

    def lot_from_line(self, line, n, src):
        L = LINES[line]
        seeds = [self.genome_from_line(line) for _ in range(n)]
        return self.new_lot(seeds, {"src": src, "line": line, "xid": None, "mother": None, "father": None,
                                    "gen": 0, "label": L["name"], "anc": [line],
                                    "viab": 0.35 if line == "CUP-LIN" else 0.92})

    def genome_from_line(self, line):
        L = LINES[line]
        if L.get("wild"):
            g = GN.from_population(L["pop"], self.rng, L.get("base", ""))
        else:
            g = GN.parse(L["geno"])
        return GN.new_genome(g, L["genus"], pl=L.get("pl", 0.0), sil=L.get("sil"))

    def new_lot(self, seeds, meta):
        sid = self.new_id("S")
        lot = {"id": sid, "seeds": seeds, "n0": len(seeds), "day": self.s["day"], "used": 0}
        lot.update(meta)
        self.s["lots"][sid] = lot
        return sid

    def plant_from_line(self, line, zone, stage, src):
        gen = self.genome_from_line(line)
        p = self.new_plant(gen, zone, {"line": line, "lot": None, "xid": None, "mother": None, "father": None,
                                       "gen": 0, "label": LINES[line]["name"], "src": src, "anc": [line], "how": "引入"})
        if stage in ("mature", "juvenile"):
            g = self.genus(p)
            p["stage"] = stage
            p["age"] = (g["mature"] + (2 if g["annual"] else 30)) if stage == "mature" else 8
            p["size"] = round(g["height"] * GN.height_factor(gen) * (0.9 if stage == "mature" else 0.4), 1)
            p["pot"] = "M"
            p["germ_day"] = self.s["day"]
            p["rest"] = self.rng.randint(0, 6)
            self.catalog_line(p)
        return p["id"]

    def new_plant(self, genome, zone, meta):
        pid = self.new_id("P")
        p = {"id": pid, "name": "", "genome": genome, "zone": zone, "stage": "seed", "age": 0, "size": 0.0,
             "health": 80.0, "water": 60.0, "food": 60.0, "pot": "S", "pests": {}, "bag": False,
             "flower": None, "fruit": None, "rest": 0, "blooms": 0, "obs": {}, "hist": [], "tags": [],
             "diary": [], "marks": [], "tests": {}, "alive": True, "death": None, "cold": 0, "doubt": False,
             "born": self.s["day"], "germ_day": None, "germ_ok": True, "streaks": [], "wet_days": 0}
        p.update(meta)
        self.s["plants"][pid] = p
        self.hist(p, f"登记：{meta.get('src') or meta.get('how', '')}")
        return p

    def hist(self, p, text):
        p["hist"].append([self.s["day"], text])
        if len(p["hist"]) > 80:
            p["hist"] = p["hist"][:5] + p["hist"][-70:]

    def genus(self, p):
        return GENERA[p["genome"]["genus"].split("×")[0]]

    def gname(self, p):
        return "×".join(GENERA[x]["name"] for x in p["genome"]["genus"].split("×"))

    def pname(self, p):
        nick = f"「{p['name']}」" if p["name"] else ""
        return f"{p['id']}{nick}"

    def zone_plants(self, z, alive=True):
        return [p for p in self.s["plants"].values() if p["zone"] == z and (p["alive"] or not alive)
                and p["stage"] not in ("gone", "lent")]

    def zone_count(self, z):
        return len(self.zone_plants(z))

    def zcap(self, z):
        return self.s["kcap"] if z == "K" else ZONES[z]["cap"]

    def catalog_line(self, p):
        cat = self.s["catalog"]
        for g in p["genome"]["genus"].split("×"):
            if g not in cat["genera"]:
                cat["genera"].append(g)
        for a in p.get("anc", []):
            if a in LINES and a not in cat["lines"]:
                cat["lines"].append(a)

    def kill(self, p, cause):
        p["alive"] = False
        p["stage"] = "dead"
        p["death"] = [self.s["day"], cause]
        p["fruit"] = None
        p["flower"] = None
        self.hist(p, f"死亡：{cause}")
        self.s["stats"]["died"] += 1
        if p["id"] in self.s["collection"]:
            self.s["collection"].remove(p["id"])
            self.press(p, auto=True)

    def press(self, p, auto=False):
        spec = {"id": p["id"], "name": p["name"], "line": p["line"], "label": p.get("label", ""),
                "gname": self.gname(p), "obs": {k: v[1] for k, v in p["obs"].items()}, "day": self.s["day"],
                "born": p["born"], "diary": list(p["diary"]), "tags": list(p["tags"]),
                "how": "收藏温室里自然死亡，做成了标本" if auto else "压制成标本"}
        self.s["herbarium"].append(spec)
        if auto:
            self.news(f"📕 收藏温室里的 {self.pname(p)} 死了。你把它压成了标本，日记和标签都夹在一起。")

    # ───── 环境 ─────
    def zone_env(self, z):
        s = self.s
        zs = s["zones"][z]
        zd = ZONES[z]
        out_t, daylen = outside(s["day"])
        if zd["heat"]:
            t = max(zs["temp"], zd["min"] if zd["min"] is not None else -99)
            t = max(t, out_t - zd["cool"])  # 降温能力有限
            if self.flag("heatwave") and z in ("A", "N", "K", "B"):
                t = max(t, out_t + 5)
            if self.flag("heater_broken") and z in ("A", "B", "N"):
                t = min(t, {"A": 9, "B": 14, "N": 12}[z])
        else:
            t = out_t + 3
        photo = zs["photo"] if (zs["photo"] and self.up("lamp")) else daylen
        return {"temp": round(t, 1), "daylen": round(photo, 1), "light": zd["light"], "hum": zd["hum"],
                "radio": zs["radio"], "nb": s["nb_tonight"].get(z, False)}

    def patrol_night(self, day):
        if season_of(day) == "冬":
            return day % 2 == 1
        return year_day(day) % 3 == 1

    # ───── 观察：基因型 → 可见表型 ─────
    def view(self, p):
        """返回 {性状: (键, 描述)}，只包含当前阶段、当前环境下看得见的东西。"""
        gen = p["genome"]
        g = self.genus(p)
        env = self.zone_env(p["zone"]) if p["zone"] in ZONES else {"temp": 20, "light": 1, "radio": False, "daylen": 12}
        v = {}
        st = p["stage"]
        if st in ("seed", "nogerm", "gone", "lent"):
            return v
        lk, lt = GN.leaf(gen, env["light"])
        if self.genus(p) is GENERA["Umbrafilix"]:
            lt = lt.replace("叶", "羽片")
        v["leaf"] = (lk, lt)
        hk = "health_" + ("good" if p["health"] >= 75 else "ok" if p["health"] >= 50 else "weak" if p["health"] >= 25 else "dying")
        v["health"] = (hk, {"health_good": "健壮", "health_ok": "还行", "health_weak": "虚弱", "health_dying": "奄奄一息"}[hk])
        if st == "dead":
            return {"leaf": v["leaf"]} if gen["pl"] < 1 else {}
        if st != "seedling":
            base = g["height"]
            r = p["size"] / base
            hc = "h_xs" if r < 0.45 else "h_s" if r < 0.75 else "h_m" if r < 1.05 else "h_l" if r < 1.3 else "h_xl"
            v["height"] = (hc, f"{p['size']:.0f} cm（{ {'h_xs': '极矮', 'h_s': '偏矮', 'h_m': '中等', 'h_l': '偏高', 'h_xl': '很高'}[hc]}）")
            sk, stx = GN.stem(gen)
            if p["genome"]["genus"].startswith("Umbrafilix"):
                sk, stx = ("curl", "羽片卷曲不展") if sk == "twisted" else ("flat", "羽片舒展")
            v["stem"] = (sk, stx)
        if env["radio"] and "Aeris" in gen["genus"]:
            v["sound"] = ("lean", "叶片整齐地朝收音机那边偏过去") if GN.sound_responsive(gen) else ("still", "收音机开着，叶子没什么反应")
        if env["temp"] < 10:
            tol = GN.tolerance(gen, "cold") + (0.3 if g["temp"][0] <= 4 else 0)
            v["cold"] = ("cold_ok", "低温下叶片舒展，没有冻伤") if tol >= 0.6 else ("cold_mild", "叶缘有一点冻伤的水渍斑") if tol >= 0.3 else ("cold_hurt", "叶子冻得发软、发暗")
        if p["water"] < 20:
            tol = GN.tolerance(gen, "drought")
            v["drought"] = ("dry_ok", "土很干，叶子还挺着") if tol >= 0.5 else ("dry_wilt", "土干了，叶子耷拉下来")
        if env["light"] < 0.75:
            tol = GN.tolerance(gen, "shade") + (0.5 if g["light"] <= 0.6 else 0)
            v["shade"] = ("shade_ok", "光线暗，叶片照样油亮") if tol >= 0.5 else ("shade_leggy", "光线暗，节间拉长，有点徒长")
        if st == "flowering" and p["flower"]:
            fl = p["flower"]
            if GN.needs_nightbreak(gen) and not fl.get("open"):
                v["flower"] = ("bud_closed", "花苞紧闭，没有开")
            else:
                ck, ct = GN.flower_color(gen, env["temp"])
                skind = GN.streak_type(gen)
                if skind != "none":
                    n = fl.get("streaks", 0)
                    ck += "+streak"
                    ct += f"，花瓣上有 {n} 道红色条纹" if n else "，这一季没有条纹"
                if GN.is_wide_hybrid(gen):
                    ck += "+hybrid"
                    ct += "，花形介于两个亲本之间，有点不对称"
                v["flower"] = (ck, ct)
                sk, stt = GN.scent(gen, env["temp"])
                v["scent"] = ("none" if sk == "none_silent" else sk, stt)
        if p.get("bloom_age"):
            a = p["bloom_age"]
            m = g["mature"]
            bc = "b_early" if a < m * 0.85 else "b_late" if a > m * 1.5 else "b_normal"
            ph = p.get("bloom_photo", 12)
            sd = "_sd" if ph <= 12.5 else "_ld"
            v["bloom"] = (bc + sd, {"b_early": "开花早", "b_normal": "开花期正常", "b_late": "开花晚"}[bc]
                          + ("，在短日照下开的" if sd == "_sd" else "，在长日照下开的") + f"（发芽后第 {a} 天第一次开花，当时日照 {ph} 小时）")
        if p["fruit"] and st == "fruiting":
            fr = p["fruit"]
            if self.s["day"] >= fr["ready"]:
                v["fruit"] = ("fruit_ripe", "果荚成熟，裂开了一条缝，可以采种了")
            else:
                v["fruit"] = ("fruit_green", f"果荚还是绿的（大约第 {fr['ready']} 天成熟）")
        if p["pests"]:
            v["pests"] = ("pest", "；".join(f"{PESTS[k]['name']}：{PESTS[k]['look']}" for k in p["pests"]))
        return v

    def observe(self, p, quiet=False):
        v = self.view(p)
        cat = self.s["catalog"]["traits"]
        newt = []
        for t, (k, txt) in v.items():
            if t in ("health", "pests", "fruit"):
                p["obs"][t] = [k, txt, self.s["day"]]
                continue
            p["obs"][t] = [k, txt, self.s["day"]]
            key = f"{t}:{k}"
            if key not in cat:
                cat[key] = [self.s["day"], p["id"], txt.split("（")[0]]
                newt.append(txt.split("（")[0])
        self.catalog_line(p)
        self.s["stats"]["observed"] += 1
        self.check_anomalies_on_observe(p, v)
        self._newt = newt
        return v

    def check_anomalies_on_observe(self, p, v):
        gen = p["genome"]
        fl = v.get("flower")
        if "Noctubella" in gen["genus"] and fl and fl[0] != "bud_closed" and GN.needs_nightbreak(gen):
            self.set_anomaly("noc", 1)
            if self.s["zones"][p["zone"]]["nb"]:
                self.set_anomaly("noc", 2)
        if fl and "+streak" in fl[0]:
            self.set_anomaly("streak", 1)
            if len(set(p["streaks"])) >= 2 and "lin_p1" in self.s["docs"]:
                self.set_anomaly("streak", 2)
        sc = v.get("scent")
        if sc and "Odorina" in gen["genus"]:
            if sc[0] == "none" and "O" in gen["g"]["O"]:
                p["was_silent"] = True
            elif sc[0] != "none" and p.get("was_silent"):
                self.set_anomaly("scent", 2)
        snd = v.get("sound")
        if snd:
            self.s.setdefault("sound_seen", [])
            if snd[0] not in self.s["sound_seen"]:
                self.s["sound_seen"].append(snd[0])
            if snd[0] == "lean":
                self.set_anomaly("sound", 1)
            if len(self.s["sound_seen"]) == 2 or ("lean" in self.s["sound_seen"] and "mo_draft" in self.s["docs"]):
                self.set_anomaly("sound", 2)
        lf = v.get("leaf")
        if lf:
            if lf[0].startswith("inkbronze"):
                self.set_anomaly("bronze", 1)
            if "sector" in lf[0] or lf[0] == "albino":
                self.set_anomaly("chimera", 1)
                self.check_chimera()

    def check_chimera(self):
        """正交和反交都做过，而且双方后代都观察过叶片 → 解释。"""
        as_m = as_f = 0
        for x in self.s["crosses"].values():
            if not x.get("lot"):
                continue
            kids = [p for p in self.s["plants"].values() if p.get("xid") == x["id"] and "leaf" in p["obs"]]
            if len(kids) < 5:
                continue
            if x.get("m_pl", 0) > 0 and x.get("f_pl", 0) == 0:
                as_m += 1
            if x.get("f_pl", 0) > 0 and x.get("m_pl", 0) == 0:
                as_f += 1
        if as_m and as_f:
            self.set_anomaly("chimera", 2)

    # ───── 一天的模拟 ─────
    def plant_day(self, p, env):
        s = self.s
        g = self.genus(p)
        gen = p["genome"]
        day = s["day"]
        if p["stage"] == "seed":
            if day >= p["germ_day"]:
                if p["germ_ok"]:
                    p["stage"] = "seedling"
                    p["age"] = 0
                    p["size"] = 1.0
                    p["health"] = 70.0
                    s["stats"]["germ"] += 1
                    self.hist(p, "发芽")
                    if gen["pl"] >= 1:
                        self.hist(p, "子叶是白的")
                else:
                    p["stage"] = "nogerm"
                    p["alive"] = False
                    p["death"] = [day, "没有发芽"]
                    self.hist(p, "过了发芽期，没有出苗")
            return
        if p["stage"] in ("dead", "nogerm", "gone", "lent"):
            return
        p["age"] += 1
        t = env["temp"]
        # 水分
        evap = (2.5 + max(0, t - 10) / 4 + p["size"] / 25) * (1.2 - env["hum"] / 120)
        p["water"] = max(0.0, p["water"] - evap)
        p["food"] = max(0.0, p["food"] - (0.6 + p["size"] / 80))
        # 适应度
        lo, hi = g["temp"]
        lo -= 6 * GN.tolerance(gen, "cold")
        f = 1.0
        if t < lo:
            f -= min(0.8, (lo - t) * 0.05)
        elif t > hi:
            f -= min(0.8, (t - hi) * 0.07)
        dt = GN.tolerance(gen, "drought")
        if p["water"] < 10:
            f -= 0.8 * (1 - 0.7 * dt)
        elif p["water"] < 20:
            f -= 0.45 * (1 - 0.7 * dt)
        elif p["water"] < 30:
            f -= 0.12 * (1 - dt)
        if p["water"] > 88:
            p["wet_days"] += 1
        else:
            p["wet_days"] = 0
        if p["wet_days"] >= 3:
            f -= 0.3
            if p["wet_days"] == 3:
                self.hist(p, "盆土一直太湿，根有点发黑")
        if p["food"] < 15:
            f -= 0.15
        light_need = g["light"]
        lt = env["light"] + 0.4 * GN.tolerance(gen, "shade")
        if lt < light_need - 0.15:
            f -= min(0.3, (light_need - lt) * 0.6)
        if p["size"] > POT_CAP[p["pot"]] and p["stage"] != "seedling":
            f -= 0.15
            if not p.get("rootbound"):
                p["rootbound"] = True
                self.hist(p, "根从盆底钻出来了")
        if p["zone"] == "N" and p["age"] > 16:
            f -= 0.15
        for k, sev in p["pests"].items():
            f -= 0.05 * sev
        if gen["pl"] >= 1:
            f = -1 if p["age"] > 4 else 0.3
        if GN.is_wide_hybrid(gen) and not gen["dbl"]:
            f -= 0.05
        f = max(-1.0, min(1.0, f))
        p["health"] = max(0.0, min(100.0, p["health"] + (f - 0.6) * (30 if f < 0.6 else 18)))
        if p["health"] <= 0:
            cause = "白化苗，子叶的养分耗尽了" if gen["pl"] >= 1 else self.death_cause(p, env)
            self.kill(p, cause)
            self.news(f"🥀 {self.pname(p)}（{self.gname(p)}）死了：{cause}")
            return
        # 胁迫沉默 / 春化解除
        if p["health"] < 35 and "O" in gen["g"]["O"] and "O" not in gen["sil"] and self.rng.random() < 0.04:
            gen["sil"].append("O")
        if t <= 10:
            p["cold"] += 1
            if p["cold"] == 10:
                self.hist(p, "在低温里待满了十天")
            if p["cold"] >= 10 and "O" in gen["sil"]:
                gen["sil"].remove("O")
                p["cold"] = 0
        else:
            p["cold"] = max(0, p["cold"] - 1)
        # 生长
        target = g["height"] * GN.height_factor(gen) * (0.55 + 0.45 * max(0, f)) * (1.0 if lt >= light_need else 1.15)
        rate = 0.05 if p["stage"] == "seedling" else 0.09
        if p["size"] < target:
            p["size"] = round(p["size"] + (target - p["size"]) * rate * max(0.1, f), 2)
        # 阶段
        if p["stage"] == "seedling" and p["age"] >= 7:
            p["stage"] = "juvenile"
        mature_at = g["mature"] * (0.72 if GN.early(gen) else 1.0)
        if p["stage"] == "juvenile" and p["age"] >= mature_at:
            p["stage"] = "mature"
            self.hist(p, "长成了")
        if g["annual"] and p["age"] >= g["life"] and p["stage"] in ("mature", "juvenile"):
            self.kill(p, "一年生植物，寿命到了，自然枯萎")
            self.news(f"🍂 {self.pname(p)}（{self.gname(p)}）枯萎了：一年生，到时候了。")
            return
        if p["rest"] > 0:
            p["rest"] -= 1
        # 开花
        if p["stage"] == "mature" and g["flowers"] and p["rest"] == 0 and f > 0.2:
            induce = True
            if GN.short_day(gen) and (env["daylen"] > 12.5 or env["nb"]):
                induce = False
            if induce:
                self.start_flower(p, env)
        elif p["stage"] == "flowering":
            if p["fruit"]:
                self.fruit_day(p)
            self.flower_day(p, env)
        elif p["stage"] == "fruiting":
            self.fruit_day(p)

    def death_cause(self, p, env):
        g = self.genus(p)
        if p["water"] < 15:
            return "缺水，干死了"
        if p["wet_days"] >= 3:
            return "长期积水，烂根"
        if env["temp"] < g["temp"][0] - 3:
            return "冻死了"
        if env["temp"] > g["temp"][1] + 3:
            return "热死了"
        if p["pests"]:
            return "病虫害"
        return "长期胁迫，衰弱而死"

    def start_flower(self, p, env):
        gen = p["genome"]
        p["stage"] = "flowering"
        p["blooms"] += 1
        n = 0
        st = GN.streak_type(gen)
        if st == "many":
            n = self.rng.randint(3, 14)
        elif st == "few":
            n = self.rng.randint(0, 4)
        if st != "none":
            p["streaks"].append(n)
        p["flower"] = {"start": self.s["day"], "end": self.s["day"] + self.genus(p)["flower"], "open": False,
                       "opened": 0, "streaks": n, "crossed": False}
        if not p.get("bloom_age"):
            p["bloom_age"] = p["age"]
            p["bloom_photo"] = env["daylen"]
        self.hist(p, f"第 {p['blooms']} 次开花" + ("（花苞）" if GN.needs_nightbreak(gen) else ""))
        self.news(f"🌸 {self.pname(p)}（{self.gname(p)}）开花了。" if not GN.needs_nightbreak(gen)
                  else f"🌱 {self.pname(p)}（{self.gname(p)}）长出了花苞。")
        self.update_open(p, env)

    def update_open(self, p, env):
        if not p["flower"]:
            return
        if GN.needs_nightbreak(p["genome"]):
            was = p["flower"]["open"]
            p["flower"]["open"] = bool(env["nb"])
            if p["flower"]["open"]:
                p["flower"]["opened"] += 1
                if not was:
                    self.news(f"🔔 {self.pname(p)}（{self.gname(p)}）的花今天早上开了。")
        else:
            p["flower"]["open"] = True

    def flower_day(self, p, env):
        fl = p["flower"]
        self.update_open(p, env)
        # 熊蜂
        if self.flag("bees") and p["zone"] == "A" and not p["bag"] and not p["fruit"] and fl["open"] and self.rng.random() < 0.5:
            self.open_pollinate(p, force=True)
        if self.s["day"] >= fl["end"]:
            if not p["fruit"] and not p["bag"] and (fl["opened"] > 0 or not GN.needs_nightbreak(p["genome"])):
                self.open_pollinate(p)
            if GN.needs_nightbreak(p["genome"]) and fl["opened"] == 0:
                self.hist(p, "这一季的花苞一次也没开，枯掉了")
            p["flower"] = None
            if p["fruit"]:
                p["stage"] = "fruiting"
            else:
                p["stage"] = "mature"
                p["rest"] = 6 if self.genus(p)["annual"] else 14
            p["bag"] = False

    def fruit_day(self, p):
        fr = p["fruit"]
        day = self.s["day"]
        x = self.s["crosses"].get(fr["xid"])
        if not fr["ok"] and day >= fr["set"] + 3:
            p["fruit"] = None
            if p["stage"] == "flowering" and p["flower"]:
                p["flower"]["crossed"] = False
            else:
                p["stage"] = "mature"
                p["rest"] = 6 if self.genus(p)["annual"] else 12
            if x:
                x["status"] = "失败：没有坐果"
                x["ok"] = False
            self.hist(p, f"{fr['xid']} 授粉失败，没有坐果")
            self.news(f"✖ {self.pname(p)} 上的 {fr['xid']} 没有坐果。")
            return
        if fr["ok"] and not fr.get("told") and day >= fr["set"] + 3:
            fr["told"] = True
            if x:
                x["status"] = "坐果"
                x["ok"] = True
            self.hist(p, f"{fr['xid']} 坐果了")
        if fr["ok"] and day == fr["ready"]:
            self.news(f"🫛 {self.pname(p)} 的果荚（{fr['xid']}）成熟了，可以采种（harvest {p['id']}）。")
        if fr["ok"] and day > fr["ready"] + 6:
            p["fruit"] = None
            p["stage"] = "mature"
            p["rest"] = 6 if self.genus(p)["annual"] else 12
            if x:
                x["status"] = "失败：错过采种期，种子散落了"
            self.hist(p, f"{fr['xid']} 的果荚裂开，种子散掉了（错过了采种期）")
            self.news(f"💨 {self.pname(p)} 的果荚（{fr['xid']}）裂开了，种子撒了一地。错过了采种期。")

    def pollinate(self, mother, father_gen, father_ref, kind, father_pl=0.0, force_ok=None):
        """建立杂交记录和果实。返回 xid。"""
        mg = mother["genome"]
        c, typ = GN.compat(mg, father_gen)
        prob = c * min(1.0, 0.4 + mother["health"] / 120) * GN.fertility(father_gen)
        if kind == "self" and not self.genus(mother)["selfok"]:
            prob *= 0.05
        ok = self.rng.random() < prob if force_ok is None else force_ok
        if typ == "none":
            ok = False
        xid = self.new_id("X")
        self.s["crosses"][xid] = {
            "id": xid, "day": self.s["day"], "mother": mother["id"], "father": father_ref, "kind": kind,
            "ok": None, "status": "授粉，等待坐果", "lot": None, "wide": typ == "wide", "report": False,
            "m_pl": mg["pl"], "f_pl": father_pl, "notes": [],
            "_fgen": GN.copy_genome(father_gen),
        }
        fr = self.genus(mother)["fruit"]
        mother["fruit"] = {"xid": xid, "ok": ok, "set": self.s["day"], "ready": self.s["day"] + fr + 3}
        if mother["flower"]:
            mother["flower"]["crossed"] = True
        self.s["stats"]["crosses"] += 1
        return xid

    def open_pollinate(self, p, force=False):
        if p["fruit"]:
            return
        gen = p["genome"]
        cands = [q for q in self.zone_plants(p["zone"]) if q is not p and q["stage"] == "flowering" and q["flower"]
                 and q["flower"]["open"] and GN.compat(gen, q["genome"])[1] != "none"]
        r = self.rng.random()
        if cands and (force or r < 0.35):
            q = self.rng.choice(cands)
            xid = self.pollinate(p, q["genome"], "open", "open", q["genome"]["pl"])
            self.s["crosses"][xid]["_true_father"] = q["id"]
        elif self.genus(p)["selfok"] and (force or r < 0.3):
            xid = self.pollinate(p, gen, "open", "open", gen["pl"])
            self.s["crosses"][xid]["_true_father"] = p["id"]
        else:
            return
        self.s["crosses"][xid]["status"] = "开放授粉（父本不明），等待坐果"
        self.hist(p, f"自然授粉（{xid}，父本不明）" + ("——熊蜂" if force else ""))

    def pests_day(self):
        for z in ZONES:
            plants = [p for p in self.zone_plants(z) if p["stage"] not in ("seed",)]
            if not plants:
                continue
            env = self.zone_env(z)
            se = season_of(self.s["day"])
            for k, d in PESTS.items():
                base = 0.005
                if d["hot"] and env["temp"] > 22:
                    base += 0.02
                if d["dry"] and env["hum"] < 55:
                    base += 0.015
                if k == "mildew" and env["hum"] >= 70 and env["temp"] < 22:
                    base += 0.02
                if k == "gnat" and any(p["water"] > 85 for p in plants):
                    base += 0.03
                if se == "冬":
                    base *= 0.4
                if z == "K":
                    base *= 0.3
                if self.rng.random() < base:
                    p = self.rng.choice(plants)
                    if k not in p["pests"]:
                        p["pests"][k] = 1
                        self.hist(p, f"发现{d['name']}")
                        self.news(f"🐛 {ZONES[z]['name']}的 {self.pname(p)} 上出现了{d['name']}。")
            for p in plants:
                for k in list(p["pests"]):
                    if p["pests"][k] < 5 and self.rng.random() < 0.3:
                        p["pests"][k] += 1
                    if self.rng.random() < 0.08 * p["pests"][k]:
                        q = self.rng.choice(plants)
                        if k not in q["pests"]:
                            q["pests"][k] = 1
                            self.hist(q, f"{PESTS[k]['name']}从旁边传过来了")

    def end_day(self):
        s = self.s
        day = s["day"]
        for e in EVENTS:
            if e["at"] == "dusk" and self.event_today(e):
                self.fire_event(e["id"], closed=True)
        # 今夜：夜断（补光 / 巡逻）
        nb = {}
        for z, zs in s["zones"].items():
            nb[z] = bool(zs["nb"] and self.up("nblamp"))
        if self.patrol_night(day):
            nb[CORRIDOR_ZONE] = True
        s["nb_tonight"] = nb
        s["day"] += 1
        s["min"] = 0
        s["news"] = []
        # 自动照料
        for p in s["plants"].values():
            if not p["alive"] or p["stage"] in ("seed", "gone", "lent"):
                continue
            if p["zone"] == "K":
                p["water"] = max(p["water"], 60)
                p["food"] = max(p["food"], 50)
                p["pests"] = {k: v for k, v in p["pests"].items() if v > 2}
            elif self.up("drip") and p["zone"] in ZONES and p["water"] < 45:
                p["water"] = 65
        envs = {z: self.zone_env(z) for z in ZONES}
        for pid in list(s["plants"]):
            p = s["plants"][pid]
            if p["zone"] in envs:
                self.plant_day(p, envs[p["zone"]])
        self.pests_day()
        # 花粉、组培、种子库
        for q in list(s["pollen"].values()):
            q["age"] += 1
        for lot in s["lots"].values():
            lot["viab"] = max(0.0, lot["viab"] - 0.0015)
        for fl in s["flasks"].values():
            if fl["state"] == "growing" and s["day"] >= fl["ready"]:
                fl["state"] = "contaminated" if fl["bad"] else "ready"
                self.news(f"🧪 组培瓶 {fl['id']}（来自 {fl['src']}）" + ("长了霉，污染了。" if fl["bad"] else "里的小苗长好了，可以 transplant。"))
        # 花费
        cost = 0.0
        out_t, daylen = outside(s["day"])
        for z, zs in s["zones"].items():
            if not self.zone_plants(z) or not ZONES[z]["heat"]:
                continue
            e = envs[z]
            if e["temp"] > out_t:
                cost += (e["temp"] - out_t) * 0.9
            elif e["temp"] < out_t:
                cost += (out_t - e["temp"]) * 1.0
            if zs["photo"] and self.up("lamp") and zs["photo"] > daylen:
                cost += (zs["photo"] - daylen) * 2.0
            if zs["nb"] and self.up("nblamp"):
                cost += 1
        cost = round(cost)
        s["funds"] -= cost
        # 早上
        yd = year_day(s["day"])
        hdr = f"\n☀️ ── 第 {s['day']} 天 · {season_of(s['day'])}季第 {(yd - 1) % SEASON_LEN + 1} 天 · 星期{WEEK_CN[weekday(s['day'])]} ──"
        self.say(hdr)
        self.say(f"   室外 {out_t:.0f}℃，日照 {daylen:.1f} 小时。昨天的暖气、制冷和补光花了 {cost} 元。")
        if (s["day"] - 1) % GRANT_EVERY == 0:
            g = 800 + s["bonus"]
            s["funds"] += g
            self.say(f"💰 两周一次的拨款到账：{g} 元（基本 800" + (f" + 报告奖励 {s['bonus']}" if s["bonus"] else "") + "）。")
            s["bonus"] = 0
        for e in EVENTS:
            if e["at"] == "dawn" and self.event_today(e):
                self.fire_event(e["id"])
        if s["news"]:
            self.say("昨夜到今早：", *("  " + x for x in s["news"][:25]))
            if len(s["news"]) > 25:
                self.say(f"  ……还有 {len(s['news']) - 25} 条（log 查看）")
            for x in s["news"]:
                s["log"].append([s["day"], x])

    def event_today(self, e):
        if e["id"] in self.s["edone"] and not e.get("yearly"):
            return False
        d = self.s["day"]
        if e.get("day") is not None:
            if e.get("yearly"):
                if year_day(d) != e["day"]:
                    return False
                if [e["id"], d] in self.s.get("ydone", []):
                    return False
            elif d != e["day"]:
                return False
        return self.ok(e.get("need", []))

    def fire_event(self, eid, closed=False):
        e = EVENT_BY_ID[eid]
        if not self.event_today(e):
            return
        if e.get("yearly"):
            self.s.setdefault("ydone", []).append([eid, self.s["day"]])
        if eid not in self.s["edone"]:
            self.s["edone"].append(eid)
        self.run_eff(e.get("eff", []))
        ch = e.get("choice")
        if ch:
            opts = [i for i, o in enumerate(ch["opts"]) if self.ok(o["need"])]
            if not opts:
                return
            if closed:
                o = ch["opts"][opts[-1]]
                self.run_eff(o["eff"])
                return
            self.s["pending"] = {"src": "event", "id": eid, "opts": opts}
            self.say("❗ " + ch["text"], *[f"  {k + 1}. {ch['opts'][i]['label']}" for k, i in enumerate(opts)],
                     "（choose <编号>）")

    def bar(self):
        s = self.s
        alive = sum(1 for p in s["plants"].values() if p["alive"] and p["stage"] not in ("gone", "lent"))
        here = [NPCS[n]["name"] for n in NPCS if self.present(n)]
        b = (f"📊 第{s['day']}天 {hm(s['min'])}（剩 {self.left() // 60}h{self.left() % 60:02d}）｜{season_of(s['day'])}"
             f"｜💰{s['funds']}｜声誉 {s['rep']}｜植株 {alive}｜批次 {len(s['lots'])}｜在所：{'、'.join(here) or '无人'}")
        if s["pending"]:
            b += "｜❗等你 choose"
        return b


# ───────── 特殊效果 / 条件 ─────────
def _sc_nursery_two(g):
    lots = {}
    for p in g.zone_plants("N"):
        if p["stage"] in ("seedling", "juvenile") and p.get("lot"):
            lots.setdefault(p["lot"], []).append(p)
    return len([l for l in lots.values() if len(l) >= 2]) >= 2


def _sc_collection_any(g):
    return bool(g.s["collection"] or g.s["herbarium"])


def _sc_aeris_any(g):
    return any(p["alive"] and "Aeris" in p["genome"]["genus"] and p["stage"] in ("mature", "flowering", "fruiting")
               for p in g.s["plants"].values())


def _sc_lin_reply(g):
    return g.s.get("letter_day") is not None and g.s["day"] >= g.s["letter_day"] + 6


def _sc_lin_visit(g):
    return g.s.get("reply_day") is not None and g.s["day"] >= g.s["reply_day"] + 7


def _sc_lin_leave(g):
    return g.s.get("visit_day") is not None and g.s["day"] >= g.s["visit_day"] + 2


SPECIAL_COND = {"lin_reply_due": _sc_lin_reply, "lin_visit_due": _sc_lin_visit, "lin_leave_due": _sc_lin_leave,
                "nursery_two_lots": _sc_nursery_two, "collection_any": _sc_collection_any, "aeris_any": _sc_aeris_any}


def _sp_mixup(g, arg):
    lots = {}
    for p in g.zone_plants("N"):
        if p["stage"] in ("seedling", "juvenile") and p.get("lot"):
            lots.setdefault(p["lot"], []).append(p)
    keys = sorted(k for k, v in lots.items() if len(v) >= 2)[:2]
    a, b = lots[keys[0]], lots[keys[1]]
    fields = ("lot", "xid", "mother", "father", "gen", "label", "anc", "line")
    k = max(1, min(len(a), len(b)) // 2)
    pa = [g.rng.choice(a) for _ in range(k)]
    pb = [g.rng.choice(b) for _ in range(k)]
    for x, y in zip(pa, pb):
        if x is y or x.get("_true") or y.get("_true"):
            continue
        x["_true"] = {f: x.get(f) for f in fields}
        y["_true"] = {f: y.get(f) for f in fields}
        for f in fields:
            x[f], y[f] = y[f], x[f]
    for p in a + b:
        p["doubt"] = True
        g.hist(p, "来源存疑：实习生可能插错了标签")
    g.say(f"小满跑过来，脸是红的：「我昨天把育苗室里两盘苗（{keys[0]} 和 {keys[1]}）端上架子的时候，可能把标签插反了……也可能没有。我不确定。」",
          f"（这两批苗现在都标着「来源存疑」。可以 relabel <植株> <批次> 改记录，clear <植株> 去掉存疑标记。）")


def _sp_audit(g, arg):
    if g.s["funds"] >= 0:
        g.run_eff(["flag:audit_ok", "trust:jiang:+1", "say:蒋会计花了一下午对你的物资账。最后他合上本子：「对上了。」"])
    else:
        g.run_eff(["rep:-3", "trust:jiang:-1", "say:蒋会计看着你的账，叹了口气：「赤字。」他在本子上画了一个圈。"])


def _sp_cert(g, arg):
    bad = sum(1 for f in g.s["flasks"].values() if f["bad"] and f["day"] >= g.s["day"] - 14)
    if bad <= 1:
        g.run_eff(["flag:cert_passed", "trust:ge:+1", "log:组培室认证通过了。小葛请全组喝奶茶。"])
    else:
        g.run_eff(["trust:ge:-1", "flag:lab_closed", "log:组培室认证没过：最近两周污染了好几瓶。组培室停用七天整改。小葛一整天没说话。"])


def _sp_spend(g, arg):
    g.spend(int(arg))


def _sp_seedbank_hit(g, arg):
    x = float(arg)
    for lot in g.s["lots"].values():
        lot["viab"] = round(lot["viab"] * (1 - x), 3)


def _sp_corridor(g, arg):
    if g.flag("radio_offer"):
        g.fire_event("e_radio_move")
        return
    g.s["zones"][CORRIDOR_ZONE]["radio"] = False
    g.setflag("corridor_done")
    g.log("走廊改造开始了。老岑的收音机被撤走了，主温室里一下子安静下来。")


def _sp_radio_to(g, arg):
    g.s["zones"][CORRIDOR_ZONE]["radio"] = False
    if arg in ZONES:
        g.s["zones"][arg]["radio"] = True
        g.s["saved_radio_zone"] = arg
        g.setflag("radio_saved")
        g.say(f"老岑把收音机挂到了{ZONES[arg]['name']}的柱子上，「戏照听。电费算你的。」")
    g.setflag("corridor_done")


def _sp_openday_collection(g, arg):
    n = len(g.s["collection"]) + len(g.s["herbarium"])
    g.run_eff(["rep:+5", "trust:wen:+1", "funds:+100",
               f"say:你领着一拨又一拨的人走过窄窄的收藏温室。{n} 件收藏，你讲了每一件的来历。有个小孩指着一盆长得最怪的问：「它为什么长这样？」你说：「我也不知道，所以留着。」"])


def _sp_openday_sell(g, arg):
    sold = 0
    for p in list(g.s["plants"].values()):
        if sold >= 10:
            break
        if p["alive"] and p["zone"] in ("N", "A") and "Ruberia" in p["genome"]["genus"] and p["stage"] in ("seedling", "juvenile") \
                and p.get("gen", 0) == 0 and not p["fruit"] and not p["tags"] and not p["diary"] and p["id"] not in g.s["collection"]:
            p["alive"] = False
            p["stage"] = "gone"
            p["death"] = [g.s["day"], "开放日卖给了访客"]
            g.hist(p, "开放日卖给了一位访客")
            sold += 1
    g.run_eff([f"funds:+{15 * sold}", "rep:+1"])
    g.say(f"卖出了 {sold} 株朱点花苗，收入 {15 * sold} 元。" if sold else "你摆了一下午摊，可惜没有朱点花苗可卖。")


def _sp_evaluation(g, arg):
    s = g.s
    yr = (s["day"] - 1) // YEAR_LEN + 1
    reps = sum(1 for r in s["reports"] if r[0] > (yr - 1) * YEAR_LEN)
    expl = sum(1 for v in s["catalog"]["anomalies"].values() if v >= 2)
    traits = len(s["catalog"]["traits"])
    alive = [p for p in s["plants"].values() if p["alive"] and p["stage"] not in ("gone", "lent", "seed")]
    hp = sum(p["health"] for p in alive) / len(alive) if alive else 0
    score = reps * 2 + expl * 2 + traits // 10 + (2 if hp >= 60 else 0) + (1 if s["funds"] >= 0 else -2)
    g.setflag("eval_done")
    if score >= 12:
        res, bonus = "优秀", 600
        g.run_eff(["rep:+8", "trust:wen:+1"])
    elif score >= 6:
        res, bonus = "合格", 250
        g.run_eff(["rep:+3"])
    else:
        res, bonus = "需要整改", 0
        g.run_eff(["rep:-5"])
        if s["kcap"] > 6:
            s["kcap"] = 6
            over = s["collection"][6:]
            for pid in over:
                s["collection"].remove(pid)
                s["plants"][pid]["zone"] = "A"
                g.hist(s["plants"][pid], "收藏温室缩小，搬回了主温室")
            g.log("评估结果不好。收藏温室的一半被划给了仓库，只剩 6 个位置。" + ("多出来的植物搬回了主温室。" if over else ""))
    if res != "需要整改" and s["kcap"] < ZONES["K"]["cap"]:
        s["kcap"] = ZONES["K"]["cap"]
        g.log("收藏温室恢复了原来的大小。")
    s["bonus"] += bonus
    s.setdefault("evals", []).append([s["day"], res, score])
    g.log(f"📋 年度评估：{res}（研究报告 {reps} 篇，解释的异常 {expl} 个，图鉴性状 {traits} 条，温室植株平均健康 {hp:.0f}）。"
          + (f"下次拨款加 {bonus} 元。" if bonus else ""))


def _sp_heater(g, arg):
    s = g.s
    if arg == "rescue":
        moved = 0
        for p in g.zone_plants("B"):
            if g.genus(p)["temp"][0] >= 15:
                for z in ("N", "K"):
                    if g.zone_count(z) < g.zcap(z):
                        p["zone"] = z
                        g.hist(p, f"锅炉坏了，临时搬到{ZONES[z]['name']}")
                        moved += 1
                        break
        g.say(f"你和小满搬了一上午，挪走了 {moved} 盆怕冷的。")
        g.setflag("heater_broken")
    elif arg == "heaters":
        g.say("电暖器嗡嗡地响了一夜，热带温室守住了十八度。主温室还是冷。")
        g.setflag("heater_broken")
        g.setflag("heaters_b")
    else:
        g.setflag("heater_broken")
        g.say("你等着。")
    s.setdefault("timers", []).append([s["day"] + 2, "unflag:heater_broken"])
    s["timers"].append([s["day"] + 2, "unflag:heaters_b"])


def _sp_mo_borrow(g, arg):
    cands = [p for p in g.s["plants"].values() if p["alive"] and "Aeris" in p["genome"]["genus"]
             and p["stage"] in ("mature", "flowering", "fruiting") and p["id"] not in g.s["collection"]]
    if not cands:
        return
    p = cands[0]
    p["stage"] = "lent"
    p["flower"] = None
    p["fruit"] = None
    g.hist(p, "借给莫博士做声学实验")
    g.s["lent"] = p["id"]
    g.setflag("mo_borrowed")
    g.say(f"莫博士小心翼翼地抱走了 {g.pname(p)}，像抱着一只猫。")


def _sp_mo_return(g, arg):
    pid = g.s.get("lent")
    if pid and pid in g.s["plants"]:
        p = g.s["plants"][pid]
        p["stage"] = "mature"
        p["zone"] = "A" if g.zone_count("A") < g.zcap("A") else "N"
        g.hist(p, "从莫博士那里还回来了，叶子上贴着一个小小的传感器贴片")
        g.say(f"莫博士把 {g.pname(p)} 还回来了，叶子上还贴着一个小小的传感器贴片。他塞给你一份论文草稿。")
    g.s["lent"] = None


def _sp_old_lot(g, arg):
    sid = max(g.s["lots"])
    g.s["lots"][sid]["viab"] = 0.35
    g.s["lots"][sid]["note"] = "1998 年的种子，活力很低"


def _sp_year_review(g, arg):
    s = g.s
    yr = (s["day"] - 1) // YEAR_LEN + 1
    st = s["stats"]
    g.log(f"📔 第 {yr} 年结束了。这一年：播种 {st['sown']} 粒，出苗 {st['germ']} 株，授粉 {st['crosses']} 次，采种 {st['harvests']} 次，"
          f"死亡 {st['died']} 株，观察记录 {st['observed']} 次，写了 {st['reports']} 篇报告。图鉴里有 {len(s['catalog']['traits'])} 种性状表现，"
          f"收藏温室里 {len(s['collection'])} 株，标本 {len(s['herbarium'])} 份。")
    g.log("研究所的日子还在继续。明天是新一年的春天。")


def _sp_mark_day(g, arg):
    g.s[arg] = g.s["day"]


SPECIALS = {
    "mark_day": _sp_mark_day, "mixup": _sp_mixup, "audit": _sp_audit, "cert": _sp_cert, "spend": _sp_spend, "seedbank_hit": _sp_seedbank_hit,
    "corridor": _sp_corridor, "radio_to": _sp_radio_to, "openday_collection": _sp_openday_collection,
    "openday_sell": _sp_openday_sell, "evaluation": _sp_evaluation, "heater": _sp_heater, "mo_borrow": _sp_mo_borrow,
    "mo_return": _sp_mo_return, "old_lot": _sp_old_lot, "year_review": _sp_year_review,
}

EVENTS.append({"id": "e_radio_move", "day": None, "at": "never", "choice": {
    "text": "走廊改造要开工了。老岑提着收音机问你：「这个挂哪儿？」",
    "opts": [{"label": f"挂到{ZONES[z]['name']}", "need": [], "eff": [f"special:radio_to:{z}"]} for z in ("A", "B", "C", "N")]
    + [{"label": "让它撤走", "need": [], "eff": ["special:radio_to:none", "log:收音机撤走了。"]}]}})
EVENT_BY_ID["e_radio_move"] = EVENTS[-1]


# ───────── 查找 ─────────
def _norm(x):
    return x.strip()


def find_plant(g, q, alive=True):
    q = _norm(q).upper()
    if not q:
        return None, "要写植株编号，比如 P0003。"
    if re.fullmatch(r"P?\d{1,4}", q):
        q = "P" + q.lstrip("P").zfill(4)
    p = g.s["plants"].get(q)
    if not p:
        for x in g.s["plants"].values():
            if x["name"] and x["name"] == _norm(q):
                p = x
                break
    if not p:
        return None, f"没有植株「{q}」。（plants 看列表）"
    if alive and (not p["alive"] or p["stage"] in ("gone", "lent")):
        return None, f"{p['id']} 已经不在了（{STAGE_CN.get(p['stage'], p['stage'])}）。"
    return p, None


def find_zone(q):
    q = _norm(q)
    if q.upper() in ZONES:
        return q.upper()
    for z, d in ZONES.items():
        if q == d["name"]:
            return z
    return None


def find_npc(g, q, need_present=True):
    q = _norm(q).lower()
    for nid, d in NPCS.items():
        if q == nid or q in [a.lower() for a in d["alias"]]:
            if need_present and not g.present(nid):
                return None, f"{d['name']}现在不在。（people 看今天谁在）"
            return nid, None
    return None, f"所里没有「{q}」这个人。"


def find_topic(q):
    q = _norm(q).lower()
    for t, al in TOPICS.items():
        if q == t or q in [a.lower() for a in al]:
            return t
    return None


TRAIT_CN = {"leaf": "叶色", "height": "株高", "stem": "茎秆", "flower": "花色", "scent": "香气", "bloom": "花期",
            "cold": "耐寒表现", "drought": "耐旱表现", "shade": "耐阴表现", "sound": "声响应", "seeds": "结籽",
            "health": "健康"}


def find_trait(q):
    q = _norm(q).lower()
    for k, v in TRAIT_CN.items():
        if q == k or q == v or q == v[:2]:
            return k
    return None


# ───────── 指令 ─────────
HELP = """【不太正常的植物研究所】你是新来的植物研究员。每天 8 小时工时（08:00—16:00），大部分动作都要花时间，end 结束这一天。
用法：greenhouse_lab.cmd("指令")；多条用 ; 隔开，一次最多 10 条（遇到要你决定的事、或一天结束时自动停下）。
植株写编号（P0003 或 3），批次 S001，杂交实验 X001，花粉 Q001，组培瓶 F001，温室 A/B/C/N/D/K。
 看    status｜zones｜zone <区>｜plants [区|all|dead|<品系>]｜plant <株>｜tree <株>｜people｜npc <人>｜supplies
 观察  observe <株|区>（每株 5 分，记录当下看得见的性状）｜test <株> <位点>（分子标记，60 分，耗试剂）
 记录  lots｜lot <批次>｜exp [实验]｜ratio <实验|批次>[+<实验>…] <性状>（统计分离比+卡方）｜select <实验|批次> <性状> <表现>
       catalog [traits|anomalies|lines]｜docs｜read <文件>｜log [天]｜note <文字>｜notes｜mark <株> <文字>（标记可疑）
 栽培  sow <批次> <粒数> [区]｜water <株|区>｜feed <株|区>｜prune <株>｜repot <株> S|M|L｜treat <株|区> <方法>
       move <株> <区>｜cut <株>（扦插/分株）｜culture <株> [double]（组培/秋水仙素加倍）｜flasks｜transplant <瓶>
       discard <株>（淘汰，记录保留）｜dump <批次>（清掉剩余种子，记录保留）
 育种  cross <母本> <父本株|花粉>｜self <株>｜bag/unbag <株>（套袋防止自然授粉）｜pollen <株>（采花粉）｜harvest <株>
 环境  set <区> temp <℃>｜set <区> light <小时|0>｜set <区> radio on|off｜set <区> nightbreak on|off
 收藏  keep <株>（搬进私人收藏温室）｜collection｜diary <株> <文字>｜name <株> <名字>｜tag <株> <标签>｜press <株>
 人    talk <人>｜ask <人> <话题>｜give <株> <人>｜write lin
 经营  shop｜buy <物资> [数量]｜upgrade <设备>｜report <实验>｜report anomaly <异常>
 探索  open D｜search <区>
 时间  end [天数]（结束今天；多天最多 7 天，期间没人照料）｜choose <编号>
种子库里的批次就是你的材料；表型要靠 observe 一株一株记下来，图鉴和统计只用你记下来的数据。"""


def c_help(g, a):
    g.say(HELP)


def c_status(g, a):
    s = g.s
    out_t, daylen = outside(s["day"])
    g.say(f"第 {s['day']} 天（第 {(s['day'] - 1) // YEAR_LEN + 1} 年 {season_of(s['day'])}季），{hm(s['min'])}，今天还剩 {g.left()} 分钟工时。"
          f"室外 {out_t:.0f}℃，日照 {daylen:.1f} 小时。")
    g.say(f"经费 {s['funds']} 元｜研究声誉 {s['rep']}｜下次拨款：第 {((s['day'] - 1) // GRANT_EVERY + 1) * GRANT_EVERY + 1} 天"
          + (f"（已攒报告奖励 {s['bonus']}）" if s["bonus"] else ""))
    for z in ZONES:
        if s["zones"][z]["locked"]:
            continue
        ps = g.zone_plants(z)
        e = g.zone_env(z)
        flags = []
        if e["radio"]:
            flags.append("收音机")
        if s["zones"][z]["nb"] and g.up("nblamp"):
            flags.append("夜间补光")
        g.say(f"  {z} {ZONES[z]['name']}：{len(ps)}/{g.zcap(z)} 株，{e['temp']:.0f}℃，日照 {e['daylen']:.1f}h" + (f"，{'、'.join(flags)}" if flags else ""))
    need = []
    for p in s["plants"].values():
        if not p["alive"] or p["stage"] in ("seed", "gone", "lent") or p["zone"] == "K":
            continue
        if p["water"] < 25:
            need.append(f"{p['id']} 缺水")
        if p["pests"]:
            need.append(f"{p['id']} 有虫病")
        if p["fruit"] and p["fruit"]["ok"] and s["day"] >= p["fruit"]["ready"]:
            need.append(f"{p['id']} 可以采种")
        if p["zone"] == "N" and p["age"] > 14:
            need.append(f"{p['id']} 该移出育苗室")
    if need:
        g.say("需要留意：" + "；".join(need[:15]) + ("……" if len(need) > 15 else ""))
    if s["pending"]:
        g.say("❗ 有一件事等你决定（choose <编号>）。")


def c_zones(g, a):
    for z, d in ZONES.items():
        zs = g.s["zones"][z]
        if zs["locked"]:
            g.say(f"{z} {d['name']}：锁着。")
            continue
        e = g.zone_env(z)
        g.say(f"{z} {d['name']}（{len(g.zone_plants(z))}/{g.zcap(z)}）：{e['temp']:.0f}℃，湿度 {d['hum']}%，光照 {'强' if d['light'] >= 1 else '中' if d['light'] >= 0.8 else '弱'}，日照 {e['daylen']:.1f}h"
              + ("，收音机开着" if e["radio"] else ""))


def c_zone(g, a):
    z = find_zone(a[0]) if a else None
    if not z:
        return c_zones(g, a)
    d = ZONES[z]
    zs = g.s["zones"][z]
    if zs["locked"]:
        g.say(f"{d['name']}：{d['desc']}")
        return
    e = g.zone_env(z)
    g.say(f"【{z} {d['name']}】{d['desc']}")
    g.say(f"  温度 {e['temp']:.0f}℃（设定 {zs['temp'] if zs['temp'] is not None else '不加热'}）｜湿度 {d['hum']}%｜日照 {e['daylen']:.1f}h"
          + (f"（补光设定 {zs['photo']}h）" if zs["photo"] else "（自然光）") + ("｜收音机开着" if e["radio"] else "")
          + ("｜夜间补光" if zs["nb"] and g.up("nblamp") else ""))
    _plant_table(g, g.zone_plants(z))


def _short(p, g):
    o = p["obs"]
    bits = []
    for t in ("flower", "leaf", "height", "stem"):
        if t in o:
            bits.append(o[t][1].split("，")[0] if t != "height" else o[t][1].split("（")[0])
    if not o:
        bits.append("（还没观察过）")
    return "、".join(bits)


def _plant_table(g, plants):
    if not plants:
        g.say("  （没有植株）")
        return
    for p in plants:
        st = STAGE_CN.get(p["stage"], p["stage"])
        extra = []
        if p["stage"] == "flowering" and p["flower"]:
            if GN.needs_nightbreak(p["genome"]) and not p["flower"]["open"]:
                extra.append("花苞未开")
            if p["bag"]:
                extra.append("套袋")
        if p["fruit"]:
            extra.append(f"果实 {p['fruit']['xid']}")
        if p["water"] < 25 and p["stage"] not in ("seed",) and p["alive"]:
            extra.append("缺水")
        if p["pests"]:
            extra.append("有虫病")
        if p["doubt"]:
            extra.append("来源存疑")
        lab = p.get("label", "")
        disp = lab if p.get("gen", 0) == 0 and lab else f"{g.gname(p)} {lab}"
        g.say(f"  {g.pname(p)}  {disp}｜{st}｜健康 {p['health']:.0f}"
              + (f"｜{'，'.join(extra)}" if extra else "") + f"｜{_short(p, g)}")


def c_plants(g, a):
    s = g.s
    arg = a[0] if a else ""
    z = find_zone(arg) if arg else None
    if z:
        ps = g.zone_plants(z)
    elif arg in ("dead", "死亡", "失败"):
        ps = [p for p in s["plants"].values() if not p["alive"]]
    elif arg in ("all", "全部"):
        ps = list(s["plants"].values())
    elif arg:
        ps = [p for p in s["plants"].values() if p["alive"] and (p["line"] == arg.upper() or arg in g.gname(p) or p.get("lot") == arg.upper()
                                                                 or p.get("xid") == arg.upper() or arg in p["tags"])]
    else:
        ps = [p for p in s["plants"].values() if p["alive"] and p["stage"] not in ("gone", "lent")]
    g.say(f"共 {len(ps)} 株" + ("（只列出前 60 株）" if len(ps) > 60 else "") + "：")
    by = {}
    for p in ps[:60]:
        by.setdefault(p["zone"], []).append(p)
    for zz, lst in by.items():
        g.say(f"【{ZONES[zz]['name'] if zz in ZONES else zz}】")
        if arg in ("dead", "死亡", "失败", "all", "全部"):
            for p in lst:
                d = p["death"]
                g.say(f"  {g.pname(p)} {g.gname(p)} {p.get('label', '')}｜{STAGE_CN.get(p['stage'], p['stage'])}"
                      + (f"｜第 {d[0]} 天，{d[1]}" if d else ""))
        else:
            _plant_table(g, lst)


def _origin(g, p):
    s = g.s
    if p.get("xid"):
        x = s["crosses"].get(p["xid"])
        f = x["father"] if x else "?"
        ftxt = "父本不明（开放授粉）" if f == "open" else "自交" if x and x["kind"] == "self" else f"♂ {f}"
        return f"{p['xid']}：♀ {x['mother'] if x else '?'} × {ftxt}，批次 {p.get('lot')}"
    if p.get("how") in ("扦插", "组培"):
        return f"{p['how']}自 {p.get('mother')}"
    return p.get("src", "")


def c_plant(g, a):
    p, err = find_plant(g, a[0] if a else "", alive=False)
    if not p:
        g.say(err)
        return
    s = g.s
    lines = [f"【{g.pname(p)}】{g.gname(p)}｜{p.get('label', '')}｜{STAGE_CN.get(p['stage'], p['stage'])}"
             + (f"｜在{ZONES[p['zone']]['name']}" if p["zone"] in ZONES and p["alive"] else "")]
    lines.append(f"  来源：{_origin(g, p)}" + ("（⚠ 来源存疑）" if p["doubt"] else ""))
    lines.append(f"  祖先品系：{'、'.join(LINES[x]['name'] for x in p.get('anc', []) if x in LINES) or '—'}")
    if p["alive"] and p["stage"] not in ("seed",):
        lines.append(f"  健康 {p['health']:.0f}｜盆土湿度 {p['water']:.0f}｜养分 {p['food']:.0f}｜{POT_CN[p['pot']]}｜株高约 {p['size']:.0f} cm｜发芽后 {p['age']} 天"
                     + (f"｜已开花 {p['blooms']} 次" if p["blooms"] else "") + ("｜套袋中" if p["bag"] else ""))
    elif p["stage"] == "seed":
        lines.append(f"  第 {p['born']} 天播下，还没出苗。")
    if p["death"]:
        lines.append(f"  第 {p['death'][0]} 天：{p['death'][1]}")
    if p["obs"]:
        lines.append("  最近一次观察记录：")
        for t, (k, txt, d) in p["obs"].items():
            if t in TRAIT_CN or t in ("fruit", "pests"):
                lines.append(f"    {TRAIT_CN.get(t, {'fruit': '果实', 'pests': '病虫'}.get(t, t))}：{txt}（第 {d} 天）")
    else:
        lines.append("  还没有观察记录。（observe）")
    if p["tests"]:
        lines.append("  分子检测：" + "，".join(f"{l} = {v}" for l, v in p["tests"].items()))
    if len(p["streaks"]) > 1:
        lines.append("  历次花期的条纹数：" + "、".join(map(str, p["streaks"])))
    if p["tags"]:
        lines.append("  标签：" + "、".join(p["tags"]))
    for m in p["marks"]:
        lines.append(f"  ⚑ 第 {m[0]} 天标记：{m[1]}")
    for d in p["diary"][-5:]:
        lines.append(f"  ✎ 第 {d[0]} 天：{d[1]}")
    lines.append("  经历：" + "；".join(f"第{d}天 {t}" for d, t in p["hist"][-10:]))
    g.say(*lines)


def c_tree(g, a):
    p, err = find_plant(g, a[0] if a else "", alive=False)
    if not p:
        g.say(err)
        return
    s = g.s

    def node(pid_or_ref, depth, prefix):
        if depth > 4:
            return
        if pid_or_ref in s["plants"]:
            q = s["plants"][pid_or_ref]
            ob = q["obs"].get("flower") or q["obs"].get("leaf")
            g.say(f"{prefix}{g.pname(q)} {q.get('label', '')} {g.gname(q)}" + (f"｜{ob[1].split('，')[0]}" if ob else "") + ("" if q["alive"] else "（†）"))
            if q.get("xid"):
                x = s["crosses"].get(q["xid"])
                if x:
                    node(x["mother"], depth + 1, prefix + "  ♀ ")
                    f = x["father"]
                    if f == "open":
                        g.say(prefix + "  ♂ 不明（开放授粉）")
                    elif x["kind"] == "self":
                        g.say(prefix + "  ♂ （自交）")
                    elif f.startswith("Q") and f in s["pollen"]:
                        node(s["pollen"][f]["src"], depth + 1, prefix + "  ♂ ")
                    else:
                        node(f, depth + 1, prefix + "  ♂ ")
            elif q.get("how") in ("扦插", "组培") and q.get("mother"):
                node(q["mother"], depth + 1, prefix + "  ⤷ ")
            else:
                g.say(f"{prefix}  └ {q.get('src', '')}")
        else:
            g.say(f"{prefix}{pid_or_ref}")
    node(p["id"], 0, "")


def c_lots(g, a):
    s = g.s
    if not s["lots"]:
        g.say("种子库是空的。")
        return
    cap = SEEDBANK_CAP + (40 if g.up("seedbank2") else 0)
    live = [l for l in s["lots"].values() if l["seeds"]]
    g.say(f"🌰 种子库（{len(live)}/{cap} 个批次有种子）：")
    for l in s["lots"].values():
        if not l["seeds"] and not (a and a[0] == "all"):
            continue
        g.say(f"  {l['id']} {_lot_name(g, l)}｜剩 {len(l['seeds'])}/{l['n0']} 粒｜活力约 {int(l['viab'] * 100)}%｜第 {l['day']} 天入库")
    if not (a and a[0] == "all"):
        g.say("（lots all 连用完的批次一起看）")


def _lot_name(g, l):
    if l.get("xid"):
        x = g.s["crosses"][l["xid"]]
        f = "开放授粉" if x["father"] == "open" else "自交" if x["kind"] == "self" else f"× {x['father']}"
        return f"{l['label']}（{l['xid']}：{x['mother']} {f}）"
    return f"{LINES[l['line']]['name']}［{l['line']}］" + ("野生种群" if LINES[l["line"]].get("wild") else "品系")


def c_lot(g, a):
    sid = a[0].upper() if a else ""
    l = g.s["lots"].get(sid)
    if not l:
        g.say("没有这个批次。（lots）")
        return
    g.say(f"【{sid}】{_lot_name(g, l)}", f"  来源：{l['src']}", f"  第 {l['day']} 天入库，原有 {l['n0']} 粒，剩 {len(l['seeds'])} 粒，活力约 {int(l['viab'] * 100)}%"
          + (f"（{l['note']}）" if l.get("note") else ""))
    kids = [p for p in g.s["plants"].values() if p.get("lot") == sid]
    if kids:
        _summary(g, kids)


def _summary(g, kids):
    g.say(f"  播下 {len(kids)} 粒：" + "，".join(f"{STAGE_CN[k]} {v}" for k, v in _counter(p["stage"] for p in kids).items()))
    for t in ("leaf", "flower", "height", "stem", "scent", "cold", "sound"):
        c = _counter(p["obs"][t][1].split("（")[0] if t != "height" else p["obs"][t][1].split("（")[1].rstrip("）")
                     for p in kids if t in p["obs"])
        if c:
            g.say(f"  已观察{TRAIT_CN[t]}：" + "，".join(f"{k} {v}" for k, v in c.items()))
    doubt = sum(1 for p in kids if p["doubt"])
    if doubt:
        g.say(f"  ⚠ 其中 {doubt} 株来源存疑。")


def _counter(it):
    d = {}
    for x in it:
        d[x] = d.get(x, 0) + 1
    return dict(sorted(d.items(), key=lambda kv: -kv[1]))


def c_exp(g, a):
    s = g.s
    if not a:
        if not s["crosses"]:
            g.say("还没有做过授粉实验。")
            return
        g.say("🧫 授粉实验：")
        for x in s["crosses"].values():
            f = "开放授粉" if x["father"] == "open" else "自交" if x["kind"] == "self" else x["father"]
            g.say(f"  {x['id']} 第 {x['day']} 天｜♀ {x['mother']} × {f}｜{x['status']}" + (f"｜批次 {x['lot']}" if x["lot"] else "")
                  + ("｜已写报告" if x["report"] else ""))
        return
    xid = a[0].upper()
    x = s["crosses"].get(xid)
    if not x:
        g.say("没有这个实验编号。")
        return
    f = "开放授粉（父本不明）" if x["father"] == "open" else "自交" if x["kind"] == "self" else x["father"]
    g.say(f"【{xid}】第 {x['day']} 天｜♀ {x['mother']} × ♂ {f}｜{x['status']}" + ("｜远缘杂交" if x["wide"] else ""))
    for n in x["notes"]:
        g.say(f"  ✎ {n}")
    if x["lot"]:
        kids = [p for p in s["plants"].values() if p.get("xid") == xid]
        g.say(f"  种子批次 {x['lot']}，剩 {len(s['lots'][x['lot']]['seeds'])} 粒。")
        if kids:
            _summary(g, kids)


def _offspring(g, ref):
    ref = ref.upper()
    s = g.s
    if "+" in ref:
        kids = []
        for r in ref.split("+"):
            k, _ = _offspring(g, r)
            if k is None:
                return None, ref
            kids += [p for p in k if p not in kids]
        return kids, ref
    if ref in s["crosses"]:
        return [p for p in s["plants"].values() if p.get("xid") == ref], ref
    if ref in s["lots"]:
        return [p for p in s["plants"].values() if p.get("lot") == ref], ref
    return None, ref


def _cat_key(p, t):
    k, txt, _ = p["obs"][t]
    if t == "height":
        return txt.split("（")[1].rstrip("）")
    if t == "flower":
        base = txt.split("，")[0]
        return base + ("（带条纹）" if "+streak" in k else "")
    if t == "leaf":
        return txt.split("（")[0].replace("约 ", "")
    return txt.split("（")[0]


def c_ratio(g, a):
    if len(a) < 2:
        g.say("用法：ratio <实验或批次> <性状>（几个实验合并统计：ratio X003+X004 花色），性状：" + "、".join(f"{v}({k})" for k, v in TRAIT_CN.items() if k != "health"))
        return
    kids, ref = _offspring(g, a[0])
    if kids is None:
        g.say("没有这个实验或批次。")
        return
    t = find_trait(a[1])
    if not t:
        g.say("不认识这个性状。可以用：" + "、".join(f"{v}({k})" for k, v in TRAIT_CN.items()))
        return
    obs = [p for p in kids if t in p["obs"]]
    if t == "leaf":
        obs = [p for p in obs]
    if not obs:
        g.say(f"{ref} 的后代里还没有人记录过{TRAIT_CN[t]}。（先 observe）")
        return
    c = _counter(_cat_key(p, t) for p in obs)
    tot = sum(c.values())
    g.say(f"📈 {ref} 后代的{TRAIT_CN[t]}（已观察 {tot} 株，共 {len(kids)} 株）：")
    for k, v in c.items():
        g.say(f"  {k}：{v}（{v / tot:.0%}）")
    doubt = sum(1 for p in obs if p["doubt"])
    if doubt:
        g.say(f"  ⚠ 其中 {doubt} 株来源存疑。")
    counts = sorted(c.values(), reverse=True)
    fits = GN.fit_ratios(counts)
    if len(c) == 1:
        g.say("  只有一种表现。")
    elif fits:
        g.say("  和常见分离比的卡方检验（p 越大越吻合，p < 0.05 通常认为不符合）：")
        for name, chi, p in fits[:4]:
            g.say(f"    {name:8s} χ²={chi:6.2f}  p={p:.3f}" + ("  ←" if p == fits[0][2] and p >= 0.05 else ""))
    else:
        g.say("  类别太多，没有现成的比例可比。")
    if tot < REPORT_MIN:
        g.say(f"  （样本只有 {tot} 株，少于 {REPORT_MIN} 株，结论不太可靠。）")
    _anomaly_from_ratio(g, ref, t, c, kids)


def _anomaly_from_ratio(g, ref, t, c, kids):
    if t == "leaf" and sum(c.values()) >= 10:
        anc = set()
        for p in kids:
            anc.update(p.get("anc", []))
        gen2 = all(p.get("gen", 0) >= 2 for p in kids)
        if "CUP-LIN" in anc and ({"CUP-1", "CUP-H"} & anc) and gen2 and len(c) == 1 and "墨铜" in next(iter(c)):
            g.set_anomaly("bronze", 2)
    g.check_chimera()


def c_select(g, a):
    if len(a) < 3:
        g.say("用法：select <实验或批次> <性状> <表现关键词>，比如 select X003 花色 淡紫")
        return
    kids, ref = _offspring(g, a[0])
    t = find_trait(a[1])
    if kids is None or not t:
        g.say("实验/批次或性状不对。")
        return
    kw = " ".join(a[2:])
    hit = [p for p in kids if t in p["obs"] and kw in p["obs"][t][1] and p["alive"]]
    g.say(f"{ref} 后代中{TRAIT_CN[t]}含「{kw}」、还活着的：{len(hit)} 株")
    _plant_table(g, hit)


def c_catalog(g, a):
    s = g.s
    cat = s["catalog"]
    sub = a[0] if a else ""
    if sub in ("anomalies", "异常"):
        if not cat["anomalies"]:
            g.say("异常记录还是空的。")
            return
        for aid, st in cat["anomalies"].items():
            title, seen, why = ANOMALIES[aid]
            g.say(f"❓ {title}［{aid}］——{'已解释' if st >= 2 else '观察到，原因不明'}", f"   {seen}")
            if st >= 2:
                g.say(f"   {why}")
        return
    if sub in ("lines", "品系"):
        g.say(f"📚 见过的品系 {len(cat['lines'])}/{len([k for k, v in LINES.items() if not v.get('hidden')])}+：")
        for l in cat["lines"]:
            g.say(f"  {l} {LINES[l]['name']}——{LINES[l]['note']}")
        return
    if sub in ("traits", "性状"):
        by = {}
        for key, (d, pid, txt) in cat["traits"].items():
            t = key.split(":")[0]
            by.setdefault(t, []).append(f"{txt}（{pid}，第{d}天）")
        g.say(f"📗 图鉴：观察到的性状表现 {len(cat['traits'])} 种")
        for t, lst in by.items():
            g.say(f"【{TRAIT_CN.get(t, t)}】" + "；".join(lst))
        return
    g.say(f"📗 图鉴：属 {len(cat['genera'])}/{len(GENERA)}，品系 {len(cat['lines'])}，性状表现 {len(cat['traits'])} 种，异常记录 {len(cat['anomalies'])} 条，标本 {len(s['herbarium'])} 份。")
    for gname in cat["genera"]:
        G = GENERA[gname]
        n = sum(1 for k, v in cat["traits"].items() for p in [s["plants"].get(v[1])] if p and gname in p["genome"]["genus"])
        g.say(f"  {G['name']}（{gname}）——{G['look']}｜记录了 {n} 种表现")
    g.say("（catalog traits｜catalog anomalies｜catalog lines）")


def c_docs(g, a):
    if not g.s["docs"]:
        g.say("你手上还没有文件。")
    for d in g.s["docs"]:
        g.say(f"  {d}：{DOCS[d][0]}")


def c_read(g, a):
    d = a[0] if a else ""
    if d not in g.s["docs"]:
        g.say("你没有这份文件。（docs）")
        return
    title, text = DOCS[d]
    g.say(f"📄 {title}", text)
    g.spend(10)
    if d == "lin_p1":
        for p in g.s["plants"].values():
            if len(set(p["streaks"])) >= 2 and "streak" in g.s["catalog"]["anomalies"]:
                g.set_anomaly("streak", 2)
                break
    if d == "mo_draft" and "lean" in g.s.get("sound_seen", []):
        g.set_anomaly("sound", 2)
    if d == "lin_p5":
        g.say("（这页纸的最后一句，你看了两遍。）")


def c_log(g, a):
    try:
        d = int(a[0]) if a else g.s["day"]
    except ValueError:
        d = g.s["day"]
    lines = [t for k, t in g.s["log"] if k == d or (not a and k == d - 1)]
    g.say(f"🗒️ 第 {d} 天的记录：" if lines else "那天没有记录。")
    for t in lines[:60]:
        g.say("  " + t)


def c_note(g, a):
    if not a:
        return c_notes(g, a)
    g.s["notes"].append([g.s["day"], " ".join(a)[:400]])
    g.say("记在实验记录本上了。")


def c_notes(g, a):
    if not g.s["notes"]:
        g.say("记录本上还没有你写的东西。")
    for d, t in g.s["notes"][-40:]:
        g.say(f"  第{d}天：{t}")


def c_mark(g, a):
    if len(a) < 2:
        g.say("用法：mark <株> <文字>，比如 mark P0031 叶色和兄弟株都不一样，疑似突变")
        return
    p, err = find_plant(g, a[0], alive=False)
    if not p:
        g.say(err)
        return
    p["marks"].append([g.s["day"], " ".join(a[1:])[:200]])
    g.say(f"⚑ 已在 {p['id']} 的档案上做了标记。")


def _cost(g, m):
    if g.left() < m:
        g.say(f"今天剩下的工时不够了（需要 {m} 分钟，还剩 {g.left()} 分钟）。end 结束今天。")
        return False
    return True


def c_observe(g, a):
    if not a:
        g.say("观察哪一株？observe <株> 或 observe <区>（区里每株都看一遍）")
        return
    z = find_zone(a[0])
    if z:
        ps = [p for p in g.zone_plants(z) if p["stage"] not in ("seed",)]
        if not ps:
            g.say("那里没有可以观察的植株。")
            return
        m = 5 * len(ps)
        if g.left() < 5:
            g.say("今天没有时间了。")
            return
        can = min(len(ps), g.left() // 5)
        ps = ps[:can]
        g.say(f"🔍 你在{ZONES[z]['name']}里一株一株看过去（{len(ps)} 株，{5 * len(ps)} 分钟）：")
        before = len(g.s["catalog"]["traits"])
        for p in ps:
            v = g.observe(p, quiet=True)
            g.say(f"  {g.pname(p)} {p.get('label', '')}：" + "；".join(txt for t, (k, txt) in v.items() if t not in ("health",)) + f"｜{v.get('health', ('', ''))[1]}")
        g.spend(5 * len(ps))
        newn = len(g.s["catalog"]["traits"]) - before
        if newn:
            g.say(f"  📗 图鉴新增 {newn} 种性状表现。")
        if can < m // 5:
            g.say(f"（时间不够，还有 {m // 5 - can} 株没看。）")
        return
    p, err = find_plant(g, a[0])
    if not p:
        g.say(err)
        return
    if not _cost(g, 5):
        return
    if p["stage"] == "seed":
        g.say(f"{p['id']} 还没出苗。土面是平的。")
        g.spend(5)
        return
    mark = len(g.out)
    v = g.observe(p)
    g.out[mark:mark] = [f"🔍 {g.pname(p)}（{g.gname(p)}，{STAGE_CN[p['stage']]}，{ZONES[p['zone']]['name']}）："] + \
        [f"  {TRAIT_CN.get(t, {'fruit': '果实', 'pests': '病虫'}.get(t, t))}：{txt}" for t, (k, txt) in v.items()]
    if g._newt:
        g.say("  📗 图鉴新增：" + "、".join(g._newt))
    g.spend(5)


def c_test(g, a):
    if len(a) < 2:
        g.say("用法：test <株> <位点>。能检测的位点：" + "、".join(f"{l}({d[3]})" for l, d in GN.LOCI.items() if d[4]))
        return
    p, err = find_plant(g, a[0])
    if not p:
        g.say(err)
        return
    l = a[1]
    if l not in GN.LOCI or not GN.LOCI[l][4]:
        g.say("这个位点没有可用的分子标记。能检测的：" + "、".join(f"{x}({d[3]})" for x, d in GN.LOCI.items() if d[4]))
        return
    if g.s["supplies"]["marker"] < 1:
        g.say("分子标记试剂用完了。（buy marker）")
        return
    if not _cost(g, 60):
        return
    g.s["supplies"]["marker"] -= 1
    res = GN.genotype_text(p["genome"], l)
    p["tests"][l] = res
    g.s["stats"]["tests"] += 1
    g.say(f"🧬 {p['id']} 的 {l}（{GN.LOCI[l][3]}）位点：{res}")
    g.hist(p, f"分子检测 {l} = {res}")
    if l == "O" and "O" in p["genome"]["g"]["O"] and p["obs"].get("scent", [""])[0] == "none":
        g.set_anomaly("scent", 1)
    g.spend(60)


def _sow_zone(g, a):
    z = find_zone(a[2]) if len(a) > 2 else "N"
    return z


def c_sow(g, a):
    s = g.s
    if len(a) < 2:
        g.say("用法：sow <批次> <粒数> [区，默认育苗室 N]")
        return
    lot = s["lots"].get(a[0].upper())
    if not lot:
        g.say("没有这个批次。（lots）")
        return
    try:
        n = int(a[1])
    except ValueError:
        g.say("粒数要写数字。")
        return
    z = _sow_zone(g, a)
    if not z or s["zones"][z]["locked"] or z == "K":
        g.say("不能播在那里。")
        return
    n = min(n, len(lot["seeds"]))
    if n <= 0:
        g.say("这个批次已经没有种子了。")
        return
    room = g.zcap(z) - g.zone_count(z)
    if n > room:
        g.say(f"{ZONES[z]['name']}只剩 {room} 个位置。")
        return
    if s["supplies"]["soil"] < 1 or s["supplies"]["pot_s"] < (n if z != "N" else 0):
        g.say("培养土或小花盆不够了。（supplies / buy）")
        return
    m = 10 + 2 * n
    if not _cost(g, m):
        return
    s["supplies"]["soil"] -= max(1, n // 12)
    if z != "N":
        s["supplies"]["pot_s"] -= n
    env = g.zone_env(z)
    ids = []
    for _ in range(n):
        gen = lot["seeds"].pop(0)
        lot["used"] += 1
        G = GENERA[gen["genus"].split("×")[0]]
        tf = 1.0 if G["temp"][0] - 2 <= env["temp"] <= G["temp"][1] + 2 else 0.5
        v = lot["viab"] * tf * (0.5 if GN.is_wide_hybrid(gen) else 1.0)
        meta = {k: lot.get(k) for k in ("xid", "mother", "father", "gen", "label", "anc")}
        meta.update({"line": lot["line"], "lot": lot["id"], "src": f"播种自 {lot['id']}", "how": "播种"})
        p = g.new_plant(gen, z, meta)
        p["germ_day"] = s["day"] + G["germ"] + (2 if tf < 1 else 0) + g.rng.randint(0, 2)
        p["germ_ok"] = g.rng.random() < v
        ids.append(p["id"])
    s["stats"]["sown"] += n
    gs = GENERA[s["plants"][ids[0]]["genome"]["genus"].split("×")[0]]["germ"]
    g.say(f"🌱 从 {lot['id']} 取了 {n} 粒" + ("（用完了）" if not lot["seeds"] else f"（还剩 {len(lot['seeds'])} 粒）")
          + f"，播在{ZONES[z]['name']}：{ids[0]}—{ids[-1]}。大约 {gs} 天出苗。")
    g.spend(m)


def _targets(g, arg):
    z = find_zone(arg)
    if z:
        return [p for p in g.zone_plants(z) if p["stage"] != "seed" or True], True
    p, err = find_plant(g, arg)
    if not p:
        g.say(err)
        return None, False
    return [p], False


def c_water(g, a):
    if not a:
        g.say("water <株> 或 water <区>")
        return
    ps, zone = _targets(g, a[0])
    if ps is None:
        return
    m = 20 if zone else 3
    if not _cost(g, m):
        return
    for p in ps:
        p["water"] = min(100.0, p["water"] + 55)
    g.say(f"💧 浇了 {len(ps)} 盆。" + ("（浇得太勤会烂根，盆土湿度可以在 plant 里看）" if any(p["water"] > 95 for p in ps) else ""))
    g.spend(m)


def c_feed(g, a):
    if not a:
        g.say("feed <株> 或 feed <区>")
        return
    ps, zone = _targets(g, a[0])
    if ps is None:
        return
    need = max(1, len(ps) // 6)
    if g.s["supplies"]["nutrient"] < need:
        g.say("营养液不够了。（buy nutrient）")
        return
    m = 25 if zone else 5
    if not _cost(g, m):
        return
    g.s["supplies"]["nutrient"] -= need
    for p in ps:
        p["food"] = min(100.0, p["food"] + 50)
    g.say(f"🧴 给 {len(ps)} 盆施了营养液（用掉 {need} 瓶）。")
    g.spend(m)


def c_prune(g, a):
    p, err = find_plant(g, a[0] if a else "")
    if not p:
        g.say(err)
        return
    if not _cost(g, 10):
        return
    p["size"] = round(p["size"] * 0.85, 1)
    for k in list(p["pests"]):
        p["pests"][k] -= 1
        if p["pests"][k] <= 0:
            del p["pests"][k]
    p["rootbound"] = False if p["size"] <= POT_CAP[p["pot"]] else p.get("rootbound")
    g.hist(p, "修剪")
    g.say(f"✂️ 修剪了 {p['id']}：剪掉徒长的枝条和发黄的老叶" + ("，顺手剪掉了长虫的部分" if p["pests"] else "") + "。")
    g.spend(10)


def c_repot(g, a):
    if len(a) < 2 or a[1].upper() not in POT_CAP:
        g.say("用法：repot <株> S|M|L")
        return
    p, err = find_plant(g, a[0])
    if not p:
        g.say(err)
        return
    k = a[1].upper()
    key = {"S": "pot_s", "M": "pot_m", "L": "pot_l"}[k]
    if g.s["supplies"][key] < 1 or g.s["supplies"]["soil"] < 1:
        g.say(f"{POT_CN[k]}或培养土不够了。")
        return
    if not _cost(g, 15):
        return
    g.s["supplies"][key] -= 1
    g.s["supplies"]["soil"] -= 1
    p["pot"] = k
    p["rootbound"] = False
    p["health"] = max(0.0, p["health"] - 3)
    g.hist(p, f"换到{POT_CN[k]}")
    g.say(f"🪴 {p['id']} 换进了{POT_CN[k]}。")
    g.spend(15)


def c_treat(g, a):
    if len(a) < 2:
        g.say("用法：treat <株|区> <方法>，方法：soap 肥皂水、bio 瓢虫、fungicide 杀菌剂、pesticide 杀虫剂")
        return
    ps, zone = _targets(g, a[0])
    if ps is None:
        return
    meth = a[1]
    if meth not in ("soap", "bio", "fungicide", "pesticide"):
        g.say("方法：soap、bio、fungicide、pesticide")
        return
    if g.s["supplies"][meth] < 1:
        g.say(f"{SUPPLIES[meth][0]}用完了。")
        return
    m = 30 if zone else 10
    if not _cost(g, m):
        return
    g.s["supplies"][meth] -= 1
    cured = 0
    for p in ps:
        for k in list(p["pests"]):
            if meth in PESTS[k]["treat"]:
                p["pests"][k] -= {"soap": 2, "bio": 3, "fungicide": 4, "pesticide": 5}[meth]
                if p["pests"][k] <= 0:
                    del p["pests"][k]
                    cured += 1
        if meth == "pesticide" and "Aeris" in p["genome"]["genus"]:
            p["health"] = max(0.0, p["health"] - 10)
    g.say(f"🧯 用{SUPPLIES[meth][0]}处理了 {len(ps)} 盆，清掉了 {cured} 处病虫害。")
    g.spend(m)


def c_move(g, a):
    if len(a) < 2:
        g.say("用法：move <株> <区>")
        return
    p, err = find_plant(g, a[0])
    if not p:
        g.say(err)
        return
    z = find_zone(a[1])
    if not z or g.s["zones"][z]["locked"]:
        g.say("没有这个温室，或者它锁着。")
        return
    if z == "K":
        return c_keep(g, a[:1])
    if g.zone_count(z) >= g.zcap(z):
        g.say(f"{ZONES[z]['name']}满了。")
        return
    if not _cost(g, 5):
        return
    if p["zone"] == "N" and p["pot"] == "S" and g.s["supplies"]["pot_s"] >= 1:
        g.s["supplies"]["pot_s"] -= 1
    if p["id"] in g.s["collection"]:
        g.s["collection"].remove(p["id"])
    p["zone"] = z
    g.hist(p, f"搬到{ZONES[z]['name']}")
    g.say(f"{p['id']} 搬到了{ZONES[z]['name']}。")
    g.spend(5)


def c_cut(g, a):
    p, err = find_plant(g, a[0] if a else "")
    if not p:
        g.say(err)
        return
    if not g.genus(p)["cut"]:
        g.say(f"{g.gname(p)}扦插不容易活，所里一般不这么繁殖。（可以试试组培）")
        return
    if p["stage"] not in ("juvenile", "mature", "flowering", "fruiting"):
        g.say("太小了，剪不下来。")
        return
    if g.zone_count("N") >= g.zcap("N"):
        g.say("育苗室满了。")
        return
    if not _cost(g, 20):
        return
    gen = GN.clone(p["genome"])
    if gen["pl"] > 0:  # 嵌合体的插条可能取到全绿或全白的部分
        x = g.rng.random()
        gen["pl"] = 0.0 if x < 0.3 else 1.0 if x < 0.4 else gen["pl"]
    meta = {k: p.get(k) for k in ("line", "lot", "xid", "gen", "label", "anc")}
    meta.update({"mother": p["id"], "father": None, "src": f"扦插自 {p['id']}", "how": "扦插"})
    q = g.new_plant(gen, "N", meta)
    q["germ_day"] = g.s["day"] + 5
    q["germ_ok"] = g.rng.random() < 0.7
    q["label"] = (p.get("label") or "") + "（扦插）"
    g.hist(p, f"剪下插条 {q['id']}")
    g.say(f"✂️ 从 {p['id']} 剪了一段插条，插在育苗室：{q['id']}。大约五天能看出有没有生根。")
    g.spend(20)


def c_culture(g, a):
    p, err = find_plant(g, a[0] if a else "")
    if not p:
        g.say(err)
        return
    dbl = len(a) > 1 and a[1] in ("double", "加倍")
    s = g.s
    if g.flag("lab_closed") and s["day"] < 36:
        g.say("组培室在整改，暂时不能用。")
        return
    if s["supplies"]["agar"] < 1 or (dbl and s["supplies"]["colchicine"] < 1):
        g.say("培养基" + ("或秋水仙素" if dbl else "") + "不够了。")
        return
    if not _cost(g, 45):
        return
    s["supplies"]["agar"] -= 1
    if dbl:
        s["supplies"]["colchicine"] -= 1
    fid = g.new_id("F")
    bad = g.rng.random() < (0.05 if g.up("hood") else 0.18)
    s["flasks"][fid] = {"id": fid, "src": p["id"], "day": s["day"], "ready": s["day"] + 12, "state": "growing",
                        "bad": bad, "double": dbl, "dbl_ok": dbl and g.rng.random() < 0.4, "genome": GN.copy_genome(p["genome"])}
    g.hist(p, f"取外植体做组培（{fid}{'，秋水仙素处理' if dbl else ''}）")
    g.say(f"🧪 从 {p['id']} 切了一小块组织，接种进组培瓶 {fid}" + ("，培养基里加了秋水仙素" if dbl else "") + "。大约十二天后看结果。")
    g.spend(45)


def c_flasks(g, a):
    if not g.s["flasks"]:
        g.say("组培室里没有你的瓶子。")
    for f in g.s["flasks"].values():
        st = {"growing": f"培养中（第 {f['ready']} 天左右）", "ready": "小苗长好了", "contaminated": "污染了", "done": "已移栽"}[f["state"]]
        g.say(f"  {f['id']} 来自 {f['src']}｜{st}" + ("｜秋水仙素" if f["double"] else ""))


def c_transplant(g, a):
    s = g.s
    fid = a[0].upper() if a else ""
    f = s["flasks"].get(fid)
    if not f:
        g.say("没有这个组培瓶。")
        return
    if f["state"] == "contaminated":
        f["state"] = "done"
        g.say(f"{fid} 污染了，只能倒掉。小葛帮你把瓶子泡进了消毒液。")
        return
    if f["state"] != "ready":
        g.say("还没长好。" if f["state"] == "growing" else "已经移栽过了。")
        return
    n = 3
    if g.zone_count("N") + n > g.zcap("N"):
        g.say("育苗室放不下三株小苗。")
        return
    if not _cost(g, 20):
        return
    src = s["plants"].get(f["src"])
    ids = []
    for _ in range(n):
        gen = GN.clone(f["genome"], double=f["dbl_ok"])
        meta = {k: (src.get(k) if src else None) for k in ("line", "lot", "xid", "gen", "label", "anc")}
        meta.update({"mother": f["src"], "father": None, "src": f"组培自 {f['src']}（{fid}）", "how": "组培"})
        q = g.new_plant(gen, "N", meta)
        q["stage"] = "seedling"
        q["germ_day"] = s["day"]
        q["size"] = 2.0
        q["label"] = (meta.get("label") or "") + ("（加倍）" if f["double"] else "（组培）")
        ids.append(q["id"])
    f["state"] = "done"
    g.say(f"🧪 {fid} 的小苗移进了育苗室：{'、'.join(ids)}。" + ("秋水仙素处理过——加倍有没有成功，要等开花结籽才知道。" if f["double"] else ""))
    g.spend(20)


def c_discard(g, a):
    p, err = find_plant(g, a[0] if a else "")
    if not p:
        g.say(err)
        return
    if p["id"] in g.s["collection"]:
        g.say("这株在收藏温室里。真要淘汰的话先 move 出来。")
        return
    g.kill(p, "淘汰（记录保留）")
    g.s["stats"]["died"] -= 1
    g.say(f"🗑️ 淘汰了 {p['id']}。它的档案还在，plants dead 能看到。")
    g.spend(5)


def _flowering_ok(g, p, who):
    if p["stage"] != "flowering" or not p["flower"]:
        g.say(f"{p['id']} 现在没有开花，不能当{who}。")
        return False
    if not p["flower"]["open"]:
        g.say(f"{p['id']} 的花苞没有开，没法授粉。")
        return False
    return True


def c_cross(g, a):
    s = g.s
    if len(a) < 2:
        g.say("用法：cross <母本> <父本株或花粉批次 Qxxx>")
        return
    m, err = find_plant(g, a[0])
    if not m:
        g.say(err)
        return
    if not _flowering_ok(g, m, "母本"):
        return
    if m["fruit"]:
        g.say(f"{m['id']} 这一季已经授过粉了（{m['fruit']['xid']}）。")
        return
    ref = a[1].upper()
    if ref.startswith("Q"):
        q = s["pollen"].get(ref)
        if not q:
            g.say("没有这个花粉批次。")
            return
        life = 30 if g.up("freezer") else 5
        if q["age"] > life:
            g.say(f"{ref} 放了 {q['age']} 天，已经没有活力了。")
            return
        fgen, fpl, src = q["genome"], q["pl"], ref
    else:
        f, err = find_plant(g, a[1])
        if not f:
            g.say(err)
            return
        if f is m:
            return c_self(g, a[:1])
        if not _flowering_ok(g, f, "父本"):
            return
        fgen, fpl, src = f["genome"], f["genome"]["pl"], f["id"]
    if s["supplies"]["bags"] < 1:
        g.say("授粉隔离袋用完了。")
        return
    if not _cost(g, 30):
        return
    s["supplies"]["bags"] -= 1
    c, typ = GN.compat(m["genome"], fgen)
    xid = g.pollinate(m, fgen, src, "cross", fpl)
    m["bag"] = True
    g.hist(m, f"去雄、授粉（{xid}，♂ {src}），套袋")
    note = "两种植物亲缘太远，大概不会成功。" if typ == "none" else "远缘杂交，成功率不高。" if typ == "wide" else ""
    g.say(f"🐝 {xid}：给 {m['id']} 去了雄，用 {src} 的花粉授粉，套上了隔离袋。三天左右能看出有没有坐果。" + note)
    g.spend(30)


def c_self(g, a):
    p, err = find_plant(g, a[0] if a else "")
    if not p:
        g.say(err)
        return
    if not _flowering_ok(g, p, "自交亲本"):
        return
    if p["fruit"]:
        g.say(f"{p['id']} 这一季已经授过粉了。")
        return
    if g.s["supplies"]["bags"] < 1:
        g.say("授粉隔离袋用完了。")
        return
    if not _cost(g, 15):
        return
    g.s["supplies"]["bags"] -= 1
    xid = g.pollinate(p, p["genome"], p["id"], "self", p["genome"]["pl"])
    g.s["crosses"][xid]["kind"] = "self"
    p["bag"] = True
    g.hist(p, f"人工自交（{xid}），套袋")
    g.say(f"🐝 {xid}：{p['id']} 人工自交，套袋。")
    g.spend(15)


def c_bag(g, a):
    p, err = find_plant(g, a[0] if a else "")
    if not p:
        g.say(err)
        return
    if g.s["supplies"]["bags"] < 1:
        g.say("隔离袋用完了。")
        return
    g.s["supplies"]["bags"] -= 1
    p["bag"] = True
    g.say(f"🛍️ {p['id']} 套上了隔离袋，不会被乱授粉了。（这一季花期结束后会取下）")
    g.spend(3)


def c_unbag(g, a):
    p, err = find_plant(g, a[0] if a else "")
    if not p:
        g.say(err)
        return
    p["bag"] = False
    g.say(f"{p['id']} 的隔离袋取下了。")


def c_pollen(g, a):
    p, err = find_plant(g, a[0] if a else "")
    if not p:
        g.say(err)
        return
    if not _flowering_ok(g, p, "花粉来源"):
        return
    if not _cost(g, 15):
        return
    qid = g.new_id("Q")
    g.s["pollen"][qid] = {"id": qid, "src": p["id"], "day": g.s["day"], "age": 0,
                          "genome": GN.copy_genome(p["genome"]), "pl": p["genome"]["pl"]}
    g.hist(p, f"采集花粉 {qid}")
    life = 30 if g.up("freezer") else 5
    g.say(f"🌼 从 {p['id']} 采了花粉，编号 {qid}，能保存大约 {life} 天。")
    g.spend(15)


def c_harvest(g, a):
    s = g.s
    p, err = find_plant(g, a[0] if a else "")
    if not p:
        g.say(err)
        return
    fr = p["fruit"]
    if not fr or not fr["ok"] or s["day"] < fr["set"] + 3:
        g.say(f"{p['id']} 上没有能采的果实。")
        return
    if s["day"] < fr["ready"]:
        g.say(f"果荚还没熟（大约第 {fr['ready']} 天）。")
        return
    cap = SEEDBANK_CAP + (40 if g.up("seedbank2") else 0)
    if sum(1 for l in s["lots"].values() if l["seeds"]) >= cap:
        g.say("种子库满了。用完或清理一些批次再来（种子库的空批次不占位置）。")
        return
    if not _cost(g, 20):
        return
    x = s["crosses"][fr["xid"]]
    G = g.genus(p)
    fgen = x["_fgen"]
    c, typ = GN.compat(p["genome"], fgen)
    n = G["seeds"] * GN.seed_factor(p["genome"]) * (0.5 + p["health"] / 200)
    if typ == "wide":
        n *= 0.15
    if p["genome"].get("dbl"):
        n *= 0.6
    n = max(1, int(round(n * (0.85 + 0.3 * g.rng.random()))))
    seeds = GN.make_seeds(p["genome"], fgen, n, g.rng, wide=(typ == "wide"))
    fp = s["plants"].get(x["father"]) if x["father"] in s["plants"] else None
    if x["father"].startswith("Q") and x["father"] in s["pollen"]:
        fp = s["plants"].get(s["pollen"][x["father"]]["src"])
    tf = s["plants"].get(x.get("_true_father")) if x["father"] == "open" else fp
    gen = max(p.get("gen", 0), (tf.get("gen", 0) if tf else 0)) + 1
    anc = sorted(set(p.get("anc", [])) | (set(fp.get("anc", [])) if fp else set()))
    if x["kind"] == "self" or (fp and fp.get("lot") == p.get("lot") and p.get("lot")):
        label = f"F{gen}" if p.get("gen", 0) >= 1 else "自交 S1"
    elif x["father"] == "open":
        label = f"开放授粉 G{gen}"
    elif fp and (p.get("gen", 0) == 0) != (fp.get("gen", 0) == 0) and (set(p.get("anc", [])) & set(fp.get("anc", []))):
        label = "回交 BC"
    elif fp and p.get("gen", 0) == 0 and fp.get("gen", 0) == 0:
        label = "F1"
    else:
        label = f"杂交 G{gen}"
    if typ == "wide":
        label = "远缘 F1"
    sid = g.new_lot(seeds, {"src": f"{x['id']} 采种（♀ {p['id']}）", "line": p["line"], "xid": x["id"], "mother": p["id"],
                            "father": x["father"], "gen": gen, "label": label, "anc": anc, "viab": 0.9})
    x["lot"] = sid
    x["status"] = f"已采种：{n} 粒"
    p["fruit"] = None
    p["stage"] = "mature"
    p["rest"] = 6 if G["annual"] else 12
    g.hist(p, f"采种 {sid}（{n} 粒）")
    sk = "seeds_few" if n < G["seeds"] * 0.6 else "seeds_many" if n > G["seeds"] * 1.2 else "seeds_mid"
    p["obs"]["seeds"] = [sk, {"seeds_few": "结籽少", "seeds_mid": "结籽中等", "seeds_many": "结籽多"}[sk] + f"（{n} 粒）", s["day"]]
    key = f"seeds:{sk}"
    if key not in s["catalog"]["traits"]:
        s["catalog"]["traits"][key] = [s["day"], p["id"], p["obs"]["seeds"][1].split("（")[0]]
    s["stats"]["harvests"] += 1
    g.say(f"🫘 从 {p['id']} 采到 {n} 粒种子，入库批次 {sid}（{label}）。")
    if G["annual"] and p["age"] > G["life"] * 0.8:
        g.say(f"  （{p['id']} 是一年生的，大概快到头了。）")
    g.spend(20)


def c_dump(g, a):
    lot = g.s["lots"].get(a[0].upper()) if a else None
    if not lot:
        g.say("用法：dump <批次>（把剩下的种子处理掉，批次记录保留）")
        return
    n = len(lot["seeds"])
    lot["seeds"] = []
    lot["note"] = (lot.get("note", "") + f" 第 {g.s['day']} 天清理，弃掉 {n} 粒").strip()
    g.say(f"🗑️ {lot['id']} 剩下的 {n} 粒种子处理掉了。批次记录还在（lots all）。")


def c_relabel(g, a):
    if len(a) < 2:
        g.say("用法：relabel <株> <批次>，把这株的来源记录改成那个批次")
        return
    p, err = find_plant(g, a[0], alive=False)
    if not p:
        g.say(err)
        return
    lot = g.s["lots"].get(a[1].upper())
    if not lot:
        g.say("没有这个批次。")
        return
    old = p.get("lot")
    for k in ("xid", "mother", "father", "gen", "label", "anc", "line"):
        p[k] = lot.get(k)
    p["lot"] = lot["id"]
    g.hist(p, f"来源记录从 {old} 改为 {lot['id']}（第 {g.s['day']} 天，手动更正）")
    g.say(f"✏️ {p['id']} 的来源记录改成了 {lot['id']}。旧记录保留在经历里。")


def c_clear(g, a):
    p, err = find_plant(g, a[0] if a else "", alive=False)
    if not p:
        g.say(err)
        return
    p["doubt"] = False
    g.hist(p, "确认来源，去掉存疑标记")
    g.say(f"{p['id']} 不再标记为来源存疑。")


def c_set(g, a):
    s = g.s
    if len(a) < 3:
        g.say("用法：set <区> temp <℃> | light <小时，0 = 自然光> | radio on|off | nightbreak on|off")
        return
    z = find_zone(a[0])
    if not z or s["zones"][z]["locked"]:
        g.say("没有这个温室，或者它锁着。")
        return
    k, v = a[1], a[2]
    zs = s["zones"][z]
    if k == "temp":
        if not ZONES[z]["heat"]:
            g.say("这里没有暖气。")
            return
        try:
            t = int(v)
        except ValueError:
            g.say("温度写整数。")
            return
        lo = ZONES[z]["min"]
        if t < lo or t > 34:
            g.say(f"{ZONES[z]['name']}能设定的温度是 {lo}~34℃。")
            return
        zs["temp"] = t
        g.say(f"🌡️ {ZONES[z]['name']}设定为 {t}℃。（实际温度还受室外影响：夏天降温能力有限）")
    elif k == "light":
        if not g.up("lamp"):
            g.say("没有补光灯组，不能控制日照。（upgrade lamp）")
            return
        try:
            h = float(v)
        except ValueError:
            g.say("写小时数，0 表示自然光。")
            return
        if h != 0 and not 8 <= h <= 18:
            g.say("日照可以设 8~18 小时（遮光帘加补光灯），0 是自然光。")
            return
        zs["photo"] = h
        g.say(f"💡 {ZONES[z]['name']}的日照设为 {h} 小时。" if h else f"💡 {ZONES[z]['name']}恢复自然光照。")
    elif k == "radio":
        on = v in ("on", "开", "1")
        corridor = z == CORRIDOR_ZONE and not g.flag("corridor_done")
        saved = s.get("saved_radio_zone") == z
        if corridor:
            g.say("走廊那台收音机是老岑的，开不开由他（白天一直开着）。")
            return
        if on and not saved and not g.up("radio"):
            g.say("这里没有收音机。（upgrade radio）")
            return
        if on and not saved:
            old = s.get("radio_zone")
            if old and old != z and s.get("saved_radio_zone") != old:
                s["zones"][old]["radio"] = False
                g.say(f"（便携收音机从{ZONES[old]['name']}拿了过来。）")
            s["radio_zone"] = z
        zs["radio"] = on
        g.say(f"📻 {ZONES[z]['name']}的收音机{'开了' if on else '关了'}。")
    elif k in ("nightbreak", "nb"):
        if not g.up("nblamp"):
            g.say("没有夜间补光定时器。（upgrade nblamp）")
            return
        zs["nb"] = v in ("on", "开", "1")
        g.say(f"🌙 {ZONES[z]['name']}的夜间补光{'打开' if zs['nb'] else '关闭'}了：每天半夜亮灯 15 分钟。" if zs["nb"] else f"🌙 {ZONES[z]['name']}的夜间补光关了。")
    else:
        g.say("可以设定：temp、light、radio、nightbreak")
        return
    g.spend(5)


def c_keep(g, a):
    s = g.s
    p, err = find_plant(g, a[0] if a else "")
    if not p:
        g.say(err)
        return
    if p["id"] in s["collection"]:
        g.say("它已经在收藏温室里了。")
        return
    if len(s["collection"]) >= s["kcap"]:
        g.say(f"收藏温室满了（{s['kcap']} 个位置）。")
        return
    if not _cost(g, 10):
        return
    p["zone"] = "K"
    s["collection"].append(p["id"])
    g.hist(p, "搬进了私人收藏温室")
    g.say(f"🏡 {g.pname(p)} 搬进了收藏温室。给它写点什么吧：diary {p['id']} <文字>，或者 tag {p['id']} <标签>。")
    g.spend(10)


def c_collection(g, a):
    s = g.s
    g.say(f"🏡 私人收藏温室（{len(s['collection'])}/{s['kcap']}）")
    if not s["collection"] and not s["herbarium"]:
        g.say("  还是空的。什么都可以放进来——不一定要稀有，只要你想留着。（keep <株>）")
        return
    for pid in s["collection"]:
        p = s["plants"][pid]
        g.say(f"· {g.pname(p)}  {g.gname(p)} {p.get('label', '')}，来源：{_origin(g, p)}")
        o = p["obs"]
        look = "；".join(o[t][1] for t in ("flower", "leaf", "stem", "height") if t in o)
        if look:
            g.say(f"    最近的样子：{look}")
        if p["tags"]:
            g.say("    标签：" + "、".join(p["tags"]))
        firsts = [h for h in p["hist"] if any(k in h[1] for k in ("发芽", "开花", "死亡", "授粉", "采种", "搬进", "发现", "检测"))][:6]
        if firsts:
            g.say("    它的日子：" + "；".join(f"第{d}天{t}" for d, t in firsts))
        for d, t in p["diary"]:
            g.say(f"    ✎ 第 {d} 天：{t}")
    if s["herbarium"]:
        g.say(f"📕 标本册（{len(s['herbarium'])} 份）")
        for sp in s["herbarium"][-20:]:
            look = "；".join(sp["obs"].get(t, "") for t in ("flower", "leaf") if sp["obs"].get(t))
            g.say(f"· {sp['id']}" + (f"「{sp['name']}」" if sp["name"] else "") + f" {sp['gname']} {sp['label']}——{sp['how']}（第 {sp['day']} 天）"
                  + (f"：{look}" if look else ""))
            for d, t in sp["diary"][-2:]:
                g.say(f"    ✎ 第 {d} 天：{t}")


def c_diary(g, a):
    if len(a) < 2:
        g.say("用法：diary <株> <文字>")
        return
    p, err = find_plant(g, a[0], alive=False)
    if not p:
        g.say(err)
        return
    p["diary"].append([g.s["day"], " ".join(a[1:])[:300]])
    g.say(f"✎ 写进了 {p['id']} 的日记。")


def c_name(g, a):
    if len(a) < 2:
        g.say("用法：name <株> <名字>")
        return
    p, err = find_plant(g, a[0], alive=False)
    if not p:
        g.say(err)
        return
    p["name"] = " ".join(a[1:])[:20]
    g.hist(p, f"取名「{p['name']}」")
    g.say(f"{p['id']} 现在叫「{p['name']}」。")


def c_tag(g, a):
    if len(a) < 2:
        g.say("用法：tag <株> <标签>，比如 tag P0012 丑但特别")
        return
    p, err = find_plant(g, a[0], alive=False)
    if not p:
        g.say(err)
        return
    t = " ".join(a[1:])[:20]
    if t not in p["tags"]:
        p["tags"].append(t)
    g.say(f"🏷️ {p['id']}：{'、'.join(p['tags'])}")


def c_press(g, a):
    p, err = find_plant(g, a[0] if a else "", alive=False)
    if not p:
        g.say(err)
        return
    if not _cost(g, 30):
        return
    if p["alive"]:
        if p["id"] in g.s["collection"]:
            g.s["collection"].remove(p["id"])
        g.press(p)
        g.kill(p, "压制成标本")
        g.s["stats"]["died"] -= 1
    else:
        if any(sp["id"] == p["id"] for sp in g.s["herbarium"]):
            g.say("已经压过了。")
            return
        g.press(p)
    g.say(f"📕 {p['id']} 压进了标本册，标签、日记和最后一次观察记录都抄在台纸上。")
    g.spend(30)


def c_supplies(g, a):
    s = g.s
    g.say("📦 物资：" + "，".join(f"{SUPPLIES[k][0]} {v}" for k, v in s["supplies"].items()))
    if s["ups"]:
        g.say("🛠️ 设备：" + "、".join(UPGRADES[u][0] for u in s["ups"]))


def c_shop(g, a):
    g.say("🛒 物资（buy <物资> [数量]）：")
    for k, (n, price, _) in SUPPLIES.items():
        g.say(f"  {k:10s} {n}  {price} 元/份｜库存 {g.s['supplies'][k]}")
    g.say("🛠️ 设备（upgrade <设备>）：")
    for k, (n, price, d) in UPGRADES.items():
        g.say(f"  {k:10s} {n}  {'已有' if g.up(k) else str(price) + ' 元'}——{d}")
    g.say(f"经费 {g.s['funds']} 元。")


def c_buy(g, a):
    if not a or a[0] not in SUPPLIES:
        g.say("买什么？shop 看列表。")
        return
    try:
        n = int(a[1]) if len(a) > 1 else 1
    except ValueError:
        n = 1
    n = max(1, min(n, 200))
    cost = SUPPLIES[a[0]][1] * n
    if g.s["funds"] < cost:
        g.say(f"要 {cost} 元，经费不够。")
        return
    g.s["funds"] -= cost
    g.s["supplies"][a[0]] += n
    g.say(f"🛒 买了 {n} 份{SUPPLIES[a[0]][0]}，花了 {cost} 元。")


def c_upgrade(g, a):
    if not a or a[0] not in UPGRADES:
        return c_shop(g, a)
    u = a[0]
    if g.up(u):
        g.say("已经有了。")
        return
    n, price, d = UPGRADES[u]
    if g.s["funds"] < price:
        g.say(f"{n}要 {price} 元，经费不够。")
        return
    g.s["funds"] -= price
    g.s["ups"].append(u)
    g.say(f"🛠️ 添置了{n}。{d}")


def c_people(g, a):
    here = [n for n in NPCS if g.present(n)]
    g.say("今天在所里：" + ("、".join(f"{NPCS[n]['name']}［{n}］（{NPCS[n]['role']}）" for n in here) if here else "没有人。"))
    if "fan" in NPCS and not g.present("fan"):
        g.say("（老范是夜班保安，傍晚 14:00 以后才来。）")


def c_npc(g, a):
    if not a:
        for n, d in NPCS.items():
            if g.npc(n)["met"]:
                g.say(f"  {d['name']}［{n}］{d['role']}——{g.trust_word(n)}")
        return
    nid, err = find_npc(g, " ".join(a), need_present=False)
    if not nid:
        g.say(err)
        return
    d = NPCS[nid]
    n = g.npc(nid)
    g.say(f"【{d['name']}】{d['role']}。{d['bio']}", f"  对你：{g.trust_word(nid)}" + ("（今天在）" if g.present(nid) else ""))
    if n["mem"]:
        g.say("  记得：" + "；".join(m[1] for m in n["mem"]))


def _voice(g, nid):
    n = g.npc(nid)
    for m in n["mem"]:
        key = m[0] + str(m[2])
        if key not in n["voiced"] and m[2] < g.s["day"]:
            n["voiced"].append(key)
            g.say(f"（{NPCS[nid]['name']}还记得：{m[1]}。）")
            return


def c_talk(g, a):
    nid, err = find_npc(g, " ".join(a)) if a else (None, "和谁说话？people 看今天谁在。")
    if not nid:
        g.say(err)
        return
    if not _cost(g, 20):
        return
    n = g.npc(nid)
    n["met"] = True
    n["last"] = g.s["day"]
    _voice(g, nid)
    for e in TALK.get(nid, []):
        if e["id"] not in n["said"] and g.ok(e["need"]):
            n["said"].append(e["id"])
            g.say(f"💬 {e['say']}")
            g.run_eff(e.get("eff", []))
            g.spend(20)
            return
    lines = IDLE.get(nid, ["……"])
    g.say(f"💬 {lines[n['idle'] % len(lines)]}")
    n["idle"] += 1
    g.spend(20)


def c_ask(g, a):
    if len(a) < 2:
        g.say("用法：ask <人> <话题>，话题比如：" + "、".join(v[0] for v in TOPICS.values()))
        return
    nid, err = find_npc(g, a[0])
    if not nid:
        g.say(err)
        return
    t = find_topic(" ".join(a[1:]))
    if not t:
        g.say("你不知道该怎么问起这个。可以问的话题：" + "、".join(v[0] for v in TOPICS.values()))
        return
    if not _cost(g, 15):
        return
    n = g.npc(nid)
    n["met"] = True
    for idx, e in enumerate(ASK.get(nid, [])):
        if e["about"] == t and g.ok(e["need"]):
            first = str(idx) not in n["asked"]
            n["asked"].append(str(idx))
            g.say(f"💬 {e['say']}")
            if first:
                g.run_eff(e.get("eff", []))
            g.spend(15)
            return
    g.say(f"💬 {ASK_DEFAULT.get(nid, '……')}")
    g.spend(15)


def c_give(g, a):
    if len(a) < 2:
        g.say("用法：give <株> <人>")
        return
    p, err = find_plant(g, a[0])
    if not p:
        g.say(err)
        return
    nid, err = find_npc(g, a[1])
    if not nid:
        g.say(err)
        return
    if p["id"] in g.s["collection"]:
        g.say("这株在你的收藏温室里。真要送人，先 move 出来。")
        return
    if not _cost(g, 10):
        return
    gen = p["genome"]
    if nid == "luo" and g.flag("luo_asks") and not g.flag("luo_helped"):
        fl = p["obs"].get("flower", [""])[0]
        cold = p["obs"].get("cold", [""])[0]
        if "Ruberia" in gen["genus"] and fl.startswith(("lilac", "pink")) and cold in ("cold_ok", "cold_mild"):
            g.run_eff(["flag:luo_helped", "trust:luo:+2", "mem:luo:help:你给了我一株冷室里也能开的浅色朱点花", "rep:+3",
                       f"say:骆青禾拿着 {p['id']} 看了很久，翻了翻你的观察记录。「低温下记录过开花……好。」她把它抱走了，「我会在记录里写上你的编号。」"])
            p["alive"] = False
            p["stage"] = "gone"
            p["death"] = [g.s["day"], "送给了骆青禾，作为冷蓝项目的亲本"]
            g.hist(p, "送给骆青禾当冷蓝项目的亲本")
            g.spend(10)
            return
        g.say("骆青禾看了看：「我要的是淡紫或者浅色的朱点花，而且得有在 10℃ 以下的观察记录，证明它在冷的地方还挺得住。」")
        g.spend(10)
        return
    g.run_eff([f"trust:{nid}:+1", f"mem:{nid}:gift:你送了我一盆{g.gname(p)}"])
    p["alive"] = False
    p["stage"] = "gone"
    p["death"] = [g.s["day"], f"送给了{NPCS[nid]['name']}"]
    g.hist(p, f"送给了{NPCS[nid]['name']}")
    g.say(f"🎁 {NPCS[nid]['name']}收下了 {p['id']}。" + {"cen": "「放我值班室，我给它浇水。浇多少你别管。」", "mo": "「我给它放点音乐。」",
                                                         "xiaoman": "「我会每天给它浇水的！」——你有点担心。", "fan": "「我夜里看着它。」"}.get(nid, ""))
    g.spend(10)


def c_write(g, a):
    if not a or a[0] not in ("lin", "林知秋"):
        g.say("写信给谁？现在能写的只有 write lin（要先有地址）。")
        return
    if not g.flag("lin_addr"):
        g.say("你没有林知秋的地址。")
        return
    if g.flag("letter_sent"):
        g.say("信已经寄出去了。")
        return
    if not _cost(g, 30):
        return
    g.setflag("letter_sent")
    g.s["letter_day"] = g.s["day"]
    g.say("✉️ 你写了一封信：自我介绍，D 温室，那个铁盒，你种出来的墨铜叶。写到最后不知道怎么结尾，就写了「祝好」。寄到了那个三十年前的地址。")
    g.spend(30)


def c_open(g, a):
    z = find_zone(a[0]) if a else None
    if z != "D":
        g.say("能打开的只有 D：open D")
        return
    if not g.s["zones"]["D"]["locked"]:
        g.say("D 已经开着了。")
        return
    if not g.flag("d_key"):
        g.say("门锁着。锁是新换的，钥匙不在你这儿。")
        return
    if not _cost(g, 20):
        return
    g.s["zones"]["D"]["locked"] = False
    g.say("🔑 锁有点涩，转了两下才开。D 温室里一股潮湿的泥土味，玻璃上的苔藓把光滤成了绿色。木架子上摆着一排排空花盆。（search D 可以仔细找找）")
    g.spend(20)


def c_search(g, a):
    z = find_zone(a[0]) if a else None
    if not z:
        g.say("搜哪个温室？search A|B|C|N|D|K")
        return
    if g.s["zones"][z]["locked"]:
        g.say("锁着。")
        return
    if not _cost(g, 30):
        return
    if z == "D":
        k = g.s["searched"].get("D", 0)
        if k < len(SEARCH_D):
            e = SEARCH_D[k]
            g.s["searched"]["D"] = k + 1
            g.say("🔦 " + e["say"])
            g.run_eff(e["eff"])
            g.spend(30)
            return
    lines = SEARCH_IDLE[z]
    k = g.s["searched"].get(z + ":idle", 0)
    g.s["searched"][z + ":idle"] = k + 1
    g.say("🔦 " + lines[k % len(lines)])
    g.spend(30)


def c_report(g, a):
    s = g.s
    if not a:
        g.say("用法：report <实验编号> 或 report anomaly <异常>")
        return
    if a[0] in ("anomaly", "异常"):
        aid = a[1] if len(a) > 1 else ""
        if g.anomaly(aid) < 2:
            g.say("这个异常你还没弄明白，写不出报告。（catalog anomalies）")
            return
        if any(r[1] == "anomaly:" + aid for r in s["reports"]):
            g.say("这个已经写过了。")
            return
        if not _cost(g, 120):
            return
        s["reports"].append([s["day"], "anomaly:" + aid])
        s["bonus"] += 250
        s["stats"]["reports"] += 1
        g.run_eff(["rep:+6"])
        g.say(f"📝 你写了一篇关于「{ANOMALIES[aid][0]}」的研究报告，交给了闻所长。下次拨款会多 250 元。")
        g.spend(120)
        return
    xid = a[0].upper()
    x = s["crosses"].get(xid)
    if not x:
        g.say("没有这个实验。")
        return
    if x["report"]:
        g.say("这个实验已经写过报告了。")
        return
    kids = [p for p in s["plants"].values() if p.get("xid") == xid]
    best = 0
    for t in TRAIT_CN:
        best = max(best, sum(1 for p in kids if t in p["obs"]))
    if best < REPORT_MIN:
        g.say(f"后代里记录过同一性状的只有 {best} 株，至少要 {REPORT_MIN} 株才能写报告。")
        return
    if not _cost(g, 90):
        return
    x["report"] = True
    bonus = min(300, 120 + best * 4)
    s["bonus"] += bonus
    s["reports"].append([s["day"], xid])
    s["stats"]["reports"] += 1
    g.run_eff(["rep:+3"])
    g.say(f"📝 你整理了 {xid} 的数据，写成一篇研究报告（{best} 株后代的观察记录）。下次拨款多 {bonus} 元。")
    g.spend(90)


def c_choose(g, a):
    p = g.s["pending"]
    if not p:
        g.say("现在没有需要决定的事。")
        return
    try:
        k = int(a[0]) - 1
    except (IndexError, ValueError):
        g.say("choose 后面写编号。")
        return
    e = EVENT_BY_ID[p["id"]]
    if not 0 <= k < len(p["opts"]):
        g.say("没有这个编号。")
        return
    o = e["choice"]["opts"][p["opts"][k]]
    g.s["pending"] = None
    g.run_eff(o["eff"])


def c_end(g, a):
    s = g.s
    try:
        n = int(a[0]) if a else 1
    except ValueError:
        n = 1
    n = max(1, min(n, 7))
    for i in range(n):
        if i > 0 and s["pending"]:
            break
        g.end_day()
        for t in list(s.get("timers", [])):
            if t[0] <= s["day"]:
                s["timers"].remove(t)
                g.run_eff([t[1]])
        if s["pending"]:
            break


COMMANDS = {
    "help": c_help, "status": c_status, "st": c_status, "zones": c_zones, "map": c_zones, "zone": c_zone,
    "plants": c_plants, "ls": c_plants, "plant": c_plant, "tree": c_tree, "lots": c_lots, "lot": c_lot,
    "exp": c_exp, "ratio": c_ratio, "select": c_select, "catalog": c_catalog, "docs": c_docs, "read": c_read,
    "log": c_log, "note": c_note, "notes": c_notes, "mark": c_mark, "observe": c_observe, "obs": c_observe,
    "test": c_test, "sow": c_sow, "water": c_water, "feed": c_feed, "prune": c_prune, "repot": c_repot,
    "treat": c_treat, "move": c_move, "cut": c_cut, "culture": c_culture, "flasks": c_flasks,
    "transplant": c_transplant, "discard": c_discard, "cross": c_cross, "self": c_self, "bag": c_bag,
    "unbag": c_unbag, "pollen": c_pollen, "harvest": c_harvest, "relabel": c_relabel, "clear": c_clear, "dump": c_dump,
    "set": c_set, "keep": c_keep, "collection": c_collection, "diary": c_diary, "name": c_name, "tag": c_tag,
    "press": c_press, "supplies": c_supplies, "shop": c_shop, "buy": c_buy, "upgrade": c_upgrade,
    "people": c_people, "npc": c_npc, "talk": c_talk, "ask": c_ask, "give": c_give, "write": c_write,
    "open": c_open, "search": c_search, "report": c_report, "choose": c_choose, "end": c_end, "sleep": c_end,
}
ZH = {"帮助": "help", "状态": "status", "温室": "zones", "植株": "plants", "档案": "plant", "谱系": "tree",
      "种子": "lots", "批次": "lot", "实验": "exp", "比例": "ratio", "筛选": "select", "图鉴": "catalog",
      "文件": "docs", "阅读": "read", "日志": "log", "笔记": "note", "标记": "mark", "观察": "observe",
      "检测": "test", "播种": "sow", "浇水": "water", "施肥": "feed", "修剪": "prune", "换盆": "repot",
      "治虫": "treat", "移动": "move", "扦插": "cut", "组培": "culture", "杂交": "cross", "授粉": "cross",
      "自交": "self", "套袋": "bag", "采粉": "pollen", "采种": "harvest", "设置": "set", "收藏": "keep",
      "收藏温室": "collection", "日记": "diary", "取名": "name", "标签": "tag", "标本": "press", "物资": "supplies",
      "商店": "shop", "买": "buy", "升级": "upgrade", "人": "people", "聊": "talk", "问": "ask", "送": "give",
      "写信": "write", "打开": "open", "搜": "search", "报告": "report", "选": "choose", "结束": "end", "睡觉": "end"}
FREE = {"help", "status", "st", "zones", "map", "zone", "plants", "ls", "plant", "tree", "lots", "lot", "exp",
        "ratio", "select", "catalog", "docs", "log", "note", "notes", "mark", "flasks", "collection", "diary", "name",
        "tag", "supplies", "shop", "people", "npc", "choose", "relabel", "clear"}


def run(g, line):
    parts = line.strip().split()
    if not parts:
        return
    c, args = parts[0].lower(), parts[1:]
    c = ZH.get(parts[0], c)
    fn = COMMANDS.get(c)
    if not fn:
        g.say(f"❓ 不认识的指令「{parts[0]}」。help 看全部指令。")
        return
    if g.s["pending"] and c not in FREE:
        p = g.s["pending"]
        e = EVENT_BY_ID[p["id"]]
        g.say("❗ 有件事要先决定：" + e["choice"]["text"],
              *[f"  {k + 1}. {e['choice']['opts'][i]['label']}" for k, i in enumerate(p["opts"])], "（choose <编号>）")
        return
    g.s["turn"] += 1
    fn(g, args)


# ───────── 入口 ─────────
_G = None
_PATH = None


def _load(path):
    for p in (path, path + ".bak"):
        if not os.path.exists(p):
            continue
        try:
            with open(p, encoding="utf-8") as f:
                st = json.load(f)
            if not isinstance(st, dict) or not isinstance(st.get("plants"), dict):
                continue
            st = _migrate(st)
            if st is None or not _consistent(st):
                continue
            return st, p != path
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return None, False


def _consistent(st):
    """读档时检查编号和谱系：编号计数器不能落后于已有编号，引用必须存在。"""
    for k, coll in (("P", st["plants"]), ("S", st["lots"]), ("X", st["crosses"])):
        for i in coll:
            if int(i[1:]) >= st["next"][k]:
                return False
    for p in st["plants"].values():
        if p.get("lot") and p["lot"] not in st["lots"]:
            return False
        if p.get("xid") and p["xid"] not in st["crosses"]:
            return False
    for x in st["crosses"].values():
        if x["mother"] not in st["plants"]:
            return False
    return True


def _migrate(st):
    v = st.get("v", 0)
    if v > VERSION:
        return None
    base = _fresh_state(st.get("seed", 1))
    for k, val in base.items():
        st.setdefault(k, val)
    for k, val in base["supplies"].items():
        st["supplies"].setdefault(k, 0)
    st["v"] = VERSION
    return st


def set_save_path(path):
    """指定存档位置（之后的读写都用这个路径）。"""
    global _PATH, _G
    _PATH = path
    _G = None
    return f"存档位置：{path}"


def _start(g):
    s = g.s
    for line in START_LOTS:
        g.lot_from_line(line, START_LOT_SIZE, "种子库原有批次")
    for line, z, stage, src in START_PLANTS:
        g.plant_from_line(line, z, stage, src)
    g.say(f"🌿 《{TITLE}》")
    g.say(f"☀️ ── 第 1 天 · 春季第 1 天 · 星期一 ──")
    for e in EVENTS:
        if e["at"] == "dawn" and g.event_today(e):
            g.fire_event(e["id"])


def _game():
    global _G
    if _G is None:
        path = _PATH or _save_path()
        st, recovered = _load(path)
        if st is None:
            corrupt = os.path.exists(path)
            if corrupt:
                try:
                    shutil.copyfile(path, path + f".corrupt-{int(_time.time())}")
                except OSError:
                    pass
            _G = Game(_fresh_state(int(_time.time() * 1000) & 0xFFFFFFFF), path)
            _start(_G)
            _G.save()
            if corrupt:
                _G.say("（存档和备份都读不了，坏掉的存档另存了一份，开了新的一局。）")
        else:
            _G = Game(st, path)
            if recovered:
                _G.say("（主存档损坏了，已经从备份恢复。）")
    return _G


def cmd(text="status"):
    """执行指令，返回文字。多条用 ; 或换行分隔（一次最多 10 条）。"""
    g = _game()
    lines = [x.strip() for x in str(text).replace("；", ";").replace("\n", ";").split(";") if x.strip()]
    if not lines:
        lines = ["status"]
    over = len(lines) > MAX_BATCH
    lines = lines[:MAX_BATCH]
    multi = len(lines) > 1
    for k, ln in enumerate(lines):
        if multi:
            g.out.append(f"▶ {ln}")
        snapshot = json.dumps(g.s, ensure_ascii=False)
        rng_state = g.rng.state
        day = g.s["day"]
        try:
            run(g, ln)
            g.save()
        except Exception as ex:  # 一条坏指令不能弄坏存档：回滚这一条
            g.s = json.loads(snapshot)
            g.rng = Rng(rng_state)
            g.out.append(f"⚠️ 这条指令出错了（{type(ex).__name__}: {ex}），已经撤销，存档没受影响。")
        if multi:
            g.out.append("")
        rest = len(lines) - k - 1
        if rest and (g.s["pending"] or g.s["day"] != day):
            why = "有事等你决定" if g.s["pending"] else "新的一天开始了"
            g.out.append(f"⏸️ 批量指令在这里停下（{why}），后面 {rest} 条没有执行。")
            break
    if over:
        g.out.append(f"（一次最多 {MAX_BATCH} 条，后面的没有执行）")
    res = "\n".join(g.out).rstrip() + "\n" + g.bar()
    g.out = []
    return res


def new_game(seed=None, force=False):
    """开始新游戏。已有进度时要 force=True，旧存档会先备份。"""
    global _G
    path = _PATH or _save_path()
    if os.path.exists(path):
        st, _ = _load(path)
        if st and st.get("turn", 0) > 0 and not force:
            return f"⚠️ 已经有一局在进行中（第 {st['day']} 天）。确定要重开，请用 new_game(seed, force=True)，旧存档会先自动备份。"
        root, ext = os.path.splitext(path)
        try:
            shutil.copyfile(path, f"{root}.old-{int(_time.time() * 1000)}{ext}")
        except OSError:
            pass
    if seed is None:
        seed = int(_time.time() * 1000) & 0xFFFFFFFF
    _G = Game(_fresh_state(int(seed) & 0xFFFFFFFF), path)
    _start(_G)
    _G.save()
    res = "\n".join(_G.out) + "\n先 help 看看能做什么，或者 talk wen 去所长办公室报到。\n" + _G.bar()
    _G.out = []
    return res
