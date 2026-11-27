# UsbSerialPtt

USBシリアル変換器の制御線（CTS / DSR / CD / RI）を、Android上のVoIPアプリのハードウェアPTTとして使うためのアプリです。

アマチュア無線の自作インターフェース「Super Kurchunk Gen2」と組み合わせると、無線機のスピーカーマイクのPTTスイッチで、QSO OneなどのAndroidアプリの送受信を切り替えられます。「使い慣れた無線機のマイクを握ってVoIPで交信する」ための橋渡しアプリです。

デモ動画（スマートフォン＋Super Kurchunk）: https://youtu.be/gL1hC6ltb88

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

## ライセンス

このリポジトリ（JL1LBI/ham-radio）のルートにある LICENSE に従います。

JL1LBI
