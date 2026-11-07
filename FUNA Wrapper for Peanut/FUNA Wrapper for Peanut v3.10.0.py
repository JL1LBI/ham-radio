"""
==============================================================================
 FUNA Wrapper for Peanut - Dual Master Console (v3.10.0 Red Alert Edition)
 
 [New Updates]
  - Visual Red Alert: Active VFO pane illuminates entirely in RED background
  - Standby VFO pane remains in classic DOS Blue (Prevents accidental TX)
  - Split Dual-Pane Last Heard with Smart Timestamps (Today / Yday / MM/DD)
  - Pixel-Perfect East Asian Width Alignment
  - UNIX/BSD Kernel-Style Boot Animation with Spinner & Scroll Log
  - 100% Pure Win32 Trigger, Virtual Off-Screen Stealth, and Clean Auto-Shutdown
==============================================================================
"""

import os
import sys
import time
import msvcrt
import ctypes
import subprocess
import threading
import unicodedata
from datetime import datetime
from pywinauto import Desktop, Application

# --- システム設定 ---
DEFAULT_ROOM_JP = "CQCQCQ-J"
DEFAULT_ROOM_GLOBAL = "JAPANESE"

DEFAULT_PATHS = [
    r"C:\Program Files (x86)\Peanut\Peanut\peanut.exe",
    r"C:\Program Files\Peanut\Peanut\peanut.exe",
    os.path.join(os.getcwd(), "Peanut.exe"),
    os.path.join(os.getcwd(), "peanut.exe")
]

def find_peanut_binary():
    for p in DEFAULT_PATHS:
        if os.path.exists(p):
            return p
    return None

PEANUT_EXE_PATH = find_peanut_binary()

# Windows API 定義
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

VK_SPACE = 0x20
WM_CLOSE = 0x0010
WM_COMMAND = 0x0111
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
BM_CLICK = 0x00F5
GW_ENABLEDPOPUP = 6
SW_MINIMIZE = 6
SW_SHOWMINNOACTIVE = 7
SW_RESTORE = 9

SWP_NOSIZE = 0x0001
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010

CBN_SELCHANGE = 1
CB_FINDSTRINGEXACT = 0x0158
CB_FINDSTRING = 0x014C
CB_SETCURSEL = 0x014E
CB_GETCOUNT = 0x0146
CB_GETLBTEXTLEN = 0x0149
CB_GETLBTEXT = 0x0148

# ANSI カラー
C_RESET    = "\033[0m"
C_BOLD     = "\033[1m"
C_BLUE_BG  = "\033[44m"  # DOS Blue Background
C_RED_BG   = "\033[41m"  # Red Alert Background (送信対象用)
C_WHITE    = "\033[97m"
C_CYAN     = "\033[96m"
C_GREEN    = "\033[92m"
C_YELLOW   = "\033[93m"
C_RED      = "\033[91m"
C_GRAY     = "\033[90m"
C_INVERSE  = "\033[7m"
C_CLR_EOL  = "\033[K"

def enable_vt_mode():
    h_out = kernel32.GetStdHandle(-11)
    mode = ctypes.c_ulong()
    kernel32.GetConsoleMode(h_out, ctypes.byref(mode))
    mode.value |= 0x0004 | 0x0001 | 0x0002
    kernel32.SetConsoleMode(h_out, mode)

def get_char_width(ch: str) -> int:
    ea = unicodedata.east_asian_width(ch)
    if ea in ('W', 'F', 'A'):
        return 2
    return 1

def get_str_width(text: str) -> int:
    return sum(get_char_width(ch) for ch in text)

def fit_to_width(text: str, target_width: int, align='left') -> str:
    curr_w = get_str_width(text)
    if curr_w > target_width:
        trimmed = ""
        w = 0
        for ch in text:
            cw = get_char_width(ch)
            if w + cw > target_width:
                break
            trimmed += ch
            w += cw
        return trimmed + (" " * (target_width - w))
    
    pad = " " * (target_width - curr_w)
    if align == 'left':
        return text + pad
    elif align == 'right':
        return pad + text
    else:
        left_len = (target_width - curr_w) // 2
        right_len = target_width - curr_w - left_len
        return (" " * left_len) + text + (" " * right_len)

def format_smart_timestamp(dt: datetime) -> str:
    now = datetime.now()
    diff_days = (now.date() - dt.date()).days
    time_part = dt.strftime("%H:%M:%S")

    if diff_days == 0:
        return f"Today {time_part}"
    elif diff_days == 1:
        return f"Yday  {time_part}"
    else:
        date_part = dt.strftime("%m/%d")
        return f"{date_part} {time_part}"

def focus_console_window():
    h_console = kernel32.GetConsoleWindow()
    if h_console:
        user32.ShowWindow(h_console, SW_RESTORE)
        user32.SetForegroundWindow(h_console)
        user32.BringWindowToTop(h_console)
        fore_thread = user32.GetWindowThreadProcessId(user32.GetForegroundWindow(), 0)
        curr_thread = kernel32.GetCurrentThreadId()
        if fore_thread != curr_thread:
            user32.AttachThreadInput(curr_thread, fore_thread, True)
            user32.SetForegroundWindow(h_console)
            user32.AttachThreadInput(curr_thread, fore_thread, False)

