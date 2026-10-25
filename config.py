# -*- coding: utf-8 -*-
"""
智学网单词助手 —— 配置
改完保存，重新运行脚本即可生效。带 [可调] 的地方都可以放心改。
"""
from pathlib import Path

# ---------------- 目录 ----------------
ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"                      # 数据/抓取结果都放这里
RAW_DIR = DATA_DIR / "raw_screens"            # 抓取时的原始屏幕文字（排查用）
WORDS_FILE = DATA_DIR / "words.json"          # 单词表（抓到后可以用记事本直接改）

# ---------------- 设备 ----------------
# adb 的完整路径。你电脑上没把 adb 加进 PATH，所以这里直接指向 AndroidSDK 自带的。
ADB_PATH = r"D:\AndroidSDK\platform-tools\adb.exe"

# 模拟器预设（设置页可选）：运行时会先连它的默认端口，连不上再自动探测 adb 设备
# auto / ldplayer(雷电 5555) / mumu(MuMu 7555) / bluestacks(蓝叠 5555) / custom
EMULATOR = "auto"

# 自定义设备串号（adb devices 里显示的那一列，如 127.0.0.1:7555）。
# 填了就优先用它；EMULATOR 选 custom 时也是用这个。留空 = 自动。
DEVICE_SERIAL = ""

# ---------------- 屏幕监听 ----------------
POLL_INTERVAL = 2.0          # 每隔几秒看一眼屏幕
PAGE_SETTLE = 1.2            # 页面变化后先等几秒（等动画/加载稳定）再识别
CAPTURE_SCROLL_WAIT = 0.9    # 抓列表时，每次滑动后等几秒
CAPTURE_MAX_SCROLLS = 80     # 抓列表时最多滑多少屏

# 屏幕上这些文字不参与匹配（UI 按钮/提示语，防止误匹配）
IGNORE_TEXTS = [
    "跳过", "下一题", "下一词", "上一步", "提交", "确认", "确定", "取消", "完成",
    "播放", "返回", "退出", "练习", "单词", "单词表", "音标", "拼写",
    "中文", "释义", "开始", "继续", "提示", "查看", "解析", "收词", "朗读", "录音",
    # 单词跟读页的 UI 文字（实测）
    "单词跟读", "跟读", "点击录音", "点击停止", "示范音",
]

# ---------------- 状态栏噪音过滤 ----------------
# 这些包名下的文字直接丢掉。实测状态栏/通知栏都来自 com.android.systemui。
NOISE_PACKAGES = [
    "com.android.systemui",
]
# 兜底规则：文字符合这些特征的也丢掉。
# 注意：这里只用"一眼假"的强特征（满格/百分比/apk 之类），
# 千万别把"信号""下载""通知"这种普通词加进来 —— 它们可能真是某个单词的释义。
NOISE_REGEXES = [
    r"^\d{1,2}:\d{2}$",                 # 5:23
    r"^[上下]午\s*\d{1,2}:\d{2}$",      # 下午5:23
    r".*\.apk$",                        # 通知里的安装包名
    r".*满格。?$",                      # WLAN 信号满格。
    r".*(正在充电|已完成\s*\d+%).*",    # 正在充电，已完成 100%。
    r"^(Android|安卓)\s*系统通知.*",
    r"^(WLAN|WiFi|Wi-Fi)\s.*$",
]

# ---------------- 模糊匹配 ----------------
MATCH_MIN_SCORE = 0.55    # 得分达到多少才认为"认出来了"（0~1）
MATCH_LOW_SCORE = 0.35    # 低于 MIN 但高于 LOW：只提示不动作，让你自己判断
MATCH_MIN_MARGIN = 0.06   # 第一名比第二名至少高多少，否则提示"有歧义"
# 分词时忽略的虚词，不参与匹配
STOPWORDS = ["的", "了", "地", "得", "使", "让", "某人", "某物", "通常", "常", "等"]

# ---------------- 朗读（TTS） ----------------
TTS_ENGINE = "auto"       # auto / piper / powershell（auto=Piper，不行才用 PowerShell 兜底）
TTS_REPEAT = 1            # 每个单词读几遍（提示/试听用）
TTS_REPEAT_READING = 1    # 朗读页录音时读几遍（读多遍更稳但更慢；保证不超 10 秒）
TTS_REPEAT_GAP = 0.9      # 两遍之间隔几秒（只有读多遍时才用得上）
TTS_DEDUP_SECONDS = 6.0   # 同一个词多少秒内不重复朗读（防重复；自动流程里不受此限制）

