# -*- coding: utf-8 -*-
"""智学网拼写页的"自绘键盘"（id=ky_keyboard）。

这个键盘是画出来的，uiautomator 看不到任何按键节点 —— 只能按坐标点。
下面的坐标是 2026-10-06 从截图里实测出来的（找每个键的深色字形中心），
存的是"相对键盘区域的 0~1 比例"，换分辨率也能用：
    x = 键盘左边缘 + x比例 × 键盘宽度
    y = 键盘上边缘 + y比例 × 键盘高度
键盘布局：qwertyuiop / asdfghjkl / ⇧zxcvbnm⌫ / 123 ? / ' ! - 清空
"""
import time
import xml.etree.ElementTree as ET

import config

_TEXT = "ky_keyboard"          # 键盘容器的 resource-id 后缀
_SLOTS = "word_view"           # 字母格子容器的 resource-id 后缀

# 每行的 y 比例（4 行均分）
_ROW_Y = {1: 0.125, 2: 0.375, 3: 0.625, 4: 0.875}

# 每个键：(行号, x 比例) —— 实测值
_KEYS = {
    "q": (1, 0.0685), "w": (1, 0.1648), "e": (1, 0.2611), "r": (1, 0.3593),
    "t": (1, 0.4519), "y": (1, 0.5500), "u": (1, 0.6463), "i": (1, 0.7426),
    "o": (1, 0.8389), "p": (1, 0.9352),

    "a": (2, 0.1157), "s": (2, 0.2130), "d": (2, 0.3074), "f": (2, 0.4056),
    "g": (2, 0.5000), "h": (2, 0.5981), "j": (2, 0.6907), "k": (2, 0.7907),
    "l": (2, 0.8870),

    "shift": (3, 0.0917),
    "z": (3, 0.2130), "x": (3, 0.3074), "c": (3, 0.4056), "v": (3, 0.5009),
    "b": (3, 0.5981), "n": (3, 0.6944), "m": (3, 0.7907),
    "backspace": (3, 0.9093),

    # 实测（2026-11-08 拼写页日志）：底排从左到右是 123 ? / ' ! - 清空，
    # 原来把 ' 和 ! 的横坐标标反了，导致 find one's way into 敲成 findone!swayinto
    "123": (4, 0.0898), "?": (4, 0.2259), "/": (4, 0.3630), "'": (4, 0.5009),
    "!": (4, 0.6370), "-": (4, 0.7741), "clear": (4, 0.9102),
}


def _find_kb(d, timeout=0.8):
    try:
        el = d(resourceIdMatches=f".*{_TEXT}$")
        if el.exists(timeout=timeout):
            return el
    except Exception:
        pass
    return None


def _keyboard_rect(d):
    el = _find_kb(d)
    if el is None:
        return None
    b = (el.info or {}).get("bounds") or {}
    if not all(k in b for k in ("left", "top", "right", "bottom")):
        return None
    return b["left"], b["top"], b["right"], b["bottom"]


def has_keyboard(d):
    """屏幕上有没有这个自绘键盘（拼写页才有的）"""
    return _keyboard_rect(d) is not None


def _tap(d, rect, label):
    item = _KEYS.get(str(label).lower())
    if item is None:
        return False
    row, xf = item
    l, t, r, b = rect
    d.click(int(l + (r - l) * xf), int(t + (b - t) * _ROW_Y[row]))
    time.sleep(config.KEY_CLICK_WAIT)
    return True


def tap_key(d, label):
    """按标签点一个键（q~p、shift、backspace、clear 等）"""
    rect = _keyboard_rect(d)
    return rect is not None and _tap(d, rect, label)


def slots_from_xml(xml):
    """数出拼写页字母格子的数量（找不到返回 0）。可用来校验词长。"""
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return 0
    for node in root.iter():
        if (node.get("resource-id") or "").endswith(_SLOTS):
            return sum(1 for child in node.iter() if child.get("clickable") == "true")
    return 0


def read_slots(d):
    """读取字母格里当前填入的内容（按顺序拼起来）。读不到返回 None。"""
    try:
        xml = d.dump_hierarchy()
        root = ET.fromstring(xml)
    except Exception:
        return None
    for node in root.iter():
        if (node.get("resource-id") or "").endswith(_SLOTS):
            letters = []
            for child in node.iter():
                if child is node:
                    continue
                t = (child.get("text") or "").strip()
                if t and child.get("clickable") == "true":
                    letters.append(t)
            return "".join(letters)
    return None


def type_word(d, word, clear_first=False, keep_punct=False):
    """按字母逐个点，把单词敲进去。有打不出的字符返回 False。

    clear_first=True 时先点一次「清空」（只取一次键盘位置，省一次查找）。
    词组里的空格直接忽略（"dig up" 就敲 digup，实测这样没问题）。
    keep_punct=True 时撇号/连字符也照着点（当页面把它们算进字母格时）。
    """
    rect = _keyboard_rect(d)
    if rect is None:
        return False
    if clear_first:
        _tap(d, rect, "clear")
        time.sleep(0.12)
    said_space = False
    for ch in str(word).lower():
        if ch.isalpha() and ch in _KEYS:
            if not _tap(d, rect, ch):
                print(f"[键盘] 打不出字符 {ch!r}")
                return False
        elif keep_punct and ch in ("'", "-") and ch in _KEYS:
            if not _tap(d, rect, ch):
                print(f"[键盘] 打不出字符 {ch!r}")
                return False
        elif ch == " ":
            if not said_space:
                print("[键盘] （词组，空格忽略，直接拼字母）")
                said_space = True
        else:
            print(f"[键盘] 忽略特殊字符 {ch!r}")
    return True


def clear_all(d):
    """点「清空」，把已输入的内容清掉"""
    return tap_key(d, "clear")
