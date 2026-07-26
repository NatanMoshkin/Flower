# Flower — project TODO / open issues

## TODO:

_(active TODOs land here; deferred items go under "Out of scope
(Future)" at the bottom.)_

### Robot tuning parameters — VISU exposure + range limits

The 11 `ST_RobotParams` tuning values have **documented valid ranges that
nothing on the PLC side enforces**. Ranges and units were traced to the
robot repo (`167_01_Saad_Flower/Robot/167-01-Saad/`, which is neither this
repo nor FlowerPyHmi — easy to miss):

- **Units are percentages.** `global.lua:44-48` `Init()` calls
  `VelJ(J_SPEED)` / `VelL(L_SPEED)` — commented "Joint Speed %" / "Linear
  Speed %" — plus `SpeedFactor(FACTOR_SPEED)` with `FACTOR_SPEED = 80`
  scaling everything globally. `WAX_SPEED` / `WATER_SPEED` feed the `v=`
  velocity-ratio option of `MovL` (`src0.lua:112,114,144,152`).
- **Authoritative ranges**, from the vendor's own GUI which clamps to them
  (`Robot/167-01-Saad/tcp client.py:14-21`, clamp at `:90`; byte-identical
  copy at `RobotBridge/Client_working_example/tcp client.py`, pasted into
  `readme.txt:27-32`):

  | Param | Range |
  |---|---|
  | `J_SPEED`, `L_SPEED` | 1–100 |
  | `WAX_SPEED`, `WATER_SPEED` | 0–100 |
  | `REPEATS` | 1–10 |
  | `START_WAIT`, `WATER_WAIT`, `STAND_WAIT`, `END_WAIT`, `WAX_WAIT_TIME_OUT` | 10–10000 |
  | `WAX_WAIT_TIME_IN` | 0–10000 |

Nothing validates these anywhere in our stack: `src2.lua:44-54` assigns
`tonumber()` straight through with no clamp, `ST_RobotParams` is bare `INT`
defaults, and `FB_RobotTcpClient` only marshals name/value. FlowerPyHmi now
range-checks on write (rejects with a 400 rather than clamping silently, so
the operator sees what was refused) — but it is only one of several possible
writers.

**Current VISU state (updated 2026-07-26):** all 11 tuning values are now
editable on `PLC1/VISU/Robot.TcVIS`, each with `InputBoxMin`/`InputBoxMax`
set to the vendor range in the table above (`scripts/add_robot_params.py`).
So the panel is bounded — **but per-control limits only protect the control
they are set on**, which is why item 1 below still matters: FlowerPyHmi,
any future ADS client, and the `bSetParam` escape hatch all bypass them.

Note the comment in `ST_RobotParams` ("All INT so the classic VISU HMI binds
NumericInput directly") describes an intent that was never implemented.

To do, in preference order:

1. ~~Clamp in `FB_RobotTcpClient`.~~ **Done 2026-07-26.** `ClampParam` /
   `ParamMin` / `ParamMax` bound every writer that reaches the robot through
   this FB — the panel, FlowerPyHmi over ADS, any future ADS client, and the
   `bSetParam` escape hatch (via `ParamIndex` reverse lookup; unknown names
   pass through unclamped, which is the point of an escape hatch).

   Two design points worth not undoing:
   - The clamp **writes the bounded value back into `stParams`**
     (`SetParamValue`). It is not cosmetic: the shadow is updated to the
     value that was *sent*, so leaving an out-of-range number in the field
     would keep it permanently different from its shadow and the FB would
     re-send on every idle scan — a silent packet storm. Writing back
     converges, and the panel then shows what the robot actually got.
   - Clamping applies **only on the way out**, never to values arriving in a
     `SYNC` reply. Rewriting a robot-sourced value would push our table back
     at the robot, and if the table were ever wrong the two ends would fight.
2. ~~Add the NumericInputs to `Robot.TcVIS` with `min`/`max`.~~ **Done
   2026-07-26** — 11 editable fields, each range-clamped per the table.
   (The open question of whether a panel operator *should* be able to change
   robot speeds was answered by doing it; revisit if that turns out wrong.)
3. ~~Replace the stale `ST_RobotParams` comment with the real units and
   ranges.~~ **Done 2026-07-26** — the struct now documents percentages vs
   milliseconds, cites `global.lua` for the units, carries the range per
   field, and says outright that `INT` is an encoding detail. The old claim
   that it was "all INT so the classic VISU HMI binds NumericInput directly"
   described an intent that went unimplemented until the panel grid landed.

Keep `scripts/check_pyhmi_contract.py` in mind: if bounds move into the PLC,
FlowerPyHmi's copy in `flower_py_hmi/robot.py` (`ParamField.lo/hi`) becomes a
second source of truth that nothing keeps in step.


## SHIPPED: robot integration architecture — TCP-only (2026-07-26)

Resolved. `FB_RobotTcpClient` (`Tc2_TcpIp` on TF6310) is the sole channel
between the PLC and the Dobot. The former discrete-I/O handshake
(`STAND_SEQ_DO`/`STAND_SEQ_DI`) is retired; `DI[13]` and `DO[7]` are free.

The four original options in `docs/robot-integration-options.md` are now
historic; the file is kept for archaeology but does not describe current
behaviour. `RobotBridge/` (Python) is out of scope for the panel — kept
only as protocol reference (`Client_working_example/`). `FlowerPyHmi/`
remains engineering-side (runs on any developer laptop) and unaffected.


## DECISION: 167_01 panel solution — TCP-only robot comms + global Auto/Manual interlock

Scope: `Panel_PLC_HMI/167_01_Saad_PLC/` is the **only** PLC solution.

**`Flower_PLC_HMI/` was deleted 2026-07-26.** It held the dev PLC solution
(a byte-for-byte mirror for local PC testing) and the TwinCAT web HMI
`Flower_HMI/`. Both are retired — there is no mirror to keep in sync any
more, so PLC edits land in one place only. The engineering-side UI is now
`FlowerPyHmi` (separate git repo at `167_01_Saad_Flower/FlowerPyHmi`,
talks ADS to the panel; not a submodule, so nothing keeps its symbol
contract in step automatically — run `python scripts/check_pyhmi_contract.py`
after changing any HMI-facing GVL or DUT). Recover the old solution from
git history if ever needed.

**Global Auto/Manual hard interlock (2026-07-19).** A single machine-wide
BOOL `GVL_HmiPersistent.stMasterAutoCfg.bAutoMode` is the sole source of
truth for every piston's mode — "no option to double control". `MAIN` drives
it unconditionally each scan onto BOTH `eMode` and `bMode` of all eight
pistons (six Sep/Push + two Grip). `FB_SolSpringPiston_2Pos` edge-syncs the
two, so forcing only one would let a stray toggle propagate for a scan;
forcing both closes that gap. In Auto the MasterAutoCycle owns all eight
pistons — no per-piston auto tiles in the panel solution. In Manual the
master cycle is held IDLE and the operator jogs. `E_ControlMode`:
Manual=0, Automatic=1.

**Robot comms — TCP-only (2026-07-26).** `FB_RobotTcpClient` (native ST,
uses free-with-TF6310 `Tc2_TcpIp`) dials the robot server `:6001`. TF6310
is installed+running on the CP6606 — the documented exception to the
avoid-paid-libs rule. All start/stop/reset traffic goes through this
channel; the former discrete-I/O handshake (`STAND_SEQ_DO`/`STAND_SEQ_DI`)
is retired and its DI[13] / DO[7] channels are free.

- Protocol (raw ASCII, NO newline framing; one send → one reply — matches
  `RobotBridge/Client_working_example/tcp client.py` + `dummy_server.py`
  plus the new STATE/CMD frames):

  | PLC → robot | Robot → PLC | Purpose |
  |---|---|---|
  | `GET_SYNC` | `SYNC:NAME=VALUE,...` | Pull all 11 tuning params |
  | `NAME:VALUE` | `OK: SET NAME` | Set one tuning param |
  | `New_Bulb:1` | `OK: SET New_Bulb` | Start a fresh bulb |
  | `STATE:<n>` | `CMD:<m>` | State push + command receive |

- `STATE:<n>` (`n = INT` value of `E_MasterAutoStep`, or `MANUAL=30` when
  `bAutoMode=FALSE`). Sent on every change of `stParams.nStateOut` and
  every `IDLE_STATE_MS` (default 1000 ms) as keep-alive. Replaces the old
  `HEARTBEAT` frame.
- `CMD:<m>` (`m` ∈ {0,1,2}: 0=none, 1=start cycle, 2=reset error).
  Written into `stParams.nRobotCmd`; `MAIN` R_TRIGs on the value and
  feeds pulses into FB_MasterAutoCycle (`bExtStartPulse`) or the HMI's
  `bReset`. The robot is responsible for zeroing after the next state
  push acknowledges the command.

- `DUTs/ST_RobotParams.TcDUT` — 11 INT tuning params + request flags
  (`bGetSync`, `bSetParam`/`sSetName`/`nSetVal`, `bTriggerNewBulb`, FB
  auto-clears each after ACK) + the two INTs `nStateOut` / `nRobotCmd`.
- `GVL_Robot`: `stParams`, `sRobotHost` (default '192.168.201.1'),
  `nRobotPort` (6001), `bTcpEnable`. Status mirror in `stRobot`:
  `eConnState`/`sConnStateText`/`nPacketsRx`/`nPacketsTx`/
  `sLastMessage`/`sLastTxMessage`. `MAIN` calls `fbRobotTcp` each scan.
- Connection state machine: Disconnected → Connecting → Connected → (any
  socket error) close + reconnect after 3 s. Empty `sSrvNetId` targets
  the local TF6310 server. `CMD:0/1/2` verified against the robot
  2026-07-26.

**Tuning params are read/write (shadow-copy push, 2026-07-26).** They used
to be read-only in practice: `GET_SYNC` pulled values in, but the only way
to push one back was the `bSetParam`/`sSetName`/`nSetVal` triple, which
*nothing* ever set — no VISU page, no MAIN code, no HMI binding. Since
`GVL_Robot` is `AddSymbol`-exposed, an operator editing `stParams.J_SPEED`
saw the value change, nothing was sent, and the next reconnect's `GET_SYNC`
silently reverted it.

`FB_RobotTcpClient` now keeps `aShadow : ARRAY[1..11] OF INT`, re-baselined
by `SetShadowAll` after every `GET_SYNC` round-trip. Any live field that
diverges from its shadow slot is an operator edit and is pushed as
`NAME:VALUE`, one param per round-trip; `HandleReply` banks the value that
was *sent* (`nPendVal`), so an edit made mid-round-trip is re-sent rather
than swallowed. So an HMI NumericInput can bind straight to
`GVL_Robot.stParams.J_SPEED` and just work. The `bSetParam` triple survives
as a raw escape hatch for names that aren't struct fields.

Index↔name mapping lives in `ParamValue` / `ParamName` and **must** match
the robot's `SYNC_ORDER`. `bShadowValid` gates detection until the first
SYNC lands, so the compiled-in defaults are never mistaken for edits.

`IO_IDLE` priority order matters and is asserted by the tests:
1. post-connect one-shot `GET_SYNC` — a `STATE` reply can carry `CMD:1`,
   and a cycle must not start on unsynced params;
2. `STATE` on change — `CMD` frames ride back on `STATE` replies, so a
   write burst must not starve start/reset;
3. explicit `bSetParam` / `bTriggerNewBulb` / `bGetSync`;
4. detected edits;
5. `STATE` keep-alive.

*Known limitation:* `stParams` is both setpoint and actual, so an edit made
while the link is down is overwritten by the reconnect's `GET_SYNC`.
Separating desired-vs-actual needs a second struct — deferred.

`scripts/test_param_shadow_logic.py` ports the sequencer to Python and runs it
against the protocol (9 cases: no startup echo, edit pushed, all three
speeds, state preemption, CMD during write burst, mid-flight re-edit,
escape hatch, re-sync baseline, malformed SYNC). Run
`python scripts/test_param_shadow_logic.py`. It validates the *algorithm*, not
the ST build — a TwinCAT compile is still required.


## DECISION: FB_MasterAutoCycle drives the full-machine auto sequence

The machine's operator-facing cycle is implemented as `FB_MasterAutoCycle`
(commit `9ba7a14`, with mode-forcing added in `8a39fae`, and simplified
robot interface added 2026-07-10). It coordinates the 3 pairs of (SepSolN,
PushSolN) pistons in parallel with a single robot handshake signal. The
former "Pair count" runtime knob (`uiPairCount`) was removed 2026-07-12 —
pair count is fixed at 3.

**Robot interface (TCP-only, 2026-07-26):** all robot signals travel over
`FB_RobotTcpClient` (see the panel-solution decision above for the
protocol). No discrete-I/O handshake anymore.

| Direction | ST_RobotParams field | Wire | Semantic |
|---|---|---|---|
| PLC → Robot | `nStateOut : INT` | `STATE:<n>` frame | `TO_INT(eStep)` in Auto; `MANUAL=30` in Manual. Robot derives "PLC is running" from `n ≠ 0`. |
| Robot → PLC | `nRobotCmd : INT` | `CMD:<m>` reply | 0=none, 1=start cycle (rising edge → `bExtStartPulse`), 2=reset error (rising edge → `stMasterAuto.bReset`). |

The former `POS1/POS2/POS3` + `AUTO_STARTED/PUSH_DONE/PISTONS_ERROR` TCP
protocol and the `STAND_SEQ_DO`/`STAND_SEQ_DI` discrete-I/O handshake
are both retired. `WAIT_POS2` is retired too — the Dobot's
`PerformStandSequence` moves the arm clear of the stand *before* it
issues `CMD:1`, so no intermediate "robot moved away" wait is needed.

**Fifteen-state state machine** (`E_MasterAutoStep`; `WAIT_POS2` value
still declared in the enum but unused — safe to remove once every HMI
page has stopped referring to it):

```
IDLE (0)                Wait for operator START OR bExtStartPulse (robot
                        CMD:1 edge) OR bSimStep_Idle OR bContinuous checked
                        (level — while checked, IDLE starts the next cycle
                        immediately). On start, transitions to
                        INIT_PUSH_RETRACTING (not directly to SEP_EXTENDING)
                        so pistons left extended by a prior manual move are
                        driven home first. nStateOut = 0 here so the robot
                        sees "PLC idle" via TCP.
INIT_PUSH_RETRACTING(10) Drive PushCmdRetract[1..3]; wait AND of all 3
                        PushIsRetracted. Auto-satisfies on the next scan
                        when push is already home.
INIT_SEP_RETRACTING (11) Drive SepCmdRetract[1..3]; wait AND of all 3
                        SepIsRetracted.
INIT_GRIP_RETRACTING(12) Drive GripCmdRetract[1..2]; wait AND of all
                        GripIsRetracted. Defensive symmetry with the INIT
                        Sep/Push states so a manual jog left extended does
                        not collide with the arriving plate.
WAIT_PLATE (20)         Wait `bPlateSenL AND bPlateSenR` (robot has placed
                        the plate). Latched at start only; sensors not
                        monitored past this step. Timeout uses
                        `tPlateWaitTimeoutMs` (bounded by robot placement time).
                        `stCfg.bBypassPlateSensors` suppresses the timeout
                        ERROR only — see the plate-sensor section below.
GRIP_EXTENDING (21)     Drive GripCmdExtend[1..2]; wait AND of all
                        GripIsExtended. Plate clamped from both sides.
SEP_EXTENDING (1)       Drive SepCmdExtend[1..3]; wait AND of all
                        SepIsExtended. Grip stays extended for every state
                        below (held from GRIP_EXTENDING through SEP_RETRACTED_DWELL).
PUSH_EXTENDING (3)      Drive PushCmdExtend[1..3]; wait AND of all PushIsExtended.
DWELL_PUSH (4)          Hold both extended; wait tDwellPushMs (default 2000).
PUSH_RETRACTING (5)     Drive PushCmdRetract[1..3]; wait AND of all PushIsRetracted.
PUSH_RETRACTED_DWELL(6) Wait tPushRetractedDwellMs (default 500).
SEP_RETRACTING (7)      Drive SepCmdRetract[1..3]; wait AND of all SepIsRetracted.
SEP_RETRACTED_DWELL (8) Wait tSepRetractedDwellMs (default 500).
GRIP_RETRACTING (22)    Drive GripCmdRetract[1..2]; wait AND of all
                        GripIsRetracted. Releases the plate; increment
                        nCyclesCompleted; back to IDLE (which re-arms by
                        itself while Continuous is checked).
ERR (99)                Latched. iErrorCode = step's fault code.
                        bContinuous cleared on entry so RESET does not
                        restart motion. nStateOut = 99 so the robot sees
                        the fault via TCP. Reset on HMI RESET rising edge
                        OR robot CMD:2.
```

A 16th sentinel value **MANUAL (30)** exists in the enum but is never
assigned to `eStep`. `MAIN` reports it to the robot as `nStateOut = 30`
while `bAutoMode = FALSE` — the enum is the shared vocabulary between
PLC and robot, so this sentinel lives there rather than as a magic INT.

**Error codes** (`ST_HmiMasterAuto.iErrorCode : INT`, 0 = OK):

| Code | Meaning                            |
|------|------------------------------------|
| 0    | OK                                 |
| 1    | SEP_EXTENDING timeout              |
| 3    | PUSH_EXTENDING timeout             |
| 4    | PUSH_RETRACTING timeout            |
| 5    | SEP_RETRACTING timeout             |
| 6    | INIT_PUSH_RETRACTING timeout       |
| 7    | INIT_SEP_RETRACTING timeout        |
| 8    | INIT_GRIP_RETRACTING timeout       |
| 9    | WAIT_PLATE timeout (plate not present) — suppressed by `bBypassPlateSensors` |
| 10   | GRIP_EXTENDING timeout             |
| 11   | GRIP_RETRACTING timeout            |
| 99   | Operator STOP while running        |

(Code 2 was the retired `WAIT_POS2` timeout.)

**Master sensorless mode** (`stMasterAutoCfg.bNoSensors`, default FALSE) —
mirrors the per-piston `bNoSensors`. When TRUE, the 8 movement states
(both INIT sets, both GRIP states, all 4 Sep/Push states) ignore sensor
feedback and advance when `tStepTimeoutMs` expires — the timeout doubles
as the fixed step duration, so error codes 1/3/4/5/6/7/8/10/11 cannot
occur while sensorless. `WAIT_PLATE` uses its own `tPlateWaitTimeoutMs`
and still requires both plate sensors TRUE (bNoSensors doesn't skip the
plate gate). Panel checkbox "No sensors (timed steps)" is the third
checkbox on `AutoMain.TcVIS` at (20,335), bound to `stCfg.bNoSensors`
— added 2026-07-26 by `scripts/add_nosensors_checkbox.py`, which clones the
existing "Auto Mode" checkbox block rather than authoring one. **Use that
cloning approach for any further classic-VISU element** — these files use
numeric-ID serialization and XAE silently drops elements it cannot parse,
so always open the page in TcXaeShell and confirm the element renders
before activating.

## PLATE SENSORS: status on Main + bypass (2026-07-26)

**Status.** `Main.TcVIS` shows both plate sensors in the 110 px strip to the
right of the embedded AutoMain frame (which spans x −4…684): a "Plate" title
with `L` / `R` lamps at x=724, bound to `GVL_HMI.bPlateSenL` / `bPlateSenR`
(MAIN's mirror of `GVL_App.bPlateSen*`). On the home screen, so the operator
can see plate presence without opening a page.
Built by `scripts/add_main_plate_status.py`.

**Bypass.** `stCfg.bBypassPlateSensors` (default FALSE, 4th checkbox on
AutoMain at (20,375)). It removes **only the WAIT_PLATE timeout error**, not
the wait:

- the `bPlateSenL AND bPlateSenR` fast-path still advances the cycle, so
  with healthy sensors behaviour is completely unchanged;
- with unwired or faulty sensors, `tPlateWaitTimeoutMs` degrades into a
  fixed placement dwell and the cycle continues instead of raising error 9.

That shape was chosen over "ignore the sensors entirely" because the robot
still needs time to place the plate — a bypass that advanced instantly would
close the grippers on nothing.

It is deliberately **separate from `bNoSensors`**, which by long-standing
decision does not cover `WAIT_PLATE`. Skipping the plate gate is
safety-relevant and should be an explicit choice, not something inherited
from a bench-testing flag.

**Per-step simulate flags** on `ST_HmiMasterAuto.bSimStep_*` let a bench
operator advance any waiting step without physical sensors — rising-edge
triggered, FB auto-clears after consumption. `UC_MasterAutoCycle` renders
them as a vertical table (one row per state in chronological run order),
background highlights yellow when `eStep` matches the row's enum value,
red for the ERR row.

**External start pulse.** MAIN owns the `R_TRIG` on `stParams.nRobotCmd = 1`
and feeds a one-scan pulse into FB_MasterAutoCycle's `bExtStartPulse`
VAR_INPUT. HMI checkbox "Sim bStartAssembly" binds
`ST_HmiMasterAuto.bSimStartAssembly` (TwoWay) — a bench sim flag consumed
by the FB's own R_TRIG and OR-merged inside the IDLE state exit condition
alongside the operator's START button and the external pulse. Also driven
by PB1 rising edge in Auto mode (see the panel-hardware decision below).

**Logging.** `F_LogEvent` fires on every state transition (INFO for
normal `PREV -> NEW`, ERR for entries into ERR with `sMsg = sErrorText`),
on operator START/STOP/RESET edges, on Sim start edges, and on external
start pulses. `sSource = stHmi.Name`. Bench sim step advances are not
logged (would spam production).

## DECISION: per-piston auto tiles + sensorless mode

Every piston (SepSol1..3, PushSol1..3) has its own `FB_PistonAutoCycle`
instance in MAIN and a dedicated tile on `StartPage.content` (3×2 grid,
337×340 tiles: Sep row on top, Push row on bottom). Each tile binds to
`GVL_HMI.stXxxAuto` (runtime state) and `GVL_HmiPersistent.stXxxAutoCfg`
(PERSISTENT config). Callers wire each auto FB's `bCmdExtend` /
`bCmdRetract` outputs into the piston FB's `bAutoCmd*` inputs OR-merged
with `fbMasterAutoCycle.bXxxCmd*[i]`, so both the per-piston tile and
the master sequence can drive the same piston without stepping on each
other.

**Sensorless mode** (`ST_HmiPistonAutoCfg.bNoSensors`, default FALSE):
- FALSE — standard sensor-driven behavior. `tTimeoutExtendMs` /
  `tTimeoutRetractMs` are timeouts; expiry raises an error.
- TRUE — the state machine ignores sensor feedback and advances on
  timer expiry. Same fields become fixed extend/retract *durations*
  (relabelled in the UC as "Extend time (ms)" / "Retract time (ms)"). No
  feedback-mismatch check, no "sensor never arrived" error path. Use for
  bench cycling on pistons whose proximity switches aren't wired.

## DECISION: PLC is the TCP client; robot is the server

The robot comms live in `FB_RobotTcpClient` (`Panel_PLC_HMI/…/PLC1/POUs/`)
which uses the free-with-TF6310 `Tc2_TcpIp` library to dial the robot at
`GVL_Robot.sRobotHost:nRobotPort` (default `192.168.201.1:6001`). TF6310
is installed+running on the CP6606 — this is the documented exception
to the avoid-paid-libs rule (see project memory
`feedback_avoid_licensed_beckhoff_libs.md`).

The former Python bridge (`RobotBridge/`) is out of scope for the panel
solution because Windows Embedded Compact 7 on ARM has no supported
CPython+pyads. Kept only as protocol reference
(`Client_working_example/tcp client.py` and `dummy_server.py`).

Connection semantics:
- Persistent socket (one open TCP connection while up).
- 2-second timeout on connect / send / recv (per Tc2_TcpIp).
- On any error → close socket → wait 3 s → re-dial. Repeats forever
  while `bTcpEnable = TRUE`.
- `STATE:<n>` keep-alive every ~1 s serves the "is the socket alive?"
  role that a bare HEARTBEAT used to fill.

## PANEL VISU: page inventory + the numeric-entry constraint (2026-07-26)

Six classic VISU pages, all registered in `PLC1.plcproj` with a
`<Compile Include>` + `<DependentUpon>VISU\VisualizationManager.TcVMO</...>`
block (a new `.TcVIS` is invisible to the build without one):

| Page | Contents | Reached from |
|---|---|---|
| `Main` | AutoMain embedded as a frame + 3 nav buttons | — |
| `AutoMain` | title, step/error fields, START/STOP/RESET, 3 checkboxes | embedded in Main |
| `PistonsManual` | 6 Piston frames (Sep/Push 1-3) | Main |
| `GripperManual` | 2 Piston frames (`stGripSolL` / `stGripSolR`) | Main |
| `Robot` | conn state, Rx/Tx counts, last Rx/Tx, nStateOut, nRobotCmd, Get Sync + New Bulb buttons | Main |
| `Piston` | the reusable per-piston control, instanced via frames | — |

Each page's `<Visu Id>` GUID equals every `VisualElementOwningObjectGuid`
inside it — hold that invariant when cloning a page.

**Numeric entry — resolved 2026-07-26.** The project originally had only two
input mechanisms (`Visu_TapInput` → BOOL, and `ChangeVisuInputAction`), so
there was nothing to clone for an editable number. The operator authored one
template in TcXaeShell (`GenElemInst_229` on `Robot`), and all 16 editable
fields are clones of it.

The template is a plain **`VisuFbElemTextfield`** whose `OnMouseClick`
carries an **`InputBoxInputAction`**; `UseTextOutputVariable=true` means it
writes back through the normal displayed-variable member (`2477733581L`).
So a display field and an edit field differ *only* by that action block —
which is exactly why it could not be invented and had to come from the IDE.

- `Robot` — 11 params at x 420-770, `GVL_Robot.stParams.<NAME>` (absolute:
  standalone page).
- `AutoMain` — 5 timers at x 500-780, `stCfg.<name>` (**interface-relative**:
  AutoMain is embedded as a frame in Main and declares
  `stCfg : ST_HmiMasterAutoCfg`; absolute paths would be wrong here).

Build/verify scripts, all idempotent and all cloning proven blocks rather
than authoring them: `scripts/build_grippermanual.py`,
`scripts/build_robot_page.py`, `scripts/add_main_nav.py`,
`scripts/add_nosensors_checkbox.py`, and `scripts/validate_visu.py`
(**run this after every VISU edit** — it asserts each element is a direct
child of `VisualElementList`, which is the check XML well-formedness does
not give you).

Static label text lives in `GlobalTextList.TcGTLO`, keyed by each element's
counter member `823443203L`. The scripts register their own entries; XAE
also adds missing ones on first open.


## PANEL HARDWARE: 3 push buttons + 3 LEDs (2026-07-26)

Three momentary-contact push buttons with integrated LEDs are wired to
the panel's DI/DO. Behaviour is gated by `bAutoMode`:

| PB | DI | LED (DO) | In Automatic | In Manual |
|---|---|---|---|---|
| PB1 | dIn[20] | dOut[10] | Rising edge → cycle-start bypass (writes `stMasterAuto.bSimStartAssembly := TRUE`). Redundant with robot CMD:1. | Held → both grip pistons extend (`bJogExtend` OR-merged into `FB_SolSpringPiston_2Pos` at MAIN call site). |
| PB2 | dIn[21] | dOut[11] | Ignored. | Held → all 3 SepSol pistons extend. |
| PB3 | dIn[22] | dOut[12] | Ignored. | Held → all 3 PushSol pistons extend. |

LEDs are dumb mirrors of the raw PB press state (`GVL_App.bLedPbN :=
GVL_App.bPbN`) — a wiring / hardware-health diagnostic, not a status
indicator. Room to repurpose later: swap the LED-write source (running,
error latched, TCP connected, etc.) without touching the DI wiring.

PB inputs live in `GVL_App` (not HMI-mapped). `PRG_IoMap.ReadInputs`
copies from `dIn[20..22]`; `PRG_IoMap.WriteOutputs` copies to
`dOut[10..12]`. MAIN's jog OR-merge into piston FBs uses the new
`FB_SolSpringPiston_2Pos.bJogExtend` VAR_INPUT so the HMI-owned
`stHmi.bManJogExtend` field is not mutated by MAIN.

## DECISION: HMI contract lives in any GVL with the `TcHmiSymbol.AddSymbol` pragma

Four GVLs expose symbols to the HMI today: `GVL_HMI`, `GVL_HmiPersistent`,
`GVL_Log`, `GVL_Robot`. Kept split by concern (piston state / persistent
config / diagnostics / robot bridge). The `{attribute 'TcHmiSymbol.AddSymbol'}`
pragma is the searchable marker — grep for it under `PLC1/GVLs/` and you
have the whole PLC↔HMI contract:

```
grep -l "TcHmiSymbol.AddSymbol" Panel_PLC_HMI/167_01_Saad_PLC/167_01_Saad_PLC/PLC1/GVLs/
```

**Rule for new HMI-facing symbols:** put them in the GVL whose concern
they match. Do not consolidate into `GVL_HMI`. Add the pragma so they
show up in the grep.

**Naming convention:** GVL names reflect *concern*, not HMI-facing status —
`GVL_Robot`, `GVL_Log`, `GVL_HmiPersistent`. The pragma is the marker, not
the `Hmi*` prefix. `GVL_HMI` (piston state) is a legacy name; it could be
renamed to `GVL_HmiPistons` for symmetry, but that's cosmetic churn — no
value if kept as-is. Do not rename `GVL_Robot`/`GVL_Log` to add an `Hmi`
prefix; their concern is more specific than "HMI-facing".

## DECISION: FB interface convention — VAR_INPUT / VAR_OUTPUT / VAR_IN_OUT

The `FB_MasterAutoCycle` / `FB_PistonAutoCycle` / `FB_SolSpringPiston_2Pos`
interfaces settled on this split — new FBs should follow it:

| Section | When to use | Rationale |
|---|---|---|
| `VAR_INPUT` | Read-once sensors, discrete signals, setpoints (`bSwitchExtended`, `bAtPos1`, per-scan raw values) | Copy-on-call semantics; caller passes a value, FB reads it and doesn't write back. Cheap for scalars. |
| `VAR_OUTPUT` | FB-produced per-scan signals that the caller reads (`bCmdExtend`, `bSepCmdExtend[]`, `bAnyRunning`, `iErrorCode`) | Caller reads via `.OutputName`. Enables OR-merge at the call site: `fbA.bCmdExtend OR fbB.bCmdExtend`. |
| `VAR_IN_OUT` | Large shared structs the FB both reads and writes (`stHmi`, `stAuto`, `stCfg`, `stRobot`) | Pass-by-reference under the hood — zero copy cost. Works with persistent structs (VAR_OUTPUT would reset each cold boot). |

**Alternatives considered and rejected:**
- All-`VAR_OUTPUT` for configs → copies large structs every scan; also
  breaks persistence (VAR_OUTPUT is not persistent-safe).
- All-`VAR_IN_OUT` (including for outputs) → breaks the OR-merge pattern
  at call sites; anyone with the ref can mutate what should be a produced
  signal.
- `POINTER TO` / `REFERENCE TO` → lower-level than `VAR_IN_OUT`, no
  init/bounds checks. Use only for array-of-refs situations; otherwise
  `VAR_IN_OUT` wins.

## DECISION: IO mapping architecture (Level 1 today; Level 2 for future)

**Current state (Level 1):** IO copy lives in a dedicated `PRG_IoMap`
PROGRAM with two actions — `PRG_IoMap.ReadInputs` and
`PRG_IoMap.WriteOutputs`. `PRG_IoMap`'s own implementation body is
`ReadInputs(); WriteOutputs();`, so both fire every time the task calls
`PRG_IoMap`. PRG_IoMap runs on a dedicated `IOmapTask` (5 ms cycle,
priority 15) which pre-empts `PlcTask` (10 ms, priority 20). MAIN sees
fresh sensor state when it starts, and command writes it makes to
`GVL_App.bValve*` land on the physical outputs within the next 5 ms
IOmapTask cycle. MAIN no longer touches `GVL_IO` directly.

**Do not call `PRG_IoMap.ReadInputs` / `.WriteOutputs` from MAIN** — that
would double-execute them on top of the task-driven call and break scan
ordering assumptions.

**Reference architecture (Level 2, future):** The Vacuum sister project
(`C:\Users\Natan.Moshkin\source\repos\Vacuum\KFM010_SCD_PLC`) uses a
richer pattern:

- A top-level `PROGRAM IO` with empty body acts as a namespace container.
- Its `VAR_OUTPUT` slots are per-station `IOModel` FBs.
- Each `IOModel` FB is `FUNCTION_BLOCK FINAL` with `VAR_OUTPUT` members of
  type `TC_Terminals.EL1008` / `TC_Terminals.EL2008` / `TC_Terminals.EL3078`
  etc. — typed Beckhoff terminal FBs from the free `TC_Terminals` library.
- Consumers reference `IO.Services.DI_01.Ch2` directly — compile-time
  typed access, no copy loop, no BOOL-index bookkeeping.
- Example: `Vacuum/.../IOModels/ServicesIOModel.TcPOU`,
  `.../MAIN.TcPOU` (declared but never called; TwinCAT auto-instantiates
  PROGRAM singletons and wires their internal AT % declarations).

**Do not adopt Level 2 blindly.** Verify `TC_Terminals` library
availability on the CP6606 WinCE 7 ARM target before committing — the
Vacuum project runs on a beefier CX-class controller. If unsupported,
Level 1 is the ceiling for this platform.

## DECISION: physical IO channel assignment

`GVL_IO.dIn` sized `ARRAY[1..24] OF BOOL`, `GVL_IO.dOut` sized
`ARRAY[1..16] OF BOOL`. All 8 pistons, the plate sensors, and the
panel push-buttons + LEDs are wired. Mapping lives in `PRG_IoMap.TcPOU`
(`ReadInputs` / `WriteOutputs` actions).

| Actuator / signal | DI (Retract) | DI (Extend) | DO |
|---|---|---|---|
| SepSol1 | dIn[1] | dIn[2] | dOut[1] |
| SepSol2 | dIn[3] | dIn[4] | dOut[2] |
| SepSol3 | dIn[5] | dIn[6] | dOut[3] |
| PushSol1 | dIn[7] | dIn[8] | dOut[4] |
| PushSol2 | dIn[9] | dIn[10] | dOut[5] |
| PushSol3 | dIn[11] | dIn[12] | dOut[6] |
| (retired robot discrete-IO) | dIn[13] free | — | dOut[7] free |
| GripSolL | dIn[14] | dIn[15] | dOut[8] |
| GripSolR | dIn[16] | dIn[17] | dOut[9] |
| PlateSenL | dIn[18] | — | — |
| PlateSenR | dIn[19] | — | — |
| PB1 (grip / cycle-start bypass) | dIn[20] | — | dOut[10] LED1 |
| PB2 (Sep jog) | dIn[21] | — | dOut[11] LED2 |
| PB3 (Push jog) | dIn[22] | — | dOut[12] LED3 |
| free | dIn[23..24] | — | dOut[13..16] |

Tag convention: `<Device>Sol<N>` = single Extend coil (SOL-Spring, spring
retracts). Retract sensors still exist on the DI side — the
retracted-position feedback is useful even without a retract coil.

To add a new actuator, extend `GVL_IO` (already sized DI[1..24] /
DO[1..16]; grow arrays if needed), add its GVL_App alias, wire it in
`PRG_IoMap.ReadInputs` / `WriteOutputs`, then finish the EtherCAT link
in the System Manager.

## Out of scope (Future)

- **Review persistent vars** — verify `stXxxAutoCfg` and `stMasterAutoCfg`
  actually survive a power-cycle. Needs a bench test (set value → hard
  power cycle → verify), not a code review.
- **Reassign LEDs to functional statuses.** Currently PB1/2/3 LEDs are
  dumb mirrors of the press state. Repurposing candidates: LED1 = cycle
  running, LED2 = error latched, LED3 = TCP connected. Deferred until
  operator preference is known — the LED source is a one-line change in
  `MAIN.TcPOU`.
- ~~Delete deprecated fields in `ST_HmiRobot`.~~ **Done 2026-07-26** —
  `bAtPos1/2/3`, `bTx*` and `bRxResetError` removed. Nothing referenced them:
  no POU, no VISU page, and `scripts/check_pyhmi_contract.py` still resolves
  229/229 FlowerPyHmi symbols without them.


## Playwright

- http://127.0.0.1:3003/liveview_64DA0B941E542F0480ED7063192BC500.html
- Put the screenshots to some temp folder