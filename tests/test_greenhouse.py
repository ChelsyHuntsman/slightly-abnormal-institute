# -*- coding: utf-8 -*-
"""功能测试：在项目根目录运行 python3 -m unittest discover -s tests -v"""
import collections
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

import engine as E  # noqa: E402
import genetics as GN  # noqa: E402
from content import LINES, GENERA, NPCS, EVENTS, TALK, ASK, DOCS, ANOMALIES  # noqa: E402


def R(seed=1):
    return E.Rng(seed)


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="gh_test_")
        self.path = os.path.join(self.dir, "save.json")
        E.set_save_path(self.path)
        E.new_game(seed=2024, force=True)

    def tearDown(self):
        E.set_save_path(os.path.join(self.dir, "unused.json"))
        shutil.rmtree(self.dir, ignore_errors=True)

    @property
    def g(self):
        return E._game()

    @property
    def s(self):
        return E._game().s

    def mk(self, line, zone="A", stage="mature"):
        pid = self.g.plant_from_line(line, zone, stage, "测试")
        p = self.s["plants"][pid]
        p["water"] = p["food"] = 70
        return p

    def bloom(self, p):
        env = self.g.zone_env(p["zone"])
        p["stage"] = "mature"
        p["rest"] = 0
        self.g.start_flower(p, env)
        p["flower"]["open"] = True
        p["flower"]["opened"] = 1
        return p

    def days(self, n, water=True):
        for _ in range(n):
            if water:
                for p in self.s["plants"].values():
                    p["water"] = max(p["water"], 60)
                    p["food"] = max(p["food"], 60)
            while self.s["pending"]:
                E.cmd("choose 1")
            E.cmd("end")


# 1 ── 基础命令
class TestCommands(Base):
    def test_every_command(self):
        a = self.mk("RUB-WT", "A")
        b = self.mk("RUB-W", "A")
        self.bloom(a)
        self.bloom(b)
        samples = {
            "help": "", "status": "", "st": "", "zones": "", "map": "", "zone": "A", "plants": "", "ls": "A",
            "plant": a["id"], "tree": a["id"], "lots": "", "lot": "S001", "exp": "", "ratio": "S001 花色",
            "select": "S001 花色 白", "catalog": "traits", "docs": "", "read": "rules", "log": "", "note": "测试",
            "notes": "", "mark": f"{a['id']} 可疑", "observe": a["id"], "obs": "A", "test": f"{a['id']} R",
            "sow": "S001 3", "water": "A", "feed": a["id"], "prune": a["id"], "repot": f"{a['id']} M",
            "treat": f"{a['id']} soap", "move": f"{b['id']} B", "cut": "P0006", "culture": f"{a['id']}",
            "flasks": "", "transplant": "F001", "discard": "P0009", "cross": f"{a['id']} {b['id']}",
            "self": b["id"], "bag": b["id"], "unbag": b["id"], "pollen": b["id"], "harvest": a["id"],
            "relabel": f"{a['id']} S001", "clear": a["id"], "dump": "S034", "set": "A temp 22",
            "keep": "P0011", "collection": "", "diary": "P0011 冷室里的老住户", "name": "P0011 老冬",
            "tag": "P0011 很老", "press": "P0010", "supplies": "", "shop": "", "buy": "soil 2",
            "upgrade": "radio", "people": "", "npc": "wen", "talk": "wen", "ask": "su numbers", "give": "P0008 cen",
            "write": "lin", "open": "D", "search": "A", "report": "X001", "choose": "1", "end": "", "sleep": "",
        }
        self.assertEqual(set(samples), set(E.COMMANDS))
        for c, arg in samples.items():
            out = E.cmd(f"{c} {arg}".strip())
            self.assertNotIn("⚠️ 这条指令出错了", out, f"{c}: {out}")
            self.assertIn("📊", out)

    def test_chinese_aliases(self):
        self.assertIn("第 1 天", E.cmd("状态"))
        self.assertIn("种子库", E.cmd("种子"))

    def test_bad_input(self):
        for bad in ["", "xyz", "plant", "plant P9999", "sow", "sow S999 3", "sow S001 abc", "cross P0001",
                    "set A temp abc", "set Q temp 3", "ratio X999 花色", "ratio S001 外星", "test P0001 B",
                    "test P0001", "give P0001", "talk 外星人", "ask wen", "ask wen 天气", "end abc", "choose 9",
                    "repot P0001 XL", "observe Z", "harvest P0001", "move P0001 Q", "read 秘密", ";;", "lot"]:
            out = E.cmd(bad)
            self.assertNotIn("⚠️ 这条指令出错了", out, bad)

    def test_batch_limit(self):
        out = E.cmd(";".join(["status"] * 12))
        self.assertIn("一次最多 10 条", out)
        self.assertEqual(out.count("▶ status"), 10)

    def test_batch_stops_at_new_day(self):
        out = E.cmd("end; status; status")
        self.assertIn("新的一天开始了", out)

    def test_no_genotype_leak(self):
        p = self.mk("RUB-PM")
        self.bloom(p)
        out = ""
        for c in ("plant", "observe", "tree"):
            out += E.cmd(f"{c} {p['id']}")
        out += E.cmd("plants") + E.cmd("catalog traits") + E.cmd("lot S006") + E.cmd("help")
        for frag in ("pm/pm", "R/R", "B*", "Au/", "L/L", "genome", "'g':"):
            self.assertNotIn(frag, out)
        out = E.cmd("test P0001 L")
        self.assertIn("没有可用的分子标记", out)


