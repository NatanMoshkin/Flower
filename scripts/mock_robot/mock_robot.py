# python
# Dummy TCP server that emulates the Dobot Lua server (src2.lua).
# Use it to test "tcp client.py" without the robot.
# Protocol (mirrors handle_tcp() in src2.lua):
#   "GET_SYNC"    -> "SYNC:J_SPEED=..,L_SPEED=..,REPEATS=..,..."
#   "HEARTBEAT"   -> "1"
#   "STATE:<n>"   -> "CMD:<m>"   <-- the PLC's state push; see decide_cmd()
#   "NAME:VALUE"  -> stores the value, replies "OK: SET NAME"
# Variables persist across client reconnects (like Lua globals).
#
# STATE/CMD is the channel the PLC runs its whole handshake over, and it was
# MISSING here (and in the committed src2.lua). Because "STATE:0" contains a
# colon it fell through to the generic NAME:VALUE branch and was answered
# "OK: SET STATE", which the PLC discards -- so nRobotCmd never left 0 and no
# cycle could ever start, while the link looked perfectly healthy: connected,
# both packet counters climbing. That is why the STATE test below MUST come
# before the colon branch.
#
# Usage:
#   python dummy_server.py             # auto: request a bulb whenever PLC is IDLE
#   python dummy_server.py --manual    # press Enter to request one bulb
#   python dummy_server.py --no-bulbs  # never request; just watch the states

import argparse
import select
import socket
import threading
import time

HOST = "0.0.0.0"   # same as ip in global.lua
PORT = 6001        # same as port in global.lua

# Drop a client that has gone quiet for this long. The PLC pushes STATE every
# ~1 s, so 5 s of silence means it is gone, not merely idle.
#
# Backstop rather than the main defence: serve_forever() also watches the
# listening socket, so a reconnecting PLC pre-empts a stale socket at once
# instead of waiting this out. See serve_forever's docstring for the bench
# failure that motivated both.
CLIENT_IDLE_TIMEOUT = 5.0

