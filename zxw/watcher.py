# -*- coding: utf-8 -*-
"""弹窗 watcher：自动点掉无害弹窗，提醒需要人工处理的按钮。

页面上出现什么文字可以自己配：config.AUTO_CLICK_TEXTS / WARN_ONLY_TEXTS。
"""
import config


def check(d, texts):
    """每次页面变化时调用，返回这次帮你点掉的按钮文字列表"""
    handled = []

    for t in config.AUTO_CLICK_TEXTS:
        if t in texts:
            try:
                if d(text=t).click_exists(timeout=1.0):
                    handled.append(t)
                    print(f"[弹窗] 已自动点掉「{t}」")
            except Exception as e:
                print(f"[弹窗] 点击「{t}」失败: {e}")

    for t in config.WARN_ONLY_TEXTS:
        if t in texts:
            print(f"[弹窗] 屏幕上有「{t}」按钮，需要你自己确认（故意不帮你点）")

    return handled
