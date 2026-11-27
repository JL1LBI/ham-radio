import asyncio
import json
import logging
import os
import queue
import re
import threading
import tkinter as tk
import webbrowser
from tkinter import ttk
from typing import Dict, Optional

import numpy as np
import pystray
import requests
import sounddevice as sd
from livekit import rtc
from PIL import Image, ImageDraw

API_BASE = "https://qso1.net/api/beacon/w"
SAMPLERATE = 48000
CHANNELS = 1
BLOCKSIZE = 480  # 10ms @ 48kHz

HEADERS = {
    "Origin": "https://qso1.net",
    "Referer": "https://qso1.net/beacon",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
}

OFF_LABEL = "-- OFF --"
QRZ_URL = "https://www.qrz.com/db/JL1LBI"

DEFAULT_JP_ROOMS = [
    ("place-c-jp", "Japan 🇯🇵"),
    ("r-7bad2a17", "Japan-X"),
    ("r-d8ec56c3", "JP-Izumo_Room"),
]
DEFAULT_JP_SLUGS = {slug for slug, _ in DEFAULT_JP_ROOMS}

# カラーパレット
BG_MAIN = "#1B1F24"
BG_PANEL = "#242A32"
BG_INPUT = "#2D343E"
BG_MINI_BTN = "#2B313B"
FG_TEXT = "#E6EDF3"
FG_MUTED = "#8B949E"
FG_CREDIT = "#586069"
FG_CREDIT_HOVER = "#8B949E"

LED_OFF = "#3D2B1B"
LED_OFF_GLOW = "#523A24"
LED_ON = "#FF8C00"
LED_ON_GLOW = "#FFD580"

COLOR_RX = "#3FB950"
COLOR_WAIT = "#D29922"
COLOR_ERR = "#F85149"
COLOR_TOPMOST_ON = "#1F6FEB"
COLOR_MUTE_ON = "#B62324"

LANG_LABELS = {
    "日本語": "ja",
    "English": "en",
    "Français": "fr",
}
LANG_CODES_TO_LABELS = {v: k for k, v in LANG_LABELS.items()}

TRANSLATIONS = {
    "ja": {
        "status_disconnected": "未接続（待機中）",
        "status_connecting": "接続しています...",
        "status_connected": "接続中（同時ワッチ中）",
        "muted_suffix": " [ミュート]",
        "btn_connect": "接続",
        "btn_disconnect": "切断",
        "topmost_on": "常に前面: ON",
        "topmost_off": "常に前面: OFF",
        "mute_on": "ミュート: ON",
        "mute_off": "ミュート: OFF",
        "btn_tray": "トレイ格納",
        "tray_show": "ウィンドウを表示",
        "tray_mute": "一括ミュート",
        "tray_topmost": "常に前面に表示",
        "tray_quit": "終了",
    },
    "en": {
        "status_disconnected": "Disconnected (Idle)",
        "status_connecting": "Connecting...",
        "status_connected": "Connected (Watching)",
        "muted_suffix": " [MUTED]",
        "btn_connect": "Connect",
        "btn_disconnect": "Disconnect",
        "topmost_on": "Always on Top: ON",
        "topmost_off": "Always on Top: OFF",
        "mute_on": "Mute All: ON",
        "mute_off": "Mute All: OFF",
        "btn_tray": "To Tray",
        "tray_show": "Show Window",
        "tray_mute": "Mute All",
        "tray_topmost": "Always on Top",
        "tray_quit": "Quit",
    },
    "fr": {
        "status_disconnected": "Déconnecté (En attente)",
        "status_connecting": "Connexion en cours...",
        "status_connected": "Connecté (Écoute)",
        "muted_suffix": " [MUET]",
        "btn_connect": "Connecter",
        "btn_disconnect": "Déconnecter",
        "topmost_on": "Premier plan: ON",
        "topmost_off": "Premier plan: OFF",
        "mute_on": "Muet: ON",
        "mute_off": "Muet: OFF",
        "btn_tray": "Réduire",
        "tray_show": "Afficher la fenêtre",
        "tray_mute": "Tout couper (Muet)",
        "tray_topmost": "Toujours au premier plan",
        "tray_quit": "Quitter",
    },
}


def get_config_path() -> str:
    base = os.getenv("APPDATA") or os.path.join(os.path.expanduser("~"), ".config")
    cfg_dir = os.path.join(base, "qso1-vfo-watch")
    os.makedirs(cfg_dir, exist_ok=True)
    return os.path.join(cfg_dir, "config.json")


