# -*- coding: utf-8 -*-
"""页面操作：按文字找按钮并点击、判断当前阶段（朗读页/拼写页）、把答案填进输入框。

关于点击：智学网的按钮经常是「图标可点击 + 文字只是标签」，比如"点击录音"
这几个字本身 clickable=false，真正能点的是它上面那个圆形图标。所以点击逻辑是：
  文字精确/包含/描述匹配 → 节点本身可点击就点它
                        → 否则找它旁边（含包围它的）可点击节点，点那个图标
                        → 再不行才点文字自身的坐标
"""
import re
import time
import xml.etree.ElementTree as ET

import config

_BOUNDS_RE = re.compile(r"\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]")


# ---------------- 基本的找/点 ----------------

def _find_el(d, t, timeout=1.0):
    """按 精确文字 → 包含文字 → 描述包含 找节点"""
    for sel in (dict(text=t), dict(textContains=t), dict(descriptionContains=t)):
        try:
            el = d(**sel)
            if el.exists(timeout=timeout if sel.get("text") else 0.3):
                return el
        except Exception:
            continue
    return None


def _info_bounds(info):
    b = (info or {}).get("bounds") or {}
    if all(k in b for k in ("left", "top", "right", "bottom")):
        return b["left"], b["top"], b["right"], b["bottom"]
    return None


def _parse_bounds(s):
    m = _BOUNDS_RE.search(s or "")
    if not m:
        return None
    return tuple(int(x) for x in m.groups())


def clickable_nodes(xml):
    """控件树里所有 clickable=true 的节点坐标 [(l,t,r,b), ...]"""
    out = []
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return out
    for node in root.iter():
        if node.get("clickable") == "true":
            b = _parse_bounds(node.get("bounds"))
            if b:
                out.append(b)
    return out


def _pick_click_target(text_bounds, nodes, max_gap=90):
    """算出该点哪里，返回 (x, y)；没有合适的可点击邻居返回 None。

    text_bounds: (l, t, r, b) 文字节点的坐标
    nodes: clickable_nodes() 的结果
    max_gap: 图标和文字的间隙上限（图标在文字上方/下方，间隙很小才算它的按钮）
    """
    l, t, r, b = text_bounds
    cx, cy = (l + r) // 2, (t + b) // 2

    # 1) 被某个可点击节点包住（整行是个大按钮）→ 点文字中心
    for (nl, nt, nr, nb) in nodes:
        if nl <= cx <= nr and nt <= cy <= nb:
            return cx, cy

    # 2) 正上/正下方、水平有重叠、间隙很小的可点击节点（就是它那个图标）
    best, best_gap = None, None
    for (nl, nt, nr, nb) in nodes:
        if not (nl < r and nr > l):        # 水平方向要有重叠
            continue
        if nb <= t:                        # 图标在文字上方
            gap = t - nb
        elif nt >= b:                      # 图标在文字下方
            gap = nt - b
        else:
            continue
        if gap <= max_gap and (best_gap is None or gap < best_gap):
            best, best_gap = (nl, nt, nr, nb), gap
    if best:
        return (best[0] + best[2]) // 2, (best[1] + best[3]) // 2
    return None


def exists_any(d, candidates):
    """返回屏幕上第一个存在的候选文字（都没有则 None），不点击"""
    for t in candidates:
        try:
            if d(text=t).exists(timeout=0.2):
                return t
        except Exception:
            continue
    return None


def _find_by_id(d, suffix, timeout=0.5):
    """按 resource-id 后缀找控件（实测智学网的按钮都有 id，比文字稳）"""
    if not suffix:
        return None
    try:
        el = d(resourceIdMatches=f".*{re.escape(suffix)}$")
        if el.exists(timeout=timeout):
            return el
    except Exception:
        pass
    return None


