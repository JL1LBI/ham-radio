"""
==============================================================================
 FUNA Wrapper for Peanut - Dual Master Console (v3.4.0 Sequence Fixed)
 
 [Fixes]
  - Fixed 'is_online' bug: uses 'hostStatus' instead of 'PTTlabel'
  - Strict Sequence: Ensure OFF -> Setup (JP/Global) -> Auto ON -> Sync Rooms
  - Keeps Console Focus Foreground
  - Pop-up Room Selector with Instant Filter
  - 100% Pure Win32 PTT & Message Trigger (Zero Mouse Movement)
==============================================================================
"""

import os
import sys
import time
import msvcrt
import ctypes
import subprocess
import threading
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

# Windows API
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

VK_SPACE = 0x20
WM_COMMAND = 0x0111
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
BM_CLICK = 0x00F5
GW_ENABLEDPOPUP = 6
SW_MINIMIZE = 6
SW_RESTORE = 9
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
C_BLUE_BG  = "\033[44m"
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

def focus_console_window():
    """コマンドプロンプトに最前面フォーカスを強制復帰"""
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

def get_all_peanut_hwnds():
    """最小化含む全Peanutウィンドウを列挙"""
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


class PeanutFastInstance:
    def __init__(self, hwnd, label="PEANUT"):
        self.hwnd = hwnd
        self.label = label
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

    def minimize(self):
        user32.ShowWindow(self.hwnd, SW_MINIMIZE)

    def is_tx(self) -> bool:
        try:
            return "PTT ON" in self.ctrl_ptt_label.window_text()
        except Exception:
            return False

    def is_online(self) -> bool:
        """
        【超重要修正】hostStatus の文字列で正確に判定する
        'Disconnected' が含まれている場合は絶対にOFFLINE
        """
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
        """確実にOFF状態にする（Setupに入る前の必須処理）"""
        if self.is_online():
            print(f"    [{self.label}] 現在Onlineのため、一度Offにします...")
            self.toggle_on_off()
            for _ in range(15):
                time.sleep(0.2)
                if not self.is_online():
                    break
            time.sleep(0.5)

    def ensure_online(self, max_retries=6) -> bool:
        """確実にOnlineにする"""
        for _ in range(max_retries):
            if self.is_online():
                return True
            self.toggle_on_off()
            time.sleep(1.2)
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

    def configure_master_pure(self, target_master_name: str) -> bool:
        """確実にOFFの状態でSetupを開き、Masterを設定してSaveする"""
        try:
            self.ensure_offline()

            print(f"    [{self.label}] Setupボタンをクリック中...")
            user32.PostMessageW(self.ctrl_setup_btn.handle, BM_CLICK, 0, 0)

            setup_dlg = None
            for _ in range(30):
                time.sleep(0.15)
                popup_hwnd = user32.GetWindow(self.hwnd, GW_ENABLEDPOPUP)
                if popup_hwnd and popup_hwnd != self.hwnd:
                    buf = ctypes.create_unicode_buffer(64)
                    user32.GetWindowTextW(popup_hwnd, buf, 64)
                    if "setup" in buf.value.lower():
                        app = Application(backend="uia").connect(handle=popup_hwnd)
                        setup_dlg = app.window(handle=popup_hwnd)
                        break

            if not setup_dlg:
                print(f"    [{self.label}] エラー: Setup画面が開きませんでした。")
                return False

            master_combo = setup_dlg.child_window(auto_id="masterlistComboBox", control_type="ComboBox")
            hwnd_combo = master_combo.handle
            idx = user32.SendMessageW(hwnd_combo, CB_FINDSTRINGEXACT, -1, target_master_name)
            if idx != -1:
                print(f"    [{self.label}] -> '{target_master_name}' を選択")
                user32.SendMessageW(hwnd_combo, CB_SETCURSEL, idx, 0)
                parent = user32.GetParent(hwnd_combo)
                ctrl_id = user32.GetDlgCtrlID(hwnd_combo)
                user32.SendMessageW(parent, WM_COMMAND, (CBN_SELCHANGE << 16) | ctrl_id, hwnd_combo)

            time.sleep(0.3)
            save_btn = setup_dlg.child_window(auto_id="saveButton", control_type="Button")
            user32.PostMessageW(save_btn.handle, BM_CLICK, 0, 0)

            for _ in range(30):
                time.sleep(0.15)
                curr_popup = user32.GetWindow(self.hwnd, GW_ENABLEDPOPUP)
                if curr_popup == self.hwnd or curr_popup == 0:
                    break

            time.sleep(0.5)
            print(f"    [{self.label}] Setup設定完了 (Master: {target_master_name})")
            return True
        except Exception as e:
            print(f"    [{self.label}] Setup例外: {e}")
            return False