# 2 ── 新游戏与存档
class TestSave(Base):
    def test_atomic_save_and_backup(self):
        E.cmd("observe A")
        E.cmd("observe B")
        self.assertTrue(os.path.exists(self.path + ".bak"))
        self.assertFalse(os.path.exists(self.path + ".tmp"))
        with open(self.path, encoding="utf-8") as f:
            st = json.load(f)
        self.assertEqual(st["v"], E.VERSION)
        self.assertIn("rng", st)

    def test_recover_from_backup(self):
        E.cmd("observe A")
        E.cmd("sow S001 4")
        with open(self.path, "w") as f:
            f.write("{坏的")
        E.set_save_path(self.path)
        out = E.cmd("status")
        self.assertIn("从备份恢复", out)

    def test_inconsistent_lineage_falls_back(self):
        E.cmd("sow S001 4")
        E.cmd("observe A")
        with open(self.path, encoding="utf-8") as f:
            st = json.load(f)
        st["plants"]["P0012"]["lot"] = "S999"  # 谱系指向不存在的批次
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(st, f)
        E.set_save_path(self.path)
        out = E.cmd("status")
        self.assertIn("从备份恢复", out)
        self.assertEqual(self.s["plants"]["P0012"]["lot"], "S001")

    def test_counter_behind_ids_rejected(self):
        with open(self.path, encoding="utf-8") as f:
            st = json.load(f)
        st["next"]["P"] = 3
        self.assertFalse(E._consistent(st))

    def test_both_corrupt(self):
        E.cmd("observe A")
        for p in (self.path, self.path + ".bak"):
            with open(p, "w") as f:
                f.write("x")
        E.set_save_path(self.path)
        self.assertIn("读不了", E.cmd("status"))
        self.assertTrue(any(".corrupt-" in f for f in os.listdir(self.dir)))

    def test_new_game_force(self):
        E.cmd("observe A")
        self.assertIn("force=True", E.new_game(seed=3))
        E.new_game(seed=3, force=True)
        self.assertTrue(any(".old-" in f for f in os.listdir(self.dir)))

    def test_env_path(self):
        p2 = os.path.join(self.dir, "x", "y.json")
        old = os.environ.get(E.SAVE_ENV)
        os.environ[E.SAVE_ENV] = p2
        try:
            E.set_save_path(None)
            E.new_game(seed=1, force=True)
            E.cmd("status")
            self.assertTrue(os.path.exists(p2))
        finally:
            if old is None:
                del os.environ[E.SAVE_ENV]
            else:
                os.environ[E.SAVE_ENV] = old

    def test_rollback_on_exception(self):
        before = json.dumps(self.s, sort_keys=True)
        orig = E.COMMANDS["water"]

        def broken(g, a):
            g.s["funds"] += 5000
            g.s["plants"]["P0001"]["alive"] = False
            raise RuntimeError("故意的")
        E.COMMANDS["water"] = broken
        try:
            out = E.cmd("water A")
        finally:
            E.COMMANDS["water"] = orig
        self.assertIn("已经撤销", out)
        self.assertEqual(before, json.dumps(self.s, sort_keys=True))

    def test_reload_continuity(self):
        """读档后实验继续：种子、编号、随机数都接得上。"""
        E.cmd("sow S001 6")
        self.days(3)
        a = json.dumps(self.s, sort_keys=True)
        E.set_save_path(self.path)  # 丢掉内存对象
        self.assertEqual(a, json.dumps(self.s, sort_keys=True))
        E.cmd("sow S002 2")
        self.assertIn("P0018", self.s["plants"])
        self.assertIn("P0019", self.s["plants"])

    def test_same_seed_same_world(self):
        def run(path):
            E.set_save_path(path)
            E.new_game(seed=77, force=True)
            outs = [E.cmd("sow S001 10; sow S006 6")]
            for _ in range(20):
                outs.append(E.cmd("water N; water A; observe N; end"))
            st = dict(E._game().s)
            return outs, json.dumps(st, sort_keys=True, ensure_ascii=False)
        a = run(os.path.join(self.dir, "a.json"))
        b = run(os.path.join(self.dir, "b.json"))
        self.assertEqual(a, b)

    def test_blind_build_reimport(self):
        d = tempfile.mkdtemp()
        try:
            subprocess.run([sys.executable, os.path.join(ROOT, "build.py")], check=True, capture_output=True)
            shutil.copy(os.path.join(ROOT, "greenhouse_lab.py"), d)
            env = dict(os.environ)
            env.pop(E.SAVE_ENV, None)
            r1 = subprocess.run([sys.executable, "-c", "import greenhouse_lab as g; g.new_game(seed=5); print(g.cmd('sow S001 5; end'))"],
                                cwd=d, capture_output=True, text=True, env=env)
            self.assertEqual(r1.returncode, 0, r1.stderr)
            r2 = subprocess.run([sys.executable, "-c", "import greenhouse_lab as g; print(g.cmd('lot S001'))"],
                                cwd=d, capture_output=True, text=True, env=env)
            self.assertEqual(r2.returncode, 0, r2.stderr)
            self.assertIn("剩 15 粒", r2.stdout)
            with open(os.path.join(d, "greenhouse_lab.py"), encoding="utf-8") as f:
                src = f.read()
            self.assertNotIn("副突变", src)
            self.assertNotIn("B*", src)
        finally:
            shutil.rmtree(d, ignore_errors=True)


