"""
Flower — Robot Bridge Monitor & Tester (GUI).

A tkinter desktop app that lets you:

  1) See exactly what state the whole bridge is in RIGHT NOW
     - live snapshot of GVL_Robot.stRobot via pyads (polled 5x/sec)
     - live console tail of the bridge subprocess
  2) Start / stop the bridge (robot_bridge.py) without a terminal
  3) Play the robot — connect a TCP client to the bridge and send POS frames,
     with a byte-level view of what actually went on the wire

The GUI has an explanation panel next to every section — this is intended
for someone new to TCP/IP.

Runs standalone: `python bridge_gui.py [--config config.yaml]`
No extra dependencies beyond what the bridge already needs (pyads, pyyaml).
"""
from __future__ import annotations

import argparse
import queue
import socket
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from tkinter import (
    Tk, Frame, LabelFrame, Label, Button, Entry, Text, Canvas,
    StringVar, IntVar, BooleanVar, END, N, S, E, W, NSEW, DISABLED, NORMAL,
    WORD, INSERT, messagebox,
)
from tkinter import ttk

try:
    import pyads
except ImportError:
    pyads = None

try:
    import yaml
except ImportError:
    yaml = None


# =========================================================================
# Theme — dark, matches the docs
# =========================================================================

class T:
    BG      = "#1e1e1e"
    BG2     = "#252526"
    BG3     = "#2d2d30"
    BORDER  = "#3e3e42"
    TEXT    = "#e0e0e0"
    MUTED   = "#a0a0a0"
    ACCENT  = "#4fc3f7"   # cyan
    ACCENT2 = "#81c784"   # green
    WARN    = "#ffb74d"   # yellow
    DANGER  = "#e57373"   # red
    GREY    = "#5a5a5a"

    UI        = ("Segoe UI", 10)
    UI_BOLD   = ("Segoe UI", 10, "bold")
    UI_SMALL  = ("Segoe UI", 9)
    UI_HEADER = ("Segoe UI", 11, "bold")
    UI_TITLE  = ("Segoe UI", 14, "bold")
    MONO      = ("Consolas", 10)
    MONO_S    = ("Consolas", 9)

STATE_COLORS = {
    0: (T.GREY,    "Disconnected"),
    1: (T.WARN,    "Connecting"),
    2: (T.ACCENT2, "Connected"),
    3: (T.DANGER,  "Error"),
}


# =========================================================================
# Bridge process manager — subprocess.Popen wrapper with non-blocking stdout
# =========================================================================

class BridgeProcess:
    """Manages robot_bridge.py as a child process. Non-blocking log tail."""

    def __init__(self):
        self._proc: subprocess.Popen | None = None
        self._reader: threading.Thread | None = None
        self._q: queue.Queue[str] = queue.Queue()
        self._stopped_flag = threading.Event()

    @property
    def is_running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    @property
    def pid(self) -> int | None:
        return self._proc.pid if self.is_running else None

    def start(self, config_path: Path) -> None:
        if self.is_running:
            return
        script = Path(__file__).with_name("robot_bridge.py")
        # -u forces unbuffered stdout so we see log lines immediately.
        cmd = [sys.executable, "-u", str(script), "--config", str(config_path)]
        self._proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,          # line-buffered
            cwd=str(script.parent),
        )
        self._stopped_flag.clear()
        self._reader = threading.Thread(target=self._reader_loop, daemon=True)
        self._reader.start()

    def stop(self, timeout: float = 3.0) -> None:
        if not self.is_running:
            return
        try:
            self._proc.terminate()
            self._proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            self._proc.kill()
            self._proc.wait(timeout=1.0)
        except Exception:
            pass
        self._stopped_flag.set()

    def poll_lines(self) -> list[str]:
        """Drain the queue non-blockingly. Called from the tk main loop."""
        out = []
        while True:
            try:
                out.append(self._q.get_nowait())
            except queue.Empty:
                break
        return out

    def _reader_loop(self) -> None:
        assert self._proc is not None and self._proc.stdout is not None
        try:
            for line in self._proc.stdout:
                self._q.put(line.rstrip("\n"))
        except Exception:
            pass
        self._q.put(f"[process exited with code {self._proc.returncode}]")


# =========================================================================
# PLC monitor — polls GVL_Robot.stRobot via pyads. Threaded, tk-safe queue.
# =========================================================================

@dataclass
class PlcSnapshot:
    ok: bool = False
    error: str = ""
    Name: str = ""
    eConnState: int = 0
    sConnStateText: str = ""
    bAtPos1: bool = False
    bAtPos2: bool = False
    bAtPos3: bool = False
    nPacketsRx: int = 0
    sLastMessage: str = ""
    when: float = field(default_factory=time.time)


