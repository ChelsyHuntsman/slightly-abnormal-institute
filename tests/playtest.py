# -*- coding: utf-8 -*-
"""长周期机器人试玩：几个种子 × 三种风格，检查报错、数据一致性、谱系、资源。

用法：python3 tests/playtest.py [种子数，默认 3] [天数，默认 112]
"""
import collections
import os
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from bots import Bot, E  # noqa: E402

STYLES = ["breeder", "collector", "manager"]


def invariants(s):
    bad = []
    if not E._consistent(s):
        bad.append("编号或谱系引用不一致")
    seen = set()
    for pid, p in s["plants"].items():
        if pid != p["id"]:
            bad.append(f"{pid} 的 id 字段不对")
        if pid in seen:
            bad.append(f"{pid} 重复")
        seen.add(pid)
        if p["alive"] and p["stage"] in ("dead", "nogerm"):
            bad.append(f"{pid} 状态矛盾")
        if p["zone"] == "K" and p["alive"] and p["stage"] not in ("gone", "lent") and pid not in s["collection"]:
            bad.append(f"{pid} 在收藏温室但不在收藏列表")
        if p.get("mother") and p["mother"] not in s["plants"]:
            bad.append(f"{pid} 的母本不存在")
    for pid in s["collection"]:
        if s["plants"][pid]["zone"] != "K":
            bad.append(f"收藏列表里的 {pid} 不在收藏温室")
    if len(s["collection"]) > s["kcap"]:
        bad.append("收藏温室超容量")
    for z, d in E.ZONES.items():
        n = sum(1 for p in s["plants"].values() if p["zone"] == z and p["alive"] and p["stage"] not in ("gone", "lent"))
        cap = s["kcap"] if z == "K" else d["cap"]
        if n > cap + 3:  # 锅炉事故时允许临时挤一挤
            bad.append(f"{z} 超容量 {n}/{cap}")
    for x in s["crosses"].values():
        if x.get("lot") and x["lot"] not in s["lots"]:
            bad.append(f"{x['id']} 的批次不存在")
    for l in s["lots"].values():
        used = sum(1 for p in s["plants"].values() if p.get("_true", {}).get("lot", p.get("lot")) == l["id"] and p.get("how") == "播种")
        if used + len(l["seeds"]) != l["n0"]:
            bad.append(f"{l['id']} 种子数对不上：播了 {used}，剩 {len(l['seeds'])}，原有 {l['n0']}")
    if s["min"] > E.DAY_MIN:
        bad.append("工时越界")
    for k, v in s["supplies"].items():
        if v < 0:
            bad.append(f"物资 {k} 是负数")
    return bad


def main(n_seeds=3, days=112):
    d = tempfile.mkdtemp(prefix="gh_play_")
    t0 = time.time()
    problems = []
    rows = collections.defaultdict(list)
    for seed in range(1, n_seeds + 1):
        for style in STYLES:
            b = Bot(style, seed * 7919, os.path.join(d, f"{style}_{seed}.json"))
            s = b.play(days)
            if b.errors:
                problems.append((style, seed, "指令报错", b.errors[0]))
            if b.cmds >= b.max_cmds:
                problems.append((style, seed, "指令数用尽"))
            for p in invariants(s):
                problems.append((style, seed, p))
            alive = sum(1 for p in s["plants"].values() if p["alive"] and p["stage"] not in ("gone", "lent"))
            maxgen = max([p.get("gen", 0) for p in s["plants"].values()] or [0])
            rows[style].append((s["funds"], s["rep"], alive, len(s["plants"]), len(s["crosses"]), s["stats"]["harvests"],
                                maxgen, len(s["catalog"]["traits"]), sum(1 for v in s["catalog"]["anomalies"].values() if v >= 2),
                                len(s["reports"]), len(s["collection"]) + len(s["herbarium"]), b.cmds))
    print(f"种子 {n_seeds} 个 × 风格 {len(STYLES)} 种 × {days} 天，用时 {time.time() - t0:.0f}s")
    names = ["经费", "声誉", "活植株", "登记植株", "授粉", "采种", "最高世代", "图鉴性状", "解释的异常", "报告", "收藏+标本", "指令"]
    for st in STYLES:
        avg = [sum(r[k] for r in rows[st]) / len(rows[st]) for k in range(len(names))]
        print(f"  {st:9s} " + "｜".join(f"{n} {v:.0f}" for n, v in zip(names, avg)))
    print(f"发现的问题：{len(problems)}")
    for p in problems[:30]:
        print("  ", p)
    return problems


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    days = int(sys.argv[2]) if len(sys.argv) > 2 else 112
    sys.exit(1 if main(n, days) else 0)