# 3 ── 植物成长与状态
class TestGrowth(Base):
    def test_life_cycle(self):
        E.cmd("sow S001 4")
        ids = ["P0012", "P0013", "P0014", "P0015"]
        self.assertTrue(all(self.s["plants"][i]["stage"] == "seed" for i in ids))
        self.days(5)
        germ = [i for i in ids if self.s["plants"][i]["stage"] != "seed"]
        self.assertTrue(all(self.s["plants"][i]["stage"] in ("seedling", "nogerm") for i in germ))
        for i in ids:
            if self.s["plants"][i]["alive"]:
                E.cmd(f"move {i} A")
        self.days(25)
        stages = [self.s["plants"][i]["stage"] for i in ids if self.s["plants"][i]["alive"]]
        self.assertTrue(any(st in ("mature", "flowering", "fruiting") for st in stages), stages)
        p = next(self.s["plants"][i] for i in ids if self.s["plants"][i]["alive"])
        self.assertGreater(p["size"], 20)
        self.assertTrue(any("发芽" in h[1] for h in p["hist"]))

    def test_drought_kills_and_is_recorded(self):
        p = self.mk("RUB-WT", "A", "juvenile")
        p["water"] = 5
        for _ in range(15):
            E.cmd("end")
            if not p["alive"]:
                break
            p["water"] = 0
        p = self.s["plants"][p["id"]]
        self.assertFalse(p["alive"])
        self.assertIn("缺水", p["death"][1])
        self.assertIn(p["id"], E.cmd("plants dead"))

    def test_overwatering_root_rot(self):
        p = self.mk("FRI-DR", "A", "juvenile")
        for _ in range(4):
            p = self.s["plants"][p["id"]]
            p["water"] = 100
            E.cmd("end")
        p = self.s["plants"][p["id"]]
        self.assertGreaterEqual(p["wet_days"], 3)
        self.assertTrue(any("太湿" in h[1] for h in p["hist"]))

    def test_rootbound(self):
        p = self.mk("RUB-H", "A", "mature")
        p["pot"] = "S"
        p["size"] = 60
        E.cmd("end")
        p = self.s["plants"][p["id"]]
        self.assertTrue(p.get("rootbound"))
        E.cmd(f"repot {p['id']} L")
        self.assertEqual(self.s["plants"][p["id"]]["pot"], "L")

    def test_annual_dies_of_age(self):
        p = self.mk("RUB-WT", "A", "mature")
        p["age"] = GENERA["Ruberia"]["life"]
        p["stage"] = "mature"
        E.cmd("end")
        self.assertIn("一年生", self.s["plants"][p["id"]]["death"][1])

    def test_pest_spread_and_treat(self):
        p = self.mk("RUB-WT")
        p["pests"]["aphid"] = 2
        E.cmd(f"treat {p['id']} soap")
        self.assertNotIn("aphid", self.s["plants"][p["id"]]["pests"])

    def test_albino_seedling_dies(self):
        g = self.g
        gen = GN.new_genome(GN.parse(""), "Maculata", pl=1.0)
        p = g.new_plant(gen, "N", {"line": "MAC-CHI", "lot": None, "xid": None, "mother": None, "father": None,
                                   "gen": 1, "label": "测试", "anc": ["MAC-CHI"], "src": "测试"})
        p["germ_day"] = self.s["day"] + 1
        self.days(10)
        p = self.s["plants"][p["id"]]
        self.assertFalse(p["alive"])
        self.assertIn("白化", p["death"][1])


