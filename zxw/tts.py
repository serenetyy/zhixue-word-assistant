# -*- coding: utf-8 -*-
"""电脑端朗读单词。三个后备梯队：

  1. Edge 神经网络语音（edge-tts，最清晰，需要联网）
  2. Windows SAPI SpVoice（本机 Zira 等，pywin32；pyttsx3 有"同一引擎只出声一次"
     的著名 bug，已弃用）
  3. PowerShell System.Speech（最后的兜底）

用哪个由 config.TTS_ENGINE 决定（auto=按上面顺序自动挑）。
朗读在后台线程里排队，不会卡住主流程。
"""
import asyncio
import ctypes
import os
import queue
import subprocess
import tempfile
import threading
import time
import wave
import winsound

import config

_MP3_PATH = os.path.join(tempfile.gettempdir(), "zxw_tts.mp3")
_PREVIEW_PIPER = {}       # 设置页试读用的 Piper 模型缓存（按模型路径）


def _play_mp3(path):
    """用 Windows 自带的 MCI 播放 mp3，阻塞到播完为止"""
    winmm = ctypes.WinDLL("winmm")
    winmm.mciSendStringW.argtypes = [
        ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint, ctypes.c_void_p,
    ]
    winmm.mciSendStringW.restype = ctypes.c_uint
    buf = ctypes.create_unicode_buffer(512)

    def send(cmd):
        return winmm.mciSendStringW(cmd, buf, 511, None)

    send("close zxw_tts")                       # 清理上次可能没关干净的
    err = send(f'open "{path}" type mpegvideo alias zxw_tts')
    if err:
        err = send(f'open "{path}" alias zxw_tts')
    if err:
        raise RuntimeError(f"MCI 打不开音频（错误码 {err}）")
    try:
        send("setaudio zxw_tts volume to 1000")   # 拉满，方便麦克风采到
        err = send("play zxw_tts wait")
        if err:
            raise RuntimeError(f"MCI 播放失败（错误码 {err}）")
    finally:
        send("close zxw_tts")


def _powershell_say(text, rate_val=None):
    """最后的兜底：用 PowerShell 的 System.Speech 读一遍（同步）"""
    rate = max(-10, min(10, int(round(((config.TTS_RATE if rate_val is None else rate_val) - 150) / 25.0))))
    safe = str(text).replace("'", "''")
    ps = (
        "Add-Type -AssemblyName System.Speech; "
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        f"$s.Rate = {rate}; "
        "try { $s.SelectVoice((($s.GetInstalledVoices() | Where-Object "
        "{ $_.VoiceInfo.Culture.Name -like 'en*' })[0]).VoiceInfo.Name) } catch {}; "
        f"$s.Speak('{safe}')"
    )
    flags = 0x08000000 if os.name == "nt" else 0   # CREATE_NO_WINDOW：不弹黑框
    subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps],
        capture_output=True, timeout=120, creationflags=flags,
    )


def _resolve_piper_model(path_str):
    from pathlib import Path

    p = Path(path_str or config.TTS_PIPER_MODEL)
    if not p.is_absolute():
        p = Path(config.ROOT) / p
    return p


def speak_preview(text, engine="auto", rate=None, sapi_hint=None, piper_model=None):
    """设置页"试读"：按传入的参数同步读一遍，返回实际用的引擎名。

    和正式流程的 Speaker 分开实现（那个是后台队列），这里要立即、可指定嗓音/模型。
    """
    text = (text or "").strip()
    if not text:
        return "none"
    engine = (engine or "auto").lower()
    rate_val = int(rate) if rate is not None else config.TTS_RATE
    hint = sapi_hint if sapi_hint is not None else config.TTS_VOICE_HINT
    used = None

    if engine in ("auto", "piper"):
        p = _resolve_piper_model(piper_model)
        if p.exists():
            try:
                voice = _PREVIEW_PIPER.get(str(p))
                if voice is None:
                    from piper import PiperVoice

                    voice = PiperVoice.load(str(p))
                    _PREVIEW_PIPER[str(p)] = voice
                path = os.path.join(tempfile.gettempdir(), "zxw_preview.wav")
                with wave.open(path, "wb") as wf:
                    voice.synthesize_wav(text, wf)
                winsound.PlaySound(path, winsound.SND_FILENAME)
                used = "piper"
            except Exception as e:
                print(f"[试读] Piper 失败: {e}")
        else:
            print(f"[试读] Piper 模型不存在: {p}")

    if used is None and engine in ("auto", "sapi", "edge"):
        try:
            import pythoncom
            import win32com.client

            pythoncom.CoInitialize()
            v = win32com.client.Dispatch("SAPI.SpVoice")
            pick = _pick_voice(v, hint)
            if pick is not None:
                v.Voice = pick
            v.Rate = max(-10, min(10, int(round((rate_val - 150) / 25.0))))
            v.Volume = int(max(0.0, min(1.0, config.TTS_VOLUME)) * 100)
            v.Speak(text)
            used = "sapi"
        except Exception as e:
            print(f"[试读] SAPI 失败: {e}")

    if used is None:
        _powershell_say(text, rate_val)
        used = "powershell"
    return used


