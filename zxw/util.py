# -*- coding: utf-8 -*-
"""小工具：时间戳、重新识别当前单词、读进度文字、朗读文本展开（两个流程共用）"""
import re
import time

import config
from . import actions, matcher, page


def ts():
    return time.strftime("%H:%M:%S")


def speech_text(word):
    """把词条里的缩写展开成能读的完整词（只为发音，不影响拼写）。

    "set sth aside" → "set something aside"；"sth" → "something"
    """
    if not word:
        return word
    out = str(word)
    # 长缩写先替换（"e.g." 要在 "etc" 之类之前）
    for key in sorted(config.SPEECH_EXPAND, key=len, reverse=True):
        out = re.sub(
            rf"(?<![A-Za-z]){re.escape(key)}(?![A-Za-z])",
            config.SPEECH_EXPAND[key],
            out,
            flags=re.IGNORECASE,
        )
    return out


def fresh_word(d, items, fallback):
    """重新读一遍屏幕、重新识别当前单词（每次朗读/填写前都做一遍，防止拿到旧词）"""
    try:
        scr = page.read_screen(d)
        ranked = matcher.rank(scr["texts"], items, topk=1)
        if ranked and ranked[0]["score"] >= config.MATCH_MIN_SCORE:
            return ranked[0]["item"].get("word") or fallback
    except Exception as e:
        print(f"           [重识别失败] {e}")
    return fallback


def progress_text(d):
    """取"N/148"这个进度文字，用来确认真的翻页了"""
    try:
        el = actions._find_by_id(d, "tv_progress", timeout=0.3)
        if el is not None:
            return (el.get_text() or "").strip()
    except Exception:
        pass
    return None