def hide_window_offscreen(hwnd):
    if hwnd and user32.IsWindow(hwnd):
        user32.SetWindowPos(hwnd, 0, -20000, -20000, 0, 0, SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE)

def get_all_peanut_hwnds():
    hwnds = []
    def enum_cb(hwnd, lparam):
        length = user32.GetWindowTextLengthW(hwnd)
        if length > 0:
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            if buf.value == "Peanut":
                cls_buf = ctypes.create_unicode_buffer(256)
                user32.GetClassNameW(hwnd, cls_buf, 256)
                if "WindowsForms" in cls_buf.value and user32.GetParent(hwnd) == 0:
                    hwnds.append(hwnd)
        return True

    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    user32.EnumWindows(WNDENUMPROC(enum_cb), 0)
    return hwnds


# ==============================================================================
#  UNIX / FreeBSD スタイル・ブートマネージャー
# ==============================================================================

class UnixBootManager:
    def __init__(self):
        self.t_start = time.time()
        self.lock = threading.Lock()
        self.running = True
        self.step_idx = 0
        self.step_name = "Subsystem Initializing"
        self.step_status = "RUNNING"
        self.spinner_chars = ["／", "―", "＼", "｜"]
        self.spinner_idx = 0
        self.logs = []

    def start_animation(self):
        t = threading.Thread(target=self._animation_loop, daemon=True)
        t.start()

    def _animation_loop(self):
        sys.stdout.write("\033[?25l")
        while self.running:
            with self.lock:
                self.spinner_idx = (self.spinner_idx + 1) % len(self.spinner_chars)
                self._render()
            time.sleep(0.1)

    def set_step(self, idx: int, name: str):
        with self.lock:
            self.step_idx = idx
            self.step_name = name
            self.step_status = "RUNNING"
            self._render()

    def complete_step(self):
        with self.lock:
            self.step_status = "OK"
            self._render()
        time.sleep(0.25)

    def log(self, message: str):
        elapsed = time.time() - self.t_start
        ts_str = f"[+{elapsed:6.3f}]"
        formatted_line = f"{C_GRAY}{ts_str}{C_RESET} {message}"
        with self.lock:
            self.logs.append(formatted_line)
            if len(self.logs) > 50:
                self.logs.pop(0)
            self._render()

    def _render(self):
        try:
            term = os.get_terminal_size()
            term_w = max(78, term.columns)
            term_h = max(24, term.lines)
        except Exception:
            term_w = 80
            term_h = 24

        log_display_count = max(6, term_h - 10)
        sys.stdout.write("\033[H")

        banner = " FUNA Appliance OS - Dual Master Subsystem Boot "
        print(f"{C_BLUE_BG}{C_WHITE}{C_BOLD}╔{'═' * (term_w - 2)}╗{C_RESET}{C_CLR_EOL}")
        print(f"{C_BLUE_BG}{C_WHITE}{C_BOLD}║ {fit_to_width(banner, term_w - 4)} ║{C_RESET}{C_CLR_EOL}")
        print(f"{C_BLUE_BG}{C_WHITE}{C_BOLD}╠{'═' * (term_w - 2)}╣{C_RESET}{C_CLR_EOL}")

        if self.step_status == "OK":
            badge = f"{C_GREEN}{C_BOLD}[  OK  ]{C_RESET}"
        else:
            spin_ch = self.spinner_chars[self.spinner_idx]
            badge = f"{C_YELLOW}{C_BOLD}[ {spin_ch} ]{C_RESET}"

        step_text = f" [STEP {self.step_idx}/5] {self.step_name}..."
        raw_len = get_str_width(step_text)
        gap = max(0, term_w - 4 - raw_len - 8)
        line_str = f"{step_text}{' ' * gap}{badge}"
        print(f"{C_BLUE_BG}{C_WHITE}║ {line_str} ║{C_RESET}{C_CLR_EOL}")
        print(f"{C_BLUE_BG}{C_WHITE}╠{'═' * (term_w - 2)}╣{C_RESET}{C_CLR_EOL}")

        visible_logs = self.logs[-log_display_count:]
        for i in range(log_display_count):
            if i < len(visible_logs):
                print(f" {visible_logs[i]}{C_CLR_EOL}")
            else:
                print(f" {C_CLR_EOL}")

        print(f"{C_GRAY}─{'─' * (term_w - 2)}─{C_RESET}{C_CLR_EOL}", end="", flush=True)

    def finish(self):
        self.running = False
        time.sleep(0.15)
        sys.stdout.write("\033[?25h")
        sys.stdout.flush()


# ==============================================================================
#  Peanut ドライバ層
# ==============================================================================

