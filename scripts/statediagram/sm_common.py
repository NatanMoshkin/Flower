"""Shared state/edge scaffolding for the three Auto state-machine diagrams.

The three pages must be comparable at a glance, so they all start from the same
row assignment and the same lane geometry — the only things that move are what
the variant genuinely changes.
"""

from sm_render import BOX_W, BUS_X, COL1_X, PAD_X, RAIL_A, RAIL_B, Edge, State

# key, label, wire value, class, row  — column 0, top to bottom
MAIN_ROWS = [
    ("NOT_HOMED", "NOT_HOMED", 40, "arm", 0),
    ("IDLE", "IDLE", 0, "arm", 1),
    ("INIT_PUSH", "INIT_PUSH_RETRACTING", 10, "init", 2),
    ("INIT_SEP", "INIT_SEP_RETRACTING", 11, "init", 3),
    ("INIT_GRIP", "INIT_GRIP_RETRACTING", 12, "init", 4),
    ("CHECK_PLATE", "CHECK_PLATE", 20, "wait", 5),
    ("GRIP_EXT", "GRIP_EXTENDING", 21, "cycle", 6),
    ("SEP_EXT", "SEP_EXTENDING", 1, "cycle", 7),
    ("PUSH_EXT", "PUSH_EXTENDING", 3, "cycle", 8),
    ("DWELL_PUSH", "DWELL_PUSH", 4, "cycle", 9),
    ("PUSH_RET", "PUSH_RETRACTING", 5, "cycle", 10),
    ("PUSH_RET_DW", "PUSH_RETRACTED_DWELL", 6, "cycle", 11),
    ("SEP_RET", "SEP_RETRACTING", 7, "cycle", 12),
    ("SEP_RET_DW", "SEP_RETRACTED_DWELL", 8, "cycle", 13),
    ("GRIP_RET", "GRIP_RETRACTING", 22, "cycle", 14),
]

SUBS = {
    "NOT_HOMED": "in Auto, NOT armed",
    "IDLE": "armed — awaiting CMD:1",
    "CHECK_PLATE": "tPlateWaitTimeoutMs",
    "DWELL_PUSH": "tDwellPushMs",
    "PUSH_RET_DW": "tPushRetractedDwellMs",
    "SEP_RET_DW": "tSepRetractedDwellMs",
}

# The nine movement states share tStepTimeoutMs; each has its own error code.
FAULTERS = [
    ("INIT_PUSH", 6), ("INIT_SEP", 7), ("INIT_GRIP", 8), ("CHECK_PLATE", 9),
    ("GRIP_EXT", 10), ("SEP_EXT", 1), ("PUSH_EXT", 3), ("PUSH_RET", 4),
    ("SEP_RET", 5), ("GRIP_RET", 11),
]

# One-line guards only — the vertical gap between boxes is 44 px.
CYCLE_CHAIN = [
    ("CHECK_PLATE", "GRIP_EXT", "bPlateOk   (L OR R)"),
    ("GRIP_EXT", "SEP_EXT", "grip extended   (L OR R)"),
    ("SEP_EXT", "PUSH_EXT", "all 3 sep extended"),
    ("PUSH_EXT", "DWELL_PUSH", "all 3 push extended"),
    ("DWELL_PUSH", "PUSH_RET", "dwell elapsed"),
    ("PUSH_RET", "PUSH_RET_DW", "all 3 push retracted"),
    ("PUSH_RET_DW", "SEP_RET", "dwell elapsed"),
    ("SEP_RET", "SEP_RET_DW", "all 3 sep retracted"),
    ("SEP_RET_DW", "GRIP_RET", "dwell elapsed"),
]


def main_states(relabel=None, reclass=None):
    """Column-0 states. `relabel` maps key -> new label for the rename variant."""
    relabel, reclass = relabel or {}, reclass or {}
    return [State(k, relabel.get(k, lb), v, reclass.get(k, c), 0, r,
                  sub=SUBS.get(k, ""))
            for k, lb, v, c, r in MAIN_ROWS]


