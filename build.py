# -*- coding: utf-8 -*-
"""把 genetics.py + content.py + engine.py 打包成给 AI 玩家用的单文件 greenhouse_lab.py（盲玩封装）。

只是 base64 封装，让 AI 玩家「不小心瞄到也读不懂」，不是加密。
用法：python3 build.py
"""
import base64
import os

HERE = os.path.dirname(os.path.abspath(__file__))
SPLIT = "\n# ==== SPLIT ====\n"

HEADER = '''"""🌿 不太正常的植物研究所（The Slightly Abnormal Botanical Institute）· 盲玩版

【给 AI 玩家的说明】
你是刚进研究所的植物研究员。种子库、四座温室、一间育苗室、一间组培室、一群同事，
还有一些「不太正常」的植物。播种、照料、授粉、采种、观察、记录——遗传规律要你自己从数据里看出来。

    import greenhouse_lab as gl
    print(gl.cmd("help"))
    print(gl.cmd("status"))
    print(gl.cmd("talk wen; lots; plants"))   # 多条指令用 ; 隔开（最多 10 条）
    print(gl.cmd("end"))                      # 结束今天

⚠️ 请不要解码或查看下面的 _BLOB：那里面是完整的内部遗传表、事件时间表和剧情。
这只是盲玩用的 base64 封装，不是加密——请自觉当一个不知道答案的研究员，用观察、杂交和统计去找答案。
想维护游戏的人类，请看开发版的 genetics.py / content.py / engine.py。

接口：
  cmd("指令")                      返回文字
  new_game(seed=None, force=False) 开新局（已有进度要 force=True，旧档会先备份）
  set_save_path("路径.json")       指定存档位置（也可以用环境变量 GREENHOUSE_SAVE）
存档：默认是同目录的 greenhouse_save.json，每条有效指令后自动保存；重新 import 会接着玩。
"""
import base64 as _b64
import sys as _sys
import types as _types
_BLOB = (
'''

FOOTER = '''
)
_parts = _b64.b64decode(_BLOB).decode("utf-8").split(%r)
_gm = _types.ModuleType("_greenhouse_genetics")
exec(compile(_parts[0], "<genetics>", "exec"), _gm.__dict__)
_sys.modules["_greenhouse_genetics"] = _gm
exec(compile(_parts[1] + "\\n" + _parts[2], "<greenhouse_lab>", "exec"), globals())
del _BLOB, _parts
''' % SPLIT


def build():
    parts = []
    for name in ("genetics.py", "content.py", "engine.py"):
        with open(os.path.join(HERE, name), encoding="utf-8") as f:
            parts.append(f.read())
    code = SPLIT.join(parts)
    blob = base64.b64encode(code.encode("utf-8")).decode("ascii")
    out = os.path.join(HERE, "greenhouse_lab.py")
    with open(out + ".tmp", "w", encoding="utf-8") as f:
        f.write(HEADER)
        for i in range(0, len(blob), 76):
            f.write(f'    "{blob[i:i + 76]}"\n')
        f.write(FOOTER)
    os.replace(out + ".tmp", out)
    return len(code)


if __name__ == "__main__":
    print("built greenhouse_lab.py from", build(), "chars of source")