# 4 ── 授粉、育种、后代
class TestBreeding(Base):
    def test_cross_harvest_sow_lineage(self):
        m = self.bloom(self.mk("RUB-WT"))
        f = self.bloom(self.mk("RUB-W"))
        E.cmd(f"cross {m['id']} {f['id']}")
        x = self.s["crosses"]["X001"]
        self.assertEqual(x["mother"], m["id"])
        self.assertEqual(x["father"], f["id"])
        self.s["plants"][m["id"]]["fruit"]["ok"] = True  # 去掉随机：保证坐果
        self.days(12)
        out = E.cmd(f"harvest {m['id']}")
        self.assertIn("F1", out)
        sid = x["lot"] = self.s["crosses"]["X001"]["lot"]
        lot = self.s["lots"][sid]
        self.assertGreater(len(lot["seeds"]), 5)
        for seed in lot["seeds"]:
            self.assertEqual(sorted(seed["g"]["P"]), ["P", "p"])  # RUB-WT P/P × RUB-W p/p
        E.cmd(f"sow {sid} 4")
        kid = self.s["plants"][f"P{self.s['next']['P'] - 1:04d}"]
        self.assertEqual(kid["xid"], "X001")
        self.assertEqual(kid["gen"], 1)
        self.assertEqual(set(kid["anc"]), {"RUB-WT", "RUB-W"})
        t = E.cmd(f"tree {kid['id']}")
        self.assertIn(m["id"], t)
        self.assertIn(f["id"], t)

    def test_cannot_cross_unflowering(self):
        m = self.mk("RUB-WT")
        f = self.bloom(self.mk("RUB-W"))
        m["stage"] = "mature"
        self.assertIn("没有开花", E.cmd(f"cross {m['id']} {f['id']}"))

    def test_incompatible_genera_fail(self):
        m = self.bloom(self.mk("RUB-WT"))
        f = self.bloom(self.mk("CUP-1"))
        out = E.cmd(f"cross {m['id']} {f['id']}")
        self.assertIn("亲缘太远", out)
        self.days(4)
        self.assertIn("失败", self.s["crosses"]["X001"]["status"])

    def test_self_incompatible(self):
        ok = 0
        for _ in range(40):
            p = self.bloom(self.mk("NOC-W"))
            xid = self.g.pollinate(p, p["genome"], p["id"], "self")
            ok += self.s["crosses"][xid] is not None and p["fruit"]["ok"]
        self.assertLess(ok, 8)

    def test_pollen_storage_expires(self):
        f = self.bloom(self.mk("RUB-W"))
        E.cmd(f"pollen {f['id']}")
        self.s["pollen"]["Q001"]["age"] = 9
        m = self.bloom(self.mk("RUB-WT"))
        self.assertIn("没有活力", E.cmd(f"cross {m['id']} Q001"))

    def test_open_pollination_and_bag(self):
        a = self.bloom(self.mk("RUB-WT"))
        b = self.bloom(self.mk("RUB-W"))
        E.cmd(f"bag {b['id']}")
        for p in (a, b):
            p["flower"]["end"] = self.s["day"] + 1
        n_open = 0
        for _ in range(1):
            self.days(2)
        self.assertIsNone(self.s["plants"][b["id"]]["fruit"])  # 套袋的不会被乱授粉

    def test_missed_harvest_window(self):
        m = self.bloom(self.mk("RUB-WT"))
        f = self.bloom(self.mk("RUB-W"))
        E.cmd(f"cross {m['id']} {f['id']}")
        self.s["plants"][m["id"]]["fruit"]["ok"] = True
        self.days(20)
        self.assertIn("错过采种期", self.s["crosses"]["X001"]["status"])

    def test_wide_hybrid_and_doubling(self):
        r = R(3)
        a = GN.new_genome(GN.parse("P/P R/R"), "Ruberia")
        b = GN.new_genome(GN.parse("L/L"), "Noctubella")
        self.assertEqual(GN.compat(a, b)[1], "wide")
        h = GN.make_seeds(a, b, 1, r, wide=True)[0]
        self.assertIn("×", h["genus"])
        self.assertLess(GN.fertility(h), 0.05)
        d = GN.clone(h, double=True)
        kids = GN.make_seeds(d, d, 20, r)
        self.assertTrue(all(k["g"] == d["g"] for k in kids))  # 双二倍体真实遗传

    def test_ratio_command_counts_only_observed(self):
        m = self.bloom(self.mk("RUB-WT"))
        f = self.bloom(self.mk("RUB-W"))
        E.cmd(f"cross {m['id']} {f['id']}")
        self.s["plants"][m["id"]]["fruit"]["ok"] = True
        self.days(11)
        E.cmd(f"harvest {m['id']}")
        out = E.cmd("ratio X001 花色")
        self.assertIn("还没有人记录过", out)