def core_edges(by, err_key="ERR", fault_arrow_on=None,
               idle_start_rehome=True):
    """Everything common to all three diagrams: the homing chain, the bulb
    cycle, the cycle return, the fault bus and the two global overrides."""
    e = []
    fault_arrow_on = fault_arrow_on or FAULTERS[-1][0]

    # arming: START from NOT_HOMED, routed past IDLE on the inner rail
    e.append(Edge("NOT_HOMED:w", "INIT_PUSH:w", kind="op", label="START",
                  via=[(RAIL_A, by["NOT_HOMED"].cy), (RAIL_A, by["INIT_PUSH"].cy)],
                  label_at=(RAIL_A - 8, by["NOT_HOMED"].cy + 34), label_side="l"))

    # the two IDLE exits — the reason bHomeThenIdle exists
    e.append(Edge("IDLE:s", "INIT_PUSH:n", kind="seq", label="robot CMD:1"))
    # Removed from the machine 2026-08-05: START in IDLE now does nothing. The
    # archived proposal pages still show it, because it existed when they were
    # written.
    if idle_start_rehome:
        e.append(Edge("IDLE:e", "INIT_PUSH:e", kind="op", label="START (re-home)",
                      via=[(COL1_X + BOX_W + 40, by["IDLE"].cy),
                           (COL1_X + BOX_W + 40, by["INIT_PUSH"].cy)],
                      label_at=(COL1_X + BOX_W + 48, by["IDLE"].cy + 34),
                      label_side="r"))

    e.append(Edge("INIT_PUSH:s", "INIT_SEP:n", label="all 3 push retracted"))
    e.append(Edge("INIT_SEP:s", "INIT_GRIP:n", label="all 3 sep retracted"))

    # the fork
    e.append(Edge("INIT_GRIP:w", "IDLE:w", kind="op", label="home → armed",
                  via=[(RAIL_A, by["INIT_GRIP"].cy), (RAIL_A, by["IDLE"].cy)],
                  label_at=(RAIL_A - 8, by["INIT_GRIP"].cy - 26), label_side="l"))
    e.append(Edge("INIT_GRIP:s", "CHECK_PLATE:n", label="→ run the bulb"))

    for src, dst, lab in CYCLE_CHAIN:
        e.append(Edge(f"{src}:s", f"{dst}:n", label=lab))

    # cycle return on the outer rail, entering IDLE above its west port so it
    # does not land on the same pixel as the homing return
    e.append(Edge("GRIP_RET:w", "IDLE:w", kind="seq", label="nCyclesCompleted + 1",
                  via=[(RAIL_B, by["GRIP_RET"].cy), (RAIL_B, by["IDLE"].cy + 14),
                       (PAD_X, by["IDLE"].cy + 14)],
                  label_at=(RAIL_B - 8, by["GRIP_RET"].cy - 34), label_side="l"))

    # fault bus: ten spurs, one trunk, one arrowhead
    err = by[err_key]
    for k, code in FAULTERS:
        s = by[k]
        e.append(Edge(f"{k}:e", f"{err_key}:w", kind="fault",
                      arrow=(k == fault_arrow_on),
                      via=[(BUS_X, s.cy), (BUS_X, err.cy)],
                      label=str(code), label_at=(BUS_X - 8, s.cy - 6),
                      label_side="l"))

    # global overrides
    # Labels centred on the short horizontal run between the ghost box and
    # column 0; anything longer overlaps one box or the other, and both ghost
    # boxes already name their own condition in their sub-line.
    mid = (PAD_X + BOX_W + COL1_X) / 2
    e.append(Edge("STOP:w", "NOT_HOMED:e", kind="op", label="disarm",
                  label_at=(mid, by["STOP"].cy - 9), label_side="c"))
    e.append(Edge("MANUAL_IL:w", "NOT_HOMED:e", kind="op", label="re-park",
                  via=[(PAD_X + BOX_W + 30, by["MANUAL_IL"].cy),
                       (PAD_X + BOX_W + 30, by["NOT_HOMED"].cy)],
                  label_at=(mid + 14, by["MANUAL_IL"].cy - 9), label_side="c"))
    return e


def override_states(stop_row=0, manual_row=1):
    """The two global overrides as ghost boxes in column 1.

    manual_row is settable because the Pause variant needs column 1 row 1 for
    PAUSED — it belongs beside IDLE, not buried lower down. Moving the ghost to
    row 3 keeps its arrow in the empty gutter between the columns.
    """
    return [
        State("STOP", "STOP  — global override", None, "ghost", 1, stop_row,
              sub="from any state except ERR"),
        State("MANUAL_IL", "Manual  — global override", None, "ghost", 1,
              manual_row, sub="except NOT_HOMED and ERR"),
    ]


