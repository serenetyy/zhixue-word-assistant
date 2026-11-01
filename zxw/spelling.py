# -*- coding: utf-8 -*-
"""拼写流程 —— 和朗读流程完全分开，可以单独跑、单独调。

实测（2026-10-06 第 75/148 题）：
  - 题目给中文释义（tv_meaning），字母格子（word_view），
    键盘是自绘的（ky_keyboard，画出来的，uiautomator 看不到按键）
  - 所以输入只能按坐标点键（坐标在 keyboard.py 里，实测值）
  - 提交按钮在右下角，文字是「确定」，提交后结果出来它会变成「下一题」

流程：读屏（释义 + 字母格数）→ 选词校正 → 清空 → 逐字母输入 → 读回校验
     → 点「确定」→ 点「下一题」
"""
import re
import time

import config
from . import actions, keyboard, matcher, page
from .util import progress_text, ts


def _letters(s):
    """只保留英文字母（小写），用于比较字母格内容"""
    return re.sub(r"[^a-z]", "", str(s).lower())


def _refine_word(texts, items, word, slot_count):
    """用字母格数量做一次安全的选词校正。

    只在前几名里存在"字数吻合"的候选、且与第一名得分接近时，才替换。
    （词组带空格时格子数可能不等于字母数，所以不做硬过滤）
    """
    if not texts or slot_count < 2:
        return word
    ranked = matcher.rank(texts, items, topk=3)
    if not ranked:
        return word
    top = ranked[0]
    if len(_letters(top["item"].get("word", ""))) == slot_count:
        return top["item"].get("word", word)
    same = [r for r in ranked[1:]
            if len(_letters(r["item"].get("word", ""))) == slot_count]
    if (len(same) == 1
            and same[0]["score"] >= config.MATCH_MIN_SCORE
            and top["score"] - same[0]["score"] <= 0.15):
        better = same[0]["item"].get("word", "")
        print(f"           按字母格数（{slot_count}）校正："
              f"{top['item'].get('word')} → {better}")
        return better
    return word


def do_spelling(d, word, items):
    # 1) 读一次屏幕：拿中文释义 + 字母格数量（提词与校验都用得上）
    texts, slot_count = None, 0
    try:
        scr = page.read_screen(d)
        texts = scr["texts"]
        slot_count = keyboard.slots_from_xml(scr["xml"])
    except Exception as e:
        print(f"           [提示] 读取屏幕失败（{e}），沿用上一步识别结果。")

    # 2) 字母格数量校对所选单词
    word = _refine_word(texts, items, word, slot_count)
    print(f"[{ts()}] 拼写页：识别到 {word}。")
    if not config.AUTO_FILL_ANSWER:
        print("           （自动填答未启用：config.AUTO_FILL_ANSWER=False，请手动拼写。）")
        return

    # 3) 一次取键盘位置：先清空再逐字母输入
    if not keyboard.type_word(d, word, clear_first=True):
        print("           [注意] 未找到拼写键盘（ky_keyboard），请手动输入。")
        return

    # 4) 读回字母格校验；不一致自动重输一次
    expected = _letters(word)
    typed = keyboard.read_slots(d)
    if typed is None:
        print("           （无法读取字母格内容，跳过输入校验）")
    elif typed.lower() != expected:
        print(f"           输入校验不一致（{typed!r}），重输一次。")
        keyboard.type_word(d, word, clear_first=True)
        typed2 = keyboard.read_slots(d)
        if typed2 is not None and typed2.lower() != expected:
            print(f"           [注意] 重输后仍不一致（{typed2!r}），请手动检查。")
    else:
        print("           输入校验通过。")

    print(f"           已输入 {word}，正在提交。")
    time.sleep(config.AFTER_FILL_WAIT)

    # 5) 提交 → 等结果 → 下一题（快速轮询）
    before = progress_text(d)
    actions.submit_and_next(d)
    for _ in range(8):
        time.sleep(0.3)
        after = progress_text(d)
        if after and before and after != before:
            print(f"           已进入下一题：{after}")
            return
    got = actions.find_and_click(d, config.NEXT_BUTTONS)
    if got:
        print(f"           再次点击「{got}」")
    for _ in range(6):
        time.sleep(0.4)
        after = progress_text(d)
        if after and before and after != before:
            print(f"           已进入下一题：{after}")
            return
    print("           未能确认翻页，请查看屏幕，并手动点击「下一题」。")
