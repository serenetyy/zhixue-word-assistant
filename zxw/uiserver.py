# -*- coding: utf-8 -*-
"""可视化设置页：本地小网页，改参数、选嗓音/模型、单词试读。

启动：python main.py ui
- 只监听 127.0.0.1
- 保存时把参数写回 config.py（只改对应行，注释都保留）
- 试读会按页面上的当前参数（不用先保存）立即朗读
"""
import json
import re
import runpy
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import config
from . import tts


def config_path():
    return Path(config.ROOT) / "config.py"


def load_values(path=None):
    """执行 config.py，取出可编辑的简单配置项（不污染本进程的 config 模块）"""
    path = Path(path) if path else config_path()
    ns = runpy.run_path(str(path))
    out = {}
    for k, v in ns.items():
        if not k.isupper():
            continue
        if isinstance(v, (bool, int, float, str, list, dict)):
            out[k] = v
    return out


def _coerce(old, value):
    if isinstance(old, bool):
        return bool(value)
    if isinstance(old, int):
        return int(float(value))
    if isinstance(old, float):
        return float(value)
    if isinstance(old, str):
        return str(value)
    if isinstance(old, list):
        return list(value)
    if isinstance(old, dict):
        return dict(value)
    return value


def apply_changes(changes, path=None):
    """把 changes 写回 config.py 对应行（保留行尾注释），返回最新配置"""
    path = Path(path) if path else config_path()
    src = path.read_text(encoding="utf-8")
    current = load_values(path)
    for key, value in (changes or {}).items():
        if key not in current or isinstance(current[key], (dict, list)):
            continue          # 只允许改简单配置项（列表/字典留着手改）
        new_val = _coerce(current[key], value)
        pattern = re.compile(rf"^({re.escape(key)}\s*=\s*)(.*?)(\s*#.*)?$", re.M)
        literal = repr(new_val)

        def repl(m, literal=literal):
            return f"{m.group(1)}{literal}{m.group(3) or ''}"

        src, n = pattern.subn(repl, src, count=1)
        if n == 0:
            raise ValueError(f"config.py 里找不到 {key} 的赋值行")
    path.write_text(src, encoding="utf-8")
    return load_values(path)


def list_voices():
    """列可选的嗓音/模型：本机 SAPI 嗓音、Piper 模型、Edge 常用嗓音"""
    out = {"sapi": [], "piper": [], "edge": []}
    try:
        import pythoncom
        import win32com.client

        pythoncom.CoInitialize()
        v = win32com.client.Dispatch("SAPI.SpVoice")
        vs = v.GetVoices()
        out["sapi"] = [vs.Item(i).GetDescription() for i in range(vs.Count)]
    except Exception as e:
        out["sapi_error"] = str(e)
    d = Path(config.ROOT) / "data" / "piper_voices"
    if d.exists():
        out["piper"] = sorted(p.name for p in d.glob("*.onnx"))
    out["edge"] = [
        "en-US-AriaNeural", "en-US-JennyNeural", "en-US-MichelleNeural",
        "en-GB-SoniaNeural", "en-GB-LibbyNeural",
    ]
    return out


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass                     # 控制台安静点

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        try:
            if self.path in ("/", "/index.html"):
                html = (Path(config.ROOT) / "ui" / "index.html").read_text(encoding="utf-8")
                self._send(200, html, "text/html; charset=utf-8")
            elif self.path.startswith("/api/config"):
                self._send(200, json.dumps(load_values(), ensure_ascii=False))
            elif self.path.startswith("/api/voices"):
                self._send(200, json.dumps(list_voices(), ensure_ascii=False))
            else:
                self._send(404, json.dumps({"error": "not found"}))
        except Exception as e:
            self._send(500, json.dumps({"error": str(e)}, ensure_ascii=False))

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
            data = json.loads(self.rfile.read(length) or b"{}")
        except Exception:
            data = {}
        try:
            if self.path.startswith("/api/config"):
                values = apply_changes(data.get("changes") or {})
                self._send(200, json.dumps({"ok": True, "config": values}, ensure_ascii=False))
            elif self.path.startswith("/api/speak"):
                used = tts.speak_preview(
                    data.get("text", ""),
                    engine=data.get("engine"),
                    rate=data.get("rate"),
                    sapi_hint=data.get("sapi_hint"),
                    piper_model=data.get("piper_model"),
                )
                self._send(200, json.dumps(
                    {"ok": used != "none", "engine": used}, ensure_ascii=False))
            else:
                self._send(404, json.dumps({"error": "not found"}))
        except Exception as e:
            self._send(500, json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))


def serve(port=8765, open_browser=True):
    srv = ThreadingHTTPServer(("127.0.0.1", port), _Handler)
    url = f"http://127.0.0.1:{port}/"
    print(f"[UI] 设置页: {url}   （Ctrl+C 退出）")
    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n[UI] 已退出")
    finally:
        srv.server_close()
