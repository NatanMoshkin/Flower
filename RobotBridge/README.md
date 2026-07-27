# Flower — RobotBridge (RETIRED, kept as protocol reference)

> **This directory is not part of the machine.** Nothing here runs in
> production, and most of it can no longer run at all. It is kept for two
> reasons only: the vendor's reference client documents the robot's wire
> protocol and parameter ranges, and the git history explains why the
> architecture changed.
>
> **Do not plan from this directory.** The current design is in `CLAUDE.md`
> (see *DECISION: 167_01 panel solution — TCP-only robot comms*).

## Why it was retired (2026-07-26)

RobotBridge existed to keep TCP/IP out of the PLC. The reasoning was that
Beckhoff's TF6310 TCP/IP supplement is a paid licence, so a single-file Python
process would own the socket and translate each direction into ADS reads and
writes. That premise no longer holds:

1. **TF6310 is installed and running on the CP6606.** It is the documented
   exception to the avoid-paid-libraries rule, so the PLC can open its own
   socket. `FB_RobotTcpClient` (native ST, `Tc2_TcpIp`) now dials the robot at
   `GVL_Robot.sRobotHost:nRobotPort` directly.
2. **The bridge could never have run on the target anyway.** The panel is a
   CP6606 running Windows Embedded Compact 7 on ARM, which has no supported
   CPython, and therefore no `pyads`. The bridge only ever ran on a laptop.
3. **The protocol it implemented was never the robot's protocol.** The bridge
   parses newline-terminated `POS1` / `POS2` / `POS3` frames. The real Dobot
   emits nothing of the kind — there is no `POS` emission anywhere in the robot
   source. The frames it sent back (`AUTO_STARTED`, `PUSH_DONE`,
   `PISTONS_ERROR`, `HEARTBEAT`) are equally fictional.

The engineering-side UI is now **FlowerPyHmi** (separate repo, talks ADS to the
panel), which absorbed the only two jobs of the bridge that were real: draining
the PLC log ring, and simulating the robot for bench tests.

## What the machine actually does now

```
CP6606 panel ── TCP (Tc2_TcpIp) ──▶ Dobot robot server :6001
   FB_RobotTcpClient                (raw ASCII, no newline framing)
```

| PLC → robot | Robot → PLC | Purpose |
|---|---|---|
| `GET_SYNC` | `SYNC:NAME=VALUE,...` | Pull all 11 tuning parameters |
| `NAME:VALUE` | `OK: SET NAME` | Set one tuning parameter |
| `New_Bulb:1` | `OK: SET New_Bulb` | Start a fresh bulb |
| `STATE:<n>` | `CMD:<m>` | Push machine step, receive command |

`STATE:<n>` carries the master-cycle step (or `30` for MANUAL) and doubles as
the keep-alive. `CMD:<m>` is `0` = none, `1` = start cycle, `2` = reset error.

## What is still in use

Two files, and **only as documentation**. Neither is executed by anything.

| File | Why it is kept |
|---|---|
| `Client_working_example/tcp client.py` | The **vendor's own** PyQt5 GUI for the robot. It is the authoritative source for the 11 parameter names, **the order they appear in a `SYNC` reply**, and **their valid ranges** — it clamps to them, which is where the range table in `CLAUDE.md` comes from. `FB_RobotTcpClient`'s `ParamValue` / `ParamName` index mapping must match this file's order. A byte-identical copy lives in the robot repo at `Robot/167-01-Saad/`. |
| `Client_working_example/dummy_server.py` | Emulates the Dobot's own Lua server (`src2.lua`) for `GET_SYNC` and `NAME:VALUE`. Useful as the closest available statement of what the robot end actually does. |

Note what the reference client does **not** do: it has no range enforcement on
the PLC side, no `STATE`/`CMD` frames, and it clamps only in its own UI. That is
why `FB_RobotTcpClient` re-clamps every parameter on the way out — the vendor
GUI's limits protect the vendor GUI and nothing else.

**For actual bench testing, use FlowerPyHmi's simulator instead**
(`FlowerPyHmi/tools/dummy_server_tcp.py`). It handles the full current protocol
including the `STATE` / `CMD` frames that `dummy_server.py` predates.

## What is retired

Everything else. Two of these would now **fail at runtime**, because they write
`ST_HmiRobot` fields that were deleted from the PLC on 2026-07-26
(`bAtPos1/2/3`, `bTx*`, `bRxResetError`). The struct today holds only
`eConnState`, `sConnStateText`, `nPacketsRx`, `nPacketsTx`, `sLastMessage`,
`sLastTxMessage`.

| File | Status | Superseded by |
|---|---|---|
| `robot_bridge.py` | **Dead** — writes deleted PLC fields; parses `POS` frames the robot never sends. | `FB_RobotTcpClient` in the PLC |
| `bridge_gui.py` | **Dead** — polls deleted PLC fields; drives the bridge subprocess. | FlowerPyHmi's Robot page |
| `sim_robot.py` | Obsolete — sends `POS` frames to a bridge that no longer exists. | `FlowerPyHmi/tools/dummy_server_tcp.py` |
| `sim_robot_server.py` | Obsolete — plays the robot server, expecting the retired `AUTO_STARTED` / `PUSH_DONE` / `PISTONS_ERROR` / `HEARTBEAT` frames. | `FlowerPyHmi/tools/dummy_server_tcp.py` |
| `log_pump.py` | Obsolete — drained `GVL_Log` into the CSV logger. | `FlowerPyHmi/flower_py_hmi/plc_log.py` |
| `csv_logger.py` | Obsolete — daily CSV `logging.Handler`. | `FlowerPyHmi/flower_py_hmi/logging_setup.py` (rotating files) |
| `retention.py` | Obsolete — age/size caps on `logs/`. | `RotatingFileHandler` size + backup count |
| `config.yaml`, `config.example.yaml` | Obsolete — endpoints and ADS route for the dead bridge. Robot endpoint now lives in `GVL_Robot` (persistent, editable on the panel's Robot page). | `GVL_Robot.sRobotHost` / `.nRobotPort` |
| `start_bridge.bat`, `start_gui.bat` | Obsolete launchers. | — |
| `logs/*.csv` | Old output from bridge runs in July 2026. | — |
| `requirements.txt` | Obsolete — `pyads` + `pyyaml` for the bridge. | FlowerPyHmi's own `pyproject.toml` |

### One live loose end this leaves in the PLC

`GVL_Log.stBridgeCfg` (`ST_LogBridgeCfg`: log dir, level, retention days/MB,
poll ms) exists **solely** so `log_pump.py` could publish its configuration for
an HMI to display. With the pump retired, nothing writes it — the struct reads
as empty strings and zeros, and FlowerPyHmi's Logs page renders a blank "Log
bridge config" block because of it. Removing `stBridgeCfg` from `GVL_Log`,
`ST_LogBridgeCfg.TcDUT`, and the FlowerPyHmi Logs page is a tracked follow-up.

## Can this directory be deleted?

Not yet, and not entirely. `Client_working_example/` is the only copy of the
vendor protocol reference inside this repo, and `CLAUDE.md` cites it by file and
line for the parameter range table. The rest could go — it is recoverable from
git history — but it costs nothing to keep and it explains the four options that
`docs/robot-integration-options.md` weighed before the TCP-only decision landed.

If it is ever pruned, keep `Client_working_example/` and this README.
