"""
==============================================================================
 FUNA Wrapper for Peanut - Dual Master Console (v1.0.0)
 Target: Peanut by David (PA7LIM)
 UI Style: MS-DOS Classic / vi-mode Fullscreen TUI
==============================================================================
"""

import os
import sys
import time
import ctypes
import threading
from datetime import datetime
from pywinauto import Desktop, Application

# Windows API 定義
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

VK_SPACE = 0x20
WM_COMMAND = 0x0111
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
CBN_SELCHANGE = 1
CB_FINDSTRINGEXACT = 0x0158
CB_FINDSTRING = 0x014C
CB_SETCURSEL = 0x014E
CB_GETCOUNT = 0x0146
CB_GETLBTEXTLEN = 0x0149
CB_GETLBTEXT = 0x0148

# ANSI カラーコード (MS-DOS / レトロターミナル風)
C_RESET   = "\033[0m"
C_BOLD    = "\033[1m"
C_BLUE_BG = "\033[44m"  # DOS Blue Background
C_WHITE   = "\033[97m"
C_CYAN    = "\033[96m"
C_GREEN   = "\033[92m"
C_YELLOW  = "\033[93m"
C_RED     = "\033[91m"
C_GRAY    = "\033[90m"
C_INVERSE = "\033[7m"

def enable_vt_mode():
    """WindowsコンソールでANSIエスケープシーケンスを有効化"""
    h_out = kernel32.GetStdHandle(-11)
    mode = ctypes.c_ulong()
    kernel32.GetConsoleMode(h_out, ctypes.byref(mode))
    mode.value |= 0x0004 | 0x0001 | 0x0002  # ENABLE_VIRTUAL_TERMINAL_PROCESSING
    kernel32.SetConsoleMode(h_out, mode)

class PeanutFastInstance:
    """Win32 API直結の超高速Peanutコントローラ"""
    def __init__(self, hwnd, label="PEANUT"):
        self.hwnd = hwnd
        self.label = label
        self.app = Application(backend="uia").connect(handle=hwnd)
        self.main_win = self.app.window(handle=hwnd)

        # UIA要素キャッシュ
        self.ctrl_ptt_label = self.main_win.child_window(auto_id="PTTlabel", control_type="Text")
        self.ctrl_his_call = self.main_win.child_window(auto_id="hisCallLabel", control_type="Text")
        self.ctrl_his_name = self.main_win.child_window(auto_id="nameStaticLabel", control_type="Text")
        self.ctrl_message = self.main_win.child_window(auto_id="messageLabel", control_type="Text")
        self.ctrl_room_combo = self.main_win.child_window(auto_id="RoomComboBox", control_type="ComboBox")
        self.ctrl_room_desc = self.main_win.child_window(auto_id="roomDescriptionLabel", control_type="Text")
        self.ctrl_country_combo = self.main_win.child_window(auto_id="countryComboBox", control_type="ComboBox")
        
        # クリック用のPaneコントロール
        self.ctrl_onair_switch = self.main_win.child_window(auto_id="onAIRswitch")
        self.ctrl_onoff_switch = self.main_win.child_window(auto_id="OnOffToggleSwitch")
        
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
        """フォーカスを奪わずにOn/Offを切り替える"""
        try:
            self.ctrl_onoff_switch.click_input()
        except Exception:
            pass

    def tx_on(self):
        """PTT押下 (TX開始)"""
        if not self.is_tx():
            try:
                self.ctrl_onair_switch.click_input()
            except Exception:
                pass

    def tx_off(self):
        """PTT解除 (RX待機)"""
        if self.is_tx():
            try:
                self.ctrl_onair_switch.click_input()
            except Exception:
                pass

    def set_room_fast(self, room_name: str) -> bool:
        """Win32 APIで数千件の中からでも一瞬でRoomを変更し、通知を送る"""
        try:
            hwnd = self.hwnd_room_combo
            # 1. 完全一致検索
            idx = user32.SendMessageW(hwnd, CB_FINDSTRINGEXACT, -1, room_name)
            if idx == -1:
                # 2. 前方一致検索
                idx = user32.SendMessageW(hwnd, CB_FINDSTRING, -1, room_name)

            if idx != -1:
                # 選択をセット
                user32.SendMessageW(hwnd, CB_SETCURSEL, idx, 0)
                # 親ウィンドウへ選択変更通知 (CBN_SELCHANGE) を発火
                parent = user32.GetParent(hwnd)
                ctrl_id = user32.GetDlgCtrlID(hwnd)
                wparam = (CBN_SELCHANGE << 16) | (ctrl_id & 0xFFFF)
                user32.SendMessageW(parent, WM_COMMAND, wparam, hwnd)
                return True
        except Exception:
            pass
        return False


