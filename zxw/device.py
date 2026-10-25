# -*- coding: utf-8 -*-
"""设备连接：找串号 → 连上 uiautomator2"""
import os
import re
import subprocess
import time
from pathlib import Path

import config

# 常见安卓模拟器在本机监听的 adb 端口（一台设备都找不到时挨个试）
COMMON_PORTS = [
    7555,           # MuMu
    5555,           # 雷电 / BlueStacks / 夜神（部分）
    62001, 62025,   # 夜神
    21503,          # MuMu 旧版
]

# 设置页可选的模拟器预设 → 默认 adb 端口
EMULATOR_PORTS = {
    "ldplayer": 5555,      # 雷电模拟器
    "mumu": 7555,          # MuMu 模拟器
    "bluestacks": 5555,    # 蓝叠模拟器
}
EMULATOR_NAMES = {
    "ldplayer": "雷电模拟器",
    "mumu": "MuMu 模拟器",
    "bluestacks": "蓝叠模拟器",
}

_ADB = None


def _adb_exe():
    """决定用哪个 adb：config.ADB_PATH 优先，否则用 PATH 里的"""
    global _ADB
    if _ADB is not None:
        return _ADB
    exe = (config.ADB_PATH or "").strip()
    if exe:
        p = Path(exe)
        if p.exists():
            # 加进 PATH，这样 uiautomator2 内部的 adbutils 也能找到
            os.environ["PATH"] = str(p.parent) + os.pathsep + os.environ.get("PATH", "")
            os.environ["ADBUTILS_ADB_PATH"] = str(p)
            _ADB = str(p)
            return _ADB
        print(f"[警告] config.ADB_PATH 指向的文件不存在: {p}，改用 PATH 里的 adb")
    _ADB = "adb"
    return _ADB


def adb(args, timeout=20):
    return subprocess.run([_adb_exe()] + args, capture_output=True, text=True, timeout=timeout)


def adb_devices():
    """返回 [(串号, 状态)]，状态一般是 device / offline / unauthorized"""
    try:
        p = adb(["devices"])
    except FileNotFoundError:
        raise RuntimeError(
            "找不到 adb。请把 config.py 里的 ADB_PATH 改成 adb.exe 的完整路径，"
            "或安装 Android platform-tools 并加入 PATH。"
        )
    devs = []
    for line in (p.stdout or "").splitlines()[1:]:
        line = line.strip()
        if not line:
            continue
        parts = re.split(r"\s+", line)
        if len(parts) >= 2:
            devs.append((parts[0], parts[1]))
    return devs


def list_devices_text():
    try:
        devs = adb_devices()
    except RuntimeError as e:
        return f"（读取设备列表失败: {e}）"
    if not devs:
        return "（没有检测到设备）"
    return "  " + "\n  ".join(f"{s}  [{st}]" for s, st in devs)


def pick_serial(serial=None):
    serial = (serial or config.DEVICE_SERIAL or "").strip()
    if serial:
        return serial

    # 设置页选过模拟器预设 → 先连它的默认端口
    emu = (getattr(config, "EMULATOR", "auto") or "auto").strip().lower()
    port = EMULATOR_PORTS.get(emu)
    if port:
        addr = f"127.0.0.1:{port}"
        try:
            r = adb(["connect", addr], timeout=10)
        except Exception:
            r = None
        if r is not None:
            out = ((r.stdout or "") + (r.stderr or "")).lower()
            if "cannot" not in out and ("connected to" in out or "already connected" in out):
                print(f"[连接] 已连接{EMULATOR_NAMES.get(emu, emu)}默认端口 {addr}")
                time.sleep(0.8)
                return addr
        print(f"[连接] 预设的 {addr} 连不上，改为自动探测 adb 设备")

    devs = adb_devices()
    ready = [s for s, st in devs if st == "device"]
    if ready:
        return ready[0]
    if any(st == "unauthorized" for _, st in devs):
        raise RuntimeError(
            "设备显示 unauthorized：请在模拟器/手机的弹窗里点『允许 USB 调试』，然后重试。"
        )

    # 一台都没有 → 挨个试常见模拟器端口
    for port in COMMON_PORTS:
        addr = f"127.0.0.1:{port}"
        try:
            r = adb(["connect", addr], timeout=10)
        except Exception:
            continue
        out = ((r.stdout or "") + (r.stderr or "")).lower()
        if "cannot" not in out and ("connected to" in out or "already connected" in out):
            print(f"[连接] 自动连上了 {addr}")
            time.sleep(1.0)
            return addr

    raise RuntimeError(
        "没有检测到安卓设备。请先启动模拟器（并进入系统桌面），"
        "或把手机用 USB 连上并打开『USB 调试』，然后重试。"
    )


def connect(serial=None):
    """连上设备并返回 uiautomator2 的 Device 对象"""
    s = pick_serial(serial)
    import uiautomator2 as u2

    print(f"[连接] 正在连接 {s}（首次连接会自动部署 uiautomator 服务，可能要十几秒）...")
    d = u2.connect(s)
    try:
        info = d.info
    except Exception as e:
        raise RuntimeError(f"连上了 {s}，但 uiautomator2 无法读取设备信息: {e}")
    w = info.get("displayWidth") or "?"
    h = info.get("displayHeight") or "?"
    print(f"[连接] 成功，屏幕 {w}x{h}，设备 {info.get('productName') or ''}")
    return d
