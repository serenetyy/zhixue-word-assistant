# -*- coding: utf-8 -*-
"""朗读（单词跟读）流程 —— 和拼写流程完全分开，可以单独跑、单独调。

流程：点录音 → 0.5s → 重新识别并朗读 → 1s → 点"波纹"结束录音
     → 等评测（没过自动重录，重录时读 2 遍）→ 点「下一题」
"""
import time

import config
from . import actions
from .util import fresh_word, progress_text, ts


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
    word = fresh_word(d, items, word)           # 每次朗读前重新识别，不拿旧词
    speaker.prepare(word)                       # Edge 需要联网合成，先在录音窗口外备好
    repeat = max(min_repeat, speaker.repeat_fit(config.READ_RECORD_BUDGET))
    got = actions.click_control(d, [config.ID_RECORD], config.READ_BUTTONS)
    if not got:
        return False
    print(f"[{ts()}] 朗读页: 点『录音』成功（{got}，读 {repeat} 遍）")
    time.sleep(config.READ_AFTER_CLICK_WAIT)

    speaker.speak(word, force=True, repeat=repeat)
    speaker.wait()                              # 等读完
    time.sleep(config.READ_AFTER_SPEAK_WAIT)

    # 结束录音：录音中提示是"点击波纹，结束录音"，点 layout_recording 那块面板。
    # 读一遍时录音常自己提前结束（说完静音一会就收），点空属正常，不影响。
    stop = actions.click_control(d, [config.ID_RECORD_WAVE], ["点击波纹，结束录音"])
    print(f"           结束录音: {stop or '（录音已自行结束，正常）'}")
    time.sleep(config.AFTER_STOP_WAIT)
    return True


def do_reading(d, word, speaker, items):
    """朗读页完整流程（含没通过时的自动重录、翻页重试）"""
    scored = False
    for attempt in range(1 + max(0, config.READ_RETRY_TIMES)):
        if attempt:
            print(f"           自动重录（第 {attempt + 1} 遍，多读一遍更稳）...")
        # 第一次按配置读（默认1遍）；重录时至少读2遍，提高被评测通过的概率
        if not _record_once(d, word, speaker, items, min_repeat=1 if attempt == 0 else 2):
            print(f"[{ts()}] 朗读页: 没找到录音按钮，只朗读不点击")
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
    before = progress_text(d)
    for _ in range(3):                       # 点"下一题"，没翻页就再试
        got2 = actions.click_control(d, [config.ID_NEXT], config.NEXT_BUTTONS)
        if not got2:
            print("           没找到『下一题』，按 n 手动点")
            return
        time.sleep(1.3)
        after = progress_text(d)
        if after and after != before:
            print(f"           已翻到 {after}"
                  + ("" if scored else "（这题没录上，想补录可以点『上一题』回去）"))
            return
    print("           点了『下一题』但页面没翻，按 n 再试")
