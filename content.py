# -*- coding: utf-8 -*-
"""《不太正常的植物研究所》内容数据（剧透！AI 玩家请不要读这个文件）。

条件：day>=N day<=N day==N | flag:x | fact:x | trust:npc>=N | met:x | present:x | up:x | funds>=N | rep>=N
      season:春/夏/秋/冬 | anomaly:aid>=1（0 未发现 1 观察到 2 解释了）| line_alive:LINE | doc:x | ! 取反 | 嵌套列表 = 任一
效果：say:文字 | log:文字 | flag:x | unflag:x | fact:x | trust:npc:+1 | mem:npc:tag:文字 | funds:+N | rep:+N
      doc:x（得到一份文件）| lot:LINE:粒数:来源说明 | plant:LINE:区域:阶段:说明 | anomaly:aid:阶段
      supply:物资:+N | choice:eid | special:name | {"if": [...], "then": [...], "else": [...]}
"""

TITLE = "不太正常的植物研究所"
DAY_MIN = 480          # 每天 8 小时工时
SEASON_LEN = 14
YEAR_LEN = 56
SEASONS = ["春", "夏", "秋", "冬"]
START_FUNDS = 3000
START_REP = 30
GRANT_EVERY = 14
SEEDBANK_CAP = 80

# ───────── 季节与室外 ─────────
# 每季：室外温度（开始, 结束）、日照小时（开始, 结束）
SEASON_ENV = {
    "春": ((10, 18), (12.0, 13.8)),
    "夏": ((24, 30), (14.5, 14.0)),
    "秋": ((18, 9), (12.5, 10.2)),
    "冬": ((3, 5), (9.6, 10.2)),
}

# ───────── 温室区域 ─────────
ZONES = {
    "A": {"name": "主温室", "cap": 30, "temp": 20, "light": 1.0, "hum": 60, "heat": True, "min": 8, "cool": 4,
          "desc": "研究所最老的玻璃温室，南北向，铁框刷过很多遍白漆。北墙一扇门通走廊，走廊里挂着一台老收音机。"},
    "B": {"name": "热带温室", "cap": 20, "temp": 26, "light": 0.85, "hum": 80, "heat": True, "min": 18, "cool": 3,
          "desc": "闷热潮湿，玻璃上永远挂着水珠，顶上挂着遮阳网。进来眼镜会起雾。"},
    "C": {"name": "冷室", "cap": 15, "temp": 8, "light": 0.8, "hum": 55, "heat": True, "min": 2, "cool": 30,
          "desc": "半地下的低温种植间，有一台嗡嗡响的压缩机。墙上贴着「出门关灯，压缩机很贵」。"},
    "N": {"name": "育苗室", "cap": 48, "temp": 22, "light": 0.9, "hum": 70, "heat": True, "min": 15, "cool": 4,
          "desc": "一排排穴盘和育苗架，日光灯管有两根闪。苗大了要移出去，不然会挤坏。"},
    "D": {"name": "废弃温室", "cap": 12, "temp": None, "light": 0.7, "hum": 65, "heat": False, "min": None, "cool": 0,
          "desc": "园区最里面那座小温室，玻璃有几块换成了木板。门锁着。", "locked": True},
    "K": {"name": "私人收藏温室", "cap": 12, "temp": 18, "light": 0.9, "hum": 60, "heat": True, "min": 10, "cool": 4,
          "desc": "原来是工具房，所长批给你一半。窄窄一条，一面墙是玻璃。放在这里的植物有人帮忙浇水，不用你操心。"},
}
CORRIDOR_ZONE = "A"   # 走廊的收音机和夜班巡逻的手电光只照得到主温室

# ───────── 物资 / 商店 / 设备 ─────────
SUPPLIES = {
    "soil": ("培养土", 20, 30), "pot_s": ("小花盆", 2, 40), "pot_m": ("中花盆", 4, 20), "pot_l": ("大花盆", 9, 8),
    "nutrient": ("营养液", 15, 12), "soap": ("肥皂水", 5, 6), "bio": ("瓢虫（生物防治）", 40, 1),
    "fungicide": ("杀菌剂", 25, 2), "pesticide": ("杀虫剂", 30, 2), "agar": ("组培培养基", 35, 4),
    "colchicine": ("秋水仙素", 120, 1), "marker": ("分子标记试剂", 60, 3), "bags": ("授粉隔离袋", 1, 50),
}
# 物资：(中文名, 单价, 开局库存)

UPGRADES = {
    "radio": ("便携收音机", 60, "可以放在任何一个温室里（set <区> radio on）。"),
    "nblamp": ("夜间补光定时器", 180, "可以给一个温室设定夜里亮灯 15 分钟（set <区> nightbreak on）。"),
    "hood": ("超净工作台", 600, "组培污染率从 18% 降到 5%。"),
    "freezer": ("花粉冷冻盒", 150, "花粉能保存 30 天（平时只有 5 天）。"),
    "drip": ("滴灌系统", 400, "每个温室每天自动浇一次水（收藏温室本来就有人管）。"),
    "seedbank2": ("种子库扩容", 300, "种子库多 40 个批次的位置。"),
    "lamp": ("补光灯组", 350, "可以设定温室的日照时长（set <区> light <小时>）。"),
}

# ───────── 属 ─────────
# temp: 适宜温度(下限, 上限)；light: 喜好光照；mature: 发芽到成熟天数；flower: 每次花期天数；fruit: 坐果到成熟天数
GENERA = {
    "Ruberia": {"name": "朱点花", "annual": True, "flowers": True, "temp": (14, 27), "light": 1.0, "hum": 55,
                "mature": 12, "flower": 6, "fruit": 5, "height": 45, "germ": 3, "seeds": 36, "selfok": True,
                "cut": False, "life": 50,
                "look": "叶片卵形，对生，茎上有细毛。花五瓣，花心有一圈小红点——名字就是这么来的。"},
    "Noctubella": {"name": "月下铃", "annual": False, "flowers": True, "temp": (10, 24), "light": 0.9, "hum": 60,
                   "mature": 16, "flower": 8, "fruit": 6, "height": 32, "germ": 5, "seeds": 20, "selfok": False,
                   "cut": True, "life": 999,
                   "look": "低矮丛生，叶子窄长，花是下垂的钟形，一串五六朵。"},
    "Odorina": {"name": "香丝草", "annual": True, "flowers": True, "temp": (15, 29), "light": 1.0, "hum": 50,
                "mature": 14, "flower": 7, "fruit": 6, "height": 55, "germ": 4, "seeds": 40, "selfok": True,
                "cut": False, "life": 55,
                "look": "茎细长，叶子像丝一样裂开，花小，聚成一团，摸过叶子手上会留味道（如果它香的话）。"},
    "Maculata": {"name": "斑叶草", "annual": False, "flowers": True, "temp": (18, 31), "light": 0.8, "hum": 75,
                 "mature": 16, "flower": 6, "fruit": 6, "height": 28, "germ": 4, "seeds": 26, "selfok": True,
                 "cut": True, "life": 999,
                 "look": "叶子宽大，叶脉清楚，花不起眼，是从叶腋里冒出来的一小撮。"},
    "Aeris": {"name": "听风草", "annual": False, "flowers": True, "temp": (8, 25), "light": 1.0, "hum": 50,
              "mature": 12, "flower": 6, "fruit": 6, "height": 38, "germ": 4, "seeds": 28, "selfok": True,
              "cut": True, "life": 999,
              "look": "一丛细长的叶子，像禾草。花序是一根细秆顶着几颗毛球。"},
    "Spiralis": {"name": "螺茎草", "annual": True, "flowers": True, "temp": (15, 29), "light": 1.1, "hum": 55,
                 "mature": 14, "flower": 6, "fruit": 6, "height": 80, "germ": 4, "seeds": 24, "selfok": True,
                 "cut": False, "life": 55,
                 "look": "长得快，茎秆中空，节间很长。叶子一片一片地交错着往上长。"},
    "Frigida": {"name": "寒绒菊", "annual": False, "flowers": True, "temp": (2, 21), "light": 1.0, "hum": 45,
                "mature": 18, "flower": 8, "fruit": 7, "height": 30, "germ": 5, "seeds": 30, "selfok": True,
                "cut": True, "life": 999,
                "look": "叶背有一层白色绒毛，摸上去像旧毛毯。花是小菊花的样子。"},
    "Umbrafilix": {"name": "荫生蕨", "annual": False, "flowers": False, "temp": (12, 27), "light": 0.6, "hum": 80,
                   "mature": 20, "flower": 0, "fruit": 0, "height": 42, "germ": 0, "seeds": 0, "selfok": False,
                   "cut": True, "life": 999,
                   "look": "羽状复叶，新叶卷成一个个小拳头，慢慢展开。不开花，靠分株繁殖。"},
    "Cuprea": {"name": "铜叶草", "annual": False, "flowers": True, "temp": (13, 27), "light": 0.9, "hum": 60,
               "mature": 15, "flower": 6, "fruit": 6, "height": 30, "germ": 4, "seeds": 24, "selfok": True,
               "cut": True, "life": 999,
               "look": "叶片圆，边缘有细锯齿。新叶的颜色最好看，老了会变暗。"},
}