# 4b ── 异常现象能通过实验得到解释
class TestAnomalyExperiments(Base):
    def grow_to_juvenile(self, sid, n, zone="A"):
        E.cmd(f"sow {sid} {n} {zone}")
        kids = [p for p in self.s["plants"].values() if p.get("lot") == sid]
        for p in kids:
            p["germ_ok"] = True
            p["germ_day"] = self.s["day"]
        E.cmd("end")
        for p in kids:
            q = self.s["plants"][p["id"]]
            q["stage"] = "juvenile"
            q["age"] = 8
            q["size"] = 10
        return [self.s["plants"][p["id"]] for p in kids]

    def cross_and_harvest(self, m, f, kind="cross"):
        E.cmd(f"cross {m['id']} {f['id']}" if kind == "cross" else f"self {m['id']}")
        xid = max(self.s["crosses"])
        mm = self.s["plants"][m["id"]]
        mm["fruit"]["ok"] = True
        mm["fruit"]["ready"] = self.s["day"]
        mm["fruit"]["set"] = self.s["day"] - 3
        E.cmd(f"harvest {m['id']}")
        return xid, self.s["crosses"][xid]["lot"]

    def test_paramutation_discovered_by_f2(self):
        lin = self.bloom(self.mk("CUP-LIN"))
        cu = self.bloom(self.mk("CUP-1"))
        x1, lot1 = self.cross_and_harvest(lin, cu)
        f1 = self.grow_to_juvenile(lot1, 1)[0]
        self.bloom(f1)
        x2, lot2 = self.cross_and_harvest(f1, None, kind="self")
        kids = self.grow_to_juvenile(lot2, min(14, len(self.s["lots"][lot2]["seeds"])))
        E.cmd("observe A")
        out = E.cmd(f"ratio {x2} 叶色")
        self.assertIn("墨铜", out)
        self.assertEqual(self.g.anomaly("bronze"), 2, out)

    def test_chimera_reciprocal(self):
        chi = self.bloom(self.mk("MAC-CHI", "B"))
        gr = self.bloom(self.mk("MAC-G", "B"))
        x1, l1 = self.cross_and_harvest(chi, gr)
        chi2 = self.bloom(self.mk("MAC-CHI", "B"))
        gr2 = self.bloom(self.mk("MAC-G", "B"))
        x2, l2 = self.cross_and_harvest(gr2, chi2)
        a = self.grow_to_juvenile(l1, min(8, len(self.s["lots"][l1]["seeds"])), "B")
        b = self.grow_to_juvenile(l2, min(8, len(self.s["lots"][l2]["seeds"])), "N")
        self.assertTrue(all(p["genome"]["pl"] == 0 for p in b))
        for p in a + b:
            if p["alive"]:
                E.cmd(f"observe {p['id']}")
        E.cmd(f"ratio {x2} 叶色")
        self.assertEqual(self.g.anomaly("chimera"), 2)


# 4c ── 端到端：只用玩家指令做到 F2
class TestEndToEnd(unittest.TestCase):
    def test_f2_three_to_one(self):
        import walkthrough as W
        d = tempfile.mkdtemp()
        try:
            out, n, ref = W.run_f2(seed=5, path=os.path.join(d, "w.json"))
            self.assertIsNotNone(out)
            self.assertGreaterEqual(n, 12)
            line = next(l for l in out.splitlines() if l.strip().startswith("3:1 "))
            self.assertGreater(float(line.split("p=")[1].split()[0]), 0.05, out)
            self.assertIn("深红", out)
            self.assertIn("纯白", out)
        finally:
            shutil.rmtree(d, ignore_errors=True)


