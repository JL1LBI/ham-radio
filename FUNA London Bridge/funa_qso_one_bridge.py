"""
========================================================================================
 FUNA QSO One Bridge - Simplex RF <-> VoIP Cross-Link Software (v1.3)
 File: funa_qso_one_bridge.py

 【v1.3 修正点】
  1. Application Hang (デッドロック) の完全解消:
     - status_lock (データ参照のみ) と ptt_lock (PTT実行のみ) を完全分離
     - GUIメインスレッドはI/Oロック・Win32ウィンドウ切替ロックを一切待たない構造へ刷新
     - force_foreground_window から QSO One スレッドへの AttachThreadInput を削除
  2. FT-736M CAT 受信の安定化:
     - in_waiting 依存を排除し、ser.read() ベースのタイムアウト監視 (最大180ms) に変更
========================================================================================
"""

import sys
sys.coinit_flags = 2  # pywinauto / comtypes 用 (COINIT_APARTMENTTHREADED)

import os
import re
import json
import time
import math
import array
import ctypes
from ctypes import wintypes
import threading
import collections
from datetime import datetime
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox

import serial
import serial.tools.list_ports
import win32gui
import win32con
import win32process
from pywinauto import Application


# ==============================================================================
#  基本パス・設定定数
# ==============================================================================
APP_TITLE = "FUNA QSO One Bridge v1.3 (FT-736M <-> QSO One)"

def get_base_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))

BASE_DIR = get_base_dir()
CONFIG_FILE = os.path.join(BASE_DIR, "funa_bridge_config.json")
DUMP_FILE = os.path.join(BASE_DIR, "qso1_beacon_dump.txt")

# FT-736M CAT コマンド定数 (4800bps 8N2)
OP_CAT_ON   = bytes([0x00, 0x00, 0x00, 0x00, 0x00])
OP_CAT_OFF  = bytes([0x00, 0x00, 0x00, 0x00, 0x80])
OP_PTT_ON   = bytes([0x00, 0x00, 0x00, 0x00, 0x08])
OP_PTT_OFF  = bytes([0x00, 0x00, 0x00, 0x00, 0x88])
OP_REQ_SQL  = bytes([0x00, 0x00, 0x00, 0x00, 0xE7])
OP_REQ_SMTR = bytes([0x00, 0x00, 0x00, 0x00, 0xF7])

MODE_CODES = {
    "FM": 0x08,
    "FM-N": 0x88,
    "USB": 0x01,
    "LSB": 0x00,
    "CW": 0x02,
    "CW-N": 0x82,
}

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
ole32 = ctypes.windll.ole32
winmm = ctypes.windll.winmm


# ==============================================================================
#  Win32 キー入力 / フォアグラウンド切替 (ノンデッドロック版)
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
        flags |= 0x0002  # KEYEVENTF_KEYUP
    inp = INPUT()
    inp.type = 1
    inp.ki.wVk = 0x20
    inp.ki.wScan = 0x39
    inp.ki.dwFlags = flags
    user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))


def force_foreground_window(hwnd: int) -> bool:
    """他プロセススレッドへAttachせず安全にフォアグラウンド切替を行う"""
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
#  Zero-Dependency Windows Audio VOX Monitor (winmm.dll waveIn)
# ==============================================================================
class WAVEFORMATEX(ctypes.Structure):
    _fields_ = [
        ("wFormatTag", wintypes.WORD),
        ("nChannels", wintypes.WORD),
        ("nSamplesPerSec", wintypes.DWORD),
        ("nAvgBytesPerSec", wintypes.DWORD),
        ("nBlockAlign", wintypes.WORD),
        ("wBitsPerSample", wintypes.WORD),
        ("cbSize", wintypes.WORD),
    ]

class WAVEHDR(ctypes.Structure):
    _fields_ = [
        ("lpData", ctypes.c_void_p),
        ("dwBufferLength", wintypes.DWORD),
        ("dwBytesRecorded", wintypes.DWORD),
        ("dwUser", ctypes.c_size_t),
        ("dwFlags", wintypes.DWORD),
        ("dwLoops", wintypes.DWORD),
        ("lpNext", ctypes.c_void_p),
        ("reserved", ctypes.c_size_t),
    ]

class WAVEINCAPSW(ctypes.Structure):
    _fields_ = [
        ("wMid", wintypes.WORD),
        ("wPid", wintypes.WORD),
        ("vDriverVersion", wintypes.UINT),
        ("szPname", wintypes.WCHAR * 32),
        ("dwFormats", wintypes.DWORD),
        ("wChannels", wintypes.WORD),
        ("wReserved1", wintypes.WORD),
    ]


