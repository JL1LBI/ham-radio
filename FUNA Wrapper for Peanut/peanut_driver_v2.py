"""
FUNA Wrapper for Peanut - Core Driver (v2 高速版 & モーメンタリー対応)
"""

import time
import sys
import ctypes
from pywinauto import Desktop, Application

# Windows標準API (SendMessage用)
user32 = ctypes.windll.user32
CB_GETCOUNT = 0x0146
CB_GETLBTEXTLEN = 0x0149
CB_GETLBTEXT = 0x0148

class PeanutDriver:
    def __init__(self):
        self.app = None
        self.main_win = None
        # コントロールのキャッシュ
        self.ctrl_ptt_label = None
        self.ctrl_his_call = None
        self.ctrl_his_name = None
        self.ctrl_message = None
        self.ctrl_room_combo = None
        self.ctrl_room_desc = None
        self.ctrl_country_combo = None
        self.ctrl_onair_switch = None
        self.ctrl_onoff_switch = None

    def connect(self) -> bool:
        """Peanutに接続し、全コントロールをキャッシュして高速化する"""
        try:
            desktop = Desktop(backend="uia")
            candidates = desktop.windows(title="Peanut", class_name_re=".*WindowsForms.*")
            valid_wins = [w for w in candidates if w.is_visible() and w.rectangle().width() > 100]
            
            if not valid_wins:
                candidates = desktop.windows(title_re=".*Peanut.*")
                valid_wins = [w for w in candidates if w.is_visible() and w.rectangle().width() > 100]

            if not valid_wins:
                return False

            valid_wins.sort(key=lambda w: w.rectangle().width() * w.rectangle().height(), reverse=True)
            target = valid_wins[0]

            self.app = Application(backend="uia").connect(handle=target.handle)
            self.main_win = self.app.window(handle=target.handle)

            # --- 各コントロールをあらかじめキャッシュ（高速化） ---
            self.ctrl_ptt_label = self.main_win.child_window(auto_id="PTTlabel", control_type="Text")
            self.ctrl_his_call = self.main_win.child_window(auto_id="hisCallLabel", control_type="Text")
            self.ctrl_his_name = self.main_win.child_window(auto_id="nameStaticLabel", control_type="Text")
            self.ctrl_message = self.main_win.child_window(auto_id="messageLabel", control_type="Text")
            self.ctrl_room_combo = self.main_win.child_window(auto_id="RoomComboBox", control_type="ComboBox")
            self.ctrl_room_desc = self.main_win.child_window(auto_id="roomDescriptionLabel", control_type="Text")
            self.ctrl_country_combo = self.main_win.child_window(auto_id="countryComboBox", control_type="ComboBox")
            self.ctrl_onair_switch = self.main_win.child_window(auto_id="onAIRswitch")
            self.ctrl_onoff_switch = self.main_win.child_window(auto_id="OnOffToggleSwitch")

            return True
        except Exception as e:
            print(f"[Driver Connect Error] {e}")
            return False

    def is_transmitting(self) -> bool:
        """現在送信中 (TX) かどうかを判定"""
        try:
            text = self.ctrl_ptt_label.window_text()
            return "PTT ON" in text or "TX" in text
        except Exception:
            return False

    def get_status(self) -> dict:
        """全ステータスを高速取得"""
        if not self.main_win:
            return {}

        status = {
            "ptt_state": "UNKNOWN",
            "his_call": "",
            "his_name": "",
            "message": "",
            "room": "",
            "room_desc": "",
            "country": "",
        }

        try:
            status["ptt_state"] = self.ctrl_ptt_label.window_text()
            status["his_call"] = self.ctrl_his_call.window_text()
            status["his_name"] = self.ctrl_his_name.window_text()
            status["message"] = self.ctrl_message.window_text()
            status["room"] = self.ctrl_room_combo.window_text()
            status["room_desc"] = self.ctrl_room_desc.window_text()
            status["country"] = self.ctrl_country_combo.window_text()
        except Exception as e:
            status["error"] = str(e)

        return status

    def get_room_list(self) -> list:
        """Win32 API (SendMessage) を使ってRoom一覧を瞬時に全件取得"""
        try:
            hwnd = self.ctrl_room_combo.handle
            count = user32.SendMessageW(hwnd, CB_GETCOUNT, 0, 0)
            rooms = []
            for i in range(count):
                length = user32.SendMessageW(hwnd, CB_GETLBTEXTLEN, i, 0)
                buffer = ctypes.create_unicode_buffer(length + 1)
                user32.SendMessageW(hwnd, CB_GETLBTEXT, i, buffer)
                rooms.append(buffer.value)
            return rooms
        except Exception as e:
            print(f"Room一覧取得エラー: {e}")
            return []

    # --- PTT モーメンタリー制御 (TX On / TX Off) ---

    def tx_on(self):
        """送信開始（現在受信中ならPTTをONにする）"""
        if not self.is_transmitting():
            try:
                self.ctrl_onair_switch.click_input()
                return True
            except Exception as e:
                print(f"tx_on エラー: {e}")
        return False

    def tx_off(self):
        """送信終了（現在送信中ならPTTをOFFにする）"""
        if self.is_transmitting():
            try:
                self.ctrl_onair_switch.click_input()
                return True
            except Exception as e:
                print(f"tx_off エラー: {e}")
        return False

    # --- その他の操作 ---

    def toggle_on_off(self):
        """Online / Offline 切り替え"""
        try:
            self.ctrl_onoff_switch.click_input()
            return True
        except Exception as e:
            print(f"toggle_on_off エラー: {e}")
            return False

    def set_room(self, room_name: str):
        """Room名を指定して切り替え"""
        try:
            self.ctrl_room_combo.select(room_name)
            return True
        except Exception as e:
            print(f"set_room エラー: {e}")
            return False


# --- テスト用コンソール ---
def test():
    driver = PeanutDriver()
    print("Peanutに接続中 (キャッシュ構築)...")
    if not driver.connect():
        print("Peanutが見つかりません。")
        return
    print("接続完了！\n")

    # 1. 高速Room一覧取得テスト
    t0 = time.time()
    rooms = driver.get_room_list()
    elapsed = (time.time() - t0) * 1000
    print(f"[Win32 API] 取得したRoom数: {len(rooms)} 件 ({elapsed:.1f} ms)")
    if rooms:
        print(f"ルーム先頭10件: {', '.join(rooms[:10])}\n")

    # 2. ステータス取得の速度テスト
    t0 = time.time()
    status = driver.get_status()
    elapsed = (time.time() - t0) * 1000
    print(f"[ステータス取得] ({elapsed:.1f} ms): {status}\n")

    # 3. モーメンタリーPTTの擬似テスト (3秒間だけTXにして自動でRXに戻す)
    print(">>> モーメンタリーPTTテスト: [TX開始] -> (3秒待機) -> [TX終了]")
    driver.tx_on()
    time.sleep(0.5)
    print("  現在の状態:", driver.ctrl_ptt_label.window_text())
    
    time.sleep(2.5)
    driver.tx_off()
    time.sleep(0.5)
    print("  現在の状態:", driver.ctrl_ptt_label.window_text())
    print("\nドライバテスト完了！")

if __name__ == "__main__":
    test()