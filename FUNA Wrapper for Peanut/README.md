```markdown
# FUNA Wrapper for Peanut - Dual Master Console

[ 日本語 (Japanese) ] | [ [English](#funa-wrapper-for-peanut---dual-master-console-en) ]

---

# FUNA Wrapper for Peanut - Dual Master Console (日本語)

**アマチュア無線家向け VoIP ソフトウェア「Peanut」の運用体験を革新する、高速・軽量なデュアル VFO 対応 TUI（テキストユーザーインターフェース）ラッパー**

![Platform](https://img.shields.io/badge/Platform-Windows-0078D6?logo=windows)
![Python](https://img.shields.io/badge/Python-3.8%2B-blue?logo=python)
![UI](https://img.shields.io/badge/UI-Responsive%20TUI%20(MS--DOS%20Blue)-0000AA)

---

## 概要

アマチュア無線専用 VoIP クライアント「Peanut」は世界中のアマチュア無線家と手軽に交信できる素晴らしいソフトウェアですが、実運用において以下のような課題がありました。

1. **マスターサーバーの排他仕様**: 「Japan」サーバーと「Global」サーバーを同時に選択できず、国内ルームと海外/グローバルルームを同時にワッチ（同時受信）できない。
2. **トグル式 PTT**: デフォルトの送信操作が「クリックして ON、もう一度クリックして OFF」のトグル方式であり、アマチュア無線の通話感覚と合わず誤送信の原因になりやすい。
3. **外部マイク・PTT ブリッジとの親和性**: 多くの無線用 VoIP ソフトで標準となっている「スペースキー長押し（モーメンタリ）送信」に対応していないため、PC 接続のハンドマイクやフットスイッチとの連動が難しい。
4. **GUI の操作性**: ルーム切り替えのたびにマウス操作が必要で、リグ（無線機）らしい直感的な運用がしにくい。

**FUNA Wrapper for Peanut** は、これらの課題を Windows API および UI Automation の高度な制御によって解決します。  
本ツールを実行するだけで、Peanut を**自動で 2 重起動**し、それぞれを「Japan マスター」と「Global マスター」に完全自動構成。懐かしの MS-DOS 調ブルースクリーン TUI 上で、**デュアル VFO による同時ワッチ・ワンキー切り替え・スペースキー長押しでのモーメンタリ送信**を実現します。

---

## 主な特徴

### 1. デュアル Master の完全自動構成＆同時ワッチ
- 起動時に Peanut プロセスを自動検知し、不足分を自動で 2 重起動。
- 設定画面（Setup）の深部まで Win32 メッセージ経由で高速アクセスし、片方を「Japan」、もう片方を「Global」に自動設定。
- デフォルト待機ルーム（JP 側: `CQCQCQ-J` / GLOBAL 側: `JAPANESE`）へ自動接続。
- 両方のトラフィック（Last Heard）を単一コンソール上で同時にリアルタイム監視。

### 2. トランシーバー感覚のデュアル VFO 切替（[Tab] キー）
- `Tab` キーを押すだけで、送信対象（ACTIVE VFO）を「JP」と「GLOBAL」の間で瞬時にトグル切り替え。
- 高級無線機のサブバンド・メインバンド切り替えのような快適な操作感を提供。

### 3. モーメンタリー PTT 制御（[Space] キー長押し）
- スペースキーを**押している間だけ送信（TX ON）**、**離すと即座に受信（TX OFF）**に戻るモーメンタリ動作。
- 自作マイクインターフェース、フットスイッチ、キーボードエミュレータ経由の PTT マイクにも完全対応。

### 4. ゼロタッチ起動 ＆ 完全連動シャットダウン
- 事前に Peanut を手動起動しておく必要はありません。本ツールを立ち上げるだけで全て自動準備されます。
- 初期化完了後は Peanut 本体のウィンドウが自動最小化され、TUI コンソールが最前面にフォーカスされます。
- `q` キーで本ツールを終了すると、バックグラウンドで動作しているすべての Peanut プロセスも安全に一括終了します。

### 5. 美しいレスポンシブ MS-DOS 風 TUI ＆ 東アジア文字幅完全対応
- ターミナルのウィンドウサイズ（行数・桁数）を動的に検出し、100% 隙間なくフィットするブルーバック画面を描画。
- `East Asian Width` 判定エンジンを内蔵。日本語コールサイン・漢字・全角文字が混在しても、枠線やペインのレイアウトが崩れません。

### 6. 高速インクリメンタル検索対応 ルームセレクター（[m] キー）
- コンボボックスを展開することなく、Win32 API（`CB_GETLBTEXT`）でルーム一覧をミリ秒単位で一括ロード。
- アルファベット入力によるリアルタイム絞り込み検索、矢印キーによる選択が可能。

---

## 動作要件

- **OS**: Windows 10 / Windows 11 (64-bit 推奨)
- **Python**: Python 3.8 以上
- **対象ソフトウェア**: Peanut for Windows (公式クライアント)
- **依存ライブラリ**:
  - `pywinauto` (UI Automation 操作用)
  - `ctypes`, `msvcrt`, `unicodedata`, `threading` などの標準モジュール

---

## インストール手順

1. **Python のインストール**  
   Python 公式サイト等から Python 3.x をインストールしてください（インストール時、「Add Python to PATH」にチェックを入れてください）。

2. **依存パッケージのインストール**  
   コマンドプロンプトまたは PowerShell を開き、以下を実行します。
   ```bash
   pip install pywinauto
   ```

3. **スクリプトの配置**  
   本リポジトリのスクリプトを任意のフォルダに配置します。  
   Peanut の実行ファイルが標準パス（`C:\Program Files (x86)\Peanut\Peanut\peanut.exe` 等）以外にある場合は、スクリプトと同じフォルダに `peanut.exe` を置くか、スクリプト先頭の `DEFAULT_PATHS` を編集してください。

---

## 使い方

### 起動
コマンドプロンプトまたは Windows ターミナルで以下を実行します。

```bash
python "FUNA Wrapper for Peanut v3.6.py"
```

> **重要**:  
> 起動シークエンス（ステップ 1/5 〜 5/5）が完了し、ブルーのメインコンソール画面が表示されるまで、**マウスやキーボードを操作せずそのままお待ちください**。  
> 接続完了後、自動的に Peanut は最小化され、コンソールが最前面になります。

---

### キーバインド一覧

| キー | 動作 |
| :--- | :--- |
| **`Space` (長押し)** | **PTT 送信 (TX)**（話している間押し続け、離すと受信に戻る） |
| **`Tab`** | **Active VFO 切替**（`JP MASTER` ⇄ `GLOBAL MASTER`） |
| **`m`** | **ルーム選択ポップアップの起動**（インクリメンタル検索対応） |
| **`o`** | **オンライン / オフライン 切替**（選択中 VFO の接続・切断トグル） |
| **`q`** | **一括終了**（Peanut プロセスも連動してすべて終了） |

#### ルームセレクター内での操作
- **文字キー入力**: ルーム名のインクリメンタル検索（リアルタイム絞り込み）
- **`↑` / `↓`**: ルームの選択移動
- **`PageUp` / `PageDown`**: 1 ページ単位のスクロール
- **`Backspace`**: 検索文字を 1 文字削除
- **`Enter`**: 選択したルームに切り替え
- **`Esc`**: ルーム選択をキャンセル

---

## ファイル構成

- **`FUNA Wrapper for Peanut v3.6.py`**  
  メインの統合アプリケーション。デュアル Peanut のライフサイクル管理、MS-DOS 風レスポンシブ TUI レンダリング、東アジア文字幅計算、モーメンタリ PTT スレッド、ポップアップルームセレクターを統合。
- **`peanut_driver_v2.py`**  
  Peanut 制御用のコア・ドライバモジュール。Win32 メッセージ直接送信による超高速なステータス取得・コントロールキャッシュ・ルームリスト取得機能を実装した単体検証用ドライバ。

---

## 注意事項・トラブルシューティング

- **Peanut の初回セットアップ**:  
  Peanut を初めて使用する場合は、あらかじめ Peanut 単体を起動してコールサインやコード認証を済ませ、正常に交信できる状態にしておいてください。
- **管理者権限について**:  
  Windows の UAC（ユーザーアカウント制御）設定によっては、コマンドプロンプトを「管理者として実行」して本ツールを起動する必要がある場合があります。
- **PTT マイクの連動**:  
  本ツールはキーボードの `VK_SPACE` (スペースキー) の押し下げ状態を Win32 `GetAsyncKeyState` で直接監視しています。USB 接続のフットスイッチや PTT ブリッジ回路からスペースキーを割り当てて送信トリガーとして使用できます。

---

<br><br>

---

# FUNA Wrapper for Peanut - Dual Master Console (EN)

**A high-speed, lightweight Dual-VFO TUI (Text User Interface) wrapper engineered to elevate the user experience for the Peanut amateur radio VoIP client.**

![Platform](https://img.shields.io/badge/Platform-Windows-0078D6?logo=windows)
![Python](https://img.shields.io/badge/Python-3.8%2B-blue?logo=python)
![UI](https://img.shields.io/badge/UI-Responsive%20TUI%20(MS--DOS%20Blue)-0000AA)

---

## Overview

While **Peanut** is an outstanding VoIP application connecting amateur radio operators globally, several practical operational limitations exist:

1. **Mutually Exclusive Master Servers**: Users cannot connect to both the "Japan" and "Global" master servers simultaneously, making concurrent dual-watch of domestic and global rooms impossible.
2. **Toggle-based PTT**: The standard PTT behavior requires clicking once to start transmitting and clicking again to stop. This differs from traditional ham radio operation and increases the risk of unintended hot-micing.
3. **Lack of Momentary Support for External Mics**: Peanut lacks native support for holding the Spacebar to talk—a standard among ham radio VoIP software—making integration with external PTT hand mics or foot switches difficult.
4. **Mouse-dependent GUI**: Navigating and selecting rooms demands continuous mouse interaction, hindering smooth radio-like operation.

**FUNA Wrapper for Peanut** solves all of these issues through deep integration with Windows API and UI Automation.  
Simply running this application will **automatically spawn two instances of Peanut**, configure one to the "Japan" master and the other to the "Global" master, and present a vintage MS-DOS styled dual-pane console with **seamless dual-watch, instant VFO switching, and true momentary PTT**.

---

## Key Features

### 1. Fully Automated Dual Master Setup & Concurrent Watch
- Detects running Peanut instances on boot and automatically launches missing instances up to two.
- Accesses setup dialogs via Win32 messages to configure Master lists (`Japan` and `Global`) automatically.
- Automatically joins default standby rooms (`CQCQCQ-J` on JP, `JAPANESE` on Global).
- Displays incoming Last Heard activity from both servers simultaneously in real time.

### 2. Dual-VFO Switching ([Tab] Key)
- Toggle the active transmitting target (ACTIVE VFO) between `JP` and `GLOBAL` with a single press of the `Tab` key, mimicking high-end transceiver operations.

### 3. Momentary PTT Operation (Hold [Space] to Talk)
- Transmits (**TX ON**) while holding down the **Spacebar**, and immediately returns to receive (**TX OFF**) upon release.
- Ideal for custom microphone interfaces, foot pedals, and external hardware bridges.

### 4. Zero-Touch Boot & Synchronized Shutdown
- No need to launch Peanut manually. The script manages the entire startup and connection sequence.
- Once ready, Peanut GUI windows are automatically minimized, and the console window is brought to the front.
- Pressing `q` terminates the wrapper and gracefully closes all associated Peanut processes.

### 5. Responsive MS-DOS Blue TUI with East-Asian Width Support
- Fully responsive layout automatically scales to 100% of your terminal dimensions without border clipping.
- Includes a dedicated `East Asian Width` calculation engine, ensuring flawless text alignment even when Japanese Kanji or full-width characters are present.

### 6. Lightning-Fast Room Selector ([m] Key)
- Extracts room listings directly via Win32 messages (`CB_GETLBTEXT`) within milliseconds.
- Features real-time incremental filter search and intuitive arrow-key navigation.

---

## System Requirements

- **Operating System**: Windows 10 / Windows 11 (64-bit recommended)
- **Python**: Python 3.8 or higher
- **Target Application**: Official Peanut for Windows client
- **Dependencies**:
  - `pywinauto` (UI Automation backend)
  - Built-in modules: `ctypes`, `msvcrt`, `unicodedata`, `threading`, `subprocess`

---

## Installation

1. **Install Python**:  
   Ensure Python 3.x is installed (check "Add Python to PATH" during installation).

2. **Install Required Package**:  
   Run the following command in your terminal:
   ```bash
   pip install pywinauto
   ```

3. **Deploy the Script**:  
   Place the script in your preferred directory.  
   If Peanut is installed in a non-standard directory, place `peanut.exe` inside the script directory or update `DEFAULT_PATHS` at the top of the file.

---

## Usage

### Launching
Open Command Prompt or Windows Terminal and run:

```bash
python "FUNA Wrapper for Peanut v3.6.py"
```

> **Note**:  
> Please **do not interact with the mouse or keyboard** during the 5-step boot sequence.  
> Once initialized, Peanut windows will be minimized and the active console will take focus automatically.

---

### Keybindings

| Key | Action |
| :--- | :--- |
| **`Space` (Hold)** | **Momentary PTT (TX)** (Hold to talk, release to listen) |
| **`Tab`** | **Switch Active VFO** (`JP MASTER` ⇄ `GLOBAL MASTER`) |
| **`m`** | **Open Room Selector** (with real-time search filter) |
| **`o`** | **Toggle Connection** (Connect / Disconnect active instance) |
| **`q`** | **Quit Application** (Closes all Peanut processes) |

#### Inside the Room Selector Popup
- **Type text**: Filter rooms in real time
- **`↑` / `↓`**: Move selection up/down
- **`PageUp` / `PageDown`**: Scroll one page up/down
- **`Backspace`**: Delete filter character
- **`Enter`**: Confirm and switch to selected room
- **`Esc`**: Cancel and return to main screen

---

## File Description

- **`FUNA Wrapper for Peanut v3.6.py`**:  
  The complete standalone TUI console application. Contains instance lifecycle management, responsive rendering engine, East Asian character width alignment, background activity polling, and momentary PTT handling.
- **`peanut_driver_v2.py`**:  
  Standalone low-level driver module utilizing Win32 API messages for high-speed control, UI element caching, and diagnostic benchmarking.

---

## Disclaimer & 73

- This software is a third-party automation wrapper designed for personal ham radio enjoyment and accessibility. It is not officially affiliated with PA7LIM (author of Peanut).
- Please ensure you hold a valid amateur radio license and have completed the official Peanut registration before operating.

**73 & Good DX!**
```