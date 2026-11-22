"""
========================================================================================
 FUNA QSO One Web <-> Windows D-STAR Bridge (v1.0)
 File: funa_web_dstar_bridge.py

 【概要】
  Chrome上の QSO One Web版 (https://qso1.net/beacon : Japan-X等) と
  Windows版 QSO One (D-STAR等) を、Windowsフォーカスを極力奪わず裏で相互ブリッジする。

 【仕組み】
  - Web版 (Chrome): CDP (127.0.0.1:9222) 経由で DOM 監視 (h-[52px]トーカー枠) &
                    button[data-beacon-tx] への Pointer/Mouse イベント送出
  - Windows版:      UIA ツリー監視 (RX検出文字) & PTT制御 (CLICK / SPACE)
========================================================================================
"""

import sys
sys.coinit_flags = 2  # pywinauto / comtypes 用

import os
import re
import json
import time
import base64
import struct
import socket
import ctypes
import subprocess
import urllib.request
import urllib.parse
from ctypes import wintypes
import threading
import collections
from datetime import datetime
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox

import win32gui
import win32con
import win32process
from pywinauto import Application


# ==============================================================================
#  基本パス・設定定数
# ==============================================================================
APP_TITLE = "FUNA QSO One Web(Beacon) <-> Windows(D-STAR) Bridge v1.0"

def get_base_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))

BASE_DIR = get_base_dir()
CONFIG_FILE = os.path.join(BASE_DIR, "funa_web_dstar_config.json")
CHROME_PROFILE_DIR = os.path.join(BASE_DIR, "chrome_bridge_profile")
DUMP_WIN_FILE = os.path.join(BASE_DIR, "qso1_win_dstar_dump.txt")
DUMP_WEB_FILE = os.path.join(BASE_DIR, "qso1_web_dom_dump.txt")

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
ole32 = ctypes.windll.ole32


# ==============================================================================
#  Win32 キー入力 / フォアグラウンド補助 (ノンデッドロック版)
# ==============================================================================
class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]

class INPUT(ctypes.Structure):
    class _INPUT(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT)]
    _anonymous_ = ("_input",)
    _fields_ = [("type", wintypes.DWORD), ("_input", _INPUT)]


def send_space_key(down: bool):
    flags = 0x0008  # KEYEVENTF_SCANCODE
    if not down:
        flags |= 0x0002
    inp = INPUT()
    inp.type = 1
    inp.ki.wVk = 0x20
    inp.ki.wScan = 0x39
    inp.ki.dwFlags = flags
    user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))


def force_foreground_window(hwnd: int) -> bool:
    if not hwnd or not win32gui.IsWindow(hwnd):
        return False
    try:
        top_hwnd = hwnd
        while True:
            parent = win32gui.GetParent(top_hwnd)
            if not parent:
                break
            top_hwnd = parent

        if win32gui.IsIconic(top_hwnd):
            win32gui.ShowWindow(top_hwnd, win32con.SW_RESTORE)

        if win32gui.GetForegroundWindow() == top_hwnd:
            return True

        fore_hwnd = win32gui.GetForegroundWindow()
        fore_thread, _ = win32process.GetWindowThreadProcessId(fore_hwnd) if fore_hwnd else (0, 0)
        curr_thread = kernel32.GetCurrentThreadId()

        attached = False
        try:
            if fore_thread and fore_thread != curr_thread:
                attached = bool(user32.AttachThreadInput(curr_thread, fore_thread, True))
            win32gui.BringWindowToTop(top_hwnd)
            win32gui.SetForegroundWindow(top_hwnd)
        finally:
            if attached:
                user32.AttachThreadInput(curr_thread, fore_thread, False)

        for _ in range(6):
            if win32gui.GetForegroundWindow() == top_hwnd:
                return True
            time.sleep(0.02)
        return win32gui.GetForegroundWindow() == top_hwnd
    except Exception:
        return False


# ==============================================================================
#  標準ライブラリ製 軽量 CDP WebSocket クライアント (外部pip不要)
# ==============================================================================
class SimpleCdpClient:
    def __init__(self):
        self.sock = None
        self._rx_buf = bytearray()
        self._io_lock = threading.Lock()
        self._msg_id = 0
        self.connected = False

    def connect(self, ws_url: str):
        self.close()
        parsed = urllib.parse.urlparse(ws_url)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or 9222
        path = parsed.path or "/"
        if parsed.query:
            path += "?" + parsed.query

        sock = socket.create_connection((host, port), timeout=2.0)
        sock.settimeout(2.0)

        key = base64.b64encode(os.urandom(16)).decode("ascii")
        req = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host}:{port}\r\n"
            f"Upgrade: websocket\r\n"
            f"Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            f"Sec-WebSocket-Version: 13\r\n\r\n"
        ).encode("ascii")
        sock.sendall(req)

        raw = bytearray()
        while b"\r\n\r\n" not in raw:
            chunk = sock.recv(4096)
            if not chunk:
                sock.close()
                raise ConnectionError("WebSocketハンドシェイク失敗")
            raw.extend(chunk)

        idx = raw.find(b"\r\n\r\n")
        header_txt = raw[:idx].decode("latin-1", errors="ignore")
        if "101" not in header_txt.splitlines()[0]:
            sock.close()
            raise ConnectionError(f"WebSocket接続拒否: {header_txt.splitlines()[0]}")

        self._rx_buf = bytearray(raw[idx + 4:])
        self.sock = sock
        self.connected = True

    def close(self):
        self.connected = False
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
        self.sock = None
        self._rx_buf = bytearray()

    def _read_exact(self, n: int) -> bytes:
        while len(self._rx_buf) < n:
            chunk = self.sock.recv(max(4096, n - len(self._rx_buf)))
            if not chunk:
                raise ConnectionError("CDP WebSocket切断")
            self._rx_buf.extend(chunk)
        out = bytes(self._rx_buf[:n])
        del self._rx_buf[:n]
        return out

    def _send_frame(self, opcode: int, payload: bytes):
        length = len(payload)
        b1 = 0x80 | (opcode & 0x0F)
        if length < 126:
            hdr = struct.pack("!BB", b1, 0x80 | length)
        elif length < 65536:
            hdr = struct.pack("!BBH", b1, 0x80 | 126, length)
        else:
            hdr = struct.pack("!BBQ", b1, 0x80 | 127, length)
        mask = os.urandom(4)
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        self.sock.sendall(hdr + mask + masked)

    def _recv_text(self) -> str:
        msg_buf = bytearray()
        while True:
            b1, b2 = self._read_exact(2)
            fin = bool(b1 & 0x80)
            opcode = b1 & 0x0F
            masked = bool(b2 & 0x80)
            plen = b2 & 0x7F

            if plen == 126:
                plen = struct.unpack("!H", self._read_exact(2))[0]
            elif plen == 127:
                plen = struct.unpack("!Q", self._read_exact(8))[0]

            mask = self._read_exact(4) if masked else b""
            data = self._read_exact(plen)
            if masked:
                data = bytes(b ^ mask[i % 4] for i, b in enumerate(data))

            if opcode == 0x9:  # Ping -> Pong
                self._send_frame(0xA, data)
                continue
            elif opcode == 0xA:  # Pong
                continue
            elif opcode == 0x8:  # Close
                raise ConnectionError("CDP Closed by Chrome")

            msg_buf.extend(data)
            if fin:
                return msg_buf.decode("utf-8", errors="replace")

    def call(self, method: str, params: dict | None = None):
        with self._io_lock:
            if not self.connected or not self.sock:
                raise ConnectionError("CDP未接続")
            self._msg_id += 1
            req_id = self._msg_id
            payload = json.dumps({"id": req_id, "method": method, "params": params or {}}).encode("utf-8")
            try:
                self._send_frame(0x1, payload)
                while True:
                    txt = self._recv_text()
                    obj = json.loads(txt)
                    if obj.get("id") == req_id:
                        if "error" in obj:
                            raise RuntimeError(str(obj["error"]))
                        return obj.get("result", {})
            except Exception:
                self.close()
                raise

    def evaluate(self, expression: str):
        res = self.call("Runtime.evaluate", {
            "expression": expression,
            "returnByValue": True,
        })
        return res.get("result", {}).get("value")


