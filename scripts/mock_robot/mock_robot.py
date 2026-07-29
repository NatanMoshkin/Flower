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
import socket
import threading

HOST = "0.0.0.0"   # same as ip in global.lua
PORT = 6001        # same as port in global.lua

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


def serve_client(conn, addr):
    global last_state

    last_state = None   # so the first STATE of a new session always prints
    print(f"New Client Connected Successfully: {addr[0]}:{addr[1]}")
    with conn:
        while True:
            try:
                data = conn.recv(1024)
            except ConnectionError:
                break
            if not data:
                break
            msg = data.decode("utf-8").strip()
            reply = handle_message(msg)
            if reply is not None:
                conn.sendall(reply.encode("utf-8"))
    print("Connection Lost - waiting for new client...")


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
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((HOST, PORT))
        server.listen(1)  # Lua server handles one client at a time
        print(f"Dummy Dobot server listening on {HOST}:{PORT}")
        while True:
            conn, addr = server.accept()
            serve_client(conn, addr)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nServer stopped.")