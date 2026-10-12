"""
FUNA Wrapper for Peanut - Dual Instance Controller & Momentary PTT Test
"""

import time
import sys
import ctypes
import threading
from pywinauto import Desktop, Application

# Windows API
user32 = ctypes.windll.user32
VK_SPACE = 0x20
CB_GETCOUNT = 0x0146
CB_GETLBTEXTLEN = 0x0149
CB_GETLBTEXT = 0x0148

class PeanutInstance:
    """単一のPeanutウィンドウを制御するクラス"""
    def __init__(self, handle, label="Peanut"):
        self.handle = handle
        self.label = label
        self.app = Application(backend="uia").connect(handle=handle)
        self.main_win = self.app.window(handle=handle)

        # 各コントロールのキャッシュ
        self.ctrl_ptt_label = self.main_win.child_window(auto_id="PTTlabel", control_type="Text")
        self.ctrl_his_call = self.main_win.child_window(auto_id="hisCallLabel", control_type="Text")
        self.ctrl_his_name = self.main_win.child_window(auto_id="nameStaticLabel", control_type="Text")
        self.ctrl_message = self.main_win.child_window(auto_id="messageLabel", control_type="Text")
        self.ctrl_room_combo = self.main_win.child_window(auto_id="RoomComboBox", control_type="ComboBox")
        self.ctrl_room_desc = self.main_win.child_window(auto_id="roomDescriptionLabel", control_type="Text")
        self.ctrl_country_combo = self.main_win.child_window(auto_id="countryComboBox", control_type="ComboBox")
        self.ctrl_onair_switch = self.main_win.child_window(auto_id="onAIRswitch")
        self.ctrl_onoff_switch = self.main_win.child_window(auto_id="OnOffToggleSwitch")

    def is_transmitting(self) -> bool:
        try:
            return "PTT ON" in self.ctrl_ptt_label.window_text()
        except Exception:
            return False

    def get_status(self) -> dict:
        status = {"state": "OFFLINE", "call": "", "name": "", "room": "", "desc": "", "country": ""}
        try:
            status["state"] = self.ctrl_ptt_label.window_text()
            status["call"] = self.ctrl_his_call.window_text()
            status["name"] = self.ctrl_his_name.window_text()
            status["room"] = self.ctrl_room_combo.window_text()
            status["desc"] = self.ctrl_room_desc.window_text()
            status["country"] = self.ctrl_country_combo.window_text()
        except Exception:
            pass
        return status

    def tx_on(self):
        if not self.is_transmitting():
            try:
                self.ctrl_onair_switch.click_input()
            except Exception:
                pass

    def tx_off(self):
        if self.is_transmitting():
            try:
                self.ctrl_onair_switch.click_input()
            except Exception:
                pass

    def toggle_on_off(self):
        try:
            self.ctrl_onoff_switch.click_input()
        except Exception:
            pass

    def set_room(self, room_name: str):
        try:
            self.ctrl_room_combo.select(room_name)
        except Exception:
            pass


