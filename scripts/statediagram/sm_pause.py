"""VARIANT: Pause / Continue from ANY step, on the orange PB2.

Per the operator's requirement: pause is available from every step of the
sequence, and Continue resumes that same step. The design that makes this both
possible and safe on spring-return pistons is "hold at the step boundary" —
pause takes effect the moment the current step's exit guard is satisfied, so
every commanded motion has completed and been sensor-confirmed. See the callout.
"""

from sm_common import (
    ROBOT_TABLE, attach_info, core_edges, main_states, override_states,
)
from sm_render import BOX_W, Edge, State, legend_html, page, render_svg

# Extra popup rows added on this page only: what pausing in each state means.
PAUSE_NOTES = {
    "IDLE": [("pause here", "the start gate — declines the robot's CMD:1. "
                            "Nothing is driven, nothing to hold.")],
    "INIT_PUSH": [("pause here", "push confirmed home, sep and grip "
                                 "uncommanded. Machine is part-homed.")],
    "INIT_SEP": [("pause here", "push and sep both confirmed home. Part-homed.")],
    "INIT_GRIP": [("pause here", "fully home and released — the safest hold "
                                 "point in the whole machine.")],
    "CHECK_PLATE": [("pause here", "plate present, grippers open, nothing "
                                  "driven. Safe — but the robot arm may still "
                                  "be in the fixture.")],
    "GRIP_EXT": [("pause here", "plate clamped, coils held. Safe hold.")],
    "SEP_EXT": [("pause here", "separators out and clamped. Safe hold.")],
    "PUSH_EXT": [("pause here", "<strong>pins fully driven and held at full "
                                "cylinder force.</strong> Mechanically at a "
                                "hard stop, but see the caution below.")],
    "DWELL_PUSH": [("pause here", "<strong>the dwell has already elapsed and "
                                  "pin load stays applied indefinitely.</strong> "
                                  "The one hold point that needs a cap.")],
    "PUSH_RET": [("pause here", "push home, separators still out, plate "
                                "clamped. Safe hold.")],
    "PUSH_RET_DW": [("pause here", "push home, separators out, clamped. Safe.")],
    "SEP_RET": [("pause here", "separators home, plate still clamped. Safe.")],
    "SEP_RET_DW": [("pause here", "sep and push home, only the clamp holding. "
                                  "Safe.")],
    "GRIP_RET": [("pause here", "plate released and the cycle already counted. "
                                "Effectively 'about to re-arm'.")],
    "NOT_HOMED": [("pause here", "rejected — nothing is driven, and PB2 is a "
                                 "manual jog in this state.")],
    "ERR": [("pause here", "rejected — PB2 is a manual jog in this state.")],
}


def build_states():
    states = main_states() + override_states(manual_row=3) + [
        State("ERR", "ERR", 99, "fault", 1, 15, sub="latched — RESET only"),
        State("PAUSED", "PAUSED — wire value only", 41, "new", 1, 1,
              sub="nStateOut only"),
    ]
    return attach_info(states, extras=PAUSE_NOTES)


def build_edges(states):
    by = {s.key: s for s in states}
    e = core_edges(by)

    e.append(Edge("ERR:e", "INIT_PUSH:e", kind="recover",
                  label="RESET\n(HMI or CMD:2)",
                  via=[(by["ERR"].x + BOX_W + 44, by["ERR"].cy),
                       (by["ERR"].x + BOX_W + 44, by["INIT_PUSH"].cy + 16),
                       (by["INIT_PUSH"].x + BOX_W + 16, by["INIT_PUSH"].cy + 16),
                       (by["INIT_PUSH"].x + BOX_W + 16, by["INIT_PUSH"].cy)],
                  label_at=(by["ERR"].x + BOX_W + 52, by["ERR"].cy - 18),
                  label_side="r"))

    # PAUSED is a wire value, not a state: eStep keeps holding the interrupted
    # step, so the arrow means "this is what the robot is told", not a
    # transition. Drawn from IDLE only because that is where the box sits; the
    # bracket note on the page says it applies to every step.
    e.append(Edge("IDLE:e", "PAUSED:w", kind="new", label="PB2",
                  label_at=(by["PAUSED"].x - 26, by["IDLE"].cy - 9),
                  label_side="l"))
    return e


