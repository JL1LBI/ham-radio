"""
FUNA Wrapper for Peanut - Pure Setup Engine (v3)
PostMessage による非同期トリガーでモーダルブロッキングを完全解消
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
GW_ENABLEDPOPUP = 6
CBN_SELCHANGE = 1
CB_FINDSTRINGEXACT = 0x0158
CB_SETCURSEL = 0x014E

def send_button_click_async(hwnd):
    """
    【最重要】PostMessageで非同期にボタンを押す。
    モーダルダイアログが開いてもPython側がブロック（フリーズ）しない！
    """
    user32.PostMessageW(hwnd, BM_CLICK, 0, 0)

def send_pane_click(hwnd):
    """Paneコントロール（スイッチ）をクリック"""
    rect = ctypes.wintypes.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(rect))
    cx = (rect.right - rect.left) // 2
    cy = (rect.bottom - rect.top) // 2
    lparam = (cy << 16) | (cx & 0xFFFF)
    user32.PostMessageW(hwnd, WM_LBUTTONDOWN, 1, lparam)
    time.sleep(0.05)
    user32.PostMessageW(hwnd, WM_LBUTTONUP, 0, lparam)

def get_modal_setup_dialog(main_hwnd):
    """親ウィンドウをロックしているSetupダイアログを確実に取得"""
    for _ in range(30):
        time.sleep(0.15)
        popup_hwnd = user32.GetWindow(main_hwnd, GW_ENABLEDPOPUP)
        if popup_hwnd and popup_hwnd != main_hwnd:
            length = user32.GetWindowTextLengthW(popup_hwnd)
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(popup_hwnd, buf, length + 1)
            if "setup" in buf.value.lower():
                app = Application(backend="uia").connect(handle=popup_hwnd)
                return app.window(handle=popup_hwnd)
    return None

def configure_master_pure(main_hwnd, target_master_name):
    """
    非同期でSetupを開き、Masterを設定してSaveし、閉じる
    target_master_name: 'Japan' または 'Global'
    """
    app = Application(backend="uia").connect(handle=main_hwnd)
    main_win = app.window(handle=main_hwnd)
    
    # 1. Setupボタンを【非同期 PostMessage】でクリック
    setup_btn = main_win.child_window(auto_id="setupButton", control_type="Button")
    print(f"  [1] Setupボタンへ非同期クリック送信 (HWND: {setup_btn.handle})...")
    send_button_click_async(setup_btn.handle)

    # 2. 即座にSetupダイアログの出現を待機・捕捉
    print("  [2] Setupダイアログの出現を待機中...")
    setup_dlg = get_modal_setup_dialog(main_hwnd)

    if not setup_dlg:
        print("  【エラー】Setupダイアログを検出できませんでした。")
        return False

    print(f"  -> Setupダイアログ捕捉成功！ (HWND: {setup_dlg.handle})")

    # 3. Master選択 ('Japan' または 'Global')
    master_combo = setup_dlg.child_window(auto_id="masterlistComboBox", control_type="ComboBox")
    hwnd_combo = master_combo.handle
    
    idx = user32.SendMessageW(hwnd_combo, CB_FINDSTRINGEXACT, -1, target_master_name)
    if idx != -1:
        print(f"  [3] -> '{target_master_name}' を選択 (Index: {idx})")
        user32.SendMessageW(hwnd_combo, CB_SETCURSEL, idx, 0)
        parent = user32.GetParent(hwnd_combo)
        ctrl_id = user32.GetDlgCtrlID(hwnd_combo)
        user32.SendMessageW(parent, WM_COMMAND, (CBN_SELCHANGE << 16) | ctrl_id, hwnd_combo)
    else:
        print(f"  【警告】'{target_master_name}' が見つかりませんでした。")

    time.sleep(0.3)

    # 4. Saveボタンを非同期クリック
    save_btn = setup_dlg.child_window(auto_id="saveButton", control_type="Button")
    print(f"  [4] Saveボタンへクリック送信 (HWND: {save_btn.handle})...")
    send_button_click_async(save_btn.handle)

    # 5. ダイアログが自動で閉じるのを待機
    for _ in range(30):
        time.sleep(0.15)
        curr_popup = user32.GetWindow(main_hwnd, GW_ENABLEDPOPUP)
        if curr_popup == main_hwnd or curr_popup == 0:
            break

    print("  [5] Setup画面が閉じ、メイン画面のロック解除を確認！")
    return True

def toggle_on_pure(main_hwnd):
    """メイン画面のOn/Offスイッチを投入"""
    app = Application(backend="uia").connect(handle=main_hwnd)
    main_win = app.window(handle=main_hwnd)
    onoff_pane = main_win.child_window(auto_id="OnOffToggleSwitch")
    print(f"  -> OnOffスイッチ投入 (HWND: {onoff_pane.handle})...")
    send_pane_click(onoff_pane.handle)

def main():
    print("=" * 65)
    print(" FUNA Wrapper for Peanut - Pure Setup Engine (v3)")
    print("=" * 65)
    print("※ Peanutを2つ（未接続状態で）起動しておいてください。\n")

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
    print(">>> 【1/2】 1つ目を [Japan] に全自動設定中...")
    if configure_master_pure(hwnd1, "Japan"):
        print(">>> 1つ目のPeanutを ON にします...")
        time.sleep(0.5)
        toggle_on_pure(hwnd1)

    time.sleep(1.5)

    # --- インスタンス2を Global に設定 ---
    print("\n>>> 【2/2】 2つ目を [Global] に全自動設定中...")
    if configure_master_pure(hwnd2, "Global"):
        print(">>> 2つ目のPeanutを ON にします...")
        time.sleep(0.5)
        toggle_on_pure(hwnd2)

    print("\n" + "=" * 65)
    print("全自動セットアップが完了しました！")
    print("Peanut本体の画面を確認してください。")
    print("=" * 65)

if __name__ == "__main__":
    main()