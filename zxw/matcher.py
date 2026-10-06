# -*- coding: utf-8 -*-
"""模糊匹配：把屏幕上的文字对上单词表里的词条。

三路信号，每个词条取最高的那路：
  中文 —— 主信号。分词 + 子串包含 + 模糊比率，容忍识别误差和多义项差异。
  音标 —— 页面出现音标时用。
  拼写 —— 页面出现英文碎片（完整单词，或 a _ _ l e 这种带空位的）时用。
"""
import logging
import re

import jieba

jieba.setLogLevel(logging.ERROR)

from rapidfuzz import fuzz

import config

# 词性标注：n. / adj. / vt. 之类，归一化时去掉
_POS_RE = re.compile(
    r"\b(?:n|v|vt|vi|adj|adv|prep|conj|pron|num|art|int|interj|aux|abbr|modal|pl|det)\s*\.",
    re.I,
)
_NON_CJK_RE = re.compile(r"[^一-鿿]+")
_IPA_SIGNS = "ˈˌːəɪʊæʌɔɜɑɒɛðθʃʒŋ"
_IPA_KEEP_RE = re.compile(r"[^a-z" + _IPA_SIGNS + r"]")
_BLANK_RE = re.compile(r"[_*·•]")   # 空位符号：_ * · •


def norm_cn(s):
    """中文释义归一化：去词性标注、只留汉字"""
    if not s:
        return ""
    return _NON_CJK_RE.sub("", _POS_RE.sub("", s))


def cn_tokens(s):
    """jieba 分词，只留有意义的词（长度>=2 且不是虚词）"""
    return {w for w in jieba.cut(s) if len(w) >= 2 and w not in config.STOPWORDS}


def _norm_ipa(s):
    return _IPA_KEEP_RE.sub("", (s or "").lower())


def _is_ipa_like(s):
    return sum(1 for c in s if c in _IPA_SIGNS) >= 2


def _score_cn(q, t, t_toks):
    """中文相似度（q/t 都已是归一化后的纯汉字）"""
    if len(q) < 2 or len(t) < 2:
        return 0.0
    # 一句话是另一句的一部分 → 基本可认定原文，按长度比例给 0.90~1.00
    if q in t or t in q:
        short, long_ = sorted((q, t), key=len)
        return 0.90 + 0.10 * len(short) / len(long_)
    # 连一个共同汉字都没有 → 不用算了
    if not (set(q) & set(t)):
        return 0.0
    qs = cn_tokens(q)
    tok = len(qs & t_toks) / len(qs | t_toks) if (qs and t_toks) else 0.0
    return max(
        tok * 0.95,                          # 按"词"的 Jaccard 重叠
        fuzz.partial_ratio(q, t) / 100 * 0.90,  # 局部相似（抗漏字、抗多义项）
        fuzz.ratio(q, t) / 100 * 0.90,          # 整体相似（抗错别字/形近字）
    )


def _score_ipa(q_ipa, q_is_ipa, t_ipa):
    if not q_is_ipa or not q_ipa or not t_ipa:
        return 0.0
    if q_ipa == t_ipa:
        return 1.0
    r = fuzz.ratio(q_ipa, t_ipa) / 100.0
    return r * 0.92 if r >= 0.7 else r * 0.70


def _score_en(raw, word):
    """英文碎片：完整单词、或 a _ _ l e 这种带空位的提示"""
    if not word:
        return 0.0
    raw = raw.strip()
    if not raw or len(raw) > 60:
        return 0.0

    if _BLANK_RE.search(raw) and re.search(r"[A-Za-z]", raw):
        parts = []
        for ch in raw:
            if ch.isspace():
                continue
            if ch.isalpha():
                parts.append(ch.lower())
            elif _BLANK_RE.match(ch):
                parts.append(".")
        pat = "".join(parts)
        if len(pat) < 3 or "." not in pat:
            return 0.0
        fixed = len(pat) - pat.count(".")
        try:
            if re.fullmatch(pat, word):
                return 0.85 + 0.15 * fixed / len(pat)
        except re.error:
            return 0.0
        return 0.0

    t = re.sub(r"[^a-z]", "", raw.lower())
    if not t:
        return 0.0
    if t == word:
        return 1.0
    if len(t) >= 4 and (t in word or word in t):
        return 0.80
    return 0.0


def prepare(items):
    """预计算每个词条的归一化字段，rank 时就不用反复算了"""
    out = []
    for it in items:
        p = dict(it)
        p["_cn"] = norm_cn(it.get("cn", ""))
        p["_ipa"] = _norm_ipa(it.get("phonetic", ""))
        p["_word"] = (it.get("word", "") or "").strip().lower()
        p["_toks"] = cn_tokens(p["_cn"])
        out.append(p)
    return out


def ensure_prepared(items):
    if items and "_cn" in items[0]:
        return items
    return prepare(items)


def _is_ui_text(t):
    t = t.strip()
    if len(t) < 2:
        return True
    if t in config.IGNORE_TEXTS:
        return True
    # 万一有噪音文字漏过了页面过滤（比如从别的地方调进来），这里再兜一层
    for rx in config.NOISE_REGEXES:
        if re.search(rx, t):
            return True
    return False


def rank(texts, items, topk=5):
    """核心入口。

    texts: 当前屏幕上的文字列表
    items: 词条列表（原始或 prepare 过的都行）
    返回: [{"item", "score", "source"}, ...] 按分数降序，最多 topk 个
    """
    items = ensure_prepared(items)

    qs = []
    for t in texts:
        if _is_ui_text(t):
            continue
        qs.append({
            "raw": t,
            "cn": norm_cn(t),
            "ipa": _norm_ipa(t),
            "ipa_like": _is_ipa_like(t),
        })
    if not qs:
        return []

    results = []
    for it in items:
        best, src = 0.0, ""
        for q in qs:
            s = _score_cn(q["cn"], it["_cn"], it["_toks"])
            if s > best:
                best, src = s, "中文"
            s = _score_ipa(q["ipa"], q["ipa_like"], it["_ipa"])
            if s > best:
                best, src = s, "音标"
            s = _score_en(q["raw"], it["_word"])
            if s > best:
                best, src = s, "拼写"
        if best > 0.0:
            results.append({"item": it, "score": round(best, 4), "source": src})

    results.sort(key=lambda r: r["score"], reverse=True)
    return results[:topk]