def click_control(d, ids, texts, timeout=1.0):
    """点控件：优先按 resource-id，找不到再退回按文字。返回点到了什么（或 None）"""
    for suffix in ids or []:
        el = _find_by_id(d, suffix, timeout=timeout)
        if el is None:
            continue
        try:
            el.click()
            return f"id:{suffix}"
        except Exception as e:
            print(f"[点击] id:{suffix} 点击失败: {e}")
    got = find_and_click(d, texts or [], timeout=timeout)
    return f"文字:{got}" if got else None


def wait_for_text(d, candidates, timeout=20.0, interval=0.5):
    """等某个文字出现（比如评分完成后出现的"点击重录"）"""
    deadline = time.time() + timeout
    while True:
        got = exists_any(d, candidates)
        if got:
            return got
        if time.time() >= deadline:
            return None
        time.sleep(interval)


def find_and_click(d, candidates, timeout=1.0):
    """按候选顺序找按钮并点击，返回点到的文字；都没找到返回 None"""
    for t in candidates:
        el = _find_el(d, t, timeout=timeout)
        if el is None:
            continue
        try:
            info = el.info or {}
        except Exception:
            info = {}

        # 文字自己就能点 → 直接点
        if info.get("clickable"):
            try:
                el.click()
                return t
            except Exception as e:
                print(f"[点击] 「{t}」点击失败: {e}")

        # 文字只是标签 → 点它旁边那个图标
        tb = _info_bounds(info)
        if tb:
            try:
                target = _pick_click_target(tb, clickable_nodes(d.dump_hierarchy()))
            except Exception as e:
                target = None
                print(f"[点击] 分析控件树失败: {e}")
            if target:
                d.click(*target)
                return t

        # 兜底：点文字自身坐标
        try:
            el.click()
            return t
        except Exception as e:
            print(f"[点击] 「{t}」坐标点击也失败: {e}")
    return None


# ---------------- 阶段判断 ----------------

def classify_phase(texts, ranked):
    """当前是朗读页还是拼写页：reading / spelling / unknown

    判断顺序很重要：先看"提交"（拼写页的特征），"朗读/录音"放后面 ——
    拼写页上经常也有个小喇叭按钮，反过来认错会把拼写题整个跳过去。
    """
    if any(t in texts for t in config.SUBMIT_BUTTONS):
        return "spelling"
    if any(t in texts for t in config.READ_BUTTONS):
        return "reading"
    if ranked:
        top = ranked[0]
        if top["source"] == "拼写" and top["score"] >= 0.98:
            return "reading"      # 页面上直接摆着完整的英文单词 → 朗读题
        if top["source"] == "中文" and top["score"] >= config.MATCH_MIN_SCORE:
            return "spelling"     # 只给了中文 → 拼写题
    return "unknown"


# ---------------- 输入框 ----------------

def get_edittexts(d, limit=6):
    """列出页面上的输入框（调试用），返回 [(序号, 现有文字, 是否聚焦)]"""
    out = []
    for i in range(limit):
        try:
            el = d(className="android.widget.EditText", instance=i)
            if not el.exists(timeout=0.1):
                break
            info = el.info or {}
            out.append((i, info.get("text", ""), bool(info.get("focused", False))))
        except Exception:
            break
    return out


def _find_edittext(d):
    try:
        el = d(className="android.widget.EditText")
        if el.exists(timeout=0.8):
            return el
    except Exception:
        pass
    return None


def _find_key(d, texts):
    """在屏幕上找一个按键（精确文字 或 精确描述）"""
    for t in texts:
        for sel in (dict(text=t), dict(description=t)):
            try:
                el = d(**sel)
                if el.exists(timeout=0.15):
                    return el
            except Exception:
                continue
    return None


def has_screen_keyboard(d, probe="abcd"):
    """屏幕上像不像有个字母键盘（探几个字母键，凑够 3 个就算有）"""
    found = 0
    for ch in probe:
        if _find_key(d, [ch, ch.upper()]) is not None:
            found += 1
    return found >= 3