BODY = """
<h2>Pause from any step, Continue resumes that step</h2>
<p>Every green, amber and blue state below is pausable. <code>eStep</code> does
not change while paused — it keeps holding the interrupted step, which is what
makes Continue trivially correct. Only the value on the wire changes.</p>

{diagram}
{legend}
<p class="pophint">Click any state box for the commands it drives <em>and</em>
what a pause in that state physically means.</p>

<div class="callout good">
<h3>The rule that makes per-step pause safe: hold at the step boundary</h3>
<p>Pause does not freeze the machine wherever it happens to be. It is
<strong>requested</strong> on the PB2 press and <strong>takes effect the moment
the current step's exit guard is satisfied</strong> — the machine simply does not
advance. One extra term per state:</p>
<p class="mono">IF &lt;exit guard&gt; AND NOT bPause THEN advance</p>
<p>Because the guard is satisfied, every motion that step commanded has already
completed <em>and been sensor-confirmed</em>. Nothing is ever held mid-stroke.
That matters because all eight actuators are <code>FB_SolSpringPiston_2Pos</code>
— single coil, spring return, <strong>no mid-position capability and no
brake</strong>. A naive freeze could not have stopped a stroke anyway; this
design does not need to.</p>
<p>Worst-case latency is therefore one step, not one bulb — typically well under
a second, or the remainder of a dwell.</p>
</div>

<div class="callout bad">
<h3>The timer is the trap</h3>
<p>Nine states run <code>tStepTimeoutMs</code> (default 10 s). Hold a state with
its timer running and the machine faults in ten seconds with an error code that
<em>lies</em> — <code>PUSH_EXTENDING timed out</code> when in fact the operator
paused. So a pause <strong>must</strong> drive <code>tonStep(IN := FALSE)</code>.</p>
<p>Conveniently that is also the right behaviour: a TON <em>resets</em> its
elapsed time when <code>IN</code> goes FALSE rather than holding it, so Continue
gives the step its full timeout budget again. No snapshot-and-restore machinery
is needed. The only casualty is <code>tElapsedS</code> reading 0.0 while paused;
a separate timer would be needed to show "how long paused".</p>
<p>Second-order benefit: with the timer stopped, <strong>a fault cannot originate
while paused at all</strong> — every PLC-detected fault in this FB is a timeout
branch. The whole "paused for three minutes, came back to a spurious timeout"
class disappears rather than being handled.</p>
</div>

<h2>Two hold points that need a decision</h2>
<div class="tblwrap"><table>
<thead><tr><th>State</th><th>Concern</th><th>Suggested</th></tr></thead>
<tbody>
<tr><td class="m">DWELL_PUSH</td>
    <td>The guard is "dwell elapsed", so a pause here holds
    <strong>full pin load on the bulb assembly indefinitely</strong>. The
    2 s squeeze becomes unbounded.</td>
    <td>Either exclude this one state from pause (advance to
    <code>PUSH_RETRACTING</code> and hold there instead — one step later, and
    push is then home), or cap the hold and auto-continue. Excluding is
    simpler and loses almost nothing.</td></tr>
<tr><td class="m">PUSH_EXTENDING</td>
    <td>Pins fully driven, coils held. Mechanically at a hard stop so it is not
    a runaway, but it is the same sustained-force question one step earlier.</td>
    <td>Safe to allow. If a jam is what made the operator reach for Pause, note
    that the guard will not be satisfied — so the pause simply never takes
    effect and the step times out into <code>ERR</code> as it does today. That
    is correct behaviour, but it must be explained to operators or Pause will
    look broken exactly when they need it.</td></tr>
<tr><td class="m">the retract chain</td>
    <td>Pausing between links leaves the machine <strong>part-homed</strong> —
    each group at a confirmed limit, nothing loaded, but not "home".</td>
    <td>Allow. Nothing is in motion and nothing is clamped. Worth showing
    distinctly on the panel so it is not mistaken for a completed home.</td></tr>
</tbody></table></div>

<div class="callout bad">
<h3>The one case where Pause cannot help</h3>
<p>Pause waits for the exit guard. If the guard is never satisfied — a jammed
piston, a sensor that never makes — then the pause <strong>never takes
effect</strong> and the step times out into <code>ERR</code> on schedule. Pause
is not an abort. The abort is <strong>STOP</strong>, which disarms immediately
from any state, and from <code>ERR</code> the manual commands are live so the jam
can be freed by hand.</p>
</div>

<h2>What the robot is told</h2>
<p><code>eStep</code> keeps holding the interrupted step, so the wire value must
come from an override in <code>MAIN</code>'s <code>nStateOut</code> computation,
not from writing <code>eStep</code>:</p>
<div class="tblwrap"><table>
<thead><tr><th>Condition</th><th>nStateOut</th></tr></thead>
<tbody>
<tr><td>NOT bAutoMode</td><td class="m">30  (MANUAL)</td></tr>
<tr><td><strong>paused (any step)</strong></td>
    <td class="m"><strong>41  (PAUSED)</strong> &larr; new</td></tr>
<tr><td>otherwise</td><td class="m">TO_INT(eStep)</td></tr>
</tbody></table></div>
<p>Three reasons for that seam. <code>eStep</code> keeps meaning &ldquo;where in
the sequence we are&rdquo;, so Continue is a single flag clear and the transition
log keeps showing real steps. Nothing needs a resume variable. And there is
already precedent one line above — the <code>MANUAL = 30</code> sentinel is
reported exactly this way and is likewise never assigned to <code>eStep</code>.</p>
<p>In practice most paused steps already report a value the robot treats as
&ldquo;wait&rdquo;, so the override only strictly matters for <code>IDLE</code>.
Reporting 41 for all of them anyway is what makes a paused machine visible as
paused rather than as merely busy.</p>

<div class="callout bad">
<h3>Reporting anything else breaks the machine</h3>
<p><strong>0 (IDLE)</strong> — the robot reads &ldquo;armed&rdquo;, sends
<code>CMD:1</code> within a second, MAIN consumes-and-clears it, and the request
is re-asserted forever: the July&nbsp;28 deadlock shape, inverted.</p>
<p><strong>99 (ERR)</strong> — the robot answers <code>CMD:2</code>, MAIN turns it
into <code>bReset</code>, and the robot <em>un-pauses the machine by homing
it</em> about a second after the operator paused, with the red lamp showing a
fault that does not exist.</p>
<p><strong>40 (NOT_HOMED)</strong> — robot-correct but panel-wrong: green goes
out and PB3 starts its blink-to-arm prompt, telling the operator to press START
on a machine that is armed and merely held.</p>
</div>

{robot}

<h2>PB2's roles stay disjoint</h2>
<div class="tblwrap"><table>
<thead><tr><th>Machine condition</th><th>PB2 does</th><th>LED2 shows</th></tr></thead>
<tbody>
<tr><td>Manual</td><td>Sep jog — momentary, level</td><td>raw press mirror</td></tr>
<tr><td>Auto + <code>ERR</code></td><td>Sep jog — momentary, level</td>
    <td>raw press mirror</td></tr>
<tr><td>Auto + <code>NOT_HOMED</code></td><td>Sep jog — momentary, level</td>
    <td>raw press mirror</td></tr>
<tr><td><strong>Auto, armed or running</strong></td>
    <td><strong>Pause / Continue</strong> — rising edge, toggles a latch</td>
    <td><strong>blink</strong> = pause requested, waiting for the step to
    finish<br><strong>steady</strong> = paused and holding</td></tr>
</tbody></table></div>
<p>Still a partition rather than a priority scheme: the jog condition and the
pause condition are Boolean complements over the same two variables, so overlap
is impossible by construction. PB3 already carries this identical split.</p>
<p>Edge-toggle, not hold-to-pause: you pause in order to walk away, hold-to-pause
would collide with the same physical grip that jogs separators in Manual, and a
level pause would restart the step's timeout budget on every release.</p>
<p>The blink&rarr;steady distinction is what makes the wait honest — without it an
operator whose step has not finished yet presses again and cancels their own
pause. And green is currently <em>steady</em> in <code>IDLE</code>, so a paused
machine would show steady green contradicting LED2: <strong>green should be off
while paused</strong>.</p>

<h2>Rules that keep it safe</h2>
<div class="tblwrap"><table>
<thead><tr><th>Rule</th><th>Why</th></tr></thead>
<tbody>
<tr><td>The flag lives in <code>GVL_HMI</code> — <strong>never</strong> in
    <code>GVL_HmiPersistent</code></td>
    <td>The biggest risk in the feature is a pause that outlives the physical
    state it was taken in. Every spring-return piston retracts on power loss,
    guaranteed, and the plate is released — so a persisted pause would resume a
    step whose assumptions are all void. Plain <code>VAR_GLOBAL</code> scrubs it
    on every cold boot and download, so the machine returns un-armed and
    un-paused for free.</td></tr>
<tr><td>STOP clears it</td>
    <td>STOP's whole point is a state only a human START leaves. A pause
    surviving STOP means the operator STOPs, presses START, and the machine homes
    and then sits paused.</td></tr>
<tr><td>Manual re-park clears it</td>
    <td>In Manual PB2 reverts to the Sep jog, so a surviving flag would be
    unreachable from the panel.</td></tr>
<tr><td>Entering ERR clears it</td>
    <td>Makes RESET-while-paused a non-question, in one site rather than eleven.</td></tr>
<tr><td>START clears it</td>
    <td>START means &ldquo;home and arm&rdquo;; emerging from the retract chain
    still paused is incoherent. Also a second way out if LED2 has failed.</td></tr>
<tr><td>Rejected from <code>NOT_HOMED</code> and <code>ERR</code></td>
    <td>Nothing is driven in either, and PB2 is a manual jog in both.</td></tr>
<tr><td>No manual commands while paused</td>
    <td>Pause holds a specific coil pattern; letting the operator jog would
    fight it and change the physical state the resumed step assumes. STOP first
    if hands-on work is needed — that reaches <code>NOT_HOMED</code>, where
    manual is allowed.</td></tr>
</tbody></table></div>

<div class="callout">
<h3>One thing Pause is not</h3>
<p>Nothing here de-energises anything. Coils are <em>held</em>, the plate stays
clamped, and in <code>CHECK_PLATE</code> the robot arm may still be moving in the
fixture. Pause is a process control, not a safety function, and must not be
labelled, lamped or trained as one.</p>
</div>
"""


def build():
    states = build_states()
    svg, _, _ = render_svg(states, build_edges(states))
    body = BODY.format(diagram=f'<div class="diagram">{svg}</div>',
                       legend=legend_html(), robot=ROBOT_TABLE)
    return page(
        "Auto state machine — Pause / Continue from any step",
        "167_01 Saad — Flower · proposed variant",
        "Pause available from every step and Continue resuming that same step, on "
        "the orange PB2. The design point that makes it safe on spring-return "
        "pistons: the pause takes effect at the <em>step boundary</em>, once the "
        "exit guard is satisfied — so nothing is ever held mid-stroke.",
        "auto-state-machine-pause.html", body, states_for_popups=states,
        status=("rejected",
                "Rejected — 2026-08-05. Not implemented.",
                "The operator decided Pause is not needed: &ldquo;no need to "
                "include PAUSED&rdquo;. Nothing on this page exists in the PLC "
                "and <code>PAUSED (41)</code> was never added to the enum. Kept "
                "for the analysis — in particular the hardware constraint that "
                "spring-return pistons cannot be stopped mid-stroke, which "
                "would govern any future attempt."))
