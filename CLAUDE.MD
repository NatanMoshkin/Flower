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