# ───────── 系谱起点（品系 / 野外种群）─────────
# geno: 纯系基因型（字符串）；pop: 种群等位频率；pl: 质体白色比例；sil: 先天沉默的位点
LINES = {
    # 朱点花
    "RUB-WT": {"genus": "Ruberia", "name": "朱点花（野生型）", "geno": "P/P R/R Y:y/y", "note": "教学用标准系，深红花。"},
    "RUB-W": {"genus": "Ruberia", "name": "白花朱点", "geno": "P:p/p R/R Y:y/y", "note": "上世纪就有的白花系。"},
    "RUB-L": {"genus": "Ruberia", "name": "淡紫朱点", "geno": "P/P R:r/r Y:y/y", "note": "花色浅，很受访客喜欢。"},
    "RUB-Y": {"genus": "Ruberia", "name": "柠檬朱点", "geno": "P/P R:r/r Y/Y", "note": "黄花系，来自南方的交换种子。"},
    "RUB-D": {"genus": "Ruberia", "name": "矮朱点", "geno": "P/P R/R Y:y/y D:d/d", "note": "盆栽用的矮化系。"},
    "RUB-PM": {"genus": "Ruberia", "name": "碎色朱点", "geno": "P:pm/pm R/R Y:y/y", "note": "档案里写着「来源：林」。花是白的，但每朵上有红色的条纹，每次都不一样。"},
    "RUB-E": {"genus": "Ruberia", "name": "早花朱点", "geno": "P/P R:R/r Y:y/y E/E", "note": "开花早一周左右。"},
    "RUB-SD": {"genus": "Ruberia", "name": "秋朱点", "geno": "P/P R:R/r F/F", "note": "只在秋天开花。春天播下去，一个夏天都只长叶子。"},
    "RUB-H": {"genus": "Ruberia", "name": "高秆朱点", "geno": "P/P R/R Y:y/y H1:H+/H+ H2:H+/H+ H3:H+/H+", "note": "能长到齐腰高。"},
    # 月下铃
    "NOC-1": {"genus": "Noctubella", "name": "月下铃（所藏）", "geno": "P/P R:R/r L/L F:f/f", "note": "研究所最老的藏品之一，花期不规律。"},
    "NOC-W": {"genus": "Noctubella", "name": "白铃", "geno": "P:p/p L/L F:f/f", "note": "白花的月下铃。"},
    "NOC-DN": {"genus": "Noctubella", "name": "不夜铃", "geno": "P/P R:r/r L:l/l F:f/f", "note": "九十年代从植物园换来的，「花期正常，没什么特别」。"},
    "NOC-Y": {"genus": "Noctubella", "name": "黄铃", "geno": "P/P R:r/r Y/Y L:L/l F:f/f", "note": "黄色钟形花。"},
    # 香丝草
    "ODO-1": {"genus": "Odorina", "name": "香丝草", "geno": "O/O R:r/r", "note": "淡紫小花，很香。"},
    "ODO-0": {"genus": "Odorina", "name": "无香丝草", "geno": "O:o/o R:r/r", "note": "不香的突变系。"},
    "ODO-S": {"genus": "Odorina", "name": "哑香丝草", "geno": "O/O R:r/r", "sil": ["O"], "note": "从别的所引进的，引进以后一直不香。没人知道为什么。"},
    "ODO-P": {"genus": "Odorina", "name": "粉香丝草", "geno": "O/O R/r", "note": "粉花，香。"},
    "ODO-E": {"genus": "Odorina", "name": "早香丝草", "geno": "O/O R:r/r E/E", "note": "开得早。"},
    # 斑叶草
    "MAC-G": {"genus": "Maculata", "name": "绿斑叶草", "geno": "V/V S:s/s G/G", "note": "名字叫斑叶草，其实是纯绿的。"},
    "MAC-V": {"genus": "Maculata", "name": "条纹斑叶草", "geno": "V:v/v S:s/s", "note": "乳白条纹，光强时更明显。"},
    "MAC-S": {"genus": "Maculata", "name": "点斑叶草", "geno": "V/V S/S", "note": "叶上有深色斑点。"},
    "MAC-CH": {"genus": "Maculata", "name": "黄绿斑叶草", "geno": "G:g/g S:s/s", "note": "叶子是柠檬绿的，有人说是缺肥，其实不是。"},
    "MAC-CHI": {"genus": "Maculata", "name": "嵌合斑叶草", "geno": "S:s/s", "pl": 0.4, "note": "叶子上有大块的白色扇区，形状每片都不一样。档案上的备注：「播种后代不稳定，请用扦插保存。——林」"},
    "MAC-VS": {"genus": "Maculata", "name": "花叶斑叶草", "geno": "V:v/v S/S", "note": "条纹加斑点，有点花哨。"},
    # 听风草
    "AER-1": {"genus": "Aeris", "name": "听风草", "geno": "Au/Au", "note": "莫博士最喜欢的那种。"},
    "AER-0": {"genus": "Aeris", "name": "普通禾叶草", "geno": "Au:au/au", "note": "长得和听风草一模一样。"},
    "AER-T": {"genus": "Aeris", "name": "高听风草", "geno": "Au/Au H1:H+/H+ H2:H+/H+", "note": "高的。"},
    "AER-C": {"genus": "Aeris", "name": "寒地禾叶草", "geno": "Au:au/au C1:C+/C+ C2:C+/C+", "note": "从北方来的，不怕冷。"},
    # 螺茎草
    "SPI-1": {"genus": "Spiralis", "name": "螺茎草", "geno": "T:t/t H1:H+/h", "note": "茎秆像拧过的毛巾。"},
    "SPI-S": {"genus": "Spiralis", "name": "直茎草", "geno": "T/T", "note": "同一个属，茎是直的。"},
    "SPI-D": {"genus": "Spiralis", "name": "矮螺茎", "geno": "T:t/t D:d/d", "note": "又矮又拧巴，所里没人喜欢它。"},
    "SPI-G": {"genus": "Spiralis", "name": "巨直茎", "geno": "T/T H1:H+/H+ H2:H+/H+ H3:H+/H+", "note": "能顶到温室的横梁。"},
    "SPI-R": {"genus": "Spiralis", "name": "红茎螺茎草", "geno": "T:t/t P/P R/R", "note": "花是红的。"},
    # 寒绒菊
    "FRI-1": {"genus": "Frigida", "name": "寒绒菊", "geno": "C1:C+/C+ C2:C+/C+", "note": "冬天放在冷室外面也不怕。"},
    "FRI-T": {"genus": "Frigida", "name": "温室绒菊", "geno": "C1:c/c C2:c/c", "note": "温室里长大的，怕冷。"},
    "FRI-DR": {"genus": "Frigida", "name": "旱生绒菊", "geno": "W1:W+/W+ W2:W+/W+ C1:C+/c", "note": "可以很久不浇水。"},
    "FRI-Y": {"genus": "Frigida", "name": "金绒菊", "geno": "P/P R:r/r Y/Y C1:C+/c", "note": "小黄花。"},
    # 荫生蕨
    "UMB-1": {"genus": "Umbrafilix", "name": "荫生蕨", "geno": "A1:A+/A+", "note": "放在最暗的角落也长得很好。"},
    "UMB-V": {"genus": "Umbrafilix", "name": "花叶蕨", "geno": "V:v/v A1:A+/a", "note": "羽片上有白色条纹。"},
    "UMB-C": {"genus": "Umbrafilix", "name": "卷叶蕨", "geno": "T:t/t A1:A+/A+", "note": "叶子一直卷着，好像永远没睡醒。"},
    # 铜叶草
    "CUP-1": {"genus": "Cuprea", "name": "铜叶草", "geno": "B:B/B", "note": "铜红色的叶子，常用来做对照。"},
    "CUP-G": {"genus": "Cuprea", "name": "绿铜叶草", "geno": "B:b/b", "note": "名字里有铜，叶子是绿的。"},
    "CUP-H": {"genus": "Cuprea", "name": "杂合铜叶草", "geno": "B:B/b", "note": "铜叶草的杂交后代，留作教学。"},
    "CUP-LIN": {"genus": "Cuprea", "name": "林氏墨铜", "geno": "B:B*/B*", "note": "颜色深得像墨。档案里没有这个品系。", "hidden": True},
    # 野外种群（迟野带回来的）
    "WILD-RUB": {"genus": "Ruberia", "name": "山谷朱点花（野生种群）", "wild": True, "base": "",
                 "pop": {"P": {"P": .55, "p": .35, "pm": .10}, "R": {"R": .5, "r": .5}, "Y": {"Y": .3, "y": .7},
                         "F": {"F": .5, "f": .5}, "H1": {"H+": .5, "h": .5}, "D": {"D": .8, "d": .2},
                         "C1": {"C+": .4, "c": .6}, "C2": {"C+": .4, "c": .6}},
                 "note": "从西山一条沟里采的，一沟里什么颜色都有。那条沟冬天会下雪。"},
    "WILD-MAC": {"genus": "Maculata", "name": "溪边斑叶草（野生种群）", "wild": True, "base": "",
                 "pop": {"V": {"V": .6, "v": .4}, "S": {"S": .3, "s": .7}, "G": {"G": .85, "g": .15}},
                 "note": "溪水边石头缝里的。"},
    "WILD-NOC": {"genus": "Noctubella", "name": "崖下月下铃（野生种群）", "wild": True, "base": "F:f/f",
                 "pop": {"L": {"L": .6, "l": .4}, "P": {"P": .8, "p": .2}, "R": {"R": .4, "r": .6}},
                 "note": "迟野说，是在一个护林员小屋后面找到的，那人每天夜里拿手电去看水表。"},
    "WILD-ODO": {"genus": "Odorina", "name": "盐碱地香丝草（野生种群）", "wild": True, "base": "",
                 "pop": {"O": {"O": .6, "o": .4}, "W1": {"W+": .6, "w": .4}, "W2": {"W+": .5, "w": .5}, "R": {"R": .3, "r": .7}},
                 "note": "长在晒盐场边上。"},
    "WILD-FRI": {"genus": "Frigida", "name": "雪线寒绒菊（野生种群）", "wild": True, "base": "",
                 "pop": {"C1": {"C+": .7, "c": .3}, "C2": {"C+": .7, "c": .3}, "Y": {"Y": .5, "y": .5}, "P": {"P": .7, "p": .3}},
                 "note": "迟野第二次进山带回来的，种子袋上还有冰碴。"},
}

