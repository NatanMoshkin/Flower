"""CURRENT Auto state machine — verified against FB_MasterAutoCycle.TcPOU.

Every claim was read from the ST source, not from CLAUDE.md. The two disagree in
several places; the disagreements are listed on the page because a diagram that
quietly matched the stale docs would be worse than no diagram at all.
"""

from sm_common import (
    ROBOT_TABLE, attach_info, core_edges, main_states, override_states,
)
from sm_render import Edge, State, legend_html, page, render_svg


def build_states():
    # ERR sits on row 15, BELOW the whole column, so the fault bus enters it at
    # a row that aligns with no state. At ERR's old mid-column row the trunk's
    # horizontal stub lined up with DWELL_PUSH, which cannot fault — it read as
    # DWELL_PUSH's own edge.
    return attach_info(main_states() + override_states() + [
        State("ERR", "ERR", 99, "fault", 1, 15, sub="latched — RESET only"),
    ])


def build_edges(states):
    by = {s.key: s for s in states}
    e = core_edges(by)
    e.append(Edge("ERR:e", "INIT_PUSH:e", kind="recover",
                  label="RESET\n(HMI button or\n robot CMD:2)",
                  via=[(by["ERR"].x + 216 + 44, by["ERR"].cy),
                       (by["ERR"].x + 216 + 44, by["INIT_PUSH"].cy + 16),
                       (by["INIT_PUSH"].x + 216 + 16, by["INIT_PUSH"].cy + 16),
                       (by["INIT_PUSH"].x + 216 + 16, by["INIT_PUSH"].cy)],
                  label_at=(by["ERR"].x + 216 + 52, by["ERR"].cy - 26),
                  label_side="r"))
    return e


