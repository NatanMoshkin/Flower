"""Verify FB_MasterAutoCycle's arming model at the state-machine level.

The 2026-07-29 change split "start" into two things with different owners:

    operator START  -> home the pistons and ARM      (stHmi.bStart, HMI or PB3)
    robot CMD:1     -> run ONE bulb cycle            (bExtStartPulse, IDLE only)

so the machine cannot move after power-up, after Manual, or after a STOP until a
human presses START, and once armed only the robot decides when a bulb runs.

This ports Sections 2 and 4 of the FB and asserts the arming transitions -- the
part where a mistake means unexpected motion. It deliberately does NOT model
piston dynamics: sensors are treated as satisfied on the next scan, which is the
bNoSensors bench case, so the assertions are about WHICH state comes next rather
than how long each takes.

Validates the algorithm, not the ST build -- a TwinCAT compile is still required.

Run:  python scripts/test_master_cycle_arming.py
Exit: 0 = all pass, 1 = a transition is wrong.
"""


class Step:
    """Mirrors E_MasterAutoStep. Values are WIRE values (nStateOut)."""
    IDLE                 = 0
    SEP_EXTENDING        = 1
    PUSH_EXTENDING       = 3
    DWELL_PUSH           = 4
    PUSH_RETRACTING      = 5
    PUSH_RETRACTED_DWELL = 6
    SEP_RETRACTING       = 7
    SEP_RETRACTED_DWELL  = 8
    INIT_PUSH_RETRACTING = 10
    INIT_SEP_RETRACTING  = 11
    INIT_GRIP_RETRACTING = 12
    CHECK_PLATE           = 20
    GRIP_EXTENDING       = 21
    GRIP_RETRACTING      = 22
    MANUAL               = 30
    NOT_HOMED            = 40
    RECOVER_PUSH_RETR    = 50
    RECOVER_SEP_RETR     = 51
    RECOVER_GRIP_RETR    = 52
    ERR                  = 99


NAME = {v: k for k, v in vars(Step).items() if not k.startswith("_")}

# The bulb cycle, in order, once the INIT chain hands over at CHECK_PLATE.
CYCLE = [
    Step.CHECK_PLATE, Step.GRIP_EXTENDING, Step.SEP_EXTENDING, Step.PUSH_EXTENDING,
    Step.DWELL_PUSH, Step.PUSH_RETRACTING, Step.PUSH_RETRACTED_DWELL,
    Step.SEP_RETRACTING, Step.SEP_RETRACTED_DWELL, Step.GRIP_RETRACTING,
]
CHAIN = [Step.INIT_PUSH_RETRACTING, Step.INIT_SEP_RETRACTING, Step.INIT_GRIP_RETRACTING]

# Fault recovery has its OWN chain since 2026-08-05: same motion and the same
# collision ordering, different identity, so a failed recovery reports codes
# 12/13/14 rather than looking exactly like a failed arming.
RECOVER = [Step.RECOVER_PUSH_RETR, Step.RECOVER_SEP_RETR, Step.RECOVER_GRIP_RETR]

MOTION = set(CHAIN) | set(CYCLE) | set(RECOVER)


