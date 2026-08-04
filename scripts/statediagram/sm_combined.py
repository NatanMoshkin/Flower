"""COMBINED TARGET: per-step Pause/Continue + separate Retract-all + a manual
window in STOP and ERR, on one state machine.

This is the page to implement from. The other three are the pieces.
"""

from sm_common import (
    ROBOT_TABLE, attach_info, core_edges, main_states, override_states,
)
from sm_render import BOX_W, Edge, State, legend_html, page, render_svg

RENAME = {
    "INIT_PUSH": "RETRACT_ALL_PUSH",
    "INIT_SEP": "RETRACT_ALL_SEP",
    "INIT_GRIP": "RETRACT_ALL_GRIP",
}
RECOVER = [
    ("REC_PUSH", "RECOVER_PUSH_RETR", 50, 12, 16),
    ("REC_SEP", "RECOVER_SEP_RETR", 51, 13, 17),
    ("REC_GRIP", "RECOVER_GRIP_RETR", 52, 14, 18),
]
for _n in list(RENAME.values()) + [r[1] for r in RECOVER]:
    assert len(_n) <= 20, f"{_n} is {len(_n)} chars — sStepText would truncate"

# Which states admit which operator input, in the combined design.
PAUSABLE = ["IDLE", "INIT_PUSH", "INIT_SEP", "INIT_GRIP", "WAIT_PLATE",
            "GRIP_EXT", "SEP_EXT", "PUSH_EXT", "PUSH_RET", "PUSH_RET_DW",
            "SEP_RET", "SEP_RET_DW", "GRIP_RET"]
MANUAL_OK = ["NOT_HOMED", "ERR"]

EXTRAS = {}
for _k in PAUSABLE:
    EXTRAS[_k] = [("operator", "<strong>Pause</strong> (PB2) — holds at this "
                               "step's boundary. Manual commands blocked.")]
EXTRAS["DWELL_PUSH"] = [("operator", "<strong>Pause excluded</strong> — the "
                                     "guard is 'dwell elapsed', so holding here "
                                     "keeps full pin load applied indefinitely. "
                                     "Pause takes effect one step later.")]
for _k in MANUAL_OK:
    EXTRAS[_k] = [("operator", "<strong>Manual commands LIVE</strong> — PB1 grip "
                               "and PB2 sep jog"
                               + (", PB3 push jog" if _k == "ERR"
                                  else "; PB3 stays START")
                               + ". Pause rejected.")]


def build_states():
    states = main_states(relabel=RENAME) + override_states(manual_row=3)
    states.append(State("ERR", "ERR", 99, "fault", 1, 15,
                        sub="latched — manual live"))
    states.append(State("PAUSED", "PAUSED — wire value only", 41, "new", 1, 1,
                        sub="nStateOut only"))
    for k, name, val, code, row in RECOVER:
        states.append(State(k, name, val, "new", 1, row,
                            sub=f"timeout → error {code}"))
    return attach_info(states, extras=EXTRAS)


def build_edges(states):
    by = {s.key: s for s in states}
    e = core_edges(by)

    # Recovery gets its own chain, so ERR stays latched while a human works.
    e.append(Edge("ERR:s", "REC_PUSH:n", kind="new",
                  label="RESET — operator, or robot CMD:2 (attempts < 3)"))
    e.append(Edge("REC_PUSH:s", "REC_SEP:n", kind="new", label="push retracted"))
    e.append(Edge("REC_SEP:s", "REC_GRIP:n", kind="new", label="sep retracted"))
    e.append(Edge("REC_GRIP:e", "IDLE:e", kind="new", label="grip retracted → armed",
                  via=[(by["REC_GRIP"].x + BOX_W + 46, by["REC_GRIP"].cy),
                       (by["REC_GRIP"].x + BOX_W + 46, by["IDLE"].cy - 16),
                       (by["IDLE"].x + BOX_W + 18, by["IDLE"].cy - 16),
                       (by["IDLE"].x + BOX_W + 18, by["IDLE"].cy)],
                  label_at=(by["REC_GRIP"].x + BOX_W + 54, by["REC_GRIP"].cy - 20),
                  label_side="r"))
    e.append(Edge("REC_GRIP:w", "ERR:w", kind="fault",
                  label="retry ≥ 3 → latch ERR,\nrefuse the robot's CMD:2",
                  via=[(by["REC_GRIP"].x - 34, by["REC_GRIP"].cy),
                       (by["REC_GRIP"].x - 34, by["ERR"].cy - 30),
                       (by["ERR"].x - 18, by["ERR"].cy - 30),
                       (by["ERR"].x - 18, by["ERR"].cy)],
                  label_at=(by["REC_GRIP"].x - 42, by["REC_GRIP"].cy + 26),
                  label_side="l"))
    e.append(Edge("IDLE:e", "PAUSED:w", kind="new", label="PB2",
                  label_at=(by["PAUSED"].x - 26, by["IDLE"].cy - 9),
                  label_side="l"))
    return e


