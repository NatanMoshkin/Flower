# python
# Dummy TCP server that emulates the Dobot Lua server (src2.lua).
# Use it to test "tcp client.py" without the robot.
# Protocol (mirrors handle_tcp() in src2.lua):
#   "GET_SYNC"    -> "SYNC:J_SPEED=..,L_SPEED=..,REPEATS=..,..."
#   "HEARTBEAT"   -> "1"
#   "NAME:VALUE"  -> stores the value, replies "OK: SET NAME"
# Variables persist across client reconnects (like Lua globals).

import socket

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