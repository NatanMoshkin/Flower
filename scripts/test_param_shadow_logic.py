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

# Mirrors ParamMin / ParamMax in the FB. Vendor ranges -- see ClampParam's
# header comment for provenance.
RANGES = {
    "J_SPEED": (1, 100), "L_SPEED": (1, 100), "REPEATS": (1, 10),
    "START_WAIT": (10, 10000), "WATER_WAIT": (10, 10000),
    "STAND_WAIT": (10, 10000), "END_WAIT": (10, 10000),
    "WATER_SPEED": (0, 100), "WAX_WAIT_TIME_IN": (0, 10000),
    "WAX_WAIT_TIME_OUT": (10, 10000), "WAX_SPEED": (0, 100),
}


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

        # --- logging model (mirrors GVL_Log + F_LogEvent) ---
        # log holds (sev, msg) for every entry F_LogEvent would ACCEPT, so DBG
        # entries are absent unless bDebugMode is set -- same filter as the FB.
        self.log = []
        self.bDebugMode = False
        self.sHost = "192.168.201.1"
        self.nPort = 6001

        self.on_connect()

    # ------------------------------------------------------------- logging
    def log_event(self, sev, msg):
        """F_LogEvent: drops DBG unless bDebugMode."""
        if sev == "DBG" and not self.bDebugMode:
            return False
        self.log.append((sev, msg))
        return True

    def logged(self, sev=None):
        return [m for s, m in self.log if sev is None or s == sev]

    def on_connect(self):
        # Mirrors the Connecting -> Connected transition.
        self.aShadow = [0] * PARAM_COUNT
        self.bShadowValid = False
        self.bAutoSyncQueued = True
        self.nLastStateSent = -1
        self.nPendIdx = 0
        self.nPendVal = 0
        # Log edge-detectors are reset with the rest of the session state.
        self.bStateUnanswered = False
        self.nLastCmdLogged = 0
        self.bTraceTx = False
        self.log_event("INFO", f"Connected {self.sHost}:{self.nPort}")

    def param_value(self, i):
        return self.stParams[SYNC_ORDER[i - 1]]

    def param_name(self, i):
        return SYNC_ORDER[i - 1]

    def set_param_value(self, i, val):
        self.stParams[SYNC_ORDER[i - 1]] = val

    def clamp_param(self, i, val):
        lo, hi = RANGES[SYNC_ORDER[i - 1]]
        return max(lo, min(val, hi))

    def param_index(self, name):
        return SYNC_ORDER.index(name) + 1 if name in SYNC_ORDER else 0

    def find_changed_param(self):
        for i in range(1, PARAM_COUNT + 1):
            if self.param_value(i) != self.aShadow[i - 1]:
                return i
        return 0

    def set_shadow_all(self):
        self.aShadow = [self.param_value(i) for i in range(1, PARAM_COUNT + 1)]
        self.bShadowValid = True

    def log_clamp(self, i, raw, sent):
        self.log_event(
            "WARN",
            f"{self.param_name(i)} {raw} out of range, clamped to {sent}")

    def scan(self, idle_elapsed=False):
        """One IO_IDLE pass. Returns the frame sent, or None."""
        nChanged = self.find_changed_param() if self.bShadowValid else 0

        # StartSend defaults every frame to traced; SendState opts out below.
        self.bTraceTx = True

        if self.bAutoSyncQueued:
            self.bAutoSyncQueued = False
            tx, pend = "GET_SYNC", self.TX_GETSYNC
        elif self.nStateOut != self.nLastStateSent:
            tx, pend = f"STATE:{self.nStateOut}", self.TX_STATE
            self.nLastStateSent, self.nPendIdx = self.nStateOut, 0
        elif self.bSetParam:
            idx = self.param_index(self.sSetName)
            if idx > 0:
                raw = self.nSetVal
                self.nSetVal = self.clamp_param(idx, raw)
                if self.nSetVal != raw:
                    self.log_clamp(idx, raw, self.nSetVal)
            tx, pend = f"{self.sSetName}:{self.nSetVal}", self.TX_SETPARAM
            self.nPendIdx = 0
        elif self.bTriggerNewBulb:
            tx, pend = "New_Bulb:1", self.TX_NEWBULB
        elif self.bGetSync:
            tx, pend = "GET_SYNC", self.TX_GETSYNC
        elif nChanged > 0:
            self.nPendIdx = nChanged
            raw = self.param_value(nChanged)
            self.nPendVal = self.clamp_param(nChanged, raw)
            if self.nPendVal != raw:
                # Logged before the write-back destroys the original value.
                self.log_clamp(nChanged, raw, self.nPendVal)
            # Write back, or the field stays out of range, never matches the
            # shadow, and the FB re-sends forever.
            self.set_param_value(nChanged, self.nPendVal)
            tx, pend = f"{self.param_name(nChanged)}:{self.nPendVal}", self.TX_SETPARAM
        elif idle_elapsed:
            tx, pend = f"STATE:{self.nStateOut}", self.TX_STATE
            self.nLastStateSent, self.nPendIdx = self.nStateOut, 0
            self.bTraceTx = False        # keep-alive repeat: not traced
        else:
            return None

        # Traced on send completion, so the entry means "this left the box".
        if self.bTraceTx:
            self.log_event("DBG", f"TX {tx}")

        self.handle_reply(pend, self.robot.exchange(tx))
        return tx

    def state_timeout(self):
        """IO_WAIT_RECV reply-timeout branch with iPend = TX_STATE.

        Tolerated rather than fatal, and edge-logged: the keep-alive re-fires
        every second, so a WARN per unanswered push would flush the ring.
        """
        if not self.bStateUnanswered:
            self.bStateUnanswered = True
            self.log_event("WARN", "STATE unanswered, link may be stale")

    def handle_reply(self, pend, rx):
        cmd_seen, cmd = False, 0

        if self.bStateUnanswered:
            self.bStateUnanswered = False
            self.log_event("INFO", "STATE replies resumed")

        if rx.startswith("CMD:"):
            cmd_seen, cmd = True, int(rx[4:])
            self.nRobotCmd = cmd

        # The idle CMD:0 answer to a keep-alive is the one reply not traced.
        if not (cmd_seen and cmd == 0):
            self.log_event("DBG", f"RX {rx[:76]}")

        if cmd_seen and cmd != self.nLastCmdLogged:
            self.nLastCmdLogged = cmd
            if cmd == 1:
                self.log_event("INFO", "CMD:1 start cycle")
            elif cmd == 2:
                self.log_event("INFO", "CMD:2 reset error")
            elif cmd != 0:
                self.log_event("WARN", f"CMD unknown, ignored: {cmd}")

        if pend == self.TX_GETSYNC:
            if rx.startswith("SYNC:"):
                for tok in rx[5:].split(","):
                    name, _, val = tok.partition("=")
                    if name in self.stParams:
                        self.stParams[name] = int(val)
                self.log_event("INFO", "SYNC ok, tuning params pulled")
            else:
                self.log_event("WARN", f"SYNC reply malformed: {rx[:54]}")
            self.set_shadow_all()
            self.bGetSync = False
        elif pend == self.TX_SETPARAM:
            if self.nPendIdx > 0:
                # Logged before the shadow is banked: aShadow still holds the
                # previous accepted value, the 'from' half of the entry.
                self.log_event(
                    "INFO",
                    f"{self.param_name(self.nPendIdx)} "
                    f"{self.aShadow[self.nPendIdx - 1]} -> {self.nPendVal}")
                self.aShadow[self.nPendIdx - 1] = self.nPendVal
                self.nPendIdx = 0
            else:
                self.log_event("INFO", f"SET {self.sSetName} = {self.nSetVal}")
                self.bSetParam = False
        elif pend == self.TX_NEWBULB:
            self.log_event("INFO", "New_Bulb acknowledged")
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


