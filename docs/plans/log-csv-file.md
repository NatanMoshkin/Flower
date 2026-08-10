# Durable CSV log on the PLC itself — implementation plan

> **STATUS: PHASE 0 PASSED, PHASES 1-2 WRITTEN, PHASES 3-4 NOT BUILT.**
> Written 2026-08-07. Phase 0 ran on the panel 2026-08-10 and the gate **passed**
> — file I/O works on WinCE 7 ARM, `\Hard Disk\` is writable, and the throwaway
> spike has been **deleted**. Phase 1 (config, status, `sToday`) is activated and
> verified on the panel. Phase 2 (`FB_LogCsvWriter`) is committed but **not yet
> compiled**. Phases 3-4 are still intent, not behaviour — do not read those
> sections as documentation. When the feature ships, strike this file through and remove its
> entry from `docs/index.html`.
>
> Open work lives in the **Active** section of `CLAUDE.md`.

## Context

**The panel log is RAM only.** `GVL_Log.aLog` is a 256-entry ring and `readme.txt`
already warns that every entry is lost on power cycle, reset or download. Under a
fault storm 256 entries is minutes, and the on-screen Logs page shows only the
newest 20.

Today the *only* durable record needs FlowerPyHmi attached over ADS from a laptop.
So a fault overnight, or on a machine nobody is sitting at, leaves nothing to read
afterwards — which is exactly when you most want the log. The CP6606 has to keep
its own record.

**CSV because the panel cannot show it.** WinCE 7 on the CP6606 has no viewer
software and no supported CPython (the reason `RobotBridge/` was abandoned). So
the file is not for reading *on* the panel — it is for copying off and opening
anywhere. CSV with RFC 4180 quoting does that with no tooling.

**Decisions taken 2026-08-07:** daily file with a size cap as a guard; INFO and
above only, never DBG; total-MB cap deleting oldest first; and **verify on the
panel before building the engine.**

## Do this first: merge, then branch

**Merge `feat/err-manual-jog-and-io-docs` into `master` before starting.** Checked
rather than assumed:

- **32 ahead, 0 behind** — the merge is a **fast-forward**. No conflicts possible.
- Three of the four bench-config files are **identical to master in commits**; the
  permanent local edits were never committed, exactly as intended.
- `PLC1.plcproj` — the one that differs — differs by **only** the two legitimate
  registrations (`ST_LogBridgeCfg` removed, `AutoConfig` added). `ProgramVersion`
  reads `3.1.4026.24` on **both** sides, i.e. the panel's value, so the hunk-level
  staging did its job and nothing bench-local leaks.

Why that order is the lower-risk one:

- 32 commits that are **built, activated and tested on the panel** (`pb_test`
  58/58, `cycle_trace` 10/10, `live_api_check` 28/28) sitting outside `master` is
  the actual exposure here — not the merge.
- This feature touches `GVL_HmiPersistent`, `GVL_Log`, `MAIN` and
  `FB_PersistentAutoSave` — all four of which changed in the last few days.
  Branching from `master` instead would guarantee conflicts; branching from the
  current branch would produce work that cannot reach `master` independently.
- The branch name is long obsolete. It says "err-manual-jog", a feature that was
  **reverted** the day after it shipped, and says nothing about the arming model,
  the RECOVER chain, the START split, `AutoConfig`, or three symbol removals.

Then branch fresh: **`feat/plc-csv-log`** off the updated `master`.

Do the merge with the four bench files left **unstaged as they are** — do not
`git stash` and reapply, and do not commit them "to keep the tree clean". They are
supposed to stay dirty.

## What already exists and gets reused

| Piece | Why it matters |
|---|---|
| `GVL_Log.aLog[0..255]` + `nWriteIdx` | The ring was *designed* for a drainer — its own comment documents `slot = nWriteIdx MOD 256` and `overflow when nWriteIdx - lastReadIdx > 256`. The Python bridge meant to drain it never shipped. This is that consumer. |
| `F_LogEvent` publish order | `nWriteIdx` increments at line 61, **after** the slot is written at 41–45. A slot is only visible once the counter passes it. |
| Single-task logging | `PRG_IoMap` (the only `IOmapTask` POU) never calls `F_LogEvent`. All logging is in `PlcTask`, so a writer FB in `PlcTask` **cannot** see a torn slot. No locking, no double-buffering. |
| `FB_PersistentAutoSave` | The async-write pattern to copy: `F_TRIG` on `BUSY` because the Beckhoff FB has no `DONE`, a `TON` quiet timer, and `START` held high until `BUSY` rises so a request cannot be dropped. |
| `MAIN` section 0a + `fbLocalTime` | `Tc2_Utilities.FB_LocalSystemTime` is already instanced, already rebuilds `sNow` on second rollover, and already degrades to `'--:--:--'` when the clock is invalid. Extend it; do not add a second time source. |
| `FB_RobotTcpClient`'s edge logging | `bStateUnanswered` logs one WARN in and one INFO out precisely so a repeating condition cannot flush a 20-entry ring. The file writer needs the same discipline for write errors. |
| FlowerPyHmi `rotate_max_bytes` / `rotate_backup_count` | Existing vocabulary for the same concept — mirror the naming so the two sides read alike. |

## Phase 0 — spike on the panel (throwaway, gate)

Two unknowns, neither answerable from the repo:

1. **Do `Tc2_System`'s file blocks work on WinCE 7 ARM at all?** `Tc2_System` is
   already referenced, but there is **no file I/O anywhere in this PLC today** —
   verified by grep. CLAUDE.md's standing rule is to confirm target capability
   before committing to an approach, and the Python bridge died exactly this way.
2. **What is the writable path?** There is **no prior art for a CE path in either
   repo** — no `\Hard Disk\`, nothing. Guessing it and building on the guess is
   the expensive mistake.

Deliverable: `FB_LogFileSpike`, called from `MAIN` behind a manual BOOL in
`GVL_Log`, that opens → writes one line → closes and mirrors `hFile`, `bError`,
`nErrId` into a GVL for ADS/VISU inspection. Plus a path probe that tries a short
candidate list and reports which one opens.

### Library verification — DONE 2026-08-10, and it corrected this plan twice

Read out of the installed `.compiled-library` files rather than from memory, which
is what this section demanded and was right to demand — two of the names below
were wrong.

**`Tc2_System` 3.10.2 has** `FB_FileOpen`, `FB_FileClose`, `FB_FileWrite`,
`FB_FileRead`, `FB_FileDelete`, `FB_FileSeek`, `FB_FileTell`, `FB_FilePuts`,
`FB_FileGets`, `FB_FileRename`, `FB_CreateDir`. Constants `PATH_GENERIC`,
`PATH_BOOTPATH`, `PATH_USERPATH1..9`, `FOPEN_MODEAPPEND`, `FOPEN_MODETEXT`,
`FOPEN_MODEWRITE`, `SEEK_*` all present. Input names confirmed: `sNetId`,
`sPathName`, `nMode`, `ePath`, `bExecute`, `tTimeout`, `hFile`, `sLine`,
`pWriteBuff`, `cbWriteLen`; outputs `bBusy`, `bError`, `nErrId`.

**CORRECTION 1 — the retention FBs do not exist under the names used below.**
`FB_FileFindFirst` / `FB_FileFindNext` / `FB_FileFindClose` are in **neither**
library. Phase 3 must use `Tc2_Utilities.FB_EnumFindFileList` and
`Tc2_Utilities.FB_EnumFindFileEntry`; `ST_FindFileEntry` is what carries
`nFileSize` / `sFileName` / `bDirectory` / `bReadOnly`. Also in `Tc2_Utilities`
and worth a look before hand-rolling anything: `FB_FileProperties` (size of one
named file, which may be all the retention sweep needs) and `FB_FileRingBuffer`.

**CORRECTION 2 — every file reference must be namespace-qualified.** This project
references `Tc2_System` **and** `Tc2_Utilities`, and **both declare**
`FB_FileOpen`, `FB_FileClose`, `FB_FilePuts`, `FB_FileRead`, `FB_FileWrite` and
`FB_FileSeek`. Unqualified those names are ambiguous and the build fails. Write
`Tc2_System.FB_FileOpen`.

**Candidate 1 is `PATH_BOOTPATH`, and that choice does real work.** It resolves to
the directory TwinCAT already writes `Port_851.bootdata` into, so on this target
with this runtime it is *provably* writable, which no hand-guessed CE path is.
That splits the gate's two questions apart: if candidate 1 fails, the file blocks
themselves are the problem, not the path. It is not necessarily where the logs
should end up living — prove capability first, choose a home second.

Deleted once it has answered. **Nothing in Phases 1–4 gets written until Phase 0
passes on the real panel.**

### GATE RESULT — PASSED on the CP6606, 2026-08-10

`python scripts/read_logfile_probe.py --net 5.79.93.36.1.1 --run`

| # | `ePath` + path | Result |
|---|---|---|
| 1 | `PATH_BOOTPATH` + `flower-spike.csv` | **OK** |
| 2 | `PATH_GENERIC` `\Hard Disk\flower-spike.csv` | **OK** |
| 3 | `PATH_GENERIC` `\Hard Disk\Logs\flower-spike.csv` | `1804` on open — directory absent |
| 4 | `PATH_GENERIC` `\Temp\flower-spike.csv` | **OK** |
| 5 | `PATH_GENERIC` `\flower-spike.csv` | **OK** |
| 6 | `PATH_USERPATH1` + `flower-spike.csv` | `1804` on open — not configured |

**4 of 6 worked, so both gate questions are answered:** `Tc2_System`'s file blocks
work on WinCE 7 ARM, and `\Hard Disk\` — the Compact Flash mount — is writable.
Both failures were `1804` on *open* with write and close never attempted, which is
a missing path rather than a missing capability; keeping the three error codes
separate is what made that distinction readable.

**The production path is `\Hard Disk\Logs\`, and candidate 3's failure is not an
objection to it** — `Logs` simply does not exist yet, and Phase 2 creates it with
`Tc2_System.FB_CreateDir` (confirmed present). The reasoning for a *dedicated
subdirectory* rather than any of the three that passed unchanged is a safety one,
recorded in full next to `sDir` in `ST_HmiLogFileCfg`: **Phase 3 deletes
oldest-first in this directory**, so pointing it at the device root or at
`PATH_BOOTPATH` — the directory holding `Port_851.bootdata` — would have the
retention sweep deleting TwinCAT's own files. A directory containing nothing but
our CSVs is what makes "delete the oldest" safe.

### `\Temp\` AND THE DEVICE ROOT `\` ARE NOT PERSISTENT STORAGE — found by the cleanup, 2026-08-10

The single most valuable result of Phase 0, and it was an accident: it came out of
adding a cleanup sweep, not out of the probe it was written for.

The write sweep passed on **four** locations. The cleanup ran afterwards, with at
least one Activate Configuration and one Download in between — and found only
**two** of those four files still present:

| Location | Wrote OK | Still there afterwards |
|---|---|---|
| `PATH_BOOTPATH` (boot dir, on Compact Flash) | yes | **yes** |
| `\Hard Disk\` (Compact Flash mount) | yes | **yes** |
| `\Temp\` | yes | **GONE** |
| `\` device root | yes | **GONE** |

A file that was opened, written and closed successfully cannot simply be absent
later unless the storage did not persist. Both survivors are on Compact Flash;
both casualties are the WinCE **RAM object store**, which is what the CE root
filesystem actually is. Restarting the device empties them.

**This is precisely the failure this whole feature exists to prevent.** The
opening argument of this plan is that a fault overnight with no laptop attached
must leave something to read. Had `\Temp\` or `\` been chosen — and *both passed
the write test cleanly* — the logger would have worked perfectly in every bench
test, on every ADS read, in every demo, and lost the entire log on the one event
that matters. It would have been discovered by someone going to read the record of
an overnight fault and finding nothing there.

`\Hard Disk\Logs\` was chosen on reasoning: operator-reachable, and a dedicated
directory makes the Phase 3 retention delete safe. It now has a third and stronger
justification, backed by measurement rather than argument: **it is one of only two
locations on this panel where a file survives a restart at all.**

**Two rules that follow, for anyone extending this:**

- **A write test is not a persistence test.** Any future path change must be
  re-verified by writing, restarting the device, and reading back — not by
  checking that the open succeeded.
- **Never fall back to `\Temp\` or `\` when the configured directory fails.** That
  is the obvious-looking defensive move and it would silently convert durable
  logging into RAM logging, reintroducing the original defect while every status
  field reports healthy. If `sDir` cannot be opened, the correct behaviour is
  `FAILED` with the error latched and visible.

### FTP IS THE RETRIEVAL PATH, and its root IS `\Hard Disk\` — established 2026-08-10

The panel runs an anonymous FTP server, and **no reconfiguration is needed**:

| PLC path | Over FTP | In Explorer |
|---|---|---|
| `\Hard Disk\Logs\flower-2026-08-10.csv` | `/Logs/flower-2026-08-10.csv` | `ftp://192.168.1.100/Logs/` |
| `PATH_BOOTPATH` (`\Hard Disk\TwinCAT\3.1\Boot`) | `/TwinCAT/3.1/Boot` | — |
| `\` and `\Temp\` (RAM object store) | **not visible** | — |

Proven by experiment rather than inferred: the FTP root was listed, the PLC probe
sweep was triggered, and `flower-spike.csv` appeared at the FTP root — then it was
deleted and confirmed gone over FTP independently of the PLC's own report.

Two things that experiment also ruled out. `CWD /Hard Disk` **fails** over FTP, so
the FTP root is not the device root. And `\Hard Disk\` is not merely an alias for
`\`: the sweep wrote to both, yet exactly one 73-byte (single-line) file appeared —
had they been the same path it would have been two lines.

**The dev target is a CX9020 running WEC7**, not the CP6606 itself — the root
carries `NK.BIN` and `CX9020_CB3011_WEC7_HPS_v610c_TC31_B4024.65`. So the
storage-card-at-FTP-root mapping is verified **on this device only**; re-check it on
the CP6606 before relying on the same paths there, using the same
write-then-look-over-FTP method.

**Consequence for Phase 2 verification, and it is a large one:** the CSV can be
retrieved and checked byte-for-byte from a developer laptop with no PLC read-back
code at all. Verification steps 2-5 become directly executable instead of needing
status symbols as a proxy.

### Line endings: keep `$N`, and do NOT write `$R$N` — measured 2026-08-10

The open question about `FB_FilePuts` is **answered**, by retrieving the probe's own
file over FTP:

```
b'"16:40:32",INFO,FB_LogFileSpike,"probe ok, quoted ""value"" with comma"\r\n'
```

71 characters plus **CRLF** = 73 bytes. So with `FOPEN_MODEAPPEND OR
FOPEN_MODETEXT`, a single `$N` in the ST string arrives on disk as **CRLF, exactly
what RFC 4180 specifies**, and `FB_FilePuts` adds no ending of its own.

**The trap this avoided:** the obvious "fix" for a suspected LF would have been to
write `$R$N` explicitly — and text mode would then have translated the `$N` again,
giving `\r\r\n` and a corrupt file. The failure mode of guessing here was worse
than the failure mode it was meant to prevent.

Also verified through that same retrieved file: Python's `csv` module parses it as
**4 clean fields**, with the embedded comma preserved and the doubled `""`
correctly unescaped to `"`, and **no phantom blank rows**. So the RFC 4180 quoting
approach Phase 2 relies on is confirmed end-to-end on real hardware, not assumed.

