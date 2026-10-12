"""
==============================================================================
 FUNA Wrapper for Peanut - Dual Master Console (v3.1.0 Appliance Edition)
 
 [Updates]
  - 100% Pure Win32 PTT (Zero Mouse Jump / Zero Focus Stealing)
  - Auto Minimize Peanut Windows (Clean Dedicated Appliance UI)
  - No Chattering / No Toggle Glitch on Spacebar Hold
  - Robust Post-Connect Room Sync (JP: CQCQCQ-J, GLOBAL: JAPANESE)
  - Ghost-Free Clean Command Line Bar
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

# Windows API 定義
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

VK_SPACE = 0x20
WM_COMMAND = 0x0111
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
BM_CLICK = 0x00F5
GW_ENABLEDPOPUP = 6
SW_MINIMIZE = 6
CBN_SELCHANGE = 1
CB_FINDSTRINGEXACT = 0x0158
CB_FINDSTRING = 0x014C
CB_SETCURSEL = 0x014E

# ANSI カラー
C_RESET   = "\033[0m"
C_BOLD    = "\033[1m"
C_BLUE_BG = "\033[44m"
C_WHITE   = "\033[97m"
C_CYAN    = "\033[96m"
C_GREEN   = "\033[92m"
C_YELLOW  = "\033[93m"
C_RED     = "\033[91m"
C_GRAY    = "\033[90m"
C_CLR_EOL = "\033[K"    # 行末までクリア

def enable_vt_mode():
    h_out = kernel32.GetStdHandle(-11)
    mode = ctypes.c_ulong()
    kernel32.GetConsoleMode(h_out, ctypes.byref(mode))
    mode.value |= 0x0004 | 0x0001 | 0x0002
    kernel32.SetConsoleMode(h_out, mode)

class PeanutFastInstance:
    def __init__(self, hwnd, label="PEANUT"):
        self.hwnd = hwnd
        self.label = label
        self.app = Application(backend="uia").connect(handle=hwnd)
        self.main_win = self.app.window(handle=hwnd)

        # コントロールキャッシュ
        self.ctrl_ptt_label = self.main_win.child_window(auto_id="PTTlabel", control_type="Text")
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

    def minimize(self):
        """Peanutウィンドウを最小化（タスクバーに格納）"""
        user32.ShowWindow(self.hwnd, SW_MINIMIZE)

    def is_tx(self) -> bool:
        try:
            return "PTT ON" in self.ctrl_ptt_label.window_text()
        except Exception:
            return False

    def get_status(self) -> dict:
        st = {"state": "OFFLINE", "call": "", "name": "", "room": "", "desc": "", "country": ""}
        try:
            st["state"] = self.ctrl_ptt_label.window_text()
            st["call"] = self.ctrl_his_call.window_text()
            st["name"] = self.ctrl_his_name.window_text()
            st["room"] = self.ctrl_room_combo.window_text()
            st["desc"] = self.ctrl_room_desc.window_text()
            st["country"] = self.ctrl_country_combo.window_text()
        except Exception:
            pass
        return st

    def _click_pane_pure(self, hwnd_pane):
        """マウスを1ミリも動かさずにPaneコントロールへ左クリックメッセージを直接送る"""
        rect = ctypes.wintypes.RECT()
        user32.GetClientRect(hwnd_pane, ctypes.byref(rect))
        cx = (rect.right - rect.left) // 2
        cy = (rect.bottom - rect.top) // 2
        lparam = (cy << 16) | (cx & 0xFFFF)
        user32.PostMessageW(hwnd_pane, WM_LBUTTONDOWN, 1, lparam)
        time.sleep(0.04)
        user32.PostMessageW(hwnd_pane, WM_LBUTTONUP, 0, lparam)

    def toggle_on_off(self):
        """On/Off スイッチを純粋メッセージ送信でトグル"""
        self._click_pane_pure(self.hwnd_onoff_switch)

    def tx_on(self):
        """PTT押下 (マウス移動・フォーカス移動ゼロでTX開始)"""
        if not self.is_tx():
            self._click_pane_pure(self.hwnd_onair_switch)

    def tx_off(self):
        """PTT解除 (マウス移動・フォーカス移動ゼロでRX待機)"""
        if self.is_tx():
            self._click_pane_pure(self.hwnd_onair_switch)

    def set_room_fast(self, room_name: str) -> bool:
        """Win32 APIで一瞬でRoom変更"""
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
        """非同期PostMessageによる完全自動Setup"""
        try:
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
                return False

            master_combo = setup_dlg.child_window(auto_id="masterlistComboBox", control_type="ComboBox")
            hwnd_combo = master_combo.handle
            idx = user32.SendMessageW(hwnd_combo, CB_FINDSTRINGEXACT, -1, target_master_name)
            if idx != -1:
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

            return True
        except Exception:
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
        self.message_line = "Ready. Press [Tab] to Switch, Hold [SPACE] to Talk."
        self.tx_state_str = "IDLE (RX Ready)"
        self.needs_redraw = True

    def boot_and_setup(self):
        print("[1/5] Peanutプロセスの検出中...")
        desktop = Desktop(backend="uia")

        def get_valid_wins():
            wins = desktop.windows(title="Peanut", class_name_re=".*WindowsForms.*")
            return [w for w in wins if w.is_visible() and w.rectangle().width() > 100]

        valid_wins = get_valid_wins()
        needed = 2 - len(valid_wins)

        if needed > 0:
            print(f"-> Peanutを {needed} 個起動中...")
            if PEANUT_EXE_PATH and os.path.exists(PEANUT_EXE_PATH):
                for _ in range(needed):
                    subprocess.Popen([PEANUT_EXE_PATH], shell=True)
                    time.sleep(3.0)
            else:
                print("【注意】Peanut.exeが見つかりません。手動起動を確認してください。")

            for _ in range(15):
                valid_wins = get_valid_wins()
                if len(valid_wins) >= 2:
                    break
                time.sleep(1.0)

        if len(valid_wins) < 2:
            print("【警告】Peanutが2つ揃いませんでした。")
            if len(valid_wins) == 1:
                self.inst_jp = PeanutFastInstance(valid_wins[0].handle, label="JP MASTER")
            return

        print(f"-> 2つのPeanutを捕捉！(HWND: {valid_wins[0].handle}, {valid_wins[1].handle})")
        inst1 = PeanutFastInstance(valid_wins[0].handle, label="INST-1")
        inst2 = PeanutFastInstance(valid_wins[1].handle, label="INST-2")

        print("[2/5] Masterサーバーの全自動構成中...")
        inst1.configure_master_pure("Japan")
        inst2.configure_master_pure("Global")

        self.inst_jp = inst1
        self.inst_gl = inst2
        self.inst_jp.label = "JP MASTER"
        self.inst_gl.label = "GLOBAL MASTER"

        print("[3/5] セッション接続 (Auto Power ON)...")
        time.sleep(0.5)
        self.inst_jp.toggle_on_off()
        time.sleep(0.6)
        self.inst_gl.toggle_on_off()

        print("[4/5] サーバー接続待機 & デフォルト待機Room同期...")
        # 接続後、サーバーからルームリストがフェッチされるのを待機
        for wait_sec in range(3, 0, -1):
            print(f"\r  サーバーリスト同期待機中... ({wait_sec}s)", end="", flush=True)
            time.sleep(1.0)
        print("\r  ルーム設定を同期中...                                    ")

        # JPとGlobalの初期ルームを設定（リトライ機構付き）
        self.inst_jp.set_room_fast(DEFAULT_ROOM_JP)
        for _ in range(5):
            if self.inst_gl.set_room_fast(DEFAULT_ROOM_GLOBAL):
                print(f"  -> GLOBAL Room を '{DEFAULT_ROOM_GLOBAL}' に同期成功！")
                break
            time.sleep(0.8)

        print("[5/5] Peanut本体ウィンドウを最小化中 (アプライアンス化)...")
        time.sleep(0.5)
        self.inst_jp.minimize()
        self.inst_gl.minimize()

        print("-> 準備完了！FUNA Wrapper TUI を起動します...")
        time.sleep(0.8)

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

                if updated:
                    self.needs_redraw = True

            except Exception:
                pass
            time.sleep(0.2)

    def momentary_ptt_thread(self):
        """物理スペースキー判定（フォーカス移動ゼロ・純粋メッセージ制御）"""
        was_pressed = False
        while self.running:
            is_pressed = (user32.GetAsyncKeyState(VK_SPACE) & 0x8000) != 0
            if is_pressed and not was_pressed:
                target = self.get_active_inst()
                if target:
                    target.tx_on()
                    self.tx_state_str = f"TRANSMITTING (TX -> {self.active_target})"
                    self.needs_redraw = True
                was_pressed = True
            elif not is_pressed and was_pressed:
                target = self.get_active_inst()
                if target:
                    target.tx_off()
                    self.tx_state_str = "IDLE (RX Ready)"
                    self.needs_redraw = True
                was_pressed = False
            time.sleep(0.01)

    def render_tui(self):
        """MS-DOS Blue Classic Fullscreen TUI"""
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

        # 最下部コマンド＆ステータスバー (残骸を絶対に出さない行末クリア付き)
        print(f"{C_CYAN}{self.message_line:<78}{C_RESET}{C_CLR_EOL}")
        print(f"{C_GRAY}[Tab]: Switch VFO | [m]: Change Room | [o]: Power On/Off | [q]: Quit{C_RESET}{C_CLR_EOL}")
        print(f"{C_CLR_EOL}", end="", flush=True)

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
            if self.needs_redraw:
                self.render_tui()
                self.needs_redraw = False

            if msvcrt.kbhit():
                ch = msvcrt.getwch()

                # [Tab]: VFO A/B 瞬時スイッチ
                if ch == "\t":
                    if self.inst_gl:
                        self.active_target = "GLOBAL" if self.active_target == "JP" else "JP"
                        self.message_line = f"Active VFO switched to [{self.active_target}]."
                    else:
                        self.message_line = "Global instance is disabled."
                    self.needs_redraw = True

                # [o]: 電源 On/Off トグル
                elif ch.lower() == "o":
                    target = self.get_active_inst()
                    target.toggle_on_off()
                    self.message_line = f"Toggled Connect/Disconnect on [{self.active_target}]."
                    self.needs_redraw = True

                # [m]: クリーンなルーム変更入力
                elif ch.lower() == "m":
                    sys.stdout.write(f"\r\033[K{C_YELLOW}[{self.active_target}] Enter Room Name: {C_RESET}")
                    sys.stdout.flush()
                    
                    room_name = input().strip()
                    if room_name:
                        self.message_line = f"Changing room to '{room_name}' on [{self.active_target}]..."
                        target = self.get_active_inst()
                        if target.set_room_fast(room_name):
                            self.message_line = f"Successfully joined '{room_name}' on [{self.active_target}]."
                        else:
                            self.message_line = f"Room '{room_name}' not found."
                    
                    # 入力完了後に画面全消去＆再描画で残骸を完全消去
                    os.system("cls")
                    self.render_tui()

                # [q]: 終了
                elif ch.lower() == "q":
                    break

            time.sleep(0.02)

        self.running = False
        print(f"\n{C_RESET}FUNA Wrapper for Peanut を終了しました。73 & Good DX!")

if __name__ == "__main__":
    app = FunaWrapperApp()
    app.run()