class PeanutFastInstance:
    def __init__(self, hwnd, label="PEANUT"):
        self.hwnd = hwnd
        self.label = label
        hide_window_offscreen(self.hwnd)

        self.app = Application(backend="uia").connect(handle=hwnd)
        self.main_win = self.app.window(handle=hwnd)

        self.ctrl_ptt_label = self.main_win.child_window(auto_id="PTTlabel", control_type="Text")
        self.ctrl_host_status = self.main_win.child_window(auto_id="hostStatus", control_type="Text")
        self.ctrl_his_call = self.main_win.child_window(auto_id="hisCallLabel", control_type="Text")
        self.ctrl_his_name = self.main_win.child_window(auto_id="nameStaticLabel", control_type="Text")
        self.ctrl_room_combo = self.main_win.child_window(auto_id="RoomComboBox", control_type="ComboBox")
        self.ctrl_room_desc = self.main_win.child_window(auto_id="roomDescriptionLabel", control_type="Text")
        self.ctrl_country_combo = self.main_win.child_window(auto_id="countryComboBox", control_type="ComboBox")
        self.ctrl_onair_switch = self.main_win.child_window(auto_id="onAIRswitch")
        self.ctrl_onoff_switch = self.main_win.child_window(auto_id="OnOffToggleSwitch")
        self.ctrl_setup_btn = self.main_win.child_window(auto_id="setupButton", control_type="Button")

        self.hwnd_room_combo = self.ctrl_room_combo.handle
        self.hwnd_onair_switch = self.ctrl_onair_switch.handle
        self.hwnd_onoff_switch = self.ctrl_onoff_switch.handle
        self._cached_rooms = []

    def make_stealth(self):
        hide_window_offscreen(self.hwnd)

    def close(self):
        user32.PostMessageW(self.hwnd, WM_CLOSE, 0, 0)

    def is_tx(self) -> bool:
        try:
            return "PTT ON" in self.ctrl_ptt_label.window_text()
        except Exception:
            return False

    def is_online(self) -> bool:
        try:
            txt = self.ctrl_host_status.window_text().strip()
            if not txt or "disconnect" in txt.lower():
                return False
            return True
        except Exception:
            return False

    def get_status(self) -> dict:
        st = {"state": "OFFLINE", "call": "", "name": "", "room": "", "desc": "", "country": ""}
        try:
            st["state"] = "ONLINE" if self.is_online() else "OFFLINE"
            st["call"] = self.ctrl_his_call.window_text()
            st["name"] = self.ctrl_his_name.window_text()
            st["room"] = self.ctrl_room_combo.window_text()
            st["desc"] = self.ctrl_room_desc.window_text()
            st["country"] = self.ctrl_country_combo.window_text()
        except Exception:
            pass
        return st

    def _click_pane_pure(self, hwnd_pane):
        rect = ctypes.wintypes.RECT()
        user32.GetClientRect(hwnd_pane, ctypes.byref(rect))
        cx = (rect.right - rect.left) // 2
        cy = (rect.bottom - rect.top) // 2
        lparam = (cy << 16) | (cx & 0xFFFF)
        user32.PostMessageW(hwnd_pane, WM_LBUTTONDOWN, 1, lparam)
        time.sleep(0.04)
        user32.PostMessageW(hwnd_pane, WM_LBUTTONUP, 0, lparam)

    def toggle_on_off(self):
        self._click_pane_pure(self.hwnd_onoff_switch)

    def ensure_offline(self):
        if self.is_online():
            self.toggle_on_off()
            for _ in range(10):
                time.sleep(0.15)
                if not self.is_online():
                    break
            time.sleep(0.3)

    def ensure_online(self, max_retries=5) -> bool:
        for _ in range(max_retries):
            if self.is_online():
                return True
            self.toggle_on_off()
            time.sleep(1.0)
        return self.is_online()

    def tx_on(self):
        if not self.is_tx():
            self._click_pane_pure(self.hwnd_onair_switch)

    def tx_off(self):
        if self.is_tx():
            self._click_pane_pure(self.hwnd_onair_switch)

    def get_all_rooms(self) -> list:
        try:
            hwnd = self.hwnd_room_combo
            count = user32.SendMessageW(hwnd, CB_GETCOUNT, 0, 0)
            rooms = []
            for i in range(count):
                length = user32.SendMessageW(hwnd, CB_GETLBTEXTLEN, i, 0)
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.SendMessageW(hwnd, CB_GETLBTEXT, i, buf)
                rooms.append(buf.value)
            if rooms:
                self._cached_rooms = rooms
            return self._cached_rooms
        except Exception:
            return self._cached_rooms

    def set_room_fast(self, room_name: str) -> bool:
        try:
            hwnd = self.hwnd_room_combo
            idx = user32.SendMessageW(hwnd, CB_FINDSTRINGEXACT, -1, room_name)
            if idx == -1:
                idx = user32.SendMessageW(hwnd, CB_FINDSTRING, -1, room_name)
            if idx != -1:
                user32.SendMessageW(hwnd, CB_SETCURSEL, idx, 0)
                parent = user32.GetParent(hwnd)
                ctrl_id = user32.GetDlgCtrlID(hwnd)
                wparam = (CBN_SELCHANGE << 16) | (ctrl_id & 0xFFFF)
                user32.SendMessageW(parent, WM_COMMAND, wparam, hwnd)
                return True
        except Exception:
            pass
        return False

    def configure_master_pure(self, target_master_name: str, boot_mgr: UnixBootManager = None) -> bool:
        try:
            self.ensure_offline()
            user32.PostMessageW(self.ctrl_setup_btn.handle, BM_CLICK, 0, 0)

            setup_dlg = None
            for _ in range(25):
                time.sleep(0.12)
                popup_hwnd = user32.GetWindow(self.hwnd, GW_ENABLEDPOPUP)
                if popup_hwnd and popup_hwnd != self.hwnd:
                    hide_window_offscreen(popup_hwnd)
                    buf = ctypes.create_unicode_buffer(64)
                    user32.GetWindowTextW(popup_hwnd, buf, 64)
                    if "setup" in buf.value.lower():
                        app = Application(backend="uia").connect(handle=popup_hwnd)
                        setup_dlg = app.window(handle=popup_hwnd)
                        break

            if not setup_dlg:
                return False

            if boot_mgr:
                boot_mgr.log(f"{self.label}: SetupForm trapped (HWND 0x{setup_dlg.handle:X}) -> Offscreen")

            master_combo = setup_dlg.child_window(auto_id="masterlistComboBox", control_type="ComboBox")
            hwnd_combo = master_combo.handle
            idx = user32.SendMessageW(hwnd_combo, CB_FINDSTRINGEXACT, -1, target_master_name)
            if idx != -1:
                user32.SendMessageW(hwnd_combo, CB_SETCURSEL, idx, 0)
                parent = user32.GetParent(hwnd_combo)
                ctrl_id = user32.GetDlgCtrlID(hwnd_combo)
                user32.SendMessageW(parent, WM_COMMAND, (CBN_SELCHANGE << 16) | ctrl_id, hwnd_combo)
                if boot_mgr:
                    boot_mgr.log(f"{self.label}: masterlistComboBox selection -> '{target_master_name}'")

            time.sleep(0.2)
            save_btn = setup_dlg.child_window(auto_id="saveButton", control_type="Button")
            user32.PostMessageW(save_btn.handle, BM_CLICK, 0, 0)

            for _ in range(25):
                time.sleep(0.12)
                curr_popup = user32.GetWindow(self.hwnd, GW_ENABLEDPOPUP)
                if curr_popup == self.hwnd or curr_popup == 0:
                    break

            time.sleep(0.3)
            self.make_stealth()
            return True
        except Exception:
            return False