## Phase 1 — config, status and the clock

**New `ST_HmiLogFileCfg`** (`PLC1/DUTs/`), instanced as
`GVL_HmiPersistent.stLogFileCfg`:

- `bEnabled : BOOL := FALSE` — **default OFF.** The panel boots from Compact
  Flash; CLAUDE.md already debounces persistent writes for that reason. Logging to
  flash is opt-in.
- `sDir : STRING(80)` — the path from Phase 0. **Persistent because the correct
  value differs between installations** — dev PC vs panel — the same test that made
  `sRobotHost` persistent. A literal would be re-applied on every download and
  silently discard what was typed.
- `uiMaxFileKB : UDINT := 512` — roll early if a day gets busy.
- `uiMaxTotalMB : UDINT := 16` — the disk ceiling.
- `uiFlushSec : UDINT := 10` — buffer flush interval.

**New `ST_HmiLogFile`** — runtime status, in **`GVL_Log`** (volatile, *not*
persistent): `sCurrentFile`, `uiBytesInFile`, `uiFilesOnDisk`,
`udiEntriesDropped`, `iErrorCode`, `sErrorText`, `eState` + `sStateText`.
`sStateText` exists because **the classic VISU cannot stringify an enum** — the
settled constraint behind every other `s*Text` mirror in this project.