# 开局时种子库里的批次（品系, 粒数）
START_LOTS = ["RUB-WT", "RUB-W", "RUB-L", "RUB-Y", "RUB-D", "RUB-PM", "RUB-E", "RUB-H", "RUB-SD", "NOC-W", "NOC-DN",
              "NOC-Y", "ODO-1", "ODO-0", "ODO-P", "ODO-E", "MAC-G", "MAC-V", "MAC-S", "MAC-CH", "MAC-VS",
              "AER-0", "AER-T", "AER-C", "SPI-1", "SPI-S", "SPI-D", "SPI-G", "SPI-R", "FRI-1", "FRI-T",
              "FRI-DR", "FRI-Y", "CUP-G", "CUP-H"]
START_LOT_SIZE = 20
# 开局时已经在温室里的植物（品系, 区域, 阶段, 说明）
START_PLANTS = [
    ("NOC-1", "A", "mature", "所里养了很多年的老株，分株来的"),
    ("NOC-1", "A", "mature", "所里养了很多年的老株，分株来的"),
    ("AER-1", "A", "mature", "莫博士寄存在这里的"),
    ("RUB-PM", "A", "mature", "上一个研究员留下的"),
    ("ODO-S", "A", "mature", "引进株"),
    ("MAC-CHI", "B", "mature", "扦插保存的老株"),
    ("CUP-1", "A", "mature", "对照株"),
    ("UMB-1", "B", "mature", "分株"),
    ("UMB-V", "B", "mature", "分株"),
    ("UMB-C", "B", "mature", "分株"),
    ("FRI-1", "C", "mature", "冷室里的老住户"),
]

# ───────── 病虫害 ─────────
PESTS = {
    "aphid": {"name": "蚜虫", "hot": True, "dry": False, "treat": ["soap", "bio", "pesticide"],
              "look": "嫩梢上挤着一层绿色的小虫，叶子背面黏黏的"},
    "mite": {"name": "红蜘蛛", "hot": True, "dry": True, "treat": ["soap", "pesticide"],
             "look": "叶面出现密密的小黄点，叶背有细丝"},
    "mildew": {"name": "白粉病", "hot": False, "dry": False, "treat": ["fungicide"],
               "look": "叶面上像撒了一层面粉"},
    "gnat": {"name": "蕈蚊", "hot": False, "dry": False, "treat": ["pesticide", "soap"],
             "look": "盆土表面飞着小黑虫，根有点软"},
}

