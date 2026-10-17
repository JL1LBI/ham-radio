"""
====================================================================
 FUNA Amateur VoIP Transceiver Wrapper for DMR Master
 Fullscreen MS-DOS / vi Style Textual Edition (IU2EUG Appliance)
====================================================================
"""

import sys
import os
import re
import time
import glob
import json
import threading
import subprocess
import ctypes
from ctypes import wintypes
from datetime import datetime

import uiautomation as auto
from rich.markup import escape
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Header, Footer, Static, RichLog, DataTable, Input, Button
from textual.screen import ModalScreen
from textual.binding import Binding

# --- Windows Win32 API 定義 ---
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

VK_SPACE = 0x20
VK_MENU = 0x12  # Alt key
KEYEVENTF_KEYUP = 0x0002

WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_CLOSE = 0x0010
SW_SHOWNOACTIVATE = 4
SWP_NOSIZE = 0x0001
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
STILL_ACTIVE = 259
GA_ROOT = 2

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dmr_config.json")


def get_true_console_hwnd():
    """Windows 11 (Windows Terminal / conhost) に対応した真のトップレベルHWNDを取得"""
    hwnd = kernel32.GetConsoleWindow()
    if hwnd:
        root_hwnd = user32.GetAncestor(hwnd, GA_ROOT)
        return root_hwnd if root_hwnd else hwnd
    return None


def force_activate_window(hwnd):
    """Windowsのフォーカス制限を100%突破して強制的に最前面アクティブ化する（Altハック）"""
    if not hwnd or not user32.IsWindow(hwnd):
        return
    try:
        # 1. 仮想Altキーの打鍵（OSのフォアグラウンドロックを解除するWin32の定石）
        user32.keybd_event(VK_MENU, 0, 0, 0)
        user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)

        # 2. スレッド入力のアタッチ
        fg_hwnd = user32.GetForegroundWindow()
        fg_thread = user32.GetWindowThreadProcessId(fg_hwnd, None)
        cur_thread = kernel32.GetCurrentThreadId()

        if fg_thread != cur_thread:
            user32.AttachThreadInput(cur_thread, fg_thread, True)
            user32.SetForegroundWindow(hwnd)
            user32.BringWindowToTop(hwnd)
            user32.AttachThreadInput(cur_thread, fg_thread, False)
        else:
            user32.SetForegroundWindow(hwnd)
            user32.BringWindowToTop(hwnd)
    except Exception:
        pass