**Three integration points that are easy to miss:**

1. `FB_PersistentAutoSave` must watch the new struct or edits never reach disk —
   **FOUR edits, not three.** The declarations, the baseline copy beside
   `shSavedMaster := …`, the two `MEMCMP` comparisons — **and the refresh of
   `shSavedLogFile` in the post-write success branch**, which this plan originally
   omitted. Without that last one `stLogFileCfg` stays permanently different from
   its saved shadow, so `bDirty` never clears and the FB rewrites the entire
   persistent image every quiet period, forever. On a Compact Flash panel that is
   a wear bug, not merely a wasted cycle — and it would be invisible except as an
   endless stream of `persistent data saved` entries in the log.
2. `MAIN` section 0a gains `GVL_Log.sToday : STRING(10)` (`YYYY-MM-DD`), rebuilt on
   **day** rollover from the `fbLocalTime` instance already there. Needed for
   filenames; `sNow` is `HH:MM:SS` only.
3. **Cold-boot decision, required by CLAUDE.md for any new persistent field:**
   `bEnabled` and `sDir` are operator/commissioning config and are **kept** — not
   cleared in `MAIN` section 0. Record that reasoning next to the declaration.

**Migration warning to verify, not assume:** changing a `PERSISTENT` GVL's layout
can invalidate the existing `Port_851.bootdata`. After the first download, check
that the operator's existing timers still hold their values; if they reset to
defaults, re-enter them once and note it.