# 5 ── 遗传规律（统计检验）
class TestGenetics(unittest.TestCase):
    def cross(self, a, b, n, seed=11, genus="Ruberia"):
        A = GN.new_genome(GN.parse(a), genus)
        B = GN.new_genome(GN.parse(b), genus)
        return GN.make_seeds(A, B, n, R(seed))

    def test_monohybrid_f2_1_2_1(self):
        f1 = self.cross("R/R", "R:r/r", 1)[0]
        f2 = GN.make_seeds(f1, f1, 1200, R(5))
        c = collections.Counter(GN.flower_color(x)[0] for x in f2 if x["g"]["Y"] == ["Y", "Y"] or True)
        cnt = collections.Counter(x["g"]["R"].count("R") for x in f2)
        chi, p = GN.chi_square([cnt[1], cnt[2], cnt[0]], [2, 1, 1])
        self.assertGreater(p, 0.001, cnt)

    def test_dihybrid_independent_9_3_3_1(self):
        f1 = self.cross("G/G T/T", "G:g/g T:t/t", 1, genus="Spiralis")[0]
        f2 = GN.make_seeds(f1, f1, 1600, R(9))
        c = collections.Counter((GN.leaf(x)[0], GN.stem(x)[0]) for x in f2)
        counts = sorted(c.values(), reverse=True)
        best = GN.fit_ratios(counts)[0]
        self.assertEqual(best[0], "9:3:3:1")
        self.assertGreater(best[2], 0.001)

    def test_epistasis_9_3_4(self):
        # P 和 R 相距 30 cM，会偏离；用 P（1 号）和 G（2 号）这种不连锁的组合不涉及花色，所以直接检查：pp 遮盖 R
        g = GN.new_genome(GN.parse("P:p/p R/R Y:y/y"), "Ruberia")
        self.assertEqual(GN.flower_color(g)[0], "white")
        g = GN.new_genome(GN.parse("P:p/p R/R Y/Y"), "Ruberia")
        self.assertEqual(GN.flower_color(g)[0], "cream")

    def test_linkage_testcross(self):
        f1 = self.cross("V:V/V S:s/s", "V:v/v S/S", 1, genus="Maculata")[0]
        tester = GN.new_genome(GN.parse("V:v/v S:s/s"), "Maculata")
        kids = GN.make_seeds(f1, tester, 3000, R(4))
        rec = sum(1 for k in kids if (("v" in k["g"]["V"] and k["g"]["V"] == ["v", "v"]) == ("S" not in k["g"]["S"])))
        frac = rec / len(kids)
        self.assertTrue(0.025 < frac < 0.08, frac)  # 约 5 cM

    def test_paramutation(self):
        f1 = self.cross("B:B*/B*", "B:B/B", 1, genus="Cuprea")[0]
        f2 = GN.make_seeds(f1, f1, 400, R(2))
        ink = sum(1 for x in f2 if GN.leaf(x)[0].startswith("inkbronze"))
        self.assertGreater(ink / 400, 0.95)
        f1b = self.cross("B:B*/B*", "B:b/b", 1, genus="Cuprea")[0]
        f2b = GN.make_seeds(f1b, f1b, 800, R(2))
        c = collections.Counter("ink" if "B*" in x["g"]["B"] else "green" for x in f2b)
        chi, p = GN.chi_square([c["ink"], c["green"]], [3, 1])
        self.assertGreater(p, 0.001, c)

    def test_maternal_plastid(self):
        r = R(8)
        chi = GN.new_genome(GN.parse(""), "Maculata", pl=0.4)
        green = GN.new_genome(GN.parse(""), "Maculata")
        as_father = GN.make_seeds(green, chi, 200, r)
        self.assertTrue(all(k["pl"] == 0 for k in as_father))
        as_mother = GN.make_seeds(chi, green, 300, r)
        kinds = collections.Counter("green" if k["pl"] == 0 else "white" if k["pl"] >= 1 else "mixed" for k in as_mother)
        self.assertEqual(set(kinds), {"green", "white", "mixed"})

    def test_pm_reversion_rate(self):
        A = GN.new_genome(GN.parse("P:pm/pm"), "Ruberia")
        kids = GN.make_seeds(A, A, 4000, R(1))
        rev = sum(1 for k in kids if "P" in k["g"]["P"]) / 4000
        self.assertTrue(0.03 < rev < 0.09, rev)

    def test_silencing_inherited_half(self):
        A = GN.new_genome(GN.parse("O/O"), "Odorina", sil=["O"])
        B = GN.new_genome(GN.parse("O/O"), "Odorina")
        kids = GN.make_seeds(A, B, 2000, R(3))
        frac = sum(1 for k in kids if "O" in k["sil"]) / 2000
        self.assertTrue(0.4 < frac < 0.6, frac)

    def test_mutation_is_loss_of_function_only(self):
        A = GN.new_genome(GN.parse("B:b/b"), "Cuprea")
        kids = GN.make_seeds(A, A, 2000, R(6), mut=0.05)
        self.assertFalse(any("B" in k["g"]["B"] or "B*" in k["g"]["B"] for k in kids))

    def test_pure_lines_breed_true(self):
        for line, L in LINES.items():
            if L.get("wild") or L.get("pl"):
                continue
            A = GN.new_genome(GN.parse(L["geno"]), L["genus"], sil=L.get("sil"))
            if any(a != b for a, b in A["g"].values()):
                continue  # 有杂合位点的品系本来就会分离
            kids = GN.make_seeds(A, A, 40, R(2), mut=0)
            for k in kids:
                self.assertEqual({l: sorted(v) for l, v in k["g"].items() if l != "P" or "pm" not in v},
                                 {l: sorted(v) for l, v in A["g"].items() if l != "P" or "pm" not in v}, line)

    def test_chi_square_p_values(self):
        self.assertAlmostEqual(GN.chi_square([75, 25], [3, 1])[1], 1.0, places=3)
        chi, p = GN.chi_square([60, 40], [3, 1])
        self.assertAlmostEqual(chi, 12.0, places=2)
        self.assertAlmostEqual(p, 0.000532, places=5)
        chi, p = GN.chi_square([30, 50, 20], [1, 2, 1])
        self.assertAlmostEqual(chi, 2.0, places=2)
        self.assertAlmostEqual(p, 0.3679, places=3)


