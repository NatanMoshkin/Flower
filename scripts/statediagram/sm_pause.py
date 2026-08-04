"""VARIANT: Pause / Continue on the orange PB2.

The recommendation drawn here is "finish the bulb, then hold at IDLE", because of
one hardware fact that rules out everything more ambitious — see the callout.
"""

from sm_common import ROBOT_TABLE, core_edges, main_states, override_states
from sm_render import BOX_W, Edge, State, legend_html, page, render_svg


def build_states():
    # PAUSED goes at column 1 row 1 — directly beside IDLE, because that is the
    # only state it applies to. The Manual ghost moves down to row 3 to free it.
    return main_states() + override_states(manual_row=3) + [
        State("ERR", "ERR", 99, "fault", 1, 15, sub="latched — only RESET leaves"),
        State("PAUSED", "PAUSED — wire value only", 41, "new", 1, 1,
              sub="nStateOut override, NOT an eStep"),
    ]


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

    # The whole feature: PB2 latches a flag, IDLE's start gate consults it, and
    # nStateOut reports 41 instead of 0 so the robot stops asking. Straight
    # horizontal hop, label above it in the clear.
    e.append(Edge("IDLE:e", "PAUSED:w", kind="new", label="PB2 → bPause",
                  label_at=((by["IDLE"].x + BOX_W + by["PAUSED"].x) / 2,
                            by["IDLE"].cy - 9), label_side="c"))
    return e