# ==============================================================================
#  Chrome QSO One Web (Beacon) コントローラ
# ==============================================================================
JS_POLL_WEB = r"""
(() => {
  const btn = document.querySelector('button[data-beacon-tx]');
  const btnText = btn ? btn.innerText.replace(/\s+/g, ' ').trim() : '';
  const btnDisabled = btn ? !!btn.disabled : true;
  const ariaPressed = btn ? (btn.getAttribute('aria-pressed') === 'true') : false;
  const rect = btn ? btn.getBoundingClientRect() : null;

  const cards = [...document.querySelectorAll('div')].filter(d => {
    const cls = typeof d.className === 'string' ? d.className : '';
    return cls.includes('h-[52px]') && cls.includes('rounded-2xl') && cls.includes('px-3.5');
  });
  const talkerText = cards.length > 0 ? cards[0].innerText.replace(/\s+/g, ' ').trim() : '';

  return {
    title: document.title || '',
    url: location.href || '',
    hasBtn: !!btn,
    btnDisabled,
    ariaPressed,
    btnText,
    talkerText,
    cx: rect ? (rect.left + rect.width / 2) : 0,
    cy: rect ? (rect.top + rect.height / 2) : 0
  };
})()
"""

JS_PTT_DOWN = r"""
(() => {
  const btn = document.querySelector('button[data-beacon-tx]');
  if (!btn || btn.disabled) return { ok: false, reason: btn ? 'disabled' : 'not_found' };
  const r = btn.getBoundingClientRect();
  const opts = {
    bubbles: true, cancelable: true, view: window,
    clientX: r.left + r.width / 2, clientY: r.top + r.height / 2,
    button: 0, buttons: 1
  };
  btn.dispatchEvent(new PointerEvent('pointerdown', { ...opts, pointerId: 1, isPrimary: true }));
  btn.dispatchEvent(new MouseEvent('mousedown', opts));
  return { ok: true };
})()
"""

JS_PTT_UP = r"""
(() => {
  const btn = document.querySelector('button[data-beacon-tx]');
  if (!btn) return { ok: false };
  const r = btn.getBoundingClientRect();
  const opts = {
    bubbles: true, cancelable: true, view: window,
    clientX: r.left + r.width / 2, clientY: r.top + r.height / 2,
    button: 0, buttons: 0
  };
  btn.dispatchEvent(new PointerEvent('pointerup', { ...opts, pointerId: 1, isPrimary: true }));
  btn.dispatchEvent(new MouseEvent('mouseup', opts));
  return { ok: true };
})()
"""

JS_DUMP_DOM = r"""
(() => {
  const out = [];
  for (const el of document.querySelectorAll('button, div, span, p')) {
    const t = (el.innerText || '').replace(/\s+/g, ' ').trim();
    if (t && t.length <= 160 && el.children.length <= 3) {
      out.push(`[${el.tagName}] (${(el.className || '').toString().slice(0, 60)}) => ${t}`);
    }
  }
  return out.slice(0, 120);
})()
"""


class WebBeaconController:
    def __init__(self, log_cb=None):
        self.cdp = SimpleCdpClient()
        self.cdp_port = 9222
        self.log_cb = log_cb
        self.status_lock = threading.Lock()
        self.ptt_lock = threading.Lock()

        self.ptt_method = "JS_EVENT"  # "JS_EVENT" or "CDP_MOUSE"
        self.own_callsign = ""
        self.ignore_own_call = True
        self.is_tx = False
        self._last_coords = (0, 0)
        self._last_talker_logged = None
        self.dump_requested = False

        self.status = {
            "cdp_connected": False,
            "page_title": "---",
            "room_ready": False,
            "btn_text": "---",
            "talker_text": "---",
            "is_receiving": False,
            "rx_callsign": "Standby",
            "self_tx_active": False,
        }

    def _log(self, msg: str):
        if self.log_cb:
            self.log_cb(msg)

    def get_status_copy(self) -> dict:
        with self.status_lock:
            return dict(self.status)

    def connect(self, cdp_port: int = 9222) -> bool:
        self.cdp_port = cdp_port
        try:
            url = f"http://127.0.0.1:{cdp_port}/json"
            with urllib.request.urlopen(url, timeout=1.5) as resp:
                pages = json.loads(resp.read().decode("utf-8"))

            target = None
            for p in pages:
                if p.get("type") == "page" and "qso1.net" in p.get("url", ""):
                    target = p
                    break
            if not target:
                self._log(f"[WEB ERR] ポート {cdp_port} の Chrome に qso1.net のタブが見つかりません。")
                return False

            ws_url = target.get("webSocketDebuggerUrl")
            if not ws_url:
                self._log("[WEB ERR] webSocketDebuggerUrl が取得できませんでした。")
                return False

            self.cdp.connect(ws_url)
            with self.status_lock:
                self.status["cdp_connected"] = True
            self._log(f"[WEB] Chrome CDP 接続完了: {target.get('url')}")
            return True
        except Exception as e:
            self.disconnect()
            self._log(f"[WEB ERR] CDP接続失敗 (Chromeが --remote-debugging-port={cdp_port} で起動しているか確認): {e}")
            return False

    def disconnect(self):
        self.cdp.close()
        self.is_tx = False
        with self.status_lock:
            self.status["cdp_connected"] = False
            self.status["room_ready"] = False
            self.status["is_receiving"] = False
            self.status["rx_callsign"] = "Standby"

    def poll_once(self):
        if not self.cdp.connected:
            return
        try:
            if self.dump_requested:
                self.dump_requested = False
                lines = self.cdp.evaluate(JS_DUMP_DOM) or []
                with open(DUMP_WEB_FILE, "w", encoding="utf-8") as df:
                    df.write(f"=== QSO One Web DOM Dump ({datetime.now()}) ===\n")
                    for ln in lines:
                        df.write(ln + "\n")
                self._log(f"[WEB DUMP] {len(lines)}件を保存しました: {DUMP_WEB_FILE}")

            data = self.cdp.evaluate(JS_POLL_WEB)
            if not isinstance(data, dict):
                return

            talker = (data.get("talkerText") or "").strip()
            btn_text = (data.get("btnText") or "").strip()
            btn_disabled = bool(data.get("btnDisabled", True))
            aria_pressed = bool(data.get("ariaPressed", False))
            has_btn = bool(data.get("hasBtn", False))
            self._last_coords = (data.get("cx", 0), data.get("cy", 0))

            if talker and talker != self._last_talker_logged:
                self._last_talker_logged = talker
                self._log(f"[WEB TALKER] {talker}")

            room_ready = has_btn and (not btn_disabled)
            self_tx = aria_pressed or ("ON AIR" in btn_text) or ("MIC..." in btn_text) or ("you are on the air" in talker.lower())

            # トーカー枠による RX 判定
            is_rx = False
            rx_call = "Standby"
            if talker:
                low = talker.lower()
                is_idle_msg = (
                    "nobody is talking" in low
                    or "not in the room yet" in low
                    or "you are on the air" in low
                )
                if not is_idle_msg:
                    own_u = self.own_callsign.strip().upper()
                    # 先頭のアバター2文字 ("JL JL1LBI ...") を避けてコールサイン抽出を試みる
                    tokens = re.findall(r"[A-Z0-9]{1,3}\d[A-Z]{1,4}(?:-[A-Z0-9]+)?", talker.upper())
                    cand = tokens[0] if tokens else talker[:14]
                    is_self = self.ignore_own_call and own_u and (own_u in cand or cand in own_u)
                    if not is_self:
                        is_rx = True
                        rx_call = cand

            with self.status_lock:
                self.status["cdp_connected"] = True
                self.status["page_title"] = data.get("title", "---")
                self.status["room_ready"] = room_ready
                self.status["btn_text"] = btn_text or "---"
                self.status["talker_text"] = talker or "---"
                self.status["self_tx_active"] = self_tx
                self.status["is_receiving"] = is_rx
                self.status["rx_callsign"] = rx_call

        except Exception as e:
            self._log(f"[WEB ERR] CDP通信切断: {e}")
            self.disconnect()

    def ptt_on(self):
        with self.ptt_lock:
            if self.is_tx or not self.cdp.connected:
                return
            try:
                if self.ptt_method == "CDP_MOUSE" and self._last_coords[0] > 0:
                    cx, cy = self._last_coords
                    self.cdp.call("Input.dispatchMouseEvent", {
                        "type": "mousePressed", "x": cx, "y": cy,
                        "button": "left", "clickCount": 1
                    })
                    self.is_tx = True
                    self._log(f"[WEB] PTT -> TX ON (CDP Mouse @ {int(cx)},{int(cy)})")
                else:
                    res = self.cdp.evaluate(JS_PTT_DOWN) or {}
                    if res.get("ok"):
                        self.is_tx = True
                        self._log("[WEB] PTT -> TX ON (JS PointerEvent)")
                    else:
                        self._log(f"[WEB WARN] PTT押下不可 ({res.get('reason')})")
            except Exception as e:
                self._log(f"[WEB ERR] PTT ON 失敗: {e}")

    def ptt_off(self):
        with self.ptt_lock:
            if not self.is_tx or not self.cdp.connected:
                self.is_tx = False
                return
            try:
                if self.ptt_method == "CDP_MOUSE" and self._last_coords[0] > 0:
                    cx, cy = self._last_coords
                    self.cdp.call("Input.dispatchMouseEvent", {
                        "type": "mouseReleased", "x": cx, "y": cy,
                        "button": "left", "clickCount": 1
                    })
                else:
                    self.cdp.evaluate(JS_PTT_UP)
                self._log("[WEB] PTT -> RX OFF")
            except Exception as e:
                self._log(f"[WEB ERR] PTT OFF 失敗: {e}")
            finally:
                self.is_tx = False


