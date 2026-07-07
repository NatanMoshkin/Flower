# Flower — project TODO / open issues

## TODO:

 - create Docs web style, similar to C:\Users\Natan.Moshkin\source\repos\BS\BS_HMI_PLC_DB and the script that will run the http://127.0.0.1:8765/docs/index.html (or different port as needed)

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
