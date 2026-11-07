```markdown
# FUNA Wrapper for WIRES-X
### TUI Frontend - Dual VFO Edition (v3.1)

[![Platform](https://img.shields.io/badge/Platform-Windows-blue.svg)](https://www.microsoft.com/)
[![Python](https://img.shields.io/badge/Python-3.10%2B-brightgreen.svg)](https://www.python.org/)
[![UI Framework](https://img.shields.io/badge/UI-Textual%20(TUI)-cyan.svg)](https://textual.textualize.io/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

[日本語](#日本語) | [English](#english)

---

<a name="日本語"></a>
## 🇯🇵 日本語

### 概要
**FUNA Wrapper for WIRES-X** は、八重洲無線（YAESU）のVoIPアマチュア無線システム「WIRES-X」を、vi/vimやMS-DOSを彷彿とさせるフルスクリーンCUI（TUI: Terminal User Interface）から完全遠隔操作するためのGUIラッパーソフトウェアです。

座標指定による擬似マウス操作を一切排除し、**Windows API（`WM_COMMAND`、`SendMessage`、メモリインジェクション、UI Automation）を直接経由したイベント駆動方式**を採用。最小化状態やバックグラウンド動作でも確実にコマンドを発行できます。
無線機の操作感を目指した「**Dual VFO（VFO A: Room / VFO B: User）**」設計により、キーボードのみでRoomやNodeを軽快に渡り歩くCQオペレーションを実現します。

---

### 主な特徴

1. **Dual VFO（VFO A: Room / VFO B: Node）ペイン**
   - **`Tab` キー** で VFO A（Room一覧）と VFO B（User/Node一覧）を瞬時にトグル切り替え。
   - **`↑` / `↓`** または **`j` / `k`** でカーソルを合わせ、**`Enter` 一発で即座に接続**。
2. **Room一覧のアクティビティ（Act）自動降順ソート**
   - 接続局数（Act）が多い順にルームがリアルタイム整列。今まさにQSOが行われているアクティブな部屋が常に最上位に表示されます。
3. **音声パケットカウンタ監視による真のリアルタイム Active QSO**
   - WIRES-X内部の受信音声パケットカウンタ（`V:xxx`）をミリ秒単位でポーリング監視。
   - 相手局がマイクを握って話している間だけ **`▶ ACTIVE QSO: [コールサイン] (DN)`** が鮮やかに点灯し、PTTを離すと約1.6秒で自動消灯して **`Last Heard: [コールサイン]`** に自動遷移します。
4. **Smart Reconnect（回線解放待機・自動切断シーケンス）**
   - すでに接続中の状態で別の局・Roomを選んだ場合、「自動切断 → 本体回線解放待機（約2.5秒） → 新規ID接続」をワンアクションで実行。本体のスタックを完全に防ぎます。
5. **接続エラー（Connection Busy）の即時フィードバック**
   - 相手が通信中、またはデジタル専用Room等の理由で接続が弾かれた場合、上部バナーが **`[ ✖ CONNECTION BUSY ]`**（赤色背景）に変化し、下部モニターにエラー理由を明示します。
6. **LIVE TRAFFIC & システムログモニター**
   - 接続先ルーム名、入室ノード数、リアルタイム交信局、およびWIRES-X本体の最新システムログ（直近3行）を常時ストリーミング表示。
7. **完全アプライアンス連動（自動起動＆連動終了）**
   - 起動時、WIRES-X本体が未起動であれば自動でバックグラウンド起動して初期化を待機。
   - **`q` キー** で終了すると、回線を安全に切断した上でWIRES-X本体も正規に連動終了（シャットダウン）します。

---

### 画面レイアウト

```text
+-----------------------------------------------------------------------------------+
| ▌FUNA Wrapper for WIRES-X▐  CURRENT: [VFO A (ROOM) *ACTIVE*]   [ ● CONNECTED ]    |
+-----------------------------------------+-----------------------------------------+
| 【 VFO A : ROOM ID 】 (Act降順 / Enter)  | 【 VFO B : USER / NODE ID 】 (Enter)     |
| Act │ Room ID │ Room Name   │ Desc     | Node ID │ Callsign    │ Node Name        |
| 046 │ 43534   │ PHILIPPINE  │ Link...  | 32386   │ JS1YVC      │ -NERIMA-         |
| 028 │ 21080   │ AMERICA-LINK│ Official | 10071   │ JR5YFG      │ --JR5YFG--       |
| 012 │ 20510   │ ALL JA CQ   │ Japan    | 18284   │ AE7JG       │ ---NWRARC1       |
+-----------------------------------------+-----------------------------------------+
| 【 LIVE TRAFFIC & SYSTEM LOG MONITOR 】                                           |
| ● ON AIR (CONNECTED) -> Room: PHILIPPINE-LINK(43534) | Members: 46 Nodes          |
| ▶ ACTIVE QSO: [ N6CLE-200 ] (DN) via WA6GM                                        |
| WIRES-X LOG: > 2026/10/01 01:16:46 Connected to PHILIPPINE-LINK(43534)            |
+-----------------------------------------------------------------------------------+
| Tab:Switch VFO | Enter:Connect | c:Direct ID | d:Disconnect | r:Sync | q:Shutdown |
+-----------------------------------------------------------------------------------+
```

---

### 動作要件

* **OS**: Windows 10 / Windows 11 (64-bit 推奨)
* **Python**: Python 3.10 以上
* **対象ソフトウェア**: 八重洲無線 WIRES-X（標準インストールパス: `C:\Program Files (x86)\YAESUMUSEN\WIRES-X\Wires-X.exe`）
* **インターフェース**: YAESU HRI-200 等のノード環境

---

### インストール手順

1. **リポジトリのクローン**
   ```bash
   git clone https://github.com/your-username/funa-wrapper-wires-x.git
   cd funa-wrapper-wires-x
   ```

2. **必要パッケージのインストール**
   ```bash
   pip install pywin32 pywinauto textual
   ```

---

### 起動方法

Windows Terminal、PowerShell、またはコマンドプロンプトで以下を実行します：

```bash
python funa_tui.py
```

*※WIRES-X本体が起動していなくても、自動で検出・起動・アタッチが行われます。*

---

### キー操作リファレンス

| キー | 動作内容 |
| :---: | :--- |
| **`Tab`** | **VFO 切り替え**（VFO A: Room ⇔ VFO B: User/Node） |
| **`↑` / `↓`**<br>`j` / `k` | カーソル移動（選択） |
| **`Enter`** | **選択中の Room / Node へ即時接続**（接続中は自動で切断→待機→接続） |
| **`c`** | **ダイレクト ID 入力接続**（視認性の高いポップアップ入力画面） |
| **`d`** | **ワンキー切断**（確認ダイアログなしで即座に回線を切断） |
| **`r`** | **手動再同期**（Room / Node リストおよびトラフィック情報の更新） |
| **`q`** | **アプライアンス連動終了**（回線切断 ＆ WIRES-X本体を安全にシャットダウン） |

---

### ファイル構成

```text
funa-wrapper-wires-x/
├── wiresx_core.py      # 制御コア層 (Win32 API / UI Automation / 状態監視ドライバー)
├── funa_tui.py         # フロントエンドUI層 (Textual製 フルスクリーン Dual VFO TUI)
├── README.md           # 本ドキュメント
└── LICENSE             # ライセンスファイル
```

---

<br>

---

<a name="english"></a>
## 🌐 English

### Overview
**FUNA Wrapper for WIRES-X** is an appliance-grade Terminal User Interface (TUI) frontend and GUI wrapper designed for the YAESU WIRES-X VoIP amateur radio system. Inspired by vi/vim and classic MS-DOS console utilities, it provides a distraction-free, full-screen console experience for managing connections without touching a mouse.

Unlike brittle macro tools relying on mouse coordinates, FUNA Wrapper drives the native application directly via the **Windows API (`WM_COMMAND`, `SendMessage`, memory inspection, and UI Automation)**. It delivers a fast, robust **Dual VFO (VFO A: Room / VFO B: User)** operational workflow engineered specifically for ham radio operators chasing CQ calls.

---

### Key Features

1. **Dual VFO (Room & Node) Workflow**
   - Toggle instantly between **VFO A (Rooms)** and **VFO B (Users / Nodes)** using the **`Tab`** key.
   - Navigate with **`↑` / `↓`** (or **`j` / `k`**) and press **`Enter`** to connect immediately.
2. **Auto-Sorted Room Activity (Act)**
   - Automatically sorts rooms in descending order by active participant count (`Act`). The busiest, most active rooms always bubble to the top.
3. **Voice Packet-Synchronized Real-Time Active QSO**
   - Tracks incoming voice stream packets (`V:xxx`) directly from internal memory in real time.
   - Highlights the transmitting station (**`▶ ACTIVE QSO: [CALLSIGN] (DN)`**) only while voice packets are actively arriving. Automatically transitions to **`Last Heard: [CALLSIGN]`** ~1.6 seconds after PTT release.
4. **Smart Reconnect & Auto-Cooldown**
   - Seamlessly hop from one room/node to another. When initiating a connection while already connected, it executes an orderly disconnect, waits for line/socket deallocation (~2.5 seconds), and connects to the target without crashing or leaving stray dialogs behind.
5. **Immediate Connection Busy / Error Detection**
   - Parses the WIRES-X engine logs in real time. If rejected by a busy node or a digital-only room, an alert banner flashes **`[ ✖ CONNECTION BUSY ]`** in bold red alongside detailed diagnostic reasons.
6. **Live Traffic & Log Monitor**
   - Displays real-time connected room status, room member node counts, active callsigns, and a 3-line live streaming WIRES-X event log directly in the footer.
7. **Full Appliance Lifecycle Integration**
   - Auto-boots the WIRES-X background client if not already running upon wrapper launch.
   - Pressing **`q`** cleanly disconnects active calls, sends native shutdown messages to WIRES-X, releases hardware audio/COM handles, and exits cleanly.

---

### Terminal Layout

```text
+-----------------------------------------------------------------------------------+
| ▌FUNA Wrapper for WIRES-X▐  CURRENT: [VFO A (ROOM) *ACTIVE*]   [ ● CONNECTED ]    |
+-----------------------------------------+-----------------------------------------+
| 【 VFO A : ROOM ID 】 (Act Sorted/Enter) | 【 VFO B : USER / NODE ID 】 (Enter)     |
| Act │ Room ID │ Room Name   │ Desc     | Node ID │ Callsign    │ Node Name        |
| 046 │ 43534   │ PHILIPPINE  │ Link...  | 32386   │ JS1YVC      │ -NERIMA-         |
| 028 │ 21080   │ AMERICA-LINK│ Official | 10071   │ JR5YFG      │ --JR5YFG--       |
| 012 │ 20510   │ ALL JA CQ   │ Japan    | 18284   │ AE7JG       │ ---NWRARC1       |
+-----------------------------------------+-----------------------------------------+
| 【 LIVE TRAFFIC & SYSTEM LOG MONITOR 】                                           |
| ● ON AIR (CONNECTED) -> Room: PHILIPPINE-LINK(43534) | Members: 46 Nodes          |
| ▶ ACTIVE QSO: [ N6CLE-200 ] (DN) via WA6GM                                        |
| WIRES-X LOG: > 2026/10/01 01:16:46 Connected to PHILIPPINE-LINK(43534)            |
+-----------------------------------------------------------------------------------+
| Tab:Switch VFO | Enter:Connect | c:Direct ID | d:Disconnect | r:Sync | q:Shutdown |
+-----------------------------------------------------------------------------------+
```

---

### Requirements

* **Operating System**: Windows 10 / Windows 11 (64-bit recommended)
* **Python**: Python 3.10 or newer
* **Target Application**: YAESU WIRES-X (Default install path: `C:\Program Files (x86)\YAESUMUSEN\WIRES-X\Wires-X.exe`)
* **Hardware**: YAESU HRI-200 or compatible node setup

---

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/your-username/funa-wrapper-wires-x.git
   cd funa-wrapper-wires-x
   ```

