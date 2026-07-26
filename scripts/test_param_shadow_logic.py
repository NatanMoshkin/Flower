"""Verify FB_RobotTcpClient's shadow-copy write path at the protocol level.

This is NOT a TwinCAT build. It is a faithful port of the FB's IO_IDLE
priority chain + HandleReply shadow bookkeeping, driven against an inline
server that speaks the same frames as
RobotBridge/Client_working_example/dummy_server.py. It catches sequencing
and shadow-bookkeeping bugs (echo storms, starvation, lost edits); it does
not prove the ST compiles.

Run:  python scripts/test_param_shadow_logic.py
"""

SYNC_ORDER = [
    "J_SPEED", "L_SPEED", "REPEATS", "START_WAIT", "WATER_WAIT",
    "STAND_WAIT", "END_WAIT", "WATER_SPEED",
    "WAX_WAIT_TIME_IN", "WAX_WAIT_TIME_OUT", "WAX_SPEED",
]
PARAM_COUNT = len(SYNC_ORDER)


class Robot:
    """Stands in for the Dobot server. Records every frame it receives."""

    def __init__(self, params):
        self.params = dict(params)
        self.rx = []
        self.queued_cmd = 0

    def exchange(self, msg):
        self.rx.append(msg)
        if msg.startswith("STATE:"):
            m, self.queued_cmd = self.queued_cmd, 0
            return f"CMD:{m}"
        if msg == "GET_SYNC":
            return "SYNC:" + ",".join(f"{k}={self.params[k]}" for k in SYNC_ORDER)
        if ":" in msg:
            name, _, val = msg.partition(":")
            if name == "New_Bulb":
                return "OK: SET New_Bulb"
            if name in self.params:
                self.params[name] = int(val)
            return f"OK: SET {name}"
        return "ERR"


class Fb:
    """Port of the FB. stParams is the PLC-side struct the HMI writes into."""

    TX_NONE, TX_GETSYNC, TX_SETPARAM, TX_NEWBULB, TX_STATE = range(5)

    def __init__(self, robot, params):
        self.robot = robot
        self.stParams = dict(params)
        self.nStateOut = 0
        self.nRobotCmd = 0
        self.bGetSync = False
        self.bSetParam = False
        self.sSetName = ""
        self.nSetVal = 0
        self.bTriggerNewBulb = False
        self.on_connect()

    def on_connect(self):
        # Mirrors the Connecting -> Connected transition.
        self.aShadow = [0] * PARAM_COUNT
        self.bShadowValid = False
        self.bAutoSyncQueued = True
        self.nLastStateSent = -1
        self.nPendIdx = 0
        self.nPendVal = 0

    def param_value(self, i):
        return self.stParams[SYNC_ORDER[i - 1]]

    def param_name(self, i):
        return SYNC_ORDER[i - 1]

    def find_changed_param(self):
        for i in range(1, PARAM_COUNT + 1):
            if self.param_value(i) != self.aShadow[i - 1]:
                return i
        return 0

    def set_shadow_all(self):
        self.aShadow = [self.param_value(i) for i in range(1, PARAM_COUNT + 1)]
        self.bShadowValid = True

    def scan(self, idle_elapsed=False):
        """One IO_IDLE pass. Returns the frame sent, or None."""
        nChanged = self.find_changed_param() if self.bShadowValid else 0

        if self.bAutoSyncQueued:
            self.bAutoSyncQueued = False
            tx, pend = "GET_SYNC", self.TX_GETSYNC
        elif self.nStateOut != self.nLastStateSent:
            tx, pend = f"STATE:{self.nStateOut}", self.TX_STATE
            self.nLastStateSent, self.nPendIdx = self.nStateOut, 0
        elif self.bSetParam:
            tx, pend = f"{self.sSetName}:{self.nSetVal}", self.TX_SETPARAM
            self.nPendIdx = 0
        elif self.bTriggerNewBulb:
            tx, pend = "New_Bulb:1", self.TX_NEWBULB
        elif self.bGetSync:
            tx, pend = "GET_SYNC", self.TX_GETSYNC
        elif nChanged > 0:
            self.nPendIdx = nChanged
            self.nPendVal = self.param_value(nChanged)
            tx, pend = f"{self.param_name(nChanged)}:{self.nPendVal}", self.TX_SETPARAM
        elif idle_elapsed:
            tx, pend = f"STATE:{self.nStateOut}", self.TX_STATE
            self.nLastStateSent, self.nPendIdx = self.nStateOut, 0
        else:
            return None

        self.handle_reply(pend, self.robot.exchange(tx))
        return tx

    def handle_reply(self, pend, rx):
        if rx.startswith("CMD:"):
            self.nRobotCmd = int(rx[4:])

        if pend == self.TX_GETSYNC:
            if rx.startswith("SYNC:"):
                for tok in rx[5:].split(","):
                    name, _, val = tok.partition("=")
                    if name in self.stParams:
                        self.stParams[name] = int(val)
            self.set_shadow_all()
            self.bGetSync = False
        elif pend == self.TX_SETPARAM:
            if self.nPendIdx > 0:
                self.aShadow[self.nPendIdx - 1] = self.nPendVal
                self.nPendIdx = 0
            else:
                self.bSetParam = False
        elif pend == self.TX_NEWBULB:
            self.bTriggerNewBulb = False


