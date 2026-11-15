# -*- coding: utf-8 -*-
"""《不太正常的植物研究所》遗传规则（剧透：内部遗传表在这里）。

一株植物的基因组：
    {"g": {位点: [母本等位, 父本等位]}, "pl": 0~1 白色质体比例（母系遗传）,
     "sil": [被沉默的位点], "dbl": 是否染色体加倍, "genus": 属（杂种为 "甲×乙"）}

规则一览：
  · 二倍体孟德尔遗传，8 条染色体，位点有位置（cM），减数分裂按 Haldane 距离发生交换 → 连锁。
  · P 色素位点上有一个不稳定的等位 pm（转座子插入）：体细胞回复 → 白花上的红色条纹（碎色）；
    生殖细胞里约 3% 回复成 P。
  · B* 是副突变等位：B*/B 杂合体里，B 在减数分裂时有 90% 被转成 B*（b 不受影响）。
  · 质体（叶片白斑嵌合）只经母本传递，后代在母本比例附近分选；纯白苗会死。
  · 表观沉默：胁迫可以让 O（香气）、R（红色）沉默；沉默按 50% 传给后代；低温春化可以解除 O 的沉默。
  · 远缘杂交（姊妹属）成功率低，F1 几乎不育；秋水仙素加倍后可育，且自交后代与亲本一致（双二倍体真实遗传）。
  · 每个位点每次减数分裂有很小的概率自发突变；诱变条件下更高。
"""
import math

# 位点：染色体、位置(cM)、等位基因（第一个是野生型显性）、中文名、能否做分子标记检测
LOCI = {
    "P": (1, 10, ["P", "p", "pm"], "花色素合成", True),
    "R": (1, 40, ["R", "r"], "红色强度", True),
    "Y": (1, 60, ["y", "Y"], "黄色素", True),
    "G": (2, 5, ["G", "g"], "叶绿素", True),
    "V": (2, 30, ["V", "v"], "条纹斑", True),
    "S": (2, 35, ["s", "S"], "叶面斑点", True),
    "H1": (3, 0, ["h", "H+"], "株高 1", False),
    "D": (3, 25, ["D", "d"], "矮化", True),
    "H2": (3, 50, ["h", "H+"], "株高 2", False),
    "F": (4, 10, ["f", "F"], "短日开花", True),
    "E": (4, 60, ["e", "E"], "早花", True),
    "O": (4, 80, ["o", "O"], "香气", True),
    "T": (5, 20, ["T", "t"], "茎秆直立", True),
    "N1": (5, 50, ["n", "N+"], "结籽 1", False),
    "N2": (5, 90, ["n", "N+"], "结籽 2", False),
    "C1": (6, 10, ["c", "C+"], "耐寒 1", False),
    "W1": (6, 30, ["w", "W+"], "耐旱 1", False),
    "H3": (6, 45, ["h", "H+"], "株高 3", False),
    "C2": (6, 60, ["c", "C+"], "耐寒 2", False),
    "A1": (6, 80, ["a", "A+"], "耐阴", False),
    "L": (7, 10, ["l", "L"], "夜断开花", False),
    "Au": (7, 40, ["au", "Au"], "声响应", False),
    "W2": (7, 70, ["w", "W+"], "耐旱 2", False),
    "B": (8, 20, ["b", "B", "B*"], "铜色叶", False),
}
CHROMS = {}
for _l, (_c, _p, *_r) in LOCI.items():
    CHROMS.setdefault(_c, []).append((_p, _l))
for _c in CHROMS:
    CHROMS[_c].sort()

MUT_RATE = 0.0005          # 每位点每次减数分裂（只发生「功能丧失」方向：显性功能等位 → 隐性）
PM_REVERT = 0.03           # pm → P 生殖细胞回复率
PARAMUT = 0.9              # B*/B 中 B 被转化的概率
SILENCE_PASS = 0.5         # 沉默状态传给后代的概率
SILENCEABLE = ("O", "R")
# 自发突变只往「功能丧失」方向走
LOSS = {"P": "p", "R": "r", "Y": "y", "G": "g", "V": "v", "D": "d", "F": "f", "O": "o", "T": "t", "E": "e",
        "L": "l", "Au": "au", "B": "b", "H+": "h", "N+": "n", "C+": "c", "W+": "w", "A+": "a", "S": "s"}

# 属之间的关系：同属自由杂交；姊妹属可以勉强杂交（F1 不育）；其他组合不能杂交
SISTER = {frozenset(("Ruberia", "Noctubella")), frozenset(("Ruberia", "Odorina")),
          frozenset(("Maculata", "Aeris")), frozenset(("Aeris", "Cuprea"))}