2. **Install required dependencies**
   ```bash
   pip install pywin32 pywinauto textual
   ```

---

### Usage

Run the following command inside Windows Terminal, PowerShell, or Command Prompt:

```bash
python funa_tui.py
```

*Note: If the WIRES-X software is not currently running, FUNA Wrapper will automatically launch it, wait for initialization, and attach to it seamlessly.*

---

### Keybindings Reference

| Key | Action |
| :---: | :--- |
| **`Tab`** | **Toggle Active VFO** (VFO A: Room ⇔ VFO B: User/Node) |
| **`↑` / `↓`**<br>`j` / `k` | Move cursor up / down |
| **`Enter`** | **Connect to Selected Target** (Handles disconnect + cooldown automatically) |
| **`c`** | **Direct ID Connect Dialog** (High-visibility modal input) |
| **`d`** | **Instant Disconnect** (One-key disconnect without confirmation prompts) |
| **`r`** | **Manual Refresh / Sync** (Reloads lists and traffic caches) |
| **`q`** | **Appliance Shutdown** (Disconnects line and cleanly terminates WIRES-X) |

---

### Architecture & Components

* **`wiresx_core.py`** : The Control Core layer. Manages Windows process handles, control IDs, memory marshaling across 32-bit/64-bit boundaries, packet counter monitoring, and low-level API commands. Completely decoupled from the UI.
* **`funa_tui.py`** : The Presentation layer. An asynchronous terminal UI application powered by the Textual framework, sporting a retro MS-DOS aesthetic with reactive event loops.

---

### Disclaimer

This software is an independent, open-source project developed for amateur radio enthusiasts. It is **not** affiliated with, endorsed by, or supported by YAESU MUSEN CO., LTD. "WIRES-X" is a registered trademark of YAESU MUSEN CO., LTD.

### License

This project is licensed under the [MIT License](LICENSE).
```