class AudioVoxMonitor:
    WHDR_DONE = 0x00000001

    def __init__(self):
        self.running = False
        self.thread = None
        self.device_id = 0
        self.level_pct = 0.0
        self.lock = threading.Lock()

    @staticmethod
    def list_input_devices() -> list[tuple[int, str]]:
        devices = []
        try:
            count = winmm.waveInGetNumDevs()
            for idx in range(count):
                caps = WAVEINCAPSW()
                res = winmm.waveInGetDevCapsW(idx, ctypes.byref(caps), ctypes.sizeof(caps))
                if res == 0:
                    devices.append((idx, caps.szPname))
        except Exception:
            pass
        return devices

    def start(self, device_id: int = 0):
        self.stop()
        self.device_id = device_id
        self.running = True
        self.thread = threading.Thread(target=self._worker, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=0.8)
        self.thread = None
        with self.lock:
            self.level_pct = 0.0

    def get_level(self) -> float:
        with self.lock:
            return self.level_pct

    def _worker(self):
        h_wave_in = wintypes.HANDLE()
        wfx = WAVEFORMATEX(
            wFormatTag=1,
            nChannels=1,
            nSamplesPerSec=8000,
            nAvgBytesPerSec=16000,
            nBlockAlign=2,
            wBitsPerSample=16,
            cbSize=0,
        )
        res = winmm.waveInOpen(ctypes.byref(h_wave_in), self.device_id, ctypes.byref(wfx), 0, 0, 0)
        if res != 0:
            self.running = False
            return

        buf_size = 800
        num_bufs = 4
        raw_buffers = [ctypes.create_string_buffer(buf_size) for _ in range(num_bufs)]
        headers = []

        for buf in raw_buffers:
            hdr = WAVEHDR()
            hdr.lpData = ctypes.addressof(buf)
            hdr.dwBufferLength = buf_size
            hdr.dwFlags = 0
            winmm.waveInPrepareHeader(h_wave_in, ctypes.byref(hdr), ctypes.sizeof(hdr))
            winmm.waveInAddBuffer(h_wave_in, ctypes.byref(hdr), ctypes.sizeof(hdr))
            headers.append(hdr)

        winmm.waveInStart(h_wave_in)

        try:
            while self.running:
                got_data = False
                for i, hdr in enumerate(headers):
                    if hdr.dwFlags & self.WHDR_DONE:
                        got_data = True
                        rec_bytes = hdr.dwBytesRecorded
                        if rec_bytes >= 2:
                            raw = raw_buffers[i].raw[:rec_bytes]
                            samples = array.array("h")
                            samples.frombytes(raw[: (len(raw) // 2) * 2])
                            if samples:
                                sq_sum = sum(s * s for s in samples)
                                rms = math.sqrt(sq_sum / len(samples))
                                pct = min(100.0, (rms / 32768.0) * 350.0)
                                with self.lock:
                                    self.level_pct = pct

                        winmm.waveInUnprepareHeader(h_wave_in, ctypes.byref(hdr), ctypes.sizeof(hdr))
                        hdr.dwFlags = 0
                        hdr.dwBytesRecorded = 0
                        winmm.waveInPrepareHeader(h_wave_in, ctypes.byref(hdr), ctypes.sizeof(hdr))
                        winmm.waveInAddBuffer(h_wave_in, ctypes.byref(hdr), ctypes.sizeof(hdr))

                if not got_data:
                    time.sleep(0.015)
        finally:
            try:
                winmm.waveInReset(h_wave_in)
                for hdr in headers:
                    winmm.waveInUnprepareHeader(h_wave_in, ctypes.byref(hdr), ctypes.sizeof(hdr))
                winmm.waveInClose(h_wave_in)
            except Exception:
                pass


# ==============================================================================
#  FT-736M CAT ドライバー
# ==============================================================================
class FT736Controller:
    MIN_CMD_GAP = 0.060
    REPLY_TIMEOUT = 0.180

    def __init__(self, log_cb=None):
        self.ser = None
        self.port = ""
        self.lock = threading.RLock()
        self.connected = False
        self.is_tx = False
        self.sql_open = False
        self.invert_sql = False
        self.log_sql_events = True
        self.last_sql_raw = ""
        self.s_meter_val = 0x30
        self.cat_ok_count = 0
        self.cat_to_count = 0
        self.log_cb = log_cb
        self._last_logged_sql = None
        self._last_cmd_end = 0.0
        self._warned_timeout_streak = 0

    def _log(self, msg: str):
        if self.log_cb:
            self.log_cb(msg)

    def connect(self, port: str) -> bool:
        self.disconnect()
        with self.lock:
            try:
                self.ser = serial.Serial(
                    port=port,
                    baudrate=4800,
                    bytesize=serial.EIGHTBITS,
                    parity=serial.PARITY_NONE,
                    stopbits=serial.STOPBITS_TWO,
                    timeout=0.03,
                    write_timeout=0.5,
                    rtscts=False,
                    dsrdtr=False,
                    xonxoff=False,
                )
                self.port = port
                self.connected = True
                self.is_tx = False
                self.sql_open = False
                self.cat_ok_count = 0
                self.cat_to_count = 0
                self._warned_timeout_streak = 0
                self._last_logged_sql = None
                self._last_cmd_end = 0.0

                self._send_cmd_locked(OP_CAT_ON, "CAT ON")
                self._send_cmd_locked(OP_PTT_OFF, "INIT RX")
                self._log(f"[CAT] {port} に接続完了 (4800bps 8N2 / CAT ON)")
                return True
            except Exception as e:
                self.connected = False
                self.ser = None
                self._log(f"[CAT ERROR] {port} 接続失敗: {e}")
                return False

    def disconnect(self):
        with self.lock:
            if self.ser and self.ser.is_open:
                try:
                    self._send_cmd_locked(OP_PTT_OFF, "SAFETY PTT OFF")
                    self._send_cmd_locked(OP_PTT_OFF, "SAFETY PTT OFF 2")
                    self._send_cmd_locked(OP_CAT_OFF, "CAT OFF")
                    self.ser.close()
                except Exception:
                    pass
            self.ser = None
            self.connected = False
            self.is_tx = False
            self.sql_open = False

    def _send_cmd_locked(self, cmd_bytes: bytes, desc: str = "", expect_reply: bool = False) -> bytes:
        if not self.ser or not self.ser.is_open:
            return b""

        now = time.monotonic()
        wait = self.MIN_CMD_GAP - (now - self._last_cmd_end)
        if wait > 0:
            time.sleep(wait)

        try:
            self.ser.reset_input_buffer()
            self.ser.write(cmd_bytes)
            self.ser.flush()
        except Exception as e:
            self._last_cmd_end = time.monotonic()
            self._log(f"[CAT TX ERR] ({desc}): {e}")
            return b""

        if not expect_reply:
            time.sleep(0.025)
            self._last_cmd_end = time.monotonic()
            return b""

        buf = bytearray()
        start = time.monotonic()
        deadline = start + self.REPLY_TIMEOUT
        last_rx_time = start

        # 送信完了まで少し待つ (11.5ms)
        time.sleep(0.015)

        while time.monotonic() < deadline:
            try:
                chunk = self.ser.read(5 - len(buf))
                if chunk:
                    buf.extend(chunk)
                    last_rx_time = time.monotonic()
                    if len(buf) >= 5:
                        break
                elif len(buf) >= 1 and (time.monotonic() - last_rx_time) >= 0.030:
                    break
            except Exception:
                break

        self._last_cmd_end = time.monotonic()
        return bytes(buf)

    def set_freq_mode(self, freq_mhz: float, mode_name: str):
        with self.lock:
            if not self.connected:
                return
            freq_10hz = int(round(freq_mhz * 100000))
            freq_str = f"{freq_10hz:08d}"
            bcd = bytes.fromhex(freq_str)
            self._send_cmd_locked(bcd + bytes([0x01]), f"FREQ {freq_mhz:.5f}MHz")
            code = MODE_CODES.get(mode_name, 0x08)
            self._send_cmd_locked(bytes([code, 0x00, 0x00, 0x00, 0x07]), f"MODE {mode_name}")
            self._log(f"[CAT] 周波数/モード適用: {freq_mhz:.5f} MHz / {mode_name}")

    def set_ptt(self, tx: bool):
        with self.lock:
            if not self.connected:
                self.is_tx = False
                return
            if self.is_tx == tx:
                return
            self.is_tx = tx
            if tx:
                self._send_cmd_locked(OP_PTT_ON, "PTT: TX ON")
                self._log("[CAT] FT-736M PTT -> TX ON (送信)")
            else:
                self._send_cmd_locked(OP_PTT_OFF, "PTT: RX OFF")
                self._send_cmd_locked(OP_PTT_OFF, "PTT: RX OFF 2")
                self._log("[CAT] FT-736M PTT -> RX (受信復帰)")

    def poll_squelch(self) -> bool:
        with self.lock:
            if not self.connected or self.is_tx:
                return False
            res = self._send_cmd_locked(OP_REQ_SQL, "SQL CHK", expect_reply=True)
            if len(res) >= 1:
                self.cat_ok_count += 1
                self._warned_timeout_streak = 0
                raw_open = bool(res[0] & 0x80)
                self.sql_open = (not raw_open) if self.invert_sql else raw_open
                self.last_sql_raw = " ".join(f"{b:02X}" for b in res)
                if self.log_sql_events and self._last_logged_sql != self.sql_open:
                    self._last_logged_sql = self.sql_open
                    st_txt = "OPEN (BUSY)" if self.sql_open else "CLOSE"
                    self._log(f"[CAT SQL] {st_txt} (0xE7 RX: {self.last_sql_raw})")
            else:
                self.cat_to_count += 1
                self._warned_timeout_streak += 1
                if self._warned_timeout_streak == 5:
                    self._log("[CAT WARN] 0xE7 スケルチ応答が連続5回タイムアウトしています (ケーブル/CAT状態確認)")
            return self.sql_open

    def poll_smeter(self) -> int:
        with self.lock:
            if not self.connected or self.is_tx:
                return self.s_meter_val
            res = self._send_cmd_locked(OP_REQ_SMTR, "S-MTR CHK", expect_reply=True)
            if len(res) >= 1:
                self.cat_ok_count += 1
                self.s_meter_val = res[0]
            else:
                self.cat_to_count += 1
            return self.s_meter_val

    @staticmethod
    def s_val_to_label(val: int) -> tuple[float, str]:
        val = max(0x30, min(0xAD, val))
        ratio = (val - 0x30) / (0xAD - 0x30)
        if ratio < 0.08:
            s_txt = "S0"
        elif ratio < 0.25:
            s_txt = "S3"
        elif ratio < 0.45:
            s_txt = "S7"
        elif ratio < 0.65:
            s_txt = "S9"
        elif ratio < 0.85:
            s_txt = "S9+20dB"
        else:
            s_txt = "S9+40dB"
        return ratio * 100.0, s_txt


# ==============================================================================
#  QSO One Flutter UIA ドライバー (ロック分離・完全ノンデッドロック設計)
# ==============================================================================
class QsoOneController:
    def __init__(self, log_cb=None):
        self.main_hwnd = None
        self.flutter_hwnd = None
        self._uia_app = None
        self._uia_win = None
        self.is_tx = False

        # status_lock: ステータス辞書の読み書きだけに使用 (即時解放・I/O禁止)
        # ptt_lock:    PTT操作のみに使用 (GUIメインスレッドからは絶対に取得しない)
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
        self.ptt_method = "SPACE"
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
                if "FLUTTER_RUNNER_WIN32_WINDOW" in cls or "qso one" in title.lower():
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

                    if self.debug_uia and ctype in ("Button", "Text", "Group", "Slider", "ProgressBar"):
                        compact = name.replace("\n", " / ")
                        if any(k in compact for k in (rx_kw, "TG", "Beacon", "通信", "送信", "TX", "RX", "たった今", "Echo")):
                            debug_items.append(f"[{ctype}] {compact[:75]}")

                    if ctype == "Text" and not detected_own_call:
                        txt_u = name.strip().upper()
                        if re.fullmatch(r"[A-Z0-9]{1,3}\d[A-Z]{1,4}", txt_u):
                            detected_own_call = txt_u
                        elif "(あなた)" in name:
                            m_own = re.match(r"^\s*([A-Z0-9]{1,3}\d[A-Z]{1,4})\b", txt_u)
                            if m_own:
                                detected_own_call = m_own.group(1)

                    if "通信あり" in name or "TG " in name or ("Beacon" in name and ctype == "Button"):
                        lines = [ln.strip() for ln in name.splitlines() if ln.strip()]
                        if "TG " in name:
                            m = re.search(r"TG\s*(\d+)", name)
                            if m:
                                room_val = f"TG{m.group(1)}"
                                if len(lines) >= 5:
                                    room_val += f" ({lines[4]})"
                        elif lines:
                            room_val = " / ".join(lines[:2])

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
                    with open(DUMP_FILE, "w", encoding="utf-8") as df:
                        df.write(f"=== QSO One UIA Dump ({datetime.now()}) ===\n")
                        for ln in full_dump_lines:
                            df.write(ln + "\n")
                    self._log(f"[DUMP] 全UIA要素({len(full_dump_lines)}件)を保存しました: {DUMP_FILE}")
                    for ln in full_dump_lines[-12:]:
                        self._log(f"  {ln[:110]}")
                except Exception as e:
                    self._log(f"[DUMP ERR] {e}")

            if self.debug_uia and debug_items:
                snap = " | ".join(debug_items[:12])
                if snap != self._last_debug_snapshot:
                    self._last_debug_snapshot = snap
                    self._log(f"[UIA DEBUG] {snap}")

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
                self._log("[QSO1 ERR] QSO One ウィンドウ未検出のためPTT送信不可")
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
                self._log(f"[QSO1] PTT -> TX ON (Mouse Click @ {pt_x},{pt_y})")
            else:
                fg_ok = force_foreground_window(m_hwnd)
                if fg_ok:
                    send_space_key(True)
                    if f_hwnd and win32gui.IsWindow(f_hwnd):
                        user32.PostMessageW(f_hwnd, win32con.WM_KEYDOWN, win32con.VK_SPACE, (0x39 << 16) | 1)
                    self.is_tx = True
                    self._log("[QSO1] PTT -> TX ON (Spacebar -> QSO One)")
                else:
                    if f_hwnd and win32gui.IsWindow(f_hwnd):
                        user32.PostMessageW(f_hwnd, win32con.WM_KEYDOWN, win32con.VK_SPACE, (0x39 << 16) | 1)
                    self.is_tx = True
                    self._log("[QSO1 WARN] QSO One フォアグラウンド切替未確認 (誤爆防止のためグローバルSpace省略)")

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
                self._log("[QSO1] PTT -> RX OFF (Mouse Release)")
            else:
                if m_hwnd and win32gui.GetForegroundWindow() == m_hwnd:
                    send_space_key(False)
                elif m_hwnd and force_foreground_window(m_hwnd):
                    send_space_key(False)
                if f_hwnd and win32gui.IsWindow(f_hwnd):
                    user32.PostMessageW(f_hwnd, win32con.WM_KEYUP, win32con.VK_SPACE, (0x39 << 16) | 0xC0000001)
                self._log("[QSO1] PTT -> RX OFF (Spacebar Release)")

            self.is_tx = False


# ==============================================================================
#  ブリッジ・ステートマシン
# ==============================================================================
class BridgeEngine:
    STATE_DISABLED   = "DISABLED"
    STATE_IDLE       = "IDLE"
    STATE_RF_TO_VOIP = "RF -> VoIP (QSO1 TX)"
    STATE_VOIP_TO_RF = "VoIP -> RF (FT-736M TX)"
    STATE_GUARD_WAIT = "GUARD WAIT"

    def __init__(self, rig: FT736Controller, qso1: QsoOneController, audio: AudioVoxMonitor, log_cb=None):
        self.rig = rig
        self.qso1 = qso1
        self.audio = audio
        self.log_cb = log_cb

        self.armed = False
        self.state = self.STATE_DISABLED
        self.tx_start_time = 0.0
        self.last_rx_seen = 0.0
        self.guard_until = 0.0

        self.trigger_mode = "CAT_SQL"
        self.vox_threshold = 12.0
        self.rf_hang_ms = 350
        self.voip_hang_ms = 350
        self.guard_ms = 600
        self.tot_sec = 120

        self.manual_rig_tx = False
        self.manual_qso1_tx = False
        self._warned_not_ready = False

    def _log(self, msg: str):
        if self.log_cb:
            self.log_cb(msg)

    def set_armed(self, armed: bool):
        self.armed = armed
        self._warned_not_ready = False
        if armed:
            self.state = self.STATE_IDLE
            self._log(f"[BRIDGE] ★ ブリッジ有効化 (ARMED | 検出方式: {self.trigger_mode})")
        else:
            self.state = self.STATE_DISABLED
            self._log("[BRIDGE] ■ ブリッジ停止 (STANDBY - モニターのみ)")

    def _is_rf_rx_active(self, sql_open: bool, audio_lvl: float) -> bool:
        vox_open = audio_lvl >= self.vox_threshold
        if self.trigger_mode == "CAT_SQL":
            return sql_open
        elif self.trigger_mode == "AUDIO_VOX":
            return vox_open
        else:
            return sql_open and vox_open

    def step(self, sql_open: bool, audio_lvl: float):
        now = time.monotonic()

        if self.manual_rig_tx or self.manual_qso1_tx:
            return

        if not self.armed:
            if self.rig.is_tx:
                self.rig.set_ptt(False)
            if self.qso1.is_tx:
                self.qso1.ptt_off()
            self.state = self.STATE_DISABLED
            return

        q_snap = self.qso1.get_status_copy()
        q_attached = q_snap["attached"]
        voip_rx = bool(q_snap["is_receiving"])
        voip_call = q_snap["rx_callsign"]

        rf_rx = self._is_rf_rx_active(sql_open, audio_lvl)

        if not q_attached or (self.trigger_mode != "AUDIO_VOX" and not self.rig.connected):
            if rf_rx and not self._warned_not_ready:
                self._warned_not_ready = True
                self._log(f"[BRIDGE WARN] RF検出しましたが未準備のため保留 (CAT={self.rig.connected}, QSO1={q_attached})")
            return
        self._warned_not_ready = False

        if self.state == self.STATE_IDLE:
            if voip_rx and self.rig.connected:
                self.state = self.STATE_VOIP_TO_RF
                self.tx_start_time = now
                self.last_rx_seen = now
                self._log(f"[ROUTE] VoIP受信検出 ({voip_call}) -> FT-736M 送信開始")
                self.rig.set_ptt(True)
            elif rf_rx:
                self.state = self.STATE_RF_TO_VOIP
                self.tx_start_time = now
                self.last_rx_seen = now
                self._log(f"[ROUTE] RF受信検出 ({self.trigger_mode}: SQL={sql_open}, VOX={audio_lvl:.1f}%) -> QSO One 送信開始")
                self.qso1.ptt_on()

        elif self.state == self.STATE_RF_TO_VOIP:
            if now - self.tx_start_time >= self.tot_sec:
                self._log(f"[TOT!] RF->VoIP 送信時間超過 ({self.tot_sec}s) 強制終了")
                self.qso1.ptt_off()
                self.state = self.STATE_GUARD_WAIT
                self.guard_until = now + (self.guard_ms / 1000.0)
                return

            if rf_rx:
                self.last_rx_seen = now
            elif now - self.last_rx_seen >= (self.rf_hang_ms / 1000.0):
                self.qso1.ptt_off()
                self._log("[ROUTE] RF受信終了 -> QSO One 送信停止 (Guard Wait)")
                self.state = self.STATE_GUARD_WAIT
                self.guard_until = now + (self.guard_ms / 1000.0)

        elif self.state == self.STATE_VOIP_TO_RF:
            if now - self.tx_start_time >= self.tot_sec:
                self._log(f"[TOT!] VoIP->RF 送信時間超過 ({self.tot_sec}s) 強制終了")
                self.rig.set_ptt(False)
                self.state = self.STATE_GUARD_WAIT
                self.guard_until = now + (self.guard_ms / 1000.0)
                return

            if voip_rx:
                self.last_rx_seen = now
            elif now - self.last_rx_seen >= (self.voip_hang_ms / 1000.0):
                self.rig.set_ptt(False)
                self._log("[ROUTE] VoIP受信終了 -> FT-736M 受信復帰 (Guard Wait)")
                self.state = self.STATE_GUARD_WAIT
                self.guard_until = now + (self.guard_ms / 1000.0)

        elif self.state == self.STATE_GUARD_WAIT:
            if self.rig.is_tx:
                self.rig.set_ptt(False)
            if self.qso1.is_tx:
                self.qso1.ptt_off()
            if now >= self.guard_until:
                self.state = self.STATE_IDLE


# ==============================================================================
#  メイン GUI アプリケーション (Tkinter)
# ==============================================================================
class FunaBridgeGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("960x760")
        self.root.minsize(880, 700)

        self.log_queue = collections.deque(maxlen=500)
        self.log_lock = threading.Lock()
        self.running = True

        self.rig = FT736Controller(log_cb=self.enqueue_log)
        self.qso1 = QsoOneController(log_cb=self.enqueue_log)
        self.audio = AudioVoxMonitor()
        self.bridge = BridgeEngine(self.rig, self.qso1, self.audio, log_cb=self.enqueue_log)

        self.config = self._load_config()
        self._install_spacebar_immunity()
        self._build_ui()
        self._apply_config_to_ui()

        threading.Thread(target=self._uia_worker, daemon=True).start()
        threading.Thread(target=self._bridge_worker, daemon=True).start()

        self._start_selected_audio()

        self.root.after(100, self._ui_tick)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.enqueue_log("[SYSTEM] FUNA QSO One Bridge v1.3 を起動しました。")

    def _install_spacebar_immunity(self):
        for cls in ("Button", "TButton", "Checkbutton", "TCheckbutton", "Combobox", "TCombobox", "Scale", "TScale"):
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
            "com_port": "COM3",
            "preset_freq": "145.50000",
            "preset_mode": "FM",
            "audio_device_idx": 0,
            "trigger_mode": "CAT_SQL",
            "vox_threshold": 12.0,
            "ptt_method": "SPACE",
            "rx_keyword": "送信中",
            "own_callsign": "",
            "ignore_own_call": True,
            "invert_sql": False,
            "log_sql_events": True,
            "poll_smeter": True,
            "rf_hang_ms": 350,
            "voip_hang_ms": 350,
            "guard_ms": 600,
            "tot_sec": 120,
            "debug_uia": False,
        }
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    if loaded.get("rx_keyword") == "送信中:":
                        loaded["rx_keyword"] = "送信中"
                    default_cfg.update(loaded)
            except Exception:
                pass
        return default_cfg

    def _save_config(self):
        self._sync_ui_to_engine()
        cfg = {
            "com_port": self.var_com.get(),
            "preset_freq": self.var_freq.get(),
            "preset_mode": self.var_mode.get(),
            "audio_device_idx": self._get_selected_audio_idx(),
            "trigger_mode": self.var_trigger.get(),
            "vox_threshold": float(self.var_vox_th.get()),
            "ptt_method": self.var_ptt_method.get(),
            "rx_keyword": self.var_rx_kw.get(),
            "own_callsign": self.var_own_call.get(),
            "ignore_own_call": bool(self.var_ignore_own.get()),
            "invert_sql": bool(self.var_invert_sql.get()),
            "log_sql_events": bool(self.var_log_sql.get()),
            "poll_smeter": bool(self.var_poll_smeter.get()),
            "rf_hang_ms": int(self.var_rf_hang.get()),
            "voip_hang_ms": int(self.var_voip_hang.get()),
            "guard_ms": int(self.var_guard_ms.get()),
            "tot_sec": int(self.var_tot_sec.get()),
            "debug_uia": bool(self.var_debug_uia.get()),
        }
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2, ensure_ascii=False)
            self.enqueue_log("[CONFIG] 設定を保存しました。")
        except Exception as e:
            self.enqueue_log(f"[CONFIG ERR] 保存失敗: {e}")

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

        # 左カラム: FT-736M CAT
        left_frame = ttk.LabelFrame(main_pane, text=" FT-736M CAT Control (4800 8N2) ", padding=10)
        left_frame.pack(side="left", fill="both", expand=True, padx=(0, 6))

        row_com = ttk.Frame(left_frame)
        row_com.pack(fill="x", pady=3)
        ttk.Label(row_com, text="COMポート:", width=11).pack(side="left")
        self.var_com = tk.StringVar()
        self.combo_com = ttk.Combobox(row_com, textvariable=self.var_com, width=14, takefocus=False)
        self.combo_com.pack(side="left", padx=3)
        ttk.Button(row_com, text="更新", width=5, takefocus=False, command=self._refresh_com_ports).pack(side="left", padx=2)
        self.btn_com_conn = ttk.Button(row_com, text="接続", width=8, takefocus=False, command=self._toggle_com)
        self.btn_com_conn.pack(side="left", padx=4)

        row_freq = ttk.Frame(left_frame)
        row_freq.pack(fill="x", pady=4)
        ttk.Label(row_freq, text="周波数/Mode:", width=11).pack(side="left")
        self.var_freq = tk.StringVar()
        ttk.Entry(row_freq, textvariable=self.var_freq, width=11).pack(side="left", padx=2)
        ttk.Label(row_freq, text="MHz").pack(side="left")
        self.var_mode = tk.StringVar()
        ttk.Combobox(row_freq, textvariable=self.var_mode, values=list(MODE_CODES.keys()), state="readonly", width=6, takefocus=False).pack(side="left", padx=4)
        ttk.Button(row_freq, text="無線機に適用", takefocus=False, command=self._apply_rig_freq).pack(side="left", padx=2)

        ttk.Separator(left_frame, orient="horizontal").pack(fill="x", pady=6)

        row_rig_stat = ttk.Frame(left_frame)
        row_rig_stat.pack(fill="x", pady=2)
        self.lbl_rig_conn = ttk.Label(row_rig_stat, text="CAT: DISCONNECTED", font=("Consolas", 9, "bold"), foreground="#cc3333")
        self.lbl_rig_conn.pack(side="left")
        self.lbl_rig_ptt = ttk.Label(row_rig_stat, text="PTT: RX", font=("Consolas", 10, "bold"), foreground="#008800")
        self.lbl_rig_ptt.pack(side="right")

        row_sql = ttk.Frame(left_frame)
        row_sql.pack(fill="x", pady=3)
        ttk.Label(row_sql, text="SQL (0xE7):", width=11).pack(side="left")
        self.lbl_sql = ttk.Label(row_sql, text="[ CLOSE ]", font=("Consolas", 10, "bold"))
        self.lbl_sql.pack(side="left")
        self.var_invert_sql = tk.BooleanVar()
        ttk.Checkbutton(row_sql, text="SQL反転", variable=self.var_invert_sql, takefocus=False, command=self._sync_ui_to_engine).pack(side="right")
        self.var_log_sql = tk.BooleanVar()
        ttk.Checkbutton(row_sql, text="SQLログ", variable=self.var_log_sql, takefocus=False, command=self._sync_ui_to_engine).pack(side="right", padx=4)

        row_smtr = ttk.Frame(left_frame)
        row_smtr.pack(fill="x", pady=3)
        ttk.Label(row_smtr, text="S-Meter:", width=11).pack(side="left")
        self.pb_smeter = ttk.Progressbar(row_smtr, maximum=100, length=130)
        self.pb_smeter.pack(side="left", padx=3)
        self.lbl_smeter = ttk.Label(row_smtr, text="S0", width=8, font=("Consolas", 9, "bold"))
        self.lbl_smeter.pack(side="left")
        self.var_poll_smeter = tk.BooleanVar()
        ttk.Checkbutton(row_smtr, text="S取得", variable=self.var_poll_smeter, takefocus=False).pack(side="right")

        row_rig_test = ttk.Frame(left_frame)
        row_rig_test.pack(fill="x", pady=(8, 0))
        self.btn_test_rig_ptt = ttk.Button(row_rig_test, text="手動テスト: FT-736M PTT (押下式)", takefocus=False)
        self.btn_test_rig_ptt.pack(fill="x")
        self.btn_test_rig_ptt.bind("<ButtonPress-1>", lambda e: self._manual_rig_ptt(True))
        self.btn_test_rig_ptt.bind("<ButtonRelease-1>", lambda e: self._manual_rig_ptt(False))

        # 右カラム: QSO One & Audio VOX
        right_frame = ttk.LabelFrame(main_pane, text=" QSO One & Audio VOX Bridge Settings ", padding=10)
        right_frame.pack(side="left", fill="both", expand=True, padx=(6, 0))

        row_qstat = ttk.Frame(right_frame)
        row_qstat.pack(fill="x", pady=2)
        self.lbl_qso_attach = ttk.Label(row_qstat, text="QSO One: 未検出", font=("Consolas", 10, "bold"), foreground="#cc3333")
        self.lbl_qso_attach.pack(side="left")
        self.lbl_qso_ptt = ttk.Label(row_qstat, text="PTT: RX", font=("Consolas", 10, "bold"), foreground="#008800")
        self.lbl_qso_ptt.pack(side="right")

        row_qinfo = ttk.Frame(right_frame)
        row_qinfo.pack(fill="x", pady=2)
        self.lbl_qso_room = ttk.Label(row_qinfo, text="Room: ---", width=26)
        self.lbl_qso_room.pack(side="left")
        self.lbl_qso_rx = ttk.Label(row_qinfo, text="RX Call: Standby", font=("Consolas", 10, "bold"))
        self.lbl_qso_rx.pack(side="right")

        ttk.Separator(right_frame, orient="horizontal").pack(fill="x", pady=5)

        row_trig = ttk.Frame(right_frame)
        row_trig.pack(fill="x", pady=2)
        ttk.Label(row_trig, text="RF受信検出:", width=12).pack(side="left")
        self.var_trigger = tk.StringVar()
        ttk.Combobox(
            row_trig, textvariable=self.var_trigger,
            values=["CAT_SQL", "AUDIO_VOX", "CAT_AND_VOX"], state="readonly", width=15, takefocus=False
        ).pack(side="left", padx=2)
        ttk.Label(row_trig, text="PTT方式:").pack(side="left", padx=(6, 2))
        self.var_ptt_method = tk.StringVar()
        ttk.Combobox(
            row_trig, textvariable=self.var_ptt_method,
            values=["SPACE", "CLICK"], state="readonly", width=8, takefocus=False
        ).pack(side="left")

        row_aud = ttk.Frame(right_frame)
        row_aud.pack(fill="x", pady=2)
        ttk.Label(row_aud, text="マイク入力:", width=12).pack(side="left")
        self.var_audio_dev = tk.StringVar()
        self.combo_audio = ttk.Combobox(row_aud, textvariable=self.var_audio_dev, state="readonly", width=32, takefocus=False)
        self.combo_audio.pack(side="left", fill="x", expand=True)
        self.combo_audio.bind("<<ComboboxSelected>>", lambda e: self._start_selected_audio())

        row_vox = ttk.Frame(right_frame)
        row_vox.pack(fill="x", pady=2)
        ttk.Label(row_vox, text="VOXレベル:", width=12).pack(side="left")
        self.pb_vox = ttk.Progressbar(row_vox, maximum=100, length=120)
        self.pb_vox.pack(side="left", padx=2)
        ttk.Label(row_vox, text="閾値:").pack(side="left", padx=(4, 2))
        self.var_vox_th = tk.DoubleVar()
        ttk.Scale(row_vox, from_=1, to=80, variable=self.var_vox_th, orient="horizontal", length=80, takefocus=False).pack(side="left")
        self.lbl_vox_th = ttk.Label(row_vox, text="12%", width=5)
        self.lbl_vox_th.pack(side="left")

        row_qcfg = ttk.Frame(right_frame)
        row_qcfg.pack(fill="x", pady=2)
        ttk.Label(row_qcfg, text="RX検出文字:", width=12).pack(side="left")
        self.var_rx_kw = tk.StringVar()
        ttk.Entry(row_qcfg, textvariable=self.var_rx_kw, width=10).pack(side="left", padx=2)
        ttk.Label(row_qcfg, text="自局Call:").pack(side="left", padx=(4, 2))
        self.var_own_call = tk.StringVar()
        ttk.Entry(row_qcfg, textvariable=self.var_own_call, width=9).pack(side="left", padx=2)
        self.var_ignore_own = tk.BooleanVar()
        ttk.Checkbutton(row_qcfg, text="自局除外", variable=self.var_ignore_own, takefocus=False).pack(side="left")

        row_tmr = ttk.Frame(right_frame)
        row_tmr.pack(fill="x", pady=3)
        ttk.Label(row_tmr, text="Hang(RF/VoIP ms):", width=16).pack(side="left")
        self.var_rf_hang = tk.StringVar()
        self.var_voip_hang = tk.StringVar()
        ttk.Entry(row_tmr, textvariable=self.var_rf_hang, width=5).pack(side="left", padx=1)
        ttk.Entry(row_tmr, textvariable=self.var_voip_hang, width=5).pack(side="left", padx=1)
        ttk.Label(row_tmr, text="Guard(ms):").pack(side="left", padx=(4, 1))
        self.var_guard_ms = tk.StringVar()
        ttk.Entry(row_tmr, textvariable=self.var_guard_ms, width=5).pack(side="left", padx=1)
        ttk.Label(row_tmr, text="TOT(s):").pack(side="left", padx=(4, 1))
        self.var_tot_sec = tk.StringVar()
        ttk.Entry(row_tmr, textvariable=self.var_tot_sec, width=4).pack(side="left", padx=1)

        row_qtest = ttk.Frame(right_frame)
        row_qtest.pack(fill="x", pady=(6, 0))
        self.btn_test_qso_ptt = ttk.Button(row_qtest, text="手動テスト: QSO One PTT (押下式)", takefocus=False)
        self.btn_test_qso_ptt.pack(side="left", fill="x", expand=True, padx=(0, 4))
        self.btn_test_qso_ptt.bind("<ButtonPress-1>", lambda e: self._manual_qso_ptt(True))
        self.btn_test_qso_ptt.bind("<ButtonRelease-1>", lambda e: self._manual_qso_ptt(False))
        ttk.Button(row_qtest, text="設定保存", takefocus=False, command=self._save_config).pack(side="right")

        # --- 下部: ログ & デバッグ ---
        log_frame = ttk.LabelFrame(self.root, text=" Bridge Event & CAT Monitor Log ", padding=8)
        log_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        log_ctrl = ttk.Frame(log_frame)
        log_ctrl.pack(fill="x", pady=(0, 4))
        self.var_debug_uia = tk.BooleanVar()
        ttk.Checkbutton(
            log_ctrl,
            text="QSO One UIA変化をリアルタイムダンプ",
            variable=self.var_debug_uia,
            takefocus=False,
            command=self._sync_ui_to_engine,
        ).pack(side="left")
        ttk.Button(
            log_ctrl,
            text="UIA全要素スナップショット (3秒後)",
            takefocus=False,
            command=self._schedule_uia_dump,
        ).pack(side="left", padx=10)
        ttk.Button(log_ctrl, text="ログクリア", takefocus=False, command=self._clear_log).pack(side="right")

        self.txt_log = scrolledtext.ScrolledText(
            log_frame, height=13, font=("Consolas", 9), bg="#10141a", fg="#e0e6ed", state="disabled", takefocus=0
        )
        self.txt_log.pack(fill="both", expand=True)

    def _schedule_uia_dump(self):
        self.enqueue_log("[DUMP] 3秒後にQSO Oneの全UIA要素をスナップショット取得します...")
        self.root.after(3000, lambda: setattr(self.qso1, "dump_requested", True))

    def _refresh_com_ports(self):
        ports = [p.device for p in serial.tools.list_ports.comports()]
        self.combo_com["values"] = ports
        if not self.var_com.get() and ports:
            self.var_com.set(ports[0])

    def _refresh_audio_devices(self):
        devs = AudioVoxMonitor.list_input_devices()
        self.audio_devices = devs
        names = [f"[{idx}] {name}" for idx, name in devs]
        self.combo_audio["values"] = names
        saved_idx = int(self.config.get("audio_device_idx", 0))
        if names:
            match = [n for idx, n in zip([d[0] for d in devs], names) if idx == saved_idx]
            self.var_audio_dev.set(match[0] if match else names[0])

    def _get_selected_audio_idx(self) -> int:
        val = self.var_audio_dev.get()
        m = re.match(r"\[(\d+)\]", val)
        return int(m.group(1)) if m else 0

    def _start_selected_audio(self):
        if getattr(self, "audio_devices", None):
            self.audio.start(self._get_selected_audio_idx())

    def _apply_config_to_ui(self):
        self._refresh_com_ports()
        self._refresh_audio_devices()
        if self.config.get("com_port"):
            self.var_com.set(self.config["com_port"])
        self.var_freq.set(self.config.get("preset_freq", "145.50000"))
        self.var_mode.set(self.config.get("preset_mode", "FM"))
        self.var_trigger.set(self.config.get("trigger_mode", "CAT_SQL"))
        self.var_vox_th.set(self.config.get("vox_threshold", 12.0))
        self.var_ptt_method.set(self.config.get("ptt_method", "SPACE"))
        self.var_rx_kw.set(self.config.get("rx_keyword", "送信中"))
        self.var_own_call.set(self.config.get("own_callsign", ""))
        self.var_ignore_own.set(self.config.get("ignore_own_call", True))
        self.var_invert_sql.set(self.config.get("invert_sql", False))
        self.var_log_sql.set(self.config.get("log_sql_events", True))
        self.var_poll_smeter.set(self.config.get("poll_smeter", True))
        self.var_rf_hang.set(str(self.config.get("rf_hang_ms", 350)))
        self.var_voip_hang.set(str(self.config.get("voip_hang_ms", 350)))
        self.var_guard_ms.set(str(self.config.get("guard_ms", 600)))
        self.var_tot_sec.set(str(self.config.get("tot_sec", 120)))
        self.var_debug_uia.set(self.config.get("debug_uia", False))
        self._sync_ui_to_engine()

    def _sync_ui_to_engine(self):
        try:
            self.bridge.trigger_mode = self.var_trigger.get()
            self.bridge.vox_threshold = float(self.var_vox_th.get())
            self.bridge.rf_hang_ms = max(0, int(self.var_rf_hang.get() or 350))
            self.bridge.voip_hang_ms = max(0, int(self.var_voip_hang.get() or 350))
            self.bridge.guard_ms = max(100, int(self.var_guard_ms.get() or 600))
            self.bridge.tot_sec = max(10, int(self.var_tot_sec.get() or 120))
        except ValueError:
            pass

        self.rig.invert_sql = bool(self.var_invert_sql.get())
        self.rig.log_sql_events = bool(self.var_log_sql.get())
        self._poll_smeter_enabled = bool(self.var_poll_smeter.get())

        self.qso1.ptt_method = self.var_ptt_method.get()
        self.qso1.rx_keyword = self.var_rx_kw.get()
        self.qso1.own_callsign_override = self.var_own_call.get()
        self.qso1.ignore_own_callsign = bool(self.var_ignore_own.get())
        self.qso1.debug_uia = bool(self.var_debug_uia.get())

    def _toggle_com(self):
        if self.rig.connected:
            self.bridge.set_armed(False)
            self.btn_arm.config(text="BRIDGE START (ARM)", bg="#06d6a0")
            threading.Thread(target=self._stop_all_and_disconnect, daemon=True).start()
        else:
            port = self.var_com.get().strip()
            if not port:
                messagebox.showwarning("警告", "COMポートを選択してください。")
                return
            threading.Thread(target=self.rig.connect, args=(port,), daemon=True).start()

    def _stop_all_and_disconnect(self):
        self.qso1.ptt_off()
        self.rig.disconnect()
        self.enqueue_log("[CAT] 切断しました。")

    def _apply_rig_freq(self):
        if not self.rig.connected:
            messagebox.showwarning("警告", "先にCOMポートへ接続してください。")
            return
        try:
            freq = float(self.var_freq.get())
            if not (50.0 <= freq <= 1300.0):
                raise ValueError("周波数範囲外")
            mode = self.var_mode.get()
            threading.Thread(target=self.rig.set_freq_mode, args=(freq, mode), daemon=True).start()
        except Exception as e:
            messagebox.showerror("エラー", f"周波数の形式が不正です: {e}")

    def _toggle_arm(self):
        if not self.bridge.armed:
            self._sync_ui_to_engine()
            if self.bridge.trigger_mode != "AUDIO_VOX" and not self.rig.connected:
                messagebox.showwarning("未接続", "FT-736M の COM ポートを接続してください。")
                return
            if not self.qso1.get_status_copy()["attached"]:
                messagebox.showwarning("未検出", "QSO One が見つかりません。QSO One を起動してください。")
                return
            self.bridge.set_armed(True)
            self.btn_arm.config(text="BRIDGE STOP", bg="#ffb703")
        else:
            self.bridge.set_armed(False)
            self.btn_arm.config(text="BRIDGE START (ARM)", bg="#06d6a0")

    def _on_emergency_rx(self):
        self.bridge.set_armed(False)
        self.bridge.manual_rig_tx = False
        self.bridge.manual_qso1_tx = False
        self.btn_arm.config(text="BRIDGE START (ARM)", bg="#06d6a0")
        threading.Thread(target=lambda: [self.qso1.ptt_off(), self.rig.set_ptt(False)], daemon=True).start()
        self.enqueue_log("[EMERGENCY] 緊急ALL RXを実行し、ブリッジを停止しました。")

    def _manual_rig_ptt(self, down: bool):
        if not self.rig.connected:
            return
        self.bridge.manual_rig_tx = down
        threading.Thread(target=self.rig.set_ptt, args=(down,), daemon=True).start()

    def _manual_qso_ptt(self, down: bool):
        self._sync_ui_to_engine()
        self.bridge.manual_qso1_tx = down
        fn = self.qso1.ptt_on if down else self.qso1.ptt_off
        threading.Thread(target=fn, daemon=True).start()

    def _clear_log(self):
        self.txt_log.config(state="normal")
        self.txt_log.delete("1.0", tk.END)
        self.txt_log.config(state="disabled")

    def _uia_worker(self):
        ole32.CoInitialize(None)
        try:
            while self.running:
                try:
                    self.qso1.scan_once()
                except Exception as e:
                    self.enqueue_log(f"[UIA ERR] {e}")
                time.sleep(0.25)
        finally:
            ole32.CoUninitialize()

    def _bridge_worker(self):
        last_sql_poll = 0.0
        last_smtr_poll = 0.0
        while self.running:
            try:
                now = time.monotonic()
                sql_open = self.rig.sql_open
                if self.rig.connected and not self.rig.is_tx:
                    if now - last_sql_poll >= 0.15:
                        sql_open = self.rig.poll_squelch()
                        last_sql_poll = time.monotonic()
                    elif getattr(self, "_poll_smeter_enabled", True) and (now - last_smtr_poll >= 0.60):
                        self.rig.poll_smeter()
                        last_smtr_poll = time.monotonic()
                elif not self.rig.connected or self.rig.is_tx:
                    sql_open = False

                audio_lvl = self.audio.get_level()
                self.bridge.step(sql_open, audio_lvl)
            except Exception as e:
                self.enqueue_log(f"[WORKER ERR] {e}")

            time.sleep(0.03)

    def _ui_tick(self):
        if not self.running:
            return

        self._sync_ui_to_engine()

        st = self.bridge.state
        if st == BridgeEngine.STATE_DISABLED:
            self.lbl_state_banner.config(text="STATE: DISABLED (STANDBY)", fg="#ffd166")
        elif st == BridgeEngine.STATE_IDLE:
            self.lbl_state_banner.config(text="STATE: ARMED - LISTENING (IDLE)", fg="#06d6a0")
        elif st == BridgeEngine.STATE_RF_TO_VOIP:
            self.lbl_state_banner.config(text="STATE: RF -> VoIP (QSO One TX!)", fg="#ff4d6d")
        elif st == BridgeEngine.STATE_VOIP_TO_RF:
            self.lbl_state_banner.config(text="STATE: VoIP -> RF (FT-736M TX!)", fg="#ff4d6d")
        elif st == BridgeEngine.STATE_GUARD_WAIT:
            self.lbl_state_banner.config(text="STATE: GUARD WAIT (LOOP PROTECT)", fg="#4cc9f0")

        if self.rig.connected:
            self.lbl_rig_conn.config(
                text=f"CAT: ON ({self.rig.port} | OK:{self.rig.cat_ok_count} TO:{self.rig.cat_to_count})",
                foreground="#008800",
            )
            self.btn_com_conn.config(text="切断")
        else:
            self.lbl_rig_conn.config(text="CAT: DISCONNECTED", foreground="#cc3333")
            self.btn_com_conn.config(text="接続")

        if self.rig.is_tx:
            self.lbl_rig_ptt.config(text="PTT: TX (ON AIR)", foreground="#cc0000")
        else:
            self.lbl_rig_ptt.config(text="PTT: RX", foreground="#008800")

        self.lbl_sql.config(
            text="[ OPEN (BUSY) ]" if self.rig.sql_open else "[ CLOSE ]",
            foreground="#d97706" if self.rig.sql_open else "#444444",
        )
        s_pct, s_lbl = FT736Controller.s_val_to_label(self.rig.s_meter_val)
        self.pb_smeter["value"] = s_pct
        self.lbl_smeter.config(text=s_lbl)

        # ロック衝突のない安全なコピー参照
        q_snap = self.qso1.get_status_copy()
        q_att = q_snap["attached"]
        q_room = q_snap["room"]
        q_call = q_snap["rx_callsign"]
        q_rx = q_snap["is_receiving"]
        q_own = q_snap["own_call"]

        if q_att:
            own_txt = f" ({q_own})" if q_own else ""
            self.lbl_qso_attach.config(text=f"QSO One: 接続OK{own_txt}", foreground="#008800")
        else:
            self.lbl_qso_attach.config(text="QSO One: 未検出", foreground="#cc3333")

        self.lbl_qso_ptt.config(
            text="PTT: TX (ON AIR)" if self.qso1.is_tx else "PTT: RX",
            foreground="#cc0000" if self.qso1.is_tx else "#008800",
        )
        self.lbl_qso_room.config(text=f"Room: {q_room[:24]}")
        self.lbl_qso_rx.config(
            text=f"RX: {q_call}",
            foreground="#cc0000" if q_rx else "#333333",
        )

        self.pb_vox["value"] = self.audio.get_level()
        self.lbl_vox_th.config(text=f"{int(self.var_vox_th.get())}%")

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
        self.audio.stop()
        try:
            self.qso1.ptt_off()
        except Exception:
            pass
        self.rig.disconnect()
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = FunaBridgeGUI(root)
    root.mainloop()