# ==============================================================================
#  Windows版 QSO One (D-STAR) UIA コントローラ
# ==============================================================================
class QsoOneWinController:
    def __init__(self, log_cb=None):
        self.main_hwnd = None
        self.flutter_hwnd = None
        self._uia_app = None
        self._uia_win = None
        self.is_tx = False

        self.status_lock = threading.Lock()
        self.ptt_lock = threading.Lock()
        self.log_cb = log_cb

        self.status = {
            "attached": False,
            "room": "---",
            "own_call": "",
            "rx_callsign": "Standby",
            "is_receiving": False,
            "raw_rx_text": "",
            "ptt_btn_screen_rect": None,
            "main_hwnd": None,
            "flutter_hwnd": None,
        }

        self.rx_keyword = "送信中"
        self.own_callsign_override = ""
        self.ignore_own_callsign = True
        self.ptt_method = "CLICK"  # Web版と共存時はCLICK推奨 (SPACEも選択可)
        self.debug_uia = False
        self.dump_requested = False
        self._last_debug_snapshot = ""

    def _log(self, msg: str):
        if self.log_cb:
            self.log_cb(msg)

    def get_status_copy(self) -> dict:
        with self.status_lock:
            return dict(self.status)

    def find_hwnds(self) -> bool:
        found = []

        def enum_cb(hwnd, _):
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd)
                cls = win32gui.GetClassName(hwnd)
                if "FLUTTER_RUNNER_WIN32_WINDOW" in cls or title.strip().lower() == "qso one":
                    found.append(hwnd)
            return True

        win32gui.EnumWindows(enum_cb, None)
        if not found:
            self.main_hwnd = None
            self.flutter_hwnd = None
            self._uia_app = None
            self._uia_win = None
            with self.status_lock:
                self.status["attached"] = False
                self.status["main_hwnd"] = None
                self.status["flutter_hwnd"] = None
            return False

        new_main = found[0]
        new_flutter = None

        def enum_child(hwnd, _):
            nonlocal new_flutter
            if win32gui.GetClassName(hwnd) == "FLUTTERVIEW":
                new_flutter = hwnd
            return True

        win32gui.EnumChildWindows(new_main, enum_child, None)
        if not new_flutter:
            new_flutter = new_main

        if new_main != self.main_hwnd:
            self.main_hwnd = new_main
            self.flutter_hwnd = new_flutter
            self._uia_app = None
            self._uia_win = None

        with self.status_lock:
            self.status["attached"] = True
            self.status["main_hwnd"] = self.main_hwnd
            self.status["flutter_hwnd"] = self.flutter_hwnd
        return True

    def scan_once(self):
        if not self.main_hwnd or not win32gui.IsWindow(self.main_hwnd):
            if not self.find_hwnds():
                return

        if self.flutter_hwnd and win32gui.IsWindow(self.flutter_hwnd):
            user32.PostMessageW(self.flutter_hwnd, win32con.WM_NULL, 0, 0)

        try:
            if self._uia_win is None:
                self._uia_app = Application(backend="uia").connect(handle=self.main_hwnd)
                self._uia_win = self._uia_app.window(handle=self.main_hwnd)

            descendants = self._uia_win.descendants()

            room_val = None
            rx_call = None
            raw_rx = ""
            receiving = False
            detected_own_call = ""
            ptt_rect = None
            debug_items = []
            full_dump_lines = []

            rx_kw = self.rx_keyword.strip() or "送信中"
            own_call_cfg = self.own_callsign_override.strip().upper()
            do_dump = self.dump_requested
            if do_dump:
                self.dump_requested = False

            for elem in descendants:
                try:
                    info = elem.element_info
                    name = info.name
                    ctype = info.control_type
                    if do_dump and name:
                        full_dump_lines.append(f"[{ctype}] {repr(name)} rect={info.rectangle}")

                    if not name:
                        continue

                    if self.debug_uia and ctype in ("Button", "Text", "Group"):
                        compact = name.replace("\n", " / ")
                        if any(k in compact for k in (rx_kw, "D-STAR", "REF", "XRF", "DCS", "TG", "通信", "送信", "TX", "RX", "たった今")):
                            debug_items.append(f"[{ctype}] {compact[:75]}")

                    if ctype == "Text" and not detected_own_call:
                        txt_u = name.strip().upper()
                        if re.fullmatch(r"[A-Z0-9]{1,3}\d[A-Z]{1,4}", txt_u):
                            detected_own_call = txt_u
                        elif "(あなた)" in name:
                            m_own = re.match(r"^\s*([A-Z0-9]{1,3}\d[A-Z]{1,4})\b", txt_u)
                            if m_own:
                                detected_own_call = m_own.group(1)

                    if "通信あり" in name or "D-STAR" in name or "REF" in name or "XRF" in name or "DCS" in name:
                        lines = [ln.strip() for ln in name.splitlines() if ln.strip()]
                        if len(lines) >= 2 and ("D-STAR" in name or "通信あり" in name):
                            room_val = " / ".join(lines[:4])

                    if rx_kw in name:
                        raw_rx = name.replace("\n", " ").strip()
                        idx = name.find(rx_kw)
                        before = name[:idx].strip()
                        after = name[idx + len(rx_kw):].lstrip(":： \t").strip()

                        if before:
                            parts = re.split(r"[,、\s·・]+", before)
                            cand_call = parts[-1].upper() if (parts and parts[-1]) else "RX_ACTIVE"
                        elif after:
                            parts = re.split(r"[,、\s·・]+", after)
                            cand_call = parts[0].upper() if (parts and parts[0]) else "RX_ACTIVE"
                        else:
                            cand_call = "RX_ACTIVE"

                        effective_own = own_call_cfg or detected_own_call
                        is_self = (
                            self.ignore_own_callsign
                            and effective_own
                            and (effective_own in cand_call or cand_call in effective_own)
                        )
                        if not is_self:
                            rx_call = cand_call
                            receiving = True

                    if ctype == "Button" and name in ("押して送信", "PTT", "離して停止", "送信中", "送信停止"):
                        r = info.rectangle
                        ptt_rect = (r.left, r.top, r.right, r.bottom)

                except Exception:
                    continue

            if do_dump:
                try:
                    with open(DUMP_WIN_FILE, "w", encoding="utf-8") as df:
                        df.write(f"=== QSO One Windows UIA Dump ({datetime.now()}) ===\n")
                        for ln in full_dump_lines:
                            df.write(ln + "\n")
                    self._log(f"[WIN DUMP] {len(full_dump_lines)}件を保存しました: {DUMP_WIN_FILE}")
                except Exception as e:
                    self._log(f"[WIN DUMP ERR] {e}")

            if self.debug_uia and debug_items:
                snap = " | ".join(debug_items[:12])
                if snap != self._last_debug_snapshot:
                    self._last_debug_snapshot = snap
                    self._log(f"[WIN UIA] {snap}")

            with self.status_lock:
                self.status["attached"] = True
                if room_val:
                    self.status["room"] = room_val
                if detected_own_call:
                    self.status["own_call"] = detected_own_call
                if ptt_rect:
                    self.status["ptt_btn_screen_rect"] = ptt_rect

                if receiving:
                    self.status["is_receiving"] = True
                    self.status["rx_callsign"] = rx_call or "ACTIVE"
                    self.status["raw_rx_text"] = raw_rx
                else:
                    self.status["is_receiving"] = False
                    self.status["rx_callsign"] = "Standby"
                    self.status["raw_rx_text"] = ""

        except Exception:
            self._uia_win = None

    def ptt_on(self):
        with self.ptt_lock:
            if self.is_tx:
                return
            snap = self.get_status_copy()
            m_hwnd = snap["main_hwnd"]
            f_hwnd = snap["flutter_hwnd"]
            ptt_rect = snap["ptt_btn_screen_rect"]

            if not m_hwnd or not win32gui.IsWindow(m_hwnd):
                self._log("[WIN ERR] Windows版 QSO One 未検出")
                return

            if self.ptt_method == "CLICK" and ptt_rect and f_hwnd:
                l, t, r, b = ptt_rect
                cx, cy = (l + r) // 2, (t + b) // 2
                try:
                    pt_x, pt_y = win32gui.ScreenToClient(f_hwnd, (cx, cy))
                except Exception:
                    w_rect = win32gui.GetWindowRect(f_hwnd)
                    pt_x, pt_y = cx - w_rect[0], cy - w_rect[1]
                lparam = ((pt_y & 0xFFFF) << 16) | (pt_x & 0xFFFF)
                user32.PostMessageW(f_hwnd, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, lparam)
                self.is_tx = True
                self._log(f"[WIN] PTT -> TX ON (Click @ {pt_x},{pt_y})")
            else:
                if force_foreground_window(m_hwnd):
                    send_space_key(True)
                    if f_hwnd and win32gui.IsWindow(f_hwnd):
                        user32.PostMessageW(f_hwnd, win32con.WM_KEYDOWN, win32con.VK_SPACE, (0x39 << 16) | 1)
                    self.is_tx = True
                    self._log("[WIN] PTT -> TX ON (Spacebar)")
                else:
                    if f_hwnd and win32gui.IsWindow(f_hwnd):
                        user32.PostMessageW(f_hwnd, win32con.WM_KEYDOWN, win32con.VK_SPACE, (0x39 << 16) | 1)
                    self.is_tx = True
                    self._log("[WIN WARN] フォアグラウンド切替未確認 (PostMessageのみ)")

    def ptt_off(self):
        with self.ptt_lock:
            if not self.is_tx:
                return
            snap = self.get_status_copy()
            m_hwnd = snap["main_hwnd"]
            f_hwnd = snap["flutter_hwnd"]
            ptt_rect = snap["ptt_btn_screen_rect"]

            if self.ptt_method == "CLICK" and ptt_rect and f_hwnd:
                l, t, r, b = ptt_rect
                cx, cy = (l + r) // 2, (t + b) // 2
                try:
                    pt_x, pt_y = win32gui.ScreenToClient(f_hwnd, (cx, cy))
                except Exception:
                    w_rect = win32gui.GetWindowRect(f_hwnd)
                    pt_x, pt_y = cx - w_rect[0], cy - w_rect[1]
                lparam = ((pt_y & 0xFFFF) << 16) | (pt_x & 0xFFFF)
                user32.PostMessageW(f_hwnd, win32con.WM_LBUTTONUP, 0, lparam)
                self._log("[WIN] PTT -> RX OFF (Click Release)")
            else:
                if m_hwnd and win32gui.GetForegroundWindow() == m_hwnd:
                    send_space_key(False)
                elif m_hwnd and force_foreground_window(m_hwnd):
                    send_space_key(False)
                if f_hwnd and win32gui.IsWindow(f_hwnd):
                    user32.PostMessageW(f_hwnd, win32con.WM_KEYUP, win32con.VK_SPACE, (0x39 << 16) | 0xC0000001)
                self._log("[WIN] PTT -> RX OFF (Spacebar Release)")
            self.is_tx = False