# ====================================================================
#  DMR Master 制御ブリッジ (バックエンドエンジン)
# ====================================================================
class DMRMasterBridge:
    def __init__(self, console_hwnd):
        self.console_hwnd = console_hwnd
        self.window = None
        self.hwnd = None
        self.pid = None
        self.ptt_button = None
        
        self.lock = threading.RLock()
        self.running = True

        self.active_tg = "NOT CONNECTED"
        self.packets_quality = "LOSS 0.0% · ISSUES 0"
        self.loss_percent = 0.0
        self.ptt_status = "STANDBY"
        self.is_tx = False

        self.rx_callsign = "[ NO ACTIVE CALL ]"
        self.rx_op_name = "-------"
        self.rx_dest_tg = "—"
        self.rx_state = "STANDBY MONITORING"
        self.last_raw_call = ""

        self.mic_devices = []
        self.selected_mic_idx = 0
        self.output_devices = []
        self.selected_out_idx = 0

        self.agc_enabled = True
        self.limiter_enabled = True
        self.noise_gate_enabled = False

        self.tg_list = [
            {"id": "TG 91",  "name": "World-wide",     "region": "World"},
            {"id": "TG 208", "name": "France",         "region": "BrandMeister"},
            {"id": "TG 440", "name": "Japan",          "region": "BrandMeister"},
            {"id": "PC 9990","name": "Parrot (global)","region": "Private audio test"},
            {"id": "TG 1",   "name": "Local",          "region": "Local"},
            {"id": "TG 2",   "name": "Cluster",        "region": "BrandMeister"},
            {"id": "TG 8",   "name": "Regional",       "region": "BrandMeister"},
            {"id": "TG 9",   "name": "Local",          "region": "Local"},
        ]
        self.new_logs = ["[INIT] FUNA Appliance System Booting..."]

    def log(self, msg: str):
        with self.lock:
            self.new_logs.append(msg)

    def save_detected_path(self, exe_path):
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump({"dmr_master_exe": exe_path}, f, indent=2)
            self.log(f"Learned DMR Master path: {os.path.basename(exe_path)}")
        except Exception:
            pass

    def load_saved_path(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    p = data.get("dmr_master_exe")
                    if p and os.path.exists(p):
                        return p
            except Exception:
                pass
        return None

    def find_executable(self):
        saved = self.load_saved_path()
        if saved:
            return saved

        patterns = [
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "*DMR*Master*.exe"),
            os.path.expandvars(r"%USERPROFILE%\Downloads\*DMR*Master*.exe"),
            os.path.expandvars(r"%USERPROFILE%\Desktop\*DMR*Master*.exe"),
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\*DMR*Master*\*DMR*Master*.exe"),
            os.path.expandvars(r"%ProgramFiles%\*DMR*Master*\*DMR*Master*.exe"),
            os.path.expandvars(r"%ProgramFiles(x86)%\*DMR*Master*\*DMR*Master*.exe"),
            os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs\**\*DMR*.lnk"),
        ]
        for pat in patterns:
            matches = glob.glob(pat, recursive=True)
            if matches:
                return matches[0]
        return None

    def ensure_dmr_master_running(self):
        win = self.find_true_dmr_master()
        if win:
            self.log("DMR Master already running.")
            self._learn_path_from_window(win)
            return True

        exe_path = self.find_executable()
        if exe_path:
            self.log(f"Spawning DMR Master: {os.path.basename(exe_path)}")
            try:
                if exe_path.endswith(".lnk"):
                    os.startfile(exe_path)
                else:
                    subprocess.Popen([exe_path], cwd=os.path.dirname(exe_path))
            except Exception as e:
                self.log(f"Launch failed: {e}")
        else:
            self.log("Waiting for DMR Master process...")

        for _ in range(30):
            time.sleep(0.5)
            win = self.find_true_dmr_master()
            if win:
                self.log("DMR Master process captured!")
                self._learn_path_from_window(win)
                return True
        return False

    def _learn_path_from_window(self, win):
        try:
            self.pid = win.ProcessId
            h_proc = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, self.pid)
            if h_proc:
                buf = ctypes.create_unicode_buffer(1024)
                size = wintypes.DWORD(len(buf))
                if kernel32.QueryFullProcessImageNameW(h_proc, 0, buf, ctypes.byref(size)):
                    self.save_detected_path(buf.value)
                kernel32.CloseHandle(h_proc)
        except Exception:
            pass

    def find_true_dmr_master(self):
        root = auto.GetRootControl()
        for win in root.GetChildren():
            if win.ControlTypeName == "WindowControl":
                if win.ClassName == "Chrome_WidgetWin_1":
                    continue
                name = win.Name or ""
                if "DMR Master" in name and "Google" not in name and "Edge" not in name:
                    if win.ButtonControl(searchDepth=3, AutomationId="PttButton").Exists(0.05) or \
                       win.DataGridControl(searchDepth=6, AutomationId="TalkgroupListBox").Exists(0.05):
                        self.pid = win.ProcessId
                        return win
        return None

    def switch_to_radio_tab(self):
        try:
            radio_btn = self.window.ButtonControl(searchDepth=4, AutomationId="RadioNavButton")
            if radio_btn.Exists(0.5):
                inv = radio_btn.GetInvokePattern()
                if inv:
                    inv.Invoke()
                    self.log("Workspace initialized -> RADIO workspace.")
                    return
            
            tab = self.window.TabItemControl(searchDepth=4, AutomationId="RadioTabItem")
            if tab.Exists(0.5):
                sel = tab.GetSelectionItemPattern()
                if sel:
                    sel.Select()
                    self.log("Selected RadioTabItem.")
        except Exception as e:
            self.log(f"Tab init error: {e}")

    def attach_and_stealth(self):
        self.window = self.find_true_dmr_master()
        if not self.window:
            return False

        self.hwnd = self.window.NativeWindowHandle
        self.pid = self.window.ProcessId
        if self.hwnd:
            # アクティブ化させずに通常表示（フォーカスを奪わせない！）
            user32.ShowWindow(self.hwnd, SW_SHOWNOACTIVATE)
            time.sleep(0.1)

            user32.SetWindowPos(
                self.hwnd, 0, 10000, 10000, 0, 0, 
                SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE
            )
            
            self.ptt_button = self.window.ButtonControl(searchDepth=4, AutomationId="PttButton")
            self.log(f"DMR Master stealthed (HWND: {hex(self.hwnd)}).")

            # 初期化: 必ず「Radio」タブを選択
            self.switch_to_radio_tab()
            
            # 強力にコンソールへフォーカスを引き戻す
            self.reclaim_focus()
            
            threading.Thread(target=self.scan_audio_devices, daemon=True).start()
            return True
        return False

    def reclaim_focus(self):
        """真のコンソールHWNDへフォーカスを強制奪還"""
        if self.console_hwnd:
            force_activate_window(self.console_hwnd)

    def terminate_dmr_master(self):
        if self.hwnd and user32.IsWindow(self.hwnd):
            user32.PostMessageW(self.hwnd, WM_CLOSE, 0, 0)
            if self.pid:
                for _ in range(20):
                    time.sleep(0.1)
                    h_proc = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, self.pid)
                    if not h_proc:
                        return
                    code = wintypes.DWORD()
                    kernel32.GetExitCodeProcess(h_proc, ctypes.byref(code))
                    kernel32.CloseHandle(h_proc)
                    if code.value != STILL_ACTIVE:
                        return
                try:
                    subprocess.run(f"taskkill /PID {self.pid} /F", shell=True, capture_output=True)
                except Exception:
                    pass

    def _parse_device_name(self, raw_str):
        m = re.search(r"Name\s*=\s*([^,}]+)", raw_str)
        if m:
            return m.group(1).strip()
        return raw_str[:35]

    def scan_audio_devices(self):
        try:
            mic_cb = self.window.ComboBoxControl(searchDepth=5, AutomationId="MicrophoneComboBox")
            if mic_cb.Exists(1.0):
                m_items = []
                for item in mic_cb.GetChildren():
                    if item.ControlTypeName == "ListItemControl":
                        clean_name = self._parse_device_name(item.Name)
                        m_items.append({"name": clean_name, "element": item})
                if m_items:
                    with self.lock:
                        self.mic_devices = m_items

            out_cb = self.window.ComboBoxControl(searchDepth=5, AutomationId="AudioOutputComboBox")
            if out_cb.Exists(1.0):
                o_items = []
                for item in out_cb.GetChildren():
                    if item.ControlTypeName == "ListItemControl":
                        clean_name = self._parse_device_name(item.Name)
                        o_items.append({"name": clean_name, "element": item})
                if o_items:
                    with self.lock:
                        self.output_devices = o_items

            self.log(f"Audio Endpoints: {len(self.mic_devices)} In / {len(self.output_devices)} Out ready.")
        except Exception as e:
            self.log(f"Audio scan error: {e}")

    def select_audio_device(self, is_mic: bool, index: int):
        def _worker():
            try:
                target_list = self.mic_devices if is_mic else self.output_devices
                if index < 0 or index >= len(target_list):
                    return
                dev = target_list[index]
                
                sel = dev["element"].GetSelectionItemPattern()
                if sel:
                    sel.Select()
                    dev_type = "MIC" if is_mic else "OUTPUT"
                    self.log(f"Routing -> {dev_type}: {dev['name']}")
                else:
                    cb_id = "MicrophoneComboBox" if is_mic else "AudioOutputComboBox"
                    cb = self.window.ComboBoxControl(searchDepth=5, AutomationId=cb_id)
                    exp = cb.GetExpandCollapsePattern()
                    if exp:
                        exp.Expand()
                        time.sleep(0.1)
                        dev["element"].Click(simulateMove=False)
                        exp.Collapse()
            except Exception as e:
                self.log(f"Device error: {e}")
            finally:
                self.reclaim_focus()

        threading.Thread(target=_worker, daemon=True).start()

    def toggle_dsp(self, dsp_name: str):
        def _worker():
            id_map = {
                "AGC": "AgcCheckBox",
                "LIMITER": "LimiterCheckBox",
                "NOISE_GATE": "NoiseGateCheckBox"
            }
            chk_id = id_map.get(dsp_name)
            if not chk_id:
                return
            try:
                chk = self.window.CheckBoxControl(searchDepth=5, AutomationId=chk_id)
                if chk.Exists(0.5):
                    tog = chk.GetTogglePattern()
                    if tog:
                        tog.Toggle()
                    else:
                        inv = chk.GetInvokePattern()
                        if inv:
                            inv.Invoke()

                    if dsp_name == "AGC":
                        self.agc_enabled = not self.agc_enabled
                    elif dsp_name == "LIMITER":
                        self.limiter_enabled = not self.limiter_enabled
                    elif dsp_name == "NOISE_GATE":
                        self.noise_gate_enabled = not self.noise_gate_enabled
                    
                    self.log(f"DSP: {dsp_name} toggled.")
            except Exception as e:
                self.log(f"DSP error: {e}")
            finally:
                self.reclaim_focus()

        threading.Thread(target=_worker, daemon=True).start()

    def background_monitor_step(self):
        try:
            if self.window and self.window.Exists(0):
                act = self.window.TextControl(searchDepth=3, AutomationId="ActiveTalkgroupText")
                if act.Exists(0) and act.Name:
                    with self.lock:
                        self.active_tg = act.Name.strip()

                pkt = self.window.TextControl(searchDepth=3, AutomationId="PacketsQualityText")
                if pkt.Exists(0) and pkt.Name:
                    val = pkt.Name.strip()
                    with self.lock:
                        self.packets_quality = val
                        m = re.search(r"LOSS\s+([\d\.]+)%", val)
                        if m:
                            self.loss_percent = float(m.group(1))

                ptt = self.window.TextControl(searchDepth=3, AutomationId="PttStatusText")
                if ptt.Exists(0) and ptt.Name:
                    with self.lock:
                        self.ptt_status = ptt.Name.strip()

                self._parse_now_on_air_deep()
        except Exception:
            pass

    def _parse_now_on_air_deep(self):
        try:
            lbl = self.window.TextControl(searchDepth=10, Name="NOW ON AIR")
            if not lbl.Exists(0):
                return

            banner = lbl.GetParentControl()
            if not banner:
                return

            texts = []
            for c, _ in auto.WalkControl(banner, maxDepth=4):
                if c.ControlTypeName == "TextControl" and c.Name:
                    val = c.Name.strip()
                    if val and val not in texts:
                        texts.append(val)

            raw_call = ""
            raw_desc = ""
            dest_val = ""

            for i, t in enumerate(texts):
                if t == "NOW ON AIR" and i + 1 < len(texts):
                    raw_call = texts[i + 1]
                    if i + 2 < len(texts) and texts[i + 2] != "Destination":
                        raw_desc = texts[i + 2]
                if t == "Destination" and i + 1 < len(texts):
                    dest_val = texts[i + 1]

            rx_log_msg = None

            with self.lock:
                if raw_call and raw_call != "NO ACTIVE CALL":
                    self.rx_state = "VOICE CALL ACTIVE"
                    clean_str = raw_call.replace("CALL:", "").strip()
                    parts = re.split(r"[\s\-\/·]+", clean_str, maxsplit=1)
                    
                    self.rx_callsign = parts[0].strip()
                    if len(parts) >= 2:
                        self.rx_op_name = parts[1].strip()
                    elif raw_desc and raw_desc != "MONITORING ACTIVE DESTINATION":
                        self.rx_op_name = raw_desc
                    else:
                        self.rx_op_name = "-------"

                    if raw_call != self.last_raw_call:
                        self.last_raw_call = raw_call
                        rx_log_msg = f"[bold yellow]RX Call:[/] [bold white]{self.rx_callsign}[/] ({self.rx_op_name})"
                else:
                    self.rx_callsign = "[ NO ACTIVE CALL ]"
                    self.rx_op_name = "-------"
                    self.rx_state = "STANDBY MONITORING"
                    self.last_raw_call = ""

                if dest_val and dest_val != "—":
                    self.rx_dest_tg = dest_val
                else:
                    self.rx_dest_tg = self.active_tg

            if rx_log_msg:
                self.log(rx_log_msg)

        except Exception:
            pass

    def sync_talkgroups(self):
        try:
            grid = self.window.DataGridControl(searchDepth=8, AutomationId="TalkgroupListBox")
            if not grid.Exists(1.0):
                return
            
            items = []
            for item in grid.GetChildren():
                if item.ControlTypeName == "DataItemControl":
                    raw_texts = [
                        c.Name.strip() for c in item.GetChildren() 
                        if c.ControlTypeName == "TextControl" and c.Name and c.Name.strip() not in ("★", "☆", "")
                    ]
                    
                    tg_id = ""
                    tg_name = ""
                    tg_region = ""

                    for t in raw_texts:
                        if (t.startswith("TG") or t.startswith("PC")) and not tg_id:
                            tg_id = t
                        elif tg_id and not tg_name:
                            tg_name = t
                        elif tg_id and tg_name and not tg_region:
                            tg_region = t

                    if not tg_id and item.Name and "·" in item.Name:
                        parts = [p.strip() for p in item.Name.split("·")]
                        if len(parts) >= 2:
                            tg_id = parts[0]
                            tg_name = parts[1]

                    if tg_id:
                        items.append({
                            "element": item,
                            "id": tg_id,
                            "name": tg_name if tg_name else "Unknown",
                            "region": tg_region if tg_region else "BrandMeister"
                        })

            if items:
                with self.lock:
                    self.tg_list = items
                self.log(f"Synced {len(items)} TGs cleanly.")
        except Exception as e:
            self.log(f"Sync error: {e}")

    def connect_talkgroup(self, index):
        def _worker():
            with self.lock:
                if index < 0 or index >= len(self.tg_list):
                    return
                target = self.tg_list[index]

            self.log(f"Connecting: [{target['id']}] {target['name']}...")
            numbers = re.findall(r'\d+', target['id'])
            tg_num = numbers[0] if numbers else ""

            if not tg_num:
                return

            self._direct_connect_internal(tg_num, target)
            self.reclaim_focus()

        threading.Thread(target=_worker, daemon=True).start()

    def _direct_connect_internal(self, tg_number, target=None):
        try:
            edit = self.window.EditControl(searchDepth=6, AutomationId="ManualTalkgroupTextBox")
            
            if not edit.Exists(0.05):
                toggle = self.window.ButtonControl(searchDepth=6, AutomationId="DirectTalkgroupToggleButton")
                if toggle.Exists(0.3):
                    inv = toggle.GetInvokePattern()
                    if inv:
                        inv.Invoke()
                time.sleep(0.08)

            edit = self.window.EditControl(searchDepth=6, AutomationId="ManualTalkgroupTextBox")
            if edit.Exists(0.3):
                val = edit.GetValuePattern()
                if val:
                    val.SetValue(str(tg_number))
                
                conn_btn = self.window.ButtonControl(searchDepth=6, Name="CONNECT TG")
                if conn_btn.Exists(0.3):
                    inv_btn = conn_btn.GetInvokePattern()
                    if inv_btn:
                        inv_btn.Invoke()
                        tg_label = target['id'] if target else f"TG {tg_number}"
                        self.log(f"[bold green]SUCCESS:[/] Connected to {tg_label}")
                        return

            if target and "element" in target:
                sel = target["element"].GetSelectionItemPattern()
                if sel:
                    sel.Select()
                conn_main = self.window.ButtonControl(searchDepth=6, AutomationId="SelectedTalkgroupConnectButton")
                if conn_main.Exists(0.2):
                    inv_m = conn_main.GetInvokePattern()
                    if inv_m:
                        inv_m.Invoke()
                        self.log(f"[bold green]SUCCESS:[/] Connected to {target['id']}")

        except Exception as e:
            self.log(f"Connect error: {e}")
        finally:
            self.reclaim_focus()

    def direct_connect(self, tg_number):
        threading.Thread(target=lambda: self._direct_connect_internal(tg_number), daemon=True).start()

    def set_ptt(self, transmit: bool):
        if self.is_tx == transmit:
            return
        self.is_tx = transmit

        if self.hwnd:
            msg = WM_KEYDOWN if transmit else WM_KEYUP
            lparam = 0x00390001 if transmit else 0xC0390001
            user32.PostMessageW(self.hwnd, msg, VK_SPACE, lparam)

            try:
                if self.ptt_button and self.ptt_button.Exists(0):
                    inv = self.ptt_button.GetInvokePattern()
                    if inv:
                        inv.Invoke()
            except Exception:
                pass

        self.log("[bold red]>>> PTT ACTIVE (TX ON AIR)[/]" if transmit else "[bold green]<<< PTT RELEASED (RX STANDBY)[/]")
        self.reclaim_focus()


