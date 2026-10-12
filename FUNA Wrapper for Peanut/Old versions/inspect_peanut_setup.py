"""
FUNA Wrapper for Peanut - Setup Dialog Inspector
PeanutのSetup画面を自動で開き、Master選択やSaveボタンのコントロールIDをダンプする
"""

import sys
import time
from pywinauto import Desktop, Application

def inspect_setup():
    print("=" * 60)
    print(" FUNA Wrapper for Peanut - Setup Dialog Inspector")
    print("=" * 60)
    print("起動中のPeanutメイン画面を検索中...")

    desktop = Desktop(backend="uia")
    candidates = desktop.windows(title="Peanut", class_name_re=".*WindowsForms.*")
    valid_wins = [w for w in candidates if w.is_visible() and w.rectangle().width() > 100]

    if not valid_wins:
        print("【エラー】Peanutが見つかりません。Peanutを1つ起動しておいてください。")
        return

    main_win = valid_wins[0]
    app = Application(backend="uia").connect(handle=main_win.handle)
    win_obj = app.window(handle=main_win.handle)

    print(f"-> メイン画面を捕捉: HWND={main_win.handle}")

    # Setupボタンの特定とクリック
    try:
        setup_btn = win_obj.child_window(auto_id="setupButton", control_type="Button")
        print("-> [Setup] ボタンをクリックして設定ダイアログを開きます...")
        setup_btn.click_input()
        time.sleep(1.5)  # ダイアログが開くのを待機
    except Exception as e:
        print(f"Setupボタンクリック失敗: {e}")
        return

    # 開いたSetupダイアログを検出
    setup_dialog = None
    for w in desktop.windows():
        title = w.window_text()
        if "setup" in title.lower() or "peanut" in title.lower():
            # メイン画面以外のウィンドウを探す
            if w.handle != main_win.handle and w.is_visible():
                setup_dialog = w
                break

    if not setup_dialog:
        print("【警告】独立したSetupウィンドウが見つかりませんでした。メイン画面内の埋め込みタブか確認します。")
        setup_dialog = win_obj

    print(f"-> Setup画面を特定: '{setup_dialog.window_text()}' (HWND={setup_dialog.handle})")

    out_file = "peanut_setup_raw_identifiers.txt"
    print(f"-> コントロール識別子をダンプ中 -> {out_file}")

    with open(out_file, "w", encoding="utf-8") as f:
        orig = sys.stdout
        sys.stdout = f
        try:
            setup_dialog.print_control_identifiers()
        finally:
            sys.stdout = orig

    print(f"\n解析完了！結果を {out_file} に保存しました。")
    print("=" * 60)

if __name__ == "__main__":
    inspect_setup()