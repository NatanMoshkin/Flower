# FlowerPyHmi — surface the PLC's CSV file log

> **STATUS: NOT STARTED.** Written 2026-08-12 as a handoff for a separate session,
> because FlowerPyHmi is a **different git repo**
> (`167_01_Saad_Flower/FlowerPyHmi`) and nothing keeps its symbol contract in step
> automatically.
>
> The PLC side is **done and verified on the panel** — Phases 0–3 of
> [`log-csv-file.md`](log-csv-file.md). This document is only the web-HMI half.

## What already exists, so nothing has to be discovered

The PLC symbols are live on the panel right now and can be read over ADS today.

**Config — `GVL_HmiPersistent.stLogFileCfg`, PERSISTENT, operator-writable:**

| Field | Type | Default | Meaning |
|---|---|---|---|
| `bEnabled` | `BOOL` | **FALSE** | master switch. Writing it is the point of this work |
| `sDir` | `STRING(80)` | `\Hard Disk\Logs\` | must stay under `\Hard Disk\` — see the warning below |
| `uiMaxFileKB` | `UDINT` | 512 | roll to the next part at this size |
| `uiMaxTotalMB` | `UDINT` | 16 | directory ceiling, pruned oldest-first |
| `uiFlushSec` | `UDINT` | 10 | buffer flush interval |

**Status — `GVL_Log.stLogFile`, volatile, read-only:**

| Field | Type | Meaning |
|---|---|---|
| `sCurrentFile` | `STRING(40)` | filename only, no directory |
| `uiBytesInFile` | `UDINT` | exact; verified byte-for-byte against the file on the card |
| `uiFilesOnDisk` | `UDINT` | refreshed by each retention sweep |
| `udiEntriesDropped` | `UDINT` | ring lapped the writer. **Non-zero is the one number worth alarming on** |
| `iErrorCode` | `UDINT` | 0 = fine |
| `sErrorText` | `STRING(80)` | |
| `eState` | `E_LogFileState` | 0 OFF / 10 BUFFER / 20 OPENING / 21 WRITING / 22 CLOSING / 30 ROTATING / 99 FAILED |
| `sStateText` | `STRING(12)` | **render this, not `eState`** |

Plus `GVL_Log.sToday : STRING(10)` (`YYYY-MM-DD`, or `0000-00-00` when the RTC is
invalid).

## The work

### 1. Poll the new symbols — `flower_py_hmi/plc_log.py`

Follow the shape already there for the log ring. Two field tuples, two roots:

```python
LOGFILE_CFG_ROOT = "GVL_HmiPersistent.stLogFileCfg"
LOGFILE_ST_ROOT  = "GVL_Log.stLogFile"
```

`sDir` is a `STRING`, the rest of the config is `PLCTYPE_UDINT` except `bEnabled`
which is `PLCTYPE_BOOL`. Status is `STRING` for `sCurrentFile` / `sErrorText` /
`sStateText`, `PLCTYPE_INT` for `eState`, `PLCTYPE_UDINT` for the four counters.

**Add them to `_cycle_symbols()`**, not to a separate `read_many`. That matters:
`scripts/check_pyhmi_contract.py` mirrors `_cycle_symbols()`, so anything read
outside it is **invisible to the contract check** — the documented blind spot that
made the `stBridgeCfg` removal register as 253/253 both before and after. 14 new
symbols should move the count **254 → 268**; if it doesn't move, they went in the
wrong place.

### 2. Render it — `templates/logs.html` + `static/logs.js`

The Logs page is the right home; it already shows the ring.

- **A "File log" toggle** bound to `bEnabled`. This is the operator-visible
  deliverable. The panel now has the same checkbox, so the two must agree.
- **Status block**: `sStateText`, `sCurrentFile`, `uiBytesInFile`,
  `uiFilesOnDisk`.
- **`udiEntriesDropped` styled as a warning when non-zero.** It means log entries
  were lost. Everywhere else in this app a zero counter is unremarkable; here it
  is the only field that says data went missing.
- **`iErrorCode` / `sErrorText` shown only when `iErrorCode <> 0`**, matching how
  the robot page treats its error text.
- **The four config numbers as editable fields**, like the master-auto timers on
  `main.html`.

### 3. Write path — `app.py`

One route per config field, mirroring `/api/master_auto/config/<field>`:

```
POST /api/log_file/config/<field>
```

**Range-check on write and reject with 400 rather than clamping** — that is this
app's existing convention for the robot tuning params, and the operator seeing
what was refused beats a silent correction. Sensible bounds: `uiMaxFileKB`
4…65536, `uiMaxTotalMB` 1…4096, `uiFlushSec` 1…3600.

**`sDir` needs a guard that is not a range.** See the warning below — a wrong
value here silently destroys durability. Refuse anything not starting
`\Hard Disk\`.

### 4. Mock — `ads_client.py`

Seed all 14 symbols in `prime_plc_log()` (or wherever the log seeds live) so mock
mode renders numbers rather than dashes. Seed `bEnabled` **FALSE** and
`sStateText` `'OFF'` so mock mode matches a freshly-commissioned panel. `pytest`
covers the mock only, so an unseeded symbol shows up as a dash that reads as
unimplemented.

### 5. Docs — `templates/docs/logs.html`

That page currently explains the ring and says a durable record needs FlowerPyHmi
attached. **That is no longer true** and is the same class of stale claim this
project keeps tripping over. Replace it with: the PLC writes its own CSV, and it
comes off the panel over FTP at `ftp://<panel-ip>/Logs/` — no laptop needed.

