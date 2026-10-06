# -*- coding: utf-8 -*-
"""从单词列表页抓取「单词 / 音标 / 中文释义」"""
import json
import re
import sys
import time

import config
from . import page

# 音标符号集合（用来认出音标行）
_IPA_CHARS = set("ˈˌːəɪʊæʌɔɜɑɒɛðθʃʒŋ")
# 音标一般被 /.../ 或 [...] 包住
_PHONETIC_WRAP_RE = re.compile(r"[\[/]([^\]/]{1,60})[\]/]")
# 英文单词：字母开头，允许字母、撇号、连字符
_WORD_RE = re.compile(r"^\s*([A-Za-z][A-Za-z'\- ]{1,29})")
# 词性标注（n. / adj. 之类），解析时要跳过，别当成英文单词
_POS_WORDS = {"n", "v", "vt", "vi", "adj", "adv", "prep", "conj", "pron",
              "num", "art", "int", "interj", "aux", "abbr", "modal", "pl", "det"}
# 行内的词性标注，识别单词前先抠掉（"apple n. 苹果" → "apple 苹果"）
_POS_INLINE_RE = re.compile(
    r"\b(?:n|v|vt|vi|adj|adv|prep|conj|pron|num|art|int|interj|aux|abbr|modal|pl|det)\s*\.",
    re.I,
)


def has_chinese(s):
    return bool(re.search(r"[一-鿿]", s))


def ipa_count(s):
    return sum(1 for c in s if c in _IPA_CHARS)


def is_phonetic(s):
    return bool(_PHONETIC_WRAP_RE.search(s)) or ipa_count(s) >= 2


def strip_phonetic_wrap(s):
    m = _PHONETIC_WRAP_RE.search(s)
    return (m.group(1) if m else s).strip()


def split_line(t):
    """把一行文字拆成 (单词, 音标, 中文) 三部分，没有的部分是空串。

    能处理这些形式：
      "apple"                        → ("apple", "", "")
      "/ˈæpl/"                       → ("", "ˈæpl", "")
      "n. 苹果；苹果树"               → ("", "", "n. 苹果；苹果树")
      "apple /ˈæpl/ n. 苹果；苹果树"  → ("apple", "ˈæpl", "n. 苹果；苹果树")
    """
    # 先把词性标注抠掉，免得干扰英文单词识别
    t = _POS_INLINE_RE.sub(" ", t)

    word = ""
    m = _WORD_RE.match(t)
    if m:
        w = m.group(1).strip()
        rest = t[m.end():].lstrip()
        # 后面紧跟数字的（比如 "Unit 1"）是标题不是单词
        if len(w) >= 2 and w.lower() not in _POS_WORDS and not rest[:1].isdigit():
            word = w

    ph = ""
    if is_phonetic(t):
        ph = strip_phonetic_wrap(t)

    cn = ""
    mc = re.search(r"[一-鿿].*", t)
    if mc:
        cn = re.sub(r"\s{2,}", " ", mc.group(0)).strip()

    # 整行是个纯单词时，别把单词本身误当成中文/音标
    return word, ph, cn


def parse_items(texts):
    """从一屏文字里解析出 [{"word","phonetic","cn"}, ...]"""
    items = []
    i, n = 0, len(texts)
    while i < n:
        word, ph, cn = split_line(texts[i])
        if not word:
            i += 1
            continue
        # 往后看几行，补齐缺的音标/中文；遇到下一个单词就停
        j = i + 1
        while j < n and j <= i + 4 and (not ph or not cn):
            w2, ph2, cn2 = split_line(texts[j])
            if w2:
                break
            if not ph and ph2:
                ph = ph2
            if not cn and cn2:
                cn = cn2
            j += 1
        items.append({"word": word, "phonetic": ph, "cn": cn})
        i = j
    return items


def load():
    """读单词表，给 run / match 用"""
    if not config.WORDS_FILE.exists():
        raise RuntimeError(
            f"还没抓过单词表（找不到 {config.WORDS_FILE}）。\n"
            "先运行: python main.py capture"
        )
    data = json.loads(config.WORDS_FILE.read_text(encoding="utf-8"))
    items = data.get("items", [])
    if not items:
        raise RuntimeError("words.json 里没有单词，请重新 capture，或用记事本手动补充。")
    return items


def save(items):
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    data = {
        "captured_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "count": len(items),
        "items": items,
    }
    config.WORDS_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n已保存 {len(items)} 个词 → {config.WORDS_FILE}")


def capture(d, interactive=True):
    """自动向下滚，把整个单词列表扫一遍"""
    print("=" * 60)
    print("抓取单词列表")
    print("请把模拟器停在【单词列表】页面（能看到英文、音标、中文的那一页），")
    print("脚本会自动往下滚，把整份列表扫一遍。")
    if interactive and sys.stdin and sys.stdin.isatty():
        input("准备好了就按回车开始（Ctrl+C 取消）...")

    config.RAW_DIR.mkdir(parents=True, exist_ok=True)
    for f in config.RAW_DIR.glob("screen_*.txt"):
        f.unlink()   # 清掉上次的原始记录

    items, by_word = [], {}
    last_sig, empty_rounds = None, 0
    for idx in range(1, config.CAPTURE_MAX_SCROLLS + 1):
        scr = page.read_screen(d)
        (config.RAW_DIR / f"screen_{idx:03d}.txt").write_text(
            "\n".join(scr["texts"]), encoding="utf-8"
        )

        new = 0
        for it in parse_items(scr["texts"]):
            key = it["word"].lower()
            if key in by_word:
                # 同一个词之前出现过但不完整，补全它
                old = by_word[key]
                for f in ("phonetic", "cn"):
                    if not old[f] and it[f]:
                        old[f] = it[f]
                continue
            by_word[key] = it
            items.append(it)
            new += 1

        print(f"  第 {idx:2d} 屏: 新识别 {new} 个词（累计 {len(items)}）")

        empty_rounds = empty_rounds + 1 if new == 0 else 0
        if scr["sig"] == last_sig or empty_rounds >= 2 or len(scr["texts"]) < 3:
            break
        last_sig = scr["sig"]
        page.swipe_up(d)
        time.sleep(config.CAPTURE_SCROLL_WAIT)

    save(items)

    no_cn = [it["word"] for it in items if not it["cn"]]
    print("\n预览（前 8 个）:")
    for it in items[:8]:
        ph = f" /{it['phonetic']}/" if it["phonetic"] else ""
        print(f"  {it['word']}{ph}  {it['cn']}")
    if no_cn:
        print(f"\n注意：有 {len(no_cn)} 个词没识别到中文释义（{', '.join(no_cn[:5])}...），")
        print("      建议用记事本打开 words.json 手工补一下，否则这些词匹配不到。")
    print("建议整体检查一遍 words.json（多了/少了的词可以直接改）。")
    return items