class FunaTUIApp:
    def __init__(self):
        self.inst_jp = None
        self.inst_gl = None
        self.active_target = "JP"  # "JP" or "GLOBAL"
        self.running = True
        self.status_jp = {}
        self.status_gl = {}
        self.last_heard_logs = []
        self.cmd_buffer = ""
        self.message_line = "Ready. Press [?] for Help."
        self.tx_state_str = "IDLE"

    def connect_peanuts(self) -> bool:
        desktop = Desktop(backend="uia")
        candidates = desktop.windows(title="Peanut", class_name_re=".*WindowsForms.*")
        valid_wins = [w for w in candidates if w.is_visible() and w.rectangle().width() > 100]

        if not valid_wins:
            return False

        if len(valid_wins) >= 2:
            inst1 = PeanutFastInstance(valid_wins[0].handle, label="INST1")
            inst2 = PeanutFastInstance(valid_wins[1].handle, label="INST2")
            
            # CountryがJPのものを特定
            if inst2.get_status().get("country") == "JP":
                self.inst_jp = inst2
                self.inst_gl = inst1
            else:
                self.inst_jp = inst1
                self.inst_gl = inst2
            self.inst_jp.label = "JP MASTER"
            self.inst_gl.label = "GLOBAL MASTER"
        else:
            self.inst_jp = PeanutFastInstance(valid_wins[0].handle, label="JP MASTER")
            self.inst_gl = None

        return True

    def get_active_inst(self) -> PeanutFastInstance:
        if self.active_target == "JP" or not self.inst_gl:
            return self.inst_jp
        return self.inst_gl

    def background_poller(self):
        """ステータスと受信履歴を常時バックグラウンド監視"""
        last_jp_call = ""
        last_gl_call = ""

        while self.running:
            try:
                if self.inst_jp:
                    self.status_jp = self.inst_jp.get_status()
                    c = self.status_jp.get("call", "")
                    if c and c not in ("PTT OFF", "PTT ON", "CALL", "") and c != last_jp_call:
                        now_str = datetime.now().strftime("%H:%M:%S")
                        self.last_heard_logs.append(f"{now_str} [JP]     {c:<10} in {self.status_jp.get('room')}")
                        last_jp_call = c

                if self.inst_gl:
                    self.status_gl = self.inst_gl.get_status()
                    c = self.status_gl.get("call", "")
                    if c and c not in ("PTT OFF", "PTT ON", "CALL", "") and c != last_gl_call:
                        now_str = datetime.now().strftime("%H:%M:%S")
                        self.last_heard_logs.append(f"{now_str} [GLOBAL] {c:<10} in {self.status_gl.get('room')}")
                        last_gl_call = c

                # ログの保持件数制限
                if len(self.last_heard_logs) > 6:
                    self.last_heard_logs = self.last_heard_logs[-6:]

            except Exception:
                pass
            time.sleep(0.3)

    def momentary_ptt_thread(self):
        """超低遅延スペースキー判定 (GetAsyncKeyState)"""
        was_pressed = False
        while self.running:
            is_pressed = (user32.GetAsyncKeyState(VK_SPACE) & 0x8000) != 0
            if is_pressed and not was_pressed:
                # 押された瞬間
                target = self.get_active_inst()
                if target:
                    target.tx_on()
                    self.tx_state_str = f"TRANSMITTING (TX -> {self.active_target})"
                was_pressed = True
            elif not is_pressed and was_pressed:
                # 離された瞬間
                target = self.get_active_inst()
                if target:
                    target.tx_off()
                    self.tx_state_str = "IDLE (RX Ready)"
                was_pressed = False
            time.sleep(0.01)

    def render_tui(self):
        """MS-DOS / vi風のフルスクリーンUIを描画"""
        os.system("cls")
        w = 78  # 画面幅

        # ステータス情報の整形
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
        print(f"{C_BLUE_BG}{C_WHITE}{C_BOLD}╔{'═' * (w - 2)}╗{C_RESET}")
        header_title = " FUNA Wrapper for Peanut - Dual Master Console "
        active_tag = f"[TARGET: {self.active_target}]"
        print(f"{C_BLUE_BG}{C_WHITE}{C_BOLD}║ {header_title}{active_tag.rjust(w - len(header_title) - 4)} ║{C_RESET}")
        print(f"{C_BLUE_BG}{C_WHITE}{C_BOLD}╠{'═' * 37}╦{'═' * 38}╣{C_RESET}")

        # デュアルパネル見出し
        tag_jp = " [1] JP MASTER " + ("(★ACTIVE)" if self.active_target == "JP" else "         ")
        tag_gl = " [2] GLOBAL MASTER " + ("(★ACTIVE)" if self.active_target == "GLOBAL" else "     ")
        print(f"{C_BLUE_BG}{C_WHITE}║{C_YELLOW if self.active_target == 'JP' else C_WHITE}{tag_jp:<37}{C_WHITE}║{C_YELLOW if self.active_target == 'GLOBAL' else C_WHITE}{tag_gl:<38}{C_WHITE}║{C_RESET}")
        print(f"{C_BLUE_BG}{C_WHITE}╠{'─' * 37}╫{'─' * 38}╣{C_RESET}")

        # パネル内部情報
        col1 = [
            f"State: {jp_st}",
            f"Room : {jp_room}",
            f"Desc : {jp_desc[:25]}",
            f"Call : {jp_call}",
            f"Name : {jp_name[:25]}"
        ]
        col2 = [
            f"State: {gl_st}",
            f"Room : {gl_room}",
            f"Desc : {gl_desc[:25]}",
            f"Call : {gl_call}",
            f"Name : {gl_name[:25]}"
        ]

        for c1, c2 in zip(col1, col2):
            print(f"{C_BLUE_BG}{C_WHITE}║ {c1:<35} ║ {c2:<36} ║{C_RESET}")

        # Last Heard ログウィンドウ
        print(f"{C_BLUE_BG}{C_WHITE}╠{'═' * (w - 2)}╣{C_RESET}")
        print(f"{C_BLUE_BG}{C_WHITE}║ {C_CYAN}LAST HEARD ACTIVITY LOG:{C_WHITE}{' ' * (w - 27)}║{C_RESET}")
        for i in range(5):
            if i < len(self.last_heard_logs):
                log_line = self.last_heard_logs[-(i + 1)]
            else:
                log_line = " "
            print(f"{C_BLUE_BG}{C_WHITE}║   {log_line:<72} ║{C_RESET}")

        # PTT ステータスインジケータ
        print(f"{C_BLUE_BG}{C_WHITE}╠{'═' * (w - 2)}╣{C_RESET}")
        tx_color = f"{C_RED}{C_BOLD}" if "TRANSMITTING" in self.tx_state_str else f"{C_GREEN}"
        ptt_display = f"PTT: {tx_color}[ {self.tx_state_str} ]{C_RESET}{C_BLUE_BG}{C_WHITE} (Hold [SPACE] to Talk)"
        print(f"{C_BLUE_BG}{C_WHITE}║  {ptt_display:<85}║{C_RESET}")
        print(f"{C_BLUE_BG}{C_WHITE}╚{'═' * (w - 2)}╝{C_RESET}")

        # 最下部：メッセージライン＆コマンドガイド
        print(f"{C_CYAN}{self.message_line}{C_RESET}")
        print(f"{C_GRAY}<Tab>: Switch | <o>: On/Off | :set <Room> or m: Change Room | :q: Quit{C_RESET}")

    def run(self):
        enable_vt_mode()
        print("Peanutプロセスを検索中...")
        if not self.connect_peanuts():
            print("【エラー】Peanutが起動していません。Peanutを立ち上げてから実行してください。")
            return

        # スレッド起動
        t_poll = threading.Thread(target=self.background_poller, daemon=True)
        t_poll.start()

        t_ptt = threading.Thread(target=self.momentary_ptt_thread, daemon=True)
        t_ptt.start()

        # メインUIループ
        while self.running:
            self.render_tui()
            
            # viライクなコマンド入力待機
            try:
                cmd = input(f"{C_YELLOW}funa:{self.active_target.lower()}> {C_RESET}").strip()
            except (KeyboardInterrupt, EOFError):
                break

            if not cmd:
                continue

            # コマンドディスパッチ
            if cmd in (":q", "q"):
                break
            elif cmd == "\t" or cmd.lower() in ("tab", "t"):
                if self.inst_gl:
                    self.active_target = "GLOBAL" if self.active_target == "JP" else "JP"
                    self.message_line = f"Switched target to [{self.active_target}]."
                else:
                    self.message_line = "Global instance is not available."
            elif cmd == "o":
                target = self.get_active_inst()
                target.toggle_on_off()
                self.message_line = f"Toggled Connect/Disconnect on [{self.active_target}]."
            elif cmd.startswith(":set ") or cmd.startswith(":room ") or cmd == "m":
                if cmd == "m":
                    room_arg = input("Enter Room Name: ").strip()
                else:
                    room_arg = cmd.split(" ", 1)[1].strip()

                if room_arg:
                    target = self.get_active_inst()
                    self.message_line = f"Setting room to '{room_arg}' on [{self.active_target}]..."
                    success = target.set_room_fast(room_arg)
                    if success:
                        self.message_line = f"Successfully joined '{room_arg}' on [{self.active_target}]."
                    else:
                        self.message_line = f"Room '{room_arg}' not found or failed to set."
            elif cmd == "?":
                self.message_line = "Commands: t(Tab switch), o(On/Off), :set <Room>, q(Quit)"
            else:
                self.message_line = f"Unknown command: '{cmd}'. Press [?] for help."

        self.running = False
        print(f"\n{C_RESET}FUNA Wrapper for Peanut を終了しました。73!")

if __name__ == "__main__":
    app = FunaTUIApp()
    app.run()