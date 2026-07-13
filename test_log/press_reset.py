"""Safely poke the MasterAuto RESET button via ADS to trigger a log emit.

RESET in a non-ERR state is a no-op for the state machine but still fires
the R_TRIG-guarded log call in section 0b. So this is a safe way to prove
the log ring is being written without touching pistons.
"""
from __future__ import annotations

import time

import pyads

AMS_NET_ID = "127.0.0.1.1.1"
AMS_PORT = 851

SYMBOL = "GVL_HMI.stMasterAuto.bReset"


def main() -> None:
    plc = pyads.Connection(AMS_NET_ID, AMS_PORT)
    plc.open()
    try:
        before = plc.read_by_name("GVL_Log.nWriteIdx", pyads.PLCTYPE_UDINT)
        print(f"nWriteIdx before RESET poke: {before}")

        plc.write_by_name(SYMBOL, True, pyads.PLCTYPE_BOOL)
        # PlcTask is 10 ms — wait a few cycles for R_TRIG to see the edge
        # and the FB to auto-clear the flag.
        time.sleep(0.100)

        cleared = plc.read_by_name(SYMBOL, pyads.PLCTYPE_BOOL)
        after = plc.read_by_name("GVL_Log.nWriteIdx", pyads.PLCTYPE_UDINT)
        print(f"bReset auto-cleared: {not cleared}")
        print(f"nWriteIdx after RESET poke: {after}")
        print(f"Delta: {after - before}  (expect 1 log entry per edge)")
    finally:
        plc.close()


if __name__ == "__main__":
    main()