# ───────── NPC ─────────
NPCS = {
    "wen": {"name": "闻所长", "full": "闻启明", "alias": ["闻所长", "所长", "闻启明", "wen"], "role": "所长",
            "bio": "五十八岁，研究兰花出身，现在一年到头在填表。办公室窗台上养着一盆从来不开花的君子兰，他说是故意的。",
            "where": "weekday"},
    "luo": {"name": "骆青禾", "full": "骆青禾", "alias": ["骆青禾", "骆老师", "青禾", "luo"], "role": "育种师",
            "bio": "所里资历最深的育种师，记录本一笔一划像印出来的。她相信一切「异常」都是记录出了错。正在做一个叫「冷蓝」的项目。",
            "where": "weekday"},
    "cen": {"name": "老岑", "full": "岑国栋", "alias": ["老岑", "岑师傅", "岑国栋", "cen"], "role": "温室管理员",
            "bio": "管锅炉、水管、玻璃和所有会坏的东西。白天在走廊里开着收音机听戏，声音不小。对植物没有感情，但从来没让一个温室冻过。",
            "where": "always"},
    "ge": {"name": "小葛", "full": "葛悦", "alias": ["小葛", "葛悦", "ge"], "role": "组织培养技术员",
           "bio": "说话很快，戴两层手套。组培室是她的地盘，进去要换鞋。她最怕的词是「污染」。",
           "where": "weekday"},
    "chi": {"name": "迟野", "full": "迟野", "alias": ["迟野", "迟哥", "chi"], "role": "野外采集员",
            "bio": "一年有一半时间不在所里。回来的时候背着一大包标本和一脸晒伤，讲的故事一半是真的。",
            "where": "away:6-17,32-44"},
    "su": {"name": "苏姨", "full": "苏玉兰", "alias": ["苏姨", "苏玉兰", "苏老师", "su"], "role": "档案管理员",
           "bio": "管了三十年档案，正在把纸质记录一页一页录进电脑。哪本账本放在哪一层，她闭着眼都知道。",
           "where": "weekday"},
    "jiang": {"name": "蒋会计", "full": "蒋明", "alias": ["蒋会计", "蒋明", "会计", "jiang"], "role": "经费负责人",
              "bio": "什么都要发票。人不坏，只是把每一分钱都当成需要解释的问题。",
              "where": "mwf"},
    "mo": {"name": "莫博士", "full": "莫一凡", "alias": ["莫博士", "莫一凡", "mo"], "role": "隔壁声学生态实验室的研究员",
           "bio": "隔壁实验室的，研究「植物对声音的响应」。经常拿着一个录音笔在温室里蹲着。大家觉得他怪，他觉得大家太吵。",
           "where": "tth"},
    "fan": {"name": "老范", "full": "范德顺", "alias": ["老范", "范师傅", "fan", "保安"], "role": "夜班保安",
            "bio": "值夜班的保安，巡逻时手电筒挂在胸前。下班前会来温室门口站一会儿，说是「看看它们睡得好不好」。",
            "where": "evening"},
    "xiaoman": {"name": "唐小满", "full": "唐小满", "alias": ["唐小满", "小满", "xiaoman", "实习生"], "role": "实习生",
                "bio": "大三的实习生，什么都想学，什么都想帮忙。浇水特别勤快，太勤快了。",
                "where": "weekday"},
    "lin": {"name": "林知秋", "full": "林知秋", "alias": ["林知秋", "林老师", "林", "lin"], "role": "前研究员（1999 年离职）",
            "bio": "九十年代在这里做遗传研究，后来离职了。所里到处是他的字：标签上、档案里、废弃温室的墙上。",
            "where": "visit"},
}
TRUST_WORDS = [(-99, "冷淡"), (-1, "有点不满"), (0, "客气"), (1, "熟络"), (2, "信任"), (3, "知己")]

TOPICS = {
    "radio": ["收音机", "广播", "radio"], "night": ["夜班", "巡逻", "夜里", "night"],
    "lin": ["林知秋", "林老师", "林", "lin"], "d": ["废弃温室", "D", "d温室", "温室d"],
    "numbers": ["编号", "缺号", "0417", "numbers"], "bluecold": ["冷蓝", "蓝花", "bluecold"],
    "budget": ["经费", "钱", "budget"], "culture": ["组培", "加倍", "秋水仙素", "culture"],
    "wild": ["野外", "采集", "wild"], "noc": ["月下铃", "noc"], "scent": ["香", "香丝草", "scent"],
    "chimera": ["嵌合", "白斑", "chimera"], "streak": ["碎色", "条纹花", "streak"], "bronze": ["墨铜", "铜叶", "bronze"],
    "eval": ["评估", "考核", "eval"], "corridor": ["走廊", "改造", "corridor"],
}

