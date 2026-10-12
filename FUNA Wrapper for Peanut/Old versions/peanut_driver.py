"""
FUNA Wrapper for Peanut - Core Driver & Test CLI
PeanutのGUIコントロールをフックし、状態取得および各種操作を行うバックエンドモジュール
"""

import time
import sys
from pywinauto import Desktop, Application

class PeanutDriver:
    def __init__(self):
        self.app = None
        self.main_win = None

    def connect(self) -> bool:
        """Peanutメインウィンドウを特定して接続する"""
        try:
            desktop = Desktop(backend="uia")
            # メイン画面（サイズが大きいもの）を特定
            candidates = desktop.windows(title="Peanut", class_name_re=".*WindowsForms.*")
            
            valid_wins = [w for w in candidates if w.is_visible() and w.rectangle().width() > 100]
            if not valid_wins:
                # 一般的なタイトル検索でリトライ
                candidates = desktop.windows(title_re=".*Peanut.*")
                valid_wins = [w for w in candidates if w.is_visible() and w.rectangle().width() > 100]

            if not valid_wins:
                return False

            # 最も面積の大きいウィンドウを接続対象とする
            valid_wins.sort(key=lambda w: w.rectangle().width() * w.rectangle().height(), reverse=True)
            target = valid_wins[0]

            self.app = Application(backend="uia").connect(handle=target.handle)
            self.main_win = self.app.window(handle=target.handle)
            return True
        except Exception as e:
            print(f"[Driver Connect Error] {e}")
            return False

    # --- 状態取得系メソッド (Read) ---

    def get_status(self) -> dict:
        """Peanutの現在の全ステータスを一括取得する"""
        if not self.main_win:
            return {}

        status = {
            "ptt_state": "",
            "his_call": "",
            "his_name": "",
            "message": "",
            "room": "",
            "room_desc": "",
            "country": "",
        }

        try:
            # 各ラベルのテキストを取得
            ptt_label = self.main_win.child_window(auto_id="PTTlabel", control_type="Text")
            if ptt_label.exists():
                status["ptt_state"] = ptt_label.window_text()

            his_call = self.main_win.child_window(auto_id="hisCallLabel", control_type="Text")
            if his_call.exists():
                status["his_call"] = his_call.window_text()

            his_name = self.main_win.child_window(auto_id="nameStaticLabel", control_type="Text")
            if his_name.exists():
                status["his_name"] = his_name.window_text()

            msg_label = self.main_win.child_window(auto_id="messageLabel", control_type="Text")
            if msg_label.exists():
                status["message"] = msg_label.window_text()

            room_box = self.main_win.child_window(auto_id="RoomComboBox", control_type="ComboBox")
            if room_box.exists():
                status["room"] = room_box.window_text()

            room_desc = self.main_win.child_window(auto_id="roomDescriptionLabel", control_type="Text")
            if room_desc.exists():
                status["room_desc"] = room_desc.window_text()

            country_box = self.main_win.child_window(auto_id="countryComboBox", control_type="ComboBox")
            if country_box.exists():
                status["country"] = country_box.window_text()

        except Exception as e:
            status["error"] = str(e)

        return status

    def get_room_list(self) -> list:
        """Roomの選択肢一覧を取得する"""
        try:
            room_box = self.main_win.child_window(auto_id="RoomComboBox", control_type="ComboBox")
            # ComboBoxのアイテム一覧を抽出
            items = [item.window_text() for item in room_box.children(control_type="ListItem")]
            if not items:
                # UIAの通常取得を試みる
                items = room_box.item_texts()
            return items
        except Exception:
            return []

    # --- 操作系メソッド (Write) ---

    def toggle_on_off(self):
        """On/Off スイッチをクリックして接続/切断を切り替える"""
        try:
            btn = self.main_win.child_window(auto_id="OnOffToggleSwitch")
            btn.click_input()
            return True
        except Exception as e:
            print(f"toggle_on_off エラー: {e}")
            return False

    def toggle_ptt(self):
        """PTT (onAIRswitch) をクリックして送信/受信を切り替える"""
        try:
            btn = self.main_win.child_window(auto_id="onAIRswitch")
            btn.click_input()
            return True
        except Exception as e:
            print(f"toggle_ptt エラー: {e}")
            return False

    def set_room(self, room_name: str):
        """Roomコンボボックスから指定のルームを選択する"""
        try:
            room_box = self.main_win.child_window(auto_id="RoomComboBox", control_type="ComboBox")
            room_box.select(room_name)
            return True
        except Exception as e:
            print(f"set_room エラー: {e}")
            return False


# --- ドライバ単体验証用インタラクティブCLI ---
def interactive_test():
    print("=" * 60)
    print(" FUNA Wrapper for Peanut - Driver Test Console")
    print("=" * 60)

    driver = PeanutDriver()
    print("Peanutに接続中...")
    if not driver.connect():
        print("【エラー】Peanutが見つかりません。Peanutを起動してください。")
        return

    print("-> Peanutの接続に成功しました！\n")

    menu = """
[操作コマンド]
  s : 現在のステータスを表示 (Status)
  p : PTT 切り替え (Toggle TX/RX)
  o : On/Off 切り替え (Toggle Connect/Disconnect)
  r : Room 一覧取得 (Get Rooms)
  m : ルーム変更 (Set Room)
  q : テスト終了 (Quit)
"""
    print(menu)

    while True:
        try:
            cmd = input("Peanut-CLI> ").strip()
            if cmd == "q":
                break
            elif cmd == "s":
                status = driver.get_status()
                print("\n--- [現在のPeanut状態] ---")
                for k, v in status.items():
                    print(f"  {k:12s}: {v}")
                print("--------------------------\n")
            elif cmd == "p":
                print("PTTを切り替えます...")
                driver.toggle_ptt()
                time.sleep(0.5)
                print("現在のPTT表示:", driver.get_status().get("ptt_state"))
            elif cmd == "o":
                print("On/Off を切り替えます...")
                driver.toggle_on_off()
            elif cmd == "r":
                print("Room一覧を取得中...")
                rooms = driver.get_room_list()
                print(f"検出されたRoom数: {len(rooms)}")
                if rooms:
                    print(", ".join(rooms[:15]) + ("..." if len(rooms) > 15 else ""))
            elif cmd == "m":
                target_room = input("変更したいRoom名を入力: ").strip()
                if target_room:
                    driver.set_room(target_room)
                    time.sleep(0.5)
                    print("現在のRoom:", driver.get_status().get("room"))
            else:
                print("無効なコマンドです。? を入力するとヘルプが出ます。")
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"エラー: {e}")

    print("\nテストを終了しました。")

if __name__ == "__main__":
    interactive_test()