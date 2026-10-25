# -*- coding: utf-8 -*-
"""核心循环：盯屏 → 认词 → 只做当前模块（朗读 / 拼写）。

一次只运行一个模块：
    python main.py run --mode reading     朗读模块
    python main.py run --mode spelling    拼写模块

当前模块完成后（检测到另一个模块的题目）：
- 默认：暂停自动操作，并提供「退出 / 暂停」两个选项；
- 加 -y：自动切换到另一个模块（自动流转）。
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

MODE_HELP = {
    "reading": "快捷键：r=重新朗读本题（录音 → 朗读 → 结束录音）  h=帮助  q=退出",
    "spelling": "快捷键：h=帮助  q=退出",
}


def _fmt_item(it):
    word = it.get("word", "?")
    ph = f" /{it['phonetic']}/" if it.get("phonetic") else ""
    cn = f"  {it['cn']}" if it.get("cn") else ""
    return f"{word}{ph}{cn}"


class Keyboard:
    """后台读命令行输入，避免主循环被 input() 阻塞"""

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


def _handle_keys(kb, d, speaker, state, ctl, mode, items):
    """快捷键。state["result"] 为当前题目的匹配结果；ctl 管理退出/暂停选择。"""
    for cmd in kb.drain():
        if cmd == "q":
            raise KeyboardInterrupt

        # 模块完成后的「1 退出 / 2 暂停」
        if ctl.get("pending_choice"):
            if cmd == "1":
                print(f"[{ts()}] 已选择退出运行。")
                raise KeyboardInterrupt
            if cmd == "2":
                ctl["pending_choice"] = None
                ctl["paused"] = True
                print(f"[{ts()}] 已暂停监听，不再自动操作（按 q 退出）。")
                continue
            if cmd:
                print("           请输入 1 或 2 后回车。")
            continue

        if cmd == "h":
            print(MODE_HELP[mode])
            continue

        # 朗读模块专属快捷键
        if cmd == "r" and mode != "reading":
            print("           （当前为拼写模块，无此操作）")
            continue

        result = state.get("result") or []
        if cmd == "r":
            if result:
                print(f"[{ts()}] 重新执行朗读流程（以当前屏幕识别结果为准）。")
                reading.do_reading(d, result[0]["item"].get("word", ""), speaker, items)
            else:
                print("           当前未识别到单词，无法重新朗读。")


def _progress_numbers(texts):
    """从 "75/148" 这类进度文字中提取 (当前, 总数)"""
    for t in texts:
        m = re.fullmatch(r"(\d+)\s*/\s*(\d+)", t.strip())
        if m:
            return int(m.group(1)), int(m.group(2))
    return None


def _print_result(ranked):
    """打印匹配结果，返回是否达到可信阈值（>= MATCH_MIN_SCORE）"""
    if not ranked or ranked[0]["score"] < config.MATCH_LOW_SCORE:
        print(f"[{ts()}] 页面已变化，未匹配到单词（普通页面或提示页，忽略）。")
        return False

    top = ranked[0]
    if top["score"] >= config.MATCH_MIN_SCORE:
        print(f"[{ts()}] 已识别：{_fmt_item(top['item'])}")
        print(f"           得分 {top['score']:.2f}（按{top['source']}匹配）")
        others = ranked[1:4]
        if others:
            print("           候选：" + "；".join(
                f"{o['item']['word']} {o['score']:.2f}" for o in others))
            if top["score"] - others[0]["score"] < config.MATCH_MIN_MARGIN:
                print("           提示：与第 2 名得分接近，请留意。")
        return True

    print(f"[{ts()}] 置信度不足，候选：" + "；".join(
        f"{r['item']['word']}({r['score']:.2f})" for r in ranked[:3]))
    print("           得分不足，不会自动操作；按 h 查看可用操作。")
    return False


def _act(d, phase, word, get_speaker, items):
    if phase == "reading" and config.AUTO_READING_FLOW:
        reading.do_reading(d, word, get_speaker(), items)
    elif phase == "spelling" and config.AUTO_FILL_ANSWER:
        spelling.do_spelling(d, word, items)
    else:
        if phase == "spelling":
            print("           （拼写页：自动填答未启用，请手动输入）")
        else:
            if get_speaker().speak(speech_text(word)):
                print(f"           >> 朗读 {word}")
        if phase == "unknown":
            print("           [阶段未识别] 仅朗读，不自动操作；")
            print("           如按钮文字不匹配，请修改 config.py 的 READ_BUTTONS /")
            print("           SUBMIT_BUTTONS / NEXT_BUTTONS。")
    return phase


def run(d, items, mode="reading", auto_yes=False):
    """只运行一个模块。mode: reading / spelling"""
    if mode not in MODE_NAMES:
        mode = "reading"
    items = matcher.prepare(items)
    speaker = Speaker() if mode == "reading" else None   # 拼写模块不初始化语音

    def get_speaker():
        nonlocal speaker
        if speaker is None:
            speaker = Speaker()
        return speaker

    kb = Keyboard() if (sys.stdin and sys.stdin.isatty()) else None

    print("=" * 60)
    print(f"本次运行模块：{MODE_NAMES[mode]}")
    if auto_yes:
        print("说明：当前模块完成后，自动切换到另一模块（自动流转）。")
    else:
        print("说明：当前模块完成后，可选择退出或暂停。")
    print(MODE_HELP[mode])
    print("=" * 60)

    last_sig = None
    last_key = None
    state = {"result": None}
    ctl = {"pending_choice": None, "paused": False}
    heard = []
    prompted = set()          # 已提示过的模块，避免重复
    saw_end = False           # 进度是否到达 N/N
    try:
        while True:
            if ctl["paused"]:
                if kb:
                    _handle_keys(kb, d, speaker, state, ctl, mode, items)
                time.sleep(config.POLL_INTERVAL)
                continue

            scr = page.read_screen(d)
            if scr["sig"] != last_sig:
                # 页面变化：先等待稳定，再读取一次
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
                    print(f"[{ts()}] 页面疑似单词列表，跳过（匹配到 {len(strong)} 个词）。")
                    state["result"] = None
                    last_key = None
                else:
                    state["result"] = ranked
                    top = ranked[0] if ranked else None
                    if top and top["score"] >= config.MATCH_MIN_SCORE:
                        phase = actions.classify_phase(scr["texts"], ranked)
                        word = top["item"].get("word", "")
                        if phase in MODE_NAMES and phase != mode:
                            # 当前模块已完成：出现另一模块的题目
                            if phase not in prompted:
                                prompted.add(phase)
                                if auto_yes:
                                    print(f"[{ts()}] {MODE_NAMES[mode]}模块已完成，"
                                          f"自动切换到{MODE_NAMES[phase]}模块。")
                                    mode = phase
                                    last_key = None
                                    last_sig = None
                                    continue
                                if kb:
                                    ctl["pending_choice"] = phase
                                    print()
                                    print("=" * 60)
                                    print(f"当前模块（{MODE_NAMES[mode]}）已完成："
                                          f"检测到{MODE_NAMES[phase]}模块的题目。")
                                    print("自动操作已暂停，请选择：")
                                    print("  1  退出运行（返回启动菜单后可切换模块）")
                                    print("  2  暂停监听（保持窗口，不再自动操作）")
                                    print("请输入 1 或 2 后回车。")
                                    print("=" * 60)
                                else:
                                    print(f"[{ts()}] 当前模块已完成；非交互运行不自动切换"
                                          f"（使用 -y 可启用自动流转）。")
                        else:
                            key = (phase, word.lower())
                            if key != last_key:
                                last_key = key
                                _print_result(ranked)
                                if word and word not in heard:
                                    heard.append(word)
                                _act(d, phase, word, get_speaker, items)
                    else:
                        _print_result(ranked)
                        if saw_end:
                            print(f"[{ts()}] 进度已到 N/N，当前页面无题目：本次运行结束。")
                            break

            if kb:
                _handle_keys(kb, d, speaker, state, ctl, mode, items)
            time.sleep(config.POLL_INTERVAL)
    except KeyboardInterrupt:
        pass
    finally:
        print("\n" + "=" * 60)
        if heard:
            print(f"本次共处理 {len(heard)} 个词：" + "、".join(heard))
        else:
            print("本次未处理到单词。")
        print("=" * 60)
