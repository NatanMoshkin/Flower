"""One-shot ADS read: dump GVL_Log.nWriteIdx and the last N entries.

No dependency on RobotBridge / log_pump / csv_logger — pure pyads.

Usage:
    python dump_log_ring.py             # dumps last 20 entries
    python dump_log_ring.py --tail 50   # dumps last 50 entries
"""
from __future__ import annotations

import argparse
import sys

import pyads

AMS_NET_ID = "127.0.0.1.1.1"
AMS_PORT = 851
RING_SIZE = 256

SEV_LABEL = {0: "DBG", 1: "INFO", 2: "WARN", 3: "ERR"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tail", type=int, default=20,
                    help="How many recent entries to dump (default 20)")
    args = ap.parse_args()

    plc = pyads.Connection(AMS_NET_ID, AMS_PORT)
    plc.open()
    try:
        write_idx = plc.read_by_name("GVL_Log.nWriteIdx", pyads.PLCTYPE_UDINT)
        debug_mode = plc.read_by_name("GVL_Log.bDebugMode", pyads.PLCTYPE_BOOL)
        print(f"GVL_Log.nWriteIdx = {write_idx}")
        print(f"GVL_Log.bDebugMode = {debug_mode}")

        if write_idx == 0:
            print("Ring is empty (no entries written yet).")
            return 0

        n = min(args.tail, RING_SIZE, write_idx)
        start = max(0, write_idx - n)
        print(f"\nLast {n} entries (idx {start} .. {write_idx - 1}):")
        print(f"{'idx':>6}  {'slot':>4}  {'sev':<4}  {'source':<20}  msg")
        print("-" * 100)
        for idx in range(start, write_idx):
            slot = idx % RING_SIZE
            sev = plc.read_by_name(f"GVL_Log.aLog[{slot}].eSev", pyads.PLCTYPE_UINT)
            source = plc.read_by_name(f"GVL_Log.aLog[{slot}].sSource", pyads.PLCTYPE_STRING)
            msg = plc.read_by_name(f"GVL_Log.aLog[{slot}].sMsg", pyads.PLCTYPE_STRING)
            print(f"{idx:>6}  {slot:>4}  {SEV_LABEL.get(sev, '???'):<4}  {source:<20}  {msg}")
    finally:
        plc.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
