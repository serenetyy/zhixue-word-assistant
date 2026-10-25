# 第三方依赖与开源协议

本项目以 Python 包形式依赖以下开源软件。各软件版权归其作者所有，使用与分发请遵守各自的许可证。

| 依赖 | 版本要求 | 许可证 | 用途 |
|---|---|---|---|
| [uiautomator2](https://github.com/openatx/uiautomator2) | >= 3.2.0 | MIT | 通过 adb 读取/操作安卓界面 |
| [RapidFuzz](https://github.com/rapidfuzz/RapidFuzz) | >= 3.5.0 | MIT | 模糊字符串匹配 |
| [jieba](https://github.com/fxsjy/jieba) | >= 0.42.1 | MIT | 中文分词 |
| [Piper TTS](https://github.com/OHF-voice/piper1-gpl)（pip 包 `piper-tts`） | >= 1.8.0 | **GPL-3.0-or-later** | 本地离线神经语音合成 |

### 关于 Piper 的 GPL 许可

`piper-tts` 1.8.x 采用 **GPL-3.0-or-later**。如果你把本项目（或其打包产物）**分发**给他人，
整体需遵守 GPL-3.0 的相应要求（例如以 GPL-3.0 许可发布整体程序并提供相应源码）。
仅在本机个人使用不构成分发，不受此约束。若希望采用宽松许可发布，可考虑仅保留
Piper 作为**可选**运行依赖、或改用旧版 MIT 许可的 piper 引擎（需自行修改代码适配接口）。

## 语音模型

- 来源：[rhasspy/piper-voices](https://huggingface.co/rhasspy/piper-voices)（Hugging Face）。
- 仓库内置 `en_US-amy-medium`；其余模型由 `install.bat` / `tools/fetch_models.py` 按需下载，**不随仓库分发**。
- 各语音模型的训练数据与许可情况不同，请在使用/再分发前阅读对应模型卡（model card）中的许可说明。

## 其他外部组件

- **Android Debug Bridge (adb)**：来自 Android SDK Platform-Tools（Google），由用户自行安装；本项目仅调用它。
- **Python**：CPython，PSF License。
- 本项目与智学网 / 讯飞（iFlytek）**无任何关联**，未包含其任何代码或资源；"智学网"仅指本工具所辅助练习的平台。

## 本项目代码

本仓库尚未附带项目自身的开源许可证文件。若公开发布，请自行选择并添加 `LICENSE`
（受上文 Piper GPL-3.0 依赖影响，推荐 GPL-3.0；如选择其他许可证请先评估合规性）。
