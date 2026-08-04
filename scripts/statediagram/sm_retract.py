"""VARIANT: separate "Retract all" from the Error state.

Two changes drawn together, because each alone leaves the other's problem
standing: rename the shared chain to say what it is (keeping its wire values),
and give fault recovery its own states so a failed recovery is distinguishable
from a failed arming.
"""

from sm_common import ROBOT_TABLE, core_edges, main_states, override_states
from sm_render import BOX_W, Edge, State, legend_html, page, render_svg

# Rename WITHOUT renumber: the wire contract stays byte-identical. Every name
# must be <= 20 chars or sStepText (STRING(20)) truncates silently on the panel.
RENAME = {
    "INIT_PUSH": "RETRACT_ALL_PUSH",
    "INIT_SEP": "RETRACT_ALL_SEP",
    "INIT_GRIP": "RETRACT_ALL_GRIP",
}
for _n in RENAME.values():
    assert len(_n) <= 20, f"{_n} is {len(_n)} chars — sStepText would truncate"

RECOVER = [
    ("REC_PUSH", "RECOVER_PUSH_RETR", 50, 12, 16),
    ("REC_SEP", "RECOVER_SEP_RETR", 51, 13, 17),
    ("REC_GRIP", "RECOVER_GRIP_RETR", 52, 14, 18),
]
for _k, _n, _v, _c, _r in RECOVER:
    assert len(_n) <= 20, f"{_n} is {len(_n)} chars — sStepText would truncate"


def build_states():
    st = main_states(relabel=RENAME) + override_states()
    st.append(State("ERR", "ERR", 99, "fault", 1, 15,
                    sub="latched — only RESET leaves"))
    for k, name, val, code, row in RECOVER:
        st.append(State(k, name, val, "new", 1, row,
                        sub=f"timeout → error {code}", tag="NEW"))
    return st


def build_edges(states):
    by = {s.key: s for s in states}
    e = core_edges(by)

    # ERR now recovers down its own chain instead of borrowing the retract chain.
    e.append(Edge("ERR:s", "REC_PUSH:n", kind="new", label="RESET (HMI or CMD:2)"))
    e.append(Edge("REC_PUSH:s", "REC_SEP:n", kind="new", label="push retracted"))
    e.append(Edge("REC_SEP:s", "REC_GRIP:n", kind="new", label="sep retracted"))
    # ...and rejoins at IDLE, which is what publishes "armed" to the robot.
    e.append(Edge("REC_GRIP:e", "IDLE:e", kind="new", label="grip retracted → armed",
                  via=[(by["REC_GRIP"].x + BOX_W + 46, by["REC_GRIP"].cy),
                       (by["REC_GRIP"].x + BOX_W + 46, by["IDLE"].cy - 16),
                       (by["IDLE"].x + BOX_W + 18, by["IDLE"].cy - 16),
                       (by["IDLE"].x + BOX_W + 18, by["IDLE"].cy)],
                  label_at=(by["REC_GRIP"].x + BOX_W + 54, by["REC_GRIP"].cy - 20),
                  label_side="r"))

    # The escalation that makes the rename worth shipping at all.
    e.append(Edge("REC_GRIP:w", "ERR:w", kind="fault",
                  label="retry ≥ 3 → back to ERR\nand refuse the robot's CMD:2",
                  via=[(by["REC_GRIP"].x - 34, by["REC_GRIP"].cy),
                       (by["REC_GRIP"].x - 34, by["ERR"].cy - 30),
                       (by["ERR"].x - 18, by["ERR"].cy - 30),
                       (by["ERR"].x - 18, by["ERR"].cy)],
                  label_at=(by["REC_GRIP"].x - 42, by["REC_GRIP"].cy + 26),
                  label_side="l"))
    return e