BODY = """
<h2>Everything at once</h2>
<p>Four changes on one machine. Purple is new or renamed; everything else is
unchanged from <a href="auto-state-machine-current.html">today</a>.</p>

{diagram}
{legend}
<p class="pophint">Click any state box for its commands, and for which operator
inputs that state accepts.</p>

<h2>The four changes</h2>
<div class="tblwrap"><table>
<thead><tr><th>#</th><th>Change</th><th>Cost</th></tr></thead>
<tbody>
<tr><td class="m">1</td>
    <td><strong>Per-step Pause / Continue</strong> on PB2, holding at the step
    boundary once the exit guard is satisfied. <code>eStep</code> unchanged;
    <code>PAUSED (41)</code> emitted from <code>nStateOut</code>.</td>
    <td>One term per pausable state, one timer guard, one enum value, one MAIN
    override, PB2 + LED2.</td></tr>
<tr><td class="m">2</td>
    <td><strong>Retract-all split from ERR.</strong> The shared chain is
    <em>renamed</em> <code>RETRACT_ALL_*</code> keeping 10/11/12; recovery gets
    its own <code>RECOVER_*</code> 50/51/52 with error codes 12/13/14.</td>
    <td>3 enum values, 3 CASE branches, 3 error codes. Wire semantics
    unchanged — every new value lands in the robot's &ldquo;wait&rdquo;.</td></tr>
<tr><td class="m">3</td>
    <td><strong>Manual commands in STOP and ERR.</strong> The existing
    <code>bJogEnable</code> window widens from <code>ERR</code> only to
    <code>ERR</code> <em>and</em> <code>NOT_HOMED</code> — which is where STOP
    puts the machine.</td>
    <td>One condition in MAIN. Already-proven mechanism.</td></tr>
<tr><td class="m">4</td>
    <td><strong>Retry counter + reset ownership</strong>, and the unsafe
    <code>CASE ELSE</code> fixed to land on <code>NOT_HOMED</code>.</td>
    <td>A counter, splitting <code>bReset</code>, two lines for the ELSE.</td></tr>
</tbody></table></div>

<div class="callout good">
<h3>The three features reinforce each other — this is not just a bundle</h3>
<p><strong>Separating <code>RECOVER_*</code> is what makes the manual window
correct.</strong> Today the window is <code>eStep = ERR</code>, and ERR is
transient in production — the robot resets it in about a second, so the operator's
jog window slams shut. With recovery in its own states, <code>ERR</code> stays
latched as a genuine &ldquo;stopped, waiting for a decision&rdquo; state while the
<em>motion</em> happens in <code>RECOVER_*</code> — where jogs are correctly
<em>off</em>, because the machine is moving.</p>
<p><strong>The retry counter is what stops the window closing anyway.</strong>
After 3 failed recovery attempts the machine latches <code>ERR</code> and refuses
the robot's <code>CMD:2</code>, so the operator gets an indefinite window instead
of a 10-second one. That needs <code>bReset</code> split into operator-vs-robot,
which is the same change.</p>
<p><strong>And Pause makes the whole thing usable without a fault.</strong> Today
the only way to get hands-on is to cause or wait for an <code>ERR</code>, or to
switch to Manual and lose the arming. Pause &rarr; STOP &rarr; manual work &rarr;
START is a clean operator path that never involves a fault at all.</p>
</div>

<h2>Operator inputs, per machine condition</h2>
<p>This is the whole panel contract in one table. Note it stays a
<strong>partition</strong> — no state accepts both a jog and a Pause, so no
priority scheme is needed.</p>
<div class="tblwrap"><table>
<thead><tr><th>Condition</th><th>PB1 (red)</th><th>PB2 (orange)</th>
<th>PB3 (green)</th><th>HMI</th></tr></thead>
<tbody>
<tr><td>Manual</td><td>grip jog</td><td>sep jog</td><td>push jog</td>
    <td>per-piston Extend/Retract</td></tr>
<tr><td><code>NOT_HOMED</code> — incl. after STOP <span class="mono">(new)</span></td>
    <td><strong>grip jog</strong></td><td><strong>sep jog</strong></td>
    <td>START</td><td><strong>jog buttons</strong></td></tr>
<tr><td><code>ERR</code> latched</td><td>grip jog</td><td>sep jog</td>
    <td>push jog</td><td>jog buttons</td></tr>
<tr><td><code>RECOVER_*</code> — moving <span class="mono">(new)</span></td>
    <td>—</td><td>—</td><td>—</td><td>—</td></tr>
<tr><td><code>IDLE</code> and all cycle steps</td><td>—</td>
    <td><strong>Pause / Continue</strong></td>
    <td>START (re-home, from IDLE)</td><td>START / STOP / RESET</td></tr>
<tr><td>Paused</td><td>—</td><td><strong>Continue</strong></td><td>START</td>
    <td>START / STOP</td></tr>
</tbody></table></div>

<div class="callout bad">
<h3>The one unavoidable conflict: PB3 in NOT_HOMED</h3>
<p><code>NOT_HOMED</code> is where STOP puts the machine, so it is exactly where
an operator wants to jog. But PB3 is <strong>START</strong> there, and its LED is
blinking the &ldquo;press me to arm&rdquo; prompt. One button cannot be both.</p>
<p>Three ways out, in preference order:</p>
<ul>
<li><strong>Recommended: PB1 and PB2 jog in <code>NOT_HOMED</code>; PB3 stays
START.</strong> Grip and sep are reachable, and the push jog is still available
from <code>ERR</code> or from Manual. Costs nothing, breaks nothing, and keeps
the only physical arm button.</li>
<li>PB3 jogs push in <code>NOT_HOMED</code> and arming moves to the HMI START
button only. Symmetric, but it removes the physical arm button and silences a
prompt operators have been trained on.</li>
<li>Long-press PB3 = START, short-press = jog. Discoverable by nobody, and a
timing-dependent safety-adjacent control. Not recommended.</li>
</ul>
<p><strong>This one needs your call</strong> — it is the only place in the combined
design where two operator intents genuinely compete for one input.</p>
</div>

<h2>Should the HMI per-piston buttons work too?</h2>
<p>&ldquo;Manual commands&rdquo; can mean just the PB jogs, or also the
Extend/Retract controls on the Piston page. The PB jogs already ride
<code>bJogEnable</code>. The HMI ones do not, because <code>MAIN</code> forces
<code>eMode := Automatic</code> and Section 0 of the piston FB then force-clears
<code>bSelectedExtend</code>/<code>bSelectedRetract</code> every scan.</p>
<p>Enabling them means relaxing that force-clear to
<code>IF eMode = Automatic AND NOT bJogEnable THEN clear</code>. Doable, but note
the asymmetry: <strong>the HMI jog latches</strong> (that is deliberate —
<code>bManJogRetract</code> sits next to it) whereas a PB jog releases when you
let go. So a latched HMI Extend would survive into the resumed sequence unless
<code>bSelected*</code> is cleared on leaving the window.</p>
<p><strong>Recommendation:</strong> enable the HMI <em>jog</em> buttons
(<code>bManJogExtend</code>, which already shares the gate) and leave the latching
Extend/Retract radio selections dead. Same capability, none of the latch hazard.</p>

<h2>Enum plan — reserve it all in one commit</h2>
<div class="tblwrap"><table>
<thead><tr><th>Value</th><th>Name</th><th>Status</th></tr></thead>
<tbody>
<tr><td class="m">0, 1, 3–8, 10–12, 20–22</td><td class="m">existing steps</td>
    <td><strong>renamed only</strong> for 10/11/12 — never renumbered</td></tr>
<tr><td class="m">2</td><td class="m">WAIT_POS2</td>
    <td>retired; do not reuse (old logs and CSV exports carry it)</td></tr>
<tr><td class="m">30</td><td class="m">MANUAL</td>
    <td>sentinel, MAIN emits it directly; never assigned to <code>eStep</code></td></tr>
<tr><td class="m">40</td><td class="m">NOT_HOMED</td><td>existing</td></tr>
<tr><td class="m">41</td><td class="m">PAUSED</td>
    <td><strong>new</strong> — wire value only, emitted from <code>nStateOut</code></td></tr>
<tr><td class="m">50 / 51 / 52</td><td class="m">RECOVER_PUSH / SEP / GRIP</td>
    <td><strong>new</strong> — real assigned states</td></tr>
<tr><td class="m">99</td><td class="m">ERR</td><td>existing; part of the protocol</td></tr>
</tbody></table></div>
<p><code>iErrorCode</code> is a separate namespace: 0, 1, 3–11 used, 2 and 99
retired, <strong>12/13/14 free</strong> for the recovery timeouts.</p>
{robot}

<div class="callout bad">
<h3>Verify against the real robot before shipping any new value</h3>
<p>The &ldquo;anything else &rarr; wait&rdquo; branch is a <em>documented</em>
contract, confirmed only against the two Python mocks in this repo. The machine
runs an <strong>uncommitted</strong> <code>src2.lua</code>. Commit it, or at
minimum read the running copy off the controller, before relying on
<code>41</code> or <code>5x</code>. Both mocks print <code>?</code> for an unknown
value, so a missed table update is cosmetic rather than a crash — but the real
Lua has not been read.</p>
</div>

<h2>Implementation order</h2>
<ol>
<li><strong>The unsafe <code>CASE ELSE</code></strong> &rarr; <code>NOT_HOMED</code>.
Alone, first, two lines. Also delete the dead <code>bAnyRunning</code> or fix its
comment while in the file.</li>
<li><strong><code>bHomeThenIdle</code> &rarr; <code>eReturnTo :
E_MasterAutoStep</code>.</strong> Zero wire risk, and it flips the fail-safe
default: an uninitialised BOOL means &ldquo;run a bulb&rdquo;, an uninitialised
enum means <code>IDLE</code>.</li>
<li><strong>One enum commit</strong> reserving <code>PAUSED (41)</code> and
<code>RECOVER_* (50/51/52)</code> together, so the robot contract changes once and
needs one verification trip.</li>
<li><strong>Widen the manual window</strong> to <code>NOT_HOMED</code> — one
condition in MAIN, and the smallest useful change on this page. Ships
independently of everything else.</li>
<li><strong><code>RECOVER_*</code> branches</strong> + error codes 12/13/14 +
the rename + the retry counter + the <code>bReset</code> split. Do not ship the
rename without the counter.</li>
<li><strong>Per-step Pause / Continue</strong> last, with its own resume state
held in <code>eStep</code> and its flag in <code>GVL_HMI</code>. Do not let it
reuse <code>eReturnTo</code> — that repeats the <code>bHomeThenIdle</code>
mistake one level up.</li>
</ol>
<p>Steps 1, 2 and 4 are each independently shippable and carry no wire risk;
they are worth doing first regardless of what happens to 5 and 6.</p>

<h2>What the test harnesses will need</h2>
<ul>
<li><code>scripts/test_master_cycle_arming.py</code> — the arming transitions.
Add: pause rejected from <code>NOT_HOMED</code> and <code>ERR</code>, STOP clears
the pause, a paused <code>IDLE</code> refuses <code>CMD:1</code>, and the recovery
chain's exit and escalation.</li>
<li><code>scripts/test_piston_jog_gate.py</code> — the solenoid ladder. Add the
widened window: jog allowed in <code>NOT_HOMED</code>, still refused in
<code>IDLE</code> and in <code>RECOVER_*</code>.</li>
<li><code>scripts/pb_test/</code> — the live-PLC harness. Two existing rules
apply: drive <code>GVL_IO.dIn[14]</code>, never <code>GVL_App.bPb2</code>; and
read transition paths from <code>GVL_Log</code>, never by polling
<code>eStep</code>.</li>
<li><code>scripts/mock_robot/mock_robot.py</code> — teach <code>STATE_NAMES</code>
the values 41 and 50/51/52 so bench traces stay readable.</li>
</ul>
"""


def build():
    states = build_states()
    svg, _, _ = render_svg(states, build_edges(states))
    body = BODY.format(diagram=f'<div class="diagram">{svg}</div>',
                       legend=legend_html(), robot=ROBOT_TABLE)
    return page(
        "Auto state machine — combined target",
        "167_01 Saad — Flower · the plan",
        "Per-step Pause/Continue, Retract-all split from <code>ERR</code>, and "
        "manual commands allowed in STOP and <code>ERR</code> — on one machine, "
        "with the implementation order and the one decision that still needs "
        "your call.",
        "auto-state-machine-combined.html", body, states_for_popups=states)