## Three things not to get wrong

**`sDir` must stay under `\Hard Disk\`.** `\Temp\` and the device root `\` are
*also* writable on the panel and are the WinCE **RAM object store** — files there
vanish on restart. Measured: Phase 0 wrote to four locations, and after an Activate
only the two on Compact Flash survived. Pointing `sDir` at either would silently
convert durable logging into RAM logging **while every status field still read
healthy** — reintroducing the exact defect the feature exists to fix. The PLC
refuses to fall back to them; the HMI must not offer them either.

**Render `sStateText`, never `eState`.** Not a style preference — the classic panel
VISU cannot stringify an enum, which is why the mirror exists at all. FlowerPyHmi
*could* map the number itself, but then the 0..99 → name mapping lives in three
places instead of two.

**Turning `bEnabled` on has a real cost.** It writes to Compact Flash. The caps
bound it (`uiMaxFileKB` per file, `uiMaxTotalMB` overall) and the flush interval
keeps it to one write per ~10 s, but the toggle should read as a commissioning
decision rather than a view option.

## Verification

1. `pytest` — mock only, must stay green.
2. `python scripts/check_pyhmi_contract.py` **from the Flower repo** — expect
   **254 → 268**. No movement means the symbols missed `_cycle_symbols()`.
3. `python tools/live_api_check.py --base http://127.0.0.1:8000 --net 5.79.93.36.1.1`
   against the panel. Note it opens its **own** ADS connection, so it needs
   `--net` as well as `--base`.
4. **End-to-end, which is the one that actually proves it:** toggle the HMI's File
   log checkbox on, then fetch the file from the laptop —
   `python scripts/read_log_csv.py --net 5.79.93.36.1.1 --ftp 192.168.1.100`
   (in the Flower repo). It validates CRLF, one header, 4 fields per row, no DBG
   rows, and cross-checks the rows against `GVL_Log.aRecent`.
5. Toggle it back **off** unless the machine is meant to keep logging.

## Also outstanding on the panel side, unrelated to this

- **`nConnectFails` is not on `Robot.TcVIS`.** FlowerPyHmi already shows it as
  *Failed connects*; the panel does not. Needs a cloned readout block per the
  VISU rule.
- **The technician manual says nothing about the file log.** Worth a short
  section — how to tick File log, and the FTP path to fetch it. Left undone
  deliberately: those manuals ship **English + Hebrew** from one content model,
  and inventing the Hebrew was not something to do unreviewed.
