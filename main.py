# -*- coding: utf-8 -*-
"""智学网单词助手 —— 入口

用法（在 zhixuewang 目录下运行）：
    python main.py probe            看当前屏幕读到哪些文字（--raw 连噪音一起看）
    python main.py capture          抓取单词列表 → data/words.json
    python main.py run              开始监听练习页（自动识别 + 朗读 + 作答）
    python main.py match "贫瘠的"   离线测试模糊匹配
    python main.py tap 朗读         在手机屏幕上点一个文字按钮（调试用）
    python main.py type apple       往当前页面的输入框填字（调试用）
    python main.py voices           列出电脑上可用的朗读嗓音
    python main.py speak apple      试听一个单词的发音
"""
import argparse
import sys
import time

# 中文输出：接在控制台上正常显示；被重定向到文件/管道时改用 UTF-8，免得编码报错
if not sys.stdout.isatty():
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

import config


def fail(msg):
    print(msg)
    sys.exit(1)


def cmd_probe(args):
    from zxw import device, page

    d = device.connect(args.serial)
    scr = page.read_screen(d)
    print(f"\n当前屏幕读到 {len(scr['texts'])} 条文字（已过滤状态栏噪音）：")
    for i, t in enumerate(scr["texts"], 1):
        print(f"  {i:2d}. {t}")

    if args.raw:
        print("\n--- 原始控件树（含噪音，带包名）---")
        for pkg, t in page.texts_from_xml(scr["xml"]):
            print(f"  {pkg:40s} | {t}")

    if len(scr["texts"]) < 3:
        print("\n[提示] 文字非常少 —— 有可能这个页面是画布（canvas）画的，")
        print("       uiautomator 读不到上面的字。那就需要截图 OCR 方案，跟我说一声。")

    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    out = config.DATA_DIR / f"probe_{time.strftime('%Y%m%d_%H%M%S')}.xml"
    out.write_text(scr["xml"], encoding="utf-8")
    print(f"\n控件树 XML 已存到: {out}")
    print("\n当前设备列表:")
    print(device.list_devices_text())


def cmd_capture(args):
    from zxw import capture, device

    d = device.connect(args.serial)
    capture.capture(d, interactive=not args.no_wait)


def cmd_run(args):
    from zxw import capture, device, monitor

    items = capture.load()
    print(f"单词表: {len(items)} 个词  ({config.WORDS_FILE})")
    print("示例: " + "；".join(it["word"] for it in items[:5]))
    d = device.connect(args.serial)
    monitor.run(d, items, mode=args.mode)


def cmd_match(args):
    from zxw import capture, matcher

    items = capture.load()
    ranked = matcher.rank(args.text, items, topk=args.top)
    if not ranked:
        print("没有任何词条匹配上。")
        return
    print(f"查询: {' | '.join(args.text)}")
    for i, r in enumerate(ranked, 1):
        it = r["item"]
        ph = f" /{it['phonetic']}/" if it.get("phonetic") else ""
        print(f"  {i}. {it['word']:<18}{ph}  [{r['source']} {r['score']:.2f}]  {it.get('cn', '')}")


def cmd_tap(args):
    from zxw import device

    d = device.connect(args.serial)
    exact = contains = None
    try:
        if d(text=args.text).exists(timeout=0.5):
            exact = d(text=args.text)
    except Exception as e:
        print(f"精确查找失败: {e}")
    try:
        if d(textContains=args.text).exists(timeout=0.5):
            contains = d(textContains=args.text)
    except Exception as e:
        print(f"包含查找失败: {e}")

    if exact is None and contains is None:
        print(f"屏幕上没找到「{args.text}」。先跑 probe 看看现在页面上有什么文字。")
        return
    target, kind = (exact, "精确") if exact is not None else (contains, "包含")
    try:
        info = target.info or {}
        print(f"找到（{kind}匹配）: {info.get('className', '')}  {info.get('bounds', {})}")
    except Exception:
        pass
    target.click()
    print(f"已点击「{args.text}」（{kind}匹配）")


def cmd_type(args):
    from zxw import actions, device

    d = device.connect(args.serial)
    boxes = actions.get_edittexts(d)
    if boxes:
        print("页面上的输入框：")
        for i, txt, foc in boxes:
            print(f"  [{i}] 现有文字={txt!r} 聚焦={foc}")
    else:
        print("没找到 EditText 输入框（也可能是 WebView 自己的输入区）")
    ok = actions.fill_answer(d, args.text)
    print(("已填入: " if ok else "填不进去: ") + args.text)
    if not ok:
        print("把这页的 probe（python main.py probe --raw）结果发我看下，我来加对应的定位方式。")


def cmd_voices(args):
    from zxw.tts import list_voices

    list_voices()


def cmd_speak(args):
    from zxw.tts import speak_once

    speak_once(args.text, repeat=args.repeat)


def main():
    p = argparse.ArgumentParser(
        description="智学网单词助手：识别题目里的单词 → 电脑朗读 → 自动作答",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = p.add_subparsers(dest="cmd")

    sp = sub.add_parser("probe", help="看当前屏幕能读到哪些文字")
    sp.add_argument("--serial", default=None)
    sp.add_argument("--raw", action="store_true", help="连状态栏噪音一起打印（带包名）")
    sp.set_defaults(func=cmd_probe)

    sp = sub.add_parser("capture", help="抓取单词列表")
    sp.add_argument("--serial", default=None)
    sp.add_argument("--no-wait", action="store_true", help="不等待回车，直接开抓")
    sp.set_defaults(func=cmd_capture)

    sp = sub.add_parser("run", help="监听练习页，识别 + 朗读 + 作答")
    sp.add_argument("--serial", default=None)
    sp.add_argument("--mode", choices=("all", "reading", "spelling"), default="all",
                    help="all=朗读+拼写都跑（默认）；reading=只跑跟读；spelling=只跑拼写")
    sp.set_defaults(func=cmd_run)

    sp = sub.add_parser("match", help="离线测试模糊匹配")
    sp.add_argument("text", nargs="+", help='要匹配的文字，例如: "苹果"')
    sp.add_argument("--top", type=int, default=5)
    sp.set_defaults(func=cmd_match)

    sp = sub.add_parser("tap", help="点一个文字按钮（调试用）")
    sp.add_argument("text", help='按钮文字，例如: "朗读"')
    sp.add_argument("--serial", default=None)
    sp.set_defaults(func=cmd_tap)

    sp = sub.add_parser("type", help="往输入框填字（调试用）")
    sp.add_argument("text", help="要填的内容")
    sp.add_argument("--serial", default=None)
    sp.set_defaults(func=cmd_type)

    sp = sub.add_parser("voices", help="列出可用嗓音")
    sp.set_defaults(func=cmd_voices)

    sp = sub.add_parser("speak", help="试听发音")
    sp.add_argument("text")
    sp.add_argument("--repeat", type=int, default=1)
    sp.set_defaults(func=cmd_speak)

    args = p.parse_args()
    if not getattr(args, "func", None):
        print(__doc__)
        return
    try:
        args.func(args)
    except RuntimeError as e:
        fail(f"\n[出错] {e}")
    except KeyboardInterrupt:
        print("\n已退出。")


if __name__ == "__main__":
    main()