## Phase 2 — `FB_LogCsvWriter`

> **WRITTEN 2026-08-10, NOT YET COMPILED.** Two departures from what this section
> originally specified, both consequences of what Phase 0 measured:
>
> - **No byte buffer.** The plan called for `ARRAY[0..2047] OF BYTE` flushed with
>   one `FB_FileWrite`. The writer uses `FB_FilePuts` per row inside a single
>   open/close instead, because the flash cost unit is the **open→close cycle**
>   rather than the individual write, `FB_FilePuts + FOPEN_MODETEXT` is the only
>   form *verified* to produce correct CRLF on this target, and the 256-entry ring
>   is already the buffer — a second one would just add a second place to lose
>   entries.
> - **A state 90.** `Fail()` originally closed the handle itself with one
>   TRUE/FALSE pair in a single scan, which starts the close and disarms it before
>   it finishes, leaking a handle **per retry** — one every 30 s for as long as the
>   machine runs, eventually presenting as the file blocks having failed. A
>   still-open handle now routes through a proper async close first.


Called from `MAIN` immediately after `fbPersistentSave();` (line ~537), the same
"last in MAIN" slot and for the same reason.

**Drain.** Own `udiLastReadIdx`. `pending := nWriteIdx - udiLastReadIdx`. If
`pending > 256` the writer fell behind: add the shortfall to `udiEntriesDropped`,
emit **one synthetic CSV row recording the loss**, and skip to `nWriteIdx - 256`.
Silent loss is the one outcome to avoid.

