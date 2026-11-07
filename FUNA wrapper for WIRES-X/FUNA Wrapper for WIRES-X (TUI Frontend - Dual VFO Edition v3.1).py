"""
====================================================================
 FUNA Wrapper for WIRES-X (TUI Frontend - Dual VFO Edition v3.1)
 File: funa_tui.py
====================================================================
"""

import sys
import time
from typing import Optional
from textual.app import App, ComposeResult
from textual.screen import ModalScreen
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Static, Input, DataTable, Label
from textual.binding import Binding
from textual import on, work

from wiresx_core import WiresXDriver

TUI_CSS = """
Screen {
    background: #000080;  /* DOS Navy Blue */
    color: #ffffff;
}

#vfo-top-bar {
    dock: top;
    height: 3;
    background: #0000aa;
    border-bottom: heavy #ffffff;
    padding: 0 1;
}

#app-title {
    text-style: bold;
    color: #ffff55;
    width: 25%;
}

#vfo-indicator {
    text-style: bold;
    color: #55ffff;
    width: 35%;
}

#live-state-banner {
    text-align: right;
    text-style: bold;
    width: 40%;
}

#vfo-container {
    height: 1fr;
}

.vfo-box {
    width: 50%;
    padding: 0 1;
    border: double #555555;
}

.vfo-active {
    border: double #00ffff !important;
    background: #000095;
}

.vfo-header {
    text-style: bold;
    padding: 0 1;
}

#vfo-a-header {
    background: #aaaa00;
    color: #000000;
}

#vfo-b-header {
    background: #00aaaa;
    color: #000000;
}

DataTable {
    background: #000080;
    color: #ffffff;
    height: 1fr;
}

DataTable > .datatable--cursor {
    background: #ffff55;
    color: #000000;
    text-style: bold;
}

#monitor-pane {
    dock: bottom;
    height: 10;
    background: #000022;
    border-top: double #00ffff;
    padding: 0 1;
}

#monitor-header {
    background: #555555;
    color: #ffff55;
    text-style: bold;
    padding: 0 1;
}

#monitor-line1 {
    color: #ffffff;
    text-style: bold;
    padding: 0 1;
}

#monitor-line2 {
    padding: 0 1;
}

#monitor-log-box {
    color: #88ff88;
    background: #000000;
    border: solid #333333;
    padding: 0 1;
    height: 4;
    margin-top: 1;
}

ConnectModal {
    align: center middle;
    background: rgba(0, 0, 0, 0.7);
}

#dialog-box {
    width: 52;
    height: 13;
    background: #0000aa;
    border: thick #ffffff;
    padding: 1 2;
}

#dialog-title {
    text-style: bold;
    color: #ffff55;
    text-align: center;
    margin-bottom: 1;
}

#dialog-input {
    background: #ffffff;
    color: #000000;
    text-style: bold;
    border: tall #00aaaa;
    margin-bottom: 1;
}

#dialog-help {
    color: #aaaaaa;
    text-align: center;
}
"""

class ConnectModal(ModalScreen[Optional[str]]):
    def compose(self) -> ComposeResult:
        with Vertical(id="dialog-box"):
            yield Label("╔══════════════════════════════════════════╗", id="dialog-deco1")
            yield Label("║          CONNECT TO ID (DIRECT)          ║", id="dialog-title")
            yield Label("╚══════════════════════════════════════════╝", id="dialog-deco2")
            yield Input(placeholder="Enter Room or Node ID (e.g. 20510)", id="dialog-input")
            yield Label("[Enter]: Connect   |   [Esc]: Cancel", id="dialog-help")

    def on_mount(self):
        self.query_one("#dialog-input", Input).focus()

    @on(Input.Submitted, "#dialog-input")
    def on_submit(self, event: Input.Submitted):
        val = event.value.strip()
        self.dismiss(val if val else None)

    def key_escape(self):
        self.dismiss(None)