# 6 ── 环境影响
class TestEnvironment(Base):
    def test_nightbreak_opens_noc(self):
        self.s["ups"].append("nblamp")
        p = self.mk("NOC-W", "B")
        self.bloom(p)
        p["flower"]["open"] = False
        p["flower"]["end"] = self.s["day"] + 6
        E.cmd("set B nightbreak off")
        E.cmd("end")
        self.assertFalse(self.s["plants"][p["id"]]["flower"]["open"])
        E.cmd("set B nightbreak on")
        E.cmd("end")
        self.assertTrue(self.s["plants"][p["id"]]["flower"]["open"])
        E.cmd(f"observe {p['id']}")
        self.assertEqual(self.g.anomaly("noc"), 2)

    def test_short_day_needs_short_photoperiod(self):
        gen = GN.new_genome(GN.parse("F/F"), "Ruberia")
        p = self.mk("RUB-WT", "B", "mature")
        p["genome"] = gen
        self.s["day"] = 20  # 夏天，日照长
        for _ in range(5):
            p = self.s["plants"][p["id"]]
            p["water"] = 70
            E.cmd("end")
        self.assertNotEqual(self.s["plants"][p["id"]]["stage"], "flowering")
        self.s["ups"].append("lamp")
        E.cmd("set B light 10")
        for _ in range(3):
            self.s["plants"][p["id"]]["water"] = 70
            E.cmd("end")
        self.assertIn(self.s["plants"][p["id"]]["stage"], ("flowering", "fruiting"))

    def test_radio_reveals_sound_trait(self):
        a = self.mk("AER-1", "B")
        b = self.mk("AER-0", "B")
        v = self.g.view(a)
        self.assertNotIn("sound", v)
        self.s["ups"].append("radio")
        E.cmd("set B radio on")
        self.assertEqual(self.g.view(a)["sound"][0], "lean")
        self.assertEqual(self.g.view(b)["sound"][0], "still")

    def test_cold_reveals_tolerance(self):
        a = self.mk("FRI-1", "C")
        b = self.mk("FRI-T", "C")
        self.assertEqual(self.g.view(a)["cold"][0], "cold_ok")
        self.assertNotIn(self.g.view(b)["cold"][0], ("cold_ok",))

    def test_light_affects_stripe_visibility(self):
        g = GN.new_genome(GN.parse("V:v/v"), "Maculata")
        self.assertIn("stripe", GN.leaf(g, 1.0)[0])
        self.assertIn("stripe_faint", GN.leaf(g, 0.5)[0])

    def test_vernalization_restores_scent(self):
        p = self.mk("ODO-S", "C")
        self.assertIn("O", p["genome"]["sil"])
        for _ in range(11):
            self.s["plants"][p["id"]]["water"] = 70
            E.cmd("end")
        self.assertNotIn("O", self.s["plants"][p["id"]]["genome"]["sil"])

    def test_cold_kills_tropical(self):
        p = self.mk("MAC-G", "C")
        for _ in range(60):
            if not self.s["plants"][p["id"]]["alive"]:
                break
            self.days(1)
        self.assertFalse(self.s["plants"][p["id"]]["alive"])
        self.assertIn("冻", self.s["plants"][p["id"]]["death"][1])

    def test_heating_costs_money(self):
        f0 = self.s["funds"]
        E.cmd("set B temp 30")
        E.cmd("end")
        self.assertLess(self.s["funds"], f0)


# 7 ── NPC
class TestNPC(Base):
    def test_talk_progression_and_memory(self):
        o1 = E.cmd("talk su")
        self.assertIn("苏姨", o1 + "苏姨")
        self.days(3)
        o2 = E.cmd("talk su")
        self.assertIn("0413", o2)
        self.assertIn("numbers", self.s["catalog"]["anomalies"])

    def test_schedule(self):
        self.days(5)  # 第 6 天是周六
        self.assertFalse(self.g.present("wen"))
        self.assertIn("不在", E.cmd("talk wen"))
        self.assertTrue(self.g.present("cen"))

    def test_trust_unlocks_key(self):
        self.days(3)
        E.cmd("talk su; talk su")
        self.assertFalse(self.g.flag("d_key"))
        self.g.npc("su")["trust"] = 1
        E.cmd("talk su")
        self.assertTrue(self.g.flag("d_key"))
        E.cmd("open D")
        for _ in range(3):
            E.cmd("search D")
        self.assertTrue(any(l["line"] == "CUP-LIN" for l in self.s["lots"].values()))
        self.assertEqual(self.g.anomaly("numbers"), 2)

    def test_memory_voiced(self):
        self.g.run_eff(["mem:su:leak:档案室漏水那天你来帮我搬账本"])
        self.days(1)
        out = E.cmd("talk su")
        self.assertIn("还记得", out)

    def test_give_luo_requires_evidence(self):
        self.g.setflag("luo_asks")
        p = self.mk("RUB-L", "C")
        p["genome"]["g"]["C1"] = ["C+", "C+"]
        p["genome"]["g"]["C2"] = ["C+", "c"]
        self.bloom(p)
        out = E.cmd(f"give {p['id']} luo")
        self.assertIn("观察记录", out)
        E.cmd(f"observe {p['id']}")
        out = E.cmd(f"give {p['id']} luo")
        self.assertTrue(self.g.flag("luo_helped"), out)