TALK = {
    "wen": [
        {"id": "w1", "need": [], "say": "「来了？坐。」闻所长把一沓表格挪开，露出一盆从来不开花的君子兰。「温室、育苗室、冷室、种子库，都归你用。经费每两个礼拜拨一次，写出东西来就多拨一点。」他想了想，「所里有些植物……脾气比较怪。你记录做细一点就行。」",
         "eff": ["flag:intro_done"]},
        {"id": "w2", "need": ["day>=8"], "say": "「青禾跟你说什么了没有？她那个冷蓝项目，做了四年了。」闻所长叹了口气，「我不懂育种，我只懂报表。报表上它一直是『进行中』。」"},
        {"id": "w3", "need": ["day>=20", "special_cond:eval_upcoming"], "say": "「上面要来人评估。」闻所长说，「第四十二天。每个项目都要拿出东西来。……收藏温室那一块，有人提议改成仓库。」他没看你。",
         "eff": ["flag:eval_known"]},
        {"id": "w4", "need": ["day>=43", "flag:eval_done"], "say": "「评估过了。」闻所长说，「过得怎么样你也看到了。」他给君子兰浇了点水，「它今年还是没开。挺好。」"},
        {"id": "w5", "need": ["anomaly:noc>=2"], "say": "「月下铃那件事，你写个说明给我。」闻所长难得笑了，「我在这儿二十年，一直以为是老范在编故事。」"},
    ],
    "luo": [
        {"id": "l1", "need": [], "say": "骆青禾在给一盘苗打标签，没抬头。「新来的？种子库的批次号一个都不要改，你要用就记清楚从哪个批次拿的、拿了几粒。」她停了一下，「还有，所里那些传说，听听就行。九成是有人记错了。」"},
        {"id": "l2", "need": ["day>=5"], "say": "「冷蓝。」骆青禾说，「我想要一种在冷天里会变蓝的朱点花。淡紫的花在低温下会偏蓝，但不够。我需要更深的底色，还要它稳定。」她给你看了一张表，上面密密麻麻全是杂交编号。",
         "eff": ["flag:luo_project_known"]},
        {"id": "l3", "need": ["anomaly:streak>=1"], "say": "「碎色？那是不稳定等位基因，不是什么怪事。」骆青禾说，「林知秋那时候就说过，没人信他。我也不太信。但条纹的数量确实每次都不一样。」"},
        {"id": "l4", "need": ["flag:luo_asked_help"], "say": "「上次你给的那批，F2 分离得很干净。」骆青禾说，「谢谢。」这大概是她能说出来的最热情的一句话了。"},
        {"id": "l5", "need": ["day>=46", "flag:luo_paused", "!flag:luo_helped"], "say": "「冷蓝我打算停了。」骆青禾说，「不是失败，是我想明白了它要的不是一个基因。」她把那本记录本合上，「也可能就是失败。」"},
    ],
    "cen": [
        {"id": "c1", "need": [], "say": "「锅炉我管，玻璃我管，水管我管。」老岑在走廊里拧收音机的旋钮，戏腔一下子大了，「你要调温度自己调，调完了别来找我说电费。」"},
        {"id": "c2", "need": ["day>=10"], "say": "「那台收音机？跟了我十二年了。」老岑说，「白天开着，晚上关。温室里那几丛草，我一开它们就往这边歪，跟听戏似的。」他自己笑了，「瞎说的。」",
         "eff": ["fact:cen_radio"]},
        {"id": "c3", "need": ["day>=28"], "say": "「走廊要改造了，换新灯、新电线。」老岑拍拍收音机，「这个也得撤，说是不安全。」",
         "eff": ["flag:corridor_known"]},
        {"id": "c4", "need": ["season:冬"], "say": "「冬天别把冷室的温度往下调了，压缩机受不了。」老岑说，「还有，B 区那块玻璃有裂，我盯着呢。」"},
    ],
    "ge": [
        {"id": "g1", "need": [], "say": "「组培室进门换鞋！」小葛一口气说完，「你要做组培就填单子，培养基我配，接种你自己来，污染了别哭。我上周哭了。」"},
        {"id": "g2", "need": ["day>=6"], "say": "「秋水仙素可以让染色体加倍。」小葛说，「远缘杂交出来的苗一般不育，加倍以后有时候就能结籽了。成功率不高。我做过三次，成了一次，那次我请全组喝奶茶。」",
         "eff": ["fact:ge_double"]},
        {"id": "g3", "need": ["day>=24"], "say": "「组培室要认证了，第二十八天有人来查。」小葛说，「这几天别给我带污染进来。求你了。」"},
        {"id": "g4", "need": ["flag:cert_passed"], "say": "「过了！」小葛说，「认证过了！我今天能多说两百个字！」"},
    ],
    "chi": [
        {"id": "h1", "need": [], "say": "「你就是新来的？」迟野背着一个快要撑破的登山包，「我明天进山，十几天。要什么跟我说，我尽量带。」",
         "eff": ["flag:chi_met"]},
        {"id": "h2", "need": ["flag:chi_back1"], "say": "「这次带回来四袋种子，一袋斑叶草，一袋朱点花，一袋月下铃，一袋香丝草。」迟野说，「月下铃那袋你注意一下——是在一个护林员小屋后面采的。那个人夜里每天拿手电筒去看水表。别的地方的月下铃都不怎么开，就他屋后那一片开得满满的。」",
         "eff": ["fact:chi_ranger"]},
        {"id": "h3", "need": ["day>=28", "flag:chi_back1"], "say": "「第二次进山，去北坡雪线。」迟野说，「寒绒菊的种群。顺利的话，冬天之前回来。」"},
    ],
    "su": [
        {"id": "s1", "need": [], "say": "苏姨的桌上摊着三本账本和一台很旧的电脑。「种质登记，我这儿有一九八二年以来全部的。」她用手指点着一行，「但是有几个号是空的。」",
         "eff": ["flag:su_met"]},
        {"id": "s2", "need": ["flag:su_met", "day>=3"], "say": "「0413 到 0419，七个号。」苏姨说，「登记簿上这七行写了日期，一九九八年十一月，后面全是空的。字是林知秋的。他那时候在用最里面那座小温室。」",
         "eff": ["fact:missing_numbers", "anomaly:numbers:1"]},
        {"id": "s3", "need": ["fact:missing_numbers", "trust:su>=1"], "say": "苏姨从抽屉最里面摸出一把钥匙，钥匙上拴着一块写着「D」的小木牌。「废弃温室的。」她说，「所长说不让人进，因为玻璃不安全。你小心点。」",
         "eff": ["flag:d_key", "say:（你拿到了废弃温室 D 的钥匙：open D）"]},
        {"id": "s4", "need": ["fact:missing_numbers", "day>=16", "!flag:d_key"], "say": "苏姨看了你一会儿，从抽屉里拿出一把拴着「D」字木牌的钥匙放在桌上。「反正你迟早会去。」",
         "eff": ["flag:d_key"]},
        {"id": "s5", "need": ["doc:lin_p3"], "say": "「林知秋的地址？」苏姨翻了半天，翻出一张泛黄的离职登记，「这个地址三十年了。你寄寄看吧。」",
         "eff": ["flag:lin_addr"]},
    ],
    "jiang": [
        {"id": "j1", "need": [], "say": "「物资领用要登记。」蒋会计推了推眼镜，「培养土、花盆、营养液、试剂，用多少记多少。月底我要对账。」"},
        {"id": "j2", "need": ["day>=15"], "say": "「第二十一天审计。」蒋会计说，「你那边的账，我会看得比较仔细。」他想了想，补了一句，「这不是针对你。」"},
        {"id": "j3", "need": ["flag:audit_ok"], "say": "「账对上了。」蒋会计说，「难得。」他在本子上打了一个很小的勾。"},
    ],
    "mo": [
        {"id": "m1", "need": [], "say": "「嘘。」莫博士蹲在听风草旁边，举着录音笔，「它在听。……开玩笑的。」他站起来，「不全是开玩笑。」"},
        {"id": "m2", "need": ["day>=6"], "say": "「听风草对一个特定频段的声音有反应，两百赫兹左右，大概是叶片基部的细胞对振动敏感。」莫博士说，「老岑那台收音机放戏的时候，正好在这个频段。普通禾叶草就没有反应——这说明是遗传的。」",
         "eff": ["fact:mo_freq"]},
        {"id": "m3", "need": ["flag:corridor_known"], "say": "「收音机要撤？」莫博士的脸一下子白了，「那我的对照组怎么办？」"},
        {"id": "m4", "need": ["flag:mo_borrowed"], "say": "「数据很好看。」莫博士给你看一张图，一条线随着声音起伏，「谢谢你借我的草。论文里会写你的名字——第六作者。」"},
    ],
    "fan": [
        {"id": "f1", "need": [], "say": "老范在温室门口站着，手电筒挂在胸前，光打在地上一个圆。「我夜里巡逻，三天一圈。」他说，「走到主温室那边的时候，会拿手电照一照，看玻璃有没有破。」",
         "eff": ["fact:fan_patrol"]},
        {"id": "f2", "need": ["anomaly:noc>=1"], "say": "「那个铃铛花？」老范挠挠头，「我也注意到了，我值班那天早上它就开着。别人值班就不开。」他有点不好意思，「我老伴说它是给我开的。」"},
        {"id": "f3", "need": ["season:冬"], "say": "「冬天人手少，我改成隔一天一圈了。」老范搓着手，「冷是冷，夜里温室里亮堂，挺好看的。」"},
    ],
    "xiaoman": [
        {"id": "x1", "need": [], "say": "「我叫唐小满！实习生！」小满说，「浇水我来！什么都可以我来！」她已经拿着水壶了。"},
        {"id": "x2", "need": ["flag:mixup_happened"], "say": "「育苗盘的事……对不起。」小满低着头，「我把两盘苗端到架子上的时候，标签可能插反了。我真的不确定。」"},
        {"id": "x3", "need": ["day>=30"], "say": "「我想毕业论文做香丝草的香气。」小满说，「为什么同样的品系，有的香有的不香？……我想先问问你。」",
         "eff": ["flag:xiaoman_topic"]},
    ],
    "lin": [
        {"id": "n1", "need": ["flag:lin_here"], "say": "林知秋比照片上老很多，头发全白了，但站在温室门口的姿势和墙上那张合影里一模一样。「它们还活着？」他问的第一句话是这个。"},
        {"id": "n2", "need": ["flag:lin_here", "anomaly:bronze>=2"], "say": "「副突变。」林知秋说，「我那时候叫它『传染性的等位基因』，被审稿人笑了。墨铜的那个等位，会把普通铜叶的等位『改写』成自己的样子。按孟德尔，F2 应该是 3:1。我的 F2 全是墨色。」他看着你的记录，「你也看到了。」"},
        {"id": "n3", "need": ["flag:lin_here"], "say": "「那七个号，我没烧。」林知秋说，「我把种子装在一个铁盒里，埋在那座温室的花台底下。我想，如果以后有人愿意认真做，就让他们找到。」"},
    ],
}

