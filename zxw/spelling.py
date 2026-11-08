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


def _letters_with_punct(s):
    """字母 + 撇号/连字符（这两种字符键盘上也有键，可能占一格）"""
    return re.sub(r"[^a-z'\-]", "", str(s).lower())


def _slot_matches(word, slot_count):
    """单词长度是否和页面的字母格数吻合。

    正常情况按字母数算；词组里的撇号/连字符如果也占格，按带标点的长度算
    （键盘上只有字母、' 和 -，空格不占格）。
    """
    plain = _letters(word)
    if len(plain) == slot_count:
        return True
    full = _letters_with_punct(word)
    return len(full) == slot_count and len(full) > len(plain)


def _refine_word(texts, items, word, slot_count):
    """用字母格数量做选词校正。

    字母格数是页面给的硬线索（几个字母就几个格），比模糊得分可靠：
    第一名跟格子数不符时，只要候选里有"等长且达到阈值"的词，就换过去。
    """
    if not texts:
        return word
    ranked = matcher.rank(texts, items, topk=10)
    if not ranked:
        return word
    top = ranked[0]
    top_word = top["item"].get("word", "")
    if slot_count < 2 or _slot_matches(top_word, slot_count):
        return top_word or word
    same = [r for r in ranked[1:]
            if _slot_matches(r["item"].get("word", ""), slot_count)
            and r["score"] >= config.MATCH_MIN_SCORE]
    if not same:
        return top_word or word
    better = max(same, key=lambda r: r["score"])["item"].get("word", "")
    if better and better.lower() != top_word.lower():
        print(f"           按字母格数（{slot_count}）校正：{top_word} → {better}")
    return better or top_word or word


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

    # 2.5) 兜底：长度和格子数对不上时，填了也一定是错的，不如不填
    if slot_count >= 2 and not _slot_matches(word, slot_count):
        print(f"           [注意] 「{word}」与页面字母格（{slot_count} 格）对不上，"
              f"为避免答错，本题不自动填写。")
        print("           多半是词表和这一轮的题目不一致：模拟器停在【单词列表】页后，"
              "回到菜单用 [1] 重新抓取单词表。")
        return

    # 3) 一次取键盘位置：先清空再逐字母输入
    plain = _letters(word)
    full = _letters_with_punct(word)
    use_punct = slot_count >= 2 and len(full) > len(plain) and len(full) == slot_count
    if not keyboard.type_word(d, word, clear_first=True, keep_punct=use_punct):
        print("           [注意] 未找到拼写键盘（ky_keyboard），请手动输入。")
        return

    # 4) 读回字母格校验；不一致自动重输一次
    expected = full if use_punct else plain
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