def _on(t):
    return f'<span class="cmd on">{t}</span>'


def _off(t):
    return f'<span class="cmd off">{t}</span>'


def _hold(t):
    return f'<span class="cmd hold">{t}</span>'


# Per-state command detail for the click-to-open popups, transcribed from
# FB_MasterAutoCycle Section 4's CASE bodies.
#
# Since 2026-08-05 every branch calls ResetAllCommands() and then re-asserts only
# what it owns, so "drives" is now the complete truth for a state -- there is no
# longer anything held by omission. The rows that used to say "holds" are kept as
# "was held" where the distinction explains an older reading of the code.
NONE_DRIVEN = _off("ResetAllCommands() only — all 10 FALSE")

COMMANDS = {
    "NOT_HOMED": [
        ("resets first + drives", NONE_DRIVEN),
        ("also clears", "iErrorCode := 0, sErrorText := ''"),
        ("timer", "none — falls to the Section 3 ELSE"),
        ("physically", "everything at its spring-return home, nothing energised"),
    ],
    "IDLE": [
        ("resets first + drives", NONE_DRIVEN),
        ("also clears", "iErrorCode := 0, sErrorText := ''"),
        ("timer", "none"),
        ("physically", "at rest and armed; the robot may command a bulb"),
    ],
    "INIT_PUSH": [
        ("resets first + drives", _on("bPushCmdRetract[1..3] := TRUE")),
        ("exit", "bAllPushRetracted (AND of all 3)"),
        ("timer", "tStepTimeoutMs → error 6"),
        ("physically", "push pins driving home on their springs"),
    ],
    "INIT_SEP": [
        ("resets first + drives", _on("bSepCmdRetract[1..3] := TRUE")),
        ("exit", "bAllSepRetracted (AND of all 3)"),
        ("timer", "tStepTimeoutMs → error 7"),
        ("physically", "push already home; separators retracting"),
    ],
    "INIT_GRIP": [
        ("resets first + drives", _on("bGripCmdRetract[1..2] := TRUE")),
        ("exit", "bAllGripRetracted — <strong>OR</strong>, not AND"),
        ("timer", "tStepTimeoutMs → error 8"),
        ("physically", "releasing the grippers; sep and push confirmed home"),
    ],
    "CHECK_PLATE": [
        ("drives", NONE_DRIVEN),
        ("exit", "bPlateOk = bPlateSenL <strong>OR</strong> bPlateSenR"),
        ("timer", "tPlateWaitTimeoutMs → error 9, suppressed by "
                  "bBypassPlateSensors (which then advances instead)"),
        ("physically", "nothing driven — but the robot arm is inside the "
                       "fixture placing the plate"),
    ],
    "GRIP_EXT": [
        ("resets first + drives", _on("bGripCmdExtend[1..2] := TRUE")),
        ("exit", "bAllGripExtended — <strong>OR</strong>, not AND"),
        ("timer", "tStepTimeoutMs → error 10"),
        ("physically", "grippers closing on the plate"),
    ],
    "SEP_EXT": [
        ("resets first + drives", _on("bSepCmdExtend[1..3] := TRUE")
                   + _on("bGripCmdExtend[1..2] := TRUE  (hold clamp)")),
        ("exit", "bAllSepExtended (AND of all 3)"),
        ("timer", "tStepTimeoutMs → error 1"),
        ("physically", "separator pins driving into the clamped plate"),
    ],
    "PUSH_EXT": [
        ("resets first + drives", _on("bSepCmdExtend[1..3] := TRUE  (hold out)")
                   + _on("bPushCmdExtend[1..3] := TRUE")
                   + _on("bGripCmdExtend[1..2] := TRUE")),
        ("exit", "bAllPushExtended (AND of all 3)"),
        ("timer", "tStepTimeoutMs → error 3"),
        ("physically", "<strong>the force stroke</strong> — pins being driven "
                       "into the bulb base"),
    ],
    "DWELL_PUSH": [
        ("resets first + drives", _on("bSepCmdExtend, bPushCmdExtend, bGripCmdExtend all TRUE")),
        ("exit", "tDwellPushMs elapsed"),
        ("timer", "tDwellPushMs — a dwell, not a timeout. No error path."),
        ("physically", "everything held out against hard stops, full pin load"),
    ],
    "PUSH_RET": [
        ("resets first + drives", _on("bSepCmdExtend[1..3] := TRUE  (sep stays out)")
                   + _on("bPushCmdRetract[1..3] := TRUE")
                   + _on("bGripCmdExtend[1..2] := TRUE")
                   + _off("Push ext := FALSE")),
        ("exit", "bAllPushRetracted (AND of all 3)"),
        ("timer", "tStepTimeoutMs → error 4"),
        ("physically", "push retracting on its springs, separators still out"),
    ],
    "PUSH_RET_DW": [
        ("resets first + drives", _on("bSepCmdExtend[1..3] := TRUE")
                   + _on("bGripCmdExtend[1..2] := TRUE")),
        ("exit", "tPushRetractedDwellMs elapsed"),
        ("timer", "dwell, no error path"),
        ("physically", "push home, separators held out, plate clamped"),
    ],
    "SEP_RET": [
        ("resets first + drives", _on("bSepCmdRetract[1..3] := TRUE")
                   + _on("bGripCmdExtend[1..2] := TRUE")
                   + _off("Sep ext := FALSE")),
        ("exit", "bAllSepRetracted (AND of all 3)"),
        ("timer", "tStepTimeoutMs → error 5"),
        ("physically", "separators retracting, plate still clamped"),
    ],
    "SEP_RET_DW": [
        ("resets first + drives", _on("bGripCmdExtend[1..2] := TRUE")),
        ("exit", "tSepRetractedDwellMs elapsed"),
        ("timer", "dwell, no error path"),
        ("physically", "sep and push home; only the clamp still holding"),
    ],
    "GRIP_RET": [
        ("resets first + drives", _on("bGripCmdRetract[1..2] := TRUE")),
        ("exit", "bAllGripRetracted — <strong>OR</strong>, not AND. "
                 "Then nCyclesCompleted + 1"),
        ("timer", "tStepTimeoutMs → error 11"),
        ("physically", "releasing the plate — last motion of the bulb"),
    ],
    "REC_PUSH": [
        ("resets first + drives", _on("bPushCmdRetract[1..3] := TRUE")),
        ("exit", "bAllPushRetracted (AND of all 3)"),
        ("timer", "tStepTimeoutMs → <strong>error 12</strong> — distinct from "
                  "arming's error 6, which is the whole point of this chain"),
        ("physically", "push pins driving home on their springs, recovering "
                       "from a fault"),
    ],
    "REC_SEP": [
        ("resets first + drives", _on("bSepCmdRetract[1..3] := TRUE")),
        ("exit", "bAllSepRetracted (AND of all 3)"),
        ("timer", "tStepTimeoutMs → <strong>error 13</strong>"),
        ("physically", "push already home; separators retracting"),
    ],
    "REC_GRIP": [
        ("resets first + drives", _on("bGripCmdRetract[1..2] := TRUE")),
        ("exit", "bAllGripRetracted — <strong>OR</strong>, not AND → IDLE"),
        ("timer", "tStepTimeoutMs → <strong>error 14</strong>"),
        ("physically", "releasing the grippers; sep and push confirmed home"),
        ("why IDLE", "the machine really IS homed at this point, so advertising "
                     "STATE:0 to the robot is honest"),
    ],
    "ERR": [
        ("resets first + drives", NONE_DRIVEN),
        ("exit", "only Section 2 RESET — HMI button, orange PB2, or robot "
                 "CMD:2 → enters RECOVER_PUSH_RETR"),
        ("timer", "none"),
        ("physically", "coils dropped, so every piston has spring-returned "
                       "home. The plate is released."),
    ],
}