class FunaWiresXApp(App):
    TITLE = "FUNA Wrapper for WIRES-X"
    CSS = TUI_CSS

    BINDINGS = [
        Binding("tab", "toggle_vfo", "Switch VFO (A/B)", show=True),
        Binding("c", "open_connect_dialog", "Connect ID", show=True),
        Binding("d", "quick_disconnect", "Disconnect", show=True),
        Binding("r", "refresh_data", "Refresh (Sync)", show=True),
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("q", "appliance_quit", "Quit (Shutdown)", show=True),
    ]

    def __init__(self, driver: Optional[WiresXDriver] = None):
        super().__init__()
        self.driver = driver if driver else WiresXDriver()
        self.active_vfo = "A"
        self.is_fetching = False
        self._last_state = "DISCONNECTED"

    def compose(self) -> ComposeResult:
        with Horizontal(id="vfo-top-bar"):
            yield Static("▌FUNA Wrapper for WIRES-X▐", id="app-title")
            yield Static("CURRENT: [VFO A (ROOM) *ACTIVE*]", id="vfo-indicator")
            yield Static("[ DISCONNECTED ]", id="live-state-banner")

        with Horizontal(id="vfo-container"):
            with Vertical(id="vfo-a-pane", classes="vfo-box vfo-active"):
                yield Label("【 VFO A : ROOM ID 】 (Act降順 / Enter: 接続)", id="vfo-a-header", classes="vfo-header")
                yield DataTable(id="table-vfo-a")

            with Vertical(id="vfo-b-pane", classes="vfo-box"):
                yield Label("【 VFO B : USER / NODE ID 】 (Enter: 接続)", id="vfo-b-header", classes="vfo-header")
                yield DataTable(id="table-vfo-b")

        with Vertical(id="monitor-pane"):
            yield Label("【 LIVE TRAFFIC & SYSTEM LOG MONITOR 】", id="monitor-header")
            yield Static("STATUS: Standby (Not Connected)", id="monitor-line1")
            yield Static("QSO: No Traffic", id="monitor-line2")
            yield Static("WIRES-X LOG: (Ready)", id="monitor-log-box")

        yield Footer()

    def on_mount(self):
        """UIメインスレッドで直接初期化とタイマー登録を実行"""
        table_a = self.query_one("#table-vfo-a", DataTable)
        table_a.cursor_type = "row"
        table_a.add_columns("Act", "Room ID", "Room Name", "Description")

        table_b = self.query_one("#table-vfo-b", DataTable)
        table_b.cursor_type = "row"
        table_b.add_columns("Node ID", "Callsign", "Node Name")

        if not self.driver.attach():
            self.notify("WIRES-X が検出されません。", severity="error")
            self.query_one("#live-state-banner", Static).update("[bold red]WIRES-X NOT FOUND[/bold red]")
            return

        self.notify(f"WIRES-X (PID: {self.driver.pid}) にアタッチ成功。")
        table_a.focus()

        # 初回リスト取得
        self.trigger_async_sync()

        # メインスレッドで確実にタイマーを登録
        self.set_interval(0.4, self.update_live_monitor_loop)
        self.set_interval(25.0, self.trigger_async_sync)

    def update_live_monitor_loop(self):
        if not self.driver.main_hwnd:
            return

        try:
            live = self.driver.get_live_traffic_info()

            banner = self.query_one("#live-state-banner", Static)
            line1 = self.query_one("#monitor-line1", Static)
            line2 = self.query_one("#monitor-line2", Static)
            log_box = self.query_one("#monitor-log-box", Static)

            state = live["state"]

            # トースト通知
            if state != self._last_state:
                self._last_state = state
                if state == "BUSY":
                    self.notify(f"接続エラー: {live['error_msg']}", severity="error", timeout=6.0)
                elif state == "CONNECTED":
                    self.notify(f"接続確立: {live['room_name']}", severity="information")

            # 1. 接続状態
            if state == "CONNECTED":
                r_name = live["room_name"] if live["room_name"] else "Connected Room"
                r_id = live["room_id"] if live["room_id"] else "-"
                m_cnt = f" | Members: [bold cyan]{live['members']} Nodes[/bold cyan]" if live["members"] else ""

                banner.update(f"[bold on green] ● CONNECTED : {r_name}({r_id}) [/bold on green]")
                line1.update(f"[bold green]● ON AIR (CONNECTED)[/bold green] -> Room: [bold yellow]{r_name}[/bold yellow] (ID: {r_id}){m_cnt}")

                # 2. パケット同期型 Active QSO vs Last Heard
                if live.get("is_active_now"):
                    mode_str = f" [cyan]({live['active_mode']})[/cyan]" if live['active_mode'] else ""
                    up_str = f" via [grey85]{live['uplink']}[/grey85]" if live['uplink'] else ""
                    line2.update(f"▶ [bold yellow]ACTIVE QSO:[/bold yellow] [bold on dark_green] {live['active_user']} [/bold on dark_green]{mode_str}{up_str}")
                elif live.get("last_heard_user"):
                    line2.update(f"▶ [grey70]STANDBY (Listening...)[/grey70]  [grey50]|  Last Heard: [cyan]{live['last_heard_user']}[/cyan] ({live['last_heard_mode']})[/grey50]")
                else:
                    line2.update("[grey60]▶ STANDBY (Listening... No Traffic)[/grey60]")

            elif state == "BUSY":
                target = f"{live['room_name']}({live['room_id']})" if live['room_id'] else "Target"
                banner.update(f"[bold on dark_red] ✖ CONNECTION BUSY : {target} [/bold on dark_red]")
                line1.update(f"[bold red]✖ CONNECTION BUSY[/bold red] -> [bold yellow]{live['error_msg']}[/bold yellow]")
                line2.update("[yellow]相手局/ルームが通信中、またはデジタル専用ルームのため拒否されました。[/yellow]")

            elif state == "CALLING":
                banner.update("[bold on yellow] ⏳ CONNECTING... [/bold on yellow]")
                line1.update("[yellow]⏳ Calling target server...[/yellow]")
                line2.update("[grey60]Waiting for server response...[/grey60]")

            else:
                banner.update("[white][ DISCONNECTED / STANDBY ][/white]")
                line1.update("[grey70]STATUS: Standby (Not Connected)[/grey70]")
                line2.update("[grey50]QSO: No Active Traffic[/grey50]")

            # 3. リアルタイムログボックス (最新3行ストリーミング)
            if live["recent_logs"]:
                formatted_logs = "\n".join([f"[grey60]>[/grey60] {line}" for line in live["recent_logs"][-3:]])
                log_box.update(formatted_logs)
            else:
                log_box.update("[grey40](No Log Events)[/grey40]")

        except Exception:
            pass

    @work(exclusive=True, thread=True)
    def trigger_async_sync(self):
        if self.is_fetching or not self.driver.main_hwnd:
            return
        self.is_fetching = True
        try:
            rooms = self.driver.get_rooms(max_items=700)
            nodes = self.driver.get_nodes(max_items=500)
            self.app.call_from_thread(self._apply_table_data, rooms, nodes)
        finally:
            self.is_fetching = False

    def _apply_table_data(self, rooms: list, nodes: list):
        table_a = self.query_one("#table-vfo-a", DataTable)
        curr_a = table_a.cursor_coordinate
        table_a.clear()
        for r in rooms:
            table_a.add_row(r["act_str"], r["id"], r["name"], r["desc"])
        if rooms and curr_a.row < len(rooms):
            table_a.move_cursor(row=curr_a.row)

        table_b = self.query_one("#table-vfo-b", DataTable)
        curr_b = table_b.cursor_coordinate
        table_b.clear()
        for n in nodes:
            table_b.add_row(n["id"], n["callsign"], n["name"])
        if nodes and curr_b.row < len(nodes):
            table_b.move_cursor(row=curr_b.row)

    def action_toggle_vfo(self):
        pane_a = self.query_one("#vfo-a-pane")
        pane_b = self.query_one("#vfo-b-pane")
        indicator = self.query_one("#vfo-indicator", Static)

        if self.active_vfo == "A":
            self.active_vfo = "B"
            pane_a.remove_class("vfo-active")
            pane_b.add_class("vfo-active")
            indicator.update("CURRENT: [bold cyan][VFO B (USER) *ACTIVE*][/bold cyan]")
            self.query_one("#table-vfo-b", DataTable).focus()
            self.notify("VFO B (USER / NODE) を選択")
        else:
            self.active_vfo = "A"
            pane_b.remove_class("vfo-active")
            pane_a.add_class("vfo-active")
            indicator.update("CURRENT: [bold yellow][VFO A (ROOM) *ACTIVE*][/bold yellow]")
            self.query_one("#table-vfo-a", DataTable).focus()
            self.notify("VFO A (ROOM) を選択")

    @on(DataTable.RowSelected)
    def on_row_selected(self, event: DataTable.RowSelected):
        try:
            row_idx = event.cursor_row
            row_data = event.data_table.get_row_at(row_idx)

            if event.data_table.id == "table-vfo-a":
                target_id = str(row_data[1]).strip()
                name = str(row_data[2]).strip()
                self.start_async_connect(target_id, f"Room: {name}")
            else:
                target_id = str(row_data[0]).strip()
                callsign = str(row_data[1]).strip()
                self.start_async_connect(target_id, f"Node: {callsign}")
        except Exception as e:
            self.notify(f"選択エラー: {e}", severity="error")

    @work(exclusive=True, thread=True)
    def start_async_connect(self, target_id: str, label: str = ""):
        try:
            def progress(msg):
                self.app.call_from_thread(self.notify, msg, timeout=3.0)

            self.app.call_from_thread(self.notify, f"接続シーケンス開始: {label} ({target_id})")

            success = self.driver.smart_connect(target_id, progress_cb=progress)
            if success:
                self.app.call_from_thread(self.notify, f"接続要求完了: {target_id}", severity="information")
            else:
                self.app.call_from_thread(self.notify, f"接続ダイアログ操作失敗: {target_id}", severity="error")
        except Exception as e:
            self.app.call_from_thread(self.notify, f"接続処理中エラー: {e}", severity="error")

    def action_open_connect_dialog(self):
        def handle_connect(target_id: Optional[str]):
            if target_id:
                self.start_async_connect(target_id, "Direct ID")

        self.push_screen(ConnectModal(), handle_connect)

    def action_quick_disconnect(self):
        self.driver.disconnect()
        self.notify("切断コマンドを送信しました。", severity="warning")

    def action_refresh_data(self):
        self.driver.refresh_list()
        self.notify("リスト再同期中...")
        self.trigger_async_sync()

    def action_appliance_quit(self):
        """[q] アプライアンス連動終了"""
        try:
            self.driver.close_wiresx()
        except Exception:
            pass
        self.exit()

    def action_cursor_down(self):
        current_table = self.query_one("#table-vfo-a" if self.active_vfo == "A" else "#table-vfo-b", DataTable)
        current_table.action_cursor_down()

    def action_cursor_up(self):
        current_table = self.query_one("#table-vfo-a" if self.active_vfo == "A" else "#table-vfo-b", DataTable)
        current_table.action_cursor_up()


def main():
    driver = WiresXDriver()

    if not driver.attach():
        print("=" * 60)
        print(" FUNA Wrapper for WIRES-X : Bootloader")
        print("=" * 60)
        print("[*] WIRES-X 本体が未起動です。")
        success = driver.ensure_running_and_attach()
        if not success:
            print("[-] WIRES-X の自動起動に失敗しました。本体を手動起動してから再実行してください。")
            sys.exit(1)
        print("[+] 準備完了。TUIコンソールを展開します...")
        time.sleep(1.0)

    app = FunaWiresXApp(driver=driver)
    app.run()


if __name__ == "__main__":
    main()