def t_clamp_above_max():
    r = Robot(ROBOT_DEFAULTS)
    fb = Fb(r, PLC_DEFAULTS)
    settle(fb)
    fb.stParams["J_SPEED"] = 500          # operator typo, max is 100
    sent = settle(fb)
    assert sent == ["J_SPEED:100"], f"sent unclamped: {sent}"
    assert r.params["J_SPEED"] == 100, "robot got an out-of-range value"
    assert fb.stParams["J_SPEED"] == 100, \
        "clamped value not written back -- HMI would show 500 while robot has 100"


def t_clamp_below_min():
    r = Robot(ROBOT_DEFAULTS)
    fb = Fb(r, PLC_DEFAULTS)
    settle(fb)
    fb.stParams["START_WAIT"] = 0          # min is 10
    assert settle(fb) == ["START_WAIT:10"]
    assert fb.stParams["START_WAIT"] == 10


def t_clamp_does_not_loop():
    """The failure this design exists to prevent.

    If the clamp only bounded the transmitted value and left the field
    alone, the field would differ from the shadow forever and the FB would
    re-send on every idle scan -- a silent packet storm.
    """
    r = Robot(ROBOT_DEFAULTS)
    fb = Fb(r, PLC_DEFAULTS)
    settle(fb)
    fb.stParams["WAX_SPEED"] = 9999
    first = settle(fb)
    assert first == ["WAX_SPEED:100"], first
    for _ in range(5):
        assert settle(fb) == [], "re-sent after clamping -- shadow never converged"


