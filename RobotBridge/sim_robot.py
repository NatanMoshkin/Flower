"""Simulate the robot: TCP client that sends POSn frames to the bridge.

Used for smoke-testing the whole path — robot -> bridge -> PLC -> HMI —
without needing a real robot on the LAN. Assumes the bridge is running
in server mode on the target host:port.

Usage:
    python sim_robot.py                        # 127.0.0.1:2000, full script
    python sim_robot.py POS1                   # single frame
    python sim_robot.py POS1 POS2              # a sequence
    python sim_robot.py --host 192.168.1.10    # remote bridge
    python sim_robot.py --port 2000 POS3
    python sim_robot.py --gap 0.5              # 500 ms between frames

Between each send, sleeps `--gap` seconds so a human watching the HMI
has time to react. Default script is POS1, POS2, POS3, FOO (unknown).
"""
from __future__ import annotations

import argparse
import socket
import sys
import time


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Send simulated robot POS frames to the bridge")
    parser.add_argument("--host", default="127.0.0.1", help="bridge host (default 127.0.0.1)")
    parser.add_argument("--port", type=int, default=2000, help="bridge port (default 2000)")
    parser.add_argument("--gap", type=float, default=1.0, help="seconds between frames (default 1.0)")
    parser.add_argument(
        "frames",
        nargs="*",
        help="frames to send. Default script: POS1 POS2 POS3 FOO",
    )
    args = parser.parse_args(argv)

    frames = args.frames or ["POS1", "POS2", "POS3", "FOO"]

    print(f"connecting to {args.host}:{args.port}", flush=True)
    with socket.create_connection((args.host, args.port)) as s:
        print("connected", flush=True)
        for i, frame in enumerate(frames):
            payload = (frame + "\n").encode("ascii")
            s.sendall(payload)
            print(f"  sent [{i+1}/{len(frames)}]: {frame}", flush=True)
            if i < len(frames) - 1:
                time.sleep(args.gap)
        print("closing", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
