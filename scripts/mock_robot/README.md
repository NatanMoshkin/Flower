# Mock robot server (`mock_robot.py`)

Stands in for the Dobot's Lua TCP server (`src2.lua`) so the panel's whole robot
handshake can be exercised without a robot. Runs on any PC with Python 3 — no
dependencies beyond the standard library.

## Why this exists

The PLC is the TCP **client**; the robot is the server. With no robot on the
network the panel sits in `Connecting` / `Error` forever and none of the
sequence, arming or logging behaviour can be tested. This gives you the server
side, plus a switch to decide when a bulb is requested.

It also documents the protocol by implementing it. The version of `src2.lua`
committed in the robot repo has **no `STATE`/`CMD` handling at all**, so it
cannot start a cycle — see [The ordering rule](#the-ordering-rule) for the exact
trap.

## The contract

This is what the real `src2.lua` must also implement. The robot acts on exactly
three values and needs no branch for anything else:

| PLC pushes | Mock replies | Meaning |
|---|---|---|
| `STATE:0` (IDLE) | `CMD:1` when it wants a bulb, else `CMD:0` | armed — start one cycle |
| `STATE:99` (ERR) | `CMD:2` | faulted — reset it; the PLC then homes itself and comes back as `STATE:0` |
| anything else, incl. `STATE:40` (`NOT_HOMED`) and `STATE:30` (`MANUAL`) | `CMD:0` | wait |

`NOT_HOMED = 40` deliberately needs no branch of its own: it lands in the final
"wait", which is exactly right — the panel is telling us it is not armed, and
only an operator can change that.

Legacy frames still work, so the vendor's `tcp client.py` is unaffected:

| PLC → | Reply |
|---|---|
| `GET_SYNC` | `SYNC:J_SPEED=..,L_SPEED=..,…` (all 11 tuning params) |
| `NAME:VALUE` | `OK: SET NAME`, and the value is stored |
| `New_Bulb:1` | `OK: SET New_Bulb` |
| `HEARTBEAT` | `1` |

## Running it

```
python scripts/mock_robot/mock_robot.py              # AUTO: request a bulb on every IDLE
python scripts/mock_robot/mock_robot.py --manual     # press Enter for one bulb
python scripts/mock_robot/mock_robot.py --no-bulbs   # never request; just watch states
```

- **AUTO** is what you want for walking the sequence — the machine produces back
  to back, so every state and every log entry appears without you touching
  anything.
- **`--manual`** is for stepping one bulb at a time while you watch the pistons.
- **`--no-bulbs`** proves the *negative* cases: that the panel does **not** move
  when it should not.

Listens on `0.0.0.0:6001`, one client at a time, exactly like the Lua server.
Tuning params persist while the process runs (they are Lua globals on the real
robot), so a reconnect does not reset them.

## Pointing the panel at it

The PLC dials `GVL_Robot.sRobotHost : nRobotPort`. The factory default is
`192.168.1.11:6001`, so either run this on the host holding that address, or type
the mock PC's address into the **Robot** page on the panel.

Two things about that field, both of which have bitten before:

- `sRobotHost` / `nRobotPort` are `VAR_GLOBAL PERSISTENT`. **Changing the literal
  in `GVL_Robot` does not retarget a panel that has already booted** — the stored
  value wins. Use the Robot page, or Reset Origin.
- Editing the IP on the Robot page tears down the live session and re-dials, so
  it takes effect immediately rather than waiting for the socket to drop.

## Reading the output

State pushes print on change, and always when a command is actually issued. The
PLC pushes `STATE` at 1 Hz forever, so echoing every keep-alive would bury the
interesting lines — the same suppression policy `FB_RobotTcpClient` uses for its
own DBG trace.

```
New Client Connected Successfully: 192.168.1.50:49812
[SYNC] sent: SYNC:J_SPEED=10,L_SPEED=10,REPEATS=2,...
[STATE] 40  NOT_HOMED
[STATE] 10  INIT_PUSH_RETRACTING
[STATE] 0   IDLE  -> CMD:1 start cycle
[STATE] 20  WAIT_PLATE
[STATE] 22  GRIP_RETRACTING
[STATE] 0   IDLE  -> CMD:1 start cycle
```

Correlate these against the panel **Logs** page. Tick **Debug** there and
`FB_RobotTcpClient` adds its own `TX` / `RX` frame trace, so you get both ends of
every exchange.

## The ordering rule

The `STATE:` test **must come before** the generic `NAME:VALUE` colon branch:

```python
if msg.startswith("STATE:"):        # <-- before
    return handle_state(...)
if ":" in msg:                      # <-- generic NAME:VALUE
    ...
```

`STATE:0` contains a colon. Fall through to the generic branch and it is treated
as a parameter write and answered `OK: SET STATE`, which the PLC discards — so
`nRobotCmd` never leaves 0 and **no cycle can ever start**, while the link looks
perfectly healthy: `Connected`, both packet counters climbing once a second. That
is precisely the failure that cost a commissioning session, and it is still the
state of the committed `src2.lua`.

## Two sockets at once

Observed on the bench 2026-07-29, and the reason this server is `select`-based
rather than a plain blocking `accept` / `recv` loop.

The panel had **two simultaneous ESTABLISHED connections** to port 6001:

```
LocalAddress LocalPort RemoteAddress RemotePort OwningProcess
192.168.1.10      6001 192.168.1.100      50807          2008
192.168.1.10      6001 192.168.1.100      50808          2008
```

The PLC opens its next socket *before* the previous one is gone. A one-client
server accepts the first and blocks reading it; the second is completed by the
kernel from the listen backlog — so it shows `ESTABLISHED` and **the PLC believes
it is connected** — but nothing ever reads it. Result: one
`New Client Connected` line, then silence, and a panel that never gets past
`Connecting` because its `GET_SYNC` is never answered.

Two defences now:

- `select` watches the **listening socket as well as** the client, so a new
  connection pre-empts the stale one immediately (`(a new connection arrived
  while one was open - dropping the stale one)`).
- a client that goes quiet for `CLIENT_IDLE_TIMEOUT` (5 s) is dropped. The PLC
  pushes `STATE` at 1 Hz, so silence that long means it is gone.

Related: `SO_REUSEADDR` is **not** set on Windows, where it lets a second
instance bind a port that is already listening. Both would appear to start and
connections would land on one of them arbitrarily — so you watch one terminal
while the panel talks to the other. `SO_EXCLUSIVEADDRUSE` makes the second
instance fail loudly instead.

## Two copies exist — keep this one canonical

There is a near-identical `dummy_server.py` in the robot repo
(`167_01_Saad_Flower/Robot/167-01-Saad/`), where it sits next to `src2.lua` as a
protocol reference for `tcp client.py`. Nothing keeps the two in step.

**Treat this copy as canonical for panel testing** — it lives with the PLC code
and the checklist that uses it. If you change the protocol, change it here first,
then decide whether the robot-repo copy is still worth keeping or should just
point at this file.

## Troubleshooting

| Symptom | Cause |
|---|---|
| Panel logs `ERR Connect failed … err 1` and retries every 3 s | Nothing listening. Mock not started, wrong IP on the Robot page, or a firewall blocking 6001. |
| `Connected`, counters climbing, but no cycle ever starts | The reply is not a `CMD:` frame. If Last Rx on the Robot page reads `OK: SET STATE`, the server is a version without STATE handling — see [the ordering rule](#the-ordering-rule). |
| One `New Client Connected` line, then **silence**, panel stuck on `Connecting` | The server was wedged on a dead socket. Fixed 2026-07-29 — but if you see it again, check for **more than one connection** from the panel: `Get-NetTCPConnection -LocalPort 6001`. See [Two sockets at once](#two-sockets-at-once). |
| Mock looks dead but the panel says `Connected` | A **second instance** is holding the port and got the connection. Now refused at startup with `Cannot listen on 0.0.0.0:6001`, but check every open terminal. |
| Mock prints `[STATE] 40 NOT_HOMED` forever | Correct and expected. The panel is in Auto but un-armed; press the green PB3 or the HMI START. |
| Mock prints `[STATE] 30 MANUAL` | The panel is in Manual. Nothing will run until it is switched to Automatic *and* armed. |
| Cycle starts once then never again | Should no longer happen (fixed 2026-07-28, `nRobotCmd` is consumed as a level and cleared). If it does, check MAIN clears `nRobotCmd`. |
| `[STATE] unparsable: …` | A malformed `STATE:` frame; the mock answers `CMD:0` and carries on. |

## Related

- `scripts/test_master_cycle_arming.py` — the arming state machine, in Python
- `scripts/test_cmd_parse.py` — `ParseCmd` fidelity (coalesced frames, sentinel)
- `scripts/test_param_shadow_logic.py` — the tuning-param write path + logging
- `docs/bench-checklist-arming.html` — the test run this mock is built for
- `CLAUDE.md` → **ARMING MODEL**, **ROBOT COMMS LOGGING**, **ROBOT CMD:1 DEADLOCK**
