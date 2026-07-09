"""
Flower — Robot TCP/IP <-> PLC ADS bridge.

Runs as a long-lived process. Talks to the industrial robot over TCP/IP
(server or client mode, chosen by config), parses line-terminated ASCII
frames of the form "POS1\\n" / "POS2\\n" / "POS3\\n", and writes the
resulting state into `GVL_Robot.stRobot` on the TwinCAT PLC over ADS.

The PLC has no networking code; this process is the whole comms layer.
See docs/superpowers/specs (or the git log) for the design context.
"""

from __future__ import annotations

import argparse
import logging
import socket
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pyads
import yaml

from csv_logger import DailyCsvHandler
from log_pump import PlcLogPump
from retention import run_retention, start_periodic_retention


# ---------------------------------------------------------------------------
# ST_HmiRobot mirror — E_RobotConnState values must match E_RobotConnState.TcDUT
# ---------------------------------------------------------------------------

class ConnState:
    DISCONNECTED = 0
    CONNECTING = 1
    CONNECTED = 2
    ERROR = 3

    _TEXT = {
        DISCONNECTED: "Disconnected",
        CONNECTING: "Connecting",
        CONNECTED: "Connected",
        ERROR: "Error",
    }

    @classmethod
    def text(cls, state: int) -> str:
        return cls._TEXT.get(state, "Unknown")


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@dataclass
class Config:
    ams_net_id: str
    ams_port: int
    symbol_prefix: str
    role: str            # "server" or "client"
    host: str            # ignored when role == "server"
    port: int
    encoding: str
    socket_timeout: float
    heartbeat_idle_seconds: float   # 0 disables the idle probe
    heartbeat_payload: bytes
    reconnect_delay: float
    # Logger settings — see csv_logger.py / log_pump.py / retention.py
    log_dir: Path
    log_retention_days: int
    log_retention_mb: int
    log_level: str
    log_plc_ring_poll_ms: int

    @classmethod
    def load(cls, path: Path) -> "Config":
        with path.open("r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        logger_cfg = raw.get("logger", {}) or {}
        robot_cfg = raw["robot"]
        return cls(
            ams_net_id=raw["plc"]["ams_net_id"],
            ams_port=int(raw["plc"]["ams_port"]),
            symbol_prefix=raw["plc"]["symbol_prefix"],
            role=robot_cfg["role"],
            host=robot_cfg.get("host", ""),
            port=int(robot_cfg["port"]),
            encoding=robot_cfg.get("encoding", "ascii"),
            socket_timeout=float(robot_cfg.get("socket_timeout", 2.0)),
            heartbeat_idle_seconds=float(robot_cfg.get("heartbeat_idle_seconds", 0)),
            heartbeat_payload=str(robot_cfg.get("heartbeat_payload", "HEARTBEAT")).encode("ascii"),
            reconnect_delay=float(raw.get("reconnect", {}).get("delay_seconds", 2.0)),
            log_dir=Path(logger_cfg.get("dir", "./logs")),
            log_retention_days=int(logger_cfg.get("retention_days", 30)),
            log_retention_mb=int(logger_cfg.get("retention_mb", 500)),
            log_level=str(logger_cfg.get("level", "INFO")).upper(),
            log_plc_ring_poll_ms=int(logger_cfg.get("plc_ring_poll_ms", 500)),
        )


# ---------------------------------------------------------------------------
# PLC-writer shim — one place that knows the ST_HmiRobot field names
# ---------------------------------------------------------------------------

class PlcRobotSymbol:
    """Wraps writes into GVL_Robot.stRobot on the PLC."""

    def __init__(self, plc: pyads.Connection, prefix: str):
        self._plc = plc
        self._prefix = prefix
        self._packets_rx = 0

    def _write(self, field: str, value, plc_type):
        self._plc.write_by_name(f"{self._prefix}.{field}", value, plc_type)

    def set_conn_state(self, state: int) -> None:
        self._write("eConnState", state, pyads.PLCTYPE_UINT)
        self._write("sConnStateText", ConnState.text(state), pyads.PLCTYPE_STRING)

    def set_position(self, pos: int) -> None:
        """Latch the given position (1/2/3) TRUE, clear the other two."""
        self._write("bAtPos1", pos == 1, pyads.PLCTYPE_BOOL)
        self._write("bAtPos2", pos == 2, pyads.PLCTYPE_BOOL)
        self._write("bAtPos3", pos == 3, pyads.PLCTYPE_BOOL)

    def record_packet(self, message: str) -> None:
        self._packets_rx += 1
        self._write("nPacketsRx", self._packets_rx, pyads.PLCTYPE_UDINT)
        self._write("sLastMessage", message[:80], pyads.PLCTYPE_STRING)


# ---------------------------------------------------------------------------
# Frame parser — pure, no I/O
# ---------------------------------------------------------------------------

class LineAccumulator:
    """Buffers received bytes and yields complete lines (stripped)."""

    def __init__(self, encoding: str):
        self._buffer = bytearray()
        self._encoding = encoding

    def feed(self, data: bytes):
        self._buffer.extend(data)
        while b"\n" in self._buffer:
            line, _, rest = self._buffer.partition(b"\n")
            self._buffer = bytearray(rest)
            yield line.decode(self._encoding, errors="replace").strip("\r\n\t ")


def parse_position(line: str) -> Optional[int]:
    """Return 1/2/3 for POS1/POS2/POS3 (case-insensitive); None otherwise."""
    upper = line.upper()
    if upper == "POS1":
        return 1
    if upper == "POS2":
        return 2
    if upper == "POS3":
        return 3
    return None


# ---------------------------------------------------------------------------
# Socket helpers — one function per role
# ---------------------------------------------------------------------------

def _tune_connected_socket(conn: socket.socket, cfg: Config) -> None:
    """Apply socket options common to both roles once a connection is up."""
    # SO_KEEPALIVE lets the OS detect a half-open TCP connection (peer power
    # loss, cable pulled) even when the robot is idle and never sends POS
    # frames. Keepalive tuning uses OS defaults — good enough for a robot
    # that emits frames often; if the plant network drops packets silently
    # for longer than the default (~2 hours on Linux, ~2 hours on Windows)
    # a broken link will linger, but the heartbeat idle-probe below catches
    # that within `heartbeat_idle_seconds`.
    conn.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)