def load_config() -> dict:
    default_cfg = {
        "lang": "ja",
        "topmost": False,
        "muted": False,
        "vfo_slugs": ["place-c-jp", "r-7bad2a17", "r-d8ec56c3"],
    }
    try:
        path = get_config_path()
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                if data.get("lang") in TRANSLATIONS:
                    default_cfg["lang"] = data["lang"]
                if isinstance(data.get("topmost"), bool):
                    default_cfg["topmost"] = data["topmost"]
                if isinstance(data.get("muted"), bool):
                    default_cfg["muted"] = data["muted"]
                if (
                    isinstance(data.get("vfo_slugs"), list)
                    and len(data["vfo_slugs"]) == 3
                ):
                    default_cfg["vfo_slugs"] = data["vfo_slugs"]
    except Exception:
        pass
    return default_cfg


def save_config(cfg: dict) -> None:
    try:
        path = get_config_path()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def create_tray_image() -> Image.Image:
    """外部画像ファイル不要でメモリ上にシンプルな無線風アイコンを生成"""
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    # 背景丸
    draw.ellipse((2, 2, 62, 62), fill=(27, 31, 36, 255), outline=(63, 185, 80, 255), width=4)
    # 中央の電波・アンテナマーク
    draw.arc((14, 14, 50, 50), start=215, end=325, fill=(255, 140, 0, 255), width=4)
    draw.arc((21, 21, 43, 43), start=215, end=325, fill=(255, 140, 0, 255), width=4)
    draw.ellipse((28, 30, 36, 38), fill=(230, 237, 243, 255))
    draw.line((32, 36, 32, 50), fill=(230, 237, 243, 255), width=4)
    return img


class AudioBuffer:
    def __init__(self, blocksize: int = BLOCKSIZE):
        self.blocksize = blocksize
        self.buffer = np.array([], dtype=np.int16)

    def add_frame(self, frame_data: np.ndarray) -> None:
        if len(self.buffer) == 0:
            self.buffer = frame_data
        else:
            self.buffer = np.concatenate([self.buffer, frame_data])

    def get_chunk(self) -> np.ndarray:
        if len(self.buffer) >= self.blocksize:
            chunk = self.buffer[: self.blocksize]
            self.buffer = self.buffer[self.blocksize :]
            return chunk
        chunk = np.zeros(self.blocksize, dtype=np.int16)
        if len(self.buffer) > 0:
            n = len(self.buffer)
            chunk[:n] = self.buffer
            self.buffer = np.array([], dtype=np.int16)
        return chunk


class _FrameAdapter:
    def __init__(self, audio_stream: rtc.AudioStream):
        self._stream = audio_stream

    def __aiter__(self):
        return self

    async def __anext__(self) -> rtc.AudioFrame:
        event = await self._stream.__anext__()
        return event.frame

    async def aclose(self) -> None:
        await self._stream.aclose()


def fetch_room_choices(saved_slugs: list[Optional[str]]) -> list[str]:
    room_map: Dict[str, dict] = {
        slug: {"slug": slug, "name": name, "listeners": None, "is_jp": True}
        for slug, name in DEFAULT_JP_ROOMS
    }

    # 前回選択していたルームがアクティブ一覧になくても選択肢に保持する
    for s in saved_slugs:
        if s and s not in room_map:
            room_map[s] = {"slug": s, "name": s, "listeners": None, "is_jp": False}

    try:
        resp = requests.get(f"{API_BASE}/rooms/active?limit=50", headers=HEADERS, timeout=8)
        resp.raise_for_status()
        for r in resp.json().get("rooms", []):
            slug = r["slug"]
            name = r.get("name", slug)
            place = r.get("place") or {}
            is_jp = (
                slug in DEFAULT_JP_SLUGS
                or place.get("country_code") == "JP"
                or "japan" in name.lower()
                or name.upper().startswith("JP")
            )
            room_map[slug] = {
                "slug": slug,
                "name": name,
                "listeners": r.get("listeners", 0),
                "is_jp": is_jp,
            }
    except Exception:
        pass

    sorted_rooms = sorted(
        room_map.values(),
        key=lambda x: (
            0 if x["is_jp"] else 1,
            -(x["listeners"] if x["listeners"] is not None else -1),
            x["name"],
        ),
    )

    choices = [OFF_LABEL]
    for r in sorted_rooms:
        if r["listeners"] is not None:
            choices.append(f"{r['name']} ({r['listeners']}) [{r['slug']}]")
        else:
            choices.append(f"{r['name']} [{r['slug']}]")
    return choices


