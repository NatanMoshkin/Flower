# Flower — project TODO / open issues

## TODO:

 * (empty — auto-sequence TODO landed as FB_MasterAutoCycle; see DECISION below)

## OPEN ISSUE: robot integration architecture (blocking — decide before shipping)

The current design (`RobotBridge/` Python + pyads) cannot run on the CP6606
because Windows Embedded Compact 7 on ARM has no supported CPython + pyads.
Discovered 2026-07-10. Four options on the table; details, tradeoffs, and
cost/effort estimates in `docs/robot-integration-options.md`.

Summary of the options:

| # | Option | Blocks / gating question |
|---|--------|--------------------------|
| 1 | Discrete I/O between robot and PLC (skip TCP entirely) | Does the robot expose DO/DI channels? Simplest and best if yes. |
| 2 | Replace CP6606 with an x86 Beckhoff (CX5340 + panel, or CP2xxx) | Capital cost, downtime, license transfer. |
| 3 | Add a companion box (RPi 4 Linux or industrial NUC) hosting `RobotBridge/` | Adds one production-critical device; violates single-box principle. |
| 4 | Serial (RS-232 / RS-485) between robot and PLC via EL6001 / EL6021, using free Tc2_SerialCom | Does the robot expose a serial port? Same "no middleware" property as Option 1 with richer message payloads. |
| — | Rewrite bridge in C#/.NET CF 3.5 for CE 7 (rejected: dead tooling) | — |

Note: `FlowerPyHmi/` is engineering-side (runs on any developer laptop) —
it is **not** part of this decision and stays on the engineering PC
regardless of which option wins. Only `RobotBridge/` is at stake.

**Next step:** verify robot HW capabilities for discrete I/O (unlocks
Option 1) and serial port (unlocks Option 4). Those two facts eliminate
most of the option space at once.

## DECISION: FB_MasterAutoCycle drives the full-machine auto sequence

The machine's operator-facing cycle is implemented as `FB_MasterAutoCycle`
(commit `9ba7a14`, with mode-forcing added in `8a39fae`). It coordinates
1..3 pairs of (SepSolN, PushSolN) pistons in parallel with the robot's
Pos1/Pos2 signals.

**Ten-state state machine** (`E_MasterAutoStep`):

```
IDLE                    Wait for operator START OR stRobot.bAtPos1 rising OR
                        bSimStep_Idle. On trigger: emit AUTO_STARTED to robot.
SEP_EXTENDING           Drive SepCmdExtend[1..N]; wait AND of enabled SepIsExtended.
WAIT_POS2               Wait for stRobot.bAtPos2 rising.
PUSH_EXTENDING          Drive PushCmdExtend[1..N]; wait AND of enabled PushIsExtended.
DWELL_PUSH              Hold both extended; wait tDwellPushMs (default 2000).
PUSH_RETRACTING         Drive PushCmdRetract[1..N]; wait AND of enabled PushIsRetracted.
                        Emit PUSH_DONE to robot on sensor-reached.
PUSH_RETRACTED_DWELL    Wait tPushRetractedDwellMs (default 500).
SEP_RETRACTING          Drive SepCmdRetract[1..N]; wait AND of enabled SepIsRetracted.
SEP_RETRACTED_DWELL     Wait tSepRetractedDwellMs (default 500). Increment nCyclesCompleted.
                        → IDLE (or immediately re-arm bStart if Continuous).
ERR                     Latched. Emit PISTONS_ERROR. iErrorCode = step's fault code.
                        Reset on HMI RESET rising edge OR stRobot.bRxResetError rising edge.
```

**Error codes** (`ST_HmiMasterAuto.iErrorCode : INT`, 0 = OK):

| Code | Meaning                            |
|------|------------------------------------|
| 0    | OK                                 |
| 1    | SEP_EXTENDING timeout              |
| 2    | WAIT_POS2 timeout                  |
| 3    | PUSH_EXTENDING timeout             |
| 4    | PUSH_RETRACTING timeout            |
| 5    | SEP_RETRACTING timeout             |
| 99   | Operator STOP while running        |

**Piston mode is forced to Automatic** on any pair with index ≤ uiPairCount
while the master is in any non-IDLE, non-ERR state (MAIN.TcPOU block right
after the `fbMasterAutoCycle()` call, gated on `bAnyRunning`). Without this
the piston FB ignores `bAutoCmd*` when in Manual mode. On IDLE/ERR the block
does nothing so operator's manual choice is preserved.

**Coexists** with the per-piston `fbSepSol1Auto` / `fbPushSol1Auto` tiles
via OR-merge on `bAutoCmd*` at each piston call site. Bench-testing loops
independently still works.

**Per-step simulate flags** on `ST_HmiMasterAuto.bSimStep_*` let a bench
operator advance any waiting step without physical sensors — rising-edge
triggered, FB auto-clears after consumption. The `AutoCycle` HMI page
exposes all 9 sim checkboxes plus `Sim bAtPos1` / `Sim bAtPos2` for
sensorless testing.

**Bidirectional protocol** with the robot (see the RobotBridge DECISION
below). Outbound: `AUTO_STARTED`, `PUSH_DONE`, `PISTONS_ERROR`. Inbound:
`RESET_ERROR`. Frame tokens are commissioning-tunable (constants live in
`RobotBridge/robot_bridge.py`'s `PlcRobotSymbol.TX_FRAMES`).

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