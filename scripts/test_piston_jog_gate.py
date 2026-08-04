"""Port of FB_SolSpringPiston_2Pos Sections 0/1/1a/1c/2 -- the solenoid ladder --
to prove the bJogEnable gate (PB jog while latched in ERR, 2026-08-04).

Why this exists: the ladder RETAINS the coil when no branch matches, so the
release branch is the only thing that brings a momentary push-button home. If
that branch's gate does not match the jog branches' gate exactly, the first PB
press in ERR strands the piston EXTENDED on an already-faulted machine, with no
panel-side way back. That is worth more than a hand-trace.

Same approach as scripts/test_master_cycle_arming.py: it validates the
*algorithm*, not the ST build. A TwinCAT compile is still required.

Run:  python scripts/test_piston_jog_gate.py
Exit: 0 = ladder behaves as specified, 1 = drift found.
"""

MANUAL, AUTOMATIC = 0, 1
RETAIN = "retain"          # no branch matched; VAR_OUTPUT keeps its value


class Piston:
    """One FB_SolSpringPiston_2Pos instance, scan by scan."""

    def __init__(self):
        self.coil = False              # bOutSolenoid
        self.sel_extend = False        # stHmi.bSelectedExtend
        self.sel_retract = False       # stHmi.bSelectedRetract
        self._prev_jog = False         # fbTrigJogRelease's F_TRIG memory

    def scan(self, *, eMode, bJogExtend=False, bJogEnable=False,
             bManJogExtend=False, bManJogRetract=False,
             bAutoCmdExtend=False, bAutoCmdRetract=False,
             bSwitchExtended=False, bSwitchRetracted=False):
        # --- 0a. effective sensors (no simulate flags in this model) ---
        ext_eff, ret_eff = bSwitchExtended, bSwitchRetracted

        # --- 0. HMI radio latching; force-cleared while Automatic ---
        if eMode == AUTOMATIC:
            self.sel_extend = self.sel_retract = False

        # --- 1. mode selection & command mapping ---
        if eMode == AUTOMATIC:
            tgt_extend = bAutoCmdExtend and not bAutoCmdRetract
            tgt_retract = bAutoCmdRetract and not bAutoCmdExtend
        elif eMode == MANUAL:
            tgt_extend, tgt_retract = self.sel_extend, self.sel_retract
        else:
            tgt_extend = tgt_retract = False

        # --- 1a. jog override clears latched selection ---
        if bManJogExtend or bManJogRetract or bJogExtend:
            self.sel_extend = self.sel_retract = False

        # --- 1b. target-reached reset ---
        if self.sel_extend and ext_eff:
            self.sel_extend = False
        if self.sel_retract and ret_eff:
            self.sel_retract = False

        # --- 1c. panel jog release edge (F_TRIG, called unconditionally) ---
        jog_release = self._prev_jog and not bJogExtend
        self._prev_jog = bJogExtend

        # --- 2. solenoid control: LATCH-and-RETAIN, no ELSE ---
        jog_allowed = (eMode == MANUAL) or bJogEnable
        if (bManJogExtend or bJogExtend) and jog_allowed:
            self.coil, branch = True, "jog-extend"
        elif bManJogRetract and jog_allowed:
            self.coil, branch = False, "jog-retract"
        elif jog_release and jog_allowed:
            self.coil, branch = False, "jog-release"
        elif tgt_extend:
            self.coil, branch = True, "target-extend"
        elif tgt_retract:
            self.coil, branch = False, "target-retract"
        else:
            branch = RETAIN
        return branch


FAILURES = []


def check(label, got, want):
    ok = got == want
    print(f"  [{'ok ' if ok else 'FAIL'}] {label}: coil={got}, expected {want}")
    if not ok:
        FAILURES.append(label)


def case(title):
    print(f"\n{title}")


# ---------------------------------------------------------------- unchanged
case("Manual jog is unchanged by the new input")
p = Piston()
p.scan(eMode=MANUAL, bJogExtend=True)
check("PB held in Manual energises", p.coil, True)
p.scan(eMode=MANUAL, bJogExtend=False)
check("PB released in Manual drops the coil", p.coil, False)