IDLE = {
    "wen": ["「表格。又是表格。」", "闻所长在给君子兰擦叶子。"], "luo": ["骆青禾在数种子，没空理你。", "「记录写了吗？」"],
    "cen": ["走廊里的收音机在唱《锁麟囊》。", "「哪个阀门又漏了？」"], "ge": ["「换鞋！」", "小葛对着烧瓶看了很久。"],
    "chi": ["迟野在整理标本夹，满桌都是压扁的叶子。"], "su": ["苏姨在敲键盘，两根手指，很稳。"],
    "jiang": ["「发票呢？」"], "mo": ["莫博士戴着耳机，对你比了个「嘘」。"], "fan": ["老范站在门口，看了一会儿就走了。"],
    "xiaoman": ["小满在给一盆已经很湿的苗浇水。", "「今天我能做什么？」"], "lin": ["林知秋在看墙上的旧标签。"],
}

ASK = {
    "wen": [{"about": "eval", "need": ["special_cond:eval_upcoming"], "say": "「每年第四十二天。看研究报告、看图鉴、看温室状况。」闻所长说，「报告多写两篇，比什么都强。」"},
            {"about": "eval", "need": [], "say": "「今年的评估已经过了。」闻所长说，「下一次是明年的第四十二天，还是那几样：报告、图鉴、温室。」"},
            {"about": "d", "need": [], "say": "「废弃温室？玻璃不安全，别去。」闻所长停了一下，「去也小心点。」"},
            {"about": "lin", "need": [], "say": "「林知秋？我来的时候他已经走了。听说跟当时的所长吵过一架。」"}],
    "luo": [{"about": "bluecold", "need": [], "say": "「我需要淡紫的底色、深一点的花青素、还要在低温下显色。」骆青禾说，「理论上 rr 加上冷处理就会偏蓝。我缺的是一株在冷室里也能好好开花的淡紫朱点花。」",
             "eff": ["flag:luo_need"]},
            {"about": "streak", "need": [], "say": "「pm，转座子插在色素基因里。有时候跳出来，那一小块细胞就恢复了红色。」骆青禾说，「教科书上的东西，没什么神秘的。」"},
            {"about": "noc", "need": [], "say": "「月下铃？我种过，不开。」骆青禾说，「我认为是那个品系有问题。」"},
            {"about": "lin", "need": [], "say": "「林知秋是个好研究员。」骆青禾说，「就是太急着解释那些解释不了的东西。」"}],
    "cen": [{"about": "radio", "need": [], "say": "「白天开，晚上关。」老岑说，「放戏，有时候放天气预报。」", "eff": ["fact:cen_radio"]},
            {"about": "corridor", "need": ["flag:corridor_known"], "say": "「第三十五天动工。」老岑说，「收音机，你要的话可以挂到温室里去，就当它没撤。我反正不在乎。」",
             "eff": ["flag:radio_offer"]},
            {"about": "d", "need": [], "say": "「D 温室？锅炉管子没通过去，冬天里面能结冰。」"},
            {"about": "night", "need": [], "say": "「夜里？夜里我不管，老范管。」"}],
    "ge": [{"about": "culture", "need": [], "say": "「切一小块组织放培养基里，十二天左右出苗。加秋水仙素就是加倍，成功率四成。污染率……看手气。」", "eff": ["fact:ge_double"]}],
    "chi": [{"about": "wild", "need": [], "say": "「野外的种群什么都有，杂得很。」迟野说，「你要找稀有的组合，最好从野生的里挑。」"},
            {"about": "noc", "need": [], "say": "「月下铃只在有人的地方开得好。」迟野说，「我一直以为是巧合。」", "eff": ["fact:chi_ranger"]}],
    "su": [{"about": "numbers", "need": [], "say": "「0413 到 0419，林知秋的字，一九九八年十一月。」苏姨说，「只有日期，没有名字，没有来源，没有去向。」", "eff": ["fact:missing_numbers", "anomaly:numbers:1"]},
           {"about": "lin", "need": [], "say": "「林知秋走之前，把他所有的记录都交了，除了那七个号。」"}],
    "jiang": [{"about": "budget", "need": [], "say": "「每两周一次拨款，基本额度八百。写研究报告每篇加钱，评估结果也算。」蒋会计说，「暖气和补光是大头。冬天你会知道的。」"}],
    "mo": [{"about": "radio", "need": [], "say": "「两百赫兹。」莫博士说，「京剧里的胡琴和老生正好在这一段。」", "eff": ["fact:mo_freq"]},
           {"about": "corridor", "need": [], "say": "「收音机撤了，听风草就『聋』了。不是真的聋——是没东西可听。」"}],
    "fan": [{"about": "night", "need": [], "say": "「三天一圈。」老范说，「第一、四、七、十……这么排。冬天隔一天。」", "eff": ["fact:fan_schedule"]},
            {"about": "noc", "need": [], "say": "「我拿手电照照玻璃，它就开了。」老范说，「我也不知道是不是我照的。」"}],
    "xiaoman": [{"about": "scent", "need": [], "say": "「哑香丝草明明是香丝草，为什么不香？」小满说，「我去冷室拿东西的时候，那边那盆好像有一点香……可能是我闻错了。」"}],
    "lin": [{"about": "chimera", "need": [], "say": "「嵌合斑叶的白斑只跟着母本走。」林知秋说，「用它当父本，后代全是绿的；当母本，什么都有。叶绿体不在细胞核里，孟德尔管不着它。」"},
            {"about": "noc", "need": [], "say": "「月下铃是长夜里被打断才开花的那种。」林知秋说，「我那时候没想到是手电。我以为是……算了，我以为的东西太多了。」"}],
}
ASK_DEFAULT = {k: "「这个我不太清楚。」" for k in NPCS}

