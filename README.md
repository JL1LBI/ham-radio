```markdown
# USB Serial Input Pin Watcher (PTT Line Checker)

アマチュア無線向けVoIPソフトウェアやインターフェース自作時に、USBシリアル変換ケーブルの入力制御ピン（DCD / DSR / CTS / RI）を使った **「ハードウェアPTT（Push To Talk）」の導通・動作確認をリアルタイムに行うための診断ツール** です。

---

## 📌 開発の背景・概要

EchoLink や WIRES-X、AllStarLink、SVXLink などのアマチュア無線VoIPソフトウェアでは、マイクのPTT信号をUSBシリアル変換アダプタ（FTDI / Prolific / CH340等）のRS-232C入力制御ピンに入力して送受信切り替えを行う手法が広く用いられています。

しかし、いざ環境を組む際に以下のようなトラブルで悩まされることがよくあります：

- 「VoIPソフト側でPTTが認識しないが、ソフトの設定ミスなのか、配線ミスなのか、マイクスイッチの不良なのか切り分けができない」
- 「マイクのPTTを押したとき、DB-9コネクタのどのピンがGNDに落ちているのか確認したい」
- 「テスターを当てながらマイクを握るのが大変」

本ツール（`serial_pin_watcher.py`）を実行すると、**監視対象の4系統の入力ピンを高速ポーリング（20ms）し、PTTのON/OFF（GNDへのショート/開放）をリアルタイムに検知して画面にログとメーターを表示**します。VoIPソフト側の設定を行う前に、ハードウェア単体での導通テスト・ピン特定を素早く確実に行うことができます。

---

## ✨ 主な機能

1. **4系統の入力ピンを一括同時監視**
   - 1番ピン: **DCD** (Carrier Detect)
   - 6番ピン: **DSR** (Data Set Ready)
   - 8番ピン: **CTS** (Clear to Send)
   - 9番ピン: **RI**  (Ring Indicator)
2. **初期待機状態の自動学習（ベースライン取得）**
   - 起動直後の「非押下状態」を基準とするため、プルアップ/プルダウンや論理反転を意識することなく、「GNDに落ちた（PTTが押された）」変化を確実に検出します。
3. **イベントログ & リアルタイムメーター**
   - PTTのON（GND落ち）/ OFF（開放）の瞬間をタイムスタンプ付きで検知・通知します。
   - コンソール最下行に4ピンの状態メーターを常時インライン表示します。
4. **COMポート自動検出**
   - PCに接続されているCOMポートを検出し、1つの場合は自動選択、複数の場合は対話形式で選択可能です。

---

## 🔌 対象ピンアサイン（DB-9 コネクタ）

一般的な D-Sub 9ピン（オス/メス）シリアル端子のピンアサインです。PTTスイッチは通常 **「5番ピン（GND）」と各入力ピンの間** に配線します。

| ピン番号 | 信号名 | 方向 | 役割 / 本ツールでの監視 |
|:---:|:---:|:---:|:---|
| **1** | **DCD** | 入力 | キャリア検出 (PTT候補①) |
| 2 | RXD | 入力 | データ受信 (監視対象外) |
| 3 | TXD | 出力 | データ送信 (監視対象外) |
| 4 | DTR | 出力 | データ端末レディ (監視対象外) |
| **5** | **GND** | 基準 | **シグナルグランド (コモン基準ライン)** |
| **6** | **DSR** | 入力 | データセットレディ (PTT候補②) |
| 7 | RTS | 出力 | 送信要求 (監視対象外) |
| **8** | **CTS** | 入力 | 送信可 (PTT候補③) |
| **9** | **RI**  | 入力 | 被呼表示 (PTT候補④) |

```text
       1       2       3       4       5
   ┌───o───────o───────o───────o───────o───┐
    \ [DCD]  [RXD]   [TXD]   [DTR]   [GND]/
     \                                   /
      \    o       o       o       o    /
       └───o───────o───────o───────o───┘
           6       7       8       9
         [DSR]   [RTS]   [CTS]    [RI]
