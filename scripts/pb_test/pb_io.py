"""ADS plumbing for the panel push-button test procedure.

Channel maps come from docs/167_01_SAAD_PinPush_IO_List.xlsx (sheet IO,
column NEW) -- the as-rewired field assignment -- and must agree with
PRG_IoMap. They are NOT the pre-rewire numbering still visible in that
sheet's GVL_IO..[] column.

Why the test drives GVL_IO.dIn[] and not GVL_App.bPbN: PRG_IoMap.ReadInputs
runs on the 5 ms IOmapTask and copies dIn -> GVL_App every cycle, so a write
to GVL_App.bPb3 is overwritten before MAIN ever sees it. Writing the raw
channel is the only way to simulate a press, and it works here because the
EtherCAT device is Disabled in the local bench .tsproj, so nothing else
drives that memory.
"""

import re
import time

import pyads

BOOL, INT, UDINT, STRING = (
    pyads.PLCTYPE_BOOL, pyads.PLCTYPE_INT, pyads.PLCTYPE_UDINT, pyads.PLCTYPE_STRING,
)

# --- push buttons: DI channel and the LED it drives ------------------------
PB_DI = {1: 13, 2: 14, 3: 15}
PB_LED_DO = {1: 7, 2: 8, 3: 9}

# --- piston end-position sensors: (retracted DI, extended DI) --------------
SENSOR_DI = {
    "Sep1": (3, 4),    "Sep2": (7, 8),    "Sep3": (11, 12),
    "Push1": (1, 2),   "Push2": (5, 6),   "Push3": (9, 10),
    "GripL": (17, 18), "GripR": (19, 20),
}

# --- solenoid coils: DO channel -------------------------------------------
COIL_DO = {
    "Sep1": 4, "Sep2": 5, "Sep3": 6,
    "Push1": 1, "Push2": 2, "Push3": 3,
    "GripL": 10, "GripR": 11,
}

# Which coils each push button jogs, per the PB table in CLAUDE.md.
PB_JOG_GROUP = {
    1: ["GripL", "GripR"],
    2: ["Sep1", "Sep2", "Sep3"],
    3: ["Push1", "Push2", "Push3"],
}

# NOTE the L/R here follows PRG_IoMap, which is the OPPOSITE of the IO list
# (the sheet puts PlateSensR on 21). Invisible while bPlateOk is an OR.
PLATE_DI = {"L": 21, "R": 22}

DO_GREEN, DO_RED = 12, 13

STEP_NAMES = {
    0: "IDLE", 1: "SEP_EXTENDING", 3: "PUSH_EXTENDING", 4: "DWELL_PUSH",
    5: "PUSH_RETRACTING", 6: "PUSH_RETRACTED_DWELL", 7: "SEP_RETRACTING",
    8: "SEP_RETRACTED_DWELL", 10: "INIT_PUSH_RETRACTING",
    11: "INIT_SEP_RETRACTING", 12: "INIT_GRIP_RETRACTING", 20: "WAIT_PLATE",
    21: "GRIP_EXTENDING", 22: "GRIP_RETRACTING", 30: "MANUAL",
    40: "NOT_HOMED", 99: "ERR",
}

# One PlcTask cycle is 10 ms and IOmapTask is 5 ms. A simulated press has to
# travel dIn -> (IOmapTask) -> GVL_App -> (MAIN) -> GVL_App.bLed -> (IOmapTask)
# -> dOut, so ~30 ms worst case. 150 ms is generous and keeps the run quick.
SETTLE = 0.15


