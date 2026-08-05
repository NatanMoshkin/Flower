"""AS-BUILT Auto state machine — verified against FB_MasterAutoCycle.TcPOU and
against the live PLC (2026-08-05).

Every claim here was read from the ST source. The behaviour was then confirmed
on the running PLC: scripts/pb_test/pb_test_procedure.py 57/57, and
scripts/pb_test/cycle_trace.py 10/10 states driving exactly the coils listed in
the popups.
"""

from sm_common import (
    ROBOT_TABLE, attach_info, core_edges, main_states, operator_rows,
    override_states,
)
from sm_render import BOX_W, Edge, State, legend_html, page, render_svg

RECOVER = [("REC_PUSH", "RECOVER_PUSH_RETR", 50, 12, 16),
           ("REC_SEP", "RECOVER_SEP_RETR", 51, 13, 17),
           ("REC_GRIP", "RECOVER_GRIP_RETR", 52, 14, 18)]

def build_states():
    st = main_states() + override_states()
    st.append(State("ERR", "ERR", 99, "fault", 1, 15, sub="latched — RESET only"))
    for k, name, val, code, row in RECOVER:
        st.append(State(k, name, val, "init", 1, row,
                        sub=f"timeout → error {code}"))
    # Every state gets a "panel buttons" row saying what PB1/PB2/PB3 do THERE.
    # That is state-dependent -- STOP works everywhere except ERR, RESET only in
    # ERR, START only in NOT_HOMED and IDLE, the combo only from IDLE -- so no
    # single table can express it and the popups are the right place. The
    # RECOVER states' command detail comes from COMMANDS like every other state,
    # because they are real states now.
    return attach_info(st, extras=operator_rows())


def build_edges(states):
    by = {s.key: s for s in states}
    e = core_edges(by)
    e.append(Edge("ERR:s", "REC_PUSH:n", kind="recover",
                  label="RESET — HMI, orange PB2, or robot CMD:2"))
    e.append(Edge("REC_PUSH:s", "REC_SEP:n", kind="recover", label="push retracted"))
    e.append(Edge("REC_SEP:s", "REC_GRIP:n", kind="recover", label="sep retracted"))
    e.append(Edge("REC_GRIP:e", "IDLE:e", kind="recover",
                  label="grip retracted → armed",
                  via=[(by["REC_GRIP"].x + BOX_W + 46, by["REC_GRIP"].cy),
                       (by["REC_GRIP"].x + BOX_W + 46, by["IDLE"].cy - 16),
                       (by["IDLE"].x + BOX_W + 18, by["IDLE"].cy - 16),
                       (by["IDLE"].x + BOX_W + 18, by["IDLE"].cy)],
                  label_at=(by["REC_GRIP"].x + BOX_W + 54, by["REC_GRIP"].cy - 20),
                  label_side="r"))
    return e


