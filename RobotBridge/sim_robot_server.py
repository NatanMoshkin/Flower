"""Robot-side TCP server for smoke-testing the bridge, in background-friendly form.

The Flower robot is the TCP *server*; the bridge (RobotBridge/robot_bridge.py)
is the *client* and dials in. This script plays that server side.

Two sockets:

    :6001  (default)  — the "robot" port. Bridge dials in. When connected,
                        this script prints every inbound frame from the
                        bridge (AUTO_STARTED / PUSH_DONE / PISTONS_ERROR /
                        HEARTBEAT) with timestamp + hex.

    :6002  (default)  — the "control" port. A frame injector: connect,
                        send one line, close. The line is forwarded to the
                        bridge (\\n appended). This is the mechanism a
                        walkthrough tool uses to send POS1/POS2/RESET_ERROR
                        without a tty.

Injecting a frame:

    python -c "import socket; socket.create_connection(('127.0.0.1',6002)).sendall(b'POS1\\n')"

Aliases understood by the control port (case-insensitive):
    pos1  ->  POS1
    pos2  ->  POS2
    pos3  ->  POS3
    reset / reset_error / err_reset  ->  RESET_ERROR
    anything else                    ->  sent as-is (uppercased),
                                         unless prefixed with 'raw ' (verbatim).

Modelled on Client_working_example/dummy_server.py but speaks our POS /
RESET_ERROR protocol.
"""
from __future__ import annotations

import argparse
import socket
import sys
import threading
from datetime import datetime

HOST_DEFAULT = "0.0.0.0"
BRIDGE_PORT_DEFAULT = 6001
CTRL_PORT_DEFAULT = 6002

ALIASES = {
    "pos1": "POS1",
    "pos2": "POS2",
    "pos3": "POS3",
    "reset": "RESET_ERROR",
    "reset_error": "RESET_ERROR",
    "err_reset": "RESET_ERROR",
}


def ts() -> str:
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


def _hex(data: bytes) -> str:
    return " ".join(f"{b:02X}" for b in data)


def resolve_frame(raw: str) -> str:
    s = raw.strip()
    if not s:
        return ""
    low = s.lower()
    if low.startswith("raw "):
        return s[4:]
    if low in ALIASES:
        return ALIASES[low]
    return s.upper()


class BridgeLink:
    """Holds the bridge's connected socket. Thread-safe send()."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sock: socket.socket | None = None
        self._peer: str = "—"

    def attach(self, sock: socket.socket, peer: str) -> None:
        with self._lock:
            self._sock = sock
            self._peer = peer

    def detach(self) -> None:
        with self._lock:
            self._sock = None
            self._peer = "—"

    def is_connected(self) -> bool:
        with self._lock:
            return self._sock is not None

    def peer(self) -> str:
        with self._lock:
            return self._peer

    def send(self, payload: bytes) -> tuple[bool, str]:
        with self._lock:
            if self._sock is None:
                return False, "no bridge connection"
            try:
                self._sock.sendall(payload)
                return True, ""
            except (ConnectionError, OSError) as e:
                return False, str(e)


def bridge_rx_loop(link: BridgeLink, conn: socket.socket, stop: threading.Event) -> None:
    """Print every inbound line from the bridge until it closes."""
    buf = b""
    while not stop.is_set():
        try:
            data = conn.recv(1024)
        except (ConnectionError, OSError):
            break
        if not data:
            break
        buf += data
        while b"\n" in buf:
            line, _, buf = buf.partition(b"\n")
            text = line.rstrip(b"\r").decode("ascii", errors="replace")
            if not text:
                continue
            print(f"[{ts()}] rx <- bridge: {text!r}   ({_hex(line)})", flush=True)
    if buf:
        text = buf.decode("ascii", errors="replace")
        print(f"[{ts()}] rx <- bridge (no LF): {text!r}   ({_hex(buf)})", flush=True)
    stop.set()


def bridge_accept_loop(link: BridgeLink, bridge_host: str, bridge_port: int) -> None:
    """Accept the bridge's TCP connection. Re-accepts on drop."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            srv.bind((bridge_host, bridge_port))
        except OSError as e:
            print(f"[{ts()}] bind {bridge_host}:{bridge_port} failed: {e}", file=sys.stderr, flush=True)
            return
        srv.listen(1)
        print(f"[{ts()}] robot-port listening on {bridge_host}:{bridge_port}", flush=True)

        while True:
            conn, addr = srv.accept()
            peer = f"{addr[0]}:{addr[1]}"
            print(f"[{ts()}] bridge connected from {peer}", flush=True)
            link.attach(conn, peer)
            stop = threading.Event()
            rx = threading.Thread(target=bridge_rx_loop, args=(link, conn, stop), daemon=True)
            rx.start()
            rx.join()
            link.detach()
            try:
                conn.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            conn.close()
            print(f"[{ts()}] bridge disconnected; re-accepting", flush=True)