class Plc:
    """Thin pyads wrapper with the read/write helpers this procedure needs."""

    def __init__(self, net_id="127.0.0.1.1.1", port=851):
        self.c = pyads.Connection(net_id, port)
        self._saved = {}

    def __enter__(self):
        self.c.open()
        state, _ = self.c.read_state()
        if state != 5:
            raise RuntimeError(f"PLC is not in RUN (ADS state {state})")
        return self

    def __exit__(self, *exc):
        self.c.close()
        return False

    # -- raw ---------------------------------------------------------------
    def r(self, sym, t=BOOL):
        return self.c.read_by_name(sym, t)

    def w(self, sym, val, t=BOOL):
        self.c.write_by_name(sym, val, t)

    # -- save / restore ----------------------------------------------------
    def save(self, sym, t=BOOL):
        """Snapshot a symbol so restore() can put it back. Live PLC: every
        field this procedure writes must be registered here first."""
        if sym not in self._saved:
            self._saved[sym] = (self.r(sym, t), t)
        return self._saved[sym][0]

    def restore(self):
        for sym, (val, t) in self._saved.items():
            try:
                self.w(sym, val, t)
            except Exception as e:                    # noqa: BLE001
                print(f"  !! could not restore {sym}: {e}")

    # -- push buttons ------------------------------------------------------
    def press(self, pb, settle=SETTLE):
        self.w(f"GVL_IO.dIn[{PB_DI[pb]}]", True)
        time.sleep(settle)

    def release(self, pb, settle=SETTLE):
        self.w(f"GVL_IO.dIn[{PB_DI[pb]}]", False)
        time.sleep(settle)

    def release_all_pbs(self):
        for pb in PB_DI:
            self.w(f"GVL_IO.dIn[{PB_DI[pb]}]", False)
        time.sleep(SETTLE)

    def led(self, pb):
        return self.r(f"GVL_IO.dOut[{PB_LED_DO[pb]}]")

    # -- pistons -----------------------------------------------------------
    def coil(self, name):
        return self.r(f"GVL_IO.dOut[{COIL_DO[name]}]")

    def coils(self, names):
        return {n: self.coil(n) for n in names}

    def all_coils(self):
        return {n: self.coil(n) for n in COIL_DO}

    def park_all_home(self):
        """Assert every 'retracted' sensor and clear every 'extended' one --
        i.e. all eight pistons at home. Lets the INIT homing chain satisfy
        immediately, which is more faithful than setting bNoSensors."""
        for ret, ext in SENSOR_DI.values():
            self.w(f"GVL_IO.dIn[{ret}]", True)
            self.w(f"GVL_IO.dIn[{ext}]", False)
        time.sleep(SETTLE)

    def set_plate(self, present):
        for di in PLATE_DI.values():
            self.w(f"GVL_IO.dIn[{di}]", present)
        time.sleep(SETTLE)

    # -- master cycle ------------------------------------------------------
    def step(self):
        return self.r("GVL_HMI.stMasterAuto.eStep", INT)

    def step_name(self):
        v = self.step()
        return STEP_NAMES.get(v, f"?{v}")

    def err_code(self):
        return self.r("GVL_HMI.stMasterAuto.iErrorCode", INT)

    def lamps(self):
        return {"green": self.r(f"GVL_IO.dOut[{DO_GREEN}]"),
                "red": self.r(f"GVL_IO.dOut[{DO_RED}]")}

    def wait_step(self, want, timeout=8.0, poll=0.02):
        """Block until eStep reaches `want`. Returns True/False only.

        Do NOT use the states seen here as the transition path. With all
        retract sensors asserted, each INIT state satisfies on the next scan,
        so the whole homing chain completes in ~3 PlcTask cycles (30 ms) --
        faster than any ADS poll can resolve, and the first observation lands
        after the chain is already over. Use transitions() on the PLC's own
        log ring instead: F_LogEvent records every 'PREV -> NEW' from inside
        the scan, so it cannot miss one."""
        want = want if isinstance(want, (list, tuple, set)) else [want]
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.step() in want:
                return True
            time.sleep(poll)
        return False

    def sample(self, sym, seconds, period=0.05, t=BOOL):
        """Sample one symbol over a window -- used for the blinking LED, where
        a single read cannot distinguish 'blinking' from 'steady'."""
        out, deadline = [], time.time() + seconds
        while time.time() < deadline:
            out.append(self.r(sym, t))
            time.sleep(period)
        return out

    # -- log ring ----------------------------------------------------------
    def log_head(self, n=8):
        out = []
        for i in range(n):
            out.append({
                "sev": self.r(f"GVL_Log.aRecent[{i}].sSevText", STRING),
                "time": self.r(f"GVL_Log.aRecent[{i}].sTime", STRING),
                "msg": self.r(f"GVL_Log.aRecent[{i}].sMsg", STRING),
            })
        return out

    def log_idx(self):
        return self.r("GVL_Log.nWriteIdx", UDINT)

    def log_since(self, idx0, n=20):
        """Entries written since log_idx() == idx0, oldest first.

        The counter and the ring are read over separate ADS calls, so a burst
        still in flight can lose its OLDEST entry from this listing. That is
        cosmetic -- it only affects the evidence string. Never assert on the
        presence of a specific entry here; assert on transitions() for the
        chain, or on absence (a delta of zero), which is race-free."""
        new = min(self.log_idx() - idx0, n)
        return list(reversed(self.log_head(new))) if new > 0 else []


_TRANS = re.compile(r"^([A-Z_]+) -> ([A-Z_]+)$")


def transitions(entries):
    """Reconstruct the state chain from the PLC's own transition log entries.

    FB_MasterAutoCycle Section 3 logs 'PREV -> NEW' on every change of eStep,
    from inside the scan -- so this is the authoritative path, immune to how
    fast the test can poll. Entries into ERR are the exception: those log
    sErrorText instead, so an ERR arrival shows up as the chain stopping plus
    a separate ERR-severity entry.
    """
    chain = []
    for e in entries:
        m = _TRANS.match(e["msg"].strip())
        if not m:
            continue
        a, b = m.group(1), m.group(2)
        if not chain or chain[-1] != a:
            chain.append(a)
        chain.append(b)
    return chain


def has_sev(entries, sev):
    return any(e["sev"].strip() == sev for e in entries)
