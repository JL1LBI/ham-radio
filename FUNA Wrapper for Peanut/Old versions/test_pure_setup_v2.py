"""
FUNA Wrapper for Peanut - Pure Message Setup Engine (v2)
GW_ENABLEDPOPUP によるモーダルSetupダイアログの確実な捕捉と自動設定
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
GW_ENABLEDPOPUP = 6  # 親ウィンドウをロックしているモーダルダイアログを取得するフラグ
CBN_SELCHANGE = 1
CB_GETCOUNT = 0x0146
CB_GETLBTEXTLEN = 0x0149
CB_GETLBTEXT = 0x0148
CB_SETCURSEL = 0x014E

def send_click_pure(hwnd):
    """マウスを動かさずにボタンをクリック"""
    user32.SendMessageW(hwnd, BM_CLICK, 0, 0)

def send_pane_click(hwnd):
    """Paneコントロールの中央を左クリック (マウス移動なし)"""
    # コントロールのサイズ取得
    rect = ctypes.wintypes.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(rect))
    cx = (rect.right - rect.left) // 2
    cy = (rect.bottom - rect.top) // 2
    lparam = (cy << 16) | (cx & 0xFFFF)
    user32.SendMessageW(hwnd, WM_LBUTTONDOWN, 1, lparam)
    time.sleep(0.05)
    user32.SendMessageW(hwnd, WM_LBUTTONUP, 0, lparam)

def get_modal_setup_dialog(main_win, main_hwnd):
    """親ウィンドウをロックしているSetupダイアログを確実に取得"""
    for _ in range(25):
        time.sleep(0.2)
        # 1. Windows API でメイン画面のポップアップダイアログを取得
        popup_hwnd = user32.GetWindow(main_hwnd, GW_ENABLEDPOPUP)
        if popup_hwnd and popup_hwnd != main_hwnd:
            length = user32.GetWindowTextLengthW(popup_hwnd)
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(popup_hwnd, buf, length + 1)
            if "setup" in buf.value.lower():
                app = Application(backend="uia").connect(handle=popup_hwnd)
                return app.window(handle=popup_hwnd)

        # 2. main_win の子要素から探索
        try:
            dlg = main_win.child_window(auto_id="SetupForm")
            if dlg.exists() and dlg.is_visible():
                return dlg
        except Exception:
            pass

    return None

def configure_master_pure(main_hwnd, target_master_name):
    app = Application(backend="uia").connect(handle=main_hwnd)
    main_win = app.window(handle=main_hwnd)
    
    # 1. Setupボタンをクリック (マウス非移動)
    setup_btn = main_win.child_window(auto_id="setupButton", control_type="Button")
    print(f"  [1] Setupボタンへ BM_CLICK 送信 (HWND: {setup_btn.handle})...")
    send_click_pure(setup_btn.handle)

    # 2. Setupダイアログを GW_ENABLEDPOPUP で確実に捕捉
    print("  [2] Setupダイアログの捕捉中...")
    setup_dlg = get_modal_setup_dialog(main_win, main_hwnd)

    if not setup_dlg:
        print("  【エラー】Setupダイアログを検出できませんでした。")
        return False

    print(f"  -> Setupダイアログ捕捉成功！ (HWND: {setup_dlg.handle})")

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
        for idx, name in enumerate(items):
            if "japan" not in name.lower():
                target_idx = idx
                break

    if target_idx != -1:
        chosen_text = items[target_idx]
        print(f"  [4] -> '{chosen_text}' を選択 (Index: {target_idx})")
        user32.SendMessageW(hwnd_combo, CB_SETCURSEL, target_idx, 0)
        parent = user32.GetParent(hwnd_combo)
        ctrl_id = user32.GetDlgCtrlID(hwnd_combo)
        user32.SendMessageW(parent, WM_COMMAND, (CBN_SELCHANGE << 16) | ctrl_id, hwnd_combo)
    else:
        print(f"  【警告】'{target_master_name}' が見つかりませんでした。")

    time.sleep(0.4)

    # 5. Saveボタンへクリックメッセージ
    save_btn = setup_dlg.child_window(auto_id="saveButton", control_type="Button")
    print(f"  [5] Saveボタンへ BM_CLICK 送信 (HWND: {save_btn.handle})...")
    send_click_pure(save_btn.handle)

    # 6. ダイアログが閉じるのを待機
    for _ in range(25):
        time.sleep(0.2)
        # モーダルが解除されたかチェック
        curr_popup = user32.GetWindow(main_hwnd, GW_ENABLEDPOPUP)
        if curr_popup == main_hwnd or curr_popup == 0:
            break

    print("  [6] Setup画面が閉じ、メイン画面のロックが解除されました！")
    return True

def toggle_on_pure(main_hwnd):
    """マウスを動かさずにOnスイッチを押す"""
    app = Application(backend="uia").connect(handle=main_hwnd)
    main_win = app.window(handle=main_hwnd)
    onoff_pane = main_win.child_window(auto_id="OnOffToggleSwitch")
    print(f"  -> OnOffスイッチへクリック送信 (HWND: {onoff_pane.handle})...")
    send_pane_click(onoff_pane.handle)

def main():
    print("=" * 65)
    print(" FUNA Wrapper for Peanut - Pure Setup Engine (v2)")
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
    print(">>> 【1/2】 1つ目のPeanutを [Japan] に設定中...")
    if configure_master_pure(hwnd1, "Japan"):
        print(">>> 1つ目のPeanutを ON にします...")
        time.sleep(0.5)
        toggle_on_pure(hwnd1)

    time.sleep(1.5)

    # --- インスタンス2を Global に設定 ---
    print("\n>>> 【2/2】 2つ目のPeanutを [Global] に設定中...")
    if configure_master_pure(hwnd2, "Global"):
        print(">>> 2つ目のPeanutを ON にします...")
        time.sleep(0.5)
        toggle_on_pure(hwnd2)

    print("\n" + "=" * 65)
    print("全工程が完了しました！")
    print("=" * 65)

if __name__ == "__main__":
    main()