# ==============================================================================
#  双方向ブリッジ・ステートマシン (Web Beacon <-> Windows D-STAR)
# ==============================================================================
class WebDstarBridgeEngine:
    STATE_DISABLED   = "DISABLED"
    STATE_IDLE       = "IDLE"
    STATE_WEB_TO_WIN = "Web(Beacon) -> Win(D-STAR TX)"
    STATE_WIN_TO_WEB = "Win(D-STAR) -> Web(Beacon TX)"
    STATE_GUARD_WAIT = "GUARD WAIT"

    def __init__(self, web: WebBeaconController, win_app: QsoOneWinController, log_cb=None):
        self.web = web
        self.win_app = win_app
        self.log_cb = log_cb

        self.armed = False
        self.state = self.STATE_DISABLED
        self.tx_start_time = 0.0
        self.last_rx_seen = 0.0
        self.guard_until = 0.0

        self.web_hang_ms = 350
        self.win_hang_ms = 350
        self.guard_ms = 700
        self.tot_sec = 55  # Web側1分制限に合わせてデフォルト55秒

        self.manual_web_tx = False
        self.manual_win_tx = False

    def _log(self, msg: str):
        if self.log_cb:
            self.log_cb(msg)

    def set_armed(self, armed: bool):
        self.armed = armed
        if armed:
            self.state = self.STATE_IDLE
            self._log("[BRIDGE] ★ ブリッジ有効化 (ARMED - 双方向監視中)")
        else:
            self.state = self.STATE_DISABLED
            self._log("[BRIDGE] ■ ブリッジ停止 (STANDBY)")

    def step(self):
        now = time.monotonic()

        if self.manual_web_tx or self.manual_win_tx:
            return

        if not self.armed:
            if self.web.is_tx:
                self.web.ptt_off()
            if self.win_app.is_tx:
                self.win_app.ptt_off()
            self.state = self.STATE_DISABLED
            return

        w_snap = self.web.get_status_copy()
        d_snap = self.win_app.get_status_copy()

        if not w_snap["cdp_connected"] or not w_snap["room_ready"] or not d_snap["attached"]:
            return

        web_rx = bool(w_snap["is_receiving"])
        web_call = w_snap["rx_callsign"]
        win_rx = bool(d_snap["is_receiving"])
        win_call = d_snap["rx_callsign"]

        if self.state == self.STATE_IDLE:
            if web_rx:
                self.state = self.STATE_WEB_TO_WIN
                self.tx_start_time = now
                self.last_rx_seen = now
                self._log(f"[ROUTE] Web(Beacon)受信 ({web_call}) -> Win(D-STAR) PTT ON")
                self.win_app.ptt_on()
            elif win_rx:
                self.state = self.STATE_WIN_TO_WEB
                self.tx_start_time = now
                self.last_rx_seen = now
                self._log(f"[ROUTE] Win(D-STAR)受信 ({win_call}) -> Web(Beacon) PTT ON")
                self.web.ptt_on()

        elif self.state == self.STATE_WEB_TO_WIN:
            if now - self.tx_start_time >= self.tot_sec:
                self._log(f"[TOT!] Web->Win 送信時間超過 ({self.tot_sec}s) 強制終了")
                self.win_app.ptt_off()
                self.state = self.STATE_GUARD_WAIT
                self.guard_until = now + (self.guard_ms / 1000.0)
                return
            if web_rx:
                self.last_rx_seen = now
            elif now - self.last_rx_seen >= (self.web_hang_ms / 1000.0):
                self.win_app.ptt_off()
                self._log("[ROUTE] Web受信終了 -> Win(D-STAR) RX復帰 (Guard Wait)")
                self.state = self.STATE_GUARD_WAIT
                self.guard_until = now + (self.guard_ms / 1000.0)

        elif self.state == self.STATE_WIN_TO_WEB:
            if now - self.tx_start_time >= self.tot_sec:
                self._log(f"[TOT!] Win->Web 送信時間超過 ({self.tot_sec}s) 強制終了")
                self.web.ptt_off()
                self.state = self.STATE_GUARD_WAIT
                self.guard_until = now + (self.guard_ms / 1000.0)
                return
            if win_rx:
                self.last_rx_seen = now
            elif now - self.last_rx_seen >= (self.win_hang_ms / 1000.0):
                self.web.ptt_off()
                self._log("[ROUTE] Win受信終了 -> Web(Beacon) RX復帰 (Guard Wait)")
                self.state = self.STATE_GUARD_WAIT
                self.guard_until = now + (self.guard_ms / 1000.0)

        elif self.state == self.STATE_GUARD_WAIT:
            if self.web.is_tx:
                self.web.ptt_off()
            if self.win_app.is_tx:
                self.win_app.ptt_off()
            if now >= self.guard_until:
                self.state = self.STATE_IDLE


