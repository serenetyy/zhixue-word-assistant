# 智学网单词助手（zhixuewang）

在电脑上盯着模拟器里的智学网单词练习：**认词 → 电脑朗读 → 自动作答**。

- **朗读页（单词跟读）**：自动点「点击录音」→ 等 0.5 秒 → 电脑用 Edge 神经女声朗读（默认 1 遍）
  → 点「波纹」结束录音 → 等评测（没通过会自动重录一次，重录时读 2 遍更稳）→ 点「下一题」。
  单题约 10 秒；读多遍可以在 `config.py` 把 `TTS_REPEAT_READING` 改为 2 或 3。
- **拼写页**：从中文释义模糊匹配出单词 → 电脑朗读 → 用 App 自绘键盘逐字母敲入
  （键盘是画出来的，只能按实测坐标点）→ 点「确定」→ 点「下一题」。单题约 13 秒。
- 一切自动操作都可以在 `config.py` 里关掉（`AUTO_READING_FLOW` / `AUTO_FILL_ANSWER`），
  关掉后只做识别 + 朗读 + 提示，自己动手。

## 工作流程

| 步骤 | 做什么 | 用哪个命令 |
|---|---|---|
| 1 | 启动模拟器，确认能连上 | `python main.py probe` |
| 2 | 手动登录智学网学生端，进入单词列表页 | —（人来做） |
| 3 | 抓取单词列表（单词/音标/中文） | `python main.py capture` |
| 4 | 开始练习，脚本自动干活 | `python main.py run` |

## 目录结构

```
zhixuewang/
├── main.py              入口，所有命令都从这里跑
├── config.py            所有可调参数（设备、阈值、按钮文字、语速、等待时间…）
├── requirements.txt     依赖清单
├── zxw/
│   ├── device.py        找设备、连 uiautomator2
│   ├── page.py          读屏文字（控件树）+ 状态栏噪音过滤
│   ├── capture.py       抓单词列表 / 读 words.json
│   ├── matcher.py       中文分词 + 模糊匹配（中文主、音标/拼写辅）
│   ├── actions.py       点按钮 / 阶段判断 / 填答案（内置键盘/输入框）
│   ├── reading.py       朗读（跟读）流程 —— 和拼写完全分开
│   ├── spelling.py      拼写流程 —— 和朗读完全分开
│   ├── keyboard.py      拼写页自绘键盘的按键坐标（实测值）
│   ├── util.py          两个流程共用的小工具
│   ├── tts.py           电脑朗读（Edge 神经语音 → SAPI → PowerShell 自动降级）
│   ├── watcher.py       弹窗处理
│   └── monitor.py       主循环：盯屏 → 认词 → 分发给两个流程
├── tests/test_matcher.py  不连设备也能跑的自测
└── data/                抓取结果（words.json）、probe 的控件树、原始屏幕记录
```

## 安装（已经帮你装好了，换电脑时照做）

```bat
cd /d D:\Codes\projects\zhixuewang
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

adb 已经配好（`config.py` 里指向 `D:\AndroidSDK\platform-tools\adb.exe`）。
朗读默认用 Edge 神经语音（需要联网；断网会自动退回本机 Zira，不影响使用）。

## 每轮使用流程

```bat
cd /d D:\Codes\projects\zhixuewang

REM ① 先确认能读到屏幕（可选，排障用）
.venv\Scripts\python main.py probe

REM ② 手动把模拟器停在【单词列表】页 → 抓取
.venv\Scripts\python main.py capture

REM ③ 开始练习，进入练习页（朗读、拼写都自动做）
.venv\Scripts\python main.py run