def run(label, body):
    try:
        body()
    except AssertionError as e:
        print(f"FAIL  {label}\n      {e}")
        return False
    print(f"PASS  {label}")
    return True


ROBOT_DEFAULTS = {
    "J_SPEED": 10, "L_SPEED": 10, "REPEATS": 2, "START_WAIT": 500,
    "WATER_WAIT": 500, "STAND_WAIT": 2000, "END_WAIT": 500,
    "WATER_SPEED": 10, "WAX_WAIT_TIME_IN": 500, "WAX_WAIT_TIME_OUT": 500,
    "WAX_SPEED": 10,
}
# PLC power-on defaults from ST_RobotParams -- deliberately DIFFERENT from
# the robot's live values, to prove the shadow suppresses a startup echo.
PLC_DEFAULTS = dict(ROBOT_DEFAULTS, J_SPEED=10, STAND_WAIT=2000)


def settle(fb, n=40):
    """Run scans until nothing more is sent."""
    sent = []
    for _ in range(n):
        tx = fb.scan()
        if tx is None:
            break
        sent.append(tx)
    return sent


def t_no_startup_echo():
    r = Robot(dict(ROBOT_DEFAULTS, J_SPEED=77, WAX_SPEED=88))
    fb = Fb(r, PLC_DEFAULTS)
    sent = settle(fb)
    # GET_SYNC must precede the initial STATE push: the reply to a STATE can
    # carry CMD:1, and we must not start a cycle on unsynced parameters.
    assert sent == ["GET_SYNC", "STATE:0"], f"wrong connect sequence: {sent}"
    assert fb.stParams["J_SPEED"] == 77, "SYNC did not populate stParams"
    writes = [m for m in r.rx if m != "GET_SYNC" and not m.startswith("STATE:")]
    assert writes == [], f"robot values echoed back as writes: {writes}"


def t_edit_is_pushed():
    r = Robot(ROBOT_DEFAULTS)
    fb = Fb(r, PLC_DEFAULTS)
    settle(fb)
    fb.stParams["J_SPEED"] = 15          # the HMI NumericInput write
    sent = settle(fb)
    assert sent == ["J_SPEED:15"], f"expected one write, got {sent}"
    assert r.params["J_SPEED"] == 15, "robot did not receive the new speed"
    assert settle(fb) == [], "write repeated after ACK"


def t_all_three_speeds():
    r = Robot(ROBOT_DEFAULTS)
    fb = Fb(r, PLC_DEFAULTS)
    settle(fb)
    fb.stParams["J_SPEED"] = 21
    fb.stParams["WATER_SPEED"] = 22
    fb.stParams["WAX_SPEED"] = 23
    sent = settle(fb)
    assert sent == ["J_SPEED:21", "WATER_SPEED:22", "WAX_SPEED:23"], sent
    for k, v in (("J_SPEED", 21), ("WATER_SPEED", 22), ("WAX_SPEED", 23)):
        assert r.params[k] == v, f"{k} not applied on robot"


