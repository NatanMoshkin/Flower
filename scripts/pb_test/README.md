# Panel push-button test procedure

Exercises every documented behaviour of the three panel push buttons and their
LEDs against a **live PLC** over ADS, and writes an HTML report.

```
python scripts/pb_test/pb_test_procedure.py                    # local runtime
python scripts/pb_test/pb_test_procedure.py --net 5.79.93.36.1.1   # a panel
python scripts/pb_test/pb_test_procedure.py --no-html           # JSON only
```

Outputs `docs/pb-test-report.html` and `scripts/pb_test/last_run.json`.
Exit code 0 = all checks passed, 1 = at least one failed, 2 = aborted.

## Do not point this at the production machine

It energises solenoid coils and drives the master auto cycle through a real
fault. Run it on the local runtime, or on a panel with **the air disconnected**.
It requires the PLC to be in RUN and refuses to start otherwise.

It is safe to interrupt: everything it writes is snapshotted first and restored
on the way out, including a 3.5 s wait for `FB_PersistentAutoSave` to flush the
persistent fields it touched (`bAutoMode`, `tPlateWaitTimeoutMs`).

## How a press is simulated

`PRG_IoMap.ReadInputs` runs on the 5 ms `IOmapTask` and copies
`GVL_IO.dIn -> GVL_App` every cycle, so **writing `GVL_App.bPb3` does nothing**
— it is overwritten before `MAIN` ever sees it. The procedure writes the raw
channels `GVL_IO.dIn[13..15]` instead, which works because the EtherCAT device
is `Disabled` in the local bench `.tsproj`, so nothing else drives that memory.

Piston position is simulated the same way (`park_all_home()` asserts every
retracted sensor), which is more faithful than setting `bNoSensors` — the real
sensor path is exercised, just with synthetic sensors. Note this only ever
asserts the *retracted* side, which is why a forward-running cycle stalls; see
**The full-cycle companion** below.

## It normalises the machine at entry

The procedure used to assume it started from a clean machine. A previous run that
ended in `ERR` then made group C fail for a reason unrelated to group C: `ERR` is
excluded from the Manual re-park, so "Manual → Auto parks in `NOT_HOMED`" could
not hold. It now clears any latched fault, disarms, and reports what it
normalised from — and its teardown RESETs before STOPping, because STOP is
excluded from `ERR` by design.

## What it checks — 57 checks in seven groups

| Group | Covers |
|---|---|
| **A** | LED1/LED2/LED3 as press mirrors in Manual |
| **B** | The three Manual jogs: PB1 grip, PB2 Sep, PB3 Push — held extends, released retracts, and the other six coils stay put |
| **C** | Auto + `NOT_HOMED`: PB3's LED blinks the arm prompt, PB1/PB2 are ignored, PB3 = operator START and homes |
| **D** | Auto + `IDLE`: **no** PB jog (manual moves are refused in every Automatic state), and PB3 re-homes rather than running a bulb |
| **E** | Auto + `ERR`: manual moves must be **REFUSED** — the negative guard on the removal of the 2026-08-04 jog window. PB3's LED stays off and PB3 does not clear the fault |
| **F** | The orange **PB2** is RESET in `ERR`, and recovery runs the dedicated `RECOVER_*` chain rather than the shared `INIT_*` one |
| **G** | The two Automatic **hold** gestures: PB1 held disarms (and an under-duration press must not), and PB2+PB3 held starts a bulb while PB3 alone only re-homes |

Roughly half the checks are **negative** — "these coils must NOT move". Those
are the ones that prove the gates gate; a jog test that only ever presses in
states where jogging is allowed cannot tell a working interlock from a missing
one.

## Transition paths come from the PLC's log, not from polling

`wait_step()` only blocks until a state is reached; **do not use what it sees as
the path**. With all retract sensors asserted, each `INIT_*` state satisfies on
the next scan, so the whole homing chain completes in ~3 `PlcTask` cycles
(30 ms) — faster than any ADS poll, and the first observation lands after it is
over. An early version of this script reported `C5` and `D4` as FAILures for
exactly that reason, and passed `E0`/`F0` on incomplete paths.

`transitions()` reconstructs the chain from `GVL_Log`, where
`FB_MasterAutoCycle` Section 3 records every `PREV -> NEW` from inside the scan.
That cannot miss one. Entries *into* `ERR` are the exception — those log
`sErrorText` instead, so an `ERR` arrival appears as the chain stopping plus a
separate `ERR`-severity entry.

## Two things the run deliberately changes

- **`GVL_Robot.bTcpEnable` is set FALSE.** The robot is not on the bench
  network, so `FB_RobotTcpClient` would log a connect failure every 3 s and
  flush the 20-entry ring before the evidence could be read. Disabling it also
  makes `ERR` **stable**, which group E needs.
- **`tPlateWaitTimeoutMs` is shortened to 700 ms** so the fault in group E
  arrives in under a second instead of ten.

Both are restored.

## What it cannot tell you

**There is no physical I/O.** A "press" is a memory write and a "coil" is a
memory read. Button contacts, LED lamps, valve wiring and the air circuit are
all still unverified — those are field checks `FLD1`–`FLD4` in
`docs/bench-checklist-arming.html`.

**Group E is a negative group now.** Manual moves are refused in every
Automatic state (operator decision 2026-08-05), so E guards the *removal* of the
jog window rather than the window itself.

**`ERR` lasts longer here than on the machine.** With a live robot,
`STATE:99` is answered `CMD:2` and the PLC clears the fault and homes about a
second after entering `ERR` — so on the machine, groups E and F pass through a
window an operator would barely see. That is fine for what they assert (jogs
refused; recovery takes the `RECOVER_*` chain) but it is why freeing a jam by
hand means switching to **Manual**.

## The full-cycle companion

`cycle_trace.py` in this directory runs ONE complete bulb with all eight pistons
emulated — a follower makes each sensor agree with its coil after a travel delay
— and checks the coil pattern of every state against what the source says it
drives. That is the end-to-end evidence for the `ResetAllCommands` refactor.

`pb_test_procedure.py` cannot do it: it asserts only the RETRACTED sensors, so a
cycle stalls in `GRIP_EXTENDING` waiting for an extend sensor that never arrives.

    python scripts/pb_test/cycle_trace.py

## Related

- `scripts/test_piston_jog_gate.py` — the same jog gate as pure logic, no PLC
- `docs/167_01_SAAD_PinPush_IO_List.xlsx` — channel map authority (sheet `IO`, column `NEW`)
- `docs/bench-checklist-arming.html` — the wider bench + field checklist
- `CLAUDE.md` → **PANEL HARDWARE**, **ARMING MODEL**