# Proposed states have no source to transcribe, so their popups describe what
# they WOULD drive — flagged as proposed so nobody mistakes them for existing
# behaviour.
PROPOSED = {
    "PAUSED": [
        ("proposed", "<strong>Wire value only — never assigned to eStep.</strong>"),
        ("drives", "nothing of its own. The interrupted step keeps asserting its "
                   "own coil pattern every scan."),
        ("emitted by", "MAIN's nStateOut computation, exactly like the existing "
                       "MANUAL = 30 sentinel"),
        ("robot sees", "STATE:41 → falls into &ldquo;anything else&rdquo; → CMD:0 "
                       "(wait). No robot-side branch needed."),
        ("leaves on", "PB2 again (Continue), START, STOP, Manual, or entering ERR"),
    ],
}


def _pb(t):
    return f'<span class="cmd on">{t}</span>'


def _pbno(t):
    return f'<span class="cmd off">{t}</span>'


# What the three panel buttons do IN THIS STATE, verified against MAIN's gates
# and FB Section 2/4:
#   PB1 held  -> bStop.  Section 2 acts in EVERY state except ERR.
#   PB2 edge  -> bReset, but MAIN gates it on eStep = ERR, so ERR only.
#   PB3 edge  -> bStart. Consumed by the NOT_HOMED and IDLE branches ONLY;
#                everywhere else it is auto-cleared and merely LOGGED.
#   PB2+PB3   -> bExtStartPulse. Consumed by the IDLE branch only.
_STOP_WORKS = _pb("PB1 held → STOP, disarms to NOT_HOMED")
_START_LOGGED = _pbno("PB3 → logs 'START pressed', no effect here")
_NO_RESET = _pbno("PB2 → nothing (RESET is ERR-only)")
_NO_COMBO = _pbno("PB2+PB3 → nothing (bulb start is IDLE-only)")

