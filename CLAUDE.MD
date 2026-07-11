# Flower — project TODO / open issues

## TODO:

**IO mapping** (see DECISION section below for reference architectures)
- Extract MAIN's READ INPUTS / WRITE OUTPUTS blocks into a dedicated
  `PRG_IoMap` PROGRAM added to the PLC task chain. Keep `GVL_IO` and
  `GVL_App` as-is (Level 1 adoption).
- Bundle #3 into the same edit: wire `GVL_Robot.stRobot.bStartAssembly ←
  GVL_IO.dIn[??]` and `GVL_Robot.stRobot.bAssemblyRunning → GVL_IO.dOut[??]`
  as `TODO channel TBD` placeholders. Channels come from the "physical DI
  channel assignment" open issue table.

## Out of scope (Future)

 - Remove the "Pair count" parameter from FB_MasterAutoCycle and HMI
 - bAssemblyRunning change to bAssemblyNOTRunning - safer to write TRUE when It's ok to mave the robot
 - **Review Persistent vars** — saving correctly? Needs bench test (write value → power-cycle → verify), not code review.

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

## OPEN ISSUE: RobotBridge protocol mismatch with the actual Dobot code

`RobotBridge/robot_bridge.py` assumes the robot pushes `POS1` / `POS2` /
`POS3` frames on TCP:6001. Inspection of the SAAD 167-01 Dobot Lua code
on 2026-07-10 shows that:

- The Dobot's TCP server on port 6001 is used only for **parameter tuning**
  (`GET_SYNC`, `NAME:VALUE`, `HEARTBEAT`, `New_Bulb:1`). No position frames
  are emitted.
- The robot ↔ PLC operational handshake is designed to run over **discrete
  I/O** (`STAND_SEQ_DO` and `STAND_SEQ_DI`), not TCP.

So `RobotBridge/`'s current protocol is orphaned. Reconcile with the robot
programmer: either retire the bridge (Option 1 outcome), repurpose it for
parameter tuning only, or ask the robot side to add position frames
(unlikely — duplicates DIO).

**Next step:** confirm with the robot programmer that Option 1 wiring
(`STAND_SEQ_DO`→PLC DI, PLC DO→`STAND_SEQ_DI`) is the intended integration.
If yes, proceed with Option 1 wiring plan and address the `RobotBridge/`
protocol mismatch as part of that work.

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

**Coexists** with the per-piston `fbSepSol1Auto` / `fbPushSol1Auto` tiles
via OR-merge on `bAutoCmd*` at each piston call site. Bench-testing loops
independently still works.

**Per-step simulate flags** on `ST_HmiMasterAuto.bSimStep_*` let a bench
operator advance any waiting step without physical sensors — rising-edge
triggered, FB auto-clears after consumption. The `AutoCycle` HMI page
today still exposes a `bSimStep_WaitPos2` checkbox and `Sim bAtPos1` /
`Sim bAtPos2` for the old interface — those are now dead in code and
should be swapped for a single `Sim bStartAssembly` binding in a follow-up
HMI edit.

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

**Current state (Level 0):** MAIN.TcPOU's implementation body contains
inline READ INPUTS / WRITE OUTPUTS blocks that copy between `GVL_IO.dIn[]`
(raw `AT %I*` BOOL array) and named `GVL_App.bSensor*` aliases, and vice
versa on the way out. Ergonomically OK for < 20 channels but doesn't scale
and doesn't separate concerns.

**Target (Level 1, tracked in TODO above):** Extract the same ST body into
a dedicated `PRG_IoMap` PROGRAM added to the PLC task chain (before/after
MAIN, depending on split). Keep `GVL_IO` raw arrays and `GVL_App` aliases.
Small, safe refactor — pure mechanical move.

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

## OPEN ISSUE: physical DI channel assignment for SepSol2/3 + PushSol2/3

`GVL_IO.dIn/dOut` sized `ARRAY[1..16] OF BOOL`. The System Manager
EtherCAT links for slots 1..8 must be re-verified after the array grew;
slots 9..16 are unassigned.

**DO is fully assigned** — the SOL-Spring migration packed all six Extend
coils into `dOut[1..6]`. **DI remains partial** — only SepSol1 and
PushSol1 have their proximity switches wired:

| Actuator  | DI (Retract) | DI (Extend) | DO (Extend) |
|-----------|--------------|-------------|-------------|
| SepSol1   | dIn[1]       | dIn[2]      | dOut[1]     |
| SepSol2   | **TBD**      | **TBD**     | dOut[2]     |
| SepSol3   | **TBD**      | **TBD**     | dOut[3]     |
| PushSol1  | dIn[7]       | dIn[8]      | dOut[4]     |
| PushSol2  | **TBD**      | **TBD**     | dOut[5]     |
| PushSol3  | **TBD**      | **TBD**     | dOut[6]     |

`dOut[7]` and `dOut[8]` were freed by the migration (previously PushSol1's
two coils) and are available for reuse.

The four unassigned DI pairs mean those actuators drive their coil in
software and on the HMI, but the "Extended" and "Retracted" position
indicators only light up via the operator's Simulate checkboxes until real
sensors are wired.

When DI channels are decided, fill in `GVL_IO.dIn[??]` in
`Flower_PLC_HMI/PLC1/POUs/MAIN.TcPOU` — the eight commented `// GVL_App…`
lines in the READ INPUTS block are placeholders.

Tag convention: `<Device>Sol<N>` = single Extend coil (SOL-Spring, spring
retracts). Retract sensors still exist on the DI side because the
retracted-position feedback is useful even without a retract coil.

## Playwright

- http://127.0.0.1:3003/liveview_64DA0B941E542F0480ED7063192BC500.html
- Put the screenshots to some temp folder