class Fb:
    """FB_MasterAutoCycle, arming logic only."""

    def __init__(self):
        self.eStep = Step.NOT_HOMED      # stHmi.eStep's declared default
        self.bHomeThenIdle = False
        self.iErrorCode = 0
        self.nCyclesCompleted = 0
        self.bContinuous = False         # kept, but must never start anything

    # -- MAIN's nStateOut mapping ------------------------------------------
    def state_out(self, bMachineAuto):
        return Step.MANUAL if not bMachineAuto else self.eStep

    def scan(self, bMachineAuto=True, bExtStartPulse=False,
             bStart=False, bStop=False, bReset=False, fault=False):
        """One PLC scan. bStart/bStop/bReset arrive already edge-detected, which
        is what the FB's R_TRIGs + auto-clear produce."""

        # ---- Section 2: global overrides, in the FB's order ---------------
        if bStop and self.eStep != Step.ERR:
            # STOP DISARMS, it does not fault. Error 99 is retired.
            self.iErrorCode = 0
            self.eStep = Step.NOT_HOMED
            self.bContinuous = False
            return

        if bReset and self.eStep == Step.ERR:
            # RESET homes; it does not drop straight to IDLE. Since 2026-08-05 it
            # runs the dedicated RECOVER chain, not the shared INIT one.
            self.iErrorCode = 0
            self.eStep = Step.RECOVER_PUSH_RETR
            return

        if not bMachineAuto and self.eStep not in (Step.NOT_HOMED, Step.ERR):
            # Manual parks in NOT_HOMED -- this IS "Manual->Auto needs a START".
            self.bContinuous = False
            self.eStep = Step.NOT_HOMED
            return

        # ---- Section 4: state machine -------------------------------------
        if fault and self.eStep in MOTION:
            self.iErrorCode = 1
            self.eStep = Step.ERR
            return

        if self.eStep == Step.NOT_HOMED:
            self.iErrorCode = 0
            if bMachineAuto and bStart:
                self.bHomeThenIdle = True
                self.eStep = Step.INIT_PUSH_RETRACTING

        elif self.eStep == Step.IDLE:
            self.iErrorCode = 0
            # Only the robot (or its bench stand-in) starts a bulb. Note bStart
            # and bContinuous are NOT in this condition any more.
            if bMachineAuto and bExtStartPulse:
                self.bHomeThenIdle = False
                self.eStep = Step.INIT_PUSH_RETRACTING
            # bStart is IGNORED here since 2026-08-05. It used to re-home and
            # come back; that was a no-op in outcome and it let a green-before-
            # orange combo press drop the bulb request, because leaving IDLE
            # meant nothing consumed the one-scan pulse. See the FB comment.

        elif self.eStep == Step.INIT_GRIP_RETRACTING:
            # The one place the two callers diverge.
            self.eStep = Step.IDLE if self.bHomeThenIdle else Step.CHECK_PLATE

        elif self.eStep == Step.GRIP_RETRACTING:
            self.nCyclesCompleted += 1
            self.eStep = Step.IDLE

        elif self.eStep == Step.RECOVER_GRIP_RETR:
            # Always IDLE -- the machine really is homed here, so STATE:0
            # is honest and the robot's next CMD:1 runs the following bulb.
            self.eStep = Step.IDLE

        elif self.eStep in RECOVER:
            self.eStep = RECOVER[RECOVER.index(self.eStep) + 1]

        elif self.eStep in CHAIN:
            self.eStep = CHAIN[CHAIN.index(self.eStep) + 1]

        elif self.eStep in CYCLE:
            self.eStep = CYCLE[CYCLE.index(self.eStep) + 1]

        # ERR is latched: no transition without bReset.


def robot_reply(state_out, wants_bulb=True):
    """The contract dummy_server.py and the real src2.lua must implement."""
    if state_out == Step.ERR:
        return 2
    if state_out == Step.IDLE and wants_bulb:
        return 1
    return 0


def run(fb, scans, **kw):
    seen = []
    for _ in range(scans):
        fb.scan(**kw)
        seen.append(fb.eStep)
    return seen


def until(fb, target, limit=40, **kw):
    for _ in range(limit):
        if fb.eStep == target:
            return True
        fb.scan(**kw)
    return fb.eStep == target


# ------------------------------------------------------------------ tests
def t_boots_not_homed():
    fb = Fb()
    assert fb.eStep == Step.NOT_HOMED, f"booted in {NAME[fb.eStep]}"
    assert fb.state_out(True) == 40, "NOT_HOMED must report 40 to the robot"
    assert robot_reply(fb.state_out(True)) == 0, "robot must be told to wait"


def t_robot_cannot_start_unarmed():
    fb = Fb()
    run(fb, 30, bExtStartPulse=True)
    assert fb.eStep == Step.NOT_HOMED, \
        f"robot started an un-armed machine: {NAME[fb.eStep]}"
    assert fb.nCyclesCompleted == 0


