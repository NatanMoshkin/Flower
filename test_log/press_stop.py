"""Poke bStop via ADS — no-op in IDLE for the state machine, but still logs.

The STOP override in FB_MasterAutoCycle.TcPOU section 2 only fires when
eStep is NOT IDLE and NOT ERR, so poking bStop in IDLE produces exactly
one "STOP pressed" INFO log entry with no state change.
"""
from __future__ import annotations

import time

import pyads

plc = pyads.Connection("127.0.0.1.1.1", 851)
plc.open()
try:
    before = plc.read_by_name("GVL_Log.nWriteIdx", pyads.PLCTYPE_UDINT)
    plc.write_by_name("GVL_HMI.stMasterAuto.bStop", True, pyads.PLCTYPE_BOOL)
    time.sleep(0.100)
    after = plc.read_by_name("GVL_Log.nWriteIdx", pyads.PLCTYPE_UDINT)
    print(f"nWriteIdx: {before} -> {after}  (delta {after - before})")
finally:
    plc.close()
