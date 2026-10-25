# -*- coding: utf-8 -*-
"""核心循环：盯屏 → 认词 → 只做当前模块（朗读 / 拼写）。

两个模块完全分开，一次只跑一个：
    python main.py run --mode reading     只做朗读
    python main.py run --mode spelling    只做拼写

当前模块做完、检测到另一个模块的题时，会像 apt 一样问：
    是否接着做拼写模块？[y/N]
加 -y 就自动继续。
"""
import re
import sys
import threading
import time

import config
from . import actions, matcher, page, reading, spelling, watcher
from .tts import Speaker
from .util import speech_text, ts

MODE_NAMES = {"reading": "朗读", "spelling": "拼写"}


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
        "  f=重填当前题  y/n=回答模块切换提示  h=帮助  q=退出")


def _handle_keys(kb, d, speaker, state, ctl):
    """state["result"] 给快捷键用；ctl 处理"是否继续另一个模块"的 y/n"""
    for cmd in kb.drain():
        if cmd == "q":
            raise KeyboardInterrupt
        if cmd == "y" and ctl.get("pending"):
            target = ctl.pop("pending")
            ctl["switch_to"] = target
            print(f"[{ts()}] 好，切换到{MODE_NAMES[target]}模块")
            continue
        if cmd == "n" and ctl.get("pending"):
            ctl.pop("pending")
            print(f"[{ts()}] 好，只做当前模块（按 q 退出）")
            continue
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


def _progress_numbers(texts):
    """从 "75/148" 这种进度文字里取出 (当前, 总数)"""
    for t in texts:
        m = re.fullmatch(r"(\d+)\s*/\s*(\d+)", t.strip())
        if m:
            return int(m.group(1)), int(m.group(2))
    return None


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


def run(d, items, mode="reading", auto_yes=False):
    """只跑一个模块。mode: reading / spelling"""
    if mode not in MODE_NAMES:
        mode = "reading"
    items = matcher.prepare(items)
    speaker = Speaker()
    kb = Keyboard() if (sys.stdin and sys.stdin.isatty()) else None

    print("=" * 60)
    print(f"本次模块: {MODE_NAMES[mode]}" + ("（-y：模块切换自动同意）" if auto_yes else ""))
    print("  当前模块做完、检测到另一个模块的题时，会问你要不要接着做 [y/N]")
    print(HELP)
    print("=" * 60)

    last_sig = None
    last_key = None
    state = {"result": None}
    ctl = {"pending": None, "switch_to": None}
    heard = []
    prompted = set()          # 已经提示过的模块，避免刷屏
    saw_end = False           # 进度到过 N/N
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
                prog = _progress_numbers(scr["texts"])
                if prog and prog[1] > 0 and prog[0] >= prog[1]:
                    saw_end = True

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
                        if phase in MODE_NAMES and phase != mode:
                            # 这是另一个模块的页面 → 当前模块这边没题了
                            other = MODE_NAMES[phase]
                            if phase not in prompted:
                                prompted.add(phase)
                                if auto_yes:
                                    print(f"[{ts()}] {MODE_NAMES[mode]}模块这边已经没题了"
                                          f" → 自动切换到{other}模块")
                                    mode = phase
                                    last_key = None
                                    last_sig = None        # 下一轮重新处理当前页
                                    continue
                                if kb:
                                    ctl["pending"] = phase
                                    print()
                                    print(f"[模块] 当前已经是{other}题"
                                          f"（{MODE_NAMES[mode]}模块应该做完了）。")
                                    print(f"[模块] 是否接着做{other}模块？[y/N]  "
                                          f"输 y 回车=继续，输 n 或直接回车=跳过")
                                    print()
                                else:
                                    print(f"[模块] 检测到{other}题，但这是非交互运行，"
                                          f"只做{MODE_NAMES[mode]}（想自动切换请加 -y）")
                        else:
                            key = (phase, word.lower())
                            if key != last_key:
                                last_key = key
                                _print_result(ranked)
                                if word and word not in heard:
                                    heard.append(word)
                                _act(d, phase, word, speaker, items)
                    else:
                        _print_result(ranked)
                        if saw_end:
                            print(f"[{ts()}] 进度已经到 N/N，这一页没有题目了 → 全部做完，退出。")
                            break

            if kb:
                _handle_keys(kb, d, speaker, state, ctl)
                if ctl.get("switch_to"):
                    mode = ctl.pop("switch_to")
                    last_key = None
                    last_sig = None        # 下一轮重新处理当前页
                    prompted.clear()
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