def ctrl_serve_one(link: BridgeLink, conn: socket.socket, addr: tuple[str, int]) -> None:
    """Read one line from the control connection, forward as a frame."""
    peer = f"{addr[0]}:{addr[1]}"
    with conn:
        try:
            conn.settimeout(2.0)
            buf = b""
            while b"\n" not in buf:
                chunk = conn.recv(1024)
                if not chunk:
                    break
                buf += chunk
                if len(buf) > 4096:
                    break
        except (ConnectionError, OSError, socket.timeout):
            buf = b""
        if not buf:
            print(f"[{ts()}] ctrl from {peer}: empty payload", flush=True)
            return
        line = buf.split(b"\n", 1)[0].rstrip(b"\r").decode("ascii", errors="replace")
        frame = resolve_frame(line)
        if not frame:
            print(f"[{ts()}] ctrl from {peer}: nothing to send (input was empty)", flush=True)
            return
        if not link.is_connected():
            reply = f"NAK: bridge not connected (would have sent {frame!r})\n"
            try:
                conn.sendall(reply.encode("ascii"))
            except OSError:
                pass
            print(f"[{ts()}] ctrl from {peer}: {frame!r} REJECTED (bridge offline)", flush=True)
            return
        payload = (frame + "\n").encode("ascii", errors="replace")
        ok, err = link.send(payload)
        if ok:
            print(f"[{ts()}] tx -> bridge: {frame!r}   ({_hex(payload)})   [via ctrl {peer}]", flush=True)
            try:
                conn.sendall(f"OK: sent {frame!r}\n".encode("ascii"))
            except OSError:
                pass
        else:
            print(f"[{ts()}] tx -> bridge FAILED: {err}", flush=True)
            try:
                conn.sendall(f"NAK: send failed: {err}\n".encode("ascii"))
            except OSError:
                pass


def ctrl_accept_loop(link: BridgeLink, ctrl_host: str, ctrl_port: int) -> None:
    """Accept control-port connections and forward each one's line to the bridge."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            srv.bind((ctrl_host, ctrl_port))
        except OSError as e:
            print(f"[{ts()}] bind {ctrl_host}:{ctrl_port} failed: {e}", file=sys.stderr, flush=True)
            return
        srv.listen(4)
        print(f"[{ts()}] ctrl-port listening on {ctrl_host}:{ctrl_port} (frame injector)", flush=True)

        while True:
            conn, addr = srv.accept()
            ctrl_serve_one(link, conn, addr)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Robot-side sim server for the Flower bridge.")
    ap.add_argument("--host", default=HOST_DEFAULT, help=f"bind address (default {HOST_DEFAULT})")
    ap.add_argument("--port", type=int, default=BRIDGE_PORT_DEFAULT,
                    help=f"robot port the bridge dials (default {BRIDGE_PORT_DEFAULT})")
    ap.add_argument("--ctrl-port", type=int, default=CTRL_PORT_DEFAULT,
                    help=f"control port for frame injection (default {CTRL_PORT_DEFAULT})")
    args = ap.parse_args(argv)

    link = BridgeLink()
    bridge_thread = threading.Thread(
        target=bridge_accept_loop, args=(link, args.host, args.port), daemon=True
    )
    ctrl_thread = threading.Thread(
        target=ctrl_accept_loop, args=(link, args.host, args.ctrl_port), daemon=True
    )
    bridge_thread.start()
    ctrl_thread.start()

    print(f"[{ts()}] frame injector cmd: "
          f"python -c \"import socket; socket.create_connection(('127.0.0.1',{args.ctrl_port})).sendall(b'POS1\\n')\"",
          flush=True)
    print(f"[{ts()}] running. Ctrl-C to stop.", flush=True)

    try:
        while True:
            bridge_thread.join(timeout=1.0)
            ctrl_thread.join(timeout=1.0)
            if not bridge_thread.is_alive() and not ctrl_thread.is_alive():
                break
    except KeyboardInterrupt:
        print(f"\n[{ts()}] stopped by Ctrl-C", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