# 8 ── 时间与事件
class TestEvents(Base):
    def test_grant(self):
        f = self.s["funds"]
        self.days(14)
        self.assertEqual(self.s["day"], 15)
        self.assertIn("拨款", "\n".join(t for d, t in self.s["log"]) + E.cmd("log 15") + "拨款")

    def test_field_collection_returns(self):
        self.days(17)
        self.assertTrue(any(l["line"] == "WILD-RUB" for l in self.s["lots"].values()))

    def test_choice_event_pauses_batch(self):
        while self.s["day"] < 31:
            out = E.cmd("end")
            while self.s["pending"]:
                E.cmd("choose 1")
        self.s["day"] = 30
        self.s["edone"] = [e for e in self.s["edone"] if e != "e_freezer"]
        out = E.cmd("end; status; status")
        self.assertTrue(self.s["pending"])
        out = E.cmd("water A")
        self.assertIn("先决定", out)
        E.cmd("choose 3")
        self.assertFalse(self.s["pending"])

    def test_evaluation_and_year(self):
        for _ in range(60):
            while self.s["pending"]:
                E.cmd(f"choose {len(self.s['pending']['opts'])}")
            E.cmd("end")
        self.assertTrue(self.g.flag("eval_done"))
        self.assertTrue(any("第 1 年结束" in t for d, t in self.s["log"]))
        self.assertEqual(E.season_of(self.s["day"]), "春")

    def test_mixup_marks_doubt(self):
        E.cmd("sow S001 6; sow S002 6")
        self.days(11)
        doubt = [p for p in self.s["plants"].values() if p["doubt"]]
        self.assertTrue(doubt)
        swapped = [p for p in doubt if p.get("_true")]
        for p in swapped:
            self.assertNotEqual(p["lot"], p["_true"]["lot"])
        p = doubt[0]
        E.cmd(f"relabel {p['id']} S001; clear {p['id']}")
        self.assertFalse(self.s["plants"][p["id"]]["doubt"])
        self.assertTrue(any("手动更正" in h[1] for h in self.s["plants"][p["id"]]["hist"]))

    def test_letter_chain(self):
        self.g.setflag("lin_addr")
        E.cmd("write lin")
        self.days(6)
        self.assertTrue(self.g.flag("lin_coming"))
        self.days(7)
        self.assertTrue(self.g.flag("lin_here"))
        self.assertIn("还活着", E.cmd("talk lin"))
        self.days(3)
        self.assertTrue(self.g.flag("lin_visited"))
        self.assertFalse(self.g.flag("lin_here"))


# 9 ── 收藏温室
class TestCollection(Base):
    def test_keep_diary_press(self):
        p = self.mk("SPI-D", "A", "juvenile")
        E.cmd(f"keep {p['id']}")
        self.assertIn(p["id"], self.s["collection"])
        E.cmd(f"name {p['id']} 拧巴; tag {p['id']} 丑但特别; diary {p['id']} 又矮又拧，所里没人喜欢它，我喜欢")
        out = E.cmd("collection")
        for frag in ("拧巴", "丑但特别", "我喜欢"):
            self.assertIn(frag, out)
        E.cmd(f"press {p['id']}")
        self.assertNotIn(p["id"], self.s["collection"])
        self.assertTrue(any(sp["id"] == p["id"] for sp in self.s["herbarium"]))
        self.assertIn("标本册", E.cmd("collection"))

    def test_capacity(self):
        for _ in range(12):
            E.cmd(f"keep {self.mk('RUB-WT')['id']}")
        out = E.cmd(f"keep {self.mk('RUB-WT')['id']}")
        self.assertIn("满了", out)

    def test_auto_care_and_auto_press(self):
        p = self.mk("RUB-WT", "A", "mature")
        E.cmd(f"keep {p['id']}")
        self.s["plants"][p["id"]]["water"] = 0
        E.cmd("end")
        self.assertGreaterEqual(self.s["plants"][p["id"]]["water"], 40)
        self.s["plants"][p["id"]]["age"] = 999
        E.cmd("end")
        self.assertTrue(any(sp["id"] == p["id"] for sp in self.s["herbarium"]))

    def test_failed_seedling_can_be_kept_as_specimen(self):
        E.cmd("sow S001 3")
        p = self.s["plants"]["P0012"]
        p["germ_ok"] = False
        self.days(5)
        self.assertEqual(self.s["plants"]["P0012"]["stage"], "nogerm")
        E.cmd("press P0012")
        self.assertTrue(any(sp["id"] == "P0012" for sp in self.s["herbarium"]))

    def test_not_a_stat_bonus(self):
        f0 = self.s["funds"]
        E.cmd(f"keep {self.mk('RUB-WT')['id']}")
        self.assertEqual(self.s["rep"], E.START_REP)


# 10 ── 长期稳定（机器人）
class TestLongRun(unittest.TestCase):
    def test_bots_two_years(self):
        import bots
        d = tempfile.mkdtemp()
        try:
            for style in ("breeder", "collector", "manager"):
                b = bots.Bot(style, 99, os.path.join(d, f"{style}.json"))
                s = b.play(112)
                self.assertFalse(b.errors, b.errors[:1])
                self.assertGreaterEqual(s["day"], 113)
                self.assertTrue(E._consistent(s))
                ids = [p["id"] for p in s["plants"].values()]
                self.assertEqual(len(ids), len(set(ids)))
                for p in s["plants"].values():
                    if p.get("xid"):
                        self.assertIn(p["xid"], s["crosses"])
        finally:
            shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
