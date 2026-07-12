# Flower — project TODO / open issues

## TODO:

_(active TODOs land here; deferred items go under "Out of scope
(Future)" at the bottom.)_

- FB_MasterAutoCycle. add "No sensors" checkbox on the Masters Auto Cycle page (and PLC FB) like the Auto settings per pistons option

- FB_MasterAutoCycle. Remove the "Pair count" parameter

- FB_MasterAutoCycle. Check "Sim bStartAssemlby" code and validate  - did not work sometimes to me while testing. It should start the cycle from Idle state

- FB_MasterAutoCycle. "Continues cycling" need to bypass the start or bStartAssemlby and go from Idle to the next state


## OPEN ISSUE: robot integration architecture (blocking — decide before shipping)

The current design (`RobotBridge/` Python + pyads) cannot run on the CP6606
because Windows Embedded Compact 7 on ARM has no supported CPython + pyads.
Discovered 2026-07-10. Four options on the table; details, tradeoffs, and
cost/effort estimates in `docs/robot-integration-options.md`.

Summary of the options (ranking updated 2026-07-10 after robot code inspection):

| # | Option | Status |
|---|--------|--------|
| **1** | **Discrete I/O between robot and PLC (skip TCP entirely)** | **★ Recommended.** Dobot code (SAAD 167-01) already defines `STAND_SEQ_DO` / `STAND_SEQ_DI` and has ≥ 10 DI + 4 DO in use — the handshake half is already built on the robot side. |
| 2 | Replace CP6606 with x86 Beckhoff (CX5340 + panel, or CP2xxx) | Fallback if Option 1 blocks. Capital cost, downtime, license transfer. |
| 3 | Add companion box (RPi 4 Linux or industrial NUC) hosting `RobotBridge/` | Fallback if Option 1 blocks. Adds one production-critical device. |
| 4 | Serial (RS-232 / RS-485) via EL6001 / EL6021 + free Tc2_SerialCom | Likely N/A — Dobot Lua code shows no serial usage. |
| — | Rewrite bridge in C#/.NET CF 3.5 for CE 7 (rejected: dead tooling) | — |

Note: `FlowerPyHmi/` is engineering-side (runs on any developer laptop) —
it is **not** part of this decision and stays on the engineering PC
regardless of which option wins. Only `RobotBridge/` is at stake.


## DECISION: FB_MasterAutoCycle drives the full-machine auto sequence

The machine's operator-facing cycle is implemented as `FB_MasterAutoCycle`
(commit `9ba7a14`, with mode-forcing added in `8a39fae`, and simplified
robot interface added 2026-07-10). It coordinates 1..3 pairs of (SepSolN,
PushSolN) pistons in parallel with a single robot handshake signal.

**Robot interface (simplified 2026-07-10):** two discrete signals, both
level (not pulsed), per the Option 1 decision in
`docs/robot-integration-options.md`. See the OPEN ISSUE section above.

| Direction | ST_HmiRobot field | Wire to Dobot (from `..\167-01-Saad\global.lua`) | Semantic |
|---|---|---|---|
| Robot → PLC | `bStartAssembly` | robot DO 2 (`STAND_SEQ_DO`) | Rising edge triggers a cycle from IDLE |
| PLC → Robot | `bAssemblyRunning` | robot DI 1 (`STAND_SEQ_DI`) | TRUE in every non-IDLE state (including ERR); FALSE in IDLE |

The former `POS1/POS2/POS3` + `AUTO_STARTED/PUSH_DONE/PISTONS_ERROR` TCP
protocol is retired. `WAIT_POS2` is retired too — the Dobot's
`PerformStandSequence` moves the arm clear of the stand *before* raising
`STAND_SEQ_DO`, so no intermediate "robot moved away" wait is needed.

**Nine-state state machine** (`E_MasterAutoStep`; `WAIT_POS2` value still
declared in the enum but unused — safe to remove once the HMI is cleaned):

```
IDLE                    Wait for operator START OR stRobot.bStartAssembly rising
                        OR bSimStep_Idle. bAssemblyRunning drops LOW here.
SEP_EXTENDING           Drive SepCmdExtend[1..N]; wait AND of enabled SepIsExtended.
PUSH_EXTENDING          Drive PushCmdExtend[1..N]; wait AND of enabled PushIsExtended.
DWELL_PUSH              Hold both extended; wait tDwellPushMs (default 2000).
PUSH_RETRACTING         Drive PushCmdRetract[1..N]; wait AND of enabled PushIsRetracted.
PUSH_RETRACTED_DWELL    Wait tPushRetractedDwellMs (default 500).
SEP_RETRACTING          Drive SepCmdRetract[1..N]; wait AND of enabled SepIsRetracted.
SEP_RETRACTED_DWELL     Wait tSepRetractedDwellMs (default 500). Increment nCyclesCompleted.
                        → IDLE (or immediately re-arm bStart if Continuous).
ERR                     Latched. iErrorCode = step's fault code. bAssemblyRunning
                        stays HIGH so the robot's own polling times out and its
                        error handler fires. Reset on HMI RESET rising edge only.
```

**Error codes** (`ST_HmiMasterAuto.iErrorCode : INT`, 0 = OK):

| Code | Meaning                            |
|------|------------------------------------|
| 0    | OK                                 |
| 1    | SEP_EXTENDING timeout              |
| 3    | PUSH_EXTENDING timeout             |
| 4    | PUSH_RETRACTING timeout            |
| 5    | SEP_RETRACTING timeout             |
| 99   | Operator STOP while running        |

(Code 2 was the retired `WAIT_POS2` timeout.)

**Piston mode force ("Put all to Auto")** — optional, off by default. When
`stMasterAutoCfg.bForceAllAuto` is TRUE, MAIN forces any pair with index ≤
uiPairCount into Automatic while the master cycle is running so `bAutoCmd*`
reaches the coil. When FALSE (default), only pistons the operator already
put into Automatic participate; pistons in Manual mode are skipped. The
gate is `bAnyRunning AND bForceAllAuto`, so on IDLE/ERR the block never
touches the operator's mode choice regardless of the flag. HMI checkbox
lives next to Continuous on the AutoCycle page.

**Coexists** with the per-piston `fbSepSol{1..3}Auto` / `fbPushSol{1..3}Auto`
tiles via OR-merge on `bAutoCmd*` at each piston call site (`fbXxxAuto.bCmd*
OR fbMasterAutoCycle.bXxxCmd*[i]`). Bench-testing loops independently still
works — see `DECISION: per-piston auto tiles` below.

**Per-step simulate flags** on `ST_HmiMasterAuto.bSimStep_*` let a bench
operator advance any waiting step without physical sensors — rising-edge
triggered, FB auto-clears after consumption. The `AutoCycle` HMI page
renders them as a vertical 9-row table (`Row0_*` … `Row8_*` in
`UC_MasterAutoCycle.usercontrol`) — one row per state, background
highlights yellow when `auto::eStep` matches the row's enum value, red
for the ERR row. The `Sim bStartAssembly` checkbox at the top drives the
robot handshake input.

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
  bench cycling on pistons whose proximity switches aren't wired
  (SepSol2/3, PushSol2/3 today per the DI channel open issue below).

## DECISION: robot is the TCP server; bridge is the client

The robot comms are done via a **Python bridge** in `RobotBridge/` that
talks TCP/IP to the robot and ADS to the PLC. This sidesteps Beckhoff's
paid TF6310 TCP/IP supplement — see
`.claude/projects/…/memory/feedback_avoid_licensed_beckhoff_libs.md`
for the rationale.

**Robot side is the TCP server, bridge dials in.** Committed values in
`RobotBridge/config.yaml`:

```yaml
robot:
  role: "client"
  host: "192.168.201.1"
  port: 6001
```

The connection semantics follow the reference client at
`RobotBridge/Client_working_example/tcp client.py`:

- Persistent socket (one open TCP connection while up).
- 2-second socket timeout on connect/recv/send.
- `SO_KEEPALIVE` enabled so a half-open TCP (peer power loss, cable pulled)
  is eventually detected by the OS.
- Optional idle-probe: after `heartbeat_idle_seconds` with no data from
  the robot, the bridge sends `HEARTBEAT` bytes just to see whether the
  send raises. We do not require the robot to reply — this only catches
  a half-open connection faster than TCP KEEPALIVE would.
- On any exception, the top-level supervisor closes the socket, waits
  `reconnect.delay_seconds`, and re-dials.

## DECISION: HMI contract lives in any GVL with the `TcHmiSymbol.AddSymbol` pragma

Four GVLs expose symbols to the HMI today: `GVL_HMI`, `GVL_HmiPersistent`,
`GVL_Log`, `GVL_Robot`. Kept split by concern (piston state / persistent
config / diagnostics / robot bridge). The `{attribute 'TcHmiSymbol.AddSymbol'}`
pragma is the searchable marker — grep for it under `PLC1/GVLs/` and you
have the whole PLC↔HMI contract:

```
grep -l "TcHmiSymbol.AddSymbol" Flower_PLC_HMI/Flower_PLC_HMI/PLC1/GVLs/
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
IOmapTask cycle. MAIN no longer touches `GVL_IO` directly. Robot-handshake
wiring (`GVL_Robot.stRobot.bStartAssembly` from a DI, `bAssemblyRunning`
to a DO) is stubbed in as commented `TODO(#3)` lines inside the actions —
un-comment once channels are picked from the open-issue table.

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

`GVL_IO.dIn` / `GVL_IO.dOut` sized `ARRAY[1..16] OF BOOL`. All six
pistons and the robot handshake are wired; channels 14..16 (DI) and
8..16 (DO) are free for future use. The mapping lives in
`PRG_IoMap.TcPOU` (`ReadInputs` and `WriteOutputs` actions).

| Actuator / signal        | DI (Retract) | DI (Extend) | DO (Extend / robot) |
|--------------------------|--------------|-------------|---------------------|
| SepSol1                  | dIn[1]       | dIn[2]      | dOut[1]             |
| SepSol2                  | dIn[3]       | dIn[4]      | dOut[2]             |
| SepSol3                  | dIn[5]       | dIn[6]      | dOut[3]             |
| PushSol1                 | dIn[7]       | dIn[8]      | dOut[4]             |
| PushSol2                 | dIn[9]       | dIn[10]     | dOut[5]             |
| PushSol3                 | dIn[11]      | dIn[12]     | dOut[6]             |
| Robot → PLC `bStartAssembly` (STAND_SEQ_DO) | dIn[13] | — | — |
| PLC → Robot `bAssemblyRunning` (STAND_SEQ_DI) | — | — | dOut[7] |

Tag convention: `<Device>Sol<N>` = single Extend coil (SOL-Spring, spring
retracts). Retract sensors still exist on the DI side — the
retracted-position feedback is useful even without a retract coil.

To add a new actuator, extend `GVL_IO` (already sized 1..16), add its
GVL_App alias, wire it in `PRG_IoMap.ReadInputs` / `WriteOutputs`, then
finish the EtherCAT link in the System Manager.

## Out of scope (Future)

- **Remove the "Pair count" parameter** from `FB_MasterAutoCycle` and its
  HMI tile — the pair count is effectively fixed at 3 for this machine, so
  the runtime knob mostly adds noise.
- **Invert `bAssemblyRunning` polarity** → `bAssemblyNOTRunning`. Safer
  fail-open semantic: PLC writes TRUE when it is *safe* to move the robot,
  so a broken PLC / cable / loose wire reads as FALSE and the robot holds
  station.
- **Review persistent vars** — verify `stXxxAutoCfg` and `stMasterAutoCfg`
  actually survive a power-cycle. Needs a bench test (set value → hard
  power cycle → verify), not a code review.
- **Reconcile `RobotBridge/` protocol with the actual Dobot code.** Its
  `robot_bridge.py` assumes the robot pushes `POS1` / `POS2` / `POS3` on
  TCP:6001, but the SAAD 167-01 Dobot Lua only uses port 6001 for
  parameter tuning (`GET_SYNC`, `NAME:VALUE`, `HEARTBEAT`, `New_Bulb:1`);
  the operational handshake is discrete I/O (`STAND_SEQ_DO` /
  `STAND_SEQ_DI`). Options: retire the bridge (Option 1 outcome above),
  repurpose it for parameter tuning only, or ask the robot side to add
  position frames (unlikely — duplicates DIO). Confirm with the robot
  programmer before doing either.


## Playwright

- http://127.0.0.1:3003/liveview_64DA0B941E542F0480ED7063192BC500.html
- Put the screenshots to some temp folder