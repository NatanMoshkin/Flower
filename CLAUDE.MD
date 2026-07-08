# Flower — project TODO / open issues

## TODO:


## OPEN ISSUE: robot TCP/IP role (server vs client)

The robot comms are done via a **Python bridge** in `RobotBridge/` that
talks TCP/IP to the robot and ADS to the PLC. This sidesteps Beckhoff's
paid TF6310 TCP/IP supplement — see
`.claude/projects/…/memory/feedback_avoid_licensed_beckhoff_libs.md`
for the rationale.

The choice of whether the **PLC-side bridge is the TCP server** (robot
dials in) or the **TCP client** (bridge dials the robot) is deferred
until commissioning. It's a one-line flip in `RobotBridge/config.yaml`:

```yaml
robot:
  role: "server"   # or "client"
  host: "192.168.1.50"   # ignored when role=server
  port: 2000
```

Default committed value: `server`, port 2000, placeholder IP. Update at
integration time.

## OPEN ISSUE: PLC↔HMI contract — HMI symbols scattered across multiple GVLs

The HMI reads/writes symbols from **four** GVLs today, all exposed via the
`{attribute 'TcHmiSymbol.AddSymbol'}` pragma and all landing in the
`SYMBOLS` map of `Server/TcHmiSrv/TcHmiSrv.Config.default.json`:

| GVL                  | Contents                                                                 | Persistent |
|----------------------|--------------------------------------------------------------------------|------------|
| `GVL_HMI`            | pistons `stSepSol1..3` + `stPushSol1..3`; auto runtime `stSepSol1Auto`   | no         |
| `GVL_HmiPersistent`  | auto config `stSepSol1AutoCfg`                                           | **yes**    |
| `GVL_Log`            | ring buffer `aLog[]`, `nWriteIdx`, `bDebugMode`                          | no         |
| `GVL_Robot`          | robot bridge state `stRobot` (written from Python over ADS)              | no         |

**Question**: is this the intended shape of the PLC↔HMI contract, or should
every HMI-facing symbol live in `GVL_HMI` so the contract surface is grep-able
from one file?

**Options to weigh next time we add an HMI-facing symbol:**

1. **Consolidate into `GVL_HMI`** — single source of truth. Requires multiple
   `VAR_GLOBAL` / `VAR_GLOBAL PERSISTENT` blocks in the same file (TwinCAT
   allows this) and mixes concerns (piston control ↔ diagnostics ↔ config ↔
   robot state). File gets bulky but the answer to "what does the HMI see?"
   is one file open away.

2. **Keep split by concern (current)** — cleaner separation of roles, but
   no single grep answers the contract question. Someone new to the project
   has to know all four GVL names.

3. **Rename convention** — call them all `GVL_HmiXXX` (`GVL_HmiLog`,
   `GVL_HmiRobot`, etc.) so `grep -l TcHmiSymbol.AddSymbol GVLs/GVL_Hmi*`
   gives you the whole contract. Keeps split-by-concern; adds a naming rule.

4. **Wrapper struct** — one `ST_HmiRoot` with sub-structs for each area; a
   single `stHmi : ST_HmiRoot` in `GVL_HMI`. Elegant but big refactor and
   the HMI UserControls would rebind through longer paths
   (`%s%ADS.PLC1.GVL_HMI.stHmi.pistons.stSepSol1%/s%`).

**Recommendation (personal, subject to revision):** option **3** — rename
`GVL_Log` → `GVL_HmiLog`, `GVL_Robot` → `GVL_HmiRobot`, keep
`GVL_HmiPersistent` as-is. Documents the contract via a shared prefix
without merging concerns. `GVL_App`, `GVL_IO`, `GVL_HmiPersistent` etc.
already read cleanly by prefix.

**When to revisit:** before adding a fifth HMI-facing GVL, or as part of a
future refactor if grepping the contract becomes painful.

## OPEN ISSUE: physical IO channel assignment for SepSol2/3 + PushSol2/3

`GVL_IO.dIn/dOut` now sized `ARRAY[1..16] OF BOOL`. The System Manager
EtherCAT links for slots 1..8 must be re-verified after the array grew;
slots 9..16 are unassigned.

Software already wired (FBs run, HMI reactive), waiting on channel numbers:

| Actuator  | DI (Retract) | DI (Extend) | DO (Retract) | DO (Extend) |
|-----------|--------------|-------------|--------------|-------------|
| SepSol1   | dIn[1]       | dIn[2]      | dOut[1]      | dOut[2]     |
| SepSol2   | **TBD**      | **TBD**     | **TBD**      | **TBD**     |
| SepSol3   | **TBD**      | **TBD**     | **TBD**      | **TBD**     |
| PushSol1  | dIn[7]       | dIn[8]      | dOut[7]      | dOut[8]     |
| PushSol2  | **TBD**      | **TBD**     | **TBD**      | **TBD**     |
| PushSol3  | **TBD**      | **TBD**     | **TBD**      | **TBD**     |

The four unassigned pistons currently run soft-only: HMI operator can
drive them and see UI feedback, but the FB outputs never reach hardware
(GVL_App aliases stay in software; the copies in MAIN's READ INPUTS /
WRITE OUTPUTS bookends are commented out with `TODO` markers).

When channels are decided, fill in `GVL_IO.dIn[??]` / `dOut[??]` in
`Flower_PLC_HMI/PLC1/POUs/MAIN.TcPOU` — the ten commented `// GVL_App…`
lines are placeholders.

Tag convention: `<Device>Sol<N><slot>` where slot 1 = RETRACT, slot 2 = EXTEND.
