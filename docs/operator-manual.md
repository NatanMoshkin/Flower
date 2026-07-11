# Flower — Operator's Manual

> Assembly stand for pin-based bulb-flower components. The machine coordinates
> six pneumatic pistons and one Dobot robot arm. This manual covers HMI
> navigation, startup, normal operation, and troubleshooting for shop-floor
> operators.

## 1. What the machine does

A cycle assembles one part on the stand:

1. The robot places a component on the stand and steps clear.
2. The robot raises `STAND_SEQ_DO`, signalling "start assembly".
3. The PLC drives three **Sep** pistons to extend (pin separators).
4. The PLC drives three **Push** pistons to extend (pin pushers), holds
   them extended for a short dwell, then retracts them.
5. The PLC retracts the Sep pistons, waits a final dwell, and drops
   `STAND_SEQ_DI` low ("assembler finished").
6. The robot removes the assembled part and starts the next cycle.

The whole cycle is coordinated by `FB_MasterAutoCycle` in the PLC and
appears to the operator as the yellow-highlighted state on the AutoCycle
page.

## 2. HMI navigation

The HMI runs on the Beckhoff panel (CP6606) and also on the engineering
PC via the web HMI. Left/right menu:

| Page              | Purpose |
|-------------------|---------|
| **Start Page**    | Per-piston auto-cycle tiles (six of them). Use these to bench-test a single piston in a loop without running the whole assembly sequence. |
| **Piston**        | Manual control panel for each of the six pistons (six tiles). Use for setup, jogging, and fault recovery. |
| **AutoCycle**     | Master assembly cycle (`FB_MasterAutoCycle`). This is the operator's primary page for a production run. |
| **Events**        | Alarm and log stream from the PLC. |
| **Settings**      | Persistent configuration (rare — most tunable values live on the AutoCycle page itself). |

The header strip on every page shows TwinCAT status, PLC state, the
logged-in user, and the current time.

## 3. Startup procedure

1. Power on the electrical cabinet. Wait ~15 s for the TwinCAT runtime
   to load — the header's PLC indicator should turn green.
2. Log in on the HMI as the operator user.
3. Open the **AutoCycle** page. Confirm:
   - Step banner reads `Idle` on a grey background.
   - Error banner is grey and empty.
   - `bAssemblyRunning (to robot)` indicator is unchecked (low).
4. Open the **Piston** page. Confirm every piston shows both position
   indicators are consistent with its physical state (retracted at
   power-on).
5. Enable the robot on the Dobot pendant.

The machine is now ready to run.

## 4. Normal operation — running an assembly cycle

**On the AutoCycle page:**

1. Set the cycle configuration if needed (only the first time or after a
   parameter change):
   - **Pair count** — how many piston pairs participate (1..3). Default 3.
   - **Dwell PUSH (ms)** — how long push pistons stay extended. Default 2000.
   - **Push retracted dwell (ms)** — pause after push retract. Default 500.
   - **Sep retracted dwell (ms)** — pause after sep retract. Default 500.
   - **Step timeout (ms)** — max time any single step may take before the
     cycle enters ERR. Default 10000.
   - **Continuous cycling** — if ticked, IDLE re-arms automatically and the
     cycle loops. Untick for single-cycle runs.
   - **Put all pistons to Auto on Start** — if ticked, MAIN forces every
     enabled piston into Automatic mode at the start of each cycle. If
     unticked (default), only pistons the operator explicitly put into
     Automatic participate; pistons left in Manual are skipped. Use with
     care — the checkbox is a convenience, not a safety feature.
2. Press **START**. The Step banner turns yellow and walks through the
   state table on the right side of the page:

   `IDLE → SEP_EXTENDING → PUSH_EXTENDING → DWELL_PUSH → PUSH_RETRACTING
    → PUSH_RETRACTED_DWELL → SEP_RETRACTING → SEP_RETRACTED_DWELL → IDLE`

3. The "Cycles" counter increments at the end of `SEP_RETRACTED_DWELL`.
4. To stop:
   - **STOP** — soft stop back to IDLE. Does not clear any error.
   - **RESET** — hard reset: forces IDLE and clears error + cycle counter.

The **robot** starts subsequent cycles by pulsing `STAND_SEQ_DO`; the
operator does not have to press START on every cycle when the robot is
active.

**Bench mode (no robot connected):** tick the `Sim bStartAssembly`
checkbox on the AutoCycle page — that simulates the robot raising its
handshake. If you also tick per-step advance checkboxes on the step
table (right side of the page), you can single-step the cycle without
waiting for physical sensors.

## 5. Manual mode — per-piston control (Piston page)

Each of the six piston tiles on the Piston page has:

- **Mode** (Manual / Automatic) — set to Manual for hand control.
- **Extend / Retract** manual command buttons.
- Position indicators showing the piston's current sensor state.

Use Manual mode for setup, physical alignment, or fault recovery. When
a piston is in Manual, `FB_MasterAutoCycle`'s command signals for that
piston are ignored (unless the "Put all pistons to Auto on Start"
checkbox is ticked on the AutoCycle page).

## 6. Per-piston auto tiles (Start Page)

The Start Page has six independent piston auto-cycle tiles (three Sep
across the top row, three Push across the bottom row). Each tile is a
mini-`FB_MasterAutoCycle` for a single piston: it loops one piston
between extended and retracted with configurable dwell times.