def default_allele(locus):
    return LOCI[locus][2][0]


def parse(spec):
    """'P/p R/R ...' → {locus: [a, b]}；没写的位点用第一个等位（纯合）。"""
    g = {l: [default_allele(l), default_allele(l)] for l in LOCI}
    for tok in spec.split():
        l, _, rest = tok.partition(":")
        if not rest:  # 形如 P/p：位点名取等位的前缀
            a, b = tok.split("/")
            l = _locus_of(a, b)
        else:
            a, b = rest.split("/")
        if l not in LOCI or a not in LOCI[l][2] or b not in LOCI[l][2]:
            raise ValueError(f"bad genotype token {tok}")
        g[l] = [a, b]
    return g


def _locus_of(a, b):
    cands = [l for l, d in LOCI.items() if a in d[2] and b in d[2]]
    if len(cands) != 1:
        raise ValueError(f"ambiguous genotype {a}/{b}: write it as Locus:{a}/{b}")
    return cands[0]


def from_population(freqs, rng, base=""):
    """野外种群：freqs = {位点: {等位: 频率}}，按 Hardy-Weinberg 抽两个等位。"""
    g = parse(base)
    for l, fr in freqs.items():
        items = list(fr.items())
        tot = sum(p for _, p in items)

        def draw():
            x = rng.random() * tot
            for a, p in items:
                x -= p
                if x <= 0:
                    return a
            return items[-1][0]
        g[l] = [draw(), draw()]
    return g


def new_genome(g, genus, pl=0.0, sil=None, dbl=False):
    return {"g": g, "pl": pl, "sil": list(sil or []), "dbl": dbl, "genus": genus}


def copy_genome(gen):
    return {"g": {l: list(v) for l, v in gen["g"].items()}, "pl": gen["pl"], "sil": list(gen["sil"]),
            "dbl": gen["dbl"], "genus": gen["genus"]}


def genera(gen):
    return gen["genus"].split("×")


def is_wide_hybrid(gen):
    return "×" in gen["genus"]


def _haldane(d_cm):
    return 0.5 * (1 - math.exp(-2 * d_cm / 100.0))


def meiosis(gen, rng, mut=MUT_RATE):
    """产生一个配子：{"a": {位点: 等位}, "sil": [...]}。连锁、交换、突变、副突变、pm 回复都在这里。"""
    g = gen["g"]
    if gen.get("dbl"):  # 双二倍体：同源配对，配子带全套 → 后代与亲本一致
        return {"a": None, "full": copy_genome(gen), "sil": list(gen["sil"])}
    # 副突变：B*/B → B 被转化
    pair_b = list(g["B"])
    if "B*" in pair_b and "B" in pair_b:
        pair_b = ["B*" if (a == "B" and rng.random() < PARAMUT) else a for a in pair_b]
    out = {}
    for c, loci in CHROMS.items():
        strand = 0 if rng.random() < 0.5 else 1
        last = None
        for pos, l in loci:
            if last is not None and rng.random() < _haldane(pos - last):
                strand = 1 - strand
            last = pos
            pair = pair_b if l == "B" else g[l]
            a = pair[strand]
            if a == "pm" and rng.random() < PM_REVERT:
                a = "P"
            elif a in LOSS and rng.random() < mut:
                a = LOSS[a]
            out[l] = a
    sil = [l for l in gen["sil"] if rng.random() < SILENCE_PASS]
    return {"a": out, "sil": sil}


def compat(m, f):
    """返回 (授粉成功率系数, 后代类型)。类型：same / wide / none。"""
    gm, gf = set(genera(m)), set(genera(f))
    if m.get("dbl") or f.get("dbl"):
        if m.get("dbl") and f.get("dbl") and m["genus"] == f["genus"]:
            return 0.7, "same"
        return 0.05, "wide"
    if is_wide_hybrid(m) or is_wide_hybrid(f):
        return 0.03, "wide"  # 不育的远缘 F1
    if gm == gf:
        return 1.0, "same"
    if len(gm) == 1 and len(gf) == 1 and frozenset(gm | gf) in SISTER:
        return 0.15, "wide"
    return 0.0, "none"


def child_genus(m, f):
    gm, gf = genera(m), genera(f)
    if gm == gf:
        return m["genus"]
    names = sorted(set(gm) | set(gf))
    return "×".join(names)


def fertilize(m, mg, fg, rng):
    """母本基因组 m，母本配子 mg，父本配子 fg → 种子基因组。"""
    if mg.get("full") is not None:  # 双二倍体自交
        child = copy_genome(mg["full"])
        child["pl"] = _plastid_sort(m["pl"], rng)
        return child
    g = {l: [mg["a"][l], fg["a"][l]] for l in LOCI}
    sil = sorted(set(mg["sil"]) | set(l for l in fg["sil"] if rng.random() < 0.5))
    return {"g": g, "pl": _plastid_sort(m["pl"], rng), "sil": sil, "dbl": False, "genus": m["genus"]}