class FunaWrapperApp:
    def __init__(self):
        self.inst_jp = None
        self.inst_gl = None
        self.active_target = "JP"
        self.running = True
        self.status_jp = {}
        self.status_gl = {}
        self.last_heard_logs = []
        self.message_line = "Ready. Press [Tab] to Switch, [m] to Select Room, Hold [SPACE] to Talk."
        self.tx_state_str = "IDLE (RX Ready)"
        self.needs_redraw = True
        self.in_selector = False

    def boot_and_setup(self):
        print("\n[ステップ 1/5] Peanutプロセスの全探索中 (最小化含む)...")
        existing_hwnds = get_all_peanut_hwnds()
        needed = 2 - len(existing_hwnds)

        if needed > 0:
            print(f"-> 検出数: {len(existing_hwnds)} 件。不足分 ({needed} 個) を起動します...")
            if PEANUT_EXE_PATH and os.path.exists(PEANUT_EXE_PATH):
                for _ in range(needed):
                    subprocess.Popen([PEANUT_EXE_PATH], shell=True)
                    time.sleep(3.0)
            else:
                print("【注意】Peanut.exeが見つかりません。")

            for _ in range(15):
                existing_hwnds = get_all_peanut_hwnds()
                if len(existing_hwnds) >= 2:
                    break
                time.sleep(1.0)

        if len(existing_hwnds) < 2:
            print("【警告】Peanutが2つ揃いませんでした。")
            if len(existing_hwnds) == 1:
                self.inst_jp = PeanutFastInstance(existing_hwnds[0], label="JP MASTER")
            return

        print(f"-> 2つのPeanutを捕捉！(HWND: {existing_hwnds[0]}, {existing_hwnds[1]})")
        inst1 = PeanutFastInstance(existing_hwnds[0], label="INST-1")
        inst2 = PeanutFastInstance(existing_hwnds[1], label="INST-2")

        print("\n[ステップ 2/5] Masterサーバーの全自動構成 (必ずOFFの状態で実行)...")
        print("  - [1/2] Japan Master を構成中...")
        inst1.configure_master_pure("Japan")
        time.sleep(0.5)
        print("  - [2/2] Global Master を構成中...")
        inst2.configure_master_pure("Global")

        self.inst_jp = inst1
        self.inst_gl = inst2
        self.inst_jp.label = "JP MASTER"
        self.inst_gl.label = "GLOBAL MASTER"

        print("\n[ステップ 3/5] セッション接続 (Auto Power ON)...")
        print("  - [JP] Onlineスイッチ投入...")
        self.inst_jp.ensure_online()
        print("  - [GLOBAL] Onlineスイッチ投入...")
        self.inst_gl.ensure_online()

        print("\n[ステップ 4/5] サーバー接続確認 & デフォルト待機Room同期...")
        for wait_sec in range(4, 0, -1):
            print(f"\r  サーバー接続＆ルームリストダウンロード待機中... ({wait_sec}s)", end="", flush=True)
            time.sleep(1.0)
        print("\r  ルーム設定を同期中...                                    ")

        # JPルーム同期
        self.inst_jp.set_room_fast(DEFAULT_ROOM_JP)
        print(f"  -> JP Room: '{DEFAULT_ROOM_JP}' に同期")

        # GLOBALルーム同期（リトライ付き）
        gl_synced = False
        for attempt in range(8):
            if self.inst_gl.set_room_fast(DEFAULT_ROOM_GLOBAL):
                print(f"  -> GLOBAL Room: '{DEFAULT_ROOM_GLOBAL}' に同期成功！")
                gl_synced = True
                break
            time.sleep(1.0)

        if not gl_synced:
            print(f"  【注意】GLOBAL Room '{DEFAULT_ROOM_GLOBAL}' の同期をスキップしました (後から[m]キーで選択可能)。")

        print("\n[ステップ 5/5] Peanut最小化 ＆ コマンドプロンプト最前面固定...")
        self.inst_jp.minimize()
        self.inst_gl.minimize()
        time.sleep(0.5)
        focus_console_window()

        print("-> 初期化完了！FUNA Wrapper TUI を起動します...")
        time.sleep(1.0)

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
                        now_str = datetime.now().strftime("%H:%M:%S")
                        self.last_heard_logs.append(f"{now_str} [JP]     {c:<10} in {self.status_jp.get('room')}")
                        last_jp_call = c
                        updated = True

                if self.inst_gl:
                    new_st_gl = self.inst_gl.get_status()
                    if new_st_gl != self.status_gl:
                        self.status_gl = new_st_gl
                        updated = True
                    c = self.status_gl.get("call", "")
                    if c and c not in ("PTT OFF", "PTT ON", "CALL", "") and c != last_gl_call:
                        now_str = datetime.now().strftime("%H:%M:%S")
                        self.last_heard_logs.append(f"{now_str} [GLOBAL] {c:<10} in {self.status_gl.get('room')}")
                        last_gl_call = c
                        updated = True

                if len(self.last_heard_logs) > 6:
                    self.last_heard_logs = self.last_heard_logs[-6:]

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
        sys.stdout.write("\033[H")
        w = 78

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

        print(f"{C_BLUE_BG}{C_WHITE}{C_BOLD}╔{'═' * (w - 2)}╗{C_RESET}{C_CLR_EOL}")
        header_title = " FUNA Wrapper for Peanut - Dual Master Console "
        active_tag = f"[ACTIVE VFO: {self.active_target}]"
        print(f"{C_BLUE_BG}{C_WHITE}{C_BOLD}║ {header_title}{active_tag.rjust(w - len(header_title) - 4)} ║{C_RESET}{C_CLR_EOL}")
        print(f"{C_BLUE_BG}{C_WHITE}{C_BOLD}╠{'═' * 37}╦{'═' * 38}╣{C_RESET}{C_CLR_EOL}")

        tag_jp = " [1] JP MASTER " + ("(★ACTIVE/TX)" if self.active_target == "JP" else "            ")
        tag_gl = " [2] GLOBAL MASTER " + ("(★ACTIVE/TX)" if self.active_target == "GLOBAL" else "        ")
        print(f"{C_BLUE_BG}{C_WHITE}║{C_YELLOW if self.active_target == 'JP' else C_WHITE}{tag_jp:<37}{C_WHITE}║{C_YELLOW if self.active_target == 'GLOBAL' else C_WHITE}{tag_gl:<38}{C_WHITE}║{C_RESET}{C_CLR_EOL}")
        print(f"{C_BLUE_BG}{C_WHITE}╠{'─' * 37}╫{'─' * 38}╣{C_RESET}{C_CLR_EOL}")

        col1 = [
            f"State: {jp_st}", f"Room : {jp_room}", f"Desc : {jp_desc[:25]}",
            f"Call : {jp_call}", f"Name : {jp_name[:25]}"
        ]
        col2 = [
            f"State: {gl_st}", f"Room : {gl_room}", f"Desc : {gl_desc[:25]}",
            f"Call : {gl_call}", f"Name : {gl_name[:25]}"
        ]

        for c1, c2 in zip(col1, col2):
            print(f"{C_BLUE_BG}{C_WHITE}║ {c1:<35} ║ {c2:<36} ║{C_RESET}{C_CLR_EOL}")

        print(f"{C_BLUE_BG}{C_WHITE}╠{'═' * (w - 2)}╣{C_RESET}{C_CLR_EOL}")
        print(f"{C_BLUE_BG}{C_WHITE}║ {C_CYAN}LAST HEARD ACTIVITY LOG (Dual Simultaneous Watch):{C_WHITE}{' ' * (w - 52)}║{C_RESET}{C_CLR_EOL}")
        for i in range(5):
            log_line = self.last_heard_logs[-(i + 1)] if i < len(self.last_heard_logs) else " "
            print(f"{C_BLUE_BG}{C_WHITE}║   {log_line:<72} ║{C_RESET}{C_CLR_EOL}")

        print(f"{C_BLUE_BG}{C_WHITE}╠{'═' * (w - 2)}╣{C_RESET}{C_CLR_EOL}")
        tx_color = f"{C_RED}{C_BOLD}" if "TRANSMITTING" in self.tx_state_str else f"{C_GREEN}"
        ptt_display = f"PTT: {tx_color}[ {self.tx_state_str} ]{C_RESET}{C_BLUE_BG}{C_WHITE} (Hold [SPACE] to Talk)"
        print(f"{C_BLUE_BG}{C_WHITE}║  {ptt_display:<85}║{C_RESET}{C_CLR_EOL}")
        print(f"{C_BLUE_BG}{C_WHITE}╚{'═' * (w - 2)}╝{C_RESET}{C_CLR_EOL}")

        print(f"{C_CYAN}{self.message_line:<78}{C_RESET}{C_CLR_EOL}")
        print(f"{C_GRAY}[Tab]: Switch VFO | [m]: Select Room | [o]: Power On/Off | [q]: Quit{C_RESET}{C_CLR_EOL}")
        print(f"{C_CLR_EOL}", end="", flush=True)

    def show_room_selector(self):
        """MS-DOS風ポップアップ・ルームセレクター"""
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
            pw = 56
            pad_left = " " * 11

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
            title = f" SELECT ROOM [{self.active_target} MASTER] "
            print(f"{pad_left}{C_BLUE_BG}{C_YELLOW}{C_BOLD}║ {title.center(pw - 4)} ║{C_RESET}{C_CLR_EOL}")
            print(f"{pad_left}{C_BLUE_BG}{C_WHITE}╠{'═' * (pw - 2)}╣{C_RESET}{C_CLR_EOL}")

            search_display = f" Search Filter: {filter_text}_"
            print(f"{pad_left}{C_BLUE_BG}{C_CYAN}║ {search_display:<51} ║{C_RESET}{C_CLR_EOL}")
            print(f"{pad_left}{C_BLUE_BG}{C_WHITE}╠{'─' * (pw - 2)}╣{C_RESET}{C_CLR_EOL}")

            for i in range(page_size):
                item_idx = scroll_offset + i
                if item_idx < len(filtered):
                    room_name = filtered[item_idx]
                    if item_idx == selected_idx:
                        line_str = f" ► {room_name}"
                        print(f"{pad_left}{C_BLUE_BG}{C_WHITE}{C_INVERSE}║ {line_str:<51} ║{C_RESET}{C_CLR_EOL}")
                    else:
                        line_str = f"   {room_name}"
                        print(f"{pad_left}{C_BLUE_BG}{C_WHITE}║ {line_str:<51} ║{C_RESET}{C_CLR_EOL}")
                else:
                    print(f"{pad_left}{C_BLUE_BG}{C_WHITE}║{' ' * (pw - 2)}║{C_RESET}{C_CLR_EOL}")

            print(f"{pad_left}{C_BLUE_BG}{C_WHITE}╠{'═' * (pw - 2)}╣{C_RESET}{C_CLR_EOL}")
            status_text = f" [{len(filtered)}/{len(all_rooms)}] <↑/↓>:Move <Enter>:OK <Esc>:Cancel"
            print(f"{pad_left}{C_BLUE_BG}{C_GRAY}║ {status_text:<51} ║{C_RESET}{C_CLR_EOL}")
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
        os.system("cls")
        print("=" * 65)
        print(" FUNA Wrapper for Peanut - Appliance Booting...")
        print("=" * 65)

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
        print(f"\n{C_RESET}FUNA Wrapper for Peanut を終了しました。73 & Good DX!")

if __name__ == "__main__":
    app = FunaWrapperApp()
    app.run()