REM    也可以分开跑：
REM    .venv\Scripts\python main.py run --mode reading    只自动做跟读题
REM    .venv\Scripts\python main.py run --mode spelling   只自动做拼写题
```

`run` 运行时的按键（自动流程卡住时用）：

- `r` 重读刚才那个词
- `1` / `2` / `3` 试听第 1/2/3 个候选
- `p` 手动点「朗读」
- `s` 手动点「提交」
- `n` 手动点「下一题」
- `f` 用当前匹配结果重填一次（填入 + 提交 + 下一题）
- `q` 退出，并打印这次处理了哪些词

## 命令一览

| 命令 | 作用 |
|---|---|
| `python main.py probe` | 打印当前屏幕读到的文字（已过滤噪音）；`--raw` 连噪音一起看 |
| `python main.py capture` | 自动下滑抓整份单词表 → `data/words.json` |
| `python main.py run` | 监听练习页，朗读+拼写都自动；加 `--mode reading` / `--mode spelling` 可只跑其中一个 |
| `python main.py match "贫瘠的"` | 离线测匹配：看会匹配到哪个词、得分多少 |
| `python main.py tap 朗读` | 在手机上点一个文字按钮（调试按钮文字用） |
| `python main.py type apple` | 往当前页面的输入框填字（调试填答用） |
| `python main.py voices` | 列出电脑上的朗读嗓音 |
| `python main.py speak apple` | 试听一个单词的发音 |

## 调参（都在 config.py）

| 参数 | 默认 | 说明 |
|---|---|---|
| `MATCH_MIN_SCORE` | 0.55 | 得分到这个数才动手；误匹配多就调高，认不出就调低 |
| `MATCH_LOW_SCORE` | 0.35 | 低于它完全不提示；中间档只列候选不动作 |
| `MATCH_MIN_MARGIN` | 0.06 | 领先第二名不到这个数会提示"有歧义" |
| `AUTO_READING_FLOW` | True | 朗读页自动流程开关 |
| `AUTO_FILL_ANSWER` | True | 拼写页自动填答开关（想自己拼就改 False） |
| `AUTO_CLICK_NEXT` | True | 朗读页读完后自动点「下一题」 |
| `READ_BUTTONS` / `SUBMIT_BUTTONS` / `NEXT_BUTTONS` | 朗读/提交/下一题… | 按钮文字对不上就往里加 |
| `READ_AFTER_CLICK_WAIT` | 0.5 | 点「点击录音」后等多久出声 |
| `READ_AFTER_SPEAK_WAIT` | 1.0 | 读完到「点波纹结束录音」之间 |
| `AFTER_FILL_WAIT` / `AFTER_SUBMIT_WAIT` | 0.4 / 0.8 | 填完→提交、提交→下一题的间隔 |
| `NEXT_BUTTON_WAIT` | 25 | 等录音评测出结果最多几秒 |
| `READ_RETRY_TIMES` | 1 | 录音没通过时自动重录几遍（0=直接跳过） |
| `POLL_INTERVAL` / `PAGE_SETTLE` | 2.0 / 1.2 | 看屏频率、页面稳定等待 |
| `TTS_RATE` / `TTS_REPEAT_READING` | 150 / 1 | 语速、跟读录音读几遍（想更稳改 2；脚本保证不超 10 秒） |
| `TTS_VOICE_HINT` | zira | 本机(SAPI)嗓音关键字：`zira`（女声）/ `david`（男声）/ `huihui`（中文） |
| `TTS_EDGE_VOICE` | en-US-AriaNeural | Edge 神经女声；可换 `en-US-JennyNeural`、`en-GB-SoniaNeural` 等 |
| `TTS_ENGINE` | auto | `auto`=Edge→SAPI→PowerShell 自动挑；固定 `sapi` 则只用本机 Zira（不需联网） |
| `NOISE_PACKAGES` / `NOISE_REGEXES` | systemui… | 状态栏噪音过滤规则 |
| `AUTO_CLICK_TEXTS` | 知道了… | 自动点掉的弹窗按钮 |

## 常见问题

**跟读页的机制（实测）**
录音约 10 秒会自动结束；录音中的按钮提示是「点击波纹，结束录音」，点的是那块
`layout_recording` 面板（脚本自动处理）。评测没通过（读音不清晰/没采到音）时页面
会退回「点击录音」，脚本会自动重录一次；想重录更多次就调 `READ_RETRY_TIMES`。
想让电脑的声音更容易被麦克风采到：用电脑麦克风、把系统音量开大一点。

**点不到「点击录音」/「提交」/「下一题」**
脚本优先按控件 id（`iv_record`、`layout_recording`、`tv_next_question`）找，
找不到才退回按文字找。文字对不上就往对应的 `*_BUTTONS` 列表里加；
也可以用 `python main.py tap 文字` 直接测试能不能点到。

**拼写页打字**
拼写页的键盘是画出来的（ky_keyboard），按键坐标是实测值、存在 `zxw/keyboard.py` 里，
脚本按坐标点键。如果在你的模拟器上敲错位了（分辨率不同），把键盘区域截图发我重新标定；
临时调试用 `python main.py type 单词` 看敲入过程。
遇到带空格的词组（比如 dig up）键盘上没有空格键，脚本会提示，需要手动补。

**状态栏文字干扰**
已经按包名（`com.android.systemui`）过滤掉了，还有漏的就把特征加进 `NOISE_REGEXES`。
注意别加"信号""下载"这种普通词 —— 它们可能真是某个单词的释义。

**连不上设备 / `unauthorized`**
模拟器要先进到系统桌面；真机要在弹窗里点"允许 USB 调试"。
都没有设备时脚本会自己试常见模拟器端口（MuMu 7555、雷电 5555、夜神 62001）。

**没声音 / 评测老不过 / 想换嗓音**
默认用 Edge 神经女声 `en-US-AriaNeural`（清晰度最好，需联网；断网会自动退回本机 Zira）。
`.venv\Scripts\python main.py speak apple` 试音；`python main.py voices` 列出全部可选嗓音
（本机 + Edge 在线）。想换：填 `TTS_EDGE_VOICE`（如 `en-US-JennyNeural`）；
想完全用本机、不联网：把 `TTS_ENGINE` 改成 `sapi`。评测老不过一般是读音不够清晰，
还可以把 `TTS_RATE`（SAPI）或 `TTS_EDGE_RATE`（如 `-15%`）调慢一点。

**匹配不准 / 老提示"有歧义"**
`python main.py match "那段中文"` 复现，看 top 几名得分差多少再调 `MATCH_MIN_SCORE`；
中文释义识别得不好时，直接用记事本改 `data/words.json` 里的 `cn` 字段最有效。

## 注意

- 自动作答的开关都在 `config.py`，随时可以关掉改成手动模式。
- 仅作个人学习辅助，请遵守学校/平台的使用规定。
