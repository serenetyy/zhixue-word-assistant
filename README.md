# 智学网单词助手

在电脑上驱动安卓模拟器做智学网单词练习：**识别题目 → 本地神经语音朗读 → 自动作答**。
支持「单词跟读」和「单词拼写」两种题型。

> 本工具与智学网 / 讯飞无任何关联，仅供个人学习辅助使用，请遵守平台使用规定。

## 功能

- **朗读页（单词跟读）**：点录音 → 电脑朗读（Piper 本地神经语音）→ 点「波纹」结束录音
  → 等评测（没过自动重录一次）→ 点下一题
- **拼写页（单词拼写）**：中文释义模糊匹配出单词 → App 自绘键盘逐字母敲入 → 点「确定」→ 点下一题
- **一次只跑一个模块**：做完会像 apt 一样问「是否接着做另一个模块？[y/N]」，加 `-y` 自动继续
- 状态栏噪音过滤、弹窗处理、防重复朗读；词组缩写朗读展开（`sth` → something，拼写仍按原词）
- **本地设置页**：换声音模型 / 语速 / 音量、单词试读、模拟器预设（雷电 / MuMu / 蓝叠）、匹配阈值

## 快速开始

1. 启动模拟器（雷电 / MuMu / 蓝叠均可，需开启 USB 调试）并**手动登录智学网学生端**
2. 双击 **`install.bat`**：检测/安装 Python 3.10+（没有则自动下载，失败切国内镜像）、
   可选创建 `.venv`、安装依赖、按需选择下载语音模型
3. 双击 **`run.bat`**，按菜单操作
4. 第一次使用：模拟器停在【单词列表】页 → `run.bat` → `[1]` 抓取词表；
   之后 `run.bat` → `[2]` 做题

## run.bat 菜单

| 选项 | 说明 |
|---|---|
| [1] 抓取单词表 | 模拟器停在【单词列表】页时使用，抓取到 `data/words.json` |
| [2] 交互模式 | 运行一个模块；结束后询问下一步（重新运行 / 切换模块 / 返回主菜单 / 退出），可 Ctrl+C 退出 |
| [3] 自动流转 | 模块完成后自动切换到另一模块（相当于 `-y`） |
| [4] 网页面板 | 打开本地设置页 `http://127.0.0.1:8765` |
| [5] 自定义参数 | 显示命令说明，输入参数直接传给 `main.py`（如 `run --mode reading -y`） |
| [0] 退出 | 关闭程序 |

> 设置页保存的参数在**下次运行模块时**生效：回到菜单重新选择模块即可（菜单每次运行都是新进程）。

## 命令行速查

| 命令 | 作用 |
|---|---|
| `python main.py capture` | 抓取单词列表 → `data/words.json`（模拟器停在单词列表页） |
| `python main.py run --mode reading` | 只做朗读；`--mode spelling` 只做拼写；`-y` 自动切换模块 |
| `python main.py ui` | 本地设置页 |
| `python main.py probe` | 看当前屏幕能读到哪些文字（`--raw` 含噪音和包名） |
| `python main.py match "贫瘠的"` | 离线测试模糊匹配 |
| `python main.py tap 朗读` / `type apple` | 调试：按文字点按钮 / 往输入框填字 |
| `python main.py voices` / `speak apple` | 列出语音模型 / 试听发音 |

## 语音模型

仓库内置 `en_US-amy-medium`（美音女声）。更多模型用 **`install.bat`** 或：

```bat
.venv\Scripts\python tools\fetch_models.py          REM 交互选择、统一下载
.venv\Scripts\python tools\fetch_models.py --list   REM 只看清单
```

下载先走国内镜像（hf-mirror.com），失败自动换官方源。设置页里可直接切换模型、调速、试读。

## 目录结构

```
├── install.bat / install.ps1  安装（bat 只是启动器，逻辑在 ps1）
├── run.bat                    启动菜单（逻辑在 tools/menu.py）
├── main.py                    命令行入口
├── config.py                  所有可调参数（设置页会写这里）
├── ui/index.html              本地设置页
├── tools/menu.py              启动菜单
├── tools/fetch_models.py      语音模型下载工具
├── zxw/                       核心代码
│   ├── device.py              设备连接（模拟器预设 + 自动探测 adb）
│   ├── page.py                读屏文字 + 状态栏噪音过滤
│   ├── capture.py             抓单词表
│   ├── matcher.py             中文分词 + 模糊匹配
│   ├── reading.py / spelling.py  朗读 / 拼写两个模块（互相独立）
│   ├── keyboard.py            拼写页自绘键盘坐标
│   ├── actions.py / util.py   页面操作 / 公用工具
│   ├── tts.py                 Piper 本地语音（PowerShell 兜底）
│   ├── uiserver.py            设置页本地服务
│   ├── watcher.py             弹窗处理
│   └── monitor.py             主循环与模块调度
├── tests/test_matcher.py      离线自测（56 项，本地保留，默认不入库）
└── data/                      本地数据（词表、模型），不入库（内置默认模型除外）
```

## 常见问题

- **连不上模拟器**：设置页选对应模拟器（雷电 5555 / MuMu 7555 / 蓝叠 5555）；连不上会自动探测 adb 设备。
  确认模拟器已进桌面、开启了 USB 调试；adb 不在 PATH 时把路径填进 `config.py` 的 `ADB_PATH`。
- **点不到按钮**：`python main.py probe` 看屏幕实际文字，把按钮文字加进 `config.py` 的 `*_BUTTONS`。
- **拼写页敲错位**：键盘坐标按 1080x1920 实测（`zxw/keyboard.py`），换分辨率需要重新标定。
- **评测老不过**：设置页换 en_US 模型、调慢语速、调大音量倍数。
- **录音**：约 10 秒自动结束（静音会被丢弃）。抓完词表建议检查一下 `data/words.json`。

## 开源协议

本项目以 **GPL-3.0** 发布，许可证全文见 [LICENSE](LICENSE)。
第三方依赖的许可说明见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)
（其中 piper-tts 同为 GPL-3.0-or-later）。
