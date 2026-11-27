# UsbSerialPtt

USBシリアル変換器の制御線（CTS / DSR / CD / RI）を、Android上のVoIPアプリのハードウェアPTTとして使うためのアプリです。

アマチュア無線の自作インターフェース「Super Kurchunk Gen2」と組み合わせると、無線機のスピーカーマイクのPTTスイッチで、QSO OneなどのAndroidアプリの送受信を切り替えられます。「使い慣れた無線機のマイクを握ってVoIPで交信する」ための橋渡しアプリです。

デモ動画（スマートフォン＋Super Kurchunk）: https://youtu.be/gL1hC6ltb88

English description is at the bottom of this page (see "English").

## ダウンロード

**[Usbserialptt.apk — Google Drive](https://drive.google.com/file/d/17MlE17ef1WRMBeqdrutXdPQrNKZYVSeW/view?usp=drivesdk)**（Android用、約6.3MB。ビルド済みのAPKです。そのまま端末にインストールできます）

## 仕組み

- ユーザー補助サービス（AccessibilityService）がUSBシリアル変換器に接続し、選択した制御線を10ms周期でポーリングします（簡易チャタリング除去付き）。
- 制御線がアクティブになると、画面上であらかじめ保存した座標（アプリのPTTボタンの位置）へロングプレス・ジェスチャーを送り続けます。ピンを離すとジェスチャーを中断し、送信を止めます。
- 連続送信保護タイマー（TOT）として、3分で自動的に送信を停止します。1回のジェスチャーは最大55秒で、ピンがONのままなら自動で継続します。
- 9600bps / 8N1でポートを開きます（制御線の読み取りのみで、データ通信はしません）。

## 設定項目

- PTTボタンの座標（X / Y）：対象アプリのPTTボタン中心の画面座標
- 対象ピン：CTS / DSR / CD / RI から選択
- 論理反転：制御線のアクティブ極性に合わせて切り替え

## 動作環境

- Android 8.0（API 26）以上
- USBホスト（OTG）対応のAndroid端末
- USBシリアル変換器（usb-serial-for-android が対応するチップ：FTDI、CP210x、CH340、PL2303など）
- Kotlin製。ライブラリは usb-serial-for-android 3.12.0（mik3y）を使用

## 使い方

1. Android Studioでビルドして端末にインストールします。
2. アプリを開き、「USB権限を要求」で変換器へのアクセスを許可します。
3. 「ユーザー補助設定を開く」から UsbSerialPtt のユーザー補助サービスを有効にします。
4. 対象アプリのPTTボタンの座標を入力し、ピンと論理反転を設定して保存します。
5. Super Kurchunk Gen2（または相当のインターフェース）を接続し、マイクのPTTを押して動作を確認します。

## このリポジトリに含まれていないもの

GitHubへの一括アップロードの制約により、バイナリファイルは除外しています。ビルド時に必要であれば、Android Studioで新規プロジェクトを作成し、次をコピーしてください。

- gradle/wrapper/gradle-wrapper.jar（Gradle 9.6.0用）
- app/src/main/res/mipmap-* の ic_launcher.webp / ic_launcher_round.webp（デフォルトのランチャーアイコン）

また、local.properties（ローカルのSDKパス）とビルド生成物（build/、.gradle/ 等）は元々含めていません。

## 備考

- パッケージ名 com.example.usbserialptt は仮のものです。ご自身の環境に合わせて変更してください（ソース内のコメントにも記載があります）。
- バージョン 1.0（debugビルドで運用中）。
- 今後の課題：切断ボタンへの入力ピン割り当てなど、残りの制御線の活用を検討中です。

## English

UsbSerialPtt turns the control lines (CTS / DSR / CD / RI) of a USB serial adapter into a hardware PTT for VoIP apps on Android.

Combined with my homebrew interface "Super Kurchunk Gen2", it lets you key the PTT of Android apps such as QSO One with the PTT switch of a real radio's speaker microphone — a bridge for "holding a familiar radio mic while talking over VoIP".

Demo video (smartphone + Super Kurchunk): https://youtu.be/gL1hC6ltb88

### Download

**[Usbserialptt.apk — Google Drive](https://drive.google.com/file/d/17MlE17ef1WRMBeqdrutXdPQrNKZYVSeW/view?usp=drivesdk)** (Android, approx. 6.3 MB. A prebuilt APK — just install it on your device; no Android Studio build needed.)

Note: UsbSerialPtt is still a prototype under active development — design and implementation are ongoing. The circuit and configuration diagrams of the hardware that connects to the smartphone will be published later (in preparation).

### How it works

- An AccessibilityService connects to the USB serial adapter and polls the selected control line every 10 ms (with simple debounce).
- While the line is active, it keeps sending a long-press gesture to the saved on-screen coordinates (the target app's PTT button). Releasing the pin cancels the gesture and stops transmission.
- A time-out timer (TOT) stops transmission automatically after 3 minutes. Each gesture lasts up to 55 seconds and is renewed automatically while the pin stays ON.
- The port is opened at 9600 bps / 8N1 (control-line reading only; no data communication).

### Settings

- PTT button coordinates (X / Y): the screen coordinates of the target app's PTT button
- Input pin: CTS / DSR / CD / RI
- Logic invert: to match the active polarity of your interface

### Requirements

- Android 8.0 (API 26) or later
- A USB host (OTG) capable Android device
- A USB serial adapter supported by usb-serial-for-android (FTDI, CP210x, CH340, PL2303, …)
- Written in Kotlin; uses usb-serial-for-android 3.12.0 (mik3y)

### Usage

1. Install the APK (or build it with Android Studio).
2. Open the app and grant USB permission for the adapter.
3. Open the accessibility settings and enable the UsbSerialPtt accessibility service.
4. Enter the PTT button coordinates of the target app, choose the pin and logic invert, and save.
5. Connect Super Kurchunk Gen2 (or an equivalent interface) and test with the microphone's PTT.

### Not included in this repository

Binary files are excluded because of the bulk-upload route used for GitHub. If you build from source, create a new Android Studio project and copy in:

- gradle/wrapper/gradle-wrapper.jar (for Gradle 9.6.0)
- The default launcher icons (ic_launcher.webp / ic_launcher_round.webp under app/src/main/res/mipmap-*)

local.properties and build outputs (build/, .gradle/, …) are not included either.

### Notes

- The package name com.example.usbserialptt is provisional; change it for your own environment.
- Version 1.0 (running as a debug build).
- Future work: using the remaining control lines, e.g. assigning one pin to a disconnect button.

## ライセンス

このリポジトリ（JL1LBI/ham-radio）のルートにある LICENSE に従います。

JL1LBI
