# 第三方依赖与开源协议

本项目以 Python 包形式依赖以下开源软件。各软件版权归其作者所有，使用与分发请遵守各自的许可证。

| 依赖 | 版本要求 | 许可证 | 用途 |
|---|---|---|---|
| [uiautomator2](https://github.com/openatx/uiautomator2) | >= 3.2.0 | MIT | 通过 adb 读取/操作安卓界面 |
| [RapidFuzz](https://github.com/rapidfuzz/RapidFuzz) | >= 3.5.0 | MIT | 模糊字符串匹配 |
| [jieba](https://github.com/fxsjy/jieba) | >= 0.42.1 | MIT | 中文分词 |
| [Piper TTS](https://github.com/OHF-voice/piper1-gpl)（pip 包 `piper-tts`） | >= 1.8.0 | **GPL-3.0-or-later** | 本地离线神经语音合成 |

### 关于 Piper 的 GPL 许可

`piper-tts` 1.8.x 采用 **GPL-3.0-or-later**，与本项目采用的 GPL-3.0 一致；
分发本项目时请一并遵守 GPL 的相应要求（例如随附源码）。仅在本机个人使用不构成分发。

## 语音模型

- 来源：[rhasspy/piper-voices](https://huggingface.co/rhasspy/piper-voices)（Hugging Face）。
- 仓库内置 `en_US-amy-medium`；其余模型由 `install.bat` / `tools/fetch_models.py` 按需下载，**不随仓库分发**。
- 各语音模型的训练数据与许可情况不同，请在使用/再分发前阅读对应模型卡（model card）中的许可说明。

## 其他外部组件

- **Android Debug Bridge (adb)**：来自 Android SDK Platform-Tools（Google），由用户自行安装；本项目仅调用它。
- **Python**：CPython，PSF License。
- 本项目与智学网 / 讯飞（iFlytek）**无任何关联**，未包含其任何代码或资源；"智学网"仅指本工具所辅助练习的平台。

## 本项目代码

本项目采用 **GPL-3.0** 许可发布，全文见仓库根目录 [LICENSE](LICENSE)。
依赖链中的 piper-tts 亦为 GPL-3.0-or-later，与本项目许可一致。
