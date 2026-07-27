# Flower — Operator's Manual

> Assembly stand for pin-based bulb-flower components. The machine coordinates
> eight pneumatic pistons and one Dobot robot arm. This manual covers panel
> navigation, startup, normal operation, and troubleshooting for shop-floor
> operators.
>
> **Applies to:** the CP6606 panel solution (`Panel_PLC_HMI/167_01_Saad_PLC/`)
> as of 2026-07-27. Engineering-side notes live in `CLAUDE.md`.

## 1. What the machine does

A cycle assembles one part on the stand:

1. The robot places a plate on the stand and moves clear.
2. Both plate sensors go TRUE, and the PLC clamps the plate with the two
   **Grip** pistons.
3. The PLC extends the three **Sep** pistons (pin separators).
4. The PLC extends the three **Push** pistons (pin pushers), holds them
   extended for a dwell, then retracts them.
5. The PLC retracts the Sep pistons, waits a dwell, then releases the Grip
   pistons.
6. The cycle counter increments and the machine returns to IDLE.

The robot starts each cycle by sending `CMD:1` over TCP; the PLC continuously
reports which step it is on so the robot knows when the stand is busy, idle, or
faulted. There is **no discrete-I/O handshake** with the robot any more — it is
all one TCP connection.

The cycle is implemented by `FB_MasterAutoCycle` and appears to the operator as
the current step on the Main screen.

## 2. Panel navigation

The operator interface is the **classic PLC visualization running on the CP6606
panel itself** — the panel is the whole control system. (There is also
`FlowerPyHmi`, an engineering-side web UI that runs on a laptop over ADS. It is
a commissioning tool, not part of the machine.)

The **Main** screen is the home screen. It embeds the auto-cycle controls
directly, shows the two plate sensors, and carries four navigation buttons:

| Page | Purpose |
|---|---|
| **Main** | Home. Auto cycle (step, error, START/STOP/RESET, config) + plate lamps. |
| **Pistons Manual** | Manual control for the six Sep/Push pistons. |
| **Gripper Manual** | Manual control for the two Grip pistons. |
| **Robot** | TCP link status, the 11 robot tuning parameters, and the robot's IP address. |
| **Log** | The 20 most recent PLC events. |

There is **no per-piston auto-cycle page in the panel solution** — the master
cycle owns all eight pistons in Automatic, and the operator jogs them in
Manual. (`FB_PistonAutoCycle` still exists in the PLC and is reachable from
FlowerPyHmi; it is not exposed on the panel.)

## 3. Startup procedure

1. Power on the electrical cabinet. Wait for the TwinCAT runtime to load.
2. On the **Main** screen, confirm:
   - Step reads `IDLE`.
   - Error code is `0` and the error text is empty.
   - The green status lamp is on steady (see §9).
3. Check the **Plate** `L` / `R` lamps on the right of the Main screen against
   the physical state of the stand.
4. Open **Pistons Manual** and **Gripper Manual**. Confirm each piston's
   position indicators match its physical state — everything should read
   retracted at power-on.
5. Open the **Robot** page and confirm the connection state reads `Connected`
   and the Rx/Tx counters are advancing.
6. Enable the robot on the Dobot pendant.

**Note on power-up mode.** `Automatic` survives a power cycle by design — the
machine comes back in the mode it was left in. It comes back at IDLE and still
needs a real start trigger, but be aware that a robot which is already running
can request a cycle immediately after power-up. Continuous cycling never
survives a restart (see §4).

## 4. Normal operation — running a cycle

Everything below is on the **Main** screen.

### Auto / Manual

`Auto Mode` is a **machine-wide** switch and the single source of truth for
every piston's mode — there is deliberately no per-piston mode selection.

- **Ticked (Automatic)** — the master cycle owns all eight pistons. Manual
  buttons and the panel jog push-buttons do nothing.
- **Unticked (Manual)** — the master cycle is held at IDLE and the operator
  drives pistons by hand.

### Configuration

Five timers, all in milliseconds, all editable on screen:

| Field | Default | Meaning |
|---|---|---|
| Dwell PUSH | 2000 | How long the push pistons stay extended. |
| Push retracted dwell | 500 | Pause after the push pistons retract. |
| Sep retracted dwell | 500 | Pause after the sep pistons retract. |
| Step timeout | 10000 | Longest any movement step may take before ERR. |
| Plate wait timeout | 10000 | Longest to wait for the plate in `WAIT_PLATE`. |

Two checkboxes:

- **No sensors (timed steps)** — the eight movement steps ignore position
  sensors and advance when `Step timeout` expires, so that field becomes a
  fixed step *duration* rather than a timeout. Error codes 1, 3, 4, 5, 6, 7, 8,
  10 and 11 cannot occur while this is on. `WAIT_PLATE` is **not** covered — it
  still needs both plate sensors.