BODY = """
<h2>Sixteen assigned states</h2>
<p>The badge on each box is its <code>E_MasterAutoStep</code> value. That value is
also what <code>MAIN</code> pushes to the robot as <code>STATE:&lt;n&gt;</code>, so
these numbers are an external contract, not internal bookkeeping. Numbers on the
red fault bus are <code>iErrorCode</code> values.</p>

{diagram}
{legend}
<p class="pophint">Click any state box (marked <strong>i</strong>) for the exact
commands it drives, what it holds by omission, its exit guard and its timer.</p>

<div class="callout">
<h3>The one thing to take away: one chain, four callers</h3>
<p>The three amber <code>INIT_*</code> states are a single retract chain, entered
from <strong>four</strong> places for <strong>two</strong> different purposes —
arming from <code>NOT_HOMED</code>, re-homing from <code>IDLE</code>, recovering
from <code>ERR</code>, and as the front half of every bulb cycle. One internal
boolean, <code>bHomeThenIdle</code>, decides which of the two exits
<code>INIT_GRIP_RETRACTING</code> takes. Written at four sites, read at exactly
one.</p>
<p>Only the bulb-cycle caller wants the <code>WAIT_PLATE</code> exit. And
<code>bHomeThenIdle</code> has <strong>no initialiser</strong>, so its
cold-boot value is <code>FALSE</code> — which is the &ldquo;run a bulb&rdquo;
direction. Nothing is broken today because all four entry points do write it,
but the fail-safe default points the wrong way.</p>
</div>

<h2>Transition detail</h2>
<p>Guards on the diagram are shortened to one line. The full set:</p>
<div class="tblwrap"><table>
<thead><tr><th>From</th><th>Guard</th><th>To</th><th>Sets</th></tr></thead>
<tbody>
<tr><td class="m">NOT_HOMED</td><td class="m">bMachineAuto AND fbTrigStart.Q</td>
    <td class="m">INIT_PUSH_RETRACTING</td><td class="m">bHomeThenIdle := TRUE</td></tr>
<tr><td class="m">IDLE</td>
    <td class="m">bMachineAuto AND (bExtStartPulse OR fbTrigStartAssembly.Q OR fbSim_Idle.Q)</td>
    <td class="m">INIT_PUSH_RETRACTING</td><td class="m">bHomeThenIdle := <strong>FALSE</strong></td></tr>
<tr><td class="m">IDLE</td><td class="m">bMachineAuto AND fbTrigStart.Q</td>
    <td class="m">INIT_PUSH_RETRACTING</td><td class="m">bHomeThenIdle := TRUE</td></tr>
<tr><td class="m">ERR</td><td class="m">fbTrigReset.Q  (HMI button or robot CMD:2)</td>
    <td class="m">INIT_PUSH_RETRACTING</td><td class="m">bHomeThenIdle := TRUE, error cleared</td></tr>
<tr><td class="m">INIT_GRIP_RETRACTING</td><td class="m">grip retracted AND bHomeThenIdle</td>
    <td class="m">IDLE</td><td class="m">—</td></tr>
<tr><td class="m">INIT_GRIP_RETRACTING</td><td class="m">grip retracted AND NOT bHomeThenIdle</td>
    <td class="m">WAIT_PLATE</td><td class="m">—</td></tr>
<tr><td class="m">any except ERR</td><td class="m">fbTrigStop.Q</td>
    <td class="m">NOT_HOMED</td><td class="m">iErrorCode := 0 — disarms, does not fault</td></tr>
<tr><td class="m">any except NOT_HOMED, ERR</td><td class="m">NOT bMachineAuto  (level, every scan)</td>
    <td class="m">NOT_HOMED</td><td class="m">—</td></tr>
</tbody></table></div>

<h2 id="unsafe">A defect worth fixing regardless of any redesign</h2>
<div class="callout bad">
<h3>The defensive <code>CASE ELSE</code> fails unsafe</h3>
<p>Any <code>eStep</code> value with no CASE branch clears all coils and then
does <code>stHmi.eStep := E_MasterAutoStep.IDLE</code>. <code>IDLE</code> is wire
value <strong>0</strong> — the one value that makes the robot send
<code>CMD:1</code> — and it is reached with the pistons in unknown positions.</p>
<p>This is reachable: <code>GVL_HMI</code> carries the
<code>TcHmiSymbol.AddSymbol</code> pragma, so <code>eStep</code> is writable over
ADS by the HMI or any client; and <code>WAIT_POS2 (2)</code> is a declared
enumerator with no branch today. <code>NOT_HOMED</code> is the correct landing
state — it reports &ldquo;wait&rdquo; and requires a human START. Two-line change,
independent of everything else on these pages.</p>
</div>

<h2>Where the code and its own comments disagree</h2>
<p>Found by reading the source against its documentation. The code is what runs;
the diagram follows the code. None of these was introduced by this exercise.</p>
<div class="tblwrap"><table>
<thead><tr><th>The comments say</th><th>The code does</th><th>Why it matters</th></tr></thead>
<tbody>
<tr><td>grip and plate aggregate with <code>AND</code></td>
    <td><code>OR</code></td>
    <td>Deliberate field deviation — GripSolR has no air. One sensor advances the cycle, so a single-gripper failure is invisible.</td></tr>
<tr><td><code>bNoSensors</code> covers 4 movement states (codes 1/3/4/5)</td>
    <td>the term is in <strong>nine</strong> states</td>
    <td>With the flag set, codes <strong>1, 3, 4, 5, 6, 7, 8, 10, 11 are all unreachable</strong> — only code 9 can fire. This is why no movement-timeout path has ever been exercised on a bench.</td></tr>
<tr><td>IDLE exits on <code>... OR stCfg.bContinuous</code>, so a persisted TRUE could start a cycle at power-up</td>
    <td>IDLE never tests it. The FB writes <code>bContinuous</code> ten times and reads it <strong>zero</strong> times</td>
    <td>The hazard <code>MAIN</code> force-clears it to prevent no longer exists in the FB. The force-clear is belt-and-braces now, not load-bearing.</td></tr>
<tr><td>code 2 = WAIT_POS2 timeout; code 99 = operator STOP</td>
    <td>neither is ever set</td>
    <td>Both unreachable. Correctly documented as retired; do not reuse either number.</td></tr>
<tr><td><code>bAnyRunning</code> is read by MAIN to force piston modes</td>
    <td>never read anywhere</td>
    <td>Dead output, misleading comment. It also reads TRUE in <code>NOT_HOMED</code>, where nothing runs.</td></tr>
<tr><td>each state clears the commands it does not own</td>
    <td>only 8 of 16 clear the full Sep/Push set; several mid-cycle states <strong>hold commands by omission</strong></td>
    <td>Load-bearing for any Pause design — see that page.</td></tr>
</tbody></table></div>

<h2>Timers</h2>
<p>A single shared <code>tonStep : TON</code>, re-armed whenever
<code>eStep</code> changes. PT is chosen per state:</p>
<div class="tblwrap"><table>
<thead><tr><th>PT source</th><th>Default</th><th>States</th></tr></thead>
<tbody>
<tr><td class="m">tStepTimeoutMs</td><td class="m">10000 ms</td>
    <td>the nine movement states — both INIT sets, both GRIP, all four Sep/Push</td></tr>
<tr><td class="m">tPlateWaitTimeoutMs</td><td class="m">10000 ms</td><td>WAIT_PLATE</td></tr>
<tr><td class="m">tDwellPushMs</td><td class="m">2000 ms</td><td>DWELL_PUSH</td></tr>
<tr><td class="m">tPushRetractedDwellMs</td><td class="m">500 ms</td><td>PUSH_RETRACTED_DWELL</td></tr>
<tr><td class="m">tSepRetractedDwellMs</td><td class="m">500 ms</td><td>SEP_RETRACTED_DWELL</td></tr>
<tr><td class="m">no timer</td><td class="m">—</td>
    <td>IDLE, NOT_HOMED, ERR — the ELSE branch holds <code>IN := FALSE</code></td></tr>
</tbody></table></div>
<p>Because <code>IN := FALSE</code> <em>resets</em> a TON's elapsed time rather
than holding it, any future feature that stops the timer gives the state its full
budget again on resume. That turns out to simplify Pause considerably.</p>

<h2>What the robot sees</h2>
<p>In Manual, <code>MAIN</code> masks the real step and reports
<code>STATE:30</code>. In Automatic it puts the raw enum value on the wire.</p>
{robot}
"""


def build():
    states = build_states()
    svg, _, _ = render_svg(states, build_edges(states))
    body = BODY.format(diagram=f'<div class="diagram">{svg}</div>',
                       legend=legend_html(show_new=False), robot=ROBOT_TABLE)
    return page(
        "Auto state machine — as it runs today",
        "167_01 Saad — Flower · Auto sequence",
        "The sixteen assigned states of <code>FB_MasterAutoCycle</code>, their exit "
        "guards, the fault paths and the two global overrides — read from the ST "
        "source rather than from the documentation, which disagrees with it in six "
        "places listed below.",
        "auto-state-machine-current.html", body, states_for_popups=states)