```

---

## 💻 動作環境・必要要件

- **Python**: 3.8 以上
- **ライブラリ**: `pyserial`
- **OS**: Windows / macOS / Linux

---

## 🚀 インストールと準備

### 1. リポジトリのクローン（またはファイルのダウンロード）

```bash
git clone https://github.com/JL1LBI/ham-radio.git
cd ham-radio
```

### 2. 依存ライブラリのインストール

```bash
pip install pyserial
```

---

## 📖 使い方

1. USBシリアル変換ケーブル（およびマイクインターフェース）をPCに接続します。
2. スクリプトを実行します：
   ```bash
   python serial_pin_watcher.py
   ```
3. ポート選択画面が出たら、使用するCOMポートの番号を入力します（ポートが1つだけの場合は自動選択されます）。
4. **「初期待機レベルを学習中...」** と表示されたら、**約0.5秒間マイクのPTTには触れずにお待ちください**。
5. 監視が始まったら、マイクのPTTスイッチを押したり離したりしてください。

### 実行画面イメージ

```text
=================================================================
 USBシリアル入力ピン・ウォッチャー (Pin Watcher)
=================================================================
[+] COMポート自動検出: COM3 (USB Serial Port)

[*] 初期待機レベルを学習中... (マイクのPTTは触らないでください)

=================================================================
  ポート [COM3] の入力4ピンを監視開始しました。
  マイク① または マイク② の PTT を押してみてください。
  どのピンがGNDに落ちたかをリアルタイムに検出します。
  [終了: Ctrl + C]
=================================================================

[21:45:02] ★★★ 【検知】 CTS (8番ピン) が GND に落ちました！ (PTT ON) ★★★
[21:45:05] --- [解除] CTS (8番ピン) が 開放されました (PTT OFF)
[21:45:08] ★★★ 【検知】 DSR (6番ピン) が GND に落ちました！ (PTT ON) ★★★
[21:45:10] --- [解除] DSR (6番ピン) が 開放されました (PTT OFF)

リアルタイム監視: CTS:[○ OPEN] | DCD:[○ OPEN] | DSR:[○ OPEN] | RI :[○ OPEN]
```

- 終了する場合はコンソールで `Ctrl + C` を押します。

---

## 🛠️ トラブルシューティング

- **PTTを押しても検知ログが出ない場合:**
  - マイク内部のスイッチがコモンGND（5番ピン）と確実に導通しているかテスター等で確認してください。
  - RS-232Cレベル（±12V）のアダプタの場合、TTLレベル（0V-5V）直結では閾値を跨げない場合があります。
- **起動時にポートが開けない (`PermissionError` など):**
  - VoIPソフトやターミナルソフト（Tera Termなど）がすでに同じCOMポートを開いていないか確認してください（ポートは排他利用となります）。

---

## 📝 ライセンス

MIT License

## ✍️ 作者

- **Callsign:** JL1LBI
- **GitHub:** [@JL1LBI](https://github.com/JL1LBI)
```

# USB Serial Input Pin Watcher (Hardware PTT Line Checker)

A real-time diagnostic utility designed for amateur radio operators to verify **hardware PTT (Push-To-Talk) input signals** (DCD / DSR / CTS / RI) on USB-to-serial adapters.

---

## 📌 Background & Overview

When setting up amateur radio VoIP software such as **EchoLink, AllStarLink (app_rpt), SVXLink, or WIRES-X**, operators often connect a microphone PTT switch to the control lines of an RS-232 / USB serial adapter (FTDI, Prolific, CH340, CP2102, etc.) to trigger transmission or carrier detection.

However, troubleshooting these hardware interfaces can often be frustrating:
- *"Is the VoIP software misconfigured, or is the physical PTT switch/wiring faulty?"*
- *"Which DB-9 input pin is being pulled to GND when I key Mic 1 or Mic 2?"*
- *"It is awkward to hold multimeter probes against tiny connector pins while keying the mic."*

`serial_pin_watcher.py` solves this problem. It polls all 4 serial input pins simultaneously at high speed (20 ms interval), establishes an idle baseline automatically, and detects state changes in real time. You can instantly confirm whether your microphone switch and physical wiring are working properly before diving into complex VoIP software configurations.

---

## ✨ Key Features

1. **Simultaneous 4-Pin Monitoring**
   - Pin 1: **DCD** (Data Carrier Detect)
   - Pin 6: **DSR** (Data Set Ready)
   - Pin 8: **CTS** (Clear to Send)
   - Pin 9: **RI**  (Ring Indicator)
2. **Automatic Baseline Calibration**
   - Automatically learns the "idle / unpressed" logic level upon launch (takes ~0.5 seconds). You don't need to worry about pull-up/pull-down logic or inverted levels—it accurately detects when a line is grounded.
3. **Event Logging & Live Status Bar**
   - Prints timestamped event logs whenever a PTT press (GND) or release (OPEN) occurs.
   - Displays a dynamic, in-place visual status meter at the bottom of the console.