# ====================================================================
#  MS-DOS スタイリング (TCSS)
# ====================================================================
DOS_STYLE = """
Screen {
    background: #000080;
    color: #ffffff;
}

#title-bar {
    dock: top;
    height: 1;
    background: #00aaaa;
    color: #000000;
    text-align: center;
    text-style: bold;
}

.panel {
    border: heavy #ffffff;
    background: #000080;
    padding: 0 1;
    margin: 0;
}

.panel-title {
    color: #ffff00;
    text-style: bold;
}

#top-row {
    height: 10;
}

#trx-panel {
    width: 50%;
    border: heavy #ffffff;
}

#trx-panel.listening {
    border: heavy #00ff00;
}

#trx-panel.tx {
    border: heavy #ff5555;
    background: #440000;
}

#station-panel {
    width: 50%;
    border: heavy #ffffff;
}

#vfo-panel {
    height: 12;
    border: heavy #ffffff;
}

#vfo-table {
    background: #000080;
    color: #ffffff;
    height: 1fr;
}

#log-panel {
    height: 1fr;
    border: heavy #ffffff;
}

RichLog {
    background: #000055;
    color: #00ffff;
}

Footer {
    background: #00aaaa;
    color: #000000;
}

AudioSetupModal, DirectTGModal {
    align: center middle;
}

.modal-dialog {
    width: 68;
    height: auto;
    border: heavy #ffff00;
    background: #0000aa;
    padding: 1 2;
}

.modal-title {
    color: #ffff00;
    text-align: center;
    text-style: bold;
    margin-bottom: 1;
}

.dialog-btn {
    margin: 1 1;
    background: #00aaaa;
    color: #000000;
}
"""