BODY = """
<h2>What changes</h2>
<p>The amber chain is <strong>renamed, not renumbered</strong> — same wire values
10 / 11 / 12, so the robot cannot tell the difference. The purple chain is new and
is used by fault recovery only. Compare against
<a href="auto-state-machine-current.html">today</a>, where <code>ERR</code>
recovers by borrowing the amber chain.</p>

{diagram}
{legend}

<h2>The problem being solved, stated honestly</h2>
<p>Today one retract chain serves four callers, and a single boolean
<code>bHomeThenIdle</code> picks its exit. It is worth separating the
<em>diagnosis</em>, but it is worth being clear about which complaints are real:</p>
<div class="tblwrap"><table>
<thead><tr><th>Complaint</th><th>Verdict</th></tr></thead>
<tbody>
<tr><td>Sharing the retract <em>motion</em> between callers</td>
    <td><strong>Not a defect.</strong> Push-before-sep-before-grip is a collision-ordering constraint, not a caller concern. Three copies would be worse. Keep sharing it.</td></tr>
<tr><td><code>RESET</code> homing instead of jumping to <code>IDLE</code></td>
    <td><strong>Correct as-is.</strong> A fault leaves pistons anywhere, so <code>IDLE</code> would advertise &ldquo;ready&rdquo; falsely. Do not touch.</td></tr>
<tr><td>One boolean, four writers</td>
    <td><strong>Inelegance with a bad default.</strong> No live defect — all four entry points do write it. But it has no initialiser, so its cold-boot value <code>FALSE</code> is the &ldquo;run a bulb&rdquo; direction. Wrong fail-safe direction.</td></tr>
<tr><td>A failed recovery is indistinguishable from a failed arming</td>
    <td><strong>Real defect, and the one this page fixes.</strong> Both report codes 6/7/8 and the same <code>sStepText</code>. Worse, <code>iErrorCode</code> is cleared at RESET <em>before</em> the retract runs — so the original diagnosis is destroyed, and the robot presses RESET about a second after the fault, usually before a human has read the panel.</td></tr>
<tr><td>The recovery retry loop</td>
    <td><strong>Real defect — and renaming states does not fix it.</strong> See below.</td></tr>
</tbody></table></div>

<div class="callout bad">
<h3>Do not ship the rename without the retry counter</h3>
<p><code>ERR</code> &rarr; <code>STATE:99</code> &rarr; robot <code>CMD:2</code>
&rarr; clear error &rarr; retract &rarr; timeout &rarr; <code>ERR</code> &rarr; …
with <strong>no attempt counter and no escalation</strong>. Each lap takes about
<code>tStepTimeoutMs</code> plus a keep-alive, so roughly 11 s, and writes about
five log entries. The panel Log page shows 20 entries — so
<strong>the original fault scrolls off the panel in about four laps, under a
minute.</strong></p>
<p>The loop also closes the operator's only repair window: the PB jogs are live
only while <code>eStep = ERR</code>, so during each 10 s retract attempt they are
dead.</p>
<p>A prettier state name on an unbounded retry loop is a cosmetic change sold as a
safety one. The counter and the escalation edge are drawn in purple above; they
are the point.</p>
</div>

<div class="callout bad">
<h3>And the escalation needs one more change to be possible at all</h3>
<p><code>MAIN</code> deliberately fans the robot's <code>CMD:2</code> into the same
<code>stHmi.bReset</code> field the HMI button writes. That was the right call for
the deadlock fix, but it means <strong>the FB cannot tell an operator RESET from a
robot RESET</strong> — so &ldquo;after 3 failed attempts, only a human may clear
this&rdquo; is not expressible until that field is split in two.</p>
<p>This, rather than the chain sharing, is the actual reason ERR recovery
misbehaves on the machine.</p>
</div>

<h2>Also replace the boolean with a target state</h2>
<p>Independent of the new chain, and worth doing first because it is free:
<code>bHomeThenIdle : BOOL</code> becomes <code>eReturnTo :
E_MasterAutoStep</code>. Four writes and one read change; no new wire values, no
robot risk, no mock churn.</p>
<p>The gain is the fail-safe direction. An uninitialised <code>BOOL</code> is
<code>FALSE</code> = &ldquo;go run a bulb&rdquo;. An uninitialised
<code>E_MasterAutoStep</code> is <code>0</code> = <code>IDLE</code> — armed and
waiting, which is the conservative direction.</p>
<p>Do <strong>not</strong> let a future Pause feature reuse
<code>eReturnTo</code>. &ldquo;Where the retract chain exits to&rdquo; and
&ldquo;which step Pause interrupted&rdquo; are different facts that happen to share
a type; merging them repeats the <code>bHomeThenIdle</code> mistake one level
up.</p>

<h2>Enum numbering</h2>
<p>Occupied: 0, 1, 2, 3, 4, 5, 6, 7, 8, 10, 11, 12, 20, 21, 22, 30, 40, 99.
<strong>Nothing may be renumbered</strong> — these are wire values. 50 / 51 / 52
are proposed because a fresh decade matches the existing convention that
non-bulb-cycle states own decades (30 Manual, 40 Not-homed, 99 Err), and
<code>STATE:5x</code> is instantly greppable in a robot log. Avoid 13&ndash;15:
adjacency to 10/11/12 invites exactly the confusion being removed.</p>
<p><code>2</code> (<code>WAIT_POS2</code>) is retired but must not be reused — old
logs and CSV exports still carry it, same rule as retired error code 99. New error
codes 12/13/14 are free; <code>iErrorCode</code> is a separate namespace from the
step enum.</p>
{robot}
<div class="callout">
<h3>Unverifiable from this repo</h3>
<p>The robot's &ldquo;anything else &rarr; wait&rdquo; branch is a
<em>documented</em> contract, confirmed only against the two Python mocks. The
machine runs an <strong>uncommitted</strong> <code>src2.lua</code>, so before
shipping any new wire value, commit it or at least read the running copy off the
controller. Both mocks print <code>?</code> for an unknown number, so a missed
table update is cosmetic rather than a crash.</p>
</div>

<h2>What each party sees during recovery</h2>
<div class="tblwrap"><table>
<thead><tr><th></th><th>Today</th><th>With this change</th></tr></thead>
<tbody>
<tr><td>Robot wire</td><td class="m">99 → 10 → 11 → 12 → 0</td><td class="m">99 → 50 → 51 → 52 → 0</td></tr>
<tr><td>Robot behaviour</td><td>wait, wait, wait, then CMD:1</td><td><strong>identical</strong></td></tr>
<tr><td>Panel step text</td><td class="m">INIT_PUSH_RETRACTING — same as arming</td><td class="m">RECOVER_PUSH_RETR — unambiguous</td></tr>
<tr><td>Error on a failed retract</td><td class="m">6 / 7 / 8 — same as arming</td><td class="m">12 / 13 / 14</td></tr>
<tr><td>Status lamps</td><td>green <em>blinking</em> = &ldquo;running&rdquo; the moment RESET lands</td><td>can now be made distinct, because the states are distinct</td></tr>
<tr><td>Runaway recovery</td><td>invisible; original fault gone from the panel in ~45 s</td><td>escalates to a latched ERR after 3 attempts</td></tr>
</tbody></table></div>
<p>Note the shape: <strong>the wire semantics do not change and the robot needs no
new branch</strong> — only the diagnosis improves. That is the right trade.</p>

<h2>Suggested order</h2>
<ol>
<li><strong>Fix the unsafe <code>CASE ELSE</code> first, on its own.</strong> It
currently snaps any unhandled <code>eStep</code> to <code>IDLE</code> — wire value
0, &ldquo;send me a bulb&rdquo; — with pistons in unknown positions.
<code>NOT_HOMED</code> is the correct landing. Two lines, unrelated to everything
else. While in the file, delete the dead <code>bAnyRunning</code> or fix its
comment.</li>
<li><code>bHomeThenIdle</code> &rarr; <code>eReturnTo</code>. Zero wire risk.</li>
<li><strong>One enum commit reserving every new wire value at once</strong> —
<code>RECOVER_*</code> 50/51/52 <em>and</em> <code>PAUSED</code> 41. Then the robot
contract changes exactly once and you make one verification trip instead of two.
This is the most valuable sequencing decision on these three pages.</li>
<li>The <code>RECOVER_*</code> branches, error codes 12/13/14, the rename — plus
the attempt counter and the <code>bReset</code> split.</li>
<li>Pause / Continue last, copying the <code>eReturnTo</code> pattern into its own
separate variable.</li>
</ol>
<p>Keep the two features in separate commits but reserve their enum values
together: they collide on the same four places — the enum, the Section 2 override
block, the Section 3 timer selector and the Section 4 <code>CASE</code> — so
parallel branches would conflict in every one of them.</p>
"""


def build():
    states = build_states()
    svg, _, _ = render_svg(states, build_edges(states))
    body = BODY.format(diagram=f'<div class="diagram">{svg}</div>',
                       legend=legend_html(), robot=ROBOT_TABLE)
    return page(
        "Auto state machine — Retract-all split from ERR",
        "167_01 Saad — Flower · proposed variant",
        "Give fault recovery its own retract chain, so a failed recovery stops "
        "looking identical to a failed arming — and rename the shared chain to say "
        "what it actually is, keeping its wire values so the robot cannot notice.",
        "auto-state-machine-retract-all.html", body)
