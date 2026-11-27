# QSO One Watch

A listen-only "watch" client for [QSO One](https://qso1.net) Beacon rooms, styled after a triple-VFO amateur radio receiver. Pick up to three Beacon rooms, press **Connect**, and listen to all of them at once — each VFO has its own orange BUSY lamp that lights up while someone is talking.

日本語の説明は下部にあります。

## Features

- **Triple-VFO simultaneous watch** — monitor up to 3 Beacon rooms at the same time; audio is mixed and played through a single output
- **Japan rooms first** — the room list is fetched live from the API and sorted with Japanese rooms (Japan, Japan-X, JP-Izumo_Room, …) at the top; the three JP rooms are the factory defaults
- **Orange BUSY LED per VFO**, plus a per-slot state indicator (OFF / … / RX / ERR)
- **QSY while connected** — change a VFO's room in the dropdown and only that slot reconnects to the new room
- **Auto-reconnect** — if a connection drops, the slot re-fetches its token and reconnects after 5 seconds
- **Trilingual UI** — 日本語 / English / Français, switchable in the window and remembered
- **System-tray residency** — minimize to the tray; the tray menu offers Show Window, Mute All, Always on Top, and Quit
- **Always-on-top and Mute-All toggles**, persisted between runs
- **Settings saved** to `%APPDATA%\qso1-vfo-watch\config.json` (language, topmost, mute, and the three VFO room selections)
- Dark, radio-panel-style UI built with tkinter; the footer credit links to the author's QRZ page

## How it works

The app talks to the same web API the official Beacon web client uses:

1. `GET https://qso1.net/api/beacon/w/rooms/active?limit=50` — list of currently active rooms (slug, name, listener count)
2. `POST https://qso1.net/api/beacon/w/token` with `{"room": "<slug>", "listen_only": true}` — returns the LiveKit server URL (`wss://beacon*.qso1.net`) and a listen-only JWT for that room
3. The official [LiveKit Python SDK](https://github.com/livekit/python-sdk) connects with that token, each room's audio tracks are fed into an `rtc.AudioMixer`, and the mixed 48 kHz mono stream is played with `sounddevice`

It is **receive-only by design**: the token is requested with `listen_only: true` and the app never publishes audio. No callsign login is required to listen.

## Requirements

- Python 3.10–3.12 (developed and tested on Windows)
- Packages:

```
pip install livekit sounddevice numpy requests pystray Pillow
```

## Run

```
python qso1_vfo_gui.py
```

Choose rooms in the three VFO dropdowns (or leave a slot on `-- OFF --`), then press **接続 / Connect**.

## Build a single-file exe (optional)

```
pyinstaller --onefile --noconsole --name qso1-vfo-watch --collect-all livekit --collect-all sounddevice --hidden-import livekit.rtc.resources --hidden-import livekit.rtc.resources.liblivekit_ffi --hidden-import numpy qso1_vfo_gui.py
```

This produces `dist\qso1-vfo-watch.exe`.

## Notes

- Unofficial, personal project — not affiliated with QSO One. The API endpoints are the ones used by the official web client and may change without notice.
- Listening works without an account; transmitting is neither supported nor intended.

## 日本語

QSO OneのBeaconルームを「聞くだけ」でワッチするための、トリプルVFO同時受信機風のGUIアプリです。

- 3つのルームを同時ワッチ（音声はミックスして再生）
- ルーム一覧はAPIから取得し、Japan系ルームを先頭に表示（初期値：Japan／Japan-X／JP-Izumo_Room）
- VFOごとにオレンジ色のBUSYランプと状態表示（OFF／…／RX／ERR）
- 接続中のままプルダウンを変えると、そのVFOだけ即座にQSY（再接続）
- 切断時は自動で再接続、UIは日本語／English／Françaisの3か国語対応
- タスクトレイ常駐、常に前面表示、一括ミュート、設定は `%APPDATA%\qso1-vfo-watch\config.json` に保存
- 受信専用です。トークンは `listen_only: true` で取得し、送信は一切しません

実行：`python qso1_vfo_gui.py`（依存パッケージは上記 Requirements を参照）

---

de JL1LBI — https://www.qrz.com/db/JL1LBI