**Filter.** Skip `eSev = DBG` unconditionally — independent of
`GVL_Log.bDebugMode`, which still governs the on-screen ring.

**Buffer, do not write per entry.** Accumulate rows into `ARRAY[0..2047] OF BYTE`;
flush when near-full **or** after `uiFlushSec`. This is the Compact Flash answer:
one write per ~10 s, not one per entry.

**CSV.** Header `time,severity,source,message`, written only when a file is
created. Quote per RFC 4180 — wrap in `"`, double any embedded `"`. **Not
theoretical:** robot frames reach messages as `SYNC:NAME=VALUE,...`, and message
text already contains commas and parentheses. Verified working on the panel
2026-08-10 — see the line-endings section above, and **end every row with a bare
`$N`, never `$R$N`**: text mode already produces CRLF and doubling it gives
`\r\r\n`.

**Async state machine.** `IDLE → OPEN(append) → WRITE → CLOSE → IDLE`, one Beckhoff
FB per step, advanced on `bBusy` falling. Never busy-wait; never hold the file open
across cycles longer than a flush needs.

**Error discipline.** On `bError`, latch `iErrorCode` / `sErrorText`, back off
(retry on a timer, not every scan), and log to the **ring** — edge-triggered, one
entry in and one out, copying `FB_RobotTcpClient`'s `bStateUnanswered` handling so
a full disk cannot flush the 20-entry ring in seconds.