def extract_slug(choice_text: str) -> Optional[str]:
    if not choice_text or choice_text == OFF_LABEL:
        return None
    m = re.search(r"\[([^\]]+)\]$", choice_text.strip())
    return m.group(1) if m else choice_text.strip()


def fetch_listen_token(room_slug: str) -> dict:
    resp = requests.post(
        f"{API_BASE}/token",
        json={"room": room_slug, "listen_only": True},
        headers=HEADERS,
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


class WatchEngine:
    def __init__(self, ui_queue: queue.Queue, muted: bool = False):
        self.ui_queue = ui_queue
        self.muted = muted
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()

        self.is_connected = False
        self.mixer: Optional[rtc.AudioMixer] = None
        self.audio_queue: Optional[queue.Queue] = None
        self.sd_stream: Optional[sd.OutputStream] = None
        self.pump_task: Optional[asyncio.Task] = None
        self.slot_tasks: Dict[int, asyncio.Task] = {}

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def _emit(self, event_type: str, *args) -> None:
        self.ui_queue.put((event_type, *args))

    def set_muted(self, muted: bool) -> None:
        self.muted = muted

    def refresh_rooms_async(self, saved_slugs: list[Optional[str]]) -> None:
        asyncio.run_coroutine_threadsafe(self._refresh_rooms(saved_slugs), self.loop)

    async def _refresh_rooms(self, saved_slugs: list[Optional[str]]) -> None:
        choices = await asyncio.to_thread(fetch_room_choices, saved_slugs)
        self._emit("rooms_updated", choices)

    def connect(self, slugs: list[Optional[str]]) -> None:
        asyncio.run_coroutine_threadsafe(self._connect_all(slugs), self.loop)

    def disconnect(self) -> None:
        asyncio.run_coroutine_threadsafe(self._disconnect_all(), self.loop)

    def switch_slot(self, slot_idx: int, slug: Optional[str]) -> None:
        asyncio.run_coroutine_threadsafe(self._switch_slot(slot_idx, slug), self.loop)

    def shutdown(self) -> None:
        fut = asyncio.run_coroutine_threadsafe(self._disconnect_all(), self.loop)
        try:
            fut.result(timeout=3)
        except Exception:
            pass
        self.loop.call_soon_threadsafe(self.loop.stop)

    async def _connect_all(self, slugs: list[Optional[str]]) -> None:
        await self._disconnect_all(silent=True)

        self.is_connected = True
        self._emit("global_state", "connecting")

        asyncio.create_task(self._refresh_rooms(slugs))

        self.audio_queue = queue.Queue(maxsize=60)
        buf = AudioBuffer(BLOCKSIZE)
        aq = self.audio_queue
        zero_chunk = np.zeros((BLOCKSIZE, 1), dtype=np.int16)

        def sd_callback(outdata, frames, time_info, status):
            while not aq.empty():
                try:
                    buf.add_frame(aq.get_nowait())
                except queue.Empty:
                    break
            chunk = buf.get_chunk()
            if self.muted:
                outdata[:] = zero_chunk
            else:
                outdata[:] = chunk.reshape(-1, 1)

        self.sd_stream = sd.OutputStream(
            samplerate=SAMPLERATE,
            channels=CHANNELS,
            blocksize=BLOCKSIZE,
            dtype="int16",
            callback=sd_callback,
            latency="low",
        )
        self.sd_stream.start()

        self.mixer = rtc.AudioMixer(
            sample_rate=SAMPLERATE, num_channels=CHANNELS, blocksize=BLOCKSIZE
        )
        self.pump_task = asyncio.create_task(self._pump_audio())

        for idx, slug in enumerate(slugs):
            await self._start_slot(idx, slug)

        self._emit("global_state", "connected")

    async def _disconnect_all(self, silent: bool = False) -> None:
        self.is_connected = False

        for idx in list(self.slot_tasks.keys()):
            await self._stop_slot(idx)

        if self.pump_task is not None:
            self.pump_task.cancel()
            try:
                await self.pump_task
            except asyncio.CancelledError:
                pass
            self.pump_task = None

        if self.mixer is not None:
            await self.mixer.aclose()
            self.mixer = None

        if self.sd_stream is not None:
            try:
                self.sd_stream.stop()
                self.sd_stream.close()
            except Exception:
                pass
            self.sd_stream = None

        self.audio_queue = None

        for idx in range(3):
            self._emit("slot_busy", idx, False)
            self._emit("slot_state", idx, "OFF")

        if not silent:
            self._emit("global_state", "disconnected")

    async def _switch_slot(self, slot_idx: int, slug: Optional[str]) -> None:
        if not self.is_connected:
            return
        await self._stop_slot(slot_idx)
        await self._start_slot(slot_idx, slug)

    async def _start_slot(self, slot_idx: int, slug: Optional[str]) -> None:
        if not slug:
            self._emit("slot_state", slot_idx, "OFF")
            self._emit("slot_busy", slot_idx, False)
            return
        self.slot_tasks[slot_idx] = asyncio.create_task(self._run_slot(slot_idx, slug))

    async def _stop_slot(self, slot_idx: int) -> None:
        task = self.slot_tasks.pop(slot_idx, None)
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._emit("slot_busy", slot_idx, False)
        self._emit("slot_state", slot_idx, "OFF")

    async def _pump_audio(self) -> None:
        assert self.mixer is not None and self.audio_queue is not None
        async for mixed_frame in self.mixer:
            samples = np.frombuffer(mixed_frame.data, dtype=np.int16)
            try:
                self.audio_queue.put_nowait(samples)
            except queue.Full:
                try:
                    self.audio_queue.get_nowait()
                    self.audio_queue.put_nowait(samples)
                except queue.Empty:
                    pass

    async def _run_slot(self, slot_idx: int, slug: str) -> None:
        while self.is_connected:
            self._emit("slot_state", slot_idx, "WAIT")
            self._emit("slot_busy", slot_idx, False)

            room: Optional[rtc.Room] = None
            track_adapters: Dict[str, _FrameAdapter] = {}
            disconnected_event = asyncio.Event()

            try:
                token_info = await asyncio.to_thread(fetch_listen_token, slug)
                ws_url = token_info["url"]
                token = token_info["token"]

                room = rtc.Room()

                def attach_track(track: rtc.Track) -> None:
                    if (
                        track.kind != rtc.TrackKind.KIND_AUDIO
                        or track.sid in track_adapters
                        or self.mixer is None
                    ):
                        return
                    stream = rtc.AudioStream.from_track(
                        track=track, sample_rate=SAMPLERATE, num_channels=CHANNELS
                    )
                    adapter = _FrameAdapter(stream)
                    track_adapters[track.sid] = adapter
                    self.mixer.add_stream(adapter)

                @room.on("track_subscribed")
                def on_track_subscribed(track, publication, participant):
                    attach_track(track)

                @room.on("track_unsubscribed")
                def on_track_unsubscribed(track, publication, participant):
                    adapter = track_adapters.pop(track.sid, None)
                    if adapter is not None:
                        if self.mixer is not None:
                            self.mixer.remove_stream(adapter)
                        asyncio.create_task(adapter.aclose())

                @room.on("active_speakers_changed")
                def on_active_speakers_changed(speakers):
                    self._emit("slot_busy", slot_idx, len(speakers) > 0)

                @room.on("disconnected")
                def on_disconnected(reason=None):
                    disconnected_event.set()

                await room.connect(
                    ws_url, token, options=rtc.RoomOptions(auto_subscribe=True)
                )

                for p in room.remote_participants.values():
                    for pub in p.track_publications.values():
                        if pub.subscribed and pub.track is not None:
                            attach_track(pub.track)

                self._emit("slot_state", slot_idx, "RX")
                await disconnected_event.wait()

            except asyncio.CancelledError:
                raise
            except Exception:
                self._emit("slot_state", slot_idx, "ERR")
            finally:
                self._emit("slot_busy", slot_idx, False)
                for adapter in list(track_adapters.values()):
                    if self.mixer is not None:
                        self.mixer.remove_stream(adapter)
                    try:
                        await adapter.aclose()
                    except Exception:
                        pass
                track_adapters.clear()
                if room is not None:
                    try:
                        await room.disconnect()
                    except Exception:
                        pass

            await asyncio.sleep(5)


class QsoWatchApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("QSO One Watch")
        self.root.configure(bg=BG_MAIN)
        self.root.resizable(False, False)

        self.cfg = load_config()
        self.lang: str = self.cfg["lang"]
        self.topmost: bool = self.cfg["topmost"]
        self.muted: bool = self.cfg["muted"]
        self.saved_slugs: list[Optional[str]] = list(self.cfg["vfo_slugs"])

        self.global_state = "disconnected"
        self.is_connected = False
        self._closing = False

        self.ui_queue: queue.Queue = queue.Queue()
        self.engine = WatchEngine(self.ui_queue, muted=self.muted)
        self.tray_icon: Optional[pystray.Icon] = None

        self._setup_style()
        self._build_ui()
        self._apply_topmost()
        self._apply_language()

        self._start_tray_icon()
        self.engine.refresh_rooms_async(self.saved_slugs)

        self.root.protocol("WM_DELETE_WINDOW", self._quit_app)
        self.root.after(50, self._poll_ui_queue)

    def _t(self, key: str) -> str:
        return TRANSLATIONS.get(self.lang, TRANSLATIONS["ja"]).get(key, key)

    def _save_current_config(self) -> None:
        self.cfg["lang"] = self.lang
        self.cfg["topmost"] = self.topmost
        self.cfg["muted"] = self.muted
        self.cfg["vfo_slugs"] = [extract_slug(v.get()) for v in self.combo_vars]
        save_config(self.cfg)

    def _setup_style(self) -> None:
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure(
            "VFO.TCombobox",
            fieldbackground=BG_INPUT,
            background=BG_PANEL,
            foreground=FG_TEXT,
            arrowcolor=FG_TEXT,
            bordercolor="#363D48",
            lightcolor=BG_INPUT,
            darkcolor=BG_INPUT,
            selectbackground=BG_INPUT,
            selectforeground=FG_TEXT,
            padding=4,
        )
        style.map(
            "VFO.TCombobox",
            fieldbackground=[("readonly", BG_INPUT)],
            foreground=[("readonly", FG_TEXT)],
            selectbackground=[("readonly", BG_INPUT)],
            selectforeground=[("readonly", FG_TEXT)],
        )
        self.root.option_add("*TCombobox*Listbox.background", BG_INPUT)
        self.root.option_add("*TCombobox*Listbox.foreground", FG_TEXT)
        self.root.option_add("*TCombobox*Listbox.selectBackground", "#388BFD")
        self.root.option_add("*TCombobox*Listbox.selectForeground", "#FFFFFF")

    def _build_ui(self) -> None:
        outer = tk.Frame(self.root, bg=BG_MAIN, padx=14, pady=12)
        outer.pack(fill="both", expand=True)

        # 上部：接続状態バー ＋ 言語切り替えプルダウン
        status_bar = tk.Frame(outer, bg=BG_MAIN)
        status_bar.pack(fill="x", pady=(0, 10))

        self.global_dot = tk.Canvas(
            status_bar, width=12, height=12, bg=BG_MAIN, highlightthickness=0
        )
        self.global_dot.pack(side="left", padx=(0, 6))
        self.global_dot_oval = self.global_dot.create_oval(
            2, 2, 10, 10, fill=FG_MUTED, outline=""
        )

        self.global_label = tk.Label(
            status_bar,
            text="",
            bg=BG_MAIN,
            fg=FG_MUTED,
            font=("Yu Gothic UI", 9, "bold"),
        )
        self.global_label.pack(side="left")

        self.lang_var = tk.StringVar(
            value=LANG_CODES_TO_LABELS.get(self.lang, "日本語")
        )
        self.lang_combo = ttk.Combobox(
            status_bar,
            textvariable=self.lang_var,
            values=list(LANG_LABELS.keys()),
            state="readonly",
            width=9,
            style="VFO.TCombobox",
            font=("Yu Gothic UI", 8),
        )
        self.lang_combo.pack(side="right")
        self.lang_combo.bind("<<ComboboxSelected>>", self._on_lang_changed)

        # 中央：3 VFO パネル
        vfo_panel = tk.Frame(
            outer,
            bg=BG_PANEL,
            padx=10,
            pady=8,
            highlightbackground="#30363D",
            highlightthickness=1,
        )
        vfo_panel.pack(fill="x")

        initial_choices = fetch_room_choices_local_only(self.saved_slugs)

        self.combos: list[ttk.Combobox] = []
        self.combo_vars: list[tk.StringVar] = []
        self.leds: list[tuple[tk.Canvas, int, int]] = []
        self.slot_labels: list[tk.Label] = []

        for i in range(3):
            row = tk.Frame(vfo_panel, bg=BG_PANEL)
            row.pack(fill="x", pady=4)

            tk.Label(
                row,
                text=f"VFO {i + 1}",
                width=5,
                anchor="w",
                bg=BG_PANEL,
                fg=FG_MUTED,
                font=("Consolas", 9, "bold"),
            ).pack(side="left", padx=(0, 6))

            slug = self.saved_slugs[i] if i < len(self.saved_slugs) else None
            init_val = OFF_LABEL
            if slug:
                matched = next(
                    (c for c in initial_choices if extract_slug(c) == slug), None
                )
                init_val = matched or f"{slug} [{slug}]"

            var = tk.StringVar(value=init_val)
            combo = ttk.Combobox(
                row,
                textvariable=var,
                values=initial_choices,
                state="readonly",
                width=28,
                style="VFO.TCombobox",
                font=("Yu Gothic UI", 9),
            )
            combo.pack(side="left", padx=(0, 8))
            combo.bind(
                "<<ComboboxSelected>>", lambda e, idx=i: self._on_combo_changed(idx)
            )

            led_canvas = tk.Canvas(
                row, width=18, height=18, bg=BG_PANEL, highlightthickness=0
            )
            led_canvas.pack(side="left", padx=(0, 6))
            led_body = led_canvas.create_oval(
                2, 2, 16, 16, fill=LED_OFF, outline="#121519", width=1
            )
            led_glow = led_canvas.create_oval(
                5, 4, 9, 8, fill=LED_OFF_GLOW, outline=""
            )

            st_lbl = tk.Label(
                row,
                text="OFF",
                width=4,
                anchor="center",
                bg=BG_PANEL,
                fg=FG_MUTED,
                font=("Consolas", 8, "bold"),
            )
            st_lbl.pack(side="left")

            self.combo_vars.append(var)
            self.combos.append(combo)
            self.leds.append((led_canvas, led_body, led_glow))
            self.slot_labels.append(st_lbl)

        # オプション行：常に前面 / ミュート / トレイ格納
        opt_row = tk.Frame(outer, bg=BG_MAIN)
        opt_row.pack(fill="x", pady=(10, 0))

        self.btn_topmost = tk.Button(
            opt_row,
            text="",
            command=self._toggle_topmost,
            relief="flat",
            bd=0,
            pady=4,
            cursor="hand2",
            font=("Yu Gothic UI", 8, "bold"),
        )
        self.btn_topmost.pack(side="left", expand=True, fill="x", padx=(0, 4))

        self.btn_mute = tk.Button(
            opt_row,
            text="",
            command=self._toggle_mute,
            relief="flat",
            bd=0,
            pady=4,
            cursor="hand2",
            font=("Yu Gothic UI", 8, "bold"),
        )
        self.btn_mute.pack(side="left", expand=True, fill="x", padx=4)

        self.btn_tray = tk.Button(
            opt_row,
            text="",
            command=self._hide_to_tray,
            bg=BG_MINI_BTN,
            fg=FG_TEXT,
            activebackground="#3A424E",
            activeforeground=FG_TEXT,
            relief="flat",
            bd=0,
            pady=4,
            cursor="hand2",
            font=("Yu Gothic UI", 8),
        )
        self.btn_tray.pack(side="left", expand=True, fill="x", padx=(4, 0))

        # 下部：接続 / 切断ボタン
        btn_row = tk.Frame(outer, bg=BG_MAIN)
        btn_row.pack(fill="x", pady=(8, 4))

        self.btn_connect = tk.Button(
            btn_row,
            text="",
            width=14,
            command=self._on_connect,
            bg="#238636",
            fg="#FFFFFF",
            activebackground="#2EA043",
            activeforeground="#FFFFFF",
            disabledforeground="#6E7681",
            relief="flat",
            bd=0,
            pady=6,
            cursor="hand2",
            font=("Yu Gothic UI", 9, "bold"),
        )
        self.btn_connect.pack(side="left", expand=True, fill="x", padx=(0, 6))

        self.btn_disconnect = tk.Button(
            btn_row,
            text="",
            width=14,
            command=self._on_disconnect,
            state="disabled",
            bg="#2D333B",
            fg="#FFFFFF",
            activebackground="#DA3633",
            activeforeground="#FFFFFF",
            disabledforeground="#586069",
            relief="flat",
            bd=0,
            pady=6,
            cursor="arrow",
            font=("Yu Gothic UI", 9, "bold"),
        )
        self.btn_disconnect.pack(side="left", expand=True, fill="x", padx=(6, 0))

        # 最下部右下：控えめな JL1LBi リンク表記
        footer = tk.Frame(outer, bg=BG_MAIN)
        footer.pack(fill="x", pady=(4, 0))

        credit_lbl = tk.Label(
            footer,
            text="JL1LBi",
            bg=BG_MAIN,
            fg=FG_CREDIT,
            font=("Segoe UI", 8),
            cursor="hand2",
            anchor="e",
        )
        credit_lbl.pack(side="right")
        credit_lbl.bind("<Button-1>", lambda e: webbrowser.open(QRZ_URL))
        credit_lbl.bind("<Enter>", lambda e: credit_lbl.config(fg=FG_CREDIT_HOVER))
        credit_lbl.bind("<Leave>", lambda e: credit_lbl.config(fg=FG_CREDIT))

    def _start_tray_icon(self) -> None:
        menu = pystray.Menu(
            pystray.MenuItem(
                lambda item: self._t("tray_show"),
                lambda icon, item: self.ui_queue.put(("show_window",)),
                default=True,
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                lambda item: self._t("tray_mute"),
                lambda icon, item: self.ui_queue.put(("toggle_mute",)),
                checked=lambda item: self.muted,
            ),
            pystray.MenuItem(
                lambda item: self._t("tray_topmost"),
                lambda icon, item: self.ui_queue.put(("toggle_topmost",)),
                checked=lambda item: self.topmost,
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                lambda item: self._t("tray_quit"),
                lambda icon, item: self.ui_queue.put(("quit_app",)),
            ),
        )
        self.tray_icon = pystray.Icon(
            "qso1_vfo_watch", create_tray_image(), "QSO One Watch", menu
        )
        threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def _hide_to_tray(self) -> None:
        self.root.withdraw()

    def _show_from_tray(self) -> None:
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()
        self._apply_topmost()

    def _on_lang_changed(self, event=None) -> None:
        selected = self.lang_var.get()
        self.lang = LANG_LABELS.get(selected, "ja")
        self._apply_language()
        self._save_current_config()

    def _apply_language(self) -> None:
        self.btn_connect.config(text=self._t("btn_connect"))
        self.btn_disconnect.config(text=self._t("btn_disconnect"))
        self.btn_tray.config(text=self._t("btn_tray"))
        self._update_option_buttons()
        self._set_global_state(self.global_state)
        if self.tray_icon is not None:
            try:
                self.tray_icon.update_menu()
            except Exception:
                pass

    def _toggle_topmost(self) -> None:
        self.topmost = not self.topmost
        self._apply_topmost()
        self._update_option_buttons()
        self._save_current_config()
        if self.tray_icon is not None:
            try:
                self.tray_icon.update_menu()
            except Exception:
                pass

    def _apply_topmost(self) -> None:
        self.root.attributes("-topmost", self.topmost)

    def _toggle_mute(self) -> None:
        self.muted = not self.muted
        self.engine.set_muted(self.muted)
        self._update_option_buttons()
        self._set_global_state(self.global_state)
        self._save_current_config()
        if self.tray_icon is not None:
            try:
                self.tray_icon.update_menu()
            except Exception:
                pass

    def _update_option_buttons(self) -> None:
        if self.topmost:
            self.btn_topmost.config(
                text=self._t("topmost_on"),
                bg=COLOR_TOPMOST_ON,
                fg="#FFFFFF",
                activebackground="#388BFD",
            )
        else:
            self.btn_topmost.config(
                text=self._t("topmost_off"),
                bg=BG_MINI_BTN,
                fg=FG_MUTED,
                activebackground="#3A424E",
            )

        if self.muted:
            self.btn_mute.config(
                text=self._t("mute_on"),
                bg=COLOR_MUTE_ON,
                fg="#FFFFFF",
                activebackground="#DA3633",
            )
        else:
            self.btn_mute.config(
                text=self._t("mute_off"),
                bg=BG_MINI_BTN,
                fg=FG_MUTED,
                activebackground="#3A424E",
            )

    def _on_combo_changed(self, idx: int) -> None:
        self._save_current_config()
        if self.is_connected:
            slug = extract_slug(self.combo_vars[idx].get())
            self.engine.switch_slot(idx, slug)

    def _on_connect(self) -> None:
        slugs = [extract_slug(v.get()) for v in self.combo_vars]
        if all(s is None for s in slugs):
            return
        self._save_current_config()
        self.is_connected = True
        self._update_buttons(connected=True)
        self.engine.connect(slugs)

    def _on_disconnect(self) -> None:
        self.is_connected = False
        self._update_buttons(connected=False)
        self.engine.disconnect()

    def _update_buttons(self, connected: bool) -> None:
        if connected:
            self.btn_connect.config(state="disabled", bg="#2D333B", cursor="arrow")
            self.btn_disconnect.config(state="normal", bg="#B62324", cursor="hand2")
        else:
            self.btn_connect.config(state="normal", bg="#238636", cursor="hand2")
            self.btn_disconnect.config(state="disabled", bg="#2D333B", cursor="arrow")

    def _set_led(self, idx: int, is_on: bool) -> None:
        canvas, body, glow = self.leds[idx]
        if is_on:
            canvas.itemconfig(body, fill=LED_ON)
            canvas.itemconfig(glow, fill=LED_ON_GLOW)
        else:
            canvas.itemconfig(body, fill=LED_OFF)
            canvas.itemconfig(glow, fill=LED_OFF_GLOW)

    def _set_slot_state(self, idx: int, state: str) -> None:
        lbl = self.slot_labels[idx]
        if state == "RX":
            lbl.config(text="RX", fg=COLOR_RX)
        elif state == "WAIT":
            lbl.config(text="...", fg=COLOR_WAIT)
        elif state == "ERR":
            lbl.config(text="ERR", fg=COLOR_ERR)
        else:
            lbl.config(text="OFF", fg=FG_MUTED)

    def _set_global_state(self, state: str) -> None:
        self.global_state = state
        mute_txt = self._t("muted_suffix") if self.muted else ""
        if state == "connected":
            self.global_dot.itemconfig(self.global_dot_oval, fill=COLOR_RX)
            self.global_label.config(
                text=self._t("status_connected") + mute_txt, fg=COLOR_RX
            )
        elif state == "connecting":
            self.global_dot.itemconfig(self.global_dot_oval, fill=COLOR_WAIT)
            self.global_label.config(
                text=self._t("status_connecting") + mute_txt, fg=COLOR_WAIT
            )
        else:
            self.global_dot.itemconfig(self.global_dot_oval, fill=FG_MUTED)
            self.global_label.config(
                text=self._t("status_disconnected") + mute_txt, fg=FG_MUTED
            )

    def _update_room_choices(self, choices: list[str]) -> None:
        for i, combo in enumerate(self.combos):
            current_slug = extract_slug(self.combo_vars[i].get())
            combo["values"] = choices
            if current_slug is None:
                self.combo_vars[i].set(OFF_LABEL)
            else:
                matched = next(
                    (c for c in choices if extract_slug(c) == current_slug), None
                )
                if matched:
                    self.combo_vars[i].set(matched)

    def _poll_ui_queue(self) -> None:
        if self._closing:
            return
        while not self.ui_queue.empty():
            try:
                ev = self.ui_queue.get_nowait()
            except queue.Empty:
                break
            kind = ev[0]
            if kind == "slot_busy":
                self._set_led(ev[1], ev[2])
            elif kind == "slot_state":
                self._set_slot_state(ev[1], ev[2])
            elif kind == "global_state":
                self._set_global_state(ev[1])
            elif kind == "rooms_updated":
                self._update_room_choices(ev[1])
            elif kind == "show_window":
                self._show_from_tray()
            elif kind == "toggle_mute":
                self._toggle_mute()
            elif kind == "toggle_topmost":
                self._toggle_topmost()
            elif kind == "quit_app":
                self._quit_app()
                return
        self.root.after(50, self._poll_ui_queue)

    def _quit_app(self) -> None:
        if self._closing:
            return
        self._closing = True
        self._save_current_config()
        if self.tray_icon is not None:
            try:
                self.tray_icon.stop()
            except Exception:
                pass
        self.engine.shutdown()
        self.root.destroy()


def fetch_room_choices_local_only(saved_slugs: list[Optional[str]]) -> list[str]:
    room_map: Dict[str, str] = {slug: name for slug, name in DEFAULT_JP_ROOMS}
    for s in saved_slugs:
        if s and s not in room_map:
            room_map[s] = s
    return [OFF_LABEL] + [f"{name} [{slug}]" for slug, name in room_map.items()]


def main() -> None:
    logging.getLogger("livekit").setLevel(logging.ERROR)
    root = tk.Tk()
    QsoWatchApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()