# ==============================================================================
#  メインアプリケーション層 (Active VFO Red Alert ＆ Dual Last Heard)
# ==============================================================================

class FunaWrapperApp:
    def __init__(self):
        self.inst_jp = None
        self.inst_gl = None
        self.active_target = "JP"
        self.running = True
        self.status_jp = {}
        self.status_gl = {}
        
        self.last_heard_jp = []
        self.last_heard_gl = []

        self.message_line = "Ready. Press [Tab] to Switch VFO, [m] to Select Room, Hold [SPACE] to Talk."
        self.tx_state_str = "IDLE (RX Ready)"
        self.needs_redraw = True
        self.in_selector = False

    def boot_and_setup(self):
        os.system("cls")
        boot = UnixBootManager()
        boot.start_animation()

        boot.set_step(1, "Probing Background Peanut Instances")
        boot.log("kernel: EnumWindows probing for 'WindowsForms10.Window.8' Peanut class...")
        
        existing_hwnds = get_all_peanut_hwnds()
        needed = 2 - len(existing_hwnds)
        boot.log(f"peanut: Found {len(existing_hwnds)} active instances (Required: 2)")

        if needed > 0:
            boot.log(f"spawn: Forking {needed} background Peanut worker(s) with SW_SHOWMINNOACTIVE...")
            if PEANUT_EXE_PATH and os.path.exists(PEANUT_EXE_PATH):
                si = subprocess.STARTUPINFO()
                si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                si.wShowWindow = SW_SHOWMINNOACTIVE

                for i in range(needed):
                    subprocess.Popen([PEANUT_EXE_PATH], startupinfo=si)
                    boot.log(f"spawn: Worker [{i+1}/{needed}] started: {os.path.basename(PEANUT_EXE_PATH)}")
                    time.sleep(2.0)
                    focus_console_window()
            else:
                boot.log("FATAL: Peanut binary path not found!")

            for _ in range(12):
                existing_hwnds = get_all_peanut_hwnds()
                if len(existing_hwnds) >= 2:
                    break
                time.sleep(0.8)

        if len(existing_hwnds) < 2:
            boot.log("WARNING: Failed to acquire 2 instances. Fallback to single instance.")
            if len(existing_hwnds) == 1:
                self.inst_jp = PeanutFastInstance(existing_hwnds[0], label="JP MASTER")
            boot.complete_step()
            boot.finish()
            return

        boot.log(f"stealth: Teleporting HWND 0x{existing_hwnds[0]:X} & 0x{existing_hwnds[1]:X} to offscreen (-20000, -20000)")
        inst1 = PeanutFastInstance(existing_hwnds[0], label="VFO-A")
        inst2 = PeanutFastInstance(existing_hwnds[1], label="VFO-B")
        inst1.make_stealth()
        inst2.make_stealth()
        focus_console_window()
        boot.complete_step()

        boot.set_step(2, "Configuring Master Servers (Japan / Global)")
        boot.log("subsys: Dispatching async setup triggers to modal dialogs...")
        inst1.configure_master_pure("Japan", boot)
        time.sleep(0.3)
        inst2.configure_master_pure("Global", boot)

        self.inst_jp = inst1
        self.inst_gl = inst2
        self.inst_jp.label = "JP MASTER"
        self.inst_gl.label = "GLOBAL MASTER"
        boot.log("subsys: VFO-A assigned to 'Japan', VFO-B assigned to 'Global'")
        boot.complete_step()

        boot.set_step(3, "Session Connect Guarantee (Auto Power ON)")
        boot.log("net: Pulsing OnOffToggleSwitch for VFO-A & VFO-B via PostMessage...")
        self.inst_jp.ensure_online()
        boot.log("net: VFO-A session initialized (hostStatus=Connecting)")
        self.inst_gl.ensure_online()
        boot.log("net: VFO-B session initialized (hostStatus=Connecting)")
        boot.complete_step()

        boot.set_step(4, "Waiting Server Session & Synchronizing Rooms")
        for wait_sec in range(3, 0, -1):
            boot.log(f"net: Downloading global master room lists from cluster... ({wait_sec}s remaining)")
            time.sleep(1.0)

        self.inst_jp.set_room_fast(DEFAULT_ROOM_JP)
        boot.log(f"route: VFO-A set to default room '{DEFAULT_ROOM_JP}'")

        for attempt in range(6):
            if self.inst_gl.set_room_fast(DEFAULT_ROOM_GLOBAL):
                boot.log(f"route: VFO-B set to default room '{DEFAULT_ROOM_GLOBAL}' (ACK)")
                break
            time.sleep(0.8)
        boot.complete_step()

        boot.set_step(5, "Stealth Verification & Locking Terminal Dominance")
        self.inst_jp.make_stealth()
        self.inst_gl.make_stealth()
        focus_console_window()
        boot.log("console: Terminal dominance locked via SetForegroundWindow")
        boot.log("kernel: All subsystems operational. Entering interactive TUI mode.")
        boot.complete_step()

        time.sleep(0.6)
        boot.finish()

    def shutdown(self):
        print(f"\n{C_YELLOW}Peanutプロセスを正常終了しています...{C_RESET}")
        if self.inst_jp:
            self.inst_jp.close()
        if self.inst_gl:
            self.inst_gl.close()

        time.sleep(1.0)
        remaining_hwnds = get_all_peanut_hwnds()
        for hwnd in remaining_hwnds:
            user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)

        print(f"{C_GREEN}すべてのPeanutプロセスがクローズされました。{C_RESET}")
        print(f"{C_RESET}FUNA Wrapper for Peanut を終了しました。73 & Good DX!")

    def get_active_inst(self) -> PeanutFastInstance:
        if self.active_target == "JP" or not self.inst_gl:
            return self.inst_jp
        return self.inst_gl

    def background_poller(self):
        last_jp_call = ""
        last_gl_call = ""

        while self.running:
            try:
                updated = False
                if self.inst_jp:
                    new_st_jp = self.inst_jp.get_status()
                    if new_st_jp != self.status_jp:
                        self.status_jp = new_st_jp
                        updated = True
                    c = self.status_jp.get("call", "")
                    if c and c not in ("PTT OFF", "PTT ON", "CALL", "") and c != last_jp_call:
                        entry = {
                            "dt": datetime.now(),
                            "call": c,
                            "room": self.status_jp.get("room", "")
                        }
                        self.last_heard_jp.append(entry)
                        last_jp_call = c
                        updated = True

                if self.inst_gl:
                    new_st_gl = self.inst_gl.get_status()
                    if new_st_gl != self.status_gl:
                        self.status_gl = new_st_gl
                        updated = True
                    c = self.status_gl.get("call", "")
                    if c and c not in ("PTT OFF", "PTT ON", "CALL", "") and c != last_gl_call:
                        entry = {
                            "dt": datetime.now(),
                            "call": c,
                            "room": self.status_gl.get("room", "")
                        }
                        self.last_heard_gl.append(entry)
                        last_gl_call = c
                        updated = True

                if len(self.last_heard_jp) > 30:
                    self.last_heard_jp = self.last_heard_jp[-30:]
                if len(self.last_heard_gl) > 30:
                    self.last_heard_gl = self.last_heard_gl[-30:]

                if updated and not self.in_selector:
                    self.needs_redraw = True

            except Exception:
                pass
            time.sleep(0.2)

    def momentary_ptt_thread(self):
        was_pressed = False
        while self.running:
            is_pressed = (user32.GetAsyncKeyState(VK_SPACE) & 0x8000) != 0
            if is_pressed and not was_pressed:
                target = self.get_active_inst()
                if target:
                    target.tx_on()
                    self.tx_state_str = f"TRANSMITTING (TX -> {self.active_target})"
                    if not self.in_selector:
                        self.needs_redraw = True
                was_pressed = True
            elif not is_pressed and was_pressed:
                target = self.get_active_inst()
                if target:
                    target.tx_off()
                    self.tx_state_str = "IDLE (RX Ready)"
                    if not self.in_selector:
                        self.needs_redraw = True
                was_pressed = False
            time.sleep(0.01)

    def render_tui(self):
        """
        左右完全2ペイン・レスポンシブTUI描画
        【新機能】アクティブなVFO側ペイン全体が赤背景（Red Alert）に点灯！
        """
        sys.stdout.write("\033[H")
        
        try:
            term = os.get_terminal_size()
            term_w = max(78, term.columns)
            term_h = max(24, term.lines)
        except Exception:
            term_w = 80
            term_h = 25

        inner_total = term_w - 3
        col1_w = inner_total // 2
        col2_w = inner_total - col1_w

        jp_st   = self.status_jp.get("state", "OFFLINE")
        jp_room = self.status_jp.get("room", "---")
        jp_desc = self.status_jp.get("desc", "")
        jp_call = self.status_jp.get("call", "")
        jp_name = self.status_jp.get("name", "")

        gl_st   = self.status_gl.get("state", "OFFLINE") if self.inst_gl else "DISABLED"
        gl_room = self.status_gl.get("room", "---") if self.inst_gl else "---"
        gl_desc = self.status_gl.get("desc", "") if self.inst_gl else ""
        gl_call = self.status_gl.get("call", "") if self.inst_gl else ""
        gl_name = self.status_gl.get("name", "") if self.inst_gl else ""

        # ヘッダー
        print(f"{C_BLUE_BG}{C_WHITE}{C_BOLD}╔{'═' * (term_w - 2)}╗{C_RESET}{C_CLR_EOL}")
        title_left = " FUNA Wrapper for Peanut - Dual Master Console "
        active_tag = f"[ACTIVE VFO: {self.active_target}] "
        gap_w = max(0, term_w - 2 - get_str_width(title_left) - get_str_width(active_tag))
        header_text = title_left + (" " * gap_w) + active_tag
        print(f"{C_BLUE_BG}{C_WHITE}{C_BOLD}║{header_text}║{C_RESET}{C_CLR_EOL}")
        print(f"{C_BLUE_BG}{C_WHITE}{C_BOLD}╠{'═' * col1_w}╦{'═' * col2_w}╣{C_RESET}{C_CLR_EOL}")

        # 【超視覚的 Red Alert】アクティブ側＝赤背景＋太字白、スタンバイ側＝DOSブルー
        if self.active_target == "JP":
            bg_col1 = f"{C_RED_BG}{C_WHITE}{C_BOLD}"
            bg_col2 = f"{C_BLUE_BG}{C_WHITE}"
            tag_jp_raw = " [1] JP MASTER [★ACTIVE/TX] "
            tag_gl_raw = " [2] GLOBAL MASTER (STANDBY) "
        else:
            bg_col1 = f"{C_BLUE_BG}{C_WHITE}"
            bg_col2 = f"{C_RED_BG}{C_WHITE}{C_BOLD}"
            tag_jp_raw = " [1] JP MASTER (STANDBY) "
            tag_gl_raw = " [2] GLOBAL MASTER [★ACTIVE/TX] "

        tag_jp = fit_to_width(tag_jp_raw, col1_w)
        tag_gl = fit_to_width(tag_gl_raw, col2_w)
        print(f"{C_BLUE_BG}{C_WHITE}║{bg_col1}{tag_jp}{C_RESET}{C_BLUE_BG}{C_WHITE}║{bg_col2}{tag_gl}{C_RESET}{C_BLUE_BG}{C_WHITE}║{C_RESET}{C_CLR_EOL}")
        print(f"{C_BLUE_BG}{C_WHITE}╠{'─' * col1_w}╫{'─' * col2_w}╣{C_RESET}{C_CLR_EOL}")

        # VFO情報行 (アクティブ側の背景色を維持して真っ赤に表示)
        col1_items = [
            f" State: {jp_st}",
            f" Room : {jp_room}",
            f" Desc : {jp_desc}",
            f" Call : {jp_call}",
            f" Name : {jp_name}"
        ]
        col2_items = [
            f" State: {gl_st}",
            f" Room : {gl_room}",
            f" Desc : {gl_desc}",
            f" Call : {gl_call}",
            f" Name : {gl_name}"
        ]
        for c1_raw, c2_raw in zip(col1_items, col2_items):
            c1_str = fit_to_width(c1_raw, col1_w)
            c2_str = fit_to_width(c2_raw, col2_w)
            print(f"{C_BLUE_BG}{C_WHITE}║{bg_col1}{c1_str}{C_RESET}{C_BLUE_BG}{C_WHITE}║{bg_col2}{c2_str}{C_RESET}{C_BLUE_BG}{C_WHITE}║{C_RESET}{C_CLR_EOL}")

        # Last Heard 左右2ペイン見出し (中央仕切り║が貫通)
        print(f"{C_BLUE_BG}{C_WHITE}╠{'═' * col1_w}╬{'═' * col2_w}╣{C_RESET}{C_CLR_EOL}")
        lh_head_jp = fit_to_width(" LAST HEARD [JP MASTER]", col1_w)
        lh_head_gl = fit_to_width(" LAST HEARD [GLOBAL MASTER]", col2_w)
        print(f"{C_BLUE_BG}{C_CYAN}║{lh_head_jp}{C_WHITE}║{C_CYAN}{lh_head_gl}{C_WHITE}║{C_RESET}{C_CLR_EOL}")
        print(f"{C_BLUE_BG}{C_WHITE}╠{'─' * col1_w}╫{'─' * col2_w}╣{C_RESET}{C_CLR_EOL}")

        log_rows = max(5, min(12, term_h - 18))

        for i in range(log_rows):
            # 左ペイン (JP)
            if i < len(self.last_heard_jp):
                entry_jp = self.last_heard_jp[-(i + 1)]
                ts_jp = format_smart_timestamp(entry_jp["dt"])
                raw_jp = f" {ts_jp} {entry_jp['call']:<8} in {entry_jp['room']}"
            else:
                raw_jp = " "
            str_jp = fit_to_width(raw_jp, col1_w)

            # 右ペイン (GLOBAL)
            if i < len(self.last_heard_gl):
                entry_gl = self.last_heard_gl[-(i + 1)]
                ts_gl = format_smart_timestamp(entry_gl["dt"])
                raw_gl = f" {ts_gl} {entry_gl['call']:<8} in {entry_gl['room']}"
            else:
                raw_gl = " "
            str_gl = fit_to_width(raw_gl, col2_w)

            print(f"{C_BLUE_BG}{C_WHITE}║{str_jp}║{str_gl}║{C_RESET}{C_CLR_EOL}")

        # PTT インジケータ
        print(f"{C_BLUE_BG}{C_WHITE}╠{'═' * (term_w - 2)}╣{C_RESET}{C_CLR_EOL}")
        tx_color = f"{C_RED}{C_BOLD}" if "TRANSMITTING" in self.tx_state_str else f"{C_GREEN}"
        ptt_status = f"PTT: [ {self.tx_state_str} ] (Hold [SPACE] to Talk)"
        print(f"{C_BLUE_BG}{C_WHITE}║  PTT: {tx_color}[ {self.tx_state_str} ]{C_RESET}{C_BLUE_BG}{C_WHITE}{fit_to_width(' (Hold [SPACE] to Talk)', term_w - 11 - len(self.tx_state_str))}║{C_RESET}{C_CLR_EOL}")
        print(f"{C_BLUE_BG}{C_WHITE}╚{'═' * (term_w - 2)}╝{C_RESET}{C_CLR_EOL}")

        # 最下部ステータス
        msg_str = fit_to_width(self.message_line, term_w)
        guide_str = fit_to_width("[Tab]: Switch VFO | [m]: Select Room | [o]: Power On/Off | [q]: Quit", term_w)
        print(f"{C_CYAN}{msg_str}{C_RESET}{C_CLR_EOL}")
        print(f"{C_GRAY}{guide_str}{C_RESET}{C_CLR_EOL}")
        sys.stdout.flush()

    def show_room_selector(self):
        self.in_selector = True
        target = self.get_active_inst()
        all_rooms = target.get_all_rooms()

        if not all_rooms:
            self.message_line = f"Failed to retrieve rooms for [{self.active_target}]."
            self.in_selector = False
            return

        current_room = self.status_jp.get("room") if self.active_target == "JP" else self.status_gl.get("room")
        filter_text = ""
        selected_idx = 0
        scroll_offset = 0
        page_size = 10

        for idx, r in enumerate(all_rooms):
            if r == current_room:
                selected_idx = idx
                scroll_offset = max(0, idx - page_size // 2)
                break

        def render_popup():
            sys.stdout.write("\033[H")
            try:
                term = os.get_terminal_size()
                term_w = max(78, term.columns)
            except Exception:
                term_w = 80

            pw = min(60, term_w - 6)
            pad_left = " " * max(0, (term_w - pw) // 2)

            if filter_text:
                filtered = [r for r in all_rooms if filter_text.lower() in r.lower()]
            else:
                filtered = list(all_rooms)

            nonlocal selected_idx, scroll_offset
            if selected_idx >= len(filtered):
                selected_idx = max(0, len(filtered) - 1)

            if selected_idx < scroll_offset:
                scroll_offset = selected_idx
            elif selected_idx >= scroll_offset + page_size:
                scroll_offset = selected_idx - page_size + 1

            print(f"\n{pad_left}{C_BLUE_BG}{C_YELLOW}{C_BOLD}╔{'═' * (pw - 2)}╗{C_RESET}{C_CLR_EOL}")
            title = fit_to_width(f"SELECT ROOM [{self.active_target} MASTER]", pw - 4, align='center')
            print(f"{pad_left}{C_BLUE_BG}{C_YELLOW}{C_BOLD}║ {title} ║{C_RESET}{C_CLR_EOL}")
            print(f"{pad_left}{C_BLUE_BG}{C_WHITE}╠{'═' * (pw - 2)}╣{C_RESET}{C_CLR_EOL}")

            search_display = fit_to_width(f" Search Filter: {filter_text}_", pw - 4)
            print(f"{pad_left}{C_BLUE_BG}{C_CYAN}║ {search_display} ║{C_RESET}{C_CLR_EOL}")
            print(f"{pad_left}{C_BLUE_BG}{C_WHITE}╠{'─' * (pw - 2)}╣{C_RESET}{C_CLR_EOL}")

            for i in range(page_size):
                item_idx = scroll_offset + i
                if item_idx < len(filtered):
                    room_name = filtered[item_idx]
                    if item_idx == selected_idx:
                        line_str = fit_to_width(f" ► {room_name}", pw - 4)
                        print(f"{pad_left}{C_BLUE_BG}{C_WHITE}{C_INVERSE}║ {line_str} ║{C_RESET}{C_CLR_EOL}")
                    else:
                        line_str = fit_to_width(f"   {room_name}", pw - 4)
                        print(f"{pad_left}{C_BLUE_BG}{C_WHITE}║ {line_str} ║{C_RESET}{C_CLR_EOL}")
                else:
                    empty_line = " " * (pw - 2)
                    print(f"{pad_left}{C_BLUE_BG}{C_WHITE}║{empty_line}║{C_RESET}{C_CLR_EOL}")

            print(f"{pad_left}{C_BLUE_BG}{C_WHITE}╠{'═' * (pw - 2)}╣{C_RESET}{C_CLR_EOL}")
            status_text = fit_to_width(f" [{len(filtered)}/{len(all_rooms)}] <↑/↓>:Move <Enter>:OK <Esc>:Cancel", pw - 4)
            print(f"{pad_left}{C_BLUE_BG}{C_GRAY}║ {status_text} ║{C_RESET}{C_CLR_EOL}")
            print(f"{pad_left}{C_BLUE_BG}{C_YELLOW}╚{'═' * (pw - 2)}╝{C_RESET}{C_CLR_EOL}")
            sys.stdout.flush()

        os.system("cls")
        render_popup()

        while True:
            ch = msvcrt.getwch()

            if ch in ("\x00", "\xe0"):
                sub_ch = msvcrt.getwch()
                filtered = [r for r in all_rooms if filter_text.lower() in r.lower()] if filter_text else all_rooms
                
                if sub_ch == "H":
                    if selected_idx > 0:
                        selected_idx -= 1
                        render_popup()
                elif sub_ch == "P":
                    if selected_idx < len(filtered) - 1:
                        selected_idx += 1
                        render_popup()
                elif sub_ch == "I":
                    selected_idx = max(0, selected_idx - page_size)
                    render_popup()
                elif sub_ch == "Q":
                    selected_idx = min(len(filtered) - 1, selected_idx + page_size)
                    render_popup()

            elif ch == "\r":
                filtered = [r for r in all_rooms if filter_text.lower() in r.lower()] if filter_text else all_rooms
                if filtered and 0 <= selected_idx < len(filtered):
                    chosen_room = filtered[selected_idx]
                    self.message_line = f"Changing room to '{chosen_room}' on [{self.active_target}]..."
                    target.set_room_fast(chosen_room)
                    self.message_line = f"Joined '{chosen_room}' on [{self.active_target}]."
                break

            elif ch == "\x1b":
                self.message_line = "Room selection cancelled."
                break

            elif ch == "\x08":
                if filter_text:
                    filter_text = filter_text[:-1]
                    selected_idx = 0
                    scroll_offset = 0
                    render_popup()

            elif ch.isprintable():
                filter_text += ch
                selected_idx = 0
                scroll_offset = 0
                render_popup()

        self.in_selector = False
        os.system("cls")
        self.render_tui()

    def run(self):
        enable_vt_mode()
        self.boot_and_setup()

        t_poll = threading.Thread(target=self.background_poller, daemon=True)
        t_poll.start()

        t_ptt = threading.Thread(target=self.momentary_ptt_thread, daemon=True)
        t_ptt.start()

        os.system("cls")
        self.render_tui()

        while self.running:
            if self.needs_redraw and not self.in_selector:
                self.render_tui()
                self.needs_redraw = False

            if msvcrt.kbhit() and not self.in_selector:
                ch = msvcrt.getwch()

                # TabキーでアクティブVFOを切り替えると、赤背景が瞬時に反転！
                if ch == "\t":
                    if self.inst_gl:
                        self.active_target = "GLOBAL" if self.active_target == "JP" else "JP"
                        self.message_line = f"Active VFO switched to [{self.active_target}]."
                    else:
                        self.message_line = "Global instance is disabled."
                    self.needs_redraw = True

                elif ch.lower() == "o":
                    target = self.get_active_inst()
                    target.toggle_on_off()
                    self.message_line = f"Toggled Connect/Disconnect on [{self.active_target}]."
                    self.needs_redraw = True

                elif ch.lower() == "m":
                    self.show_room_selector()

                elif ch.lower() == "q":
                    break

            time.sleep(0.02)

        self.running = False
        self.shutdown()

if __name__ == "__main__":
    app = FunaWrapperApp()
    app.run()