# -*- coding: utf-8 -*-
"""核心循环：盯屏 → 认词 → 按阶段自动作答。

两个阶段分开处理：
  朗读页（reading）：点"点击录音" → 0.5s → 重新识别并朗读 → 1s
                    → 点屏幕中间空白结束录音 → 等"下一题"出现 → 点"下一题"
  拼写页（spelling）：从中文释义模糊匹配出单词 → 电脑朗读 → 自动填入 → 提交 → 下一题
"""
import sys
import threading
import time

import config
from . import actions, matcher, page, watcher
from .tts import Speaker


def _ts():
    return time.strftime("%H:%M:%S")


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
                speaker.speak(w, force=True)
                print(f"[{_ts()}] 重读 {w}")
        elif cmd in ("1", "2", "3") and result:
            i = int(cmd) - 1
            if i < len(result):
                w = result[i]["item"].get("word")
                if w:
                    speaker.speak(w, force=True)
                    print(f"[{_ts()}] 试听 {w}")
        elif cmd == "p":
            got = actions.find_and_click(d, config.READ_BUTTONS)
            print(f"[{_ts()}] 点『朗读』: {got or '没找到'}")
        elif cmd == "s":
            got = actions.find_and_click(d, config.SUBMIT_BUTTONS)
            print(f"[{_ts()}] 点『提交』: {got or '没找到'}")
        elif cmd == "n":
            got = actions.find_and_click(d, config.NEXT_BUTTONS)
            print(f"[{_ts()}] 点『下一题』: {got or '没找到'}")
        elif cmd == "f" and result:
            w = result[0]["item"].get("word")
            if w:
                print(f"[{_ts()}] 重填 {w}")
                if actions.fill_answer(d, w):
                    time.sleep(config.AFTER_FILL_WAIT)
                    actions.submit_and_next(d)
                else:
                    print("           没找到输入框")


def _print_result(ranked):
    """打印匹配结果，返回是否够确信（>= MATCH_MIN_SCORE）"""
    if not ranked or ranked[0]["score"] < config.MATCH_LOW_SCORE:
        print(f"[{_ts()}] 页面变了，但没匹配到词（普通页面/提示页，忽略）")
        return False

    top = ranked[0]
    it = top["item"]
    if top["score"] >= config.MATCH_MIN_SCORE:
        print(f"[{_ts()}] 认出来了: {_fmt_item(it)}")
        print(f"           得分 {top['score']:.2f}（按{top['source']}匹配）")
        others = ranked[1:4]
        if others:
            print("           其他候选: " + "；".join(
                f"{o['item']['word']} {o['score']:.2f}" for o in others))
            if top["score"] - others[0]["score"] < config.MATCH_MIN_MARGIN:
                print("           注意: 和第2名很接近，请留意")
        return True

    print(f"[{_ts()}] 不太确定，可能候选: " + "；".join(
        f"{r['item']['word']}({r['score']:.2f})" for r in ranked[:3]))
    print("           分数不够，不会自动作答；可以按 1/2/3 试听，或按 f 强行填")
    return False


def _fresh_word(d, items, fallback):
    """重新读一遍屏幕、重新识别当前单词（每次朗读前都做一遍，防止拿到旧词）"""
    try:
        scr = page.read_screen(d)
        ranked = matcher.rank(scr["texts"], items, topk=1)
        if ranked and ranked[0]["score"] >= config.MATCH_MIN_SCORE:
            return ranked[0]["item"].get("word") or fallback
    except Exception as e:
        print(f"           [重识别失败] {e}")
    return fallback


def _progress_text(d):
    """取"N/148"这个进度文字，用来确认真的翻页了"""
    try:
        el = actions._find_by_id(d, "tv_progress", timeout=0.3)
        if el is not None:
            return (el.get_text() or "").strip()
    except Exception:
        pass
    return None


def _wait_record_result(d, timeout):
    """等录音的评分结果：'scored'=通过了 / 'discarded'=被丢弃 / None=超时"""
    deadline = time.time() + timeout
    fresh_seen = 0
    while time.time() < deadline:
        if actions.exists_any(d, config.RECORD_DONE_TEXTS):
            return "scored"
        if actions.exists_any(d, config.RECORD_FRESH_TEXTS):
            fresh_seen += 1
            if fresh_seen >= 2:      # 连续两次看到"点击录音"才算真的被丢弃
                return "discarded"
        else:
            fresh_seen = 0
        time.sleep(0.6)
    return None