BODY = """
<h2>Nineteen assigned states</h2>
<p>The badge on each box is its <code>E_MasterAutoStep</code> value, which is also
what <code>MAIN</code> pushes to the robot as <code>STATE:&lt;n&gt;</code> — an
external contract, not internal bookkeeping. Numbers on the red fault bus are
<code>iErrorCode</code> values.</p>

{diagram}
{legend}
<p class="pophint">Click any state box (marked <strong>i</strong>) for the exact
commands it drives, its exit guard, its timer, its error code — and
<strong>what each panel button does in that state</strong>, which is not the same
everywhere: STOP works in every state <em>except</em> <code>ERR</code>, RESET
only <em>in</em> <code>ERR</code>, START only in <code>NOT_HOMED</code> and
<code>IDLE</code>, and the start combo only from <code>IDLE</code>. The command
lists were confirmed against the running PLC — see <em>How this was
verified</em>.</p>

<div class="callout good">
<h3>Recovery has its own chain</h3>
<p><code>RESET</code> out of <code>ERR</code> runs
<code>RECOVER_PUSH_RETR → RECOVER_SEP_RETR → RECOVER_GRIP_RETR</code> (50/51/52),
not the shared <code>INIT_*</code> chain. Same motion and the same collision
ordering — push, then sep, then grip — but its own identity, so a failed
<em>recovery</em> reports error <strong>12/13/14</strong> and its own
<code>sStepText</code> instead of looking exactly like a failed <em>arming</em>
(6/7/8).</p>
<p>It always exits to <code>IDLE</code>: at that point the machine really is
homed, so advertising <code>STATE:0</code> is honest. The robot needed
<strong>no new branch</strong> — it acts on 0 and 99 and treats everything else
as &ldquo;wait&rdquo;.</p>
</div>

<div class="callout">
<h3>The <code>INIT_*</code> chain still has three callers</h3>
<p>Arming from <code>NOT_HOMED</code>, re-homing from <code>IDLE</code>, and the
front half of every bulb cycle. <code>bHomeThenIdle</code> still picks which of
the two exits <code>INIT_GRIP_RETRACTING</code> takes — but it is down from four
writers to three, because fault recovery no longer borrows this chain.</p>
<p>It still has <strong>no initialiser</strong>, so its cold-boot value
<code>FALSE</code> is the &ldquo;run a bulb&rdquo; direction. Nothing is broken —
all three entry points write it — but the fail-safe default points the wrong way.
Replacing it with <code>eReturnTo : E_MasterAutoStep</code> is still worth doing:
an uninitialised enum is <code>0</code> = <code>IDLE</code>.</p>
</div>

<h2>Panel buttons</h2>
<p>Two of the three gestures in Automatic are multi-second <strong>holds</strong>,
not edges — both are consequential, and a hold cannot be triggered by a knock or
a brushed sleeve. Durations are editable on <code>AutoMain</code>.</p>
<div class="tblwrap"><table>
<thead><tr><th></th><th>PB1 — red</th><th>PB2 — orange</th><th>PB3 — green</th></tr></thead>
<tbody>
<tr><td><strong>Manual</strong></td><td>grip jog</td><td>Sep jog</td><td>Push jog</td></tr>
<tr><td><strong>Automatic</strong></td>
    <td><strong>held <code>tPbStopHoldMs</code></strong> → STOP, disarming to
        <code>NOT_HOMED</code>. LED1 blinks while the hold counts.</td>
    <td>in <code>ERR</code>: <strong>RESET</strong> (edge).<br>
        with PB3: half of the start combo.</td>
    <td><strong>START</strong> (edge) — home and arm.</td></tr>
<tr><td><strong>PB2 + PB3 together</strong></td>
    <td colspan="3"><strong>held <code>tPbStartHoldMs</code> from
    <code>IDLE</code></strong> → run ONE bulb. The operator's parallel to the
    robot's <code>CMD:1</code>, fed into the same <code>bExtStartPulse</code>
    input.</td></tr>
</tbody></table></div>
<div class="callout">
<h3>Press ORANGE before GREEN — and it is not merely cosmetic</h3>
<p>The standalone PB3 START edge is suppressed while PB2 is held, so the combo
cannot fire a START on its way in. Press green first, though, and the START fires
before PB2 arrives: the machine re-homes. What happens to the cycle request then
depends on timing, and <strong>both outcomes were measured on the PLC</strong>:</p>
<ul>
<li><strong>Homing finishes before the hold completes</strong> (bench case, ~30 ms
with the pistons already home): the combo pulse lands while <code>eStep</code> is
back at <code>IDLE</code>, so you get a pointless re-home <em>and then</em> the
cycle. Observed chain:
<code>IDLE → INIT_* → IDLE → INIT_* → CHECK_PLATE</code>.</li>
<li><strong>Homing is still running when the hold completes</strong> (measured with
a 2.33 s chain against a 1 s hold): the pulse fires while <code>eStep</code> is
<code>INIT_SEP_RETRACTING</code>. <code>bExtStartPulse</code> is consumed
<em>only</em> by the <code>IDLE</code> branch, so it is <strong>silently
dropped</strong> — and because the combo's <code>R_TRIG</code> fires once per
press, holding longer does not help. Observed chain:
<code>IDLE → INIT_* → IDLE</code>, no bulb.</li>
</ul>
<p>On the machine, with real strokes, the second case is the one to expect. That
makes the button order functional rather than cosmetic.</p>
</div>
<p><strong>Manual moves are available in Manual mode only.</strong> An ERR jog
window existed briefly (2026-08-04) and was removed the next day by operator
decision. <code>scripts/test_piston_jog_gate.py</code> and
<code>pb_test</code> group E are now the negative guards on that removal.</p>

<h2>Transition detail</h2>
<div class="tblwrap"><table>
<thead><tr><th>From</th><th>Guard</th><th>To</th><th>Sets</th></tr></thead>
<tbody>
<tr><td class="m">NOT_HOMED</td><td class="m">bMachineAuto AND fbTrigStart.Q</td>
    <td class="m">INIT_PUSH_RETRACTING</td><td class="m">bHomeThenIdle := TRUE</td></tr>
<tr><td class="m">IDLE</td>
    <td class="m">bMachineAuto AND (bExtStartPulse OR fbTrigStartAssembly.Q OR fbSim_Idle.Q)</td>
    <td class="m">INIT_PUSH_RETRACTING</td>
    <td class="m">bHomeThenIdle := <strong>FALSE</strong></td></tr>
<tr><td class="m">IDLE</td><td class="m">bMachineAuto AND fbTrigStart.Q</td>
    <td class="m">INIT_PUSH_RETRACTING</td><td class="m">bHomeThenIdle := TRUE</td></tr>
<tr><td class="m">INIT_GRIP_RETRACTING</td>
    <td class="m">grip retracted AND bHomeThenIdle</td>
    <td class="m">IDLE</td><td class="m">—</td></tr>
<tr><td class="m">INIT_GRIP_RETRACTING</td>
    <td class="m">grip retracted AND NOT bHomeThenIdle</td>
    <td class="m">CHECK_PLATE</td><td class="m">—</td></tr>
<tr><td class="m">ERR</td>
    <td class="m">fbTrigReset.Q — HMI, PB2, or robot CMD:2</td>
    <td class="m">RECOVER_PUSH_RETR</td><td class="m">error cleared</td></tr>
<tr><td class="m">RECOVER_GRIP_RETR</td><td class="m">grip retracted</td>
    <td class="m">IDLE</td><td class="m">—</td></tr>
<tr><td class="m">any except ERR</td>
    <td class="m">fbTrigStop.Q — HMI, or PB1 held</td>
    <td class="m">NOT_HOMED</td>
    <td class="m">iErrorCode := 0 — disarms, does not fault</td></tr>
<tr><td class="m">any except NOT_HOMED, ERR</td>
    <td class="m">NOT bMachineAuto  (level, every scan)</td>
    <td class="m">NOT_HOMED</td><td class="m">—</td></tr>
</tbody></table></div>

<h2>Every state resets its commands first</h2>
<p>Each branch calls <code>ResetAllCommands()</code> — a METHOD on the FB, 20 call
sites — and then re-asserts only the commands it owns. Before 2026-08-05 the
bodies were a mix: eight of sixteen cleared the full Sep/Push set and the rest
inherited FALSE from whichever state ran previously, so reading one branch in
isolation could not tell you what the coils were doing.</p>
<p>Behaviour is unchanged — each old body's net effect was already
&ldquo;everything FALSE except what it listed&rdquo; — and that equivalence is
what <code>cycle_trace.py</code> demonstrates rather than asserts.</p>
<p>Note it clears <strong>commands, not coils</strong>.
<code>FB_SolSpringPiston_2Pos</code> retains its coil when no command branch
matches, so clearing mid-stroke holds the piston rather than dropping it. That is
exactly why every state must re-assert what it wants, every scan.</p>

<h2>Error codes</h2>
<div class="tblwrap"><table>
<thead><tr><th>Code</th><th>Meaning</th></tr></thead>
<tbody>
<tr><td class="m">0</td><td>OK</td></tr>
<tr><td class="m">1 / 3 / 4 / 5</td>
    <td>SEP_EXTENDING / PUSH_EXTENDING / PUSH_RETRACTING / SEP_RETRACTING timeout</td></tr>
<tr><td class="m">6 / 7 / 8</td><td>the three <code>INIT_*</code> timeouts — arming</td></tr>
<tr><td class="m">9</td><td>CHECK_PLATE timeout; suppressed by <code>bBypassPlateSensors</code></td></tr>
<tr><td class="m">10 / 11</td><td>GRIP_EXTENDING / GRIP_RETRACTING timeout</td></tr>
<tr><td class="m">12 / 13 / 14</td>
    <td><strong>the three <code>RECOVER_*</code> timeouts</strong> — recovery,
    deliberately distinct from 6/7/8</td></tr>
<tr><td class="m">2, 99</td>
    <td><strong>RETIRED</strong>, never set. Do not reuse — old logs and CSV
    exports still carry them.</td></tr>
</tbody></table></div>
<p><strong>Caveat that still matters:</strong> the <code>OR (bNoSensors AND
tonStep.Q)</code> term is present in <strong>twelve</strong> movement states now,
so with that flag set codes 1/3/4/5/6/7/8/10/11/12/13/14 are <em>all</em>
unreachable — only code 9 can fire. Every bench run so far has had it set, so no
movement-timeout path has been exercised on any panel. That is field check
<code>FLD6</code>.</p>

<h2>Timers</h2>
<div class="tblwrap"><table>
<thead><tr><th>PT source</th><th>Default</th><th>States</th></tr></thead>
<tbody>
<tr><td class="m">tStepTimeoutMs</td><td class="m">10000 ms</td>
    <td>twelve movement states — both INIT sets, the three RECOVER, both GRIP,
    all four Sep/Push</td></tr>
<tr><td class="m">tPlateWaitTimeoutMs</td><td class="m">10000 ms</td><td>CHECK_PLATE</td></tr>
<tr><td class="m">tDwellPushMs</td><td class="m">2000 ms</td><td>DWELL_PUSH</td></tr>
<tr><td class="m">tPushRetractedDwellMs</td><td class="m">500 ms</td><td>PUSH_RETRACTED_DWELL</td></tr>
<tr><td class="m">tSepRetractedDwellMs</td><td class="m">500 ms</td><td>SEP_RETRACTED_DWELL</td></tr>
<tr><td class="m">tPbStopHoldMs / tPbStartHoldMs</td><td class="m">1000 ms each</td>
    <td>not step timers — the two PB hold gestures, in <code>MAIN</code></td></tr>
<tr><td class="m">no timer</td><td class="m">—</td>
    <td>IDLE, NOT_HOMED, ERR — the ELSE branch holds <code>IN := FALSE</code></td></tr>
</tbody></table></div>

<h2>What the robot sees</h2>
<p>In Manual, <code>MAIN</code> masks the real step and reports
<code>STATE:30</code>. In Automatic it puts the raw enum value on the wire.</p>
{robot}

<h2>Two deviations that are still live</h2>
<div class="tblwrap"><table>
<thead><tr><th>Deviation</th><th>Why it stays</th></tr></thead>
<tbody>
<tr><td>Grip and plate aggregate with <code>OR</code>, not <code>AND</code>, despite the <code>bAll</code> prefix</td>
    <td><code>GripSolR</code> has no air and only one plate sensor is confirmed,
    so <code>AND</code> would fault every cycle. The cost is real: a genuine
    single-gripper failure is invisible, and error 10/11 can only fire when
    <strong>both</strong> fail. Restore the ANDs when the right gripper has air.</td></tr>
<tr><td>Plate sensors L/R are swapped between the IO list and <code>PRG_IoMap</code></td>
    <td>Invisible while <code>bPlateOk</code> is an OR, but it mislabels the
    <code>L</code>/<code>R</code> lamps on <code>Main.TcVIS</code>. Needs someone
    at the machine to say which physical side is which.</td></tr>
</tbody></table></div>
<p>Two things that <em>were</em> on this list are now fixed: the defensive
<code>CASE ELSE</code> landed on <code>IDLE</code> (wire value 0, &ldquo;send me a
bulb&rdquo;) with the pistons in unknown positions and now lands on
<code>NOT_HOMED</code>; and <code>MAIN</code>'s comment claiming
<code>IDLE</code> tests <code>bContinuous</code> as a level was corrected — it is
written ten times and read zero. <code>bAnyRunning</code> is still computed and
never read.</p>

<h2>How this was verified</h2>
<ul>
<li><code>scripts/pb_test/pb_test_procedure.py</code> — <strong>57/57</strong> over
ADS: LED wiring, the three Manual jogs, Auto/<code>NOT_HOMED</code>,
Auto/<code>IDLE</code>, Auto/<code>ERR</code> (jogs refused), recovery via PB2
through the <code>RECOVER_*</code> chain, and both hold gestures including the
under-duration press that must do nothing.</li>
<li><code>scripts/pb_test/cycle_trace.py</code> — <strong>10/10</strong>. Runs one
complete bulb with all eight pistons emulated and checks the coil pattern of
every state against the popups above.</li>
<li><code>scripts/test_master_cycle_arming.py</code> and
<code>test_piston_jog_gate.py</code> — the arming transitions and the
Manual-only jog gate as pure logic, no PLC.</li>
</ul>
<p>Not covered anywhere yet: the movement-timeout paths (see the
<code>bNoSensors</code> caveat), and everything physical — contacts, lamps, valve
wiring, air.</p>
"""


def build():
    states = build_states()
    svg, _, _ = render_svg(states, build_edges(states))
    body = BODY.format(diagram=f'<div class="diagram">{svg}</div>',
                       legend=legend_html(show_new=False), robot=ROBOT_TABLE)
    return page(
        "Auto state machine — as built",
        "167_01 Saad — Flower · Auto sequence",
        "The nineteen assigned states of <code>FB_MasterAutoCycle</code> as the "
        "source implements them, after the operator decisions of 2026-08-05: a "
        "dedicated fault-recovery chain, <code>CHECK_PLATE</code>, "
        "<code>ResetAllCommands</code> in every state, and two hold gestures on "
        "the panel buttons.",
        "auto-state-machine-current.html", body, states_for_popups=states,
        status=("built",
                "As built and tested — 2026-08-05",
                "Read from the ST source, then confirmed on the live PLC: "
                "<strong>57/57</strong> push-button checks and a full-cycle coil "
                "trace matching <strong>10/10</strong> states. The other three "
                "pages are the decision record that led here."))
