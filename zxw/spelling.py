# -*- coding: utf-8 -*-
"""拼写流程 —— 和朗读流程完全分开，可以单独跑、单独调。

流程：重新识别 → 电脑朗读 → 把答案填进输入框 → 提交 → 下一题

填答案的具体策略在 actions.fill_answer 里（实测智学网拼写题很可能要用
App 内置键盘逐个字母点，脚本会先探测屏幕上有没有字母键盘）。
调试用：python main.py type 单词
"""
import time

import config
from . import actions
from .util import fresh_word, ts


def do_spelling(d, word, speaker, items):
    word = fresh_word(d, items, word)           # 填之前重新识别一遍
    print(f"[{ts()}] 拼写页: 朗读 {word} → 自动填入 → 提交 → 下一题")
    speaker.speak(word)
    speaker.wait()
    if not config.AUTO_FILL_ANSWER:
        print("           （自动填答已关：config.AUTO_FILL_ANSWER=False，自己拼）")
        return
    if actions.fill_answer(d, word):
        print(f"           已填入 {word}")
        time.sleep(config.AFTER_FILL_WAIT)
        actions.submit_and_next(d)
    else:
        print("           [注意] 没找到输入框/键盘，没填。你手动拼，或按 f 重试")