case("Automatic without the ERR window still ignores the PB (the safety default)")
p = Piston()
br = p.scan(eMode=AUTOMATIC, bJogExtend=True, bJogEnable=False)
check("PB held in Auto does nothing", p.coil, False)
assert br == RETAIN, f"expected no branch to match, got {br}"
p.scan(eMode=AUTOMATIC, bAutoCmdExtend=True)
check("master cycle can still extend in Auto", p.coil, True)
p.scan(eMode=AUTOMATIC, bAutoCmdRetract=True)
check("master cycle can still retract in Auto", p.coil, False)

# --------------------------------------------------------------------- new
case("ERR window: PB jog works in Automatic")
p = Piston()
p.scan(eMode=AUTOMATIC, bJogExtend=True, bJogEnable=True)
check("PB held in Auto+ERR energises", p.coil, True)

case("ERR window: RELEASING must drop the coil -- the whole point of the gate")
p = Piston()
p.scan(eMode=AUTOMATIC, bJogExtend=True, bJogEnable=True)
br = p.scan(eMode=AUTOMATIC, bJogExtend=False, bJogEnable=True)
check("PB released in Auto+ERR retracts", p.coil, False)
assert br == "jog-release", f"expected the release branch, got {br}"

case("ERR window: held across several scans, then released")
p = Piston()
for _ in range(5):
    p.scan(eMode=AUTOMATIC, bJogExtend=True, bJogEnable=True)
check("still energised while held", p.coil, True)
p.scan(eMode=AUTOMATIC, bJogExtend=False, bJogEnable=True)
check("home once released", p.coil, False)

case("ERR window: extended sensor arriving does NOT drop the coil mid-jog")
p = Piston()
p.scan(eMode=AUTOMATIC, bJogExtend=True, bJogEnable=True)
p.scan(eMode=AUTOMATIC, bJogExtend=True, bJogEnable=True, bSwitchExtended=True)
check("coil holds at the extended limit", p.coil, True)

case("ERR window opens the HMI jog too, and bManJogRetract undoes it")
p = Piston()
p.scan(eMode=AUTOMATIC, bManJogExtend=True, bJogEnable=True)
check("HMI jog-extend energises in Auto+ERR", p.coil, True)
p.scan(eMode=AUTOMATIC, bManJogRetract=True, bJogEnable=True)
check("HMI jog-retract de-energises", p.coil, False)

case("ERR window does NOT revive the HMI Extend/Retract radio buttons")
p = Piston()
p.sel_extend = True                      # as if a stale selection survived
br = p.scan(eMode=AUTOMATIC, bJogEnable=True)
check("latched HMI selection stays dead", p.coil, False)
assert br == RETAIN, f"selection must not reach a branch, got {br}"
assert not p.sel_extend, "Section 0 must force-clear bSelectedExtend in Auto"

case("Leaving ERR while the PB is still held (RESET pressed mid-jog)")
# MAIN drives bJogExtend from (bManualMode OR bErrJogEnable) AND bPbN, so when
# bErrJogEnable drops the same scan, bJogExtend goes FALSE with the PB still down.
p = Piston()
p.scan(eMode=AUTOMATIC, bJogExtend=True, bJogEnable=True)
br = p.scan(eMode=AUTOMATIC, bJogExtend=False, bJogEnable=False)
check("release branch is gated off, coil RETAINS", p.coil, True)
assert br == RETAIN, f"expected retain, got {br}"
# ...and the homing chain is what takes it home, two states later.
p.scan(eMode=AUTOMATIC, bAutoCmdRetract=True)
check("INIT_GRIP_RETRACTING brings it home", p.coil, False)

case("Manual -> Auto switch with the PB held (the pre-existing case)")
p = Piston()
p.scan(eMode=MANUAL, bJogExtend=True)
br = p.scan(eMode=AUTOMATIC, bJogExtend=False, bJogEnable=False)
check("release gated off, coil RETAINS", p.coil, True)
assert br == RETAIN, f"expected retain, got {br}"
p.scan(eMode=AUTOMATIC, bAutoCmdRetract=True)
check("master cycle's INIT retract takes it home", p.coil, False)

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED: " + ", ".join(FAILURES))
    raise SystemExit(1)
print("all jog-gate cases pass")