def t_clamp_all_params():
    r = Robot(ROBOT_DEFAULTS)
    fb = Fb(r, PLC_DEFAULTS)
    settle(fb)
    for k in SYNC_ORDER:
        fb.stParams[k] = 99999
    settle(fb)
    for k in SYNC_ORDER:
        hi = RANGES[k][1]
        assert r.params[k] == hi, f"{k}: robot got {r.params[k]}, expected {hi}"
        assert fb.stParams[k] == hi, f"{k}: field not written back"


def t_clamp_escape_hatch():
    r = Robot(ROBOT_DEFAULTS)
    fb = Fb(r, PLC_DEFAULTS)
    settle(fb)
    fb.bSetParam, fb.sSetName, fb.nSetVal = True, "REPEATS", 77   # max 10
    assert settle(fb) == ["REPEATS:10"]
    assert fb.nSetVal == 10, "nSetVal not written back for the caller to see"


def t_unknown_name_passes_through():
    """The escape hatch exists for names that are not struct fields."""
    r = Robot(ROBOT_DEFAULTS)
    fb = Fb(r, PLC_DEFAULTS)
    settle(fb)
    fb.bSetParam, fb.sSetName, fb.nSetVal = True, "SOME_OTHER_NAME", 9999
    assert settle(fb) == ["SOME_OTHER_NAME:9999"], "unknown name was clamped"


def t_sync_values_not_clamped():
    """A value pulled FROM the robot must not be silently rewritten.

    Clamping applies to what we send, not to what we read. Rewriting a
    SYNC-sourced value would push our table back at the robot and, if the
    table were ever wrong, the two ends would fight.
    """
    r = Robot(dict(ROBOT_DEFAULTS, J_SPEED=250))
    fb = Fb(r, PLC_DEFAULTS)
    sent = settle(fb)
    assert fb.stParams["J_SPEED"] == 250, "SYNC value was clamped on the way in"
    assert not any(s.startswith("J_SPEED:") for s in sent), \
        f"pushed a correction back at the robot: {sent}"


# --------------------------------------------------------------- logging
# These assert the LOGGING POLICY, which exists to keep a 20-entry ring
# readable. The failure mode they guard against is not a crash: it is a log
# that technically records everything and is therefore useless.