4. **Auto COM Port Detection**
   - Scans available serial ports automatically; selects directly if only one is found, or prompts you to pick from a list if multiple adapters are connected.

---

## 🔌 DB-9 Pinout Reference

For a standard DE-9 / DB-9 connector, the PTT switch is typically wired between **Pin 5 (GND)** and one of the input control pins:

| Pin # | Signal | Direction | Role / Monitored Status |
|:---:|:---:|:---:|:---|
| **1** | **DCD** | Input | Carrier Detect (PTT candidate 1) |
| 2 | RXD | Input | Receive Data (Not monitored) |
| 3 | TXD | Output | Transmit Data (Not monitored) |
| 4 | DTR | Output | Data Terminal Ready (Not monitored) |
| **5** | **GND** | Ground | **Signal Ground (Common reference line)** |
| **6** | **DSR** | Input | Data Set Ready (PTT candidate 2) |
| 7 | RTS | Output | Request to Send (Not monitored) |
| **8** | **CTS** | Input | Clear to Send (PTT candidate 3) |
| **9** | **RI**  | Input | Ring Indicator (PTT candidate 4) |

```text
       1       2       3       4       5
   ┌───o───────o───────o───────o───────o───┐
    \ [DCD]  [RXD]   [TXD]   [DTR]   [GND]/
     \                                   /
      \    o       o       o       o    /
       └───o───────o───────o───────o───┘
           6       7       8       9
         [DSR]   [RTS]   [CTS]    [RI]
```

---

## 💻 Requirements

- **Python**: 3.8 or higher
- **Dependency**: `pyserial`
- **Supported OS**: Windows, macOS, Linux

---

## 🚀 Installation & Setup

### 1. Clone the repository

```bash
git clone https://github.com/JL1LBI/ham-radio.git
cd ham-radio
```

### 2. Install dependencies

```bash
pip install pyserial
```

---

## 📖 How to Use

1. Plug in your USB-to-serial adapter and connect your microphone/interface circuitry.
2. Run the script:
   ```bash
   python serial_pin_watcher.py
   ```
3. If multiple ports are detected, choose the corresponding port number.
4. **Wait ~0.5 seconds** while the script calibrates:
   > `[*] 初期待機レベルを学習中... (マイクのPTTは触らないでください)`  
   > *(Learning baseline... Do NOT touch the PTT switch during this moment)*
5. Once monitoring begins, key and release your microphone PTT switch.

### Example Console Output

```text
=================================================================
 USBシリアル入力ピン・ウォッチャー (Pin Watcher)
=================================================================
[+] COMポート自動検出: COM3 (USB Serial Port)

[*] 初期待機レベルを学習中... (マイクのPTTは触らないでください)

=================================================================
  ポート [COM3] の入力4ピンを監視開始しました。
  マイク① または マイク② の PTT を押してみてください。
  どのピンがGNDに落ちたかをリアルタイムに検出します。
  [終了: Ctrl + C]
=================================================================

[21:45:02] ★★★ 【検知】 CTS (8番ピン) が GND に落ちました！ (PTT ON) ★★★
[21:45:05] --- [解除] CTS (8番ピン) が 開放されました (PTT OFF)
[21:45:08] ★★★ 【検知】 DSR (6番ピン) が GND に落ちました！ (PTT ON) ★★★
[21:45:10] --- [解除] DSR (6番ピン) が 開放されました (PTT OFF)

リアルタイム監視: CTS:[○ OPEN] | DCD:[○ OPEN] | DSR:[○ OPEN] | RI :[○ OPEN]
```

- Press `Ctrl + C` at any time to exit cleanly.

---

## 🛠️ Troubleshooting

- **No detection events logged when pressing PTT:**
  - Verify with a multimeter that your PTT switch reliably shorts the target pin to Pin 5 (GND).
  - Note that true RS-232 voltage levels (±12V) vs. TTL levels (0V–5V) have different threshold voltages. Make sure your adapter matches your signal source.
- **Port cannot be opened (`PermissionError` / `AccessDenied`):**
  - Ensure no other terminal emulator (e.g., PuTTY, Tera Term) or VoIP application is currently using the same COM port. Serial ports can only be accessed exclusively by one process.

---

## 📝 License

Distributed under the [MIT License](LICENSE).

## ✍️ Author

- **Callsign:** JL1LBI
- **GitHub:** [@JL1LBI](https://github.com/JL1LBI)

73!
```
