# FUNA Amateur VoIP Transceiver Frontend (IU2EUG Appliance)

A lightweight, keyboard-driven MS-DOS/VFO-style Textual TUI frontend for **DMR Master** on Windows.  
Windows向けDMR VoIPソフトウェア「DMR Master」を、軽快かつ最小限のキーボード操作でオペレートするためのレトロスタイルTUIフロントエンドです。

---

## Language / 言語切替
- [日本語 (Japanese)](#日本語-japanese)
- [English](#english)

---

## 日本語 (Japanese)

### 概要
**DMR Master** は、BrandMeisterなどのDMRネットワークにPC単体で接続・交信できる優れたWindows用VoIPクライアントです。  
しかし、マウス操作を前提としたGUIであるため、「キーボードだけで素早くトークグループ（TG）を切り替えたい」「スペースキーの長押しだけで直感的にPTTを送受したい」「作業中に邪魔にならない軽快なコンソール画面で常駐させたい」といったアマチュア無線機（トランシーバー）らしい操作感にはいくつかのハードルがありました。

本ツールは、DMR MasterのGUIウィンドウを自動的にバックグラウンド（画面外）へステルス退避させ、UIAutomationとWin32 APIを用いてエンジンとして完全制御します。画面にはMS-DOSやレトロリグを彷彿とさせるフルスクリーンTUIを展開し、VFOダイヤル感覚でのTG切り替えや、スペースキー長押しによる軽快な交信環境を提供します。

### 主な機能・特徴
- 📟 **MS-DOS / レトロコンソール風 TUI**:
  - `Textual` ライブラリを採用。青背景に白・黄を基調とした見やすく目に優しいインターフェース。
- 🎙️ **スペースキーによる直感的 PTT**:
  - `Space` キーを長押ししている間だけ送信（TX）、離せば即座に受信待機（RX）へ復帰（Win32 `GetAsyncKeyState` による低遅延検出）。
- 🎛️ **VFO感覚のチャンネル切り替え**:
  - DMR Masterに登録されたトークグループを自動取得。`↑` / `↓` キーで選択し `Enter` を押すだけで即座に接続。
- 🔢 **クイック Direct TG 入力**:
  - 数字キー（`0`〜`9`）を押すか、`t` キーを押すだけで即座にダイレクトTG入力ダイアログが起動。世界中のTG（例: `440`, `91`, `9990` など）へ即座にQSY可能。
- 📊 **リアルタイム・トラフィックモニター & Sメーター**:
  - 受信中のコールサイン、オペレーター名、宛先TGを自動解析してハイライト表示。
  - パケットロス率からデジタルSメーターをグラフィカルに描画。
- ⚙️ **オーディオ・DSP設定ダイアログ (`m` キー)**:
  - マイク入力 / スピーカー出力デバイスの切り替え。
  - AGC（自動利得制御）、Limiter（リミッター）、Noise Gateのトグル切り替えに対応。
- 🥷 **ステルス起動 & 完全フォーカス制御**:
  - DMR Masterの実行ファイルを自動探索して起動。GUIウィンドウを画面外（座標 10000, 10000）へ移動し、誤操作を防止。
  - Windows 11 / Windows Terminal環境でも確実に入力を受け付けるAltハック＆フォーカス吸着機構を内蔵。
  - 本ツール終了時（`q`）には、バックグラウンドのDMR Masterも自動的に安全終了。

### 動作要件
- **OS**: Windows 10 / Windows 11 (64-bit)
- **Python**: Python 3.9 以降
- **対象ソフトウェア**: [DMR Master](https://dmrmaster.com/) がPCにインストールまたは展開されていること

### セットアップ手順

1. **必要なライブラリのインストール**:
   ```cmd
   pip install textual rich uiautomation
   ```

2. **DMR Masterの準備**:
   - 初回のみ、DMR Master本体を通常通り起動し、コールサイン、DMR ID、パスワード、接続サーバー等の初期設定を完了させておいてください。
   - DMR Masterが起動した状態のままでも、終了した状態からでも本スクリプトを実行可能です（自動検出・起動します）。

3. **実行**:
   ```cmd
   python "FUNA Amateur VoIP Transceiver Frontend v2.py"
   ```
   *※ DMR Masterのパスは自動検出され、次回以降のために同階層の `dmr_config.json` に保存されます。*

### 操作方法（キーバインド）

| キー | 動作 |
| :--- | :--- |
| **`Space` (長押し)** | **PTT 送信 (Push-to-Talk)** / 離すと受信待機 |
| **`↑` / `↓`** | VFOトークグループ一覧のカーソル移動 |
| **`Enter`** | 選択中のトークグループへ接続 |
| **`0` 〜 `9` または `t`** | Direct TG入力モーダルを開く（任意のTG番号を直接入力して接続） |
| **`m`** | オーディオルーティング＆DSP設定メニューを開く |
| **`s`** | DMR Masterからトークグループ一覧を強制再同期 |
| **`c`** | 画面下部のアクティビティログを消去 |
| **`q`** | アプリケーション終了（DMR Masterも同時にシャットダウン） |
| **`Esc`** | 各種ダイアログを閉じる・キャンセル |

---

## English

### Overview
**DMR Master** is a Windows VoIP client that enables amateur radio operators to access DMR networks (such as BrandMeister) directly from a PC without requiring a physical radio.  
While DMR Master provides a rich graphical interface, operating it with a mouse can be cumbersome when you want quick talkgroup changes, low-latency Push-to-Talk (PTT), and a lightweight transceiver-like experience.

**FUNA Amateur VoIP Transceiver Frontend** solves this by converting DMR Master into a headless background engine. It stealths the DMR Master GUI away to off-screen coordinates and exposes a responsive, retro MS-DOS / VFO-style terminal interface built with Textual.

### Key Features
- 📟 **Retro MS-DOS Style TUI**:
  - Classic blue-and-cyan aesthetic powered by `Textual`. Clean, distraction-free, and easy on the eyes.
- 🎙️ **Intuitive Hold-to-Talk (Spacebar PTT)**:
  - Hold `Space` to transmit; release to receive. Utilizes Win32 low-level asynchronous key detection (`GetAsyncKeyState`) for instant response.
- 🎛️ **VFO Channel Browsing**:
  - Automatically imports your Talkgroup list from DMR Master. Select channels with `↑` / `↓` and connect instantly with `Enter`.
- 🔢 **Instant Direct TG Dialing**:
  - Press any digit (`0`-`9`) or `t` to open the Direct TG entry dialog. Enter any TG ID (e.g., `91`, `440`, `9990`) to QSY immediately.
- 📊 **Live RX Traffic & Digital S-Meter**:
  - Real-time decoding and display of active Call signs, Operator names, and Destination TGs.
  - S-Meter bar dynamically computed from real-time packet loss rates.
- ⚙️ **Audio Routing & DSP Menu (`m`)**:
  - Quickly toggle input microphones and output endpoints.
  - Toggle DSP processors: AGC, Limiter, and Noise Gate.
- 🥷 **Stealth Mode & Bulletproof Focus Hook**:
  - Automatically searches, launches, and moves the DMR Master GUI off-screen (`x=10000, y=10000`).
  - Contains Windows Alt-hack routines to keep terminal focus sticky across Windows Terminal and conhost.
  - Clean shutdown sequence (`q`) terminates both the TUI and background DMR Master process safely.

### Requirements
- **Operating System**: Windows 10 / Windows 11 (64-bit)
- **Python**: Python 3.9+
- **Host Application**: [DMR Master](https://dmrmaster.com/) installed and pre-configured (Callsign, DMR ID, Password, BrandMeister server).

### Installation & Quick Start

1. **Install dependencies**:
   ```cmd
   pip install textual rich uiautomation
   ```

2. **Initial DMR Master Setup**:
   - Launch DMR Master normally once and verify your login credentials, audio devices, and network connection.
   - You can leave it open or close it before launching the frontend.

3. **Run the Frontend**:
   ```cmd
   python "FUNA Amateur VoIP Transceiver Frontend v2.py"
   ```
   *The script automatically learns the location of `DMR Master.exe` and saves it to `dmr_config.json` for future launches.*

### Keybindings Reference

| Key | Action |
| :--- | :--- |
| **`Space` (Hold)** | **Push-To-Talk (TX)** / Release to Return to Standby (RX) |
| **`Up` / `Down`** | Navigate Talkgroup / VFO table |
| **`Enter`** | Connect to selected Talkgroup |
| **`0` - `9` or `t`** | Open Direct Talkgroup entry modal |
| **`m`** | Open Audio routing & DSP setup modal |
| **`s`** | Re-sync Talkgroup list from DMR Master |
| **`c`** | Clear activity log screen |
| **`q`** | Quit application (Safely terminates DMR Master) |
| **`Esc`** | Cancel / Close active dialog |

---

## 仕組み / Architecture

```
+-------------------------------------------------------------+
|        FUNA VoIP Transceiver Frontend (Textual TUI)         |
|  - VFO Table Navigation    - RX Call/Traffic Monitor       |
|  - Spacebar PTT Listener   - Quick Direct TG Entry          |
+-------------------------------------------------------------+
                              |
       Win32 PostMessage / UIAutomation IPC Hooks
                              |
+-------------------------------------------------------------+
|         DMR Master (Hidden / Stealthed at Off-screen)       |
|  - DMR Protocol Stack      - Audio Codec & DSP Engine       |
|  - BrandMeister Gateway    - Sound Device Input/Output      |
+-------------------------------------------------------------+
```

## 免責事項 / Disclaimer
- 本ソフトウェアは個人利用およびアマチュア無線の運用の便宜を図る目的で作成された非公式のラッパーフロントエンドです。
- 各国の電波法およびアマチュア業務の運用規則、各VoIPネットワーク（BrandMeister等）の利用規約を遵守して運用してください。
- This software is an unofficial frontend wrapper designed for personal amateur radio convenience. Please ensure compliance with local radio regulations and VoIP network policies.

## Credits & 73!
- Developed by **IU2EUG / FUNA Appliance Project**
- Powered by [Textual](https://github.com/Textualize/textual), [Rich](https://github.com/Textualize/rich), and [UIAutomation](https://github.com/yinkaisheng/Python-UIAutomation-for-Windows).
```