# ==============================================================================
#  メイン GUI
# ==============================================================================
class WebDstarBridgeGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("980x760")
        self.root.minsize(900, 680)

        self.log_queue = collections.deque(maxlen=500)
        self.log_lock = threading.Lock()
        self.running = True

        self.web = WebBeaconController(log_cb=self.enqueue_log)
        self.win_app = QsoOneWinController(log_cb=self.enqueue_log)
        self.bridge = WebDstarBridgeEngine(self.web, self.win_app, log_cb=self.enqueue_log)

        self.config = self._load_config()
        self._install_spacebar_immunity()
        self._build_ui()
        self._apply_config_to_ui()

        threading.Thread(target=self._web_poll_worker, daemon=True).start()
        threading.Thread(target=self._win_uia_worker, daemon=True).start()
        threading.Thread(target=self._bridge_worker, daemon=True).start()

        self.root.after(100, self._ui_tick)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.enqueue_log("[SYSTEM] FUNA Web(Beacon) <-> Windows(D-STAR) Bridge を起動しました。")
        self.enqueue_log("[HINT] 1)「Chrome(Bridge用)起動」→ ルームへJoin →「CDP接続」")
        self.enqueue_log("[HINT] 2) 仮想オーディオケーブル(VB-Cable等)でChromeとWindows版QSO Oneの入出力をクロス配線してください。")

    def _install_spacebar_immunity(self):
        for cls in ("Button", "TButton", "Checkbutton", "TCheckbutton", "Combobox", "TCombobox"):
            self.root.unbind_class(cls, "<Key-space>")
            self.root.unbind_class(cls, "<KeyRelease-space>")
            self.root.unbind_class(cls, "<space>")

        def _block_space(event):
            if not isinstance(event.widget, (tk.Entry, ttk.Entry)):
                return "break"
            return None

        self.root.bind_all("<KeyPress-space>", _block_space)
        self.root.bind_all("<KeyRelease-space>", _block_space)

    def enqueue_log(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S.%f")[:12]
        with self.log_lock:
            self.log_queue.append(f"[{ts}] {msg}")

    def _load_config(self) -> dict:
        default_cfg = {
            "cdp_port": "9222",
            "web_url": "https://qso1.net/beacon",
            "web_ptt_method": "JS_EVENT",
            "win_ptt_method": "CLICK",
            "win_rx_keyword": "送信中",
            "own_callsign": "",
            "ignore_own_call": True,
            "web_hang_ms": 350,
            "win_hang_ms": 350,
            "guard_ms": 700,
            "tot_sec": 55,
            "debug_uia": False,
        }
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    default_cfg.update(json.load(f))
            except Exception:
                pass
        return default_cfg

    def _save_config(self):
        self._sync_ui_to_engine()
        cfg = {
            "cdp_port": self.var_cdp_port.get(),
            "web_url": self.var_web_url.get(),
            "web_ptt_method": self.var_web_ptt.get(),
            "win_ptt_method": self.var_win_ptt.get(),
            "win_rx_keyword": self.var_win_rx_kw.get(),
            "own_callsign": self.var_own_call.get(),
            "ignore_own_call": bool(self.var_ignore_own.get()),
            "web_hang_ms": int(self.var_web_hang.get()),
            "win_hang_ms": int(self.var_win_hang.get()),
            "guard_ms": int(self.var_guard_ms.get()),
            "tot_sec": int(self.var_tot_sec.get()),
            "debug_uia": bool(self.var_debug_uia.get()),
        }
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2, ensure_ascii=False)
            self.enqueue_log("[CONFIG] 設定を保存しました。")
        except Exception as e:
            self.enqueue_log(f"[CONFIG ERR] {e}")

    def _build_ui(self):
        top_frame = tk.Frame(self.root, bg="#18202c", pady=8, padx=12)
        top_frame.pack(fill="x")

        self.lbl_state_banner = tk.Label(
            top_frame,
            text="STATE: DISABLED (STANDBY)",
            font=("Consolas", 14, "bold"),
            fg="#ffd166",
            bg="#18202c",
        )
        self.lbl_state_banner.pack(side="left")

        btn_box = tk.Frame(top_frame, bg="#18202c")
        btn_box.pack(side="right")

        self.btn_arm = tk.Button(
            btn_box,
            text="BRIDGE START (ARM)",
            font=("Segoe UI", 10, "bold"),
            bg="#06d6a0",
            fg="#000000",
            width=20,
            takefocus=0,
            command=self._toggle_arm,
        )
        self.btn_arm.pack(side="left", padx=5)

        tk.Button(
            btn_box,
            text="EMERGENCY ALL RX",
            font=("Segoe UI", 10, "bold"),
            bg="#ef476f",
            fg="#ffffff",
            takefocus=0,
            command=self._on_emergency_rx,
        ).pack(side="left", padx=5)

        main_pane = ttk.Frame(self.root, padding=10)
        main_pane.pack(fill="x")

        # 左カラム: QSO One Web (Chrome CDP)
        left_frame = ttk.LabelFrame(main_pane, text=" QSO One Web版 (Chrome CDP: Beacon Japan-X) ", padding=10)
        left_frame.pack(side="left", fill="both", expand=True, padx=(0, 6))

        row_cdp = ttk.Frame(left_frame)
        row_cdp.pack(fill="x", pady=3)
        ttk.Label(row_cdp, text="CDP Port:", width=10).pack(side="left")
        self.var_cdp_port = tk.StringVar()
        ttk.Entry(row_cdp, textvariable=self.var_cdp_port, width=7).pack(side="left", padx=2)
        ttk.Button(row_cdp, text="Chrome(Bridge用)起動", takefocus=False, command=self._launch_chrome_cdp).pack(side="left", padx=4)
        self.btn_cdp_conn = ttk.Button(row_cdp, text="CDP接続", takefocus=False, command=self._toggle_cdp)
        self.btn_cdp_conn.pack(side="right")

        row_url = ttk.Frame(left_frame)
        row_url.pack(fill="x", pady=3)
        ttk.Label(row_url, text="開始URL:", width=10).pack(side="left")
        self.var_web_url = tk.StringVar()
        ttk.Entry(row_url, textvariable=self.var_web_url, width=36).pack(side="left", fill="x", expand=True)

        ttk.Separator(left_frame, orient="horizontal").pack(fill="x", pady=6)

        row_wstat = ttk.Frame(left_frame)
        row_wstat.pack(fill="x", pady=2)
        self.lbl_web_conn = ttk.Label(row_wstat, text="CDP: 未接続", font=("Consolas", 10, "bold"), foreground="#cc3333")
        self.lbl_web_conn.pack(side="left")
        self.lbl_web_ptt = ttk.Label(row_wstat, text="PTT: RX", font=("Consolas", 10, "bold"), foreground="#008800")
        self.lbl_web_ptt.pack(side="right")

        row_wbtn = ttk.Frame(left_frame)
        row_wbtn.pack(fill="x", pady=2)
        self.lbl_web_btn_state = ttk.Label(row_wbtn, text="Button: ---", width=26)
        self.lbl_web_btn_state.pack(side="left")
        self.lbl_web_rx = ttk.Label(row_wbtn, text="RX: Standby", font=("Consolas", 10, "bold"))
        self.lbl_web_rx.pack(side="right")

        row_wtalk = ttk.Frame(left_frame)
        row_wtalk.pack(fill="x", pady=2)
        self.lbl_web_talker = ttk.Label(row_wtalk, text="Talker: ---", foreground="#444444")
        self.lbl_web_talker.pack(side="left")

        row_wcfg = ttk.Frame(left_frame)
        row_wcfg.pack(fill="x", pady=3)
        ttk.Label(row_wcfg, text="Web PTT方式:", width=12).pack(side="left")
        self.var_web_ptt = tk.StringVar()
        ttk.Combobox(
            row_wcfg, textvariable=self.var_web_ptt,
            values=["JS_EVENT", "CDP_MOUSE"], state="readonly", width=13, takefocus=False
        ).pack(side="left", padx=2)

        row_wtest = ttk.Frame(left_frame)
        row_wtest.pack(fill="x", pady=(8, 0))
        self.btn_test_web_ptt = ttk.Button(row_wtest, text="手動テスト: Web版 PTT (押下式)", takefocus=False)
        self.btn_test_web_ptt.pack(fill="x")
        self.btn_test_web_ptt.bind("<ButtonPress-1>", lambda e: self._manual_web_ptt(True))
        self.btn_test_web_ptt.bind("<ButtonRelease-1>", lambda e: self._manual_web_ptt(False))

        # 右カラム: QSO One Windows版 (D-STAR)
        right_frame = ttk.LabelFrame(main_pane, text=" QSO One Windows版 (UIA: D-STAR等) ", padding=10)
        right_frame.pack(side="left", fill="both", expand=True, padx=(6, 0))

        row_dstat = ttk.Frame(right_frame)
        row_dstat.pack(fill="x", pady=2)
        self.lbl_win_conn = ttk.Label(row_dstat, text="Win版: 未検出", font=("Consolas", 10, "bold"), foreground="#cc3333")
        self.lbl_win_conn.pack(side="left")
        self.lbl_win_ptt = ttk.Label(row_dstat, text="PTT: RX", font=("Consolas", 10, "bold"), foreground="#008800")
        self.lbl_win_ptt.pack(side="right")

        row_dinfo = ttk.Frame(right_frame)
        row_dinfo.pack(fill="x", pady=2)
        self.lbl_win_room = ttk.Label(row_dinfo, text="Room: ---", width=26)
        self.lbl_win_room.pack(side="left")
        self.lbl_win_rx = ttk.Label(row_dinfo, text="RX: Standby", font=("Consolas", 10, "bold"))
        self.lbl_win_rx.pack(side="right")

        ttk.Separator(right_frame, orient="horizontal").pack(fill="x", pady=6)

        row_dcfg1 = ttk.Frame(right_frame)
        row_dcfg1.pack(fill="x", pady=3)
        ttk.Label(row_dcfg1, text="Win PTT方式:", width=12).pack(side="left")
        self.var_win_ptt = tk.StringVar()
        ttk.Combobox(
            row_dcfg1, textvariable=self.var_win_ptt,
            values=["CLICK", "SPACE"], state="readonly", width=10, takefocus=False
        ).pack(side="left", padx=2)
        ttk.Label(row_dcfg1, text="RX文字:").pack(side="left", padx=(6, 2))
        self.var_win_rx_kw = tk.StringVar()
        ttk.Entry(row_dcfg1, textvariable=self.var_win_rx_kw, width=10).pack(side="left")

        row_dcfg2 = ttk.Frame(right_frame)
        row_dcfg2.pack(fill="x", pady=3)
        ttk.Label(row_dcfg2, text="自局Call:", width=12).pack(side="left")
        self.var_own_call = tk.StringVar()
        ttk.Entry(row_dcfg2, textvariable=self.var_own_call, width=11).pack(side="left", padx=2)
        self.var_ignore_own = tk.BooleanVar()
        ttk.Checkbutton(row_dcfg2, text="自局除外 (Web/Win共通)", variable=self.var_ignore_own, takefocus=False).pack(side="left", padx=4)

        row_tmr = ttk.Frame(right_frame)
        row_tmr.pack(fill="x", pady=3)
        ttk.Label(row_tmr, text="Hang(Web/Win ms):", width=16).pack(side="left")
        self.var_web_hang = tk.StringVar()
        self.var_win_hang = tk.StringVar()
        ttk.Entry(row_tmr, textvariable=self.var_web_hang, width=5).pack(side="left", padx=1)
        ttk.Entry(row_tmr, textvariable=self.var_win_hang, width=5).pack(side="left", padx=1)
        ttk.Label(row_tmr, text="Guard(ms):").pack(side="left", padx=(4, 1))
        self.var_guard_ms = tk.StringVar()
        ttk.Entry(row_tmr, textvariable=self.var_guard_ms, width=5).pack(side="left", padx=1)
        ttk.Label(row_tmr, text="TOT(s):").pack(side="left", padx=(4, 1))
        self.var_tot_sec = tk.StringVar()
        ttk.Entry(row_tmr, textvariable=self.var_tot_sec, width=4).pack(side="left", padx=1)

        row_dtest = ttk.Frame(right_frame)
        row_dtest.pack(fill="x", pady=(8, 0))
        self.btn_test_win_ptt = ttk.Button(row_dtest, text="手動テスト: Win版 PTT (押下式)", takefocus=False)
        self.btn_test_win_ptt.pack(side="left", fill="x", expand=True, padx=(0, 4))
        self.btn_test_win_ptt.bind("<ButtonPress-1>", lambda e: self._manual_win_ptt(True))
        self.btn_test_win_ptt.bind("<ButtonRelease-1>", lambda e: self._manual_win_ptt(False))
        ttk.Button(row_dtest, text="設定保存", takefocus=False, command=self._save_config).pack(side="right")

        # --- 下部: ログ & 調査 ---
        log_frame = ttk.LabelFrame(self.root, text=" Bridge Event & Monitor Log ", padding=8)
        log_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        log_ctrl = ttk.Frame(log_frame)
        log_ctrl.pack(fill="x", pady=(0, 4))
        self.var_debug_uia = tk.BooleanVar()
        ttk.Checkbutton(
            log_ctrl,
            text="Win版 UIA変化ダンプ",
            variable=self.var_debug_uia,
            takefocus=False,
            command=self._sync_ui_to_engine,
        ).pack(side="left")
        ttk.Button(
            log_ctrl, text="Win版 UIAスナップショット(3秒後)", takefocus=False,
            command=lambda: self.root.after(3000, lambda: setattr(self.win_app, "dump_requested", True))
        ).pack(side="left", padx=6)
        ttk.Button(
            log_ctrl, text="Web版 DOMスナップショット(3秒後)", takefocus=False,
            command=lambda: self.root.after(3000, lambda: setattr(self.web, "dump_requested", True))
        ).pack(side="left", padx=4)
        ttk.Button(log_ctrl, text="ログクリア", takefocus=False, command=self._clear_log).pack(side="right")

        self.txt_log = scrolledtext.ScrolledText(
            log_frame, height=13, font=("Consolas", 9), bg="#10141a", fg="#e0e6ed", state="disabled", takefocus=0
        )
        self.txt_log.pack(fill="both", expand=True)

    def _find_chrome_exe(self) -> str:
        candidates = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        ]
        for p in candidates:
            if os.path.exists(p):
                return p
        return ""

    def _launch_chrome_cdp(self):
        exe = self._find_chrome_exe()
        if not exe:
            messagebox.showerror("エラー", "Chrome / Edge が見つかりませんでした。")
            return
        port = self.var_cdp_port.get().strip() or "9222"
        url = self.var_web_url.get().strip() or "https://qso1.net/beacon"
        os.makedirs(CHROME_PROFILE_DIR, exist_ok=True)
        args = [
            exe,
            f"--remote-debugging-port={port}",
            f"--user-data-dir={CHROME_PROFILE_DIR}",
            "--disable-background-timer-throttling",
            "--disable-renderer-backgrounding",
            "--disable-backgrounding-occluded-windows",
            url,
        ]
        subprocess.Popen(args)
        self.enqueue_log(f"[WEB] Bridge専用ブラウザを起動しました (CDP Port: {port})。ログイン＆ルームJoin後に「CDP接続」を押してください。")

    def _toggle_cdp(self):
        if self.web.cdp.connected:
            self.bridge.set_armed(False)
            self.btn_arm.config(text="BRIDGE START (ARM)", bg="#06d6a0")
            threading.Thread(target=self.web.disconnect, daemon=True).start()
        else:
            try:
                port = int(self.var_cdp_port.get().strip() or "9222")
            except ValueError:
                port = 9222
            threading.Thread(target=self.web.connect, args=(port,), daemon=True).start()

    def _apply_config_to_ui(self):
        self.var_cdp_port.set(str(self.config.get("cdp_port", "9222")))
        self.var_web_url.set(self.config.get("web_url", "https://qso1.net/beacon"))
        self.var_web_ptt.set(self.config.get("web_ptt_method", "JS_EVENT"))
        self.var_win_ptt.set(self.config.get("win_ptt_method", "CLICK"))
        self.var_win_rx_kw.set(self.config.get("win_rx_keyword", "送信中"))
        self.var_own_call.set(self.config.get("own_callsign", ""))
        self.var_ignore_own.set(self.config.get("ignore_own_call", True))
        self.var_web_hang.set(str(self.config.get("web_hang_ms", 350)))
        self.var_win_hang.set(str(self.config.get("win_hang_ms", 350)))
        self.var_guard_ms.set(str(self.config.get("guard_ms", 700)))
        self.var_tot_sec.set(str(self.config.get("tot_sec", 55)))
        self.var_debug_uia.set(self.config.get("debug_uia", False))
        self._sync_ui_to_engine()

    def _sync_ui_to_engine(self):
        try:
            self.bridge.web_hang_ms = max(0, int(self.var_web_hang.get() or 350))
            self.bridge.win_hang_ms = max(0, int(self.var_win_hang.get() or 350))
            self.bridge.guard_ms = max(100, int(self.var_guard_ms.get() or 700))
            self.bridge.tot_sec = max(10, int(self.var_tot_sec.get() or 55))
        except ValueError:
            pass

        own = self.var_own_call.get().strip().upper()
        ign = bool(self.var_ignore_own.get())

        # Windows版から自局コールが自動検出できていればWeb側にも共有
        win_own = self.win_app.get_status_copy().get("own_call", "")
        effective_own = own or win_own

        self.web.ptt_method = self.var_web_ptt.get()
        self.web.own_callsign = effective_own
        self.web.ignore_own_call = ign

        self.win_app.ptt_method = self.var_win_ptt.get()
        self.win_app.rx_keyword = self.var_win_rx_kw.get()
        self.win_app.own_callsign_override = own
        self.win_app.ignore_own_callsign = ign
        self.win_app.debug_uia = bool(self.var_debug_uia.get())

    def _toggle_arm(self):
        if not self.bridge.armed:
            self._sync_ui_to_engine()
            w_snap = self.web.get_status_copy()
            d_snap = self.win_app.get_status_copy()
            if not w_snap["cdp_connected"]:
                messagebox.showwarning("未接続", "Web版 Chrome に「CDP接続」してください。")
                return
            if not w_snap["room_ready"]:
                messagebox.showwarning("未入室", "Web版 QSO One でルームに Join (Ready to talk.) してください。")
                return
            if not d_snap["attached"]:
                messagebox.showwarning("未検出", "Windows版 QSO One が見つかりません。")
                return
            self.bridge.set_armed(True)
            self.btn_arm.config(text="BRIDGE STOP", bg="#ffb703")
        else:
            self.bridge.set_armed(False)
            self.btn_arm.config(text="BRIDGE START (ARM)", bg="#06d6a0")

    def _on_emergency_rx(self):
        self.bridge.set_armed(False)
        self.bridge.manual_web_tx = False
        self.bridge.manual_win_tx = False
        self.btn_arm.config(text="BRIDGE START (ARM)", bg="#06d6a0")
        threading.Thread(target=lambda: [self.web.ptt_off(), self.win_app.ptt_off()], daemon=True).start()
        self.enqueue_log("[EMERGENCY] 緊急ALL RXを実行し、ブリッジを停止しました。")

    def _manual_web_ptt(self, down: bool):
        if not self.web.cdp.connected:
            return
        self._sync_ui_to_engine()
        self.bridge.manual_web_tx = down
        fn = self.web.ptt_on if down else self.web.ptt_off
        threading.Thread(target=fn, daemon=True).start()

    def _manual_win_ptt(self, down: bool):
        self._sync_ui_to_engine()
        self.bridge.manual_win_tx = down
        fn = self.win_app.ptt_on if down else self.win_app.ptt_off
        threading.Thread(target=fn, daemon=True).start()

    def _clear_log(self):
        self.txt_log.config(state="normal")
        self.txt_log.delete("1.0", tk.END)
        self.txt_log.config(state="disabled")

    def _web_poll_worker(self):
        while self.running:
            try:
                if self.web.cdp.connected:
                    self.web.poll_once()
            except Exception as e:
                self.enqueue_log(f"[WEB WORKER ERR] {e}")
            time.sleep(0.10)  # 100ms 周期で高速監視

    def _win_uia_worker(self):
        ole32.CoInitialize(None)
        try:
            while self.running:
                try:
                    self.win_app.scan_once()
                except Exception as e:
                    self.enqueue_log(f"[WIN UIA ERR] {e}")
                time.sleep(0.20)
        finally:
            ole32.CoUninitialize()

    def _bridge_worker(self):
        while self.running:
            try:
                self.bridge.step()
            except Exception as e:
                self.enqueue_log(f"[BRIDGE ERR] {e}")
            time.sleep(0.03)

    def _ui_tick(self):
        if not self.running:
            return

        self._sync_ui_to_engine()

        st = self.bridge.state
        if st == WebDstarBridgeEngine.STATE_DISABLED:
            self.lbl_state_banner.config(text="STATE: DISABLED (STANDBY)", fg="#ffd166")
        elif st == WebDstarBridgeEngine.STATE_IDLE:
            self.lbl_state_banner.config(text="STATE: ARMED - LISTENING (IDLE)", fg="#06d6a0")
        elif st == WebDstarBridgeEngine.STATE_WEB_TO_WIN:
            self.lbl_state_banner.config(text="STATE: Web(Beacon) -> Win(D-STAR TX!)", fg="#ff4d6d")
        elif st == WebDstarBridgeEngine.STATE_WIN_TO_WEB:
            self.lbl_state_banner.config(text="STATE: Win(D-STAR) -> Web(Beacon TX!)", fg="#ff4d6d")
        elif st == WebDstarBridgeEngine.STATE_GUARD_WAIT:
            self.lbl_state_banner.config(text="STATE: GUARD WAIT (LOOP PROTECT)", fg="#4cc9f0")

        w_snap = self.web.get_status_copy()
        if w_snap["cdp_connected"]:
            st_txt = "CDP: 接続OK (Room Ready)" if w_snap["room_ready"] else "CDP: 接続OK (未入室)"
            self.lbl_web_conn.config(text=st_txt, foreground="#008800" if w_snap["room_ready"] else "#d97706")
            self.btn_cdp_conn.config(text="CDP切断")
        else:
            self.lbl_web_conn.config(text="CDP: 未接続", foreground="#cc3333")
            self.btn_cdp_conn.config(text="CDP接続")

        self.lbl_web_ptt.config(
            text="PTT: TX (ON AIR)" if (self.web.is_tx or w_snap["self_tx_active"]) else "PTT: RX",
            foreground="#cc0000" if (self.web.is_tx or w_snap["self_tx_active"]) else "#008800",
        )
        self.lbl_web_btn_state.config(text=f"Button: {w_snap['btn_text'][:20]}")
        self.lbl_web_rx.config(
            text=f"RX: {w_snap['rx_callsign']}",
            foreground="#cc0000" if w_snap["is_receiving"] else "#333333",
        )
        self.lbl_web_talker.config(text=f"Talker: {w_snap['talker_text'][:44]}")

        d_snap = self.win_app.get_status_copy()
        if d_snap["attached"]:
            own_t = f" ({d_snap['own_call']})" if d_snap["own_call"] else ""
            self.lbl_win_conn.config(text=f"Win版: 接続OK{own_t}", foreground="#008800")
        else:
            self.lbl_win_conn.config(text="Win版: 未検出", foreground="#cc3333")

        self.lbl_win_ptt.config(
            text="PTT: TX (ON AIR)" if self.win_app.is_tx else "PTT: RX",
            foreground="#cc0000" if self.win_app.is_tx else "#008800",
        )
        self.lbl_win_room.config(text=f"Room: {d_snap['room'][:24]}")
        self.lbl_win_rx.config(
            text=f"RX: {d_snap['rx_callsign']}",
            foreground="#cc0000" if d_snap["is_receiving"] else "#333333",
        )

        new_logs = []
        with self.log_lock:
            while self.log_queue:
                new_logs.append(self.log_queue.popleft())
        if new_logs:
            self.txt_log.config(state="normal")
            for line in new_logs:
                self.txt_log.insert(tk.END, line + "\n")
            lines_cnt = int(self.txt_log.index("end-1c").split(".")[0])
            if lines_cnt > 500:
                self.txt_log.delete("1.0", f"{lines_cnt - 400}.0")
            self.txt_log.see(tk.END)
            self.txt_log.config(state="disabled")

        self.root.after(100, self._ui_tick)

    def on_close(self):
        self.running = False
        self.bridge.set_armed(False)
        try:
            self.web.ptt_off()
            self.win_app.ptt_off()
        except Exception:
            pass
        self.web.disconnect()
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = WebDstarBridgeGUI(root)
    root.mainloop()