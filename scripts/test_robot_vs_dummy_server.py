"""Drive scripts/dummy_server_state_cmd.py over a real socket, emulating
FB_RobotTcpClient frame-for-frame.

Where test_param_shadow_logic.py tests the sequencer in isolation, this one
puts the real dummy server on the other end of a real TCP connection and
replays exactly what the FB would put on the wire -- including the new
shadow-copy parameter push. It proves the two ends agree on framing and
semantics before any TwinCAT runtime is involved.

Run:  python scripts/test_robot_vs_dummy_server.py
"""

from __future__ import annotations

import os
import pathlib
import socket
import subprocess
import threading
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
SERVER = HERE / "dummy_server_state_cmd.py"
# Not 6001: that is the real robot port and may already be held by an
# interactive dummy server. On Windows SO_REUSEADDR lets a second bind
# succeed, after which connections land on whichever socket wins the race.
HOST, PORT = "127.0.0.1", 16001

SYNC_ORDER = [
    "J_SPEED", "L_SPEED", "REPEATS", "START_WAIT", "WATER_WAIT",
    "STAND_WAIT", "END_WAIT", "WATER_SPEED",
    "WAX_WAIT_TIME_IN", "WAX_WAIT_TIME_OUT", "WAX_SPEED",
]

results = []


def check(label, cond, detail=""):
    results.append((label, bool(cond), detail))
    print(f"{'PASS' if cond else 'FAIL'}  {label}" + (f"\n      {detail}" if not cond else ""))


class Wire:
    """One send -> one reply, raw ASCII, no newline framing (as the FB does)."""

    def __init__(self, sock):
        self.s = sock
        self.sent = []

    def tx(self, msg):
        self.sent.append(msg)
        self.s.sendall(msg.encode("ascii"))
        return self.s.recv(1024).decode("ascii", "replace").strip("\x00").strip()


def wait_for_banner(proc, lines, timeout=15.0):
    """Wait for the server's 'listening' line.

    Deliberately does NOT probe with a throwaway connection: the server is
    single-threaded with listen(1), so a probe occupies the accept slot and
    the next connect gets refused. The FB likewise opens exactly one socket.
    """
    threading.Thread(
        target=lambda: [lines.append(l) for l in iter(proc.stdout.readline, "")],
        daemon=True,
    ).start()
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            return False
        if any("listening on" in l for l in list(lines)):
            return True
        time.sleep(0.1)
    return False


def main():
    if not SERVER.exists():
        print(f"missing {SERVER}")
        return 1

    proc = subprocess.Popen(
        # -u: stdout is a pipe here, so without it the banner sits in the
        # block buffer and we would time out waiting for a line that was
        # already written.
        [sys.executable, "-u", str(SERVER)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        env={**os.environ, "DUMMY_PORT": str(PORT)},
    )
    try:
        srv_out: list[str] = []
        if not wait_for_banner(proc, srv_out):
            print("server did not come up:\n" + "".join(srv_out))
            return 1

        with socket.create_connection((HOST, PORT), timeout=3) as sock:
            sock.settimeout(3)
            w = Wire(sock)

            # 1. Post-connect one-shot GET_SYNC (must precede any STATE push).
            sync = w.tx("GET_SYNC")
            check("GET_SYNC returns a SYNC frame", sync.startswith("SYNC:"), sync)
            params = {}
            for tok in sync[5:].split(","):
                k, _, v = tok.partition("=")
                params[k] = int(v)
            check("SYNC carries all 11 params in order",
                  list(params) == SYNC_ORDER, f"got {list(params)}")

            # 2. Initial STATE push -> CMD reply.
            r = w.tx("STATE:0")
            check("STATE:0 answered with a CMD frame", r.startswith("CMD:"), r)

            # 3. Shadow-copy param push: exactly what the FB emits when the
            #    operator edits stParams.J_SPEED to 15.
            r = w.tx("J_SPEED:15")
            check("J_SPEED:15 acknowledged", r == "OK: SET J_SPEED", r)
            check("robot applied the new speed",
                  int(dict(t.split("=") for t in w.tx("GET_SYNC")[5:].split(","))["J_SPEED"]) == 15)

            # 4. The other two speed params.
            for name, val in (("WATER_SPEED", 22), ("WAX_SPEED", 23)):
                r = w.tx(f"{name}:{val}")
                check(f"{name}:{val} acknowledged", r == f"OK: SET {name}", r)
            after = dict(t.split("=") for t in w.tx("GET_SYNC")[5:].split(","))
            check("all three speeds persisted on the robot",
                  (int(after["J_SPEED"]), int(after["WATER_SPEED"]), int(after["WAX_SPEED"]))
                  == (15, 22, 23), str(after))

            # 5. Keep-alive STATE frames through the master cycle steps.
            for n in (10, 11, 12, 20, 21, 1, 3, 4, 5, 6, 7, 8, 22, 0):
                r = w.tx(f"STATE:{n}")
                if not r.startswith("CMD:"):
                    check(f"STATE:{n} answered with CMD", False, r)
                    break
            else:
                check("every master-cycle STATE value answered with CMD", True)

            # 6. MANUAL sentinel.
            check("STATE:30 (MANUAL) accepted", w.tx("STATE:30").startswith("CMD:"))

            # 7. New_Bulb trigger.
            r = w.tx("New_Bulb:1")
            check("New_Bulb:1 acknowledged", r == "OK: SET New_Bulb", r)

            # 8. CMD values stay in the contract range {0,1,2}.
            codes = set()
            for _ in range(5):
                codes.add(int(w.tx("STATE:0")[4:]))
            check("CMD codes stay within {0,1,2}", codes <= {0, 1, 2}, str(codes))

    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()

    failed = [r for r in results if not r[1]]
    print()
    print(f"{len(results) - len(failed)}/{len(results)} passed"
          + ("" if not failed else f" -- {len(failed)} FAILED"))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
