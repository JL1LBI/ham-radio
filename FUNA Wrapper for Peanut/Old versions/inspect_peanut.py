"""
FUNA Wrapper for Peanut - GUI Structure Inspector (v2)
対象: Peanut (by PA7LIM)
"""

import sys
import json
import datetime
from pywinauto import Desktop, Application

def get_peanut_main_window(backend="uia"):
    """
    タイトルに 'Peanut' を含むウィンドウを全検索し、
    画面上に表示されているメインウィンドウ（面積が最大のもの）を自動選択する
    """
    desktop = Desktop(backend=backend)
    
    # 候補となるウィンドウをすべて取得
    candidates = desktop.windows(title_re=".*Peanut.*")
    
    if not candidates:
        # プロセス名で再検索
        candidates = desktop.windows(process_re=".*Peanut.*")

    if not candidates:
        return None

    print(f"\n[検索結果] 'Peanut' に一致する要素が {len(candidates)} 個見つかりました:")
    
    valid_candidates = []
    for i, w in enumerate(candidates):
        try:
            rect = w.rectangle()
            width = rect.width()
            height = rect.height()
            area = width * height
            is_vis = w.is_visible()
            title = w.window_text()
            cls_name = w.element_info.class_name
            
            print(f"  [{i}] Title: '{title}' | Class: '{cls_name}' | Size: {width}x{height} | Visible: {is_vis}")
            
            # 画面上に存在し、幅・高さがあるものを候補とする
            if is_vis and width > 50 and height > 50:
                valid_candidates.append((area, w))
        except Exception as e:
            print(f"  [{i}] 情報取得スキップ: {e}")

    if not valid_candidates:
        print("-> 可視状態のウィンドウが見つからなかったため、最初の要素を選択します。")
        return candidates[0]

    # 画面面積（Width × Height）が最も大きいものをメイン画面とみなす
    valid_candidates.sort(key=lambda x: x[0], reverse=True)
    best_window = valid_candidates[0][1]
    
    print(f"\n=> メイン画面として自動選択: '{best_window.window_text()}' (Size: {best_window.rectangle().width()}x{best_window.rectangle().height()})\n")
    return best_window

def dump_controls_tree(element, depth=0):
    """再帰的にコントロールツリーを抽出"""
    try:
        info = element.info
        element_data = {
            "depth": depth,
            "control_type": getattr(info, "control_type", None),
            "class_name": getattr(info, "class_name", ""),
            "name": getattr(info, "name", ""),
            "automation_id": getattr(info, "automation_id", ""),
            "rectangle": str(getattr(info, "rectangle", "")),
            "children": []
        }
        for child in element.children():
            element_data["children"].append(dump_controls_tree(child, depth + 1))
        return element_data
    except Exception as e:
        return {"error": str(e)}

def format_tree_text(node, indent=0):
    """ツリー辞書をインデント付きテキストに整形"""
    spaces = "  " * indent
    ctrl_type = node.get("control_type", "Unknown")
    name = f"'{node.get('name')}'" if node.get("name") else "(No Name)"
    auto_id = f" [ID: {node.get('automation_id')}]" if node.get("automation_id") else ""
    cls_name = f" [Class: {node.get('class_name')}]" if node.get("class_name") else ""
    
    line = f"{spaces}- {ctrl_type}: {name}{auto_id}{cls_name}\n"
    for child in node.get("children", []):
        line += format_tree_text(child, indent + 1)
    return line

def main():
    print("=" * 65)
    print(" FUNA Wrapper for Peanut - GUI Inspector (v2)")
    print("=" * 65)

    target_win = get_peanut_main_window(backend="uia")
    
    if not target_win:
        print("【エラー】Peanutのメインウィンドウが見つかりませんでした。")
        sys.exit(1)

    # 取得したウィンドウのハンドルを使ってApplicationオブジェクトに接続
    app = Application(backend="uia").connect(handle=target_win.handle)
    win_obj = app.window(handle=target_win.handle)

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    raw_dump_txt = f"peanut_raw_identifiers_{timestamp}.txt"
    out_txt = f"peanut_tree_{timestamp}.txt"
    out_json = f"peanut_tree_{timestamp}.json"

    print(f"[1/3] pywinauto識別子ダンプを出力中 -> {raw_dump_txt}")
    with open(raw_dump_txt, "w", encoding="utf-8") as f:
        orig_stdout = sys.stdout
        sys.stdout = f
        try:
            win_obj.print_control_identifiers()
        except Exception as e:
            print(f"ダンプ出力エラー: {e}")
        finally:
            sys.stdout = orig_stdout

    print(f"[2/3] コントロールツリー構造を解析中...")
    tree_data = dump_controls_tree(win_obj)

    print(f"[3/3] 結果をファイルに保存中 -> {out_txt}, {out_json}")
    with open(out_txt, "w", encoding="utf-8") as f:
        f.write(format_tree_text(tree_data))

    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(tree_data, f, ensure_ascii=False, indent=2)

    print("\n--- [ツリー構造プレビュー (先頭40行)] ---")
    preview = format_tree_text(tree_data).splitlines()[:40]
    print("\n".join(preview))
    if len(preview) == 40:
        print("... (続きはファイルに保存されています)")

    print("\n" + "=" * 65)
    print("解析完了！")
    print(f"・詳細識別子: {raw_dump_txt}")
    print(f"・ツリー構造: {out_txt}")
    print("=" * 65)

if __name__ == "__main__":
    main()