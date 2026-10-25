# -*- coding: utf-8 -*-
"""本地自测：不连设备也能跑。

覆盖：列表解析 / 模糊匹配 / 状态栏噪音过滤 / 朗读-拼写阶段判断。
运行: python tests/test_matcher.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 输出被重定向到文件/管道时用 UTF-8，免得音标字符在 GBK 控制台里报错
if not sys.stdout.isatty():
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

import config
from zxw import actions, capture, matcher
from zxw import page as page_mod

FAILED = []


def check(name, cond, extra=""):
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f"  （{extra}）" if extra else ""))
    if not cond:
        FAILED.append(name)


print("== 1. 列表页解析 ==")
texts = [
    "单词表",
    "apple",
    "/ˈæpl/",
    "n. 苹果；苹果树",
    "banana",
    "n. 香蕉",
    "electricity /ɪˌlekˈtrɪsəti/ n. 电；电能；电力",
    "Unit 1 词汇",
]
items = capture.parse_items(texts)
words = [it["word"] for it in items]
print("   解析结果:")
for it in items:
    print("     ", it)

check("解析出 3 个词", len(items) == 3, str(words))
apple = next((it for it in items if it["word"] == "apple"), {})
check("apple 拿到音标", apple.get("phonetic") == "ˈæpl", str(apple))
check("apple 拿到释义", "苹果" in apple.get("cn", ""), str(apple))
ele = next((it for it in items if it["word"] == "electricity"), {})
check("一行里同时含单词+音标+中文也能拆出来", ele.get("cn", "").endswith("电力"), str(ele))
check("词性标注 n. 不会被当成单词", "n" not in [w.lower() for w in words])

print()
print("== 2. 模糊匹配 ==")
prepared = matcher.prepare(capture.parse_items(texts))


def top1(q):
    r = matcher.rank([q], prepared)
    return r[0] if r else None


cases = [
    ("苹果", "apple"),            # 完全一致
    ("苹果树", "apple"),          # 多义项之一
    ("香蕉", "banana"),
    ("电；电力", "electricity"),  # 义项写法不完全一样
    ("电能", "electricity"),
    ("/ˈæpl/", "apple"),          # 音标信号
    ("a _ _ l e", "apple"),       # 带空位的拼写提示
    ("苹果树上的苹果", "apple"),   # 题干式长句
]
for q, want in cases:
    r = top1(q)
    got = r["item"]["word"] if r else "(无)"
    ok = got == want and r and r["score"] >= config.MATCH_MIN_SCORE
    check(f"{q!r} → {want}", ok,
          f"实际 {got} {r['score'] if r else 0:.2f} ({r['source'] if r else '-'})")

r = matcher.rank(["今天天气不错", "下一页"], prepared)
check("无关文字匹配不到词", not r or r[0]["score"] < config.MATCH_MIN_SCORE,
      f"最高 {r[0]['score'] if r else 0:.2f}")

print()
print("== 3. 状态栏噪音过滤 ==")
# 这段 XML 是按你模拟器上真实 dump 的结构缩写的
xml = """<hierarchy rotation="0">
<node package="com.android.systemui" class="android.widget.TextView" text="5:23"/>
<node package="com.android.systemui" class="android.widget.TextView" text="下午5:23"/>
<node package="com.android.systemui" class="android.widget.ImageView" text="内容下载管理器通知：3E41898CFC25A61DB9A695B21A9F9139.apk"/>
<node package="com.android.systemui" class="android.widget.FrameLayout" text="WLAN 信号满格。"/>
<node package="com.android.systemui" class="android.widget.LinearLayout" text="正在充电，已完成 100%。"/>
<node package="com.iflytek.elpmobile.student" class="android.widget.TextView" text="barren"/>
<node package="com.iflytek.elpmobile.student" class="android.widget.TextView" text="['bærən] adj. 贫瘠的，不毛的；不结果实的"/>
</hierarchy>"""
clean = page_mod.clean_pairs(page_mod.texts_from_xml(xml))
print("   过滤后:", clean)
check("状态栏时间被过滤", "5:23" not in clean and "下午5:23" not in clean)
check("通知/充电/信号被过滤",
      not any(("满格" in t or "充电" in t or "apk" in t) for t in clean), str(clean))
check("正文文字保留", len(clean) == 2 and clean[0] == "barren", str(clean))

# 万一有噪音漏过了页面过滤，匹配层也要挡住（"信号"是真单词，不能误伤它）
noisy = matcher.prepare([{"word": "signal", "phonetic": "ˈsɪɡnəl", "cn": "n. 信号；标志"}])
r = matcher.rank(["WLAN 信号满格。"], noisy)
check("漏网噪音不会误匹配（但『信号』本身还能查）",
      (not r or r[0]["score"] < config.MATCH_MIN_SCORE)
      and matcher.rank(["信号"], noisy)[0]["item"]["word"] == "signal")

print()
print("== 4. 朗读页 / 拼写页 判断 ==")
check("有『提交』→ 拼写页", actions.classify_phase(["提交", "贫瘠的，不毛的"], []) == "spelling")
check("有『朗读』→ 朗读页", actions.classify_phase(["朗读", "下一题", "barren"], []) == "reading")
check("『提交』优先级高于『朗读』（拼写页也可能有喇叭按钮）",
      actions.classify_phase(["朗读", "提交"], []) == "spelling")
check("只给中文 → 拼写页",
      actions.classify_phase(["贫瘠的，不毛的"],
                             [{"item": {"word": "barren"}, "score": 0.95, "source": "中文"}]) == "spelling")
check("页面上直接有完整英文 → 朗读页",
      actions.classify_phase(["barren"],
                             [{"item": {"word": "barren"}, "score": 1.0, "source": "拼写"}]) == "reading")

print()
print("== 5. 按钮点击定位（文字只是标签，图标才可点）==")
# 坐标就是刚才从你模拟器真实 probe 下来的（单词跟读题那一页）
nodes = [(9, 72, 153, 204),        # 返回按钮
         (87, 1411, 273, 1597),    # 示范音图标
         (417, 1381, 663, 1627)]   # 录音图标

t = actions._pick_click_target((117, 1606, 243, 1663), nodes)
check("『示范音』→ 点它上面的图标", t == (180, 1504), str(t))
t = actions._pick_click_target((456, 1630, 624, 1687), nodes)
check("『点击录音』→ 点它上面的图标", t == (540, 1504), str(t))
t = actions._pick_click_target((84, 1770, 1032, 1890), nodes)
check("『下一题』→ 不会误点到录音图标（间隙太远，找不到邻居）", t is None, str(t))
t = actions._pick_click_target((522, 1339, 561, 1357),
                               [(500, 1300, 580, 1400)])   # 文字被可点击大按钮包住
check("文字被可点击节点包住 → 点文字中心", t == (541, 1348), str(t))


class _FakeTextEl:
    """模拟"点击重录"提示：前几次查询不存在（评分中），之后出现"""
    def __init__(self, dev):
        self.dev = dev

    def exists(self, timeout=0):
        self.dev.polls += 1
        return self.dev.polls >= self.dev.appear_at


class _FakeDev:
    def __init__(self, appear_at=3):
        self.polls = 0
        self.appear_at = appear_at

    def __call__(self, **sel):
        return _FakeTextEl(self)


fd2 = _FakeDev(appear_at=3)
r = actions.wait_for_text(fd2, ["点击重录"], timeout=3, interval=0.05)
check("等评分完成（『点击重录』出现才返回）",
      r == "点击重录" and fd2.polls >= 3, f"{r} polls={fd2.polls}")

fd3 = _FakeDev(appear_at=10 ** 9)
r = actions.wait_for_text(fd3, ["点击重录"], timeout=0.5, interval=0.05)
check("一直不出现 → 超时返回 None", r is None, str(r))

print()
print("== 6. 拼写页：内置键盘输入 ==")


class _AbsentEl:
    def exists(self, timeout=0):
        return False


class _KeyEl:
    def __init__(self, dev, ch):
        self.dev = dev
        self.ch = ch

    def exists(self, timeout=0):
        return True

    def click(self):
        self.dev.clicks.append(self.ch)


class _KeyDev:
    """假设备：屏幕上只有 keys 里的字母键"""

    def __init__(self, keys):
        self.keys = set(keys)
        self.clicks = []

    def __call__(self, **sel):
        t = sel.get("text") or sel.get("description")
        if t and t in self.keys:
            return _KeyEl(self, t)
        return _AbsentEl()


kd = _KeyDev(list("abcdefghijklmnopqrstuvwxyz"))
check("能认出屏幕上的字母键盘", actions.has_screen_keyboard(kd))
check("按顺序敲出 'cat'",
      actions.type_via_screen_keyboard(kd, "cat") and kd.clicks == ["c", "a", "t"],
      str(kd.clicks))

kd2 = _KeyDev(list("ab"))
check("缺字母键 → 返回 False", not actions.type_via_screen_keyboard(kd2, "cat"))
check("键太少不算键盘", not actions.has_screen_keyboard(_KeyDev(["a", "b"])))

print()
print("== 7. 拼写页自绘键盘（ky_keyboard）坐标 ==")
from zxw import keyboard as kb_mod


class _KbEl:
    def exists(self, timeout=0):
        return True

    @property
    def info(self):
        # 就是实测的键盘区域
        return {"bounds": {"left": 0, "top": 1164, "right": 1080, "bottom": 1740}}


class _KbDev:
    def __init__(self):
        self.clicks = []

    def __call__(self, **sel):
        return _KbEl()

    def click(self, x, y):
        self.clicks.append((x, y))


kd3 = _KbDev()
check("能认出 ky_keyboard", kb_mod.has_keyboard(kd3))
kb_mod.tap_key(kd3, "q")
check("q 键坐标 = (74, 1236)", kd3.clicks[-1] == (73, 1236), str(kd3.clicks[-1]))
kb_mod.tap_key(kd3, "l")
check("l 键坐标", kd3.clicks[-1] == (int(1080 * 0.8870), 1380), str(kd3.clicks[-1]))
kb_mod.tap_key(kd3, "backspace")
check("退格键坐标", kd3.clicks[-1] == (int(1080 * 0.9093), 1524), str(kd3.clicks[-1]))
kb_mod.tap_key(kd3, "clear")
check("清空键坐标 = (983, 1668)", kd3.clicks[-1] == (983, 1668), str(kd3.clicks[-1]))

kd3.clicks.clear()
kb_mod.type_word(kd3, "cat")
check("type_word('cat') 依次点 c-a-t", kd3.clicks == [
    (int(1080 * 0.4056), 1524), (int(1080 * 0.1157), 1380), (int(1080 * 0.4519), 1236),
], str(kd3.clicks))

print()
print("== 8. 朗读缩写展开（只影响发音，不影响拼写）==")
from zxw import util as util_mod

check("sth → something", util_mod.speech_text("sth") == "something")
check("词组里也能换（set sth aside）",
      util_mod.speech_text("set sth aside") == "set something aside")
check("大小写不敏感", util_mod.speech_text("Sth") == "something")
check("相似词不误伤（sthg 不变）", util_mod.speech_text("sthg") == "sthg")
check("sb's → somebody's", util_mod.speech_text("sb's") == "somebody's")

print()
print("== 9. 设置页参数读写（用临时副本，不动真配置）==")
import shutil
import tempfile

from zxw import uiserver

tmpdir = tempfile.mkdtemp()
cfg_copy = os.path.join(tmpdir, "config.py")
shutil.copy(
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.py"),
    cfg_copy,
)
vals = uiserver.load_values(cfg_copy)
check("能读出配置", vals.get("TTS_ENGINE") == "auto" and "MATCH_MIN_SCORE" in vals,
      str(vals.get("TTS_ENGINE")))
new_vals = uiserver.apply_changes(
    {"TTS_PIPER_LENGTH": 1.1, "MATCH_MIN_SCORE": 0.6, "RUN_MODE": "spelling"}, cfg_copy
)
check("数值写回", abs(new_vals["TTS_PIPER_LENGTH"] - 1.1) < 1e-9
      and abs(new_vals["MATCH_MIN_SCORE"] - 0.6) < 1e-9,
      str((new_vals["TTS_PIPER_LENGTH"], new_vals["MATCH_MIN_SCORE"])))
check("字符串写回", new_vals["RUN_MODE"] == "spelling", str(new_vals.get("RUN_MODE")))
src = open(cfg_copy, encoding="utf-8").read()
check("注释保留（TTS_PIPER_LENGTH 行尾注释还在）", ">1 更慢" in src)
shutil.rmtree(tmpdir, ignore_errors=True)

print()
print("== 10. 单模块 / 进度解析 ==")
from zxw import monitor as monitor_mod

check("进度解析 75/148", monitor_mod._progress_numbers(["单词拼写", "75/148", "上一题"]) == (75, 148))
check("进度解析（没有进度文字）", monitor_mod._progress_numbers(["abc", "1-2"]) is None)
check("模块名齐全", set(monitor_mod.MODE_NAMES) == {"reading", "spelling"})

print()
if FAILED:
    print(f"有 {len(FAILED)} 项失败: {FAILED}")
    sys.exit(1)
print("全部通过。")