def t_operator_start_homes_to_idle():
    fb = Fb()
    fb.scan(bStart=True)
    assert fb.eStep == Step.INIT_PUSH_RETRACTING
    assert until(fb, Step.IDLE), f"homing did not reach IDLE ({NAME[fb.eStep]})"
    assert fb.nCyclesCompleted == 0, "homing must not count as a bulb"


def t_start_is_ignored_in_idle():
    """START in IDLE must do NOTHING -- not even a harmless re-home.

    This is what makes the PB2+PB3 bulb-start combo reliable: if a stray green
    press cannot move the machine out of IDLE, the combo's one-scan pulse always
    lands in the one branch that consumes it."""
    fb = Fb()
    fb.scan(bStart=True)
    assert until(fb, Step.IDLE), "could not arm"
    for _ in range(5):
        fb.scan(bStart=True)
        assert fb.eStep == Step.IDLE,             f"START moved an armed machine to {NAME[fb.eStep]}"
    # ...and the robot can still start a bulb straight afterwards
    fb.scan(bExtStartPulse=True)
    assert fb.eStep == Step.INIT_PUSH_RETRACTING
    assert fb.bHomeThenIdle is False, "a bulb must take the CHECK_PLATE exit"


def t_start_never_runs_a_cycle():
    """The whole point: START homes and stops. It must not touch CHECK_PLATE."""
    fb = Fb()
    fb.scan(bStart=True)
    seen = run(fb, 30)
    assert Step.CHECK_PLATE not in seen, "operator START ran a bulb cycle"
    assert fb.eStep == Step.IDLE


def t_robot_runs_cycle_once_armed():
    fb = Fb()
    fb.scan(bStart=True)
    until(fb, Step.IDLE)
    fb.scan(bExtStartPulse=True)
    seen = run(fb, 30)
    assert Step.CHECK_PLATE in seen, "robot start never reached the bulb cycle"
    assert fb.eStep == Step.IDLE, f"cycle ended in {NAME[fb.eStep]}"
    assert fb.nCyclesCompleted == 1


def t_stays_armed_across_cycles():
    fb = Fb()
    fb.scan(bStart=True)
    until(fb, Step.IDLE)
    for n in (1, 2, 3):
        fb.scan(bExtStartPulse=True)
        assert until(fb, Step.IDLE, limit=40), "cycle did not complete"
        assert fb.nCyclesCompleted == n, f"bulb {n} lost"


def t_continuous_cannot_start():
    fb = Fb()
    fb.scan(bStart=True)
    until(fb, Step.IDLE)
    fb.bContinuous = True
    seen = run(fb, 30)
    assert all(s == Step.IDLE for s in seen), "bContinuous started a cycle"
    assert fb.nCyclesCompleted == 0


def t_stop_disarms_without_faulting():
    fb = Fb()
    fb.scan(bStart=True)
    until(fb, Step.IDLE)
    fb.scan(bExtStartPulse=True)
    until(fb, Step.SEP_EXTENDING)
    fb.scan(bStop=True)
    assert fb.eStep == Step.NOT_HOMED, f"STOP left it in {NAME[fb.eStep]}"
    assert fb.iErrorCode == 0, "STOP must not raise an error code (99 retired)"
    # And the robot must be told to wait, NOT to reset.
    assert robot_reply(fb.state_out(True)) == 0, \
        "robot would try to recover an operator STOP"


def t_stop_survives_robot_pressure():
    fb = Fb()
    fb.scan(bStart=True)
    until(fb, Step.IDLE)
    fb.scan(bExtStartPulse=True)
    until(fb, Step.SEP_EXTENDING)
    fb.scan(bStop=True)
    run(fb, 30, bExtStartPulse=True)     # robot keeps asking
    assert fb.eStep == Step.NOT_HOMED, "robot restarted after an operator STOP"


def t_stop_from_idle_disarms():
    fb = Fb()
    fb.scan(bStart=True)
    until(fb, Step.IDLE)
    fb.scan(bStop=True)
    assert fb.eStep == Step.NOT_HOMED, "STOP in IDLE did not disarm"