def t_state_change_preempts_writes():
    r = Robot(ROBOT_DEFAULTS)
    fb = Fb(r, PLC_DEFAULTS)
    settle(fb)
    for k in SYNC_ORDER:                  # a burst of 11 pending writes
        fb.stParams[k] += 1
    fb.nStateOut = 21                     # ...and a state change same scan
    first = fb.scan()
    assert first == "STATE:21", f"state push was starved behind writes: {first}"


def t_cmd_still_arrives_during_writes():
    r = Robot(ROBOT_DEFAULTS)
    fb = Fb(r, PLC_DEFAULTS)
    settle(fb)
    for k in SYNC_ORDER:
        fb.stParams[k] += 1
    r.queued_cmd = 1
    settle(fb)                            # drain the writes
    fb.scan(idle_elapsed=True)            # keep-alive STATE carries CMD back
    assert fb.nRobotCmd == 1, "CMD:1 never reached the PLC"


def t_reedit_midflight_not_lost():
    """Operator edits the same param again while the write is in flight."""
    r = Robot(ROBOT_DEFAULTS)
    fb = Fb(r, PLC_DEFAULTS)
    settle(fb)
    fb.stParams["J_SPEED"] = 15
    nChanged = fb.find_changed_param()
    fb.nPendIdx, fb.nPendVal = nChanged, fb.param_value(nChanged)
    rx = r.exchange(f"{fb.param_name(nChanged)}:{fb.nPendVal}")
    fb.stParams["J_SPEED"] = 30           # second edit, pre-ACK
    fb.handle_reply(Fb.TX_SETPARAM, rx)
    sent = settle(fb)
    assert sent == ["J_SPEED:30"], f"second edit lost, got {sent}"
    assert r.params["J_SPEED"] == 30


def t_escape_hatch_still_works():
    r = Robot(ROBOT_DEFAULTS)
    fb = Fb(r, PLC_DEFAULTS)
    settle(fb)
    fb.bSetParam, fb.sSetName, fb.nSetVal = True, "SOME_OTHER_NAME", 5
    sent = settle(fb)
    assert sent == ["SOME_OTHER_NAME:5"], sent
    assert fb.bSetParam is False, "bSetParam not auto-cleared"


def t_resync_rebaselines():
    """A manual GET_SYNC pull must not echo the pulled values back out."""
    r = Robot(dict(ROBOT_DEFAULTS, J_SPEED=99))
    fb = Fb(r, PLC_DEFAULTS)
    settle(fb)
    r.params["J_SPEED"] = 55              # changed on the robot side
    fb.bGetSync = True
    sent = settle(fb)
    assert sent == ["GET_SYNC"], f"pull echoed back: {sent}"
    assert fb.stParams["J_SPEED"] == 55


def t_malformed_sync_still_enables_detection():
    class BadRobot(Robot):
        def exchange(self, msg):
            self.rx.append(msg)
            return "GARBAGE" if msg == "GET_SYNC" else super().exchange(msg)

    r = BadRobot(ROBOT_DEFAULTS)
    fb = Fb(r, PLC_DEFAULTS)
    settle(fb)
    assert fb.bShadowValid, "one bad SYNC frame disabled the write path forever"
    fb.stParams["J_SPEED"] = 15
    assert settle(fb) == ["J_SPEED:15"]


if __name__ == "__main__":
    tests = [
        ("no startup echo of robot values", t_no_startup_echo),
        ("HMI edit is pushed as NAME:VALUE", t_edit_is_pushed),
        ("all three speed params push", t_all_three_speeds),
        ("state change preempts pending writes", t_state_change_preempts_writes),
        ("CMD still arrives during write burst", t_cmd_still_arrives_during_writes),
        ("re-edit mid-flight is not lost", t_reedit_midflight_not_lost),
        ("explicit bSetParam escape hatch", t_escape_hatch_still_works),
        ("manual GET_SYNC re-baselines", t_resync_rebaselines),
        ("malformed SYNC still enables detection", t_malformed_sync_still_enables_detection),
    ]
    ok = all([run(label, body) for label, body in tests])
    print()
    print("ALL PASS" if ok else "FAILURES PRESENT")
    raise SystemExit(0 if ok else 1)