def t_log_production_is_quiet():
    """With Debug off, an idle link must not produce entries at all.

    The keep-alive runs at 1 Hz. If it logged, 20 seconds would flush every
    cycle event off the panel's Logs page.
    """
    r = Robot(ROBOT_DEFAULTS)
    fb = Fb(r, PLC_DEFAULTS)
    settle(fb)
    before = len(fb.log)
    for _ in range(30):
        fb.scan(idle_elapsed=True)
    assert len(fb.log) == before, \
        f"idle link logged {len(fb.log) - before} entries: {fb.log[before:]}"


def t_log_keepalive_not_traced_even_in_debug():
    r = Robot(ROBOT_DEFAULTS)
    fb = Fb(r, PLC_DEFAULTS)
    settle(fb)
    fb.bDebugMode = True
    before = len(fb.log)
    for _ in range(10):
        fb.scan(idle_elapsed=True)
    new = fb.log[before:]
    assert new == [], f"keep-alive traced despite the exclusion: {new}"


def t_log_state_change_is_traced_in_debug():
    """The counterpart: a state change IS worth a trace line."""
    r = Robot(ROBOT_DEFAULTS)
    fb = Fb(r, PLC_DEFAULTS)
    settle(fb)
    fb.bDebugMode = True
    fb.nStateOut = 21
    fb.scan()
    assert "TX STATE:21" in fb.logged("DBG"), fb.logged("DBG")
    # ...but its CMD:0 reply is still not traced.
    assert "RX CMD:0" not in fb.logged("DBG"), "idle reply was traced"


def t_log_cmd_logged_once_per_command():
    """The robot may repeat a command until it sees the state change."""
    class StickyRobot(Robot):
        def exchange(self, msg):
            self.rx.append(msg)
            if msg.startswith("STATE:"):
                return "CMD:1"          # never clears
            return super().exchange(msg)

    r = StickyRobot(ROBOT_DEFAULTS)
    fb = Fb(r, PLC_DEFAULTS)
    settle(fb)
    for _ in range(8):
        fb.scan(idle_elapsed=True)
    starts = [m for m in fb.logged("INFO") if m == "CMD:1 start cycle"]
    assert len(starts) == 1, f"expected 1 start entry, got {len(starts)}"


def t_log_cmd_relogs_after_zero():
    """A second genuine command must not be swallowed as a repeat."""
    r = Robot(ROBOT_DEFAULTS)
    fb = Fb(r, PLC_DEFAULTS)
    settle(fb)
    for queued in (1, 0, 1):
        r.queued_cmd = queued
        fb.scan(idle_elapsed=True)
    starts = [m for m in fb.logged("INFO") if m == "CMD:1 start cycle"]
    assert len(starts) == 2, f"expected 2 start entries, got {len(starts)}"


def t_log_unknown_cmd_warns():
    r = Robot(ROBOT_DEFAULTS)
    fb = Fb(r, PLC_DEFAULTS)
    settle(fb)
    r.queued_cmd = 7                    # MAIN acts on 1 and 2 only
    fb.scan(idle_elapsed=True)
    assert any("CMD unknown, ignored: 7" in m for m in fb.logged("WARN")), \
        fb.logged("WARN")


def t_log_param_change_shows_from_and_to():
    r = Robot(ROBOT_DEFAULTS)
    fb = Fb(r, PLC_DEFAULTS)
    settle(fb)
    was = fb.stParams["J_SPEED"]
    fb.stParams["J_SPEED"] = 25
    settle(fb)
    assert f"J_SPEED {was} -> 25" in fb.logged("INFO"), fb.logged("INFO")


def t_log_clamp_warns_with_original_value():
    """The clamp write-back destroys the operator's number.

    Without this entry the edit simply appears not to have taken.
    """
    r = Robot(ROBOT_DEFAULTS)
    fb = Fb(r, PLC_DEFAULTS)
    settle(fb)
    fb.stParams["J_SPEED"] = 500
    settle(fb)
    warns = fb.logged("WARN")
    assert any("500" in m and "100" in m for m in warns), \
        f"clamp not reported with both values: {warns}"