# ───────── 文件 / 手写记录 ─────────
DOCS = {
    "rules": ("研究所种质管理规定（第三版）", "「一、每一个批次必须有编号、来源、日期和数量。二、播种、移栽、杂交必须当天登记。三、淘汰的植株保留记录。四、记录可以修改，不能删除。」最下面有人用铅笔加了一行：「五、有些植物不讲规定。」"),
    "lin_p1": ("林知秋笔记 · 第 1 页", "「1998.3.12 碎色朱点第三次开花。条纹数 7。上次 4。再上次 11。不是环境——三株在同一个架子上，条纹数各不相同。是同一个东西在跳。跳出来的地方，颜色就回来了。」"),
    "lin_p2": ("林知秋笔记 · 第 2 页", "「1998.6.2 嵌合斑叶草，正反交。♀嵌合 × ♂绿：后代有绿有白有花。♀绿 × ♂嵌合：后代全绿。白斑跟着母亲走。不在核里。」"),
    "lin_p3": ("林知秋笔记 · 第 3 页", "「1998.9.30 墨铜 × 铜叶，F1 墨色。F1 自交，F2 应该是 3 墨 : 1 铜（不对，墨和铜都是显性，应该全有色，但墨和铜应该 3:1 分开）。实际 112 株全墨。重复两次，一样。它把另一个等位改了。审稿意见：『作者应检查种子是否混杂。』」"),
    "lin_p4": ("林知秋笔记 · 第 4 页", "「1998.11.20 编号 0413-0419。我把种子收起来了。所长要我把『不可靠的品系』处理掉。我不处理。我也不登记。如果有人找到这些，请别急着下结论。种出来，看，数，再看。」"),
    "lin_p5": ("林知秋笔记 · 第 5 页", "「月下铃只在一些早上开着。我记了三个月：开花的早上，前一夜都有人进过主温室。可能是开门的风？可能是温度？我试了吹风，不开。试了加温，不开。……我没试过光。」"),
    "radio_sched": ("走廊广播时间表（手写，贴在收音机背面）", "「06:00 新闻　07:30 戏曲　12:00 天气　14:00 戏曲　18:00 关。——岑」"),
    "mo_draft": ("莫博士的论文草稿（第一页）", "「听风草（Aeris sp.）叶基部对 180–220 Hz 振动呈现可重复的定向偏转。普通禾叶草无此响应。F1 呈响应，提示单个显性位点……」页边写着：「需要更多对照。收音机？？」"),
    "luo_notes": ("骆青禾的杂交记录（借阅）", "「冷蓝 · 第 4 年。rr × rr 稳定淡紫。冷处理（8℃）偏蓝。问题：冷室里朱点花开花差，株弱。需要耐寒背景。寒绒菊不能和朱点花杂交。考虑野外种群。」"),
    "chi_field": ("迟野的野外记录本（复印页）", "「西山七号沟，朱点花种群，花色：红、粉、白、紫、黄、杂色都有。有几株白花上带红条纹。拍照。采种 60 粒。」"),
    "cen_memo": ("走廊改造通知", "「第 35 天起，主楼走廊更换照明及线路。走廊内私人电器一律撤除。——后勤」"),
    "lin_letter": ("林知秋的回信", "「收到你的信，我很高兴，也很意外。那座温室还在？花台底下有一个铁盒。如果你愿意，过些日子我想回去看一眼。不必告诉所长，告诉了也行。——林知秋」"),
}

# ───────── 异常现象（图鉴的「异常记录」）─────────
ANOMALIES = {
    "noc": ("月下铃只在某些夜里开花", "开花的早晨，前一夜都有人带着手电走过主温室。",
            "月下铃（L 等位）需要长夜被一段光打断才开花——夜断效应。老范的手电就是那段光。"),
    "streak": ("碎色朱点花的条纹每次都不一样", "同一株，每一季的条纹数都不同。",
               "色素基因里插着一个会跳的片段（pm）。跳出去的那块组织恢复了红色。它偶尔也在种子里跳出去，后代里就会冒出正常的红花。"),
    "scent": ("哑香丝草明明是香丝草，却不香", "检测显示它有香气基因，但闻不到。",
              "香气基因被表观沉默了。低温（春化）可以解除沉默；胁迫会让它重新沉默。沉默状态有一半机会传给后代。"),
    "sound": ("听风草会朝收音机歪", "开着收音机的温室里，听风草的叶子偏向声源。",
              "听风草带有一个显性的声响应等位（Au），对约 200 Hz 的振动有反应。没有声音就看不出来。"),
    "numbers": ("登记簿上缺了七个编号", "0413 到 0419，只有日期，没有内容。",
                "林知秋把一批「不可靠」的种子藏了起来，没有登记。"),
    "bronze": ("墨铜叶的遗传", "林氏墨铜的叶子比普通铜叶深得多，像墨里掺了铜。它和普通铜叶草杂交以后会怎样，还不知道。",
               "墨铜 × 铜叶的 F2 没有按 3:1 分离，全是墨色。副突变：墨铜等位（B*）会把配对的普通铜叶等位（B）改写成自己。和绿叶（b）杂交时就正常分离。"),
    "chimera": ("斑叶草的白斑", "有些斑叶草的叶子上有大块白斑。白斑会不会传给后代、怎么传，还不知道。",
                "正交和反交的后代完全不同：白斑只跟着母本走。白斑来自质体（叶绿体）缺陷，质体只经卵细胞传递，不经花粉。"),
}