def _pick_voice(voice_obj, hint):
    """挑一个嗓音。hint 可以是描述关键字（zira/david/huihui），也可以是语言代码（en-us/zh-cn）"""
    hint = (hint or "").lower().strip()
    voices = voice_obj.GetVoices()
    count = voices.Count
    if count == 0:
        return None

    def desc(i):
        return voices.Item(i).GetDescription()

    # 1) 关键字直接出现在描述里
    if hint:
        for i in range(count):
            if hint in desc(i).lower():
                return voices.Item(i)
    # 2) 语言代码：en-us / zh-cn
    if hint.startswith("en"):
        en = voice_obj.GetVoices("Language=409")     # 409 = en-US
        if en.Count:
            return en.Item(0)
        for i in range(count):
            if "english" in desc(i).lower():
                return voices.Item(i)
    if hint.startswith("zh"):
        zh = voice_obj.GetVoices("Language=804")     # 804 = zh-CN
        if zh.Count:
            return zh.Item(0)
        for i in range(count):
            if "chinese" in desc(i).lower():
                return voices.Item(i)
    # 3) 默认第一个
    return voices.Item(0)


class Speaker:
    """后台线程 + 队列朗读。同一个词短时间内不会重复读（防重复）。"""

    def __init__(self, repeat=None):
        self.repeat = repeat or config.TTS_REPEAT
        self._q = queue.Queue()
        self._last_text, self._last_ts = None, 0.0
        self._engine_name = None          # worker 初始化完会写上 edge/sapi/powershell
        self._edge_cache = None           # (voice, text)：这个组合的 mp3 已合成好
        self._cache_lock = threading.Lock()
        threading.Thread(target=self._worker, daemon=True).start()

    def repeat_fit(self, max_seconds):
        """按当前已合成的音频长度，算"最多能读几遍"（不超录音窗口）。

        只在 Edge 模式下有意义（mp3 大小 ≈ 时长）；SAPI 照配置来。
        需要先调用过 prepare()，否则按配置返回。
        """
        if self._engine_name != "edge":
            return self.repeat
        try:
            dur = os.path.getsize(_MP3_PATH) * 8 / 48000.0   # 48kbps 估算时长
        except OSError:
            return self.repeat
        gap = config.TTS_REPEAT_GAP
        n = int((max_seconds + gap) // (dur + gap))          # n*dur+(n-1)*gap <= max
        return max(1, min(config.TTS_REPEAT_READING, n))

    def prepare(self, text):
        """提前合成音频（只有 Edge 需要联网合成，慢；在进录音窗口前先备好）。

        失败不影响后续：真播的时候还会再试一次，再失败自动降级 SAPI。
        """
        text = (text or "").strip()
        if not text or self._engine_name != "edge":
            return
        voice = config.TTS_EDGE_VOICE
        try:
            with self._cache_lock:
                if self._edge_cache != (voice, text):
                    self._edge_synth(text, voice, _MP3_PATH)
                    self._edge_cache = (voice, text)
        except Exception as e:
            print(f"[TTS] 预合成失败({e})，播放时再试")

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
        # state 里放三个引擎的实例（None=这个引擎没启用/没初始化成功）
        state = {"piper": None, "edge": None, "sapi": None}
        mode = config.TTS_ENGINE
        candidates = {
            "auto": ["piper", "sapi"],
            "piper": ["piper"],
            "sapi": ["sapi"],
            "edge": ["edge", "sapi"],
            "powershell": [],
        }.get(mode, ["piper", "sapi"])

        self._engine_name = "powershell"
        for name in candidates:
            if name == "piper":
                voice = self._init_piper()
                if voice is not None:
                    state["piper"] = voice
                    self._engine_name = "piper"
                    break
            elif name == "edge":
                if self._init_edge():
                    state["edge"] = config.TTS_EDGE_VOICE
                    self._engine_name = "edge"
                    print(f"[TTS] 使用嗓音: {config.TTS_EDGE_VOICE}（Edge 神经网络语音）")
                    break
            elif name == "sapi":
                voice = self._init_sapi()
                if voice is not None:
                    state["sapi"] = voice
                    self._engine_name = "sapi"
                    break
        if self._engine_name == "powershell":
            print("[TTS] 用 PowerShell 系统语音朗读")

        while True:
            item = self._q.get()
            try:
                if item is None:
                    return
                text, repeat = item
                times = max(1, repeat or self.repeat)
                for i in range(times):
                    self._speak_once(text, state)
                    if i < times - 1:
                        time.sleep(config.TTS_REPEAT_GAP)
            except Exception as e:
                print(f"[TTS] 朗读出错: {e}")
            finally:
                self._q.task_done()

    def _speak_once(self, text, state):
        """读一遍。Piper → Edge → SAPI → PowerShell，谁坏了就往下走。"""
        if state["piper"] is not None:
            try:
                self._say_piper(state["piper"], text)
                return
            except Exception as e:
                print(f"[TTS] Piper 朗读失败({e})，降级")
                state["piper"] = None
        if state["edge"]:
            try:
                self._say_edge(state["edge"], text)
                return
            except Exception as e:
                print(f"[TTS] Edge 语音失败({e})，本场改用本机嗓音兜底")
                state["edge"] = None
        if state["sapi"] is not None:
            try:
                state["sapi"].Speak(text)
                return
            except Exception as e:
                print(f"[TTS] SAPI 朗读失败({e})，改用 PowerShell")
                state["sapi"] = None
        self._say_powershell(text)

    def _init_piper(self):
        """加载本地 Piper 神经语音模型"""
        try:
            from pathlib import Path

            from piper import PiperVoice
        except Exception as e:
            print(f"[TTS] Piper 不可用: {e}")
            return None
        try:
            path = Path(config.TTS_PIPER_MODEL)
            if not path.is_absolute():
                path = Path(config.ROOT) / path
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

    def _say_piper(self, voice, text):
        path = os.path.join(tempfile.gettempdir(), "zxw_piper.wav")
        with wave.open(path, "wb") as wf:
            voice.synthesize_wav(text, wf)
        winsound.PlaySound(path, winsound.SND_FILENAME)   # 阻塞到播完

    def _init_edge(self):
        """验证 Edge 语音可用（会真合成一小段，不出声）"""
        try:
            import edge_tts  # noqa: F401
            self._edge_synth("ok", config.TTS_EDGE_VOICE, _MP3_PATH)
            return True
        except Exception as e:
            print(f"[TTS] Edge 语音不可用: {e}")
            return False

    def _edge_synth(self, text, voice, path):
        import edge_tts

        async def _run():
            comm = edge_tts.Communicate(text, voice, rate=config.TTS_EDGE_RATE)
            await comm.save(path)

        asyncio.run(_run())

    def _say_edge(self, voice, text):
        with self._cache_lock:
            if self._edge_cache != (voice, text):     # 同一个词播多遍时只合成一次
                self._edge_synth(text, voice, _MP3_PATH)
                self._edge_cache = (voice, text)
            _play_mp3(_MP3_PATH)

    def _init_sapi(self):
        """初始化 SAPI 嗓音，成功返回 voice 对象，失败返回 None"""
        try:
            import pythoncom
            import win32com.client

            pythoncom.CoInitialize()      # 子线程里用 COM 必须先在当前线程初始化
            voice = win32com.client.Dispatch("SAPI.SpVoice")
            pick = _pick_voice(voice, config.TTS_VOICE_HINT)
            if pick is not None:
                voice.Voice = pick
            voice.Rate = max(-10, min(10, int(round((config.TTS_RATE - 150) / 25.0))))
            voice.Volume = int(max(0.0, min(1.0, config.TTS_VOLUME)) * 100)
            desc = voice.Voice.GetDescription()
            print(f"[TTS] 使用嗓音: {desc}")
            return voice
        except Exception as e:
            print(f"[TTS] SAPI 初始化失败: {e}")
            return None

    def _say_powershell(self, text):
        _powershell_say(text)


def list_voices():
    """列所有可用嗓音：本机 SAPI + Edge 在线神经网络语音"""
    import pythoncom
    import win32com.client

    pythoncom.CoInitialize()
    v = win32com.client.Dispatch("SAPI.SpVoice")
    vs = v.GetVoices()
    print(f"本机嗓音（SAPI）一共 {vs.Count} 个：")
    for i in range(vs.Count):
        print(f"  {i}. {vs.Item(i).GetDescription()}")
    print('  想指定某个，把它描述里的关键字（zira / david / huihui）填进 config.py 的 TTS_VOICE_HINT')

    print("\nEdge 在线神经网络嗓音（英文，清晰度最好；名字填进 TTS_EDGE_VOICE）:")
    try:
        import edge_tts
        voices = asyncio.run(edge_tts.list_voices())
    except Exception as e:
        print(f"  （获取失败: {e}）")
        return
    for item in voices:
        loc = item.get("Locale", "")
        if loc.startswith("en-"):
            print(f"  {item['ShortName']:34s} {item.get('Gender', ''):7s} {loc}")


def speak_once(text, repeat=1):
    """命令行试听用：读完就退出"""
    sp = Speaker(repeat=repeat)
    time.sleep(0.3)
    sp.speak(text, force=True)
    sp.wait()
