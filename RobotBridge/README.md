# Flower — Robot TCP/IP bridge

Middleware that translates between the industrial robot (TCP/IP, ASCII
`POS1\n` / `POS2\n` / `POS3\n` frames) and the TwinCAT PLC (ADS).

Runs as a long-lived Python process. No Beckhoff TF-supplement licenses
are involved — ADS is built into TwinCAT and free, and `pyads` is MIT.

## Data flow

```
   Robot ── TCP/IP ──▶  robot_bridge.py ── ADS ──▶  PLC (GVL_Robot.stRobot) ──▶  HMI "Robot" page
```

The PLC has no networking code. Everything the operator sees on the
Robot HMI page (`bAtPos1/2/3`, `eConnState`, `nPacketsRx`, `sLastMessage`)
is written into `GVL_Robot.stRobot` by this bridge.

## Install

Requires Python 3.9+.

```
pip install -r requirements.txt
```

On Linux, `pyads` needs the Beckhoff ADS client library. See the
[pyads docs](https://pyads.readthedocs.io/en/latest/documentation/setup.html)
— the shortest path is `sudo apt install libads-dev` on Debian/Ubuntu.
On Windows the DLL ships with TwinCAT itself.

## Configure

```
cp config.example.yaml config.yaml
# edit config.yaml
```

Key fields:

| Field                       | Meaning                                                                                             |
|-----------------------------|-----------------------------------------------------------------------------------------------------|
| `plc.ams_net_id`            | AMS Net ID of the TwinCAT runtime. `127.0.0.1.1.1` for local.                                       |
| `plc.ams_port`              | 851 for PLC1 (default).                                                                             |
| `plc.symbol_prefix`         | Root symbol path of the `ST_HmiRobot` instance. Keep as `GVL_Robot.stRobot` unless renamed in PLC.  |
| `robot.role`                | `"server"` (bridge listens, robot dials in) or `"client"` (bridge dials the robot).                 |
| `robot.host`                | Robot's IP; ignored when `role="server"`.                                                           |
| `robot.port`                | TCP port. Same value applies to both roles.                                                         |
| `robot.encoding`            | Character encoding of the robot's frames. Default `ascii`.                                          |
| `reconnect.delay_seconds`   | Backoff between reconnect attempts.                                                                 |

## Route setup (remote hosts only)

If the bridge and TwinCAT are on the same machine, skip this — the
local route is present out of the box (`ams_net_id = 127.0.0.1.1.1`).

If they're on different machines, add a route on the TwinCAT engineering
PC pointing at the bridge host's AMS Net ID (System Manager → Routes →
Add Route). Then update `plc.ams_net_id` in `config.yaml`.

## Run

```
python robot_bridge.py --config config.yaml
```

Or, on Windows:

```
start_bridge.bat
```

For unattended operation, wrap `start_bridge.bat` in a Windows Scheduled
Task set to "run whether user is logged on or not", or install it as a
service with [NSSM](https://nssm.cc/).

## Smoke test

1. Build + Activate the PLC so `GVL_Robot.stRobot` is visible in the
   ADS symbol table.
2. `python robot_bridge.py --config config.yaml` — logs should show
   `ADS opened to 127.0.0.1.1.1:851` and (server mode) `listening on :2000`.
3. On the HMI Robot page, `eConnState` should read `Connecting`.
4. In another shell, run the companion sim script:

   ```
   python sim_robot.py           # sends POS1, POS2, POS3, FOO with 1s gap
   python sim_robot.py POS1 POS3 # custom sequence
   ```

   Expect on the HMI:
   - `eConnState → Connected` as soon as the client attaches.
   - `POS1` → `bAtPos1` lights green. `nPacketsRx = 1`, `sLastMessage = "POS1"`.
   - `POS2` → POS1 clears, POS2 lights.
   - `POS3` → POS2 clears, POS3 lights.
   - `FOO` → no `bAtPos*` change; `sLastMessage = "FOO"`,
     counter still increments (unknown-frame path).

5. When `sim_robot.py` exits: bridge logs the disconnect,
   `eConnState → Disconnected`, then transitions back to `Connecting`
   within `reconnect.delay_seconds`.

Alternatives (if you don't want to use `sim_robot.py`):
`nc 127.0.0.1 2000` on Linux/WSL/Git Bash, or a plain PowerShell
`TcpClient` one-liner — see the docs' Operation → Smoke test tab.

## Files

| File                   | Role                                                             |
|------------------------|------------------------------------------------------------------|
| `robot_bridge.py`      | The bridge. Single file, no framework.                           |
| `sim_robot.py`         | TCP client that sends POS frames for smoke testing.              |
| `config.example.yaml`  | Template; committed to git.                                      |
| `config.yaml`          | Your real endpoints; **gitignored**.                             |
| `requirements.txt`     | `pyads` + `pyyaml`.                                              |
| `start_bridge.bat`     | Convenience Windows launcher.                                    |