BODY = """
<h2>What changes</h2>
<p>Exactly one guard, one flag and one wire value. Everything green, amber and
blue below is unchanged from <a href="auto-state-machine-current.html">today</a>;
the purple is the whole feature.</p>

{diagram}
{legend}

<div class="callout bad">
<h3>The hardware fact that decides this design</h3>
<p>All eight actuators are <code>FB_SolSpringPiston_2Pos</code>: <strong>single
coil, spring return, no mid-position capability</strong>. Energised drives
extended; de-energised lets the spring pull it home. There is no brake and no
third position.</p>
<p>So <strong>a pause can never stop a piston mid-stroke.</strong> Freezing the
sequencer freezes the <em>sequencer</em> — the pneumatic already in flight
completes its travel either way. &ldquo;Pause&rdquo; on this machine can only
mean one of two things: finish the stroke then hold, or finish the bulb then
hold.</p>
<p>Worse, a mid-stroke freeze is actively bad in two states.
<code>PUSH_EXTENDING</code> is the force stroke — holding the coil means full
cylinder force on a partially-seated pin for as long as the operator is away, and
if a jam is what made them reach for Pause, holding force is exactly the wrong
response. <code>GRIP_RETRACTING</code> releases the plate, so pausing there leaves
it loose in the fixture mid-cycle.</p>
</div>

<h2>Recommended: pause takes effect at IDLE</h2>
<p>Press PB2 at any point; the current bulb <strong>runs to completion</strong>,
increments the counter, returns to <code>IDLE</code> — and there declines the
robot's next <code>CMD:1</code>. Continue clears the flag and the robot's next
keep-alive starts the following bulb about a second later.</p>
<ul>
<li><strong>Zero mid-cycle physical risk.</strong> The plate is never left
clamped, no pin is ever left loaded, the retract chain is never split, no timeout
is ever stretched, no coil is held out of sequence.</li>
<li><strong>One code site in the FB</strong> — the <code>IDLE</code> exit
condition. Nothing else in the state machine is touched.</li>
<li><strong>Nothing to restore.</strong> There is no interrupted state to
remember, so there is no resume variable to get wrong.</li>
<li><strong>Cost: latency.</strong> Worst case is roughly 5&ndash;8 s — grip, sep,
push, the 2 s dwell, both retracts and two 0.5 s dwells. That is what most
assembly cells do, and it is the honest meaning of &ldquo;pause&rdquo;.</li>
</ul>
<p>It is <em>not</em> a substitute for &ldquo;stop now&rdquo;. That intent is
already served — <strong>STOP</strong> disarms immediately, and a fault leaves the
three PB jogs live so a jam can be freed by hand.</p>

<h2>Why the wire value is an override, not a state</h2>
<p><code>eStep</code> stays at <code>IDLE</code> while paused. Only
<code>MAIN</code>'s <code>nStateOut</code> computation reports <code>41</code>:</p>
<div class="tblwrap"><table>
<thead><tr><th>Condition</th><th>nStateOut</th></tr></thead>
<tbody>
<tr><td>NOT bAutoMode</td><td class="m">30  (MANUAL)</td></tr>
<tr><td><strong>paused</strong></td><td class="m"><strong>41  (PAUSED)</strong> &larr; new</td></tr>
<tr><td>otherwise</td><td class="m">TO_INT(eStep)</td></tr>
</tbody></table></div>
<p>Three reasons for that seam. <code>eStep</code> keeps meaning &ldquo;where in
the sequence we are&rdquo;, so the transition log keeps showing real steps. No
<code>eStep</code> write means no resume logic. And there is already precedent
one line above: the <code>MANUAL = 30</code> sentinel is reported exactly this
way and is likewise never assigned to <code>eStep</code>.</p>

<div class="callout bad">
<h3>Reporting anything else here breaks the machine</h3>
<p><strong>Report 0 (IDLE)</strong> and the robot reads &ldquo;armed&rdquo;, sends
<code>CMD:1</code> within a second, MAIN consumes-and-clears it, and the request is
re-asserted forever — the July&nbsp;28 deadlock shape, inverted.</p>
<p><strong>Report 99 (ERR)</strong> and the robot answers <code>CMD:2</code>, which
MAIN turns into <code>bReset</code> — so the robot <em>un-pauses the machine by
homing it</em>, about a second after the operator paused, while the red lamp shows
a fault that does not exist.</p>
<p><strong>Report 40 (NOT_HOMED)</strong> is robot-correct but panel-wrong: green
goes out and PB3 starts its blink-to-arm prompt, telling the operator to press
START on a machine that is armed and merely held — and pressing START discards the
pause.</p>
</div>

{robot}

<h2>PB2's three roles do not collide</h2>
<p>PB2 already carries two jobs, and Pause fits the remaining hole exactly. The
arbitration term is the Boolean complement of the existing jog gate over the same
two variables, so overlap is impossible by construction — a partition, not a
priority scheme. PB3 already carries this identical split.</p>
<div class="tblwrap"><table>
<thead><tr><th>Machine condition</th><th>PB2 does</th><th>LED2 shows</th></tr></thead>
<tbody>
<tr><td>Manual</td><td>Sep jog (momentary, level)</td><td>raw press mirror</td></tr>
<tr><td>Auto + ERR</td><td>Sep jog (momentary, level)</td><td>raw press mirror</td></tr>
<tr><td><strong>Auto, not ERR</strong> — free today</td>
    <td><strong>Pause / Continue</strong> (rising edge, toggles a latch)</td>
    <td><strong>blink</strong> = will stop at end of bulb<br><strong>steady</strong> = paused</td></tr>
</tbody></table></div>
<p>Edge-toggle rather than hold-to-pause, for three reasons: you pause in order to
walk away; hold-to-pause would collide with the same physical grip that jogs
separators in Manual; and a level pause restarts the state's timeout budget on
every release.</p>
<p>The blink&rarr;steady distinction is what makes the deferred stop honest.
Without it the operator presses again during the 5&ndash;8 s wait and cancels their
own pause. One more lamp edit is easy to miss: green is currently
<em>steady</em> in <code>IDLE</code>, so a paused machine would show steady green
contradicting LED2 — green should be off while paused.</p>

<h2>Rules that keep it safe</h2>
<div class="tblwrap"><table>
<thead><tr><th>Rule</th><th>Why</th></tr></thead>
<tbody>
<tr><td>The flag lives in <code>GVL_HMI</code> — <strong>never</strong> in <code>GVL_HmiPersistent</code></td>
    <td>The biggest risk in the whole feature is a pause that outlives the physical state it was taken in. Every spring-return piston retracts on power loss, guaranteed, and the plate is released. A persisted pause would resume a sequence whose assumptions are all void. Plain <code>VAR_GLOBAL</code> scrubs on every cold boot and download, so the machine returns un-armed and un-paused for free.</td></tr>
<tr><td>STOP clears it</td>
    <td>STOP's whole point is a state only a human START leaves. A pause surviving STOP means the operator STOPs, presses START, and the machine homes and then sits paused.</td></tr>
<tr><td>Manual re-park clears it</td>
    <td>In Manual PB2 reverts to the Sep jog, so a surviving flag would be unreachable from the panel.</td></tr>
<tr><td>Entering ERR clears it</td>
    <td>Same reason, and it makes RESET-while-paused a non-question. One site in Section 2 rather than eleven ERR entries.</td></tr>
<tr><td>Rejected from <code>NOT_HOMED</code></td>
    <td>Nothing is driven there. A flag set in <code>NOT_HOMED</code> that leaked through START &rarr; home &rarr; arm gives a machine that arms and then refuses to run with no visible reason.</td></tr>
<tr><td>START clears it</td>
    <td>START means &ldquo;home and arm&rdquo;; emerging from the retract chain still paused is incoherent. Also a second way out if LED2 has failed.</td></tr>
</tbody></table></div>

<div class="callout good">
<h3>A bonus that falls out of it</h3>
<p>Every PLC-detected fault in this FB is a timeout branch. Parked at
<code>IDLE</code> no timer runs at all, so <strong>a fault cannot originate while
paused</strong> — the entire &ldquo;paused three minutes, came back to a spurious
timeout&rdquo; class disappears rather than being handled.</p>
</div>

<div class="callout">
<h3>One thing Pause is not</h3>
<p>Nothing here de-energises anything. Coils are <em>held</em>, the plate stays
clamped, and in <code>WAIT_PLATE</code> the robot arm is still moving in the
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
        "Auto state machine — with Pause / Continue",
        "167_01 Saad — Flower · proposed variant",
        "Pause and Continue on the orange PB2, which is unused in Automatic today. "
        "One hardware fact — spring-return pistons cannot stop mid-stroke — rules "
        "out a freeze and points at a much smaller change: finish the bulb, then "
        "hold at <code>IDLE</code>.",
        "auto-state-machine-pause.html", body)