class PlcMonitor:
    """Polls GVL_Robot.stRobot every `interval_ms` in a background thread."""

    FIELDS = [
        ("Name",           "PLCTYPE_STRING"),
        ("eConnState",     "PLCTYPE_UINT"),
        ("sConnStateText", "PLCTYPE_STRING"),
        ("bAtPos1",        "PLCTYPE_BOOL"),
        ("bAtPos2",        "PLCTYPE_BOOL"),
        ("bAtPos3",        "PLCTYPE_BOOL"),
        ("nPacketsRx",     "PLCTYPE_UDINT"),
        ("sLastMessage",   "PLCTYPE_STRING"),
    ]

    def __init__(self, ams_net_id: str, ams_port: int, symbol_prefix: str, interval_ms: int = 200):
        self._ams = ams_net_id
        self._port = ams_port
        self._prefix = symbol_prefix
        self._interval = interval_ms / 1000.0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last: PlcSnapshot = PlcSnapshot()
        self._lock = threading.Lock()

    def start(self) -> None:
        if pyads is None:
            self._last = PlcSnapshot(ok=False, error="pyads not installed")
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def snapshot(self) -> PlcSnapshot:
        with self._lock:
            return self._last

    def _loop(self) -> None:
        plc = None
        while not self._stop.is_set():
            try:
                if plc is None:
                    plc = pyads.Connection(self._ams, self._port)
                    plc.open()
                snap = PlcSnapshot(ok=True)
                for name, tp in self.FIELDS:
                    v = plc.read_by_name(f"{self._prefix}.{name}", getattr(pyads, tp))
                    setattr(snap, name, v)
                with self._lock:
                    self._last = snap
            except Exception as e:
                with self._lock:
                    self._last = PlcSnapshot(ok=False, error=str(e))
                try:
                    if plc is not None:
                        plc.close()
                except Exception:
                    pass
                plc = None
                time.sleep(1.0)   # slow down on error
            self._stop.wait(self._interval)
        try:
            if plc is not None:
                plc.close()
        except Exception:
            pass


# =========================================================================
# Robot simulator — TCP client. Sends ASCII frames terminated with '\n'.
# =========================================================================

class RobotSimulator:
    """Plays the robot: opens a TCP client to the bridge and sends frames."""

    def __init__(self):
        self._sock: socket.socket | None = None
        self._addr: tuple[str, int] = ("", 0)
        self.last_sent_bytes: bytes = b""

    @property
    def is_connected(self) -> bool:
        return self._sock is not None

    @property
    def remote(self) -> str:
        return f"{self._addr[0]}:{self._addr[1]}" if self.is_connected else "—"

    def connect(self, host: str, port: int) -> None:
        s = socket.create_connection((host, port), timeout=5.0)
        s.settimeout(None)
        self._sock = s
        self._addr = (host, port)

    def disconnect(self) -> None:
        if self._sock is not None:
            try:
                self._sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                self._sock.close()
            except OSError:
                pass
        self._sock = None
        self._addr = ("", 0)

    def send(self, frame: str) -> bytes:
        if self._sock is None:
            raise RuntimeError("not connected")
        # Bridge expects newline-terminated ASCII. We always append '\n'.
        payload = (frame + "\n").encode("ascii", errors="replace")
        self._sock.sendall(payload)
        self.last_sent_bytes = payload
        return payload


# =========================================================================
# UI helpers
# =========================================================================

def hex_dump(data: bytes) -> tuple[str, str]:
    """Return (hex line, ascii line) for a small byte string.
    ASCII line uses . for non-printable and \\n for LF (educational)."""
    hex_line = " ".join(f"{b:02X}" for b in data)
    parts = []
    for b in data:
        if b == 0x0A:
            parts.append("\\n")
        elif b == 0x0D:
            parts.append("\\r")
        elif 0x20 <= b < 0x7F:
            parts.append(f" {chr(b)}")
        else:
            parts.append(" .")
    ascii_line = " ".join(parts)
    return hex_line, ascii_line


class LED(Canvas):
    """A colored circle for boolean or state indication."""

    def __init__(self, parent, size: int = 18):
        super().__init__(parent, width=size, height=size, bg=T.BG2,
                         highlightthickness=0, borderwidth=0)
        pad = 2
        self._oval = self.create_oval(pad, pad, size - pad, size - pad,
                                      fill=T.GREY, outline=T.BORDER)

    def set_color(self, color: str) -> None:
        self.itemconfig(self._oval, fill=color)


class SectionFrame(LabelFrame):
    """Standardized styling for section headers."""

    def __init__(self, parent, title: str):
        super().__init__(parent, text=title, bg=T.BG, fg=T.ACCENT,
                         font=T.UI_HEADER, bd=1, relief="solid",
                         highlightbackground=T.BORDER, padx=10, pady=8)


def styled_button(parent, text: str, command, danger: bool = False,
                  primary: bool = False, small: bool = False):
    bg = T.DANGER if danger else (T.ACCENT if primary else T.BG3)
    fg = T.BG if (danger or primary) else T.TEXT
    return Button(
        parent, text=text, command=command,
        bg=bg, fg=fg, activebackground=T.BG3, activeforeground=T.ACCENT,
        font=T.UI_SMALL if small else T.UI_BOLD,
        relief="flat", bd=0, padx=10, pady=4, cursor="hand2",
    )


def styled_entry(parent, textvariable, width: int = 20, monospace: bool = False):
    return Entry(
        parent, textvariable=textvariable, width=width,
        bg=T.BG3, fg=T.ACCENT2, insertbackground=T.ACCENT,
        relief="flat", bd=0,
        font=T.MONO if monospace else T.UI,
    )


def styled_label(parent, text: str, fg: str = T.TEXT, font=T.UI, bg: str = T.BG):
    return Label(parent, text=text, fg=fg, bg=bg, font=font, anchor=W, justify="left")


# =========================================================================
# App
# =========================================================================