**Turning `bEnabled` off** flushes what is buffered and closes cleanly rather than
abandoning the file.

## Phase 3 — rotation and retention

**Filename** `flower-YYYY-MM-DD.csv` from `sToday`, rolling to `-002`, `-003` if
`uiMaxFileKB` is hit within a day. **If the RTC is invalid** (`sNow` reads
`'--:--:--'` — the PLC already detects this) fall back to `flower-nodate-NNN.csv`
and do not rotate by date. An unset panel clock is a real condition here, not a
hypothetical.

**Retention** runs only on rotation, never per write: enumerate the directory with
`Tc2_Utilities.FB_EnumFindFileList` / `FB_EnumFindFileEntry` (**not**
`FB_FileFindFirst|Next|Close` — those do not exist, see the Phase 0 correction),
sum `ST_FindFileEntry.nFileSize`, and delete oldest-by-name
until under `uiMaxTotalMB`. Oldest-by-name is correct *because* the names sort
chronologically — a further reason to prefer the dated scheme. Never delete the
file currently open.

## Phase 4 — surfacing it

- **VISU:** extend `Logs.TcVIS` with the enable checkbox, the four numeric fields
  and the status/error text. Per the standing rule: **clone proven blocks**, never
  author elements; then `scripts/validate_visu.py`, and
  `scripts/fix_visu_object_guids.py` only if a whole page is cloned.
- **FlowerPyHmi:** add the cfg + status fields, then re-run
  `python scripts/check_pyhmi_contract.py` from the Flower repo (currently
  253/253). The count only moves if the symbols join the polled set — as the
  `stBridgeCfg` removal proved, that check is blind to anything read outside
  `_cycle_symbols()`.
- **Docs:** `readme.txt`'s "the panel log is RAM ONLY" line becomes wrong the
  moment this ships, as does the equivalent claim in the technician manual
  (`scripts/manuals/mn_technician.py` — edit the module, never the generated HTML).
- **This file:** strike it through and remove its `docs/index.html` entry. A stale
  plan at the top of the doc index is exactly the failure this project keeps
  hitting.

## Verification

1. **Phase 0 gate, on the panel:** the spike opens, writes and closes, and reports
   the working path. Do not proceed otherwise.
2. **Dev PC, sensors emulated:** enable logging, run bulbs via
   `scripts/pb_test/cycle_trace.py`, then diff the CSV rows against
   `GVL_Log.aRecent` — every INFO+ entry present, no DBG, ordering preserved.
3. **Quoting:** force a message containing a comma and a quote, then confirm the
   file parses with Python's `csv` module and the field is intact.
4. **Rotation:** set `uiMaxFileKB` to ~4 KB, generate traffic, confirm `-002`
   appears and the header is written once per file.
5. **Retention:** set `uiMaxTotalMB` to 1, generate until it trips, confirm oldest
   files are deleted, the total stays under the cap, and the open file survives.
6. **Overflow:** stall the writer (point `sDir` at a bad path), generate >256
   entries, restore, and confirm `udiEntriesDropped` is non-zero and the synthetic
   loss row appears — the failure must be visible.
7. **RTC:** clear the panel clock, confirm the `nodate` fallback rather than a
   filename built from garbage.
8. **Regression:** `scripts/pb_test/pb_test_procedure.py` (58/58),
   `cycle_trace.py` (10/10), the four Python ports, both VISU validators, and
   FlowerPyHmi `pytest` + `tools/live_api_check.py`.
9. **Flash-wear sanity on the panel:** with logging on and the machine idle,
   confirm writes happen at the flush interval, not per scan.

## Risks

- **CE7/ARM file I/O** — the Phase 0 gate exists for this and nothing else.
- **Compact Flash wear** — mitigated by default-off, buffering and a flush
  interval. State the wear argument in the config comments so nobody "improves" it
  into a per-entry write.
- **A blocking or spinning writer would hurt the 10 ms `PlcTask`** — hence async
  throughout and backoff on error.
- **Persistent layout change** may reset existing tunables once (Phase 1).
- **Do not commit the four bench-config files.** `PLC1.plcproj` is the trap: it is
  both a bench file and where new DUTs must be registered, so it needs hunk-level
  staging — as done for `AutoConfig` (`e7859c7`) and `ST_LogBridgeCfg` (`6b88015`).