# ====================================================================
#  DIRECT TG 入力モーダルダイアログ
# ====================================================================
class DirectTGModal(ModalScreen):
    BINDINGS = [
        Binding("escape", "cancel", "Cancel", priority=True),
    ]

    def __init__(self, initial_char=""):
        super().__init__()
        self.initial_char = initial_char

    def compose(self) -> ComposeResult:
        with Vertical(classes="modal-dialog"):
            yield Static("■ DIRECT TALKGROUP ENTRY ■", classes="modal-title")
            yield Static("Enter Talkgroup Number (e.g. 440, 91, 9990):")
            yield Input(value=self.initial_char, id="tg-input", placeholder="TG Number...")
            with Horizontal():
                yield Button("Connect", id="btn-ok", classes="dialog-btn")
                yield Button("Cancel", id="btn-cancel", classes="dialog-btn")

    def on_mount(self) -> None:
        inp = self.query_one("#tg-input", Input)
        inp.focus()
        if self.initial_char:
            inp.cursor_position = len(self.initial_char)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value.strip())

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-ok":
            val = self.query_one("#tg-input", Input).value.strip()
            self.dismiss(val)
        else:
            self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)


# ====================================================================
#  AUDIO & DSP SETUP モーダルダイアログ
# ====================================================================
class AudioSetupModal(ModalScreen):
    BINDINGS = [
        Binding("escape", "cancel", "Back", priority=True),
    ]

    def __init__(self, bridge: DMRMasterBridge):
        super().__init__()
        self.bridge = bridge

    def compose(self) -> ComposeResult:
        with Vertical(classes="modal-dialog"):
            yield Static("■ [ AUDIO ROUTING & DSP SETUP MENU ] ■", classes="modal-title")
            yield Static("", id="audio-settings-content")
            with Horizontal():
                yield Button("[1] Mic Toggle", id="btn-mic", classes="dialog-btn")
                yield Button("[2] Out Toggle", id="btn-out", classes="dialog-btn")
                yield Button("[3] AGC", id="btn-agc", classes="dialog-btn")
                yield Button("[4] Limiter", id="btn-lim", classes="dialog-btn")
            yield Button("Return to VFO (ESC)", id="btn-close", classes="dialog-btn")

    def on_mount(self) -> None:
        self._refresh_content()

    def _refresh_content(self) -> None:
        with self.bridge.lock:
            mics = self.bridge.mic_devices
            outs = self.bridge.output_devices
            cur_mic = mics[self.bridge.selected_mic_idx]["name"] if mics else "Windows Default Mic"
            cur_out = outs[self.bridge.selected_out_idx]["name"] if outs else "Windows Default Output"
            agc = "[X] ON" if self.bridge.agc_enabled else "[ ] OFF"
            lim = "[X] ON" if self.bridge.limiter_enabled else "[ ] OFF"
            gate = "[X] ON (-50dB)" if self.bridge.noise_gate_enabled else "[ ] OFF"

        text = (
            f" 1. MIC INPUT   : [cyan]{escape(cur_mic[:36])}[/]\n"
            f" 2. AUDIO OUTPUT: [cyan]{escape(cur_out[:36])}[/]\n"
            f" 3. AGC         : [yellow]{escape(agc)}[/]\n"
            f" 4. LIMITER     : [yellow]{escape(lim)}[/]\n"
            f" 5. NOISE GATE  : [white]{escape(gate)}[/]\n"
        )
        self.query_one("#audio-settings-content", Static).update(text)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "btn-mic":
            if self.bridge.mic_devices:
                self.bridge.selected_mic_idx = (self.bridge.selected_mic_idx + 1) % len(self.bridge.mic_devices)
                self.bridge.select_audio_device(True, self.bridge.selected_mic_idx)
        elif bid == "btn-out":
            if self.bridge.output_devices:
                self.bridge.selected_out_idx = (self.bridge.selected_out_idx + 1) % len(self.bridge.output_devices)
                self.bridge.select_audio_device(False, self.bridge.selected_out_idx)
        elif bid == "btn-agc":
            self.bridge.toggle_dsp("AGC")
        elif bid == "btn-lim":
            self.bridge.toggle_dsp("LIMITER")
        elif bid == "btn-close":
            self.dismiss(None)
            return

        time.sleep(0.05)
        self._refresh_content()

    def action_cancel(self) -> None:
        self.dismiss(None)