def _plastid_sort(f, rng):
    """母系质体分选：母本白色质体比例 f → 子代比例。"""
    if f <= 0:
        return 0.0
    if f >= 1:
        return 1.0
    x = rng.random()
    if x < (1 - f) * 0.55:
        return 0.0
    if x < (1 - f) * 0.55 + f * 0.25:
        return 1.0
    v = f + (rng.random() - 0.5) * 0.5
    return round(min(0.95, max(0.05, v)), 2)


def make_seeds(m, f, n, rng, mut=MUT_RATE, wide=False):
    """n 粒种子的基因组；远缘杂交的种子标记 genus 为杂种。"""
    out = []
    for _ in range(n):
        mg = meiosis(m, rng, mut)
        fg = meiosis(f, rng, mut)
        if fg.get("full") is not None and mg.get("full") is None:
            fg = {"a": {l: fg["full"]["g"][l][int(rng.random() * 2)] for l in LOCI}, "sil": fg["sil"]}
        if mg.get("full") is not None and fg.get("full") is None:
            mg = {"a": {l: mg["full"]["g"][l][int(rng.random() * 2)] for l in LOCI}, "sil": mg["sil"]}
        child = fertilize(m, mg, fg, rng)
        if wide:
            child["genus"] = child_genus(m, f)
        out.append(child)
    return out


def clone(gen, rng=None, double=False):
    c = copy_genome(gen)
    if double:
        c["dbl"] = True
    return c


# ───────── 基因型 → 表型 ─────────
def _has(g, l, a):
    return a in g["g"][l]


def _count(g, l, a):
    return g["g"][l].count(a)


def _silenced(g, l):
    return l in g["sil"]


def fertility(gen):
    if gen.get("dbl"):
        return 0.6
    if is_wide_hybrid(gen):
        return 0.02
    return 1.0


def flower_color(gen, temp=20.0):
    """返回 (颜色键, 中文描述)。不考虑条纹（条纹见 streak_type）。"""
    g = gen
    pg = g["g"]["P"]
    pigment = "P" in pg
    yellow = _has(g, "Y", "Y")
    if not pigment:
        key = "cream" if yellow else "white"
    else:
        r = 0 if _silenced(g, "R") else _count(g, "R", "R")
        if r == 2:
            key = "orange" if yellow else "crimson"
        elif r == 1:
            key = "apricot" if yellow else "pink"
        else:
            key = "lemon" if yellow else "lilac"
    deep = pigment and temp < 12 and key in ("crimson", "pink", "lilac")
    if deep:
        key = key + "_deep"
    return key, COLOR_CN[key]


COLOR_CN = {
    "white": "纯白", "cream": "奶油白", "crimson": "深红", "pink": "粉红", "lilac": "淡紫",
    "orange": "朱橙", "apricot": "杏色", "lemon": "柠檬黄",
    "crimson_deep": "深红（低温下发暗，近乎酒红）", "pink_deep": "粉红（低温下偏玫瑰色）",
    "lilac_deep": "淡紫（低温下偏蓝紫）",
}


def streak_type(gen):
    """pm 等位的体细胞回复：none / few / many。只在没有正常 P 时可见。"""
    pg = gen["g"]["P"]
    if "P" in pg or "pm" not in pg:
        return "none"
    return "many" if pg.count("pm") == 2 else "few"


def leaf(gen, light=1.0):
    """叶片表型 → (键, 描述)。light 0~1.5，强光下条纹更明显。"""
    g = gen
    parts = []
    if gen["pl"] >= 1:
        return "albino", "通体白化（没有叶绿素）"
    b = g["g"]["B"]
    if "B*" in b:
        base, txt = "inkbronze", "墨铜色"
    elif "B" in b:
        base, txt = "bronze", "铜红色"
    elif g["g"]["G"] == ["g", "g"]:
        base, txt = "chartreuse", "黄绿色"
    else:
        base, txt = "green", "绿色"
    parts.append(base)
    desc = txt
    if g["g"]["V"] == ["v", "v"]:
        if light >= 0.8:
            parts.append("stripe")
            desc += "，带乳白色纵条纹"
        else:
            parts.append("stripe_faint")
            desc += "，隐约有浅色条纹（光太弱，看不太清）"
    if "S" in g["g"]["S"]:
        parts.append("spot")
        desc += "，散布深色斑点"
    if gen["pl"] > 0:
        parts.append("sector")
        desc += f"，有不规则的白色嵌合扇区（约 {int(gen['pl'] * 100)}%）"
    return "+".join(parts), desc


