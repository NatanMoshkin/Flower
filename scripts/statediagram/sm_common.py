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
    ("WAIT_PLATE", "WAIT_PLATE", 20, "wait", 5),
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
    "IDLE": "armed — robot may send CMD:1",
    "WAIT_PLATE": "tPlateWaitTimeoutMs",
    "DWELL_PUSH": "tDwellPushMs",
    "PUSH_RET_DW": "tPushRetractedDwellMs",
    "SEP_RET_DW": "tSepRetractedDwellMs",
}

# The nine movement states share tStepTimeoutMs; each has its own error code.
FAULTERS = [
    ("INIT_PUSH", 6), ("INIT_SEP", 7), ("INIT_GRIP", 8), ("WAIT_PLATE", 9),
    ("GRIP_EXT", 10), ("SEP_EXT", 1), ("PUSH_EXT", 3), ("PUSH_RET", 4),
    ("SEP_RET", 5), ("GRIP_RET", 11),
]

# One-line guards only — the vertical gap between boxes is 44 px.
CYCLE_CHAIN = [
    ("WAIT_PLATE", "GRIP_EXT", "bPlateOk   (L OR R)"),
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


def core_edges(by, err_key="ERR", fault_arrow_on=None):
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
    e.append(Edge("IDLE:e", "INIT_PUSH:e", kind="op", label="START (re-home)",
                  via=[(COL1_X + BOX_W + 40, by["IDLE"].cy),
                       (COL1_X + BOX_W + 40, by["INIT_PUSH"].cy)],
                  label_at=(COL1_X + BOX_W + 48, by["IDLE"].cy + 34), label_side="r"))

    e.append(Edge("INIT_PUSH:s", "INIT_SEP:n", label="all 3 push retracted"))
    e.append(Edge("INIT_SEP:s", "INIT_GRIP:n", label="all 3 sep retracted"))

    # the fork
    e.append(Edge("INIT_GRIP:w", "IDLE:w", kind="op", label="home → armed",
                  via=[(RAIL_A, by["INIT_GRIP"].cy), (RAIL_A, by["IDLE"].cy)],
                  label_at=(RAIL_A - 8, by["INIT_GRIP"].cy - 26), label_side="l"))
    e.append(Edge("INIT_GRIP:s", "WAIT_PLATE:n", label="→ run the bulb"))

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
