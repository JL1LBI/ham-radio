"""
FUNA Wrapper for Peanut - Pure Message Setup Engine (Zero-Mouse)
マウスを一切動かさず、Win32内部メッセージのみでSetupとOnを完全制御する
"""

import time
import ctypes
from pywinauto import Desktop, Application

# Windows API
user32 = ctypes.windll.user32
BM_CLICK = 0x00F5
WM_COMMAND = 0x0111
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
CBN_SELCHANGE = 1
CB_GETCOUNT = 0x0146
CB_GETLBTEXTLEN = 0x0149
CB_GETLBTEXT = 0x0148
CB_SETCURSEL = 0x014E

def send_click_pure(hwnd):
    """マウスを動かさずにボタンをクリック (BM_CLICK)"""
    user32.SendMessageW(hwnd, BM_CLICK, 0, 0)

def send_mouse_click_pure(hwnd):
    """マウスを動かさずにコントロール内部へ左クリックメッセージを直接送る"""
    user32.SendMessageW(hwnd, WM_LBUTTONDOWN, 1, 0)
    time.sleep(0.05)
    user32.SendMessageW(hwnd, WM_LBUTTONUP, 0, 0)

def configure_master_pure(main_hwnd, target_master_name):
    """
    マウスを一切動かさずにSetupを開き、Masterを設定してSaveする
    """
    app = Application(backend="uia").connect(handle=main_hwnd)
    main_win = app.window(handle=main_hwnd)
    
    # 1. Setupボタンのハンドルを取得してメッセージクリック
    setup_btn = main_win.child_window(auto_id="setupButton", control_type="Button")
    print(f"  [1] Setupボタンへ BM_CLICK 送信 (HWND: {setup_btn.handle})...")
    send_click_pure(setup_btn.handle)

    # 2. Setupダイアログの出現を待機 (Desktop全体から捕捉)
    desktop = Desktop(backend="uia")
    setup_dlg = None
    for _ in range(25):
        time.sleep(0.2)
        wins = desktop.windows(title="Setup", auto_id="SetupForm")
        if wins and wins[0].is_visible():
            setup_dlg = wins[0]
            break

    if not setup_dlg:
        print("  【エラー】Setupダイアログが検出できませんでした。")
        return False

    print(f"  [2] Setupダイアログ捕捉完了 (HWND: {setup_dlg.handle})")

    # 3. Masterリストの全項目取得
    master_combo = setup_dlg.child_window(auto_id="masterlistComboBox", control_type="ComboBox")
    hwnd_combo = master_combo.handle
    count = user32.SendMessageW(hwnd_combo, CB_GETCOUNT, 0, 0)
    items = []
    for i in range(count):
        length = user32.SendMessageW(hwnd_combo, CB_GETLBTEXTLEN, i, 0)
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.SendMessageW(hwnd_combo, CB_GETLBTEXT, i, buf)
        items.append(buf.value)

    print(f"  [3] Master選択肢: {items}")

    # 4. 対象項目の選択
    target_idx = -1
    for idx, name in enumerate(items):
        if target_master_name.lower() in name.lower():
            target_idx = idx
            break

    if target_idx == -1 and target_master_name.lower() != "japan":
        # Japan以外（Globalなど）
        for idx, name in enumerate(items):
            if "japan" not in name.lower():
                target_idx = idx
                break

    if target_idx != -1:
        chosen_text = items[target_idx]
        print(f"  [4] -> '{chosen_text}' を選択 (インデックス {target_idx})")
        user32.SendMessageW(hwnd_combo, CB_SETCURSEL, target_idx, 0)
        parent = user32.GetParent(hwnd_combo)
        ctrl_id = user32.GetDlgCtrlID(hwnd_combo)
        user32.SendMessageW(parent, WM_COMMAND, (CBN_SELCHANGE << 16) | ctrl_id, hwnd_combo)
    else:
        print(f"  【警告】'{target_master_name}' に合致する項目が見つかりませんでした。")

    time.sleep(0.3)

    # 5. Saveボタンへクリックメッセージ
    save_btn = setup_dlg.child_window(auto_id="saveButton", control_type="Button")
    print(f"  [5] Saveボタンへ BM_CLICK 送信 (HWND: {save_btn.handle})...")
    send_click_pure(save_btn.handle)

    # 6. ダイアログが消えるのを待機
    for _ in range(25):
        time.sleep(0.2)
        if not setup_dlg.is_visible():
            break

    print("  [6] Setup完了！親画面ロック解除。")
    return True

def toggle_on_pure(main_hwnd):
    """マウスを動かさずにOnスイッチへクリックメッセージ送信"""
    app = Application(backend="uia").connect(handle=main_hwnd)
    main_win = app.window(handle=main_hwnd)
    onoff_pane = main_win.child_window(auto_id="OnOffToggleSwitch")
    print(f"  -> OnOffスイッチへ左クリックメッセージ送信 (HWND: {onoff_pane.handle})...")
    send_mouse_click_pure(onoff_pane.handle)

def main():
    print("=" * 65)
    print(" FUNA Wrapper for Peanut - Pure Message Setup Test (Zero-Mouse)")
    print("=" * 65)
    print("※ Peanutを2つ（未接続のOFF状態で）起動しておいてください。\n")

    desktop = Desktop(backend="uia")
    wins = desktop.windows(title="Peanut", class_name_re=".*WindowsForms.*")
    valid_wins = [w for w in wins if w.is_visible() and w.rectangle().width() > 100]

    if len(valid_wins) < 2:
        print(f"検出されたPeanutは {len(valid_wins)} 個です。2つ起動してください。")
        return

    hwnd1 = valid_wins[0].handle
    hwnd2 = valid_wins[1].handle
    print(f"Peanut捕捉成功: [1] HWND={hwnd1}, [2] HWND={hwnd2}\n")

    # --- インスタンス1を Japan に設定 ---
    print(">>> 【テスト 1/2】 1つ目のPeanutを [Japan] に設定します...")
    if configure_master_pure(hwnd1, "Japan"):
        print(">>> 1つ目のPeanutの電源をONにします...")
        toggle_on_pure(hwnd1)

    time.sleep(1.5)

    # --- インスタンス2を Global に設定 ---
    print("\n>>> 【テスト 2/2】 2つ目のPeanutを [Global] に設定します...")
    if configure_master_pure(hwnd2, "Global"):
        print(">>> 2つ目のPeanutの電源をONにします...")
        toggle_on_pure(hwnd2)

    print("\n" + "=" * 65)
    print("すべての処理が完了しました！")
    print("画面上のPeanut本体が、それぞれJapanとGlobalになり、")
    print("両方ともON（接続状態）になっているか確認してください。")
    print("=" * 65)

if __name__ == "__main__":
    main()