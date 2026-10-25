# -*- coding: utf-8 -*-
"""电脑端朗读单词（Piper 本地神经语音）。

- 默认 Piper：离线、稳定、神经语音音质；模型放在 data/piper_voices/，可以换着选
- 万一 Piper 不可用，自动降级到 PowerShell 的 System.Speech 兜底
- 朗读在后台线程里排队，不会卡住主流程
（Edge 在线语音和本机 SAPI 已按需求移除）
"""
import os
import queue
import subprocess
import tempfile
import threading
import time
import wave
import winsound

import config

_PREVIEW_PIPER = {}       # 设置页试读用的模型缓存（按模型路径）


def _resolve_piper_model(path_str):
    from pathlib import Path

    p = Path(path_str or config.TTS_PIPER_MODEL)
    if not p.is_absolute():
        p = Path(config.ROOT) / p
    return p


def _syn_config(overrides=None):
    """合成参数（语速 / 音量），只在真正合成时才 import piper"""
    from piper import SynthesisConfig

    params = {
        "length_scale": float(config.TTS_PIPER_LENGTH),
        "volume": float(config.TTS_PIPER_VOLUME),
    }
    params.update(overrides or {})
    return SynthesisConfig(**params)


def _synth_piper(voice, text, out_path, syn_config=None):
    with wave.open(out_path, "wb") as wf:
        voice.synthesize_wav(text, wf, syn_config=syn_config or _syn_config())


def _powershell_say(text):
    """最后的兜底：用 PowerShell 的 System.Speech 读一遍（同步）"""
    safe = str(text).replace("'", "''")
    ps = (
        "Add-Type -AssemblyName System.Speech; "
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        "try { $s.SelectVoice((($s.GetInstalledVoices() | Where-Object "
        "{ $_.VoiceInfo.Culture.Name -like 'en*' })[0]).VoiceInfo.Name) } catch {}; "
        f"$s.Speak('{safe}')"
    )
    flags = 0x08000000 if os.name == "nt" else 0   # CREATE_NO_WINDOW：不弹黑框
    subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps],
        capture_output=True, timeout=120, creationflags=flags,
    )


class Speaker:
    """后台线程 + 队列朗读。同一个词短时间内不会重复读（防重复）。"""

    def __init__(self, repeat=None):
        self.repeat = repeat or config.TTS_REPEAT
        self._q = queue.Queue()
        self._last_text, self._last_ts = None, 0.0
        self._engine_name = None
        threading.Thread(target=self._worker, daemon=True).start()

    # ---------- 对外接口 ----------
    def speak(self, text, force=False, repeat=None):
        text = (text or "").strip()
        if not text:
            return False
        now = time.time()
        if (not force
                and text.lower() == self._last_text
                and now - self._last_ts < config.TTS_DEDUP_SECONDS):
            return False
        self._last_text, self._last_ts = text.lower(), now
        self._q.put((text, repeat))
        return True

    def wait(self):
        """等队列里的朗读都放完"""
        self._q.join()

    # ---------- 内部 ----------
    def _worker(self):
        voice = None
        if config.TTS_ENGINE in ("auto", "piper"):
            voice = self._init_piper()
        self._engine_name = "piper" if voice is not None else "powershell"
        if voice is None:
            print("[TTS] Piper 不可用，用 PowerShell 系统语音兜底")

        while True:
            item = self._q.get()
            try:
                if item is None:
                    return
                text, repeat = item
                times = max(1, repeat or self.repeat)
                for i in range(times):
                    if voice is not None and not self._try_piper(voice, text):
                        voice = None
                        print("[TTS] 改用 PowerShell 兜底")
                    if voice is None:
                        _powershell_say(text)
                    if i < times - 1:
                        time.sleep(config.TTS_REPEAT_GAP)
            except Exception as e:
                print(f"[TTS] 朗读出错: {e}")
            finally:
                self._q.task_done()

    def _try_piper(self, voice, text):
        try:
            path = os.path.join(tempfile.gettempdir(), "zxw_piper.wav")
            _synth_piper(voice, text, path)
            winsound.PlaySound(path, winsound.SND_FILENAME)   # 阻塞到播完
            return True
        except Exception as e:
            print(f"[TTS] Piper 朗读失败({e})")
            return False

    def _init_piper(self):
        try:
            from piper import PiperVoice
        except Exception as e:
            print(f"[TTS] Piper 不可用: {e}")
            return None
        try:
            path = _resolve_piper_model(config.TTS_PIPER_MODEL)
            if not path.exists():
                print(f"[TTS] Piper 模型不存在: {path}")
                return None
            t0 = time.time()
            voice = PiperVoice.load(str(path))
            print(f"[TTS] 使用嗓音: Piper {path.stem}（本地神经语音，"
                  f"加载 {time.time() - t0:.1f}s）")
            return voice
        except Exception as e:
            print(f"[TTS] Piper 初始化失败: {e}")
            return None


def list_voices():
    """列出本地可用的 Piper 模型（数据在 data/piper_voices/）"""
    d = _resolve_piper_model("data/piper_voices")
    models = sorted(p.name for p in d.glob("*.onnx")) if d.exists() else []
    print(f"本地 Piper 模型（{len(models)} 个，放在 data/piper_voices/）：")
    for name in models:
        print("  " + name)
    if not models:
        print("  （没有模型。用 python -m piper.download_voices en_US-amy-medium "
              "--download-dir data\\piper_voices 下载）")
    print("\n换模型：改 config.TTS_PIPER_MODEL，或打开设置页 python main.py ui 里选。")


def speak_preview(text, piper_model=None, length=None, volume=None):
    """设置页"试读"：按传入参数同步读一遍，返回实际用的引擎名。"""
    text = (text or "").strip()
    if not text:
        return "none"
    p = _resolve_piper_model(piper_model)
    if p.exists():
        try:
            from piper import PiperVoice

            voice = _PREVIEW_PIPER.get(str(p))
            if voice is None:
                voice = PiperVoice.load(str(p))
                _PREVIEW_PIPER[str(p)] = voice
            overrides = {}
            if length is not None:
                overrides["length_scale"] = float(length)
            if volume is not None:
                overrides["volume"] = float(volume)
            out = os.path.join(tempfile.gettempdir(), "zxw_preview.wav")
            _synth_piper(voice, text, out, _syn_config(overrides))
            winsound.PlaySound(out, winsound.SND_FILENAME)
            return "piper"
        except Exception as e:
            print(f"[试读] Piper 失败: {e}")
    else:
        print(f"[试读] Piper 模型不存在: {p}")
    _powershell_say(text)
    return "powershell"


def speak_once(text, repeat=1):
    """命令行试听用：读完就退出"""
    sp = Speaker(repeat=repeat)
    time.sleep(0.3)
    sp.speak(text, force=True)
    sp.wait()