def t_log_unanswered_state_is_edge_logged():
    r = Robot(ROBOT_DEFAULTS)
    fb = Fb(r, PLC_DEFAULTS)
    settle(fb)
    for _ in range(10):                 # robot stops answering
        fb.state_timeout()
    stale = [m for m in fb.logged("WARN") if "unanswered" in m]
    assert len(stale) == 1, f"expected 1 stale-link WARN, got {len(stale)}"
    fb.scan(idle_elapsed=True)          # robot answers again
    assert "STATE replies resumed" in fb.logged("INFO"), fb.logged("INFO")


def t_log_malformed_sync_warns():
    class BadRobot(Robot):
        def exchange(self, msg):
            self.rx.append(msg)
            return "GARBAGE" if msg == "GET_SYNC" else super().exchange(msg)

    r = BadRobot(ROBOT_DEFAULTS)
    fb = Fb(r, PLC_DEFAULTS)
    settle(fb)
    assert any("malformed" in m for m in fb.logged("WARN")), fb.logged("WARN")
    assert "SYNC ok, tuning params pulled" not in fb.logged("INFO"), \
        "reported a good pull on a garbage frame"


def t_log_newbulb_and_escape_hatch():
    r = Robot(ROBOT_DEFAULTS)
    fb = Fb(r, PLC_DEFAULTS)
    settle(fb)
    fb.bTriggerNewBulb = True
    settle(fb)
    assert "New_Bulb acknowledged" in fb.logged("INFO"), fb.logged("INFO")
    fb.bSetParam, fb.sSetName, fb.nSetVal = True, "SOME_OTHER_NAME", 5
    settle(fb)
    assert "SET SOME_OTHER_NAME = 5" in fb.logged("INFO"), fb.logged("INFO")


def t_log_connect_names_the_endpoint():
    """'Connect failed' without the endpoint cannot distinguish a wrong IP
    from a robot that is switched off."""
    r = Robot(ROBOT_DEFAULTS)
    fb = Fb(r, PLC_DEFAULTS)
    assert any("192.168.201.1:6001" in m for m in fb.logged("INFO")), \
        fb.logged("INFO")


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
        ("clamp above max", t_clamp_above_max),
        ("clamp below min", t_clamp_below_min),
        ("clamped write does not re-send forever", t_clamp_does_not_loop),
        ("all 11 params clamp to their max", t_clamp_all_params),
        ("escape hatch is clamped too", t_clamp_escape_hatch),
        ("unknown escape-hatch name passes through", t_unknown_name_passes_through),
        ("SYNC-sourced values are not clamped", t_sync_values_not_clamped),
        ("LOG idle link is silent in production", t_log_production_is_quiet),
        ("LOG keep-alive not traced even in debug", t_log_keepalive_not_traced_even_in_debug),
        ("LOG state change is traced in debug", t_log_state_change_is_traced_in_debug),
        ("LOG repeated CMD logs once", t_log_cmd_logged_once_per_command),
        ("LOG CMD re-logs after a zero", t_log_cmd_relogs_after_zero),
        ("LOG unknown CMD warns", t_log_unknown_cmd_warns),
        ("LOG param change shows from -> to", t_log_param_change_shows_from_and_to),
        ("LOG clamp warns with the original value", t_log_clamp_warns_with_original_value),
        ("LOG unanswered STATE is edge-logged", t_log_unanswered_state_is_edge_logged),
        ("LOG malformed SYNC warns", t_log_malformed_sync_warns),
        ("LOG New_Bulb + escape hatch", t_log_newbulb_and_escape_hatch),
        ("LOG connect entry names the endpoint", t_log_connect_names_the_endpoint),
    ]
    ok = all([run(label, body) for label, body in tests])
    print()
    print("ALL PASS" if ok else "FAILURES PRESENT")
    raise SystemExit(0 if ok else 1)