def height_factor(gen):
    plus = sum(gen["g"][l].count("H+") for l in ("H1", "H2", "H3"))
    f = 0.85 + 0.075 * plus  # 0.85 ~ 1.3
    if gen["g"]["D"] == ["d", "d"]:
        f *= 0.45
    return f


def stem(gen):
    if gen["g"]["T"] == ["t", "t"]:
        return "twisted", "茎秆螺旋扭曲"
    return "straight", "茎秆直立"


def scent(gen, temp=20.0):
    if "O" not in gen["g"]["O"]:
        return "none", "无香"
    if _silenced(gen, "O"):
        return "none_silent", "无香"  # 外观上与无香一样
    n = gen["g"]["O"].count("O")
    lvl = n + (1 if temp > 24 else 0) - (1 if temp < 12 else 0)
    if lvl <= 0:
        return "faint", "几乎闻不到，凑近才有一点"
    if lvl == 1:
        return "light", "淡香"
    if lvl == 2:
        return "medium", "清香"
    return "strong", "浓香，整个温室都闻得到"


def short_day(gen):
    return "F" in gen["g"]["F"]


def early(gen):
    return "E" in gen["g"]["E"]


def seed_factor(gen):
    return 0.6 + 0.2 * sum(gen["g"][l].count("N+") for l in ("N1", "N2"))  # 0.6 ~ 1.4


def tolerance(gen, kind):
    loci = {"cold": ("C1", "C2"), "drought": ("W1", "W2"), "shade": ("A1",)}[kind]
    plus = {"cold": "C+", "drought": "W+", "shade": "A+"}[kind]
    n = sum(gen["g"][l].count(plus) for l in loci)
    return n / (2 * len(loci))  # 0 ~ 1


def needs_nightbreak(gen):
    return "L" in gen["g"]["L"]


def sound_responsive(gen):
    return "Au" in gen["g"]["Au"]


def genotype_text(gen, locus):
    a, b = gen["g"][locus]
    order = LOCI[locus][2]
    a, b = sorted((a, b), key=order.index)
    return f"{a}/{b}"


# ───────── 统计：卡方检验 ─────────
def _gammainc_upper_reg(s, x):
    """正则化上不完全伽马函数 Q(s, x)（数值近似，足够做 p 值）。"""
    if x <= 0:
        return 1.0
    if x < s + 1:
        term = 1.0 / s
        tot = term
        n = 1
        while n < 500:
            term *= x / (s + n)
            tot += term
            if abs(term) < abs(tot) * 1e-12:
                break
            n += 1
        return max(0.0, 1.0 - tot * math.exp(-x + s * math.log(x) - math.lgamma(s)))
    b = x + 1 - s
    c = 1e300
    d = 1 / b
    h = d
    for i in range(1, 500):
        an = -i * (i - s)
        b += 2
        d = an * d + b
        d = 1e-300 if abs(d) < 1e-300 else d
        c = b + an / c
        c = 1e-300 if abs(c) < 1e-300 else c
        d = 1 / d
        dl = d * c
        h *= dl
        if abs(dl - 1) < 1e-12:
            break
    return min(1.0, math.exp(-x + s * math.log(x) - math.lgamma(s)) * h)


def chi_square(observed, ratio):
    tot = sum(observed)
    rs = sum(ratio)
    chi = 0.0
    for o, r in zip(observed, ratio):
        e = tot * r / rs
        if e > 0:
            chi += (o - e) ** 2 / e
    df = len(observed) - 1
    p = _gammainc_upper_reg(df / 2.0, chi / 2.0) if df > 0 else 1.0
    return chi, p


RATIOS = {
    1: [("1", [1])],
    2: [("1:1", [1, 1]), ("3:1", [3, 1]), ("15:1", [15, 1]), ("9:7", [9, 7]), ("13:3", [13, 3])],
    3: [("1:2:1", [2, 1, 1]), ("9:3:4", [9, 4, 3]), ("12:3:1", [12, 3, 1]), ("1:1:1", [1, 1, 1])],
    4: [("9:3:3:1", [9, 3, 3, 1]), ("1:1:1:1", [1, 1, 1, 1])],
}


def fit_ratios(counts):
    """counts: 按数量从大到小排好的观测数。返回 [(比例名, χ², p)]，按 p 从大到小。"""
    k = len(counts)
    res = []
    for name, ratio in RATIOS.get(k, []):
        rr = sorted(ratio, reverse=True)
        chi, p = chi_square(counts, rr)
        res.append((name, chi, p))
    res.sort(key=lambda x: -x[2])
    return res