# Robot parameters with reasonable defaults (kept while server runs)
STATE = {
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

new_bulb = False

# --------------------------------------------------------------- STATE / CMD
# E_MasterAutoStep values the PLC pushes as "STATE:<n>". Only three matter to
# us; the rest are decoded purely so the console output is readable.
STEP_NAMES = {
    0: "IDLE", 1: "SEP_EXTENDING", 3: "PUSH_EXTENDING", 4: "DWELL_PUSH",
    5: "PUSH_RETRACTING", 6: "PUSH_RETRACTED_DWELL", 7: "SEP_RETRACTING",
    8: "SEP_RETRACTED_DWELL", 10: "INIT_PUSH_RETRACTING",
    11: "INIT_SEP_RETRACTING", 12: "INIT_GRIP_RETRACTING", 20: "WAIT_PLATE",
    21: "GRIP_EXTENDING", 22: "GRIP_RETRACTING", 30: "MANUAL",
    40: "NOT_HOMED", 99: "ERR",
}

STATE_IDLE = 0
STATE_ERR = 99

CMD_NONE, CMD_START, CMD_RESET = 0, 1, 2

# Set by --manual / --no-bulbs. "auto" keeps the machine producing back to back,
# which is what you want when walking the sequence through the panel Logs page.
bulb_mode = "auto"        # auto | manual | none
wants_bulb = True         # in manual mode, armed by pressing Enter
last_state = None         # for change-only printing


def decide_cmd(state):
    """The contract the real src2.lua must implement too.

        STATE:0  (IDLE)  -> CMD:1 when we want a bulb, else CMD:0
        STATE:99 (ERR)   -> CMD:2, reset it; the PLC then homes itself and
                            comes back as IDLE on its own
        anything else    -> CMD:0, wait

    NOT_HOMED (40) and MANUAL (30) deliberately need no branch of their own --
    they land in the final "wait", which is exactly right: the panel is telling
    us it is not armed, and only an operator can change that.
    """
    global wants_bulb

    if state == STATE_ERR:
        return CMD_RESET

    if state == STATE_IDLE and bulb_mode != "none" and wants_bulb:
        if bulb_mode == "manual":
            wants_bulb = False          # one bulb per Enter
        return CMD_START

    return CMD_NONE


def handle_state(raw):
    """Reply to a "STATE:<n>" push with "CMD:<m>"."""
    global last_state

    try:
        state = int(raw)
    except ValueError:
        print(f"[STATE] unparsable: {raw!r}")
        return f"CMD:{CMD_NONE}"

    cmd = decide_cmd(state)

    # Print on change, and always when we are actually commanding something.
    # The PLC pushes STATE at 1 Hz forever; echoing every keep-alive would bury
    # the interesting lines. Mirrors the FB's own logging policy.
    if state != last_state or cmd != CMD_NONE:
        name = STEP_NAMES.get(state, "?")
        note = {CMD_START: "  -> CMD:1 start cycle",
                CMD_RESET: "  -> CMD:2 reset error"}.get(cmd, "")
        print(f"[STATE] {state:<3} {name}{note}")
    last_state = state

    return f"CMD:{cmd}"


KNOWN_TAGS = ("STATE:", "GET_SYNC", "HEARTBEAT", "New_Bulb:")


def split_frames(raw):
    """Split a read that may hold several concatenated frames.

    The protocol has no delimiter -- one send, one reply -- so normally a recv
    holds exactly one frame. But if the PLC ever gets a frame ahead (or TCP
    coalesces two writes) a naive parse sees 'STATE:0STATE:10' and answers
    nothing useful. Cut at the start of each known tag; anything without a tag is
    returned whole so NAME:VALUE writes still work.
    """
    raw = raw.strip()
    if not raw:
        return []

    cuts = []
    for tag in KNOWN_TAGS:
        start = 0
        while True:
            i = raw.find(tag, start)
            if i < 0:
                break
            cuts.append(i)
            start = i + 1

    if not cuts:
        return [raw]

    cuts = sorted(set(cuts + [len(raw)]))
    if cuts[0] != 0:
        cuts.insert(0, 0)
    out = []
    for a, b in zip(cuts, cuts[1:]):
        piece = raw[a:b].strip()
        if piece:
            out.append(piece)
    return out


def bulb_prompt():
    """--manual: each Enter arms exactly one bulb."""
    global wants_bulb
    while True:
        try:
            input()
        except (EOFError, KeyboardInterrupt):
            return
        wants_bulb = True
        print("[BULB ] armed - will send CMD:1 at the next IDLE")


# Same field order as the string.format in src2.lua
SYNC_ORDER = [
    "J_SPEED", "L_SPEED", "REPEATS", "START_WAIT", "WATER_WAIT",
    "STAND_WAIT", "END_WAIT", "WATER_SPEED",
    "WAX_WAIT_TIME_IN", "WAX_WAIT_TIME_OUT", "WAX_SPEED",
]


def build_sync():
    return "SYNC:" + ",".join(f"{k}={STATE[k]}" for k in SYNC_ORDER)


def handle_message(msg):
    """Return the reply for one message, mimicking the Lua logic."""
    global new_bulb

    if msg == "GET_SYNC":
        print("[SYNC] sent:", build_sync())
        return build_sync()

    if msg == "HEARTBEAT":
        return "1"

    # STATE push -- MUST be tested before the generic ":" branch below, which
    # would otherwise treat "STATE:0" as a parameter write and answer
    # "OK: SET STATE". That fall-through is the bug this file used to have.
    if msg.startswith("STATE:"):
        return handle_state(msg[len("STATE:"):])

    # NAME:VALUE set command
    if ":" in msg:
        name, _, raw_val = msg.partition(":")
        try:
            value = int(raw_val)
        except ValueError:
            value = None

        if name == "New_Bulb":
            new_bulb = True
            print("[SET] New_Bulb -> ON")
        elif name in STATE and value is not None:
            STATE[name] = value
            print(f"[SET] {name} = {value}")
        else:
            print(f"[SET] unknown/invalid: {msg!r}")

        # Lua replies OK even for unknown names
        return "OK: SET " + name

    print(f"[??] unhandled message: {msg!r}")
    return None


def accept_client(server):
    """Accept and configure one client socket."""
    global last_state

    conn, addr = server.accept()
    last_state = None   # so the first STATE of a new session always prints
    # Small request/reply frames: don't let Nagle sit on a 5-byte "CMD:1".
    try:
        conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    except OSError:
        pass
    print(f"New Client Connected Successfully: {addr[0]}:{addr[1]}")
    return conn


def pump(conn):
    """Read whatever is ready and answer it. False => the client is finished."""
    try:
        data = conn.recv(1024)
    except (ConnectionError, OSError):
        return False
    if not data:
        return False

    # One recv can carry more than one frame: the protocol has no delimiter, so
    # if the PLC gets a frame ahead the read holds e.g. 'STATE:0STATE:10'.
    for msg in split_frames(data.decode("utf-8", "replace")):
        reply = handle_message(msg)
        if reply is not None:
            try:
                conn.sendall(reply.encode("utf-8"))
            except (ConnectionError, OSError):
                return False
    return True


def serve_forever(server):
    """Single-client service loop, but watching the LISTENING socket too.

    The Lua server handles one client at a time and so do we -- but we cannot
    just block in recv() on that client, because the PLC opens its next socket
    BEFORE the old one is gone. Observed on the bench: two simultaneous
    ESTABLISHED connections from the panel, one of them accepted and dead, the
    other stuck unaccepted in the listen backlog. The kernel completes its
    handshake, so the PLC believes it is connected, while nothing here ever
    reads it -- one 'New Client Connected' line and then total silence, with the
    panel never getting past Connecting.

    So: select on the listener as well. A new connection pre-empts the old one
    immediately, and a client that simply goes quiet is dropped after
    CLIENT_IDLE_TIMEOUT (the PLC pushes STATE at 1 Hz, so silence means gone).
    """
    conn = None
    last_rx = 0.0

    while True:
        watch = [server] + ([conn] if conn is not None else [])
        try:
            ready, _, _ = select.select(watch, [], [], 1.0)
        except OSError:
            ready = []

        for sock in ready:
            if sock is server:
                new = accept_client(server)
                if conn is not None:
                    print("  (a new connection arrived while one was open - "
                          "dropping the stale one)")
                    conn.close()
                conn, last_rx = new, time.monotonic()
            else:
                if pump(conn):
                    last_rx = time.monotonic()
                else:
                    conn.close()
                    conn = None
                    print("Connection Lost - waiting for new client...")

        if conn is not None and time.monotonic() - last_rx > CLIENT_IDLE_TIMEOUT:
            conn.close()
            conn = None
            print(f"No data for {CLIENT_IDLE_TIMEOUT:.0f}s - dropping client, "
                  "waiting for a new one")


def main():
    global bulb_mode, wants_bulb

    ap = argparse.ArgumentParser(description="Dummy Dobot server (STATE/CMD capable)")
    group = ap.add_mutually_exclusive_group()
    group.add_argument("--manual", action="store_true",
                      help="press Enter to request one bulb")
    group.add_argument("--no-bulbs", action="store_true",
                      help="never request a bulb; just watch the state pushes")
    args = ap.parse_args()

    if args.manual:
        bulb_mode, wants_bulb = "manual", False
        threading.Thread(target=bulb_prompt, daemon=True).start()
        print("Mode: MANUAL - press Enter to request a bulb")
    elif args.no_bulbs:
        bulb_mode, wants_bulb = "none", False
        print("Mode: NO-BULBS - watching state pushes only")
    else:
        print("Mode: AUTO - a bulb is requested on every IDLE")

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        # Deliberately NOT SO_REUSEADDR on Windows, where it lets a SECOND
        # instance bind a port that is already listening. Both then appear to
        # start fine and incoming connections land on one of them arbitrarily --
        # so you watch one terminal while the panel talks to the other, and the
        # mock looks broken. SO_EXCLUSIVEADDRUSE makes the second instance fail
        # loudly instead. On POSIX, SO_REUSEADDR is safe and avoids TIME_WAIT
        # blocking a quick restart.
        try:
            if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                server.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            else:
                server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        except OSError:
            pass

        try:
            server.bind((HOST, PORT))
        except OSError as exc:
            print(f"Cannot listen on {HOST}:{PORT} -- {exc}")
            print("Something already holds that port. Close the other "
                  "mock_robot.py (check every open terminal) and retry.")
            print("  Windows:  Get-NetTCPConnection -LocalPort 6001")
            return 1
        server.listen(1)  # Lua server handles one client at a time
        print(f"Dummy Dobot server listening on {HOST}:{PORT}")
        serve_forever(server)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nServer stopped.")