# -*- coding: utf-8 -*-
"""核心循环：盯屏 → 认词 → 按阶段分发给 朗读流程 / 拼写流程。

- 朗读流程在 reading.py，拼写流程在 spelling.py，两边互不影响
- 也可以只跑其中一个：
    python main.py run --mode reading    （只处理跟读题）
    python main.py run --mode spelling   （只处理拼写题）
"""
import sys
import threading
import time

import config
from . import actions, matcher, page, reading, spelling, watcher
from .tts import Speaker
from .util import speech_text, ts

MODE_NAMES = {"all": "朗读+拼写", "reading": "只跑朗读", "spelling": "只跑拼写"}


def _fmt_item(it):
    word = it.get("word", "?")
    ph = f" /{it['phonetic']}/" if it.get("phonetic") else ""
    cn = f"  {it['cn']}" if it.get("cn") else ""
    return f"{word}{ph}{cn}"


class Keyboard:
    """后台读命令行输入，避免主循环被 input() 卡住"""

    def __init__(self):
        self._cmds = []
        self._lock = threading.Lock()
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        for line in sys.stdin:
            with self._lock:
                self._cmds.append(line.strip().lower())

    def drain(self):
        with self._lock:
            cmds, self._cmds = self._cmds, []
        return cmds


HELP = ("快捷键: r=重读  1/2/3=试听候选  p=点『朗读』  s=点『提交』  n=点『下一题』"
        "  f=重填当前题  h=帮助  q=退出")


def _handle_keys(kb, d, speaker, state):
    """state["result"] 是当前题目的匹配结果，给快捷键用"""
    for cmd in kb.drain():
        if cmd == "q":
            raise KeyboardInterrupt
        if cmd == "h":
            print(HELP)
            continue
        result = state.get("result") or []
        if cmd == "r" and result:
            w = result[0]["item"].get("word")
            if w:
                speaker.speak(speech_text(w), force=True)
                print(f"[{ts()}] 重读 {w}")
        elif cmd in ("1", "2", "3") and result:
            i = int(cmd) - 1
            if i < len(result):
                w = result[i]["item"].get("word")
                if w:
                    speaker.speak(speech_text(w), force=True)
                    print(f"[{ts()}] 试听 {w}")
        elif cmd == "p":
            got = actions.find_and_click(d, config.READ_BUTTONS)
            print(f"[{ts()}] 点『朗读』: {got or '没找到'}")
        elif cmd == "s":
            got = actions.find_and_click(d, config.SUBMIT_BUTTONS)
            print(f"[{ts()}] 点『提交』: {got or '没找到'}")
        elif cmd == "n":
            got = actions.find_and_click(d, config.NEXT_BUTTONS)
            print(f"[{ts()}] 点『下一题』: {got or '没找到'}")
        elif cmd == "f" and result:
            w = result[0]["item"].get("word")
            if w:
                print(f"[{ts()}] 重填 {w}")
                if actions.fill_answer(d, w):
                    time.sleep(config.AFTER_FILL_WAIT)
                    actions.submit_and_next(d)
                else:
                    print("           没找到输入框/键盘")


def _print_result(ranked):
    """打印匹配结果，返回是否够确信（>= MATCH_MIN_SCORE）"""
    if not ranked or ranked[0]["score"] < config.MATCH_LOW_SCORE:
        print(f"[{ts()}] 页面变了，但没匹配到词（普通页面/提示页，忽略）")
        return False

    top = ranked[0]
    it = top["item"]
    if top["score"] >= config.MATCH_MIN_SCORE:
        print(f"[{ts()}] 认出来了: {_fmt_item(it)}")
        print(f"           得分 {top['score']:.2f}（按{top['source']}匹配）")
        others = ranked[1:4]
        if others:
            print("           其他候选: " + "；".join(
                f"{o['item']['word']} {o['score']:.2f}" for o in others))
            if top["score"] - others[0]["score"] < config.MATCH_MIN_MARGIN:
                print("           注意: 和第2名很接近，请留意")
        return True

    print(f"[{ts()}] 不太确定，可能候选: " + "；".join(
        f"{r['item']['word']}({r['score']:.2f})" for r in ranked[:3]))
    print("           分数不够，不会自动作答；可以按 1/2/3 试听，或按 f 强行填")
    return False


