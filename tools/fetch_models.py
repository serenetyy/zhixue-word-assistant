# -*- coding: utf-8 -*-
"""下载 Piper 语音模型（可选，不强制全量）。

用法：
    python tools/fetch_models.py              # 交互式：列清单 → 输编号 → 统一下载
    python tools/fetch_models.py --all        # 下载全部（已存在的自动跳过）
    python tools/fetch_models.py --list       # 只看清单
    python tools/fetch_models.py --only en_US-lessac-medium,en_US-hfc_female-medium

下载源：先走国内镜像 hf-mirror.com，失败自动换 huggingface.co。
"""
import os
import sys
import urllib.request
from pathlib import Path

if not sys.stdout.isatty():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent.parent
DEST = ROOT / "data" / "piper_voices"
BASES = ["https://hf-mirror.com", "https://huggingface.co"]

# (模型名, 说明)
MODELS = [
    ("en_US-amy-medium",         "美音女声，清亮（默认，已内置）"),
    ("en_US-hfc_female-medium",  "美音女声，自然"),
    ("en_US-lessac-medium",      "美音女声，偏中性"),
    ("en_US-kristin-medium",     "美音女声"),
    ("en_GB-jenny_dioco-medium", "英音女声"),
    ("en_GB-alba-medium",        "英音（苏格兰）女声"),
    ("en_US-lessac-high",        "美音女声，高质量（较大）"),
    ("en_US-ryan-high",          "美音男声，高质量（较大）"),
]


def rel_path(name):
    """en_US-amy-medium → en/en_US/amy/medium/en_US-amy-medium"""
    locale, voice, quality = name.split("-", 2)
    return f"en/{locale}/{voice}/{quality}/{name}"


def have(name):
    return (DEST / f"{name}.onnx").exists() and (DEST / f"{name}.onnx.json").exists()


def download(url, dest):
    tmp = Path(str(dest) + ".part")
    with urllib.request.urlopen(url, timeout=240) as r, open(tmp, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        while True:
            chunk = r.read(1024 * 256)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            if total:
                pct = done * 100 // total
                print(f"\r    {pct:3d}%  ({done / 1048576:.1f}/{total / 1048576:.1f} MB)",
                      end="", flush=True)
    print()
    os.replace(tmp, dest)


def fetch_one(name):
    DEST.mkdir(parents=True, exist_ok=True)
    if have(name):
        print(f"  已存在，跳过: {name}")
        return True
    rel = rel_path(name)
    for ext in (".onnx", ".onnx.json"):
        dest = DEST / f"{name}{ext}"
        if dest.exists():
            continue
        ok = False
        for base in BASES:
            url = f"{base}/rhasspy/piper-voices/resolve/main/{rel}{ext}"
            print(f"  下载 {name}{ext}")
            print(f"    源: {base}")
            try:
                download(url, dest)
                ok = True
                break
            except Exception as e:
                print(f"    失败: {e}")
        if not ok:
            print(f"  [失败] {name}{ext} 没下下来，可以稍后再试，"
                  f"或在浏览器打开: https://hf-mirror.com/rhasspy/piper-voices/resolve/main/{rel}{ext}")
            return False
    return True


def show():
    print("可选的 Piper 语音模型（英文）：")
    for i, (name, desc) in enumerate(MODELS, 1):
        mark = "x" if have(name) else " "
        print(f"  [{mark}] {i:2d}. {name:28s} {desc}")
    print()


def main():
    args = sys.argv[1:]
    if "--list" in args:
        show()
        return

    chosen = []
    if "--all" in args:
        chosen = [m for m, _ in MODELS]
    elif "--only" in args:
        i = args.index("--only")
        names = args[i + 1].split(",") if i + 1 < len(args) else []
        chosen = [m for m in names if m in dict(MODELS)]
    else:
        show()
        print("说明：直接回车 = 跳过；输入编号用空格或逗号分隔；输入 a = 全部下载")
        try:
            sel = input("请选择要下载的模型: ").strip().lower()
        except EOFError:
            sel = ""
        if sel == "a":
            chosen = [m for m, _ in MODELS if not have(m)]
        elif sel:
            for tok in sel.replace(",", " ").split():
                if tok.isdigit() and 1 <= int(tok) <= len(MODELS):
                    chosen.append(MODELS[int(tok) - 1][0])

    if not chosen:
        print("没有选择要下载的模型，跳过。")
        return
    print(f"\n开始下载 {len(chosen)} 个模型（先国内镜像，失败自动换官方源）...")
    ok = 0
    for i, name in enumerate(chosen, 1):
        print(f"\n[{i}/{len(chosen)}] {name}")
        if fetch_one(name):
            ok += 1
    print(f"\n完成：成功 {ok}/{len(chosen)}。模型目录: {DEST}")
    if ok < len(chosen):
        sys.exit(1)


if __name__ == "__main__":
    main()