# ───────── 世界事件 ─────────
# at: "dawn"（当天开始）/ "dusk"（结束一天时）
EVENTS = [
    {"id": "e_intro", "day": 1, "at": "dawn", "eff": [
        "say:研究所在城北一片老苗圃里，四座温室、一栋两层小楼。你的工位在育苗室隔壁，桌上有一本空白的实验记录本、一支铅笔，和一张字条：「种子库的钥匙在所长那里。别动 D。——苏」",
        "doc:rules"]},
    {"id": "e_mixup", "day": 12, "at": "dawn", "need": ["special_cond:nursery_two_lots"], "eff": ["special:mixup", "flag:mixup_happened"]},
    {"id": "e_heat", "yearly": True, "day": 22, "at": "dawn", "eff": ["flag:heatwave", "say:热浪来了。主温室的温度计早上九点就过了三十度。老岑把所有的遮阳网都拉上了，「顶不住，这三天你自己看着办。」"]},
    {"id": "e_heat_end", "yearly": True, "day": 25, "at": "dawn", "eff": ["unflag:heatwave", "say:下了一场雷阵雨，热浪过去了。"]},
    {"id": "e_bees", "yearly": True, "day": 26, "at": "dawn", "eff": ["flag:bees", "say:一群熊蜂从坏了的纱窗钻进了主温室，在花上爬来爬去。老岑说三天以内补好纱窗。——没套袋的花，这几天会被乱授粉。"]},
    {"id": "e_bees_end", "yearly": True, "day": 29, "at": "dawn", "eff": ["unflag:bees", "say:纱窗补好了。熊蜂被小满一只一只用纸杯请了出去。"]},
    {"id": "e_audit", "day": 21, "at": "dusk", "eff": ["special:audit"]},
    {"id": "e_cert", "day": 28, "at": "dusk", "eff": ["special:cert"]},
    {"id": "e_freezer", "day": 31, "at": "dawn", "choice": {
        "text": "早上一进门就听见种子库的冰柜在报警：压缩机坏了，柜里已经十五度。修要两天。",
        "opts": [
            {"label": "花 200 元租一台临时冰柜，马上转移（耗时 2 小时）", "need": ["funds>=200"], "eff": ["funds:-200", "special:spend:120", "say:你和小满一箱一箱地把种子袋搬进了临时冰柜。手冻僵了，种子没事。"]},
            {"label": "把种子搬到冷室里将就两天（耗时 1 小时，有一点损失）", "need": [], "eff": ["special:spend:60", "special:seedbank_hit:0.08", "say:冷室没有冰柜冷，但总比十五度好。"]},
            {"label": "等它修好", "need": [], "eff": ["special:seedbank_hit:0.25", "say:两天以后冰柜修好了。种子库里的种子，活力都掉了一截。"]},
        ]}},
    {"id": "e_archive_leak", "day": 33, "at": "dawn", "choice": {
        "text": "苏姨打电话来：档案室漏水了，最下面一层的账本泡在水里。她一个人搬不过来。",
        "opts": [
            {"label": "放下手里的事去帮忙（耗时 3 小时）", "need": [], "eff": ["special:spend:180", "trust:su:+1", "mem:su:leak:档案室漏水那天你来帮我搬账本", "doc:lin_p5",
                                                       "say:你们把账本一本一本摊在走廊的暖气片上。有一本里夹着几页不属于任何账本的纸，字是林知秋的。苏姨看了一眼，把它递给你：「你拿着吧。」"]},
            {"label": "让小满去帮忙", "need": [], "eff": ["say:小满去了。中午回来，裤腿全湿了，说救下来大半。", "trust:xiaoman:+1"]},
            {"label": "今天走不开", "need": [], "eff": ["trust:su:-1", "say:苏姨说没事。下午你路过档案室，看见她一个人跪在地上，用吹风机一页一页地吹。"]},
        ]}},
    {"id": "e_corridor", "day": 35, "at": "dawn", "eff": ["special:corridor"]},
    {"id": "e_openday", "yearly": True, "day": 38, "at": "dawn", "choice": {
        "text": "开放日。来了很多带孩子的家长。闻所长让每个研究员拿出点东西来展示。",
        "opts": [
            {"label": "展示你的收藏温室（耗时 3 小时）", "need": ["special_cond:collection_any"], "eff": ["special:spend:180", "special:openday_collection"]},
            {"label": "摆个摊卖朱点花的苗（每株 15 元；只卖品系的小苗，不动实验材料）", "need": [], "eff": ["special:spend:180", "special:openday_sell"]},
            {"label": "躲在育苗室里干活", "need": [], "eff": ["say:你在育苗室里听着外面的喧闹声，移了一下午的苗。有个小孩隔着玻璃看了你很久。"]},
        ]}},
    {"id": "e_eval", "yearly": True, "day": 42, "at": "dusk", "eff": ["special:evaluation"]},
    {"id": "e_heater", "yearly": True, "day": 47, "at": "dawn", "choice": {
        "text": "夜里锅炉坏了。老岑在打电话叫人，说最快明天下午修好。主温室已经降到九度，热带温室十四度，还在掉。",
        "opts": [
            {"label": "把热带温室里怕冷的植物搬到收藏温室和育苗室（耗时 3 小时）", "need": [], "eff": ["special:spend:180", "special:heater:rescue"]},
            {"label": "花 300 元租电暖器，先保热带温室", "need": ["funds>=300"], "eff": ["funds:-300", "special:heater:heaters"]},
            {"label": "等修好", "need": [], "eff": ["special:heater:wait"]},
        ]}},
    {"id": "e_chi_leave1", "yearly": True, "day": 6, "at": "dawn", "eff": ["say:迟野进山了。他的工位上留了一张字条：「十几天回来。别动我的标本夹。」"]},
    {"id": "e_chi_back1", "day": 18, "at": "dawn", "eff": ["flag:chi_back1", "lot:WILD-RUB:30:迟野西山采集", "lot:WILD-MAC:20:迟野溪边采集",
                                                         "lot:WILD-NOC:16:迟野护林站采集", "lot:WILD-ODO:24:迟野盐场采集", "doc:chi_field",
                                                         "say:迟野回来了，晒得像一块烤馒头。种子库里多了四个野外批次。"]},
    {"id": "e_chi_back2", "day": 45, "at": "dawn", "eff": ["lot:WILD-FRI:24:迟野北坡雪线采集", "say:迟野第二次进山回来了，带回一袋雪线寒绒菊的种子，袋子上还有冰碴。"]},
    {"id": "e_luo_ask", "at": "dawn", "need": ["day>=16", "flag:luo_project_known"], "eff": ["flag:luo_asks", "say:骆青禾在你桌上留了一张条：「如果你有在冷室（10℃以下）也能开花的淡紫或浅色朱点花，借我一株当亲本。要有记录：花色和低温下的样子你都观察过。give <植株> luo」"]},
    {"id": "e_mo_borrow", "day": 20, "at": "dawn", "need": ["special_cond:aeris_any"], "choice": {
        "text": "莫博士来借一株听风草，要拿到他实验室做两个礼拜的声学实验。「我会好好照顾它。我保证。」",
        "opts": [
            {"label": "借给他（他挑一株听风草）", "need": [], "eff": ["special:mo_borrow", "trust:mo:+1", "mem:mo:borrow:你借我听风草做实验"]},
            {"label": "不借", "need": [], "eff": ["trust:mo:-1", "say:「好吧。」莫博士说，「我理解。」他看起来不太理解。"]},
        ]}},
    {"id": "e_mo_return", "day": 34, "at": "dawn", "need": ["flag:mo_borrowed"], "eff": ["special:mo_return", "doc:mo_draft"]},
    {"id": "e_lin_reply", "day": None, "at": "dawn", "need": ["flag:letter_sent", "special_cond:lin_reply_due"], "eff": [
        "doc:lin_letter", "flag:lin_coming", "special:mark_day:reply_day", "say:有一封寄给你的信，信封上的字你已经很熟悉了。"]},
    {"id": "e_lin_visit", "day": None, "at": "dawn", "need": ["flag:lin_coming", "special_cond:lin_visit_due"], "eff": [
        "flag:lin_here", "met:lin", "special:mark_day:visit_day",
        "say:早上，一个白头发的老人站在研究所门口，手里拿着一张很旧的门卡。门卡早就不能用了。小满去给他开了门。"]},
    {"id": "e_lin_leave", "day": None, "at": "dawn", "need": ["flag:lin_here", "special_cond:lin_leave_due"], "eff": [
        "unflag:lin_here", "flag:lin_visited", "say:林知秋走了。他在 D 温室的门框上，用铅笔写了一个日期。"]},
    {"id": "e_year", "yearly": True, "day": 56, "at": "dusk", "eff": ["special:year_review"]},
    {"id": "e_luo_stop", "day": 46, "at": "dawn", "need": ["!flag:luo_helped"], "eff": ["flag:luo_paused", "log:骆青禾把冷蓝项目的标签从温室里撤了。她说「暂停」。"]},
]

# D 温室里能搜到的东西（search D）
SEARCH_D = [
    {"need": [], "say": "D 温室里很潮，地上长了一层苔藓。木架子上还摆着几十个空花盆，每个盆上都用铅笔写着编号，最大的是 0412。墙上钉着一张纸，被水泡得只剩一角。", "eff": ["doc:lin_p1"]},
    {"need": [], "say": "你在工作台的抽屉里找到一个笔记本，前面几页被老鼠啃了，剩下的字很小很密。", "eff": ["doc:lin_p2", "doc:lin_p3"]},
    {"need": [], "say": "花台的砖有一块是松的。你撬开它，下面是一个生了锈的铁皮饼干盒。盒里有七个牛皮纸小袋，袋上写着 0413 到 0419，还有一张纸条。",
     "eff": ["doc:lin_p4", "lot:CUP-LIN:9:D 温室花台下的铁盒（0413–0419），1998 年", "special:old_lot", "anomaly:numbers:2"]},
    {"need": [], "say": "D 温室角落里有一丛没人照顾的铜叶草，叶子黑得发亮。它不在任何登记簿上。", "eff": ["plant:CUP-LIN:D:mature:D 温室里没人登记的那丛"]},
]
SEARCH_IDLE = {
    "A": ["主温室的玻璃上爬着一只壁虎。", "你在花架底下找到一支铅笔，是林知秋那个年代的牌子。"],
    "B": ["热带温室里水汽很重，你的笔记本卷了边。"], "C": ["冷室的压缩机嗡嗡响。"],
    "N": ["育苗架底下有几个空穴盘。"], "D": ["D 温室里只剩苔藓和空花盆。"], "K": ["收藏温室很安静。"],
}

# 报告评分门槛
REPORT_MIN = 12