def _act(d, phase, word, speaker, items):
    if phase == "reading" and config.AUTO_READING_FLOW:
        reading.do_reading(d, word, speaker, items)
    elif phase == "spelling" and config.AUTO_FILL_ANSWER:
        spelling.do_spelling(d, word, speaker, items)
    else:
        if speaker.speak(speech_text(word)):
            print(f"           >> 朗读 {word}")
        if phase == "unknown":
            print("           [阶段没认出来] 只朗读不操作；按钮文字对不上就改 config 里的")
            print("           READ_BUTTONS / SUBMIT_BUTTONS / NEXT_BUTTONS")


def run(d, items, mode="all"):
    """mode: all=两个阶段都跑 / reading=只跑朗读 / spelling=只跑拼写"""
    items = matcher.prepare(items)
    speaker = Speaker()
    kb = Keyboard() if (sys.stdin and sys.stdin.isatty()) else None

    print("=" * 60)
    print(f"本次范围: {MODE_NAMES.get(mode, mode)}")
    print(f"  朗读页: {'自动（点录音→朗读→点波纹→下一题）' if config.AUTO_READING_FLOW else '只提示'}")
    print(f"  拼写页: {'自动填答（朗读→填入→提交→下一题）' if config.AUTO_FILL_ANSWER else '只提示，自己拼'}")
    print(HELP)
    print("=" * 60)

    last_sig = None
    last_key = None              # (阶段, 单词)：已处理过的题，防止同题重复动作
    state = {"result": None}     # 当前题匹配结果，给快捷键用
    heard = []
    try:
        while True:
            scr = page.read_screen(d)
            if scr["sig"] != last_sig:
                # 页面变了：先等它稳定，再重新读一遍，避免抓到过渡状态
                time.sleep(config.PAGE_SETTLE)
                scr = page.read_screen(d)
                last_sig = scr["sig"]

                watcher.check(d, scr["texts"])
                ranked = matcher.rank(scr["texts"], items, topk=8)

                strong = [r for r in ranked if r["score"] >= 0.9]
                if len(strong) >= 4:
                    print(f"[{ts()}] 看着像单词列表页（一次匹配到 {len(strong)} 个词），跳过")
                    state["result"] = None
                    last_key = None
                else:
                    state["result"] = ranked
                    top = ranked[0] if ranked else None
                    if top and top["score"] >= config.MATCH_MIN_SCORE:
                        phase = actions.classify_phase(scr["texts"], ranked)
                        word = top["item"].get("word", "")
                        key = (phase, word.lower())
                        if key != last_key:
                            last_key = key
                            _print_result(ranked)
                            if word and word not in heard:
                                heard.append(word)
                            if mode != "all" and phase in ("reading", "spelling") and phase != mode:
                                other = "拼写" if phase == "spelling" else "朗读"
                                print(f"           （这是{other}页，本次{MODE_NAMES.get(mode, mode)}，不动它）")
                            else:
                                _act(d, phase, word, speaker, items)
                        # key 相同 = 还是刚才那道题，静默
                    else:
                        _print_result(ranked)

            if kb:
                _handle_keys(kb, d, speaker, state)
            time.sleep(config.POLL_INTERVAL)
    except KeyboardInterrupt:
        pass
    finally:
        print("\n" + "=" * 60)
        if heard:
            print(f"本次共处理 {len(heard)} 个词: " + ", ".join(heard))
        else:
            print("本次没有处理到单词。")
        print("=" * 60)