def t_err_recovery_is_robot_driven():
    fb = Fb()
    fb.scan(bStart=True)
    until(fb, Step.IDLE)
    fb.scan(bExtStartPulse=True)
    until(fb, Step.SEP_EXTENDING)
    fb.scan(fault=True)
    assert fb.eStep == Step.ERR
    assert robot_reply(fb.state_out(True)) == 2, "robot should send CMD:2 on 99"

    fb.scan(bReset=True)                 # CMD:2 fanned in by MAIN
    assert fb.eStep == Step.RECOVER_PUSH_RETR, \
        f"RESET went to {NAME[fb.eStep]} instead of homing"
    assert until(fb, Step.IDLE), "recovery did not reach IDLE"
    assert fb.iErrorCode == 0
    assert robot_reply(fb.state_out(True)) == 1, "robot should now start a bulb"
    fb.scan(bExtStartPulse=True)
    assert until(fb, Step.IDLE, limit=40)
    assert fb.nCyclesCompleted == 1


def t_reset_does_not_jump_to_idle():
    """RESET must produce motion towards home, never advertise ready early."""
    fb = Fb()
    fb.eStep = Step.ERR
    fb.iErrorCode = 5
    fb.scan(bReset=True)
    assert fb.eStep != Step.IDLE, "RESET advertised IDLE with pistons unknown"
    assert fb.eStep in RECOVER


def t_manual_disarms_and_auto_needs_start():
    fb = Fb()
    fb.scan(bStart=True)
    until(fb, Step.IDLE)
    fb.scan(bMachineAuto=False)
    assert fb.eStep == Step.NOT_HOMED
    assert fb.state_out(False) == 30, "Manual must report 30"
    # Back to Auto: still un-armed, robot cannot start.
    run(fb, 20, bExtStartPulse=True)
    assert fb.eStep == Step.NOT_HOMED, "Manual->Auto did not require a START"
    fb.scan(bStart=True)
    assert until(fb, Step.IDLE)


def t_err_survives_manual():
    fb = Fb()
    fb.eStep = Step.ERR
    fb.scan(bMachineAuto=False)
    assert fb.eStep == Step.ERR, "Manual cleared a latched fault"


def t_chain_exit_follows_flag():
    for flag, target in ((True, Step.IDLE), (False, Step.CHECK_PLATE)):
        fb = Fb()
        fb.eStep = Step.INIT_GRIP_RETRACTING
        fb.bHomeThenIdle = flag
        fb.scan()
        assert fb.eStep == target, \
            f"bHomeThenIdle={flag} exited to {NAME[fb.eStep]}, want {NAME[target]}"


TESTS = [
    ("boots into NOT_HOMED", t_boots_not_homed),
    ("robot cannot start an un-armed machine", t_robot_cannot_start_unarmed),
    ("operator START homes to IDLE", t_operator_start_homes_to_idle),
    ("START never runs a bulb cycle", t_start_never_runs_a_cycle),
    ("START is ignored in IDLE", t_start_is_ignored_in_idle),
    ("robot runs a cycle once armed", t_robot_runs_cycle_once_armed),
    ("stays armed across consecutive cycles", t_stays_armed_across_cycles),
    ("bContinuous cannot start a cycle", t_continuous_cannot_start),
    ("STOP disarms without faulting", t_stop_disarms_without_faulting),
    ("STOP survives a robot still asking", t_stop_survives_robot_pressure),
    ("STOP from IDLE disarms", t_stop_from_idle_disarms),
    ("ERR recovery is robot-driven", t_err_recovery_is_robot_driven),
    ("RESET does not jump to IDLE", t_reset_does_not_jump_to_idle),
    ("Manual disarms, Auto needs START", t_manual_disarms_and_auto_needs_start),
    ("ERR survives Manual", t_err_survives_manual),
    ("chain exit follows bHomeThenIdle", t_chain_exit_follows_flag),
]


def main():
    failed = 0
    for name, fn in TESTS:
        try:
            fn()
            print(f"PASS  {name}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL  {name}\n        {e}")
    print()
    print("ALL PASS" if not failed else f"{failed}/{len(TESTS)} FAILED")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