# Piper 本地神经语音（离线、稳定、免费；每个模型约 60-75MB，放 data/piper_voices/）
# 下载更多声音：python -m piper.download_voices en_US-lessac-medium --download-dir data/piper_voices
# 也可以直接用设置页（python main.py ui）选
TTS_PIPER_MODEL = "data/piper_voices/en_US-amy-medium.onnx"
TTS_PIPER_LENGTH = 1.0    # 语速：1.0=原速，>1 更慢，<1 更快
TTS_PIPER_VOLUME = 1.0    # 音量倍数：1.0=原声；想更容易被模拟器麦克风采到可调 1.3~1.8

# ---------------- 朗读发音 ----------------
# 朗读时的缩写展开（只影响发音，不影响拼写/匹配）。
# 词表里有 "set sth aside" 这种写法，朗读要读成 "set something aside"，
# 但拼写页还是敲 sth。
SPEECH_EXPAND = {
    "sth": "something",
    "sb": "somebody",
    "esp": "especially",
    "etc": "etcetera",
    "e.g.": "for example",
    "i.e.": "that is",
}

# ---------------- 自动作答流程 ----------------
AUTO_READING_FLOW = True   # 朗读页：自动点"朗读" → 电脑朗读 → 点"下一题"
AUTO_FILL_ANSWER = True    # 拼写页：自动把匹配出的单词填进输入框并提交
AUTO_CLICK_NEXT = True     # 朗读页读完后是否自动点"下一题"

# 实测到的控件 resource-id（比文字稳，脚本优先按它找；找不到自动退回按文字找）
ID_RECORD = "iv_record"              # 录音按钮（单词跟读页，点它开始录音）
ID_RECORD_WAVE = "layout_recording"  # 录音中的"波纹"面板，点它结束录音
ID_NEXT = "tv_next_question"         # "下一题"

# 录音结束、评完分后，录音按钮的提示会变成这个 → 说明可以点"下一题"了
RECORD_DONE_TEXTS = ["点击重录"]
# 录音被丢弃（麦克风没采到有效声音）时，页面会退回这个状态
RECORD_FRESH_TEXTS = ["点击录音"]
# 录音被丢弃时自动重录几遍（0=不重录，直接跳过）
READ_RETRY_TIMES = 1

# 起始模块（run 不带 --mode 时用这个；跑完会问要不要接着做另一个模块）
RUN_MODE = "reading"       # reading=先做朗读 / spelling=先做拼写

# 各阶段按钮的文字（对不上就往这里加，脚本按顺序找第一个存在的）
# "点击录音" 是实测到的朗读页按钮文字；点不到时脚本会去找它旁边的图标点
READ_BUTTONS = ["点击录音", "点击重录", "点击朗读", "开始朗读", "开始录音", "朗读", "录音"]
SUBMIT_BUTTONS = ["确定", "提交", "确认提交", "提交答案"]   # 拼写页的提交按钮文字是"确定"（实测）
NEXT_BUTTONS = ["下一题", "下一词", "下一个", "下一组"]
# 找不到输入框时，按提示文字再找一遍（"请输入单词"这类提示常常就在输入框上）
INPUT_HINTS = ["请输入", "输入单词", "点击输入", "填写", "作答"]

# 各步骤之间的等待（秒），模拟器卡就调大
READ_AFTER_CLICK_WAIT = 0.5    # 点了"点击录音"后等多久电脑再出声（先让它进录音状态）
READ_AFTER_SPEAK_WAIT = 1.0    # 读完到"点波纹结束录音"之间
AFTER_FILL_WAIT = 0.4          # 填完答案到点"提交"
AFTER_SUBMIT_WAIT = 0.8        # 提交完到点"下一题"
AFTER_STOP_WAIT = 0.5          # 点完波纹后歇一下再等评分
NEXT_BUTTON_WAIT = 25.0        # 等评分完成（"点击重录"出现），最多等几秒
KEY_CLICK_WAIT = 0.15          # 拼写页用内置键盘打字时，每个字母点击的间隔

# 注意：录音约 10 秒会自动结束（静音会被丢弃）。
# 所以 TTS_REPEAT_READING × 朗读时长 要控制在 10 秒内（默认读 1 遍，安全）。

# ---------------- 弹窗 watcher ----------------
# 屏幕上出现这些文字的按钮，脚本自动帮你点掉
AUTO_CLICK_TEXTS = ["知道了", "我知道了", "继续"]
# 出现这些文字只提醒、不点击，交给你手动处理
WARN_ONLY_TEXTS = ["退出", "结束", "放弃", "交卷"]