OPERATOR = {
    "NOT_HOMED": [
        (_pb("PB3 → START: home the pistons and ARM") + _pbno(
            "PB1 held → STOP, but already disarmed — no change") + _NO_RESET
         + _NO_COMBO)],
    "IDLE": [
        (_pb("PB2+PB3 held → run ONE bulb (= robot CMD:1)")
         + _pbno("PB3 alone → logs 'START pressed', no effect: already armed")
         + _STOP_WORKS + _NO_RESET)],
    "ERR": [
        (_pb("PB2 → RESET: enter the RECOVER chain")
         + _pbno("PB1 held → nothing: STOP is excluded from ERR")
         + _START_LOGGED + _NO_COMBO)],
    "_MOTION": [
        (_STOP_WORKS + _START_LOGGED + _NO_RESET + _NO_COMBO)],
    "_RECOVER": [
        (_pb("PB1 held → STOP, which ABORTS the recovery → NOT_HOMED")
         + _START_LOGGED + _NO_RESET + _NO_COMBO)],
}

MOTION_KEYS = ["INIT_PUSH", "INIT_SEP", "INIT_GRIP", "CHECK_PLATE", "GRIP_EXT",
               "SEP_EXT", "PUSH_EXT", "DWELL_PUSH", "PUSH_RET", "PUSH_RET_DW",
               "SEP_RET", "SEP_RET_DW", "GRIP_RET"]
RECOVER_KEYS = ["REC_PUSH", "REC_SEP", "REC_GRIP"]


def operator_rows():
    """key -> [(label, html)] describing the panel buttons in that state."""
    out = {}
    for k in ("NOT_HOMED", "IDLE", "ERR"):
        out[k] = [("panel buttons", OPERATOR[k][0])]
    for k in MOTION_KEYS:
        out[k] = [("panel buttons", OPERATOR["_MOTION"][0])]
    for k in RECOVER_KEYS:
        out[k] = [("panel buttons", OPERATOR["_RECOVER"][0])]
    return out


def info_for(key, extra=None):
    """Popup payload for a state, optionally with variant-specific extra rows."""
    rows = list(COMMANDS.get(key) or PROPOSED.get(key) or [])
    if extra:
        rows += extra
    return {"rows": [[a, b] for a, b in rows]} if rows else {}


def attach_info(states, extras=None):
    """Bolt popup data onto every state that has any. Mutates and returns."""
    extras = extras or {}
    for s in states:
        data = info_for(s.key, extras.get(s.key))
        if data:
            data["title"] = s.label
            s.info = data
    return states


ROBOT_TABLE = """
<div class="tblwrap"><table>
<thead><tr><th>STATE:&lt;n&gt;</th><th>Robot replies</th><th>Meaning</th></tr></thead>
<tbody>
<tr><td class="m">0</td><td class="m">CMD:1</td><td>armed — start one bulb</td></tr>
<tr><td class="m">99</td><td class="m">CMD:2</td><td>faulted — reset it</td></tr>
<tr><td class="m">anything else</td><td class="m">CMD:0</td><td>wait</td></tr>
</tbody></table></div>
<p>That last row is why <strong>adding</strong> a state is nearly free — any value
the robot does not recognise falls into &ldquo;wait&rdquo;, the safe default — and
why <strong>renumbering</strong> one is not. It is also why <code>NOT_HOMED = 40</code>
needed no robot-side change when it was introduced.</p>
"""
