# -*- coding: utf-8 -*-
"""run.bat 的菜单入口。

用 Python 写菜单的原因：cmd 处理中文/UTF-8 有解析 bug，Python 更稳，
而且能优雅处理 Ctrl+C（子进程中断后还能回到菜单，窗口不会直接关掉）。
"""
import os
import shlex
import subprocess
import sys
from pathlib import Path

if not sys.stdout.isatty():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable
MODE_NAMES = {"reading": "朗读", "spelling": "拼写"}

HELP = """可用命令（参数直接跟在本程序后面；完整说明见 README.md）：
  probe                     看当前屏幕能读到哪些文字（排障用）
  capture                   抓取单词列表到 data\\words.json
  run --mode reading        只做朗读模块
  run --mode spelling       只做拼写模块
  run --mode reading -y     做朗读，做完自动接着做拼写
  ui                        打开设置页
  match "贫瘠的"            离线测试模糊匹配
  tap 朗读 / type apple     调试点击 / 调试输入
  voices / speak apple      列出语音模型 / 试听发音"""


def set_title():
    try:
        import ctypes

        ctypes.windll.kernel32.SetConsoleTitleW("智学网单词助手")
    except Exception:
        pass


def ask(prompt=""):
    try:
        return input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        return ""


def run_main(args):
    """运行 main.py；Ctrl+C 中断时优雅返回，不影响菜单"""
    cmd = [PY, str(ROOT / "main.py")] + list(args)
    try:
        return subprocess.call(cmd, cwd=str(ROOT))
    except KeyboardInterrupt:
        print("\n[菜单] 已中断。")
        return 130


def pause():
    ask("\n按回车继续...")


def pick_mode():
    ans = ask("做哪个模块？1=朗读 2=拼写（回车=朗读）：")
    return "spelling" if ans == "2" else "reading"


def interactive():
    """交互模式：跑一个模块，结束后询问下一步。返回 False 表示退出程序。"""
    mode = pick_mode()
    while True:
        run_main(["run", "--mode", mode])
        print("\n模块已结束（上面是本次日志）。")
        ans = ask("下一步：1=继续跑这个模块  2=切换到另一个模块  3=返回菜单  0=退出 ：")
        if ans == "0":
            return False
        if ans == "3":
            return True
        if ans == "2":
            mode = "spelling" if mode == "reading" else "reading"
            print(f"已切换到{MODE_NAMES[mode]}模块。")
        # 其他输入 = 继续当前模块


def autoflow():
    mode = pick_mode()
    print(f"\n自动流转模式：做完{MODE_NAMES[mode]}模块后自动切换到另一个模块（-y）。")
    run_main(["run", "--mode", mode, "-y"])
    print("\n自动流转已结束。")
    pause()


def ui_panel():
    print()
    print("正在新窗口启动设置页（关闭那个窗口即可停止）...")
    cmd = f'"{PY}" "{ROOT / "main.py"}" ui'
    try:
        subprocess.Popen(cmd, cwd=str(ROOT), shell=True,
                         creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))
    except Exception as e:
        print(f"[失败] 启动设置页失败: {e}")
        pause()


def custom():
    print()
    print(HELP)
    print()
    raw = ask("输入参数（直接回车返回菜单）：")
    if not raw:
        return
    try:
        args = shlex.split(raw)
    except ValueError:
        args = raw.split()
    run_main(args)
    pause()


def main():
    set_title()
    while True:
        print()
        print("============================================")
        print("  智学网单词助手")
        print("============================================")
        print("  [1] 交互模式     跑一个模块，结束后询问下一步（Ctrl+C 可随时退出）")
        print("  [2] 自动流转     模块跑完后自动切换另一个模块")
        print("  [3] 网页面板     打开本地设置页（新窗口）")
        print("  [4] 自定义参数   打印命令说明，手动输入参数运行 main.py")
        print("  [0] 退出")
        print("============================================")
        ans = ask("请选择 [0-4]: ")
        if ans == "0":
            break
        if ans == "1":
            if interactive() is False:
                break
        elif ans == "2":
            autoflow()
        elif ans == "3":
            ui_panel()
        elif ans == "4":
            custom()
    print("再见。")


if __name__ == "__main__":
    main()
