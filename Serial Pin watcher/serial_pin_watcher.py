"""
====================================================================
 USB Serial Input Pin Watcher
 File: serial_pin_watcher.py

 監視対象ピン (全4入力系統):
   - 1番ピン: DCD (Carrier Detect)
   - 6番ピン: DSR (Data Set Ready)
   - 8番ピン: CTS (Clear to Send)
   - 9番ピン: RI  (Ring Indicator)
====================================================================
"""

import sys
import time
import serial
import serial.tools.list_ports


def select_com_port() -> str:
    """COMポートの自動検出・選択"""
    ports = list(serial.tools.list_ports.comports())
    if not ports:
        print("[-] 利用可能なCOMポートが見つかりません。")
        sys.exit(1)

    if len(ports) == 1:
        port_name = ports[0].device
        print(f"[+] COMポート自動検出: {port_name} ({ports[0].description})")
        return port_name

    print("[*] 複数のCOMポートが見つかりました:")
    for i, p in enumerate(ports):
        print(f"    [{i + 1}] {p.device} ({p.description})")
    choice = input(f"ポート番号を選択 (1〜{len(ports)}): ").strip()
    try:
        return ports[int(choice) - 1].device
    except Exception:
        return ports[0].device


def get_all_input_pins(ser: serial.Serial) -> dict:
    """全4入力ピンの論理状態を一括取得"""
    # pyserial の仕様差異を吸収 (cd または dcd)
    cd_val = getattr(ser, "cd", getattr(ser, "dcd", False))
    return {
        "DCD (1番ピン)": bool(cd_val),
        "DSR (6番ピン)": bool(ser.dsr),
        "CTS (8番ピン)": bool(ser.cts),
        "RI  (9番ピン)": bool(ser.ri),
    }


def main():
    print("=" * 65)
    print(" USBシリアル入力ピン・ウォッチャー (Pin Watcher)")
    print("=" * 65)

    port_name = select_com_port()

    try:
        ser = serial.Serial(port_name, timeout=0.1)
    except Exception as e:
        print(f"[-] ポートオープン失敗: {e}")
        sys.exit(1)

    print("\n[*] 初期待機レベルを学習中... (マイクのPTTは触らないでください)")
    time.sleep(0.5)

    # 何も押していない「待機時の初期論理レベル」を記録
    baseline = get_all_input_pins(ser)

    print("\n" + "=" * 65)
    print(f"  ポート [{port_name}] の入力4ピンを監視開始しました。")
    print("  マイク① または マイク② の PTT を押してみてください。")
    print("  どのピンがGNDに落ちたかをリアルタイムに検出します。")
    print("  [終了: Ctrl + C]")
    print("=" * 65 + "\n")

    last_active_pins = set()

    try:
        while True:
            current_pins = get_all_input_pins(ser)

            # 初期状態から論理レベルが反転したピン ＝「GNDに落とされたピン」
            active_pins = set()
            for pin_name, curr_val in current_pins.items():
                if curr_val != baseline[pin_name]:
                    active_pins.add(pin_name)

            # 状態変化（イベント）の検知・ログ表示
            pressed_pins = active_pins - last_active_pins
            released_pins = last_active_pins - active_pins

            timestamp = time.strftime("%H:%M:%S")

            for pin in pressed_pins:
                print(f"[{timestamp}] ★★★ 【検知】 {pin} が GND に落ちました！ (PTT ON) ★★★")

            for pin in released_pins:
                print(f"[{timestamp}] --- [解除] {pin} が 開放されました (PTT OFF)")

            last_active_pins = active_pins

            # コンソール下部に現在の4ピンのリアルタイムメーターを表示
            meter_line = []
            for pin_name in sorted(current_pins.keys()):
                is_grounded = pin_name in active_pins
                status_str = "● GND " if is_grounded else "○ OPEN"
                meter_line.append(f"{pin_name[:3]}:[{status_str}]")

            sys.stdout.write("\rリアルタイム監視: " + " | ".join(meter_line) + "   ")
            sys.stdout.flush()

            time.sleep(0.02)  # 20ms ポーリング

    except KeyboardInterrupt:
        print("\n\n[*] 監視を終了しました。")
    finally:
        ser.close()


if __name__ == "__main__":
    main()