def _record_once(d, word, speaker, items, min_repeat=1):
    """重新识别 → 提前合成音频 → 点录音 → 朗读 → 点波纹结束录音。动作都点到了返回 True"""
    word = _fresh_word(d, items, word)          # 每次朗读前重新识别，不拿旧词
    speaker.prepare(word)                       # Edge 需要联网合成，先在录音窗口外备好
    repeat = max(min_repeat, speaker.repeat_fit(config.READ_RECORD_BUDGET))
    got = actions.click_control(d, [config.ID_RECORD], config.READ_BUTTONS)
    if not got:
        return False
    print(f"[{_ts()}] 朗读页: 点『录音』成功（{got}，读 {repeat} 遍）")
    time.sleep(config.READ_AFTER_CLICK_WAIT)

    speaker.speak(word, force=True, repeat=repeat)
    speaker.wait()                              # 等读完
    time.sleep(config.READ_AFTER_SPEAK_WAIT)

    # 结束录音：录音中提示是"点击波纹，结束录音"，点 layout_recording 那块面板。
    # 读一遍时录音常常自己提前结束（说完静音一会就收），点空属正常，不影响。
    stop = actions.click_control(d, [config.ID_RECORD_WAVE], ["点击波纹，结束录音"])
    print(f"           结束录音: {stop or '（录音已自行结束，正常）'}")
    time.sleep(config.AFTER_STOP_WAIT)
    return True


def _do_reading(d, word, speaker, items):
    """朗读页流程（实机校准版）：
    点录音 → 0.5s → 重新识别并朗读 → 1s → 点波纹结束录音
    → 等评分（没通过会自动重录，次数看 READ_RETRY_TIMES）→ 点"下一题"
    """
    scored = False
    for attempt in range(1 + max(0, config.READ_RETRY_TIMES)):
        if attempt:
            print(f"           自动重录（第 {attempt + 1} 遍，多读一遍更稳）...")
        # 第一次按配置读（默认1遍）；重录时至少读2遍，提高被评测通过的概率
        if not _record_once(d, word, speaker, items, min_repeat=1 if attempt == 0 else 2):
            print(f"[{_ts()}] 朗读页: 没找到录音按钮，只朗读不点击")
            speaker.speak(word, force=True)
            speaker.wait()
            return
        result = _wait_record_result(d, config.NEXT_BUTTON_WAIT)
        if result == "scored":
            scored = True
            print("           评分完成（录音已生效）")
            break
        if result == "discarded":
            print("           [注意] 这遍录音没过（读音不够清晰或没采到），重录一次")
            if attempt >= config.READ_RETRY_TIMES:
                print("           重录也没过。可以试着把 TTS_RATE 调慢（比如 125），或换嗓音")
        else:
            print(f"           等了 {config.NEXT_BUTTON_WAIT:.0f}s 还没出评分结果")
            break

    if not config.AUTO_CLICK_NEXT:
        return
    before = _progress_text(d)
    for _ in range(3):                       # 点"下一题"，没翻页就再试
        got2 = actions.click_control(d, [config.ID_NEXT], config.NEXT_BUTTONS)
        if not got2:
            print("           没找到『下一题』，按 n 手动点")
            return
        time.sleep(1.3)
        after = _progress_text(d)
        if after and after != before:
            print(f"           已翻到 {after}"
                  + ("" if scored else "（这题没录上，想补录可以点『上一题』回去）"))
            return
    print("           点了『下一题』但页面没翻，按 n 再试")


def _do_spelling(d, word, speaker, items):
    """拼写页：重新识别 → 读一遍 → 自动填入 → 提交 → 下一题"""
    word = _fresh_word(d, items, word)      # 填之前重新识别一遍
    print(f"[{_ts()}] 拼写页: 朗读 {word} → 自动填入 → 提交 → 下一题")
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
        print("           [注意] 没找到输入框，没填。你手动拼，或按 f 重试")


def _act(d, phase, word, speaker, items):
    if phase == "reading" and config.AUTO_READING_FLOW:
        _do_reading(d, word, speaker, items)
    elif phase == "spelling" and config.AUTO_FILL_ANSWER:
        _do_spelling(d, word, speaker, items)
    else:
        if speaker.speak(word):
            print(f"           >> 朗读 {word}")
        if phase == "unknown":
            print("           [阶段没认出来] 只朗读不操作；按钮文字对不上就改 config 里的")
            print("           READ_BUTTONS / SUBMIT_BUTTONS / NEXT_BUTTONS")


def run(d, items):
    items = matcher.prepare(items)
    speaker = Speaker()
    kb = Keyboard() if (sys.stdin and sys.stdin.isatty()) else None

    print("=" * 60)
    print("开始监听：")
    print(f"  朗读页: {'自动（点录音→朗读→点空白→下一题）' if config.AUTO_READING_FLOW else '只提示'}")
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
                    print(f"[{_ts()}] 看着像单词列表页（一次匹配到 {len(strong)} 个词），跳过")
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