class DualPeanutController:
    """2つのPeanut（JP / Global）を統合管理するクラス"""
    def __init__(self):
        self.inst_jp = None
        self.inst_global = None
        self.active_target = "JP"  # "JP" または "GLOBAL"
        self.running = False

    def auto_detect_and_connect(self) -> bool:
        desktop = Desktop(backend="uia")
        candidates = desktop.windows(title="Peanut", class_name_re=".*WindowsForms.*")
        valid_wins = [w for w in candidates if w.is_visible() and w.rectangle().width() > 100]

        if len(valid_wins) < 2:
            print(f"【警告】検出されたPeanutウィンドウは {len(valid_wins)} 個です。")
            if len(valid_wins) == 1:
                print("1つ目のPeanutのみを [JP] として接続します（2重起動するとデュアル動作になります）。")
                self.inst_jp = PeanutInstance(valid_wins[0].handle, label="JP")
                return True
            return False

        print(f"-> 2つのPeanutを検出しました！(Handle: {valid_wins[0].handle}, {valid_wins[1].handle})")

        # 暫定的に1つ目をJP、2つ目をGLOBALとしてインスタンス化
        # （後でCountry等の内容を見て自動スワップ可能）
        self.inst_jp = PeanutInstance(valid_wins[0].handle, label="JP")
        self.inst_global = PeanutInstance(valid_wins[1].handle, label="GLOBAL")

        # Country設定から自動判定（もし2つ目がJPなら入れ替え）
        st0 = self.inst_jp.get_status()
        st1 = self.inst_global.get_status()
        if st1.get("country") == "JP" and st0.get("country") != "JP":
            self.inst_jp, self.inst_global = self.inst_global, self.inst_jp

        print(f"  [JP Master]     割り当て: Room={self.inst_jp.get_status().get('room')}")
        print(f"  [Global Master] 割り当て: Room={self.inst_global.get_status().get('room')}")
        return True

    def get_active_instance(self) -> PeanutInstance:
        if self.active_target == "JP":
            return self.inst_jp
        return self.inst_global if self.inst_global else self.inst_jp

    def switch_target(self):
        """送信・操作の対象を JP <-> GLOBAL でトグル"""
        if self.active_target == "JP" and self.inst_global:
            self.active_target = "GLOBAL"
        else:
            self.active_target = "JP"
        print(f"\n[TARGET SWITCH] 現在の操作対象: >>> {self.active_target} <<<")

    def start_momentary_ptt_listener(self):
        """物理スペースキーの状態を監視する超高速バックグラウンドスレッド"""
        def listener():
            was_pressed = False
            while self.running:
                # 物理キー状態の取得 (最上位ビットが1なら押下中)
                is_pressed = (user32.GetAsyncKeyState(VK_SPACE) & 0x8000) != 0

                if is_pressed and not was_pressed:
                    # キーが「押された」瞬間 -> TX開始
                    target = self.get_active_instance()
                    if target:
                        target.tx_on()
                        print(f"\r[PTT >> TX ON] ({self.active_target})  ", end="", flush=True)
                    was_pressed = True

                elif not is_pressed and was_pressed:
                    # キーが「離された」瞬間 -> TX終了
                    target = self.get_active_instance()
                    if target:
                        target.tx_off()
                        print(f"\r[PTT -- RX IDLE] ({self.active_target})", end="", flush=True)
                    was_pressed = False

                time.sleep(0.01)  # 10ms周期でポーリング（超低遅延）

        self.running = True
        t = threading.Thread(target=listener, daemon=True)
        t.start()


# --- デュアルコントローラーの対話型動作テスト ---
def main():
    print("=" * 65)
    print(" FUNA Wrapper for Peanut - Dual Controller Engine Test")
    print("=" * 65)

    controller = DualPeanutController()
    if not controller.auto_detect_and_connect():
        print("Peanutが起動していません。起動してから再実行してください。")
        return

    # モーメンタリーPTT監視スレッド起動
    controller.start_momentary_ptt_listener()

    print("\n【操作ガイド】")
    print("  ・[スペースキー長押し] : 押している間だけTX、離すとRX (モーメンタリーPTT)")
    print("  ・t : 操作対象を切り替え (JP <-> GLOBAL)")
    print("  ・s : 両方の現在のステータスを画面表示")
    print("  ・m : アクティブ側のRoomを変更")
    print("  ・q : テスト終了\n")

    while True:
        try:
            cmd = input().strip()
            if cmd == "q":
                break
            elif cmd == "t":
                controller.switch_target()
            elif cmd == "s":
                st_jp = controller.inst_jp.get_status() if controller.inst_jp else {}
                st_gl = controller.inst_global.get_status() if controller.inst_global else {}
                print("\n" + "=" * 60)
                print(f" [JP Master]     State: {st_jp.get('state')} | Room: {st_jp.get('room')} | Call: {st_jp.get('call')}")
                print(f" [Global Master] State: {st_gl.get('state')} | Room: {st_gl.get('room')} | Call: {st_gl.get('call')}")
                print(f" 操作ターゲット: >>> {controller.active_target} <<<")
                print("=" * 60 + "\n")
            elif cmd == "m":
                target_room = input(f"[{controller.active_target}] 変更するRoom名を入力: ").strip()
                if target_room:
                    controller.get_active_instance().set_room(target_room)
                    print(f"Roomを変更しました -> {target_room}")
        except KeyboardInterrupt:
            break

    controller.running = False
    print("\nテスト終了。")

if __name__ == "__main__":
    main()