Fields per tile:

- **START / STOP / RESET / ACK** — same semantics as the AutoCycle page.
- **Continuous** — loop, otherwise single cycle then IDLE.
- **No sensors (timed)** — see §7 below.
- **Dwell EXT / RET (ms)** — hold time at each end.
- **Extend / Retract time (ms)** — with sensors: timeout guard. Without
  sensors: fixed move duration.

Use these tiles to bench-test a single piston, verify a new sensor's
polarity, or run a burn-in loop overnight on one actuator without
running the whole assembly.

Per-piston auto tiles and the master AutoCycle can run **simultaneously**
— the PLC OR-merges their extend/retract commands so both drive the same
piston, whichever asked first wins the scan.

## 7. Sensorless mode

For pistons whose proximity switches aren't wired (or are physically
disconnected), tick the **No sensors (timed)** checkbox on that piston's
Start Page tile. The auto cycle then:

- Ignores position sensor feedback entirely.
- Uses `Extend time (ms)` and `Retract time (ms)` as fixed move
  durations (not timeouts).
- Skips the "sensor never arrived" and "both sensors active" error
  paths.

**When to use it:**
- Bench cycling before sensors are physically wired.
- Diagnosing whether a fault is in the sensor vs the actuator.
- Life-cycle stress testing.

**When NOT to use it:** any production run. Time-based operation cannot
detect a stuck piston, missing part, or blocked actuator — the cycle
will happily continue thinking each move succeeded.

## 8. Alarms and error recovery

Errors show up in three places:

1. The red banner at the bottom of the AutoCycle page (or a per-piston
   tile). Text carries the human-readable failure reason.
2. The Events page — every state transition and error is logged with a
   timestamp and source name.
3. The `iErrorCode` field on the AutoCycle page:

| Code | Meaning                     |
|------|-----------------------------|
| 0    | OK                          |
| 1    | SEP_EXTENDING timeout       |
| 3    | PUSH_EXTENDING timeout      |
| 4    | PUSH_RETRACTING timeout     |
| 5    | SEP_RETRACTING timeout      |
| 99   | Operator STOP while running |

**Recovery:**

1. Note the error code and text.
2. Check the physical state — is a piston stuck? Is a sensor loose? Is
   there debris on the stand?
3. Fix the physical issue.
4. Press **RESET** on the affected page. The step banner returns to
   grey `Idle` and the error clears.
5. Press **START** to resume, or wait for the next robot handshake.

**Note on `bAssemblyRunning` during ERR:** the PLC keeps this signal
HIGH while the master cycle is in ERR, so the robot's own polling logic
times out and its own error handler fires — this is intentional so an
operator sees the fault on both machines.

## 9. Robot handshake — quick reference

Two discrete signals exchanged with the Dobot over I/O terminals:

| Direction   | PLC channel | Robot channel     | Meaning                                                                                                                          |
|-------------|-------------|-------------------|----------------------------------------------------------------------------------------------------------------------------------|
| Robot → PLC | `dIn[13]`   | `STAND_SEQ_DO` (robot DO 2) | Rising edge in IDLE = "start assembly"                                                                                     |
| PLC → Robot | `dOut[7]`   | `STAND_SEQ_DI` (robot DI 1) | HIGH while assembling (any non-IDLE state, including ERR). Robot polls for LOW to know the assembler finished.             |

There is no TCP link between robot and PLC in the current setup.

## 10. Emergency stop

Press the physical E-Stop button on the cabinet at any time. This cuts
power to the pneumatic solenoids and the robot, regardless of PLC or
HMI state. After releasing:

1. Confirm the physical cause is cleared.
2. Reset the E-Stop button (twist to release).
3. On the HMI, press **RESET** on the AutoCycle page (and on any piston
   tile that shows an error).
4. Verify all pistons are in a safe retracted position on the Piston
   page.
5. Re-enable the robot on the Dobot pendant.
6. Resume via START.

## 11. Persistent configuration

All values marked "PERSISTENT" in the PLC (cycle timers, pair count,
continuous flag, per-piston auto config, `bNoSensors` flag) survive
power cycles. They do NOT reset on Activate Configuration unless the
struct itself changes shape.

To restore defaults, use Cold Reset from TcXaeShell on the engineering
PC — this wipes persistent memory and reboots the PLC.

## 12. Where to look when something's weird

| Symptom                                              | First thing to check                                                                     |
|------------------------------------------------------|------------------------------------------------------------------------------------------|
| Cycle stuck in EXTENDING or RETRACTING               | Position sensor loose or blocked. Check the Piston page indicators; try Manual jog.      |
| Cycle immediately errors on START                    | A piston is in Manual and its "Put all pistons to Auto" checkbox is off.                 |
| No response to robot's handshake                     | Check `STAND_SEQ_DO` wiring to `dIn[13]`. Simulate on the HMI to isolate.                |
| Persistent values reset unexpectedly                 | Did someone just do a Cold Reset in TcXaeShell? Or did a struct field get added/removed? |
| HMI symbol errors (E_SCHEMA_UNKNOWN_DEFINITION, etc) | Rebuild PLC + Activate Configuration + rebuild HMI. Talk to engineering.                 |

For anything below this troubleshooting layer — TwinCAT errors, comms
faults, HMI framework issues — see the engineering-side docs in
`CLAUDE.md` and `docs/robot-integration-options.md`.