def accept_from_robot(cfg: Config) -> socket.socket:
    """Server mode: bind + listen + accept. Blocks until a robot connects."""
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("0.0.0.0", cfg.port))
    listener.listen(1)
    logging.info("listening on :%d", cfg.port)
    try:
        conn, addr = listener.accept()
    finally:
        listener.close()
    logging.info("robot connected from %s", addr)
    _tune_connected_socket(conn, cfg)
    return conn


def connect_to_robot(cfg: Config) -> socket.socket:
    """Client mode: dial the robot's TCP server."""
    logging.info("connecting to robot %s:%d", cfg.host, cfg.port)
    conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    conn.settimeout(cfg.socket_timeout)
    conn.connect((cfg.host, cfg.port))
    logging.info("connected to %s:%d", cfg.host, cfg.port)
    _tune_connected_socket(conn, cfg)
    return conn


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def run_once(cfg: Config, plc_symbol: PlcRobotSymbol) -> None:
    """One full connect → receive → parse → disconnect cycle."""
    plc_symbol.set_conn_state(ConnState.CONNECTING)

    if cfg.role == "server":
        conn = accept_from_robot(cfg)
    elif cfg.role == "client":
        conn = connect_to_robot(cfg)
    else:
        raise ValueError(f"robot.role must be 'server' or 'client', got {cfg.role!r}")

    plc_symbol.set_conn_state(ConnState.CONNECTED)
    accumulator = LineAccumulator(cfg.encoding)

    # Set a short recv timeout so we can probe the connection when the robot
    # is idle. The heartbeat_idle_seconds gate below throttles actual probes
    # so we only send one every N idle windows, not on every recv timeout.
    if cfg.heartbeat_idle_seconds > 0:
        recv_timeout = min(cfg.socket_timeout, cfg.heartbeat_idle_seconds)
    else:
        recv_timeout = cfg.socket_timeout
    conn.settimeout(recv_timeout)

    idle_seconds = 0.0

    try:
        while True:
            try:
                data = conn.recv(4096)
            except socket.timeout:
                idle_seconds += recv_timeout
                if cfg.heartbeat_idle_seconds > 0 and idle_seconds >= cfg.heartbeat_idle_seconds:
                    # Half-open detection: send the heartbeat payload. We do
                    # not wait for a response — the send itself will raise if
                    # the TCP path is broken (BrokenPipeError / ConnectionReset
                    # once the OS notices), and TCP KEEPALIVE covers slower
                    # cases. On success, just reset the idle counter.
                    try:
                        conn.sendall(cfg.heartbeat_payload)
                        logging.debug("heartbeat sent (idle %.1fs)", idle_seconds)
                    except OSError as exc:
                        logging.info("heartbeat send failed (%s); dropping connection", exc)
                        break
                    idle_seconds = 0.0
                continue

            if not data:
                logging.info("robot closed the connection")
                break
            idle_seconds = 0.0
            for line in accumulator.feed(data):
                if not line:
                    continue
                logging.info("rx: %r", line)
                plc_symbol.record_packet(line)
                pos = parse_position(line)
                if pos is not None:
                    plc_symbol.set_position(pos)
                # unknown frames still update sLastMessage/nPacketsRx above
    finally:
        conn.close()
        plc_symbol.set_conn_state(ConnState.DISCONNECTED)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Flower robot TCP <-> PLC ADS bridge")
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="path to YAML config file (default: ./config.yaml)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="logging level (DEBUG, INFO, WARNING, ERROR)",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        format="%(asctime)s  %(levelname)-7s  %(message)s",
        level=getattr(logging, args.log_level.upper(), logging.INFO),
    )

    cfg_path = Path(args.config)
    if not cfg_path.is_file():
        logging.error("config file not found: %s", cfg_path)
        return 2

    cfg = Config.load(cfg_path)
    logging.info("loaded config: role=%s port=%d ams=%s", cfg.role, cfg.port, cfg.ams_net_id)

    # ---- Attach the daily CSV handler and enforce the configured level.
    # Both PLC-side events (via log_pump) and Python-side bridge events
    # (via logging.info/error/etc.) flow through this handler.
    root_logger = logging.getLogger()
    csv_handler = DailyCsvHandler(cfg.log_dir)
    csv_handler.setLevel(getattr(logging, cfg.log_level, logging.INFO))
    root_logger.addHandler(csv_handler)
    root_logger.setLevel(min(root_logger.level, csv_handler.level))
    logging.info("csv logger: dir=%s level=%s", cfg.log_dir, cfg.log_level)

    # ---- Initial retention sweep, then a daemon thread that reruns hourly.
    run_retention(cfg.log_dir, cfg.log_retention_days, cfg.log_retention_mb)
    retention_stop = start_periodic_retention(
        cfg.log_dir, cfg.log_retention_days, cfg.log_retention_mb, interval_s=3600.0
    )

    plc = pyads.Connection(cfg.ams_net_id, cfg.ams_port)
    plc.open()
    logging.info("ADS opened to %s:%d", cfg.ams_net_id, cfg.ams_port)

    # ---- Start pumping PLC ring buffer into our logging pipeline.
    log_pump = PlcLogPump(plc, poll_ms=cfg.log_plc_ring_poll_ms)
    log_pump.start()

    symbol = PlcRobotSymbol(plc, cfg.symbol_prefix)
    symbol.set_conn_state(ConnState.DISCONNECTED)

    try:
        while True:
            try:
                run_once(cfg, symbol)
            except Exception:  # noqa: BLE001 — top-level supervisor, log and retry
                logging.exception("bridge cycle failed; retrying in %.1fs", cfg.reconnect_delay)
                symbol.set_conn_state(ConnState.ERROR)
            time.sleep(cfg.reconnect_delay)
    except KeyboardInterrupt:
        logging.info("interrupted, shutting down")
    finally:
        try:
            symbol.set_conn_state(ConnState.DISCONNECTED)
        except Exception:  # noqa: BLE001
            pass
        log_pump.stop()
        retention_stop.set()
        plc.close()
        csv_handler.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
