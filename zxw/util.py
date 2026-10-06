# -*- coding: utf-8 -*-
"""小工具：时间戳、重新识别当前单词、读进度文字（朗读/拼写流程共用）"""
import time

import config
from . import actions, matcher, page


def ts():
    return time.strftime("%H:%M:%S")


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
