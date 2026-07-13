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

## CSV pipeline validation procedure

Proves the full ring-buffer → `PlcLogPump` → `DailyCsvHandler` → CSV file
path works end-to-end. Prereqs: PLC built + Activated with the current
`FB_MasterAutoCycle` (log-emitting) and `GVL_Log` (with `bLogEnabled` +
`stBridgeCfg`) additions.

### 1. Start RobotBridge

From the repo root:

```powershell
cd RobotBridge
python robot_bridge.py --config config.yaml
```

Expected startup lines (on stderr):

```
INFO    loaded config: role=client port=6001 ams=127.0.0.1.1.1
INFO    csv logger: dir=logs level=INFO
INFO    ADS opened to 127.0.0.1.1.1:851
INFO    stBridgeCfg written to PLC
INFO    log_pump: PLC nWriteIdx=N at start; draining last M entries
```

The bridge will also try to open a TCP client socket to the robot — if
you're just validating logs on a bench without the robot, that half will
show `WARNING socket connect failed` and retry every `reconnect_delay`
seconds. That is FINE — the log-pump thread runs independently of the
robot half.

Leave it running in one terminal.

### 2. Confirm stBridgeCfg landed on the PLC

From another terminal (in the repo root):

```powershell
python -c "import pyads; p=pyads.Connection('127.0.0.1.1.1',851); p.open(); print('dir:',   p.read_by_name('GVL_Log.stBridgeCfg.sLogDir',   pyads.PLCTYPE_STRING)); print('level:', p.read_by_name('GVL_Log.stBridgeCfg.sLogLevel', pyads.PLCTYPE_STRING)); print('poll:',  p.read_by_name('GVL_Log.stBridgeCfg.uiPollMs',  pyads.PLCTYPE_UDINT)); p.close()"
```

Expected output — the absolute log dir, `INFO` (or whatever config.yaml
says), and 500 (default poll_ms). Also visible on the HMI Logs page in
the RobotBridge config block.

### 3. Drive some log events + tail today's CSV

```powershell
python test_log\press_reset.py
python test_log\press_stop.py
```

Wait ≥ 1 poll interval (default 500 ms) for the pump to drain, then:

```powershell
Get-Content "logs\$(Get-Date -Format yyyy-MM-dd).csv" -Tail 10
```

Expected: the last rows show your RESET / STOP events, one per line, in
CSV form:

```
timestamp,severity,source,message
2026-07-13T22:15:03.412,INFO,plc.MasterAuto,RESET pressed
2026-07-13T22:15:07.987,INFO,plc.MasterAuto,STOP pressed
```

Notes on the columns:
- **timestamp** is Python wall-clock at drain time (not PLC scan time — see
  `ST_LogEntry.TcDUT` header for why this trade-off).
- **severity** is Python `levelname` from the map in `log_pump.py`:
  DBG → `DEBUG`, INFO → `INFO`, WARN → `WARNING`, ERR → `ERROR`.
- **source** is `plc.<sSource>` — the `plc.` prefix comes from the child
  logger created in `log_pump._read_and_emit`.

### 4. Common failure modes

| Symptom | Likely cause |
|---|---|
| `logs/` folder exists but no today CSV | Bridge isn't actually emitting. Check the terminal — did `ADS opened` line print? Is `log_pump: nWriteIdx` growing between drains? |
| CSV rows show only `bridge` / `log_pump` sources, none from `plc.MasterAuto` | The PLC-side ring is not advancing. Check `python test_log\dump_log_ring.py` — is `nWriteIdx` growing when you poke buttons? If not, either the PLC hasn't been Activated with the log-emitting FB or `bLogEnabled` is FALSE on the HMI. |
| Delta on `nWriteIdx` but no CSV rows | Pump is not draining. Check bridge terminal for `log_pump: drain cycle failed` traceback. |
| CSV rows time-lag by more than a couple of seconds | Poll interval is too long — lower `logger.plc_ring_poll_ms` in config.yaml. |
| CSV rows go missing | Ring overflow — the PLC produced > 256 events between two pumps. `log_pump` emits a `WARNING log_pump: ring overflow` line to warn you. Lower the poll interval or throttle the PLC's logging. |
