"""Dummy Dobot server for the STATE/CMD protocol.

Extends the reference at RobotBridge/Client_working_example/dummy_server.py
with the STATE:<n> / CMD:<m> frames added on 2026-07-26. Backward-compatible
with the old GET_SYNC / NAME:VALUE / New_Bulb frames so tuning-parameter
traffic keeps working during bring-up.

Run on the dev PC that the CP6606 dials:
    python dummy_server_state_cmd.py

Terminal keys (while running):
    1  -> queue CMD:1 (start cycle) on the NEXT STATE reply
    2  -> queue CMD:2 (reset error) on the NEXT STATE reply
    0  -> force CMD:0 explicitly (default)
    q  -> quit

The queued CMD auto-clears after one send, mimicking the real robot's
contract ("PLC's next STATE frame acknowledges the previous CMD, robot
then zeros its command").
"""

import os
import socket
import sys
import threading

HOST = "0.0.0.0"
# 6001 is the real robot port and the interactive default. Override with
# DUMMY_PORT so automated tests can run without fighting another server
# already bound to 6001 (Windows SO_REUSEADDR lets a second bind succeed and
# then silently steals connections).
PORT = int(os.environ.get("DUMMY_PORT", "6001"))

# Tuning parameters (kept warm across reconnects, mirrors real Lua state).
STATE_PARAMS = {
    "J_SPEED": 10,
    "L_SPEED": 10,
    "REPEATS": 2,
    "START_WAIT": 500,
    "WATER_WAIT": 500,
    "STAND_WAIT": 2000,
    "END_WAIT": 500,
    "WATER_SPEED": 10,
    "WAX_WAIT_TIME_IN": 500,
    "WAX_WAIT_TIME_OUT": 500,
    "WAX_SPEED": 10,
}

SYNC_ORDER = [
    "J_SPEED", "L_SPEED", "REPEATS", "START_WAIT", "WATER_WAIT",
    "STAND_WAIT", "END_WAIT", "WATER_SPEED",
    "WAX_WAIT_TIME_IN", "WAX_WAIT_TIME_OUT", "WAX_SPEED",
]

# E_MasterAutoStep INT -> name (mirrors the enum on the PLC side).
STEP_NAMES = {
    0:  "IDLE",
    1:  "SEP_EXTENDING",
    2:  "WAIT_POS2 (retired)",
    3:  "PUSH_EXTENDING",
    4:  "DWELL_PUSH",
    5:  "PUSH_RETRACTING",
    6:  "PUSH_RETRACTED_DWELL",
    7:  "SEP_RETRACTING",
    8:  "SEP_RETRACTED_DWELL",
    10: "INIT_PUSH_RETRACTING",
    11: "INIT_SEP_RETRACTING",
    12: "INIT_GRIP_RETRACTING",
    20: "WAIT_PLATE",
    21: "GRIP_EXTENDING",
    22: "GRIP_RETRACTING",
    30: "MANUAL",
    99: "ERR",
}

# Shared, mutable — one queued command reads back on the next STATE reply,
# then resets to 0.  Guarded by a lock because stdin runs on a side thread.
_lock = threading.Lock()
_pending_cmd = 0
_last_state = None
_new_bulb = False


def _stdin_thread():
    """Read single-char commands from stdin, update _pending_cmd."""
    global _pending_cmd
    print("[input] type 1 / 2 / 0 / q  (Enter to submit)")
    for line in sys.stdin:
        c = line.strip()
        if c == "q":
            print("[input] quit requested")
            # ungraceful — main loop is blocked on accept/recv, so just exit
            # after the current client disconnects.
            import os
            os._exit(0)
        if c in ("0", "1", "2"):
            with _lock:
                _pending_cmd = int(c)
            print(f"[input] queued CMD:{c} for next STATE reply")
        else:
            print(f"[input] ignored {c!r} (expected 0/1/2/q)")


def _build_sync():
    return "SYNC:" + ",".join(f"{k}={STATE_PARAMS[k]}" for k in SYNC_ORDER)


def _handle_state(msg):
    """PLC sent 'STATE:<n>'. Log it and return 'CMD:<m>'."""
    global _pending_cmd, _last_state
    try:
        n = int(msg.split(":", 1)[1])
    except (IndexError, ValueError):
        print(f"[state] malformed: {msg!r}")
        return "CMD:0"

    if n != _last_state:
        step = STEP_NAMES.get(n, f"?({n})")
        print(f"[state] {n:>3}  {step}")
        _last_state = n

    with _lock:
        m = _pending_cmd
        _pending_cmd = 0
    if m != 0:
        print(f"[cmd]   -> CMD:{m}  (auto-cleared)")
    return f"CMD:{m}"


def _handle_message(msg):
    global _new_bulb

    if msg.startswith("STATE:"):
        return _handle_state(msg)

    if msg == "GET_SYNC":
        reply = _build_sync()
        print(f"[sync]  sent {len(reply)} chars")
        return reply

    # NAME:VALUE tuning setter -- keeps the old shape.
    if ":" in msg:
        name, _, raw = msg.partition(":")
        try:
            value = int(raw)
        except ValueError:
            value = None

        if name == "New_Bulb":
            _new_bulb = True
            print("[bulb]  New_Bulb ON")
        elif name in STATE_PARAMS and value is not None:
            STATE_PARAMS[name] = value
            print(f"[set]   {name} = {value}")
        else:
            print(f"[set]   unknown/invalid: {msg!r}")
        return f"OK: SET {name}"

    print(f"[??]    unhandled: {msg!r}")
    return None


def _serve(conn, addr):
    print(f"[conn]  {addr[0]}:{addr[1]} connected")
    with conn:
        while True:
            try:
                data = conn.recv(1024)
            except ConnectionError:
                break
            if not data:
                break
            msg = data.decode("utf-8").strip()
            reply = _handle_message(msg)
            if reply is not None:
                conn.sendall(reply.encode("utf-8"))
    print(f"[conn]  {addr[0]}:{addr[1]} disconnected")


def main():
    threading.Thread(target=_stdin_thread, daemon=True).start()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((HOST, PORT))
        srv.listen(1)
        print(f"Dummy Dobot server (STATE/CMD) listening on {HOST}:{PORT}")
        while True:
            conn, addr = srv.accept()
            _serve(conn, addr)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nServer stopped.")