def type_via_screen_keyboard(d, word):
    """用屏幕上的字母键把单词敲进去（App 内置键盘 / 系统软键盘都适用）。

    每个字符都找到并点了才返回 True；中途缺键返回 False（可能敲了一半，
    上层会用 set_text 之类覆盖式重来）。
    """
    for ch in word.lower():
        if ch == " ":
            el = _find_key(d, ["空格", "space", "Space"])
        elif ch.isalpha():
            el = _find_key(d, [ch, ch.upper()])
        else:
            print(f"[填答] 单词里有特殊字符 {ch!r}，先跳过（可能要手动处理）")
            continue
        if el is None:
            print(f"[填答] 屏幕上找不到字母键 {ch!r}")
            return False
        el.click()
        time.sleep(config.KEY_CLICK_WAIT)
    return True


def _read_text(el):
    """读元素里的文字；读不到返回 None"""
    try:
        return el.get_text() or ""
    except Exception:
        return None


def fill_answer(d, word):
    """把答案填进输入框。成功返回 True。

    策略顺序（实测智学网拼写题很可能要走第 1 条）：
      1) 屏幕上有字母键盘 → 逐个字母点上去
      2) 标准输入框 → set_text（读回来验证）→ 点一下再 set_text
      3) 聚焦节点 send_keys
      4) 按提示文字找输入区
    """
    # 1) 内置键盘
    try:
        if has_screen_keyboard(d):
            if type_via_screen_keyboard(d, word):
                el = _find_edittext(d)
                got = _read_text(el) if el is not None else None
                if got is None or got.strip().lower() == word.lower():
                    return True
                print(f"[填答] 键盘敲完了但读回来是 {got!r}，继续试别的")
            else:
                print("[填答] 内置键盘没敲完，改用直接写入试试")
    except Exception as e:
        print(f"[填答] 内置键盘方式出错: {e}")

    # 2) 标准输入框
    el = _find_edittext(d)
    if el is not None:
        try:
            el.set_text(word)
            time.sleep(0.2)
            got = _read_text(el)
            if got is not None and got.strip().lower() == word.lower():
                return True          # 读回来确认写进去了才算成功
        except Exception as e:
            print(f"[填答] 直接写入失败: {e}")
        try:
            el.click()
            time.sleep(0.4)
            el.set_text(word)
            time.sleep(0.2)
            got = _read_text(el)
            if got is None or got.strip().lower() == word.lower():
                return True
        except Exception as e:
            print(f"[填答] 点击后再写也失败: {e}")

    # 3) 聚焦节点直接发按键
    try:
        if d(focused=True).exists(timeout=0.3):
            d.send_keys(word, clear=True)
            return True
    except Exception as e:
        print(f"[填答] send_keys 失败: {e}")

    # 4) 按提示文字找输入区
    for hint in config.INPUT_HINTS:
        try:
            el2 = d(textContains=hint)
            if el2.exists(timeout=0.2):
                el2.click()
                time.sleep(0.4)
                el2.set_text(word)
                return True
        except Exception:
            continue
    return False


def submit_and_next(d, tries=3):
    """点"提交" → 等 → 点"下一题"（会重试几轮，等结果页慢慢渲染出来）。

    页面提交后自动跳转、找不到"下一题"，属正常情况。
    返回：是否点到过"提交"。
    """
    got_submit = find_and_click(d, config.SUBMIT_BUTTONS)
    if not got_submit:
        print("[流程] 没找到『提交』按钮，没提交")
        return False
    time.sleep(config.AFTER_SUBMIT_WAIT)
    for _ in range(tries):
        got_next = find_and_click(d, config.NEXT_BUTTONS, timeout=0.5)
        if got_next:
            print(f"[流程] 已提交并点了『{got_next}』")
            return True
        time.sleep(0.8)
    print("[流程] 提交了但一直没找到『下一题』（可能自动跳了；不行按 n 手动点）")
    return True
