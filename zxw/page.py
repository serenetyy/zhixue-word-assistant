# -*- coding: utf-8 -*-
"""读取屏幕上的文字（控件树，不用 OCR），并过滤状态栏/通知噪声。

原理：让手机端 uiautomator 把当前界面的控件树 dump 成 XML，从 XML 里抽
text / content-desc 属性。过滤分两层：
  1. 包名过滤 —— 状态栏/通知栏的文字都来自 com.android.systemui，直接扔掉；
  2. 文字特征兜底 —— 时间、满格、充电百分比、.apk 之类的高置信特征。
"""
import hashlib
import re
import time
import xml.etree.ElementTree as ET

import config

_TEXT_ATTRS = ("text", "content-desc")


def is_noise(pkg, text):
    """这条文字是不是状态栏/通知栏的垃圾"""
    if pkg and any(pkg.startswith(p) for p in config.NOISE_PACKAGES):
        return True
    for rx in config.NOISE_REGEXES:
        if re.search(rx, text):
            return True
    return False


def clean_pairs(pairs):
    """[(包名, 文字), ...] → 去掉噪音后的文字列表（保持顺序、去重）"""
    seen, out = set(), []
    for pkg, t in pairs:
        if is_noise(pkg, t) or t in seen:
            continue
        seen.add(t)
        out.append(t)
    return out


def texts_from_xml(xml):
    """从控件树 XML 里按屏幕顺序抽取 (包名, 文字)"""
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        # 极少数情况 XML 不完整，退化成正则粗抓
        raw = re.findall(r'(?:text|content-desc)="([^"]*)"', xml)
        return [("", t.strip()) for t in raw if t.strip()]

    pairs = []
    for node in root.iter():
        pkg = node.get("package") or ""
        for attr in _TEXT_ATTRS:
            v = (node.get(attr) or "").strip()
            if v:
                pairs.append((pkg, v))
    return pairs


def read_screen(d, retries=3):
    """读取当前屏幕，返回 {"texts": 过滤后的文字, "xml": 原始控件树, "sig": 指纹}

    sig 是这一屏（过滤后）文字的指纹，用来判断"页面变了没有"。
    """
    last_err = None
    for _ in range(retries):
        try:
            xml = d.dump_hierarchy()
        except Exception as e:
            last_err = e
            time.sleep(0.6)
            continue
        if not xml or "<hierarchy" not in xml:
            last_err = RuntimeError("dump 结果不完整")
            time.sleep(0.6)
            continue
        texts = clean_pairs(texts_from_xml(xml))
        return {"texts": texts, "xml": xml, "sig": screen_signature(texts)}
    raise RuntimeError(f"读取屏幕失败（重试 {retries} 次）: {last_err}")


def screen_signature(texts):
    return hashlib.md5("\n".join(texts).encode("utf-8")).hexdigest()


def swipe_up(d):
    """向上滑一屏（翻列表用）。只在这里用坐标，其他一切定位都用文字/控件。"""
    w, h = d.window_size()
    d.swipe(w * 0.5, h * 0.72, w * 0.5, h * 0.32, 0.25)