# ====================================================================
#  メイン Textual アプリケーション
# ====================================================================
class FunaDMRApp(App):
    CSS = DOS_STYLE
    TITLE = "FUNA Amateur VoIP Transceiver [IU2EUG Appliance Node]"

    BINDINGS = [
        Binding("space", "ptt", "PTT (Hold)", priority=True),
        Binding("t", "open_direct_tg", "Direct TG"),
        Binding("m", "open_audio_menu", "Audio Menu"),
        Binding("s", "sync_tg", "Sync VFO"),
        Binding("c", "clear_log", "Clear Log"),
        Binding("q", "quit", "Quit/Poweroff"),
    ]

    def __init__(self, bridge: DMRMasterBridge):
        super().__init__()
        self.bridge = bridge
        self.is_app_running = True
        self.table_items = []

    def compose(self) -> ComposeResult:
        yield Static(" FUNA Amateur VoIP Transceiver [IU2EUG Core / Textual Edition] ", id="title-bar")

        with Vertical():
            # 上段: TRXステータス ＆ 相手局/QSO情報
            with Horizontal(id="top-row"):
                with Vertical(id="trx-panel", classes="panel"):
                    yield Static("■ [ TRX STATUS & METERS ]", classes="panel-title")
                    yield Static("", id="trx-content")

                with Vertical(id="station-panel", classes="panel"):
                    yield Static("■ [ NOW ON AIR / RX TRAFFIC ]", classes="panel-title")
                    yield Static("", id="station-content")

            # 中段: VFO チャンネル一覧 (DataTable)
            with Vertical(id="vfo-panel", classes="panel"):
                yield Static("■ [ TALKGROUPS / VFO CHANNELS ] (Up/Down: Select, Enter: Connect)", classes="panel-title")
                yield DataTable(id="vfo-table", cursor_type="row", zebra_stripes=False)

            # 下段: 通信アクティビティログ
            with Vertical(id="log-panel", classes="panel"):
                yield Static("■ [ APPLIANCE ACTIVITY LOG ]", classes="panel-title")
                yield RichLog(id="activity-log", wrap=True, highlight=False, markup=True)

        yield Footer()

    def on_mount(self) -> None:
        self.log_widget = self.query_one("#activity-log", RichLog)

        # 1. VFOテーブル初期化 & フォーカス吸着！
        table = self.query_one("#vfo-table", DataTable)
        table.add_columns("ID", "NAME", "ROUTE / NETWORK")
        self._reload_vfo_table()
        table.focus()  # ← 起動時にVFOテーブルへ入力フォーカスを確実に吸着

        # 2. バックグラウンドワーカー群の開始
        threading.Thread(target=self._monitor_worker, daemon=True).start()
        threading.Thread(target=self._ptt_worker, daemon=True).start()

        # 3. 起動直後のフォーカス完全固定シーケンス
        # 起動直後(0.1s, 0.4s, 0.8s)に強力なAltハックでコンソールを最前面に吸着
        self.set_timer(0.1, self._force_focus)
        self.set_timer(0.4, self._force_focus)
        self.set_timer(0.8, self._force_focus)

        # 4. 常駐フォーカス維持スレッド
        def _focus_guard():
            while self.is_app_running:
                force_activate_window(self.bridge.console_hwnd)
                time.sleep(0.5)
        threading.Thread(target=_focus_guard, daemon=True).start()

        # 5. UI更新ループ
        self.set_interval(0.05, self._update_ui)

    def _force_focus(self) -> None:
        force_activate_window(self.bridge.console_hwnd)
        try:
            self.query_one("#vfo-table", DataTable).focus()
        except Exception:
            pass

    def log_msg(self, text: str) -> None:
        now = datetime.now().strftime("%H:%M:%S")
        self.log_widget.write(f"[{now}] {text}")

    def _render_smeter(self, loss_pct: float, width=18) -> str:
        quality = max(0.0, 1.0 - (loss_pct / 10.0))
        filled = int(round(quality * width))
        empty = width - filled
        return "█" * filled + "░" * empty

    def _reload_vfo_table(self) -> None:
        table = self.query_one("#vfo-table", DataTable)
        table.clear()
        with self.bridge.lock:
            self.table_items = list(self.bridge.tg_list)

        for idx, tg in enumerate(self.table_items):
            table.add_row(tg["id"], tg["name"], tg["region"], key=str(idx))

    def _monitor_worker(self):
        self.bridge.sync_talkgroups()
        while self.is_app_running:
            self.bridge.background_monitor_step()
            time.sleep(0.2)

    def _ptt_worker(self):
        was_down = False
        while self.is_app_running:
            is_down = bool(user32.GetAsyncKeyState(VK_SPACE) & 0x8000)
            if is_down and not was_down:
                self.bridge.set_ptt(True)
                was_down = True
            elif not is_down and was_down:
                self.bridge.set_ptt(False)
                was_down = False
            time.sleep(0.02)

    def _update_ui(self) -> None:
        with self.bridge.lock:
            if self.bridge.new_logs:
                for l in self.bridge.new_logs:
                    self.log_msg(l)
                self.bridge.new_logs.clear()

            act_tg = self.bridge.active_tg
            ptt_st = self.bridge.ptt_status
            is_tx = self.bridge.is_tx
            loss = self.bridge.loss_percent
            pkt_txt = self.bridge.packets_quality
            call = self.bridge.rx_callsign
            op_name = self.bridge.rx_op_name
            dest_tg = self.bridge.rx_dest_tg
            rx_st = self.bridge.rx_state
            cur_tgs = list(self.bridge.tg_list)

        trx_panel = self.query_one("#trx-panel")
        trx_panel.remove_class("listening", "tx")

        if is_tx:
            trx_panel.add_class("tx")
            ptt_display = "[bold white on red] <<< TRANSMITTING (TX ON AIR) >>> [/]"
        elif "VOICE" in rx_st:
            trx_panel.add_class("listening")
            ptt_display = "[bold green]<<< RECEIVING (VOICE ACTIVE) >>>[/]"
        else:
            ptt_display = f"[cyan][ STANDBY (RX MONITORING) ][/]"

        s_bar = self._render_smeter(loss, width=18)
        trx_text = (
            f" State  : {ptt_display}\n"
            f" Target : [bold yellow]{escape(act_tg)}[/]\n"
            f" S-MTR  : [bold green][{s_bar}][/] [yellow]Loss:{loss:.1f}%[/]\n"
            f" Link   : [white]{escape(pkt_txt)}[/]\n"
            f" PTT    : [white]{escape(ptt_st)}[/]"
        )
        self.query_one("#trx-content", Static).update(trx_text)

        if call != "[ NO ACTIVE CALL ]":
            call_disp = f"[bold green]{escape(call)}[/]"
            name_disp = f"[bold white]{escape(op_name)}[/]"
            st_disp = "[bold red]VOICE CALL ACTIVE[/]"
        else:
            call_disp = "[dim][ NO ACTIVE CALL ][/dim]"
            name_disp = "[dim]-------[/dim]"
            st_disp = "[dim]STANDBY MONITORING[/dim]"

        station_text = (
            f" CALLSIGN : {call_disp}\n"
            f" OP NAME  : {name_disp}\n"
            f" TARGET TG: [bold cyan]{escape(dest_tg)}[/]\n"
            f" STATUS   : {st_disp}"
        )
        self.query_one("#station-content", Static).update(station_text)

        if len(cur_tgs) != len(self.table_items):
            self._reload_vfo_table()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        idx = int(event.row_key.value)
        self.bridge.connect_talkgroup(idx)

    def action_ptt(self) -> None:
        pass

    def action_open_direct_tg(self) -> None:
        def _on_result(tg_num):
            if tg_num:
                self.bridge.direct_connect(tg_num)
        self.push_screen(DirectTGModal(), _on_result)

    def action_open_audio_menu(self) -> None:
        self.bridge.scan_audio_devices()
        self.push_screen(AudioSetupModal(self.bridge))

    def action_sync_tg(self) -> None:
        threading.Thread(target=self.bridge.sync_talkgroups, daemon=True).start()
        self.log_msg("Synchronizing Talkgroups from DMR Master...")

    def action_clear_log(self) -> None:
        self.log_widget.clear()

    def on_key(self, event) -> None:
        if event.character and event.character.isdigit():
            def _on_result(tg_num):
                if tg_num:
                    self.bridge.direct_connect(tg_num)
            self.push_screen(DirectTGModal(initial_char=event.character), _on_result)

    def action_quit(self) -> None:
        self.is_app_running = False
        self.log_msg("[bold red]Shutting down DMR Master and appliance node...[/]")
        self.bridge.terminate_dmr_master()
        self.exit()


# ====================================================================
#  メインエントリポイント
# ====================================================================
def main():
    # Windows 11の真のトップレベルコンソールHWNDを取得
    console_hwnd = get_true_console_hwnd()

    bridge = DMRMasterBridge(console_hwnd)

    print("==================================================")
    print(" FUNA Amateur VoIP Transceiver [IU2EUG Appliance]")
    print(" Fullscreen MS-DOS Textual Edition")
    print("==================================================")
    print("1. Checking DMR Master status...")

    if not bridge.ensure_dmr_master_running():
        print("[ERROR] Could not start or find DMR Master application.")
        input("Press Enter to exit...")
        return

    print("2. Moving DMR Master to Off-screen (Stealth mode)...")
    if not bridge.attach_and_stealth():
        print("[ERROR] Failed to hook DMR Master controls.")
        input("Press Enter to exit...")
        return

    app = FunaDMRApp(bridge)
    try:
        app.run()
    finally:
        bridge.running = False
        bridge.terminate_dmr_master()
        print("\nAppliance wrapper terminated. DMR Master safely closed. 73!")


if __name__ == "__main__":
    main()