class App(Tk):

    def __init__(self, config_path: Path):
        super().__init__()
        self.title("Flower — Robot Bridge Monitor & Tester")
        self.configure(bg=T.BG)
        self.geometry("1360x900")
        self.minsize(1200, 800)

        # State
        self._config_path = config_path
        self._cfg = self._load_config()
        self._bridge = BridgeProcess()
        self._plc = PlcMonitor(
            self._cfg["plc"]["ams_net_id"],
            int(self._cfg["plc"]["ams_port"]),
            self._cfg["plc"]["symbol_prefix"],
        )
        self._sim = RobotSimulator()
        self._prev_snapshot: PlcSnapshot = PlcSnapshot()
        self._prev_bridge_running: bool = False
        self._event_lines: list[str] = []

        # Build UI
        self._build_ui()

        # Start monitors
        self._plc.start()
        self._log_event(f"GUI started. Config: {self._config_path}")
        self._log_event(f"PLC target: ams={self._cfg['plc']['ams_net_id']} port={self._cfg['plc']['ams_port']} symbol={self._cfg['plc']['symbol_prefix']}")

        # Main tick
        self.after(100, self._tick)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---- config -----------------------------------------------------------

    def _load_config(self) -> dict:
        try:
            with self._config_path.open("r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) if yaml else {}
        except FileNotFoundError:
            # Fall back to defaults so the GUI can still open
            cfg = {}
        cfg.setdefault("plc", {})
        cfg["plc"].setdefault("ams_net_id", "127.0.0.1.1.1")
        cfg["plc"].setdefault("ams_port", 851)
        cfg["plc"].setdefault("symbol_prefix", "GVL_Robot.stRobot")
        cfg.setdefault("robot", {})
        cfg["robot"].setdefault("role", "server")
        cfg["robot"].setdefault("host", "127.0.0.1")
        cfg["robot"].setdefault("port", 2000)
        return cfg

    # ---- UI construction --------------------------------------------------

    def _build_ui(self) -> None:
        # ---------- Top strip: title + flow diagram ------------------------
        header = Frame(self, bg=T.BG2, height=110)
        header.pack(side="top", fill="x")
        header.pack_propagate(False)

        Label(header, text="Flower — Robot Bridge Monitor & Tester",
              fg=T.ACCENT, bg=T.BG2, font=T.UI_TITLE, anchor=W, padx=16).pack(anchor=W, pady=(8, 0))
        Label(header,
              text="This window plays both roles: (a) it starts/stops the bridge, and (b) it plays the robot so you can smoke-test the whole chain without any hardware.",
              fg=T.MUTED, bg=T.BG2, font=T.UI_SMALL, anchor=W, padx=16, wraplength=1200, justify="left"
              ).pack(anchor=W)

        self._flow_canvas = Canvas(header, bg=T.BG2, height=54,
                                   highlightthickness=0, borderwidth=0)
        self._flow_canvas.pack(fill="x", padx=16, pady=(4, 6))
        self._draw_flow_static()

        # ---------- Main body: two-column grid -----------------------------
        body = Frame(self, bg=T.BG)
        body.pack(fill="both", expand=True, padx=10, pady=(4, 6))
        body.columnconfigure(0, weight=1, uniform="col")
        body.columnconfigure(1, weight=1, uniform="col")
        body.rowconfigure(0, weight=1)

        left = Frame(body, bg=T.BG)
        left.grid(row=0, column=0, sticky=NSEW, padx=(0, 6))
        right = Frame(body, bg=T.BG)
        right.grid(row=0, column=1, sticky=NSEW, padx=(6, 0))

        self._build_bridge_panel(left)
        self._build_simulator_panel(left)
        self._build_plc_panel(right)
        self._build_event_log_panel(right)

        # ---------- Bottom: explanation panel ------------------------------
        self._build_explanation_panel(self)

        # ---------- Status bar --------------------------------------------
        self._status_bar = Label(self, text="Ready.",
                                 anchor=W, bg=T.BG2, fg=T.MUTED, font=T.UI_SMALL,
                                 padx=10, pady=4)
        self._status_bar.pack(side="bottom", fill="x")

    # ---- Flow diagram (top strip) -----------------------------------------

    def _draw_flow_static(self) -> None:
        c = self._flow_canvas
        c.delete("all")
        c.update_idletasks()
        W_ = max(c.winfo_width(), 1200)
        H_ = 48

        boxes = [
            ("Robot / this GUI", 20,           "sim"),
            ("Bridge (robot_bridge.py)", W_ // 2 - 200, "bridge"),
            ("PLC (GVL_Robot.stRobot)", W_ // 2 + 90, "plc"),
            ("HMI Robot page", W_ - 220, "hmi"),
        ]
        bw, bh = 180, 34
        self._flow_boxes: dict[str, int] = {}
        prev_right = None
        for label, x, key in boxes:
            rect = c.create_rectangle(x, 8, x + bw, 8 + bh,
                                      fill=T.BG3, outline=T.BORDER, width=1)
            c.create_text(x + bw / 2, 8 + bh / 2, text=label,
                          fill=T.TEXT, font=T.UI_SMALL)
            self._flow_boxes[key] = rect
            if prev_right is not None:
                mid_y = 8 + bh / 2
                c.create_line(prev_right, mid_y, x, mid_y,
                              fill=T.MUTED, width=2, arrow="last")
                c.create_text((prev_right + x) / 2, mid_y - 12,
                              text={"bridge": "TCP", "plc": "ADS", "hmi": "WS/ADS"}.get(key, ""),
                              fill=T.MUTED, font=T.UI_SMALL)
            prev_right = x + bw

    def _update_flow_colors(self, snap: PlcSnapshot) -> None:
        c = self._flow_canvas
        # Sim: green if simulator client is connected
        sim_color = T.ACCENT2 if self._sim.is_connected else T.BG3
        c.itemconfig(self._flow_boxes["sim"], fill=sim_color,
                     outline=T.ACCENT2 if self._sim.is_connected else T.BORDER)
        # Bridge: green if running
        br_color = T.ACCENT2 if self._bridge.is_running else T.BG3
        c.itemconfig(self._flow_boxes["bridge"], fill=br_color,
                     outline=T.ACCENT2 if self._bridge.is_running else T.BORDER)
        # PLC: green if snapshot ok
        plc_color = T.ACCENT2 if snap.ok else T.DANGER if snap.error else T.BG3
        c.itemconfig(self._flow_boxes["plc"], fill=plc_color,
                     outline=T.ACCENT2 if snap.ok else T.BORDER)
        # HMI: we can't observe it directly. Show green when PLC is reachable
        # AND eConnState indicates the pipeline is passing data.
        hmi_color = T.ACCENT2 if snap.ok and snap.eConnState == 2 else T.BG3
        c.itemconfig(self._flow_boxes["hmi"], fill=hmi_color,
                     outline=T.BORDER)

    # ---- Panel: bridge control -------------------------------------------

    def _build_bridge_panel(self, parent) -> None:
        frame = SectionFrame(parent, "Bridge process")
        frame.pack(fill="x", pady=(0, 8))

        top = Frame(frame, bg=T.BG)
        top.pack(fill="x")

        # Row 1: config path
        Label(top, text="Config:", fg=T.MUTED, bg=T.BG, font=T.UI_SMALL).grid(row=0, column=0, sticky=W, padx=(0, 6))
        self._cfg_path_var = StringVar(value=str(self._config_path))
        e = styled_entry(top, self._cfg_path_var, width=42, monospace=True)
        e.grid(row=0, column=1, sticky=W)
        styled_button(top, "Reload", self._reload_config, small=True).grid(row=0, column=2, padx=(6, 0))

        # Row 2: quick config summary (role / port / AMS)
        self._cfg_summary = Label(
            top, text="", fg=T.ACCENT2, bg=T.BG, font=T.MONO_S, anchor=W)
        self._cfg_summary.grid(row=1, column=0, columnspan=3, sticky=W, pady=(4, 6))

        # Row 3: buttons + status
        btn_row = Frame(frame, bg=T.BG)
        btn_row.pack(fill="x", pady=(2, 4))
        self._btn_start = styled_button(btn_row, "▶ Start bridge", self._on_start_bridge, primary=True)
        self._btn_start.pack(side="left")
        self._btn_stop = styled_button(btn_row, "■ Stop bridge", self._on_stop_bridge, danger=True)
        self._btn_stop.pack(side="left", padx=(6, 0))
        self._btn_stop.configure(state=DISABLED)

        # Status LED + text
        status = Frame(frame, bg=T.BG)
        status.pack(fill="x", pady=(2, 4))
        Label(status, text="Bridge state:", fg=T.MUTED, bg=T.BG, font=T.UI_SMALL).pack(side="left")
        self._bridge_led = LED(status, size=14)
        self._bridge_led.pack(side="left", padx=(6, 4))
        self._bridge_state_label = Label(status, text="Not running",
                                         fg=T.MUTED, bg=T.BG, font=T.UI_BOLD)
        self._bridge_state_label.pack(side="left")

        # stdout tail
        Label(frame, text="Bridge stdout:",
              fg=T.MUTED, bg=T.BG, font=T.UI_SMALL).pack(anchor=W, pady=(6, 2))
        self._bridge_log = Text(frame, height=8, bg=T.BG3, fg=T.ACCENT2,
                                insertbackground=T.ACCENT, relief="flat", bd=0,
                                font=T.MONO_S, wrap="none", state=DISABLED)
        self._bridge_log.pack(fill="both", expand=False)

        self._update_cfg_summary()

    def _update_cfg_summary(self) -> None:
        cfg = self._cfg
        text = (
            f"role={cfg['robot']['role']}  port={cfg['robot']['port']}  "
            f"host={cfg['robot'].get('host', '-')}  |  "
            f"ams={cfg['plc']['ams_net_id']}:{cfg['plc']['ams_port']}  "
            f"symbol={cfg['plc']['symbol_prefix']}"
        )
        self._cfg_summary.configure(text=text)

    # ---- Panel: robot simulator ------------------------------------------

    def _build_simulator_panel(self, parent) -> None:
        frame = SectionFrame(parent, "Robot simulator  —  play the robot")
        frame.pack(fill="both", expand=True, pady=(0, 0))

        top = Frame(frame, bg=T.BG)
        top.pack(fill="x")
        Label(top, text="Target host:", fg=T.MUTED, bg=T.BG, font=T.UI_SMALL).grid(row=0, column=0, sticky=W)
        self._sim_host = StringVar(value=str(self._cfg["robot"].get("host", "127.0.0.1")))
        styled_entry(top, self._sim_host, width=18, monospace=True).grid(row=0, column=1, sticky=W, padx=(4, 12))
        Label(top, text="Port:", fg=T.MUTED, bg=T.BG, font=T.UI_SMALL).grid(row=0, column=2, sticky=W)
        self._sim_port = StringVar(value=str(self._cfg["robot"]["port"]))
        styled_entry(top, self._sim_port, width=8, monospace=True).grid(row=0, column=3, sticky=W, padx=(4, 12))

        self._btn_sim_connect = styled_button(top, "Connect", self._on_sim_connect, primary=True)
        self._btn_sim_connect.grid(row=0, column=4)
        self._btn_sim_disconnect = styled_button(top, "Disconnect", self._on_sim_disconnect, danger=True)
        self._btn_sim_disconnect.grid(row=0, column=5, padx=(6, 0))
        self._btn_sim_disconnect.configure(state=DISABLED)

        # Sim status
        st = Frame(frame, bg=T.BG)
        st.pack(fill="x", pady=(6, 4))
        Label(st, text="Client state:", fg=T.MUTED, bg=T.BG, font=T.UI_SMALL).pack(side="left")
        self._sim_led = LED(st, size=14)
        self._sim_led.pack(side="left", padx=(6, 4))
        self._sim_state_label = Label(st, text="Disconnected", fg=T.MUTED, bg=T.BG, font=T.UI_BOLD)
        self._sim_state_label.pack(side="left")

        # Send buttons
        Label(frame, text="Send a frame  (bridge parses one line per '\\n'):",
              fg=T.MUTED, bg=T.BG, font=T.UI_SMALL).pack(anchor=W, pady=(6, 2))
        btns = Frame(frame, bg=T.BG)
        btns.pack(fill="x")
        for label in ("POS1", "POS2", "POS3"):
            styled_button(btns, label, lambda l=label: self._on_sim_send(l),
                          primary=True, small=True).pack(side="left", padx=(0, 6))
        styled_button(btns, "FOO (unknown)", lambda: self._on_sim_send("FOO"), small=True).pack(side="left", padx=(6, 0))

        # Custom frame entry
        cust = Frame(frame, bg=T.BG)
        cust.pack(fill="x", pady=(6, 2))
        Label(cust, text="Custom:", fg=T.MUTED, bg=T.BG, font=T.UI_SMALL).pack(side="left")
        self._sim_custom = StringVar(value="")
        e = styled_entry(cust, self._sim_custom, width=24, monospace=True)
        e.pack(side="left", padx=(4, 6))
        e.bind("<Return>", lambda ev: self._on_sim_send_custom())
        styled_button(cust, "Send", self._on_sim_send_custom, small=True).pack(side="left")

        # Bytes preview
        Label(frame, text="Bytes on the wire (last frame):  each byte is what actually left this program.",
              fg=T.MUTED, bg=T.BG, font=T.UI_SMALL).pack(anchor=W, pady=(10, 2))
        preview = Frame(frame, bg=T.BG3, padx=8, pady=6)
        preview.pack(fill="x")
        Label(preview, text="Hex  ", fg=T.MUTED, bg=T.BG3, font=T.MONO_S).grid(row=0, column=0, sticky=W)
        self._bytes_hex = Label(preview, text="—", fg=T.ACCENT, bg=T.BG3, font=T.MONO, anchor=W)
        self._bytes_hex.grid(row=0, column=1, sticky=W)
        Label(preview, text="ASCII", fg=T.MUTED, bg=T.BG3, font=T.MONO_S).grid(row=1, column=0, sticky=W)
        self._bytes_ascii = Label(preview, text="—", fg=T.ACCENT2, bg=T.BG3, font=T.MONO, anchor=W)
        self._bytes_ascii.grid(row=1, column=1, sticky=W)

    # ---- Panel: PLC live state -------------------------------------------

    def _build_plc_panel(self, parent) -> None:
        frame = SectionFrame(parent, "PLC live state  —  GVL_Robot.stRobot (polled via ADS)")
        frame.pack(fill="x", pady=(0, 8))

        # Big state banner
        banner = Frame(frame, bg=T.BG3, padx=12, pady=10)
        banner.pack(fill="x", pady=(2, 8))
        Label(banner, text="Connection state", fg=T.MUTED, bg=T.BG3, font=T.UI_SMALL).grid(row=0, column=0, sticky=W)
        state_row = Frame(banner, bg=T.BG3)
        state_row.grid(row=1, column=0, sticky=W, pady=(2, 0))
        self._plc_conn_led = LED(state_row, size=22)
        self._plc_conn_led.pack(side="left")
        self._plc_conn_label = Label(state_row, text="—", fg=T.MUTED, bg=T.BG3, font=T.UI_TITLE)
        self._plc_conn_label.pack(side="left", padx=(8, 0))

        # Position indicators
        pos = Frame(frame, bg=T.BG)
        pos.pack(fill="x", pady=(0, 8))
        Label(pos, text="AT POSITION", fg=T.MUTED, bg=T.BG, font=T.UI_SMALL).pack(anchor=W)
        row = Frame(pos, bg=T.BG)
        row.pack(anchor=W, pady=(4, 0))
        self._pos_leds: list[LED] = []
        self._pos_labels: list[Label] = []
        for i in (1, 2, 3):
            box = Frame(row, bg=T.BG3, padx=10, pady=6)
            box.pack(side="left", padx=(0, 6))
            led = LED(box, size=20); led.pack(side="left")
            lbl = Label(box, text=f"POS {i}", fg=T.MUTED, bg=T.BG3, font=T.UI_BOLD)
            lbl.pack(side="left", padx=(6, 0))
            self._pos_leds.append(led)
            self._pos_labels.append(lbl)

        # Counters + last message
        details = Frame(frame, bg=T.BG)
        details.pack(fill="x")
        details.columnconfigure(1, weight=1)

        Label(details, text="Packets received:", fg=T.MUTED, bg=T.BG, font=T.UI_SMALL).grid(row=0, column=0, sticky=W)
        self._plc_pkts = Label(details, text="—", fg=T.ACCENT2, bg=T.BG, font=T.MONO)
        self._plc_pkts.grid(row=0, column=1, sticky=W, padx=(8, 0))

        Label(details, text="Last message:", fg=T.MUTED, bg=T.BG, font=T.UI_SMALL).grid(row=1, column=0, sticky=W)
        self._plc_last = Label(details, text="—", fg=T.ACCENT2, bg=T.BG, font=T.MONO, anchor=W)
        self._plc_last.grid(row=1, column=1, sticky=W, padx=(8, 0))

        Label(details, text="Name:", fg=T.MUTED, bg=T.BG, font=T.UI_SMALL).grid(row=2, column=0, sticky=W)
        self._plc_name = Label(details, text="—", fg=T.TEXT, bg=T.BG, font=T.MONO)
        self._plc_name.grid(row=2, column=1, sticky=W, padx=(8, 0))

        Label(details, text="ADS poll status:", fg=T.MUTED, bg=T.BG, font=T.UI_SMALL).grid(row=3, column=0, sticky=W)
        self._plc_poll_status = Label(details, text="—", fg=T.WARN, bg=T.BG, font=T.MONO_S, anchor=W)
        self._plc_poll_status.grid(row=3, column=1, sticky=W, padx=(8, 0))

    # ---- Panel: event log ------------------------------------------------

    def _build_event_log_panel(self, parent) -> None:
        frame = SectionFrame(parent, "Event log")
        frame.pack(fill="both", expand=True)

        top = Frame(frame, bg=T.BG)
        top.pack(fill="x", pady=(0, 4))
        Label(top, text="A merged feed of GUI events + PLC state changes + bridge stdout.",
              fg=T.MUTED, bg=T.BG, font=T.UI_SMALL).pack(side="left")
        styled_button(top, "Clear", self._clear_log, small=True).pack(side="right")

        self._log = Text(frame, bg=T.BG3, fg=T.TEXT,
                         insertbackground=T.ACCENT, relief="flat", bd=0,
                         font=T.MONO_S, wrap="none", state=DISABLED)
        self._log.pack(fill="both", expand=True)
        # Tag colors
        self._log.tag_configure("info",   foreground=T.TEXT)
        self._log.tag_configure("event",  foreground=T.ACCENT2)
        self._log.tag_configure("bridge", foreground=T.ACCENT)
        self._log.tag_configure("sim",    foreground=T.WARN)
        self._log.tag_configure("error",  foreground=T.DANGER)

    # ---- Panel: explanation ----------------------------------------------

    def _build_explanation_panel(self, parent) -> None:
        frame = LabelFrame(parent, text="What is happening right now",
                           bg=T.BG, fg=T.WARN, font=T.UI_HEADER,
                           bd=1, relief="solid", padx=12, pady=8, height=170)
        frame.pack(side="bottom", fill="x", padx=10, pady=(0, 8))
        frame.pack_propagate(False)
        self._explain = Text(frame, bg=T.BG, fg=T.TEXT,
                             relief="flat", bd=0, font=T.UI,
                             wrap=WORD, state=DISABLED, height=6)
        self._explain.pack(fill="both", expand=True)
        # Tags for emphasis
        self._explain.tag_configure("b", font=T.UI_BOLD, foreground=T.ACCENT)
        self._explain.tag_configure("code", font=T.MONO_S, foreground=T.ACCENT2)
        self._explain.tag_configure("warn", foreground=T.WARN)
        self._explain.tag_configure("hint", foreground=T.MUTED, font=T.UI_SMALL)

    # ---- Event log helpers ------------------------------------------------

    def _log_event(self, msg: str, tag: str = "info") -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        self._log.configure(state=NORMAL)
        self._log.insert(END, f"{ts}  ", "info")
        self._log.insert(END, msg + "\n", tag)
        self._log.see(END)
        self._log.configure(state=DISABLED)

    def _clear_log(self) -> None:
        self._log.configure(state=NORMAL)
        self._log.delete("1.0", END)
        self._log.configure(state=DISABLED)

    def _append_bridge_log(self, line: str) -> None:
        self._bridge_log.configure(state=NORMAL)
        self._bridge_log.insert(END, line + "\n")
        # Cap to last 500 lines
        if int(self._bridge_log.index("end-1c").split(".")[0]) > 500:
            self._bridge_log.delete("1.0", "50.0")
        self._bridge_log.see(END)
        self._bridge_log.configure(state=DISABLED)

    # ---- Handlers: bridge -------------------------------------------------

    def _on_start_bridge(self) -> None:
        if self._bridge.is_running:
            return
        try:
            self._bridge.start(Path(self._cfg_path_var.get()))
        except Exception as e:
            messagebox.showerror("Bridge start failed", str(e))
            self._log_event(f"bridge start failed: {e}", "error")
            return
        self._log_event(f"bridge started (PID {self._bridge.pid})", "bridge")
        self._btn_start.configure(state=DISABLED)
        self._btn_stop.configure(state=NORMAL)

    def _on_stop_bridge(self) -> None:
        if not self._bridge.is_running:
            return
        self._log_event("stopping bridge…", "bridge")
        self._bridge.stop()
        self._btn_start.configure(state=NORMAL)
        self._btn_stop.configure(state=DISABLED)

    def _reload_config(self) -> None:
        try:
            self._config_path = Path(self._cfg_path_var.get())
            self._cfg = self._load_config()
            self._sim_host.set(str(self._cfg["robot"].get("host", "127.0.0.1")))
            self._sim_port.set(str(self._cfg["robot"]["port"]))
            self._update_cfg_summary()
            self._log_event(f"config reloaded from {self._config_path}", "event")
        except Exception as e:
            self._log_event(f"config reload failed: {e}", "error")

    # ---- Handlers: simulator ---------------------------------------------

    def _on_sim_connect(self) -> None:
        try:
            host = self._sim_host.get().strip()
            port = int(self._sim_port.get())
            self._sim.connect(host, port)
            self._log_event(f"sim: connected TCP to {host}:{port}", "sim")
            self._btn_sim_connect.configure(state=DISABLED)
            self._btn_sim_disconnect.configure(state=NORMAL)
        except Exception as e:
            messagebox.showerror("Connect failed",
                                 f"Could not open a TCP client to the bridge.\n\n"
                                 f"Is the bridge running in server mode?\n\n{e}")
            self._log_event(f"sim: connect failed — {e}", "error")

    def _on_sim_disconnect(self) -> None:
        self._sim.disconnect()
        self._log_event("sim: disconnected", "sim")
        self._btn_sim_connect.configure(state=NORMAL)
        self._btn_sim_disconnect.configure(state=DISABLED)

    def _on_sim_send(self, frame: str) -> None:
        if not self._sim.is_connected:
            messagebox.showwarning("Not connected",
                                   "Press Connect first — the simulator has to open a TCP client to the bridge before it can send.")
            return
        try:
            payload = self._sim.send(frame)
            self._log_event(f"sim → bridge: {frame!r}  ({len(payload)} bytes)", "sim")
            hex_line, ascii_line = hex_dump(payload)
            self._bytes_hex.configure(text=hex_line)
            self._bytes_ascii.configure(text=ascii_line)
        except Exception as e:
            self._log_event(f"sim: send failed — {e}", "error")
            self._on_sim_disconnect()

    def _on_sim_send_custom(self) -> None:
        frame = self._sim_custom.get().strip()
        if not frame:
            return
        self._on_sim_send(frame)
        self._sim_custom.set("")

    # ---- Tick loop --------------------------------------------------------

    def _tick(self) -> None:
        # Drain bridge stdout
        for line in self._bridge.poll_lines():
            self._append_bridge_log(line)
            # Also mirror the interesting lines to the main event log
            if any(k in line for k in ("connected", "listening", "closed", "rx:", "ERROR", "failed", "exited")):
                self._log_event(f"bridge: {line}", "bridge")

        # Bridge running/stopped transition
        running = self._bridge.is_running
        if running != self._prev_bridge_running:
            if not running:
                self._log_event("bridge process ended", "bridge")
                self._btn_start.configure(state=NORMAL)
                self._btn_stop.configure(state=DISABLED)
            self._prev_bridge_running = running

        self._bridge_led.set_color(T.ACCENT2 if running else T.GREY)
        self._bridge_state_label.configure(
            text=f"Running (PID {self._bridge.pid})" if running else "Not running",
            fg=T.ACCENT2 if running else T.MUTED,
        )

        # Simulator LED
        self._sim_led.set_color(T.ACCENT2 if self._sim.is_connected else T.GREY)
        self._sim_state_label.configure(
            text=f"Connected → {self._sim.remote}" if self._sim.is_connected else "Disconnected",
            fg=T.ACCENT2 if self._sim.is_connected else T.MUTED,
        )

        # PLC snapshot
        snap = self._plc.snapshot()
        self._update_plc_display(snap)

        # Flow diagram highlight
        self._update_flow_colors(snap)

        # Explanation
        self._update_explanation(snap)

        # Status bar
        self._status_bar.configure(
            text=f"ADS: {'ok' if snap.ok else snap.error or 'no data'}   |   "
                 f"Bridge: {'running (PID '+str(self._bridge.pid)+')' if running else 'stopped'}   |   "
                 f"Sim client: {'connected' if self._sim.is_connected else 'idle'}"
        )

        self._prev_snapshot = snap
        self.after(150, self._tick)

    def _update_plc_display(self, snap: PlcSnapshot) -> None:
        if not snap.ok:
            self._plc_conn_led.set_color(T.DANGER)
            self._plc_conn_label.configure(text="ADS not reachable", fg=T.DANGER)
            self._plc_poll_status.configure(text=snap.error or "no data", fg=T.DANGER)
            return

        color, txt = STATE_COLORS.get(snap.eConnState, (T.MUTED, f"unknown ({snap.eConnState})"))
        self._plc_conn_led.set_color(color)
        self._plc_conn_label.configure(text=f"{snap.sConnStateText or txt}   ({snap.eConnState})", fg=color)

        for i, (led, lbl, val) in enumerate(zip(
            self._pos_leds, self._pos_labels,
            (snap.bAtPos1, snap.bAtPos2, snap.bAtPos3)
        )):
            led.set_color(T.ACCENT2 if val else T.GREY)
            lbl.configure(fg=T.ACCENT2 if val else T.MUTED)

        self._plc_pkts.configure(text=str(snap.nPacketsRx))
        self._plc_last.configure(text=repr(snap.sLastMessage) if snap.sLastMessage else "(empty)")
        self._plc_name.configure(text=snap.Name)
        self._plc_poll_status.configure(
            text=f"ok — last read {datetime.fromtimestamp(snap.when).strftime('%H:%M:%S.%f')[:-3]}",
            fg=T.ACCENT2,
        )

        # Log significant transitions
        prev = self._prev_snapshot
        if not prev.ok and snap.ok:
            self._log_event("plc: ADS symbol now reachable", "event")
        if prev.ok and snap.ok:
            if prev.eConnState != snap.eConnState:
                self._log_event(
                    f"plc: eConnState {prev.eConnState} → {snap.eConnState}  ({snap.sConnStateText})",
                    "event",
                )
            for i, (a, b) in enumerate(zip(
                (prev.bAtPos1, prev.bAtPos2, prev.bAtPos3),
                (snap.bAtPos1, snap.bAtPos2, snap.bAtPos3),
            )):
                if a != b:
                    self._log_event(f"plc: bAtPos{i+1} {a} → {b}", "event")
            if prev.nPacketsRx != snap.nPacketsRx:
                self._log_event(f"plc: nPacketsRx {prev.nPacketsRx} → {snap.nPacketsRx}, last={snap.sLastMessage!r}", "event")

    # ---- Explanation content ---------------------------------------------

    def _update_explanation(self, snap: PlcSnapshot) -> None:
        # Decide which of several narrations applies right now.
        running = self._bridge.is_running
        connected = self._sim.is_connected

        parts: list[tuple[str, str]] = []

        if not running:
            parts.append(("The bridge is NOT running.", "b"))
            parts.append(("  ", ""))
            parts.append((
                "Press ▶ Start bridge to launch robot_bridge.py in a child process. "
                "It will open an ADS connection to the PLC and, in ",
                ""
            ))
            parts.append(("server mode", "code"))
            parts.append((
                ", start listening on a TCP port waiting for the robot to dial in.\n",
                "",
            ))
        elif running and not connected and snap.ok and snap.eConnState == 1:
            parts.append(("The bridge is running and LISTENING (server mode).", "b"))
            parts.append(("\n", ""))
            parts.append((
                "It called socket.listen() on port ",
                "",
            ))
            parts.append((str(self._cfg["robot"]["port"]), "code"))
            parts.append((
                " and is now blocked in socket.accept(). This is what \"Connecting\" means on the PLC side — "
                "a real robot (or this GUI, if you press Connect below) would dial in and turn this into ",
                "",
            ))
            parts.append(("Connected", "code"))
            parts.append((".\n", ""))
        elif running and connected:
            parts.append(("The GUI is playing the robot.", "b"))
            parts.append(("\n", ""))
            parts.append((
                "You opened a TCP client socket to the bridge. Every ",
                "",
            ))
            parts.append(("Send", "code"))
            parts.append((
                " packs your text into ASCII bytes, appends a newline (",
                "",
            ))
            parts.append(("0x0A", "code"))
            parts.append((
                "), and writes them through the socket. The bridge's read loop concatenates incoming bytes and splits on ",
                "",
            ))
            parts.append(("\\n", "code"))
            parts.append((
                " to get whole frames. For POS1/POS2/POS3 it calls plc.write_by_name() to flip bAtPosN in ",
                "",
            ))
            parts.append(("GVL_Robot.stRobot", "code"))
            parts.append((". Unknown frames update sLastMessage but leave the position bits alone.\n", ""))
        elif not snap.ok:
            parts.append(("Cannot reach the PLC via ADS.", "warn"))
            parts.append(("\n", ""))
            parts.append((
                "The GUI can't read GVL_Robot.stRobot right now. Check that TwinCAT is in Run mode and the AMS Net ID / port in the config are correct. "
                "Details: ",
                "",
            ))
            parts.append((snap.error or "(no error text)", "code"))
            parts.append(("\n", ""))
        else:
            parts.append(("Bridge is running, but no simulator client is attached.", "b"))
            parts.append(("\n", ""))
            parts.append((
                "You can either start a real robot connection, or press Connect in the simulator panel to play the robot from this GUI.",
                "",
            ))

        # Trailing hint
        parts.append(("\n", ""))
        parts.append((
            "Hint — the Event log on the right shows the raw sequence of events across all three layers (GUI, bridge, PLC).",
            "hint",
        ))

        self._explain.configure(state=NORMAL)
        self._explain.delete("1.0", END)
        for text, tag in parts:
            if tag:
                self._explain.insert(END, text, tag)
            else:
                self._explain.insert(END, text)
        self._explain.configure(state=DISABLED)

    # ---- Shutdown ---------------------------------------------------------

    def _on_close(self) -> None:
        try:
            self._sim.disconnect()
        except Exception:
            pass
        try:
            self._bridge.stop()
        except Exception:
            pass
        try:
            self._plc.stop()
        except Exception:
            pass
        self.destroy()


# =========================================================================
# main
# =========================================================================

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Robot Bridge Monitor & Tester GUI")
    parser.add_argument(
        "--config",
        default=str(Path(__file__).with_name("config.yaml")),
        help="path to the bridge YAML config (default: ./config.yaml)",
    )
    args = parser.parse_args(argv)

    missing = []
    if pyads is None: missing.append("pyads")
    if yaml is None:  missing.append("pyyaml")
    if missing:
        print(f"Missing dependencies: {', '.join(missing)}", file=sys.stderr)
        print("Install with:  pip install -r requirements.txt", file=sys.stderr)
        return 2

    cfg_path = Path(args.config)
    if not cfg_path.exists():
        # Fall back to config.example.yaml so the GUI can still launch
        alt = cfg_path.with_name("config.example.yaml")
        if alt.exists():
            print(f"[info] {cfg_path.name} not found — using {alt.name}", file=sys.stderr)
            cfg_path = alt

    app = App(cfg_path)
    app.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
