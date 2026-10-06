# -*- coding: utf-8 -*-
"""智学网拼写页的"自绘键盘"（id=ky_keyboard）。

这个键盘是画出来的，uiautomator 看不到任何按键节点 —— 只能按坐标点。
下面的坐标是 2026-10-06 从截图里实测出来的（找每个键的深色字形中心），
存的是"相对键盘区域的 0~1 比例"，换分辨率也能用：
    x = 键盘左边缘 + x比例 × 键盘宽度
    y = 键盘上边缘 + y比例 × 键盘高度
键盘布局：qwertyuiop / asdfghjkl / ⇧zxcvbnm⌫ / 123?/!' － 清空
"""
import time

import config

_TEXT = "ky_keyboard"          # 键盘容器的 resource-id 后缀

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

    "123": (4, 0.0898), "?": (4, 0.2259), "/": (4, 0.3630), "!": (4, 0.5009),
    "'": (4, 0.6370), "-": (4, 0.7741), "clear": (4, 0.9102),
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


def type_word(d, word):
    """按字母逐个点，把单词敲进去。有打不出的字符返回 False。

    注：只处理英文字母；空格/连字符先跳过（遇到会提示）。
    """
    rect = _keyboard_rect(d)
    if rect is None:
        return False
    for ch in str(word).lower():
        if ch.isalpha() and ch in _KEYS:
            if not _tap(d, rect, ch):
                print(f"[键盘] 打不出字符 {ch!r}")
                return False
        elif ch == " ":
            print("[键盘] 这个单词带空格，键盘上没有空格键，先跳过")
        else:
            print(f"[键盘] 忽略特殊字符 {ch!r}")
    return True


def clear_all(d):
    """点「清空」，把已输入的内容清掉"""
    return tap_key(d, "clear")
