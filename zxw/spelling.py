# -*- coding: utf-8 -*-
"""拼写流程 —— 和朗读流程完全分开，可以单独跑、单独调。

实测（2026-10-06 第 75/148 题）：
  - 题目给中文释义（tv_meaning），8 个字母格子（word_view），
    键盘是自绘的（ky_keyboard，画出来的，uiautomator 看不到按键）
  - 所以输入只能按坐标点键（坐标在 keyboard.py 里，实测值）
  - 提交按钮在右下角，文字是「确定」，提交后结果出来它会变成「下一题」

流程：重新识别 → 清空 → 逐字母敲 → 点「确定」→ 点「下一题」
（拼写环节默认不朗读，看着中文直接填；想让它读就改 config.SPEAK_IN_SPELLING）
"""
import time

import config
from . import actions, keyboard
from .util import fresh_word, progress_text, ts


def do_spelling(d, word, speaker, items):
    word = fresh_word(d, items, word)           # 填之前重新识别一遍
    print(f"[{ts()}] 拼写页: 识别到 {word} → 内置键盘敲入 → 确定 → 下一题")
    if not config.AUTO_FILL_ANSWER:
        print("           （自动填答已关：config.AUTO_FILL_ANSWER=False，自己拼）")
        return

    # 1) 先清空（不管有没有内容，点一下"清空"没副作用）
    if keyboard.clear_all(d):
        time.sleep(0.3)
    else:
        print("           [注意] 没找到拼写键盘（ky_keyboard），按 f 重试或手动拼")
        return

    # 2) 逐字母敲
    if not keyboard.type_word(d, word):
        print("           [注意] 有字符没敲进去，你手动补一下，或按 f 重试")
        return
    print(f"           已敲入 {word}")
    time.sleep(config.AFTER_FILL_WAIT)

    # 3) 确定 → 等结果 → 下一题（提交和翻页都带重试）
    before = progress_text(d)
    actions.submit_and_next(d)
    for i in range(4):
        time.sleep(1.0)
        after = progress_text(d)
        if after and before and after != before:
            print(f"           已翻到 {after}")
            return
        if i == 1:      # 还没翻页：结果页可能出得慢，再点一次"下一题"
            got = actions.find_and_click(d, config.NEXT_BUTTONS)
            if got:
                print(f"           再点一次『{got}』")
    print("           没确认到翻页，看一眼屏幕；不行按 n 手动点『下一题』")