- **Bypass plate sensors** — removes only the `WAIT_PLATE` **timeout error**,
  not the wait. With healthy sensors nothing changes. With unwired or faulty
  sensors, `Plate wait timeout` degrades into a fixed placement dwell and the
  cycle continues instead of raising error 9.

Both are bench-testing aids. **Neither belongs in a production run** — see §7.

> **Continuous cycling has been removed.** Every cycle is started by the
> operator or by the robot. The panel checkbox is gone and the PLC forces the
> flag off on every scan, so nothing can re-enable it — including FlowerPyHmi,
> whose Continuous checkboxes now visibly revert when ticked.

### Running

1. Press **START**. The step walks through:

   ```
   IDLE → INIT_PUSH_RETRACTING → INIT_SEP_RETRACTING → INIT_GRIP_RETRACTING
        → WAIT_PLATE → GRIP_EXTENDING → SEP_EXTENDING → PUSH_EXTENDING
        → DWELL_PUSH → PUSH_RETRACTING → PUSH_RETRACTED_DWELL
        → SEP_RETRACTING → SEP_RETRACTED_DWELL → GRIP_RETRACTING → IDLE
   ```

   The three `INIT_*` steps drive everything home first, so a piston left
   extended by an earlier manual move cannot collide with the arriving plate.
   They satisfy immediately when the pistons are already home.

2. The cycle counter increments at the end of `GRIP_RETRACTING`.
3. To stop:
   - **STOP** — stops the cycle. Latches error 99 if it was running.
   - **RESET** — clears the error and returns to IDLE.

The robot starts subsequent cycles itself with `CMD:1`, so the operator does
not press START on every cycle while the robot is active. The robot can also
clear a fault remotely with `CMD:2`.

### Bench mode without a robot

The per-step **simulate** flags let you advance any waiting step without
physical sensors. They are not on the panel's Main screen — use FlowerPyHmi, or
the panel push-buttons for jogging.

## 5. Manual mode — piston control

With `Auto Mode` unticked, open **Pistons Manual** (six Sep/Push pistons) or
**Gripper Manual** (two Grip pistons). Each piston tile has Extend / Retract
commands, momentary jog buttons, and position indicators.

**The HMI Extend/Retract selection latches** — the piston holds its commanded
position until you select the other direction. The HMI jog buttons latch too,
but Extend and Retract jog sit side by side, so there is always a way back.

## 6. Panel push-buttons

Three momentary push-buttons with built-in LEDs. What they do depends on the
machine-wide mode:

| Button | In Automatic | In Manual |
|---|---|---|
| **PB1** | Rising edge starts a cycle (same effect as the robot's `CMD:1`). | **Held** → both Grip pistons extend. **Released** → they retract. |
| **PB2** | Ignored. | **Held** → all three Sep pistons extend. **Released** → they retract. |
| **PB3** | Ignored. | **Held** → all three Push pistons extend. **Released** → they retract. |

Push-button jog is **momentary** — release and the piston goes home. This is
different from the HMI jog, which latches.

The LEDs in the push-buttons are **wiring diagnostics only** — each one simply
mirrors whether its own button is pressed. They do not indicate machine status.
For that, use the two status lamps in §9.

## 7. Sensorless and bypass modes — when not to use them

`No sensors (timed steps)` and `Bypass plate sensors` both trade feedback for
the ability to keep moving.

**Use them for:** bench cycling before sensors are wired, isolating whether a
fault is in the sensor or the actuator, and life-cycle testing.

**Do not use them in production.** Time-based operation cannot detect a stuck
piston, a missing plate, or a blocked actuator — the cycle will continue as
though every move succeeded. `Bypass plate sensors` deliberately keeps *waiting*
rather than skipping the plate gate, precisely so the grippers do not close on
nothing, but it still cannot tell you the plate never arrived.

**These flags survive a power cycle.** A flag left on at the bench will still
be on tomorrow. Check both before a production run.

## 8. Alarms and error recovery

Errors appear as an error code plus text on the Main screen, on the **Log**
page, and on the red status lamp. The robot also sees the fault, because the
PLC reports step 99 over TCP.

| Code | Meaning |
|---|---|
| 0 | OK |
| 1 | SEP_EXTENDING timeout |
| 3 | PUSH_EXTENDING timeout |
| 4 | PUSH_RETRACTING timeout |
| 5 | SEP_RETRACTING timeout |
| 6 | INIT_PUSH_RETRACTING timeout |
| 7 | INIT_SEP_RETRACTING timeout |
| 8 | INIT_GRIP_RETRACTING timeout |
| 9 | WAIT_PLATE timeout — plate not detected |
| 10 | GRIP_EXTENDING timeout |
| 11 | GRIP_RETRACTING timeout |
| 99 | Operator STOP while running |

(Code 2 belonged to a retired step and can no longer occur.)

**Recovery:**

1. Note the code and text.
2. Check the physical state — piston stuck? sensor loose? debris on the stand?
   plate missing or misplaced?
3. Fix the physical cause.
4. Press **RESET**. Step returns to IDLE and the error clears.
5. Press **START**, or let the robot request the next cycle.

## 9. Status lamps

Two lamps report machine state. Unlike the push-button LEDs, these are real
status indicators:

| Lamp | Behaviour |
|---|---|
| **RED** | On while the cycle is latched in ERR. |
| **GREEN** | Automatic + IDLE → steady. Automatic + cycling → blinking. Manual, or ERR → off. |

Green is off in ERR so the two lamps can never contradict each other, and off
in Manual because it means "the automatic cycle is live" — which is exactly
what Manual is not.

## 10. Robot page

| Item | Notes |
|---|---|
| Connection state | `Disconnected` / `Connecting` / `Connected`. On any socket error the PLC closes and re-dials after 3 s, forever. |
| Rx / Tx counters | Should both advance at least once a second — the PLC sends a keep-alive that often. |
| Last Rx / Last Tx | The most recent frame each way. First place to look when the link misbehaves. |
| State out / Robot cmd | What the panel is telling the robot, and the last command the robot sent. |
| **Get Sync** | Pulls all 11 tuning parameters from the robot. |
| **New Bulb** | Tells the robot to start a fresh bulb. |
| 11 tuning parameters | Editable. Each field is range-limited on screen, and the PLC clamps every value again on the way out. |
| Robot IP address | Editable. Takes effect immediately — the PLC tears down the live connection and re-dials the new address. |

The robot IP and port are **commissioning values and persist**. The TCP enable
flag deliberately does not: a link disabled for a bench session comes back
enabled after a restart, so the robot can never be left unreachable for no
visible reason.

Editing a tuning parameter pushes it to the robot automatically, one parameter
per round-trip. If the link is down when you edit, the value is overwritten by
the next reconnect's sync — so make parameter changes with the link up.

## 11. Log page

The 20 most recent PLC events, newest first: severity, time, message. Two
checkboxes control logging (`Enabled`, and `Debug` for the chattiest level),
plus a total-events counter.

**Two things to know about the panel log:**

- **It lives in RAM only.** Nothing is written to disk on the panel. Every entry
  is lost on power cycle, PLC reset, or download, and only the most recent 256
  events are kept internally (the page shows 20). If you need a permanent
  record, connect FlowerPyHmi — it drains the ring into rotating files on the
  laptop.
- **Timestamps are only as good as the panel clock.** If the panel's real-time
  clock is unset, the time column reads `--:--:--` rather than a plausible wrong
  time. Treat that as "fix the clock", not "the log is broken".

## 12. Emergency stop

Press the physical E-Stop on the cabinet at any time. This cuts power to the
pneumatic solenoids and the robot regardless of PLC or panel state. After
releasing:

1. Confirm the physical cause is cleared.
2. Reset the E-Stop button (twist to release).
3. Press **RESET** on the Main screen.
4. Verify every piston is safely retracted on the two manual pages.
5. Re-enable the robot on the Dobot pendant.
6. Resume with START.

## 13. Persistent configuration

The cycle timers, the two sensor-bypass flags, `Auto Mode`, and the robot's IP
address and port all survive a power cycle. They are written to the panel's
Compact Flash automatically, about **two seconds after you stop typing** — so
make an edit, pause, and it is saved. Each save is recorded on the Log page,
and a failed save is logged as an error rather than passing silently.

Two deliberate exceptions:

- **Continuous cycling is never restored** — it is forced off on every scan.
- **Nothing else is cleared**, which is why §7 warns that a bench flag left on
  survives a reboot.

To restore defaults, engineering can do a Cold Reset from TcXaeShell — that
wipes persistent memory and reboots the PLC.

## 14. Where to look when something's weird

| Symptom | First thing to check |
|---|---|
| Cycle stuck in an EXTENDING or RETRACTING step | Position sensor loose or blocked. Compare the piston's indicators with its physical state, then try a manual jog. |
| Error 9 immediately after START | Plate not present or a plate sensor has failed. Check the `L` / `R` lamps on the Main screen. |
| Cycle will not start at all | Is `Auto Mode` ticked? In Manual the master cycle is held at IDLE by design. |
| Robot cannot start a cycle | Robot page — is the state `Connected` and are the counters moving? Check the IP address field. |
| Robot ignores a parameter change | Was the link up when you edited it? A reconnect re-reads all 11 values from the robot. |
| Green lamp off in Automatic at IDLE | Check for a latched error — green is suppressed in ERR. |
| A push-button does nothing | PB2 and PB3 are Manual-only. PB1 starts a cycle in Automatic and jogs the grippers in Manual. |
| Panel log is empty after a restart | Expected — the log is RAM-only (§11). |
| Log timestamps read `--:--:--` | The panel's clock is unset. Ask engineering to set it. |
| A saved setting reverted | Did you power off within ~2 s of typing? Or was Continuous the setting — that one never persists, by design. |

For anything below this layer — TwinCAT errors, ADS symbol problems, TCP
framing — see `CLAUDE.md` and the engineering docs in `docs/`.
