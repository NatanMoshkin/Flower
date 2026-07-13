# PLC log ring — validation test

Proves that `FB_MasterAutoCycle` writes to the `GVL_Log` ring buffer as
designed (button-press events + state transitions + errors). Uses direct
ADS reads — no dependency on `RobotBridge/` or the CSV pump.

## Prereqs

- PLC built and Activated (with the logging-enabled `FB_MasterAutoCycle`).
- `pyads` installed in the Python you invoke (`pip install pyads`).
- ADS route to the PLC. All scripts assume the local runtime:
  `AmsNetId = 127.0.0.1.1.1`, port 851. Edit the constants at the top of
  each script if you're driving a remote target.

## Files

| File | Purpose |
|---|---|
| `dump_log_ring.py` | Reads `GVL_Log.nWriteIdx` and prints the tail of the ring. Read-only. |
| `press_reset.py`   | Writes `GVL_HMI.stMasterAuto.bReset := TRUE` once, waits 100 ms, reports the delta on `nWriteIdx`. No piston motion (RESET is a no-op in IDLE). |
| `press_stop.py`    | Writes `GVL_HMI.stMasterAuto.bStop := TRUE` once. No piston motion (STOP override in section 2 gates on `eStep <> IDLE AND eStep <> ERR`, so IDLE swallows it — but the log call in section 0b still fires because it's on the rising edge, not on the state-machine consumption). |

## Procedure

### 1. Baseline

```powershell
python dump_log_ring.py
```

Right after Activate, expect:

```
GVL_Log.nWriteIdx = 0
GVL_Log.bDebugMode = False
Ring is empty (no entries written yet).
```

If `nWriteIdx > 0`, the machine has produced events already (something
happened on the HMI or an operator poked it). That's fine — just note the
current value as the baseline for the next steps.

### 2. Button-press log (safe — no motion)

```powershell
python press_reset.py
python dump_log_ring.py --tail 5
```

Expected:
- `press_reset.py` reports `Delta: 1` and `bReset auto-cleared: True`.
- The ring's newest entry is `INFO / MasterAuto / RESET pressed`.

Repeat with `press_stop.py`. The newest entry becomes
`INFO / MasterAuto / STOP pressed`, delta 1 again.

### 3. Robot start-assembly edge log

Fire the sim variant of the robot handshake (safe if the machine can
tolerate running a cycle — this WILL start SEP_EXTENDING → PUSH_EXTENDING → …
so make sure pistons are free to move first):

```powershell
python -c "import pyads,time; p=pyads.Connection('127.0.0.1.1.1',851); p.open(); p.write_by_name('GVL_HMI.stMasterAuto.bSimStartAssembly', True, pyads.PLCTYPE_BOOL); time.sleep(0.1); p.close()"
python dump_log_ring.py --tail 10
```

Expected:
- One `INFO / MasterAuto / bStartAssembly rising` entry.
- Followed by state-transition entries as the cycle runs:
  `INFO / MasterAuto / IDLE -> INIT_PUSH_RETRACTING`, then
  `INFO / MasterAuto / INIT_PUSH_RETRACTING -> INIT_SEP_RETRACTING`, and so on.

### 4. Error-path log

Force an error (easiest recipe: leave `bNoSensors = FALSE`, ensure one of
the piston sensors will not report retracted, then press START from the
HMI). Wait for `tStepTimeoutMs` (default 5 s).

Expected: `ERR / MasterAuto / INIT_PUSH_RETRACTING timed out` (or whichever
step timed out — the message tracks the timeout branch in section 4).

## Recorded results (2026-07-13, initial validation)

Session: fresh Activate → poke RESET → poke STOP → dump ring.

```
nWriteIdx before RESET poke: 0
bReset auto-cleared: True
nWriteIdx after RESET poke: 1
Delta: 1  (expect 1 log entry per edge)

nWriteIdx: 1 -> 2  (delta 1)

GVL_Log.nWriteIdx = 2
GVL_Log.bDebugMode = False

Last 2 entries (idx 0 .. 1):
   idx  slot  sev   source                msg
----------------------------------------------------------------------------------------------------
     0     0  INFO  MasterAuto            RESET pressed
     1     1  INFO  MasterAuto            STOP pressed
```

Verified:

- `F_LogEvent` writes to the ring, `nWriteIdx` increments monotonically
- Exactly one entry per rising edge (R_TRIG + auto-clear working)
- `sSource` = `stHmi.Name` = `"MasterAuto"`
- Severity INFO (`1`) correctly encoded
- Message strings intact — no truncation on 80-char field

Not yet exercised in this session (need HMI-driven cycle start):

- State-transition log (`INFO / "PREV -> NEW"`)
- Error log (`ERR / sErrorText`) — needs a forced timeout or STOP-while-running

## Where the CSV lives

Once `RobotBridge` is running, `log_pump.PlcLogPump` drains the ring at
`log_plc_ring_poll_ms` (default 500 ms) into the standard `logging`
pipeline, and `DailyCsvHandler` writes to `logs/YYYY-MM-DD.csv` at the
repo root. Without `RobotBridge` running there is no CSV — the ring is
the only place the events live.
