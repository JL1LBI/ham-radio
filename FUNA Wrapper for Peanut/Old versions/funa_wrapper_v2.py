"""
==============================================================================
 FUNA Wrapper for Peanut - Dual Master Console (v2.0.0)
 Auto-Launch, Auto-Setup (Japan & Global), Instant Tab-Switch & Real-time TUI
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

# --- 設定 ---
PEANUT_EXE_NAME = "C:\Program Files (x86)\Peanut\Peanut\peanut.exe"
# Peanut.exeのフルパス（カレントディレクトリにある場合はそのままでOK）
PEANUT_EXE_PATH = os.path.join(os.getcwd(), PEANUT_EXE_NAME)

# Windows API
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

VK_SPACE = 0x20
WM_COMMAND = 0x0111
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

def enable_vt_mode():
    h_out = kernel32.GetStdHandle(-11)
    mode = ctypes.c_ulong()
    kernel32.GetConsoleMode(h_out, ctypes.byref(mode))
    mode.value |= 0x0004 | 0x0001 | 0x0002
    kernel32.SetConsoleMode(h_out, mode)

class PeanutFastInstance:
    """単一のPeanutインスタンス操作用クラス"""
    def __init__(self, hwnd, label="PEANUT"):
        self.hwnd = hwnd
        self.label = label
        self.app = Application(backend="uia").connect(handle=hwnd)
        self.main_win = self.app.window(handle=hwnd)

        # キャッシュ
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

    def toggle_on_off(self):
        try:
            self.ctrl_onoff_switch.click_input()
        except Exception:
            pass

    def tx_on(self):
        if not self.is_tx():
            try:
                self.ctrl_onair_switch.click_input()
            except Exception:
                pass

    def tx_off(self):
        if self.is_tx():
            try:
                self.ctrl_onair_switch.click_input()
            except Exception:
                pass

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

    def configure_master(self, master_name: str):
        """Setup画面を開き、Masterを設定してSaveする"""
        try:
            self.ctrl_setup_btn.click_input()
            time.sleep(1.0)
            
            # Setupダイアログを取得
            setup_dlg = self.app.window(auto_id="SetupForm")
            if not setup_dlg.exists(timeout=3):
                return False

            master_combo = setup_dlg.child_window(auto_id="masterlistComboBox", control_type="ComboBox")
            save_btn = setup_dlg.child_window(auto_id="saveButton", control_type="Button")

            # Masterを選択
            master_combo.select(master_name)
            time.sleep(0.3)
            save_btn.click_input()
            time.sleep(1.0)
            return True
        except Exception as e:
            print(f"Setup自動設定エラー ({self.label}): {e}")
            return False


class FunaDualApp:
    def __init__(self):
        self.inst_jp = None
        self.inst_gl = None
        self.active_target = "JP"  # "JP" or "GLOBAL"
        self.running = True
        self.status_jp = {}
        self.status_gl = {}
        self.last_heard_logs = []
        self.message_line = "Ready. Press [?] for Help."
        self.tx_state_str = "IDLE (RX Ready)"
        self.needs_redraw = True

    def ensure_peanuts_running(self):
        """Peanutが2つ起動していなければ自動起動し、初期設定を行う"""
        print("[1/3] Peanutインスタンスの検出中...")
        desktop = Desktop(backend="uia")
        
        def get_valid_wins():
            wins = desktop.windows(title="Peanut", class_name_re=".*WindowsForms.*")
            return [w for w in wins if w.is_visible() and w.rectangle().width() > 100]

        valid_wins = get_valid_wins()
        
        # 不足分を起動
        needed = 2 - len(valid_wins)
        if needed > 0:
            print(f"-> Peanutが {needed} 個不足しています。自動起動します...")
            if not os.path.exists(PEANUT_EXE_PATH):
                print(f"【注意】'{PEANUT_EXE_PATH}' が見つかりません。")
                print("手動でPeanutを2つ起動してから再実行してください。")
            else:
                for _ in range(needed):
                    subprocess.Popen([PEANUT_EXE_PATH], shell=True)
                    time.sleep(2.5)
            
            # 起動待機
            for _ in range(10):
                valid_wins = get_valid_wins()
                if len(valid_wins) >= 2:
                    break
                time.sleep(1.0)

        if len(valid_wins) < 2:
            print("【警告】2つのPeanutを起動できませんでした。起動中のものだけで接続します。")
            if len(valid_wins) == 1:
                self.inst_jp = PeanutFastInstance(valid_wins[0].handle, label="JP MASTER")
            return

        print("-> 2つのPeanutを捕捉しました。初期自動設定中...")
        inst1 = PeanutFastInstance(valid_wins[0].handle, label="INST1")
        inst2 = PeanutFastInstance(valid_wins[1].handle, label="INST2")

        # 1つ目をJapan、2つ目をGlobalに設定
        print("  - INST1 を [Japan] に構成中...")
        inst1.configure_master("Japan")
        print("  - INST2 を [Global] に構成中...")
        inst2.configure_master("Global")

        self.inst_jp = inst1
        self.inst_gl = inst2
        self.inst_jp.label = "JP MASTER"
        self.inst_gl.label = "GLOBAL MASTER"

        # 両方を自動で On (Online) にする
        print("-> セッション接続 (Auto Power ON)...")
        time.sleep(0.5)
        self.inst_jp.toggle_on_off()
        self.inst_gl.toggle_on_off()
        time.sleep(1.0)
        print("-> 初期設定完了！TUIを起動します。")

    def get_active_inst(self) -> PeanutFastInstance:
        if self.active_target == "JP" or not self.inst_gl:
            return self.inst_jp
        return self.inst_gl

    def background_poller(self):
        """ステータスと受信履歴を常時リアルタイム監視"""
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
        """超低遅延スペースキー判定"""
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
        """画面をちらつかせずに再描画 (カーソルを左上に移動)"""
        # ANSIカーソルホーム位置移動 (clsより高速・ちらつきゼロ)
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

        print(f"{C_BLUE_BG}{C_WHITE}{C_BOLD}╔{'═' * (w - 2)}╗{C_RESET}")
        header_title = " FUNA Wrapper for Peanut - Dual Master Console "
        active_tag = f"[ACTIVE: {self.active_target}]"
        print(f"{C_BLUE_BG}{C_WHITE}{C_BOLD}║ {header_title}{active_tag.rjust(w - len(header_title) - 4)} ║{C_RESET}")
        print(f"{C_BLUE_BG}{C_WHITE}{C_BOLD}╠{'═' * 37}╦{'═' * 38}╣{C_RESET}")

        tag_jp = " [1] JP MASTER " + ("(★ACTIVE)" if self.active_target == "JP" else "         ")
        tag_gl = " [2] GLOBAL MASTER " + ("(★ACTIVE)" if self.active_target == "GLOBAL" else "     ")
        print(f"{C_BLUE_BG}{C_WHITE}║{C_YELLOW if self.active_target == 'JP' else C_WHITE}{tag_jp:<37}{C_WHITE}║{C_YELLOW if self.active_target == 'GLOBAL' else C_WHITE}{tag_gl:<38}{C_WHITE}║{C_RESET}")
        print(f"{C_BLUE_BG}{C_WHITE}╠{'─' * 37}╫{'─' * 38}╣{C_RESET}")

        col1 = [
            f"State: {jp_st}", f"Room : {jp_room}", f"Desc : {jp_desc[:25]}",
            f"Call : {jp_call}", f"Name : {jp_name[:25]}"
        ]
        col2 = [
            f"State: {gl_st}", f"Room : {gl_room}", f"Desc : {gl_desc[:25]}",
            f"Call : {gl_call}", f"Name : {gl_name[:25]}"
        ]

        for c1, c2 in zip(col1, col2):
            print(f"{C_BLUE_BG}{C_WHITE}║ {c1:<35} ║ {c2:<36} ║{C_RESET}")

        print(f"{C_BLUE_BG}{C_WHITE}╠{'═' * (w - 2)}╣{C_RESET}")
        print(f"{C_BLUE_BG}{C_WHITE}║ {C_CYAN}LAST HEARD ACTIVITY LOG:{C_WHITE}{' ' * (w - 27)}║{C_RESET}")
        for i in range(5):
            log_line = self.last_heard_logs[-(i + 1)] if i < len(self.last_heard_logs) else " "
            print(f"{C_BLUE_BG}{C_WHITE}║   {log_line:<72} ║{C_RESET}")

        print(f"{C_BLUE_BG}{C_WHITE}╠{'═' * (w - 2)}╣{C_RESET}")
        tx_color = f"{C_RED}{C_BOLD}" if "TRANSMITTING" in self.tx_state_str else f"{C_GREEN}"
        ptt_display = f"PTT: {tx_color}[ {self.tx_state_str} ]{C_RESET}{C_BLUE_BG}{C_WHITE} (Hold [SPACE] to Talk)"
        print(f"{C_BLUE_BG}{C_WHITE}║  {ptt_display:<85}║{C_RESET}")
        print(f"{C_BLUE_BG}{C_WHITE}╚{'═' * (w - 2)}╝{C_RESET}")

        print(f"{C_CYAN}{self.message_line:<78}{C_RESET}")
        print(f"{C_GRAY}[Tab]: Switch Target | [o]: On/Off | [m]: Room | [q]: Quit{' ' * 15}{C_RESET}")
        sys.stdout.flush()

    def run(self):
        enable_vt_mode()
        os.system("cls")
        print("=" * 60)
        print(" FUNA Wrapper for Peanut - Engine Booting...")
        print("=" * 60)

        self.ensure_peanuts_running()

        t_poll = threading.Thread(target=self.background_poller, daemon=True)
        t_poll.start()

        t_ptt = threading.Thread(target=self.momentary_ptt_thread, daemon=True)
        t_ptt.start()

        os.system("cls")
        self.render_tui()

        # msvcrt による viノーマルモード即時キー入力ループ
        while self.running:
            if self.needs_redraw:
                self.render_tui()
                self.needs_redraw = False

            if msvcrt.kbhit():
                ch = msvcrt.getwch()

                # Tabキー (即時スイッチ)
                if ch == "\t":
                    if self.inst_gl:
                        self.active_target = "GLOBAL" if self.active_target == "JP" else "JP"
                        self.message_line = f"Switched target to [{self.active_target}]."
                    else:
                        self.message_line = "Global instance is not active."
                    self.needs_redraw = True

                # On/Off 切替
                elif ch.lower() == "o":
                    target = self.get_active_inst()
                    target.toggle_on_off()
                    self.message_line = f"Toggled Connect/Disconnect on [{self.active_target}]."
                    self.needs_redraw = True

                # Room 変更プロンプト
                elif ch.lower() == "m":
                    print(f"\n{C_YELLOW}[{self.active_target}] Enter Room Name: {C_RESET}", end="", flush=True)
                    # 入力中はカーソルを表示
                    room_name = input().strip()
                    if room_name:
                        self.message_line = f"Changing room to '{room_name}' on [{self.active_target}]..."
                        target = self.get_active_inst()
                        if target.set_room_fast(room_name):
                            self.message_line = f"Successfully joined '{room_name}' on [{self.active_target}]."
                        else:
                            self.message_line = f"Room '{room_name}' not found."
                    self.needs_redraw = True

                # 終了
                elif ch.lower() == "q":
                    break

            time.sleep(0.02)  # CPU負荷軽減

        self.running = False
        print(f"\n{C_RESET}FUNA Wrapper for Peanut を終了しました。73!")

if __name__ == "__main__":
    app = FunaDualApp()
    app.run()