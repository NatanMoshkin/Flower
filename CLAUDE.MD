# Flower — project TODO / open issues

## TODO:


### Active — nothing is blocking these

- ~~**A robot that is not there flushes the whole log ring every ~100 s.**~~
  **DONE 2026-08-10 — built, downloaded and VERIFIED ON THE PANEL.** Found the
  same day; pre-existing, not introduced by the CSV work.

  `FB_RobotTcpClient` line 205 calls `Fail(eSev := ERR, …'Connect failed'…)`
  **unconditionally on every failed connect**, and the state machine re-dials
  every 3 s while `bTcpEnable` is TRUE. Measured on the panel with no robot
  attached: **all 20 slots of `GVL_Log.aRecent` were `Connect failed
  192.168.1.11:6001 err 1861`**, at ~5 s spacing. So the panel Logs page shows
  nothing else, and the ring is completely overwritten about every 100 seconds.

  **That defeats a documented diagnostic rule of this project.** The PANEL
  HARDWARE section says transition paths *must* come from `GVL_Log` rather than
  from polling `eStep`, because the homing chain completes faster than ADS can
  sample. Whenever the robot is absent — every bench session, and any production
  fault that also drops the link — the ring cannot hold a transition path long
  enough to read it.

  **The fix already exists in the same FB, ten lines away.** `bStateUnanswered`
  (lines 407-408 and 781-782) is edge-logged precisely so a repeating condition
  cannot flush the ring: one WARN in, one INFO out. The ROBOT COMMS LOGGING
  section argues for exactly that and says a level-logged WARN "would flush the
  ring in 20 seconds and hide the cause". Connect-failure never got the same
  treatment. Give it a `bConnectFailed` edge guard on the same pattern, and log
  the recovery once when a connect finally succeeds.

  **PROMOTED 2026-08-10 — it now fills a disk, not just a ring.** Verifying the
  Phase 2 CSV writer on the panel produced a file that was **95% this one line**
  (20 of 21 rows), i.e. **~50 KB/hour, ~1.2 MB/day** of pure noise onto the
  Compact Flash. It was already defeating the 20-entry `aRecent` ring — a
  documented diagnostic rule of this project — and it now also makes durable
  logging impractical. With rotation and retention still unbuilt (Phase 3),
  `stLogFileCfg.bEnabled` was deliberately left **FALSE**.

  So this was no longer a tidiness fix. It is one of two independent prerequisites
  for turning file logging on, the other being Phase 3.

  **What shipped:** `bConnectFailed` + `nLastConnectErr` guard the log at the
  *call site* (not inside `Fail()`, which has six callers and two that are
  deliberately not faults). The first failure of an outage logs at **ERR**, and so
  does any **change of error number** — guarding on the number as well as the
  boolean is the load-bearing part, because a bare boolean would swallow a
  genuinely new cause (1861 timeout vs. a lost route) on the strength of a flag the
  first failure had already set.

  A plain repeat is **demoted to DBG rather than suppressed**, so ticking Debug
  still gives the whole retry trace, and the CSV writer drops DBG unconditionally
  so the file never carries it either. Recovery logs **one INFO carrying the
  count** — `Connected after 312 failed attempts` tells you the outage length,
  which 312 identical ERRs in a 20-slot ring cannot.

  The count is not lost: new `ST_HmiRobot.nConnectFails` (consecutive failures in
  the current outage, cleared on connect), polled and rendered by FlowerPyHmi as
  **Failed connects** on the Robot page. Contract 253 → **254**.

  **Verified on the panel, all four behaviours, with the robot absent:**

  | Check | Result |
  |---|---|
  | Repeats suppressed | 7 attempts in 35 s → **0** new log entries; ring holds **1** `Connect failed` line, was 20/20 |
  | Demoted, not discarded | Debug ON → 5 `Connect retry` **DBG** lines appear; Debug OFF → 0 again |
  | Recovery carries the count | pointed at a mock robot on a laptop: **`Connected after 57 failed attempts`**, and 57 was exactly the pending count |
  | Guard re-arms | restoring the absent host produced a **fresh ERR**, then quiet again (0 entries in 15 s) |

  `nConnectFails` reset to 0 on the successful connect, as intended. The endpoint
  retarget path got exercised as a side effect and logged
  `Endpoint changed, redialling` — that still works too.

  Still to do: surface `nConnectFails` on the panel's own `Robot.TcVIS` — clone a
  proven readout block, per the standing VISU rule. FlowerPyHmi already shows it.

---

- ~~**Durable CSV log on the PLC itself.**~~ **DONE 2026-08-12 — Phases 0-3 built
  and VERIFIED ON THE PANEL.** Panel-side Phase 4 done too: a **File log**
  checkbox on `Logs.TcVIS` (`stLogFileCfg.bEnabled`), and `readme.txt` no longer
  claims the log is RAM only.

  **Two follow-ups, both recorded rather than silently skipped:**

  - **FlowerPyHmi has not been touched** — separate repo. Full spec, with all 14
    symbols checked against the PLC source, in
    **[`docs/plans/pyhmi-csv-log-handoff.md`](docs/plans/pyhmi-csv-log-handoff.md)**.
    Contract should move **254 → 268**; if it does not, the symbols missed
    `_cycle_symbols()`, which is that check's documented blind spot.
  - **The technician manual says nothing about the file log.** Worth a short
    section on the checkbox and the FTP path. Left undone deliberately: those
    manuals ship EN + Hebrew from one content model and inventing the Hebrew
    unreviewed was not the right call.

  Retrieval is `ftp://<panel-ip>/Logs/` — the panel's anonymous FTP root **is**
  the PLC's `\Hard Disk\`. `scripts/read_log_csv.py` fetches and validates it.
  Full plan: **[`docs/plans/log-csv-file.md`](docs/plans/log-csv-file.md)** —
  also the first link on `docs/index.html`. Read it before touching `GVL_Log`.

  The panel log is RAM only, so a fault overnight with no laptop attached
  leaves nothing to read. Four decisions are already taken: daily file with a
  size cap as a guard, INFO and above only (never DBG, which would bury the
  file in 1 Hz robot keep-alives and burn Compact Flash), a total-MB cap that
  deletes oldest first, and **a throwaway spike on the real CP6606 before any
  of it gets built** — there is no file I/O anywhere in this PLC today and no
  prior art for a WinCE path in either repo, and the Python bridge died of
  exactly that kind of unverified target assumption.

  **Merge this branch to `master` first** — see the item below; the plan
  explains why that order is the lower-risk one and why a fresh
  `feat/plc-csv-log` off an updated `master` is the right base.

- **Commit the robot's real `src2.lua`.** **Verified 2026-08-07:** the copy in
  `167_01_Saad_Flower/Robot/167-01-Saad/src2.lua` contains **zero** `CMD:` or
  `STATE:` strings, so it is still the pre-2026-07-28 revision whose generic
  `NAME:VALUE` branch swallows `STATE:0` and answers `OK: SET STATE`. The command
  channel is one-way dead against what is in git. The machine runs a newer,
  **uncommitted** revision that does emit `CMD:1`.

  This is the only place a real, working artefact exists nowhere in version
  control. Everything on the PLC side of the protocol — `ParseCmd`, the
  level-consume in `MAIN`, `STATE:<n>` — is committed and tested against a robot
  revision nobody can check out. `scripts/mock_robot/` and
  `RobotBridge/Client_working_example/dummy_server.py` implement the contract
  correctly and are the reference, but they are not what runs the cell.

---

- **Verify TcXaeShell 4024 on the panel can open 4026-saved files.** CLAUDE.md has
  said "confirm early, not at merge time" since 2026-08-04 and it is still
  unconfirmed, while the exposure has grown: **26 of 37 PLC source files now carry
  a `3.1.4026.x` `ProductVersion`** (28 of them already on `master`, so this is
  inherited rather than introduced by the current branch). The 11 still on the
  panel's `3.1.4024.16` are the files edited by script — `FB_MasterAutoCycle`,
  `MAIN`, `PRG_IoMap` and all eight `.TcVIS` pages — because those edits preserve
  the stamp byte-wise.

  If 4024 refuses a 4026-saved file, it is discovered at panel-deployment time,
  which is the worst moment. One panel-side open-and-build settles it.

---

- **Merge this branch to `master`.** `feat/err-manual-jog-and-io-docs` is **27
  commits** ahead. The hazard is known and specific: the four bench-config files
  (`.sln`, `.tsproj`, `PLC1.plcproj`, `VisualizationManager.TcVMO`) are
  permanently modified in the working tree for Local + TC 4026 and **must not go
  with it**. Note `PLC1.plcproj` is the awkward one — it is both a bench file and
  where new VISU pages must be registered, so it needs hunk-level care every time
  (done that way for `AutoConfig` in `e7859c7`).

---

- ~~**Remove `stBridgeCfg` / `ST_LogBridgeCfg`**~~ **DONE 2026-08-07** —
  FlowerPyHmi `21e747c`, PLC `6b88015`. Removed in that order, which was the point:
  deleting the symbol first would have made `read_many` log *"dropping N
  unresolvable symbol(s)"*, and that reads like a real fault.

  **`check_pyhmi_contract.py` reported 253/253 before AND after**, exactly as the
  recipe predicted — it mirrors `_cycle_symbols()` and these symbols were never in
  it, since they had their own `read_many`. That is the documented blind spot, not
  a pass. A cross-repo grep is what confirmed the removal.

  Two traps that a name-based cleanup would have walked into:

  - **`.bridge-cfg` is not bridge-specific.** `settings.html` uses it for two
    unrelated definition lists, so deleting the CSS rule on the strength of its
    name would have broken an unrelated page. Only `.bridge-cfg-title` and
    `.ro-tag` became unused. Verified after the fact by confirming both settings
    lists still compute `display: grid`.
  - **`PLCTYPE_UDINT`** in `plc_log.py` was orphaned *by* this change;
    **`PLCTYPE_BOOL`** was already unused before it. Both dropped, the distinction
    recorded.

  `docs/archive/configuration.html` and `archive/open-issues.html` still list it as
  pending. Left alone — dated snapshots, same convention as the validation records.

  **NOT YET COMPILED.**


### Blocked — waiting on the machine or on an operator decision

- **`FLD6`: the movement-timeout paths have never been exercised on any panel.**
  Every bench run so far has had `bNoSensors` set, and with it the **twelve**
  movement states advance on `tStepTimeoutMs` instead of on sensors — so error
  codes 1/3/4/5/6/7/8/10/11/12/13/14 are all unreachable. Needs one bench run with
  the flag clear and a sensor deliberately withheld.

  **Sharper since 2026-08-06:** `bNoSensors` and `bBypassPlateSensors` are
  `PERSISTENT` and survive a power cycle, while `bAutoMode` no longer does. So a
  restart now brings the panel back in **Automatic with both bench flags still
  set** — one less thing that resets itself. `scripts/pb_test` normalises both at
  entry and reports what it normalised from, which is how 14 false failures got
  diagnosed on 2026-08-05; do not read a red `pb_test` as a PLC fault before
  checking the persisted config.

---

- **Reassign LED1 / LED2 to functional statuses.** Partly done 2026-07-29 — LED3
  already blinks "press me to arm" in `NOT_HOMED`. LED1 and LED2 are still dumb
  press mirrors; the remaining candidates are LED2 = error latched and LED1 = TCP
  connected. Each is a one-line change in `MAIN`'s status-lamp section. Deferred
  until operator preference is known — this is a question, not a task.

---

- **An acknowledgement gate on the robot's `CMD:2`** — **not built**, and only
  worth building if operator-paced fault recovery is wanted in production. Today
  `ERR` is transient: the robot answers `STATE:99` with `CMD:2` within about a
  second, so the fault clears before anyone reaches the panel. What actually holds
  a fault open is switching to **Manual**, where `nStateOut` reports `MANUAL (30)`
  and the Manual re-park deliberately excludes `ERR`.

---

- **Plate sensor L/R are swapped** between the field IO list and `PRG_IoMap`
  (sheet: R on `dIn[21]`, L on `dIn[22]`; code: the reverse). Invisible while
  `bPlateOk` is an OR, but the `L`/`R` lamps on `Main.TcVIS` are mislabelled.
  Needs someone at the machine to say which physical side is which.


### Standing constraints — not tasks, but read before committing

- **An ADS round trip to the panel costs ~90 ms. To a local runtime it costs
  ~0.02 ms.** Measured 2026-08-10 against the CP6606 over the LAN. That is a
  **4500× difference**, and every test harness here was written against a local
  runtime where the cost is invisible.

  **Consequence: any harness that emulates the eight pistons by polling coils and
  writing sensors cannot keep up with a 1000 ms `tStepTimeoutMs` unless it
  batches.** Done naively — eight coil reads plus sixteen sensor writes — one
  emulator pass costs **2.2 s**, so the emulated piston cannot answer before the
  state faults. It does not look like a slow test; it looks like a PLC fault:
  `live_api_check` failed 9 of 28 with **error 6 at `INIT_PUSH_RETRACTING`**, the
  first movement state, and `cycle_trace` reported 3/10 states with a coil
  pattern that was correct for every state it managed to catch.

  **The three primitives that fix it, all verified on the panel:**

  | Instead of | Do | Cost |
  |---|---|---|
  | 8 × `read_by_name("GVL_IO.dOut[n]")` | one array read of `GVL_IO.dOut` (contiguous `ARRAY[1..16] OF BOOL`) | 718 ms → **78 ms** |
  | 16 × `write_by_name("GVL_IO.dIn[n]")` | one `write_list_by_name({...})` sum-up | 1496 ms → **130 ms** |
  | re-writing a sensor that already holds the value | cache and write on change only | a steady pass → **one** round trip |

  **Do not reach for a block write to `GVL_IO.dIn`.** A by-name handle to
  `dIn[1]` is a single BOOL, so writing a span through it fails with **ADS 1797
  (parameter size not correct)**; and writing the whole 24-channel array would
  clobber the PB (13-15), plate (21-22) and free channels. Sum-up addresses each
  symbol individually, so the channels it does not name are provably untouched —
  confirmed by reading them back.

  **Sampling counts against the same budget as driving.** `cycle_trace` sampled a
  state's coils with eight separate reads *inside* the state it was observing:
  720 ms of the 1000 ms timeout spent watching, which faulted
  `GRIP_EXTENDING` with error 10 after having already sampled it correctly. An
  observer slow enough to change the outcome is not an observer.

  **A false pass is the worse failure here.** `cycle_trace` never normalised
  `bNoSensors`, which is `PERSISTENT` and which `pb_test`'s teardown restores to
  whatever it found. With it set, all twelve movement states advance on
  `tStepTimeoutMs` **instead of** on sensors — so the piston emulator drives
  sensors nothing consults and `--lag` has no effect whatsoever. The tell was
  that `--lag 80ms` and `--lag 450ms` produced byte-identical output. Both
  harnesses now normalise the two bench flags at entry and print what they
  normalised from, the way `pb_test` has since 2026-08-05.

  Run these against the panel with `--net 5.79.93.36.1.1` (`pb_test`,
  `cycle_trace`) and `--net` **plus** `--base` (`live_api_check`, which opens its
  own ADS connection alongside the app and otherwise silently targets
  `127.0.0.1.1.1`).

---


- **Solution target is Local + TC 4026 for bench development** (no panel
  needed). Lives in the working tree across four files and **must never be
  merged back**: `167_01_Saad_PLC.sln` (VS 17.10, real `TwinCAT OS (x64)`
  build configs), `167_01_Saad_PLC.tsproj` (`TcVersion` 4026.25,
  `TargetNetId` replaced by `Target64Bit="true"`, EtherCAT device
  `Disabled="true"`), `PLC1.plcproj` (`ProgramVersion` 4026.25), and
  `VisualizationManager.TcVMO` (hotkey `DevId`).

  **The churn does not stop at those four.** Every `.TcPOU` / `.TcDUT` saved
  by the 4026 IDE gets its `ProductVersion` attribute rewritten (the panel's
  files are stamped `3.1.4024.16`) and its `LineIds` regenerated — inside the
  same files as the logic, so it cannot be excluded by path. Check the
  stamp before committing.

  **Unverified risk:** that TcXaeShell 4024 on the panel will still open a
  project the 4026 IDE has saved. Confirm early, not at merge time.


### Done — kept for the reasoning, not for the status

Struck-through items are complete. They are kept because most of them record *why*
a decision went the way it did, or a trap that cost real time; the status line is
the least useful part. Nothing here needs action.

1. ~~AutoMain VISU (panel HMI screen)~~ **DONE 2026-08-06, NOT YET COMPILED.**
  New `AutoConfig.TcVIS` (18 elements) reached from Main, with a Back button.
  AutoMain drops from 24 elements to **8** -- step/error text, ENABLE AUTO /
  START / STOP / RESET, and Auto Mode. Built by
  `scripts/build_autoconfig_page.py` + `finish_autoconfig_page.py`, validated by
  the new `scripts/validate_autoconfig.py`.

  **The bindings had to change FORM, not just page.** AutoMain is embedded as a
  frame in Main and declares `stCfg : ST_HmiMasterAutoCfg`, so its controls bound
  to `stCfg.tDwellPushMs`. AutoConfig is *navigated to*, and a navigated page
  receives no interface parameters -- so all 16 moved controls are retargeted to
  absolute `GVL_HmiPersistent.stMasterAutoCfg.*`. Left relative they would have
  bound to nothing and read zero while looking perfectly fine. That is the one
  check `validate_autoconfig.py` exists for.

  **Auto Mode deliberately did NOT move**, even though it looks like config: it
  is a machine *mode*, not a tuning value, and after item 2 it is not part of
  `stCfg` at all.

  Main's nav row went 4 buttons -> 5, re-spaced to 150 px at 153 pitch from x=20.

  **Three mistakes worth recording, all mine, all caught by checking rather than
  by reading:**

  - **TextIDs 1200/1201 were NOT free** -- they belong to the Logs page ("Log"
    and "Enabled"), and registering the new labels there silently overwrote two
    live captions. Restored, and the new labels moved to 1302/1303, verified
    absent first. The whole 1200-1267 range is Logs. **Check before allocating a
    TextID** -- the same discipline that was applied to 1106 and skipped here.
  - **The hand-picked GUID namespace `-1002xxxxxxxx` was already the Robot
    page's**, so Main's new nav button collided with a Robot element. Exactly the
    "two scripts counting 1,2,3 into one space" failure the VISU skill warns
    about. Moved to `-1006...`, verified absent across all 8 pages first.
    `validate_visu.py` is what caught it.
  - `fix_visu_object_guids.py` **must** be run on the clone, and it is what
    re-issued AutoConfig's ~60 generated-object GUIDs. A render check would not
    have caught leaving them: the page displays perfectly and the *build* fails,
    naming AutoMain rather than the clone.

  Registered in `PLC1.plcproj` with its `<DependentUpon>` -- without that the
  page renders in the IDE and does not exist to the build.

---

2. ~~ST_HmiMasterAutoCfg~~ **DONE 2026-08-06, NOT YET COMPILED.**
  - ~~Remove bContinuous~~ Gone from `ST_HmiMasterAutoCfg`, and with it **15 dead
    writes** in `FB_MasterAutoCycle` plus MAIN's force-clear. It was written 15
    times and read **zero** times, so no code path could start anything with it.
    **The per-piston `ST_HmiPistonAutoCfg.bContinuous` is a DIFFERENT field, is
    genuinely read by `FB_PistonAutoCycle` (line 170) to decide whether to re-arm
    after its retract dwell, and STAYS.** Two same-named fields in two structs is
    a real trap -- a FlowerPyHmi test now asserts the piston one survives, so a
    future cleanup cannot take it by association.
  - ~~bAutoMode default TRUE on startup~~ **Moved out of the struct** into plain
    `GVL_HMI.bAutoMode := TRUE` (volatile). Since `GVL_HMI` is plain
    `VAR_GLOBAL`, that initialiser is re-applied on every cold boot and download,
    so the panel **always comes up in Automatic** instead of restoring whatever
    mode was last selected. Chosen over merely defaulting the persistent field
    TRUE, which would only have applied to a fresh download -- after
    commissioning the stored value wins, the same trap as `sRobotHost`.

    **Safe because arming is a separate axis:** `eStep` still defaults to
    `NOT_HOMED`, which reports `STATE:40` and the robot reads as "wait", so
    nothing moves until an operator presses ENABLE AUTO. Booting Automatic
    decides *who may drive* the pistons, not *whether they may move*.

    **Consequence to know:** a technician who selects Manual to jog a piston and
    then power-cycles comes back in **Automatic**, where the PB jogs are off by
    design -- so a PB2 press will do nothing until Manual is re-selected.

  Only **3 real code reads** existed (`MAIN` 229/242/517); everything else was
  comment. The `AutoMain` checkbox binding became **absolute**
  (`GVL_HMI.bAutoMode`) rather than `stCfg`-relative, and `validate_automain`
  expects that. FlowerPyHmi keeps its API surface unchanged on purpose --
  `data-master-cfg="bAutoMode"` and `POST /api/master_auto/config/bAutoMode`
  still work, because to an operator it is the same machine-mode checkbox; only
  `_read_master_auto_cfg` and `_ma_config` know the symbol moved.

  Side finding: dropping `bAutoMode` out of `MASTER_AUTO_CFG_FIELDS` also dropped
  it out of `check_pyhmi_contract.py`, since that mirrors the field lists -- a
  silent coverage hole where a typo in the new path would have resolved nowhere
  with nothing to say so. Now covered explicitly: **253/253**.

  This also leaves `ST_HmiMasterAutoCfg` as **purely operator-tunable config** --
  7 timers + 2 bench flags, no machine state -- which is what makes it a coherent
  unit to put on its own AutoConfig page for item 1.

______________________________________________________________________________

---

- ~~**FlowerPyHmi Manual page: move the per-piston Auto controls to their own
  page, and add a Bypass-plate-sensors checkbox.**~~ **BOTH DONE 2026-08-05**
  (FlowerPyHmi `137d154`, `27f9215`). Option **(b)** was chosen — moved to
  `/piston-auto` and labelled non-functional, **structs kept in the PLC**.
  Three things worth knowing about how it landed:

  - The banner is the deliverable, not the move. It records that
    START/STOP/RESET/ACK write real ADS-writable symbols that nothing
    consumes — a button that succeeds and does nothing is worse than one
    that errors, and it is invisible from the UI.
  - The page is **deliberately not in the top nav**: promoting inert controls
    to a top-level destination is the opposite of what the banner is for. It
    is reached from a note left where the cards used to be.
  - The old page had the AUTO cards under a heading reading “Manual
    Control”, with the real manual cards below as “Manual (diagnostics)”.
    Both are now named for what they are.

  The Bypass checkbox needed a `Field("bBypassPlateSensors", PLCTYPE_BOOL)`
  as expected — contract is now **232/232**. Two smaller things came out of
  it: the mock had never seeded `tPbStopHoldMs`/`tPbStartHoldMs`, so mock mode
  showed a **0 ms** hold (an edge) for two controls that are deliberately
  holds; and **five places called this a “16-state” machine**. It is **19**,
  derived from the source rather than counted by hand: 19 CASE branches, 19
  distinct `eStep` assignment targets, with only `MANUAL` (a wire sentinel)
  and `WAIT_POS2` (retired) declared and never assigned.

  <details><summary>the original analysis, kept for the reasoning</summary>

  **Read this before doing it — `FB_PistonAutoCycle` is dead code in the panel
  solution.** The asked-for check was done 2026-08-05 and the answer changes the
  job: the FB exists as a POU, but **`MAIN` never declares or calls a single
  instance of it**. `MAIN`'s own comment at the piston call sites says so —
  *"The master cycle is the only auto driver"* — and each `fbXxxSolN(...)` wires
  `bAutoCmdExtend := fbMasterAutoCycle.bXxxCmdExtend[i]` with **no OR-merge** of
  a per-piston auto FB. So:

  - The eight `GVL_HMI.st<Piston>Auto` structs exist and are `AddSymbol`-exposed,
    but **nothing writes them**. The only POU that touches the family at all is
    `FB_PersistentAutoSave`, and only to watch the `*AutoCfg` structs for its
    flush timer.
  - FlowerPyHmi polls `GVL_HMI.st<Piston>Auto` (`piston_auto.py`) and renders a
    tile per piston. Those tiles are **inert**: `eStep` can only ever read 0, and
    their Start/Stop buttons write fields no code consumes.

  So this is not a layout task. Decide first **which of three** it is:
  (a) wire `FB_PistonAutoCycle` up in `MAIN`, OR-merged with the master cycle as
  the old per-piston DECISION section below describes — note that section is
  **stale for this solution**, it documents the deleted `Flower_PLC_HMI` dev
  mirror; (b) move the tiles to their own page *and label them as non-functional*;
  or (c) remove them from FlowerPyHmi and delete the dead structs. Moving inert
  controls to a tidier page without saying they are inert is the one option that
  makes things worse.

  **The Bypass checkbox is a smaller job than it looks, but not zero.**
  `stMasterAutoCfg.bBypassPlateSensors` exists in the PLC and is live (it
  suppresses only the `CHECK_PLATE` timeout error, not the wait — see the plate
  sensor section). But FlowerPyHmi **does not poll it at all**: it is absent from
  `MASTER_AUTO_CFG_FIELDS`, so the checkbox needs a `Field("bBypassPlateSensors",
  PLCTYPE_BOOL)` added as well as the control. That moves the contract count
  231 → 232, so `scripts/check_pyhmi_contract.py` will need re-running.

  </details>

---

- ~~**Rename START → ENABLE AUTO on both HMIs, and add a real START that runs
  a bulb from `IDLE`.**~~ **IMPLEMENTED 2026-08-05, NOT YET COMPILED** — done
  together with the RECOVER sim flags below, so the panel needs **one** build
  rather than two.

  | Layer | What changed |
  |---|---|
  | `ST_HmiMasterAuto` | new `bStartCycle` (operator "run one bulb") |
  | `FB_MasterAutoCycle` | `fbTrigStartCycle` OR-ed into `IDLE`'s exit; auto-clear + its own `'Operator cycle start'` log line |
  | `AutoMain.TcVIS` | `bStart` button relabelled **ENABLE AUTO**; new **START** button → `bStartCycle` at (300,255), by `scripts/add_automain_start_cycle_button.py` |
  | FlowerPyHmi | captions, `START_CYCLE_FIELD`, `/api/master_auto/start_cycle`, mock, docs |

  **The symbol did NOT move — only the caption.** `bStart` still means "home
  and arm" and is still accepted in `NOT_HOMED` only. Renaming the symbol
  would have broken every binding, the contract check and the tests, for a
  label.

  **Why a new field instead of re-admitting `fbTrigStart.Q` to `IDLE`:** one
  symbol meaning "arm" in one state and "run a bulb" in another is exactly
  the shape that let a green-before-orange combo press silently lose its bulb
  request. This restores the capability without restoring the defect. Four
  cases in `test_master_cycle_arming.py` guard it (20/20): runs a bulb from
  `IDLE`, refused when un-armed, refused in Manual, refused in `ERR`.

  Two side findings, both recorded in their own right:

  - **`check_pyhmi_contract.py` was not checking the write path at all.** Its
    write-only set covered robot symbols only — never the master-auto
    commands and never *any* of the 15 `bSimStep_*` symbols. So a renamed sim
    symbol would have sailed straight through the one check that exists to
    catch that, and `pytest` cannot see it because the mock has no PLC symbols.
    Now covered: **254/254**, write-only 5 → 27.
  - `validate_automain.py` **caught the relabel**, which is what it is for.
    Its table now expects `ENABLE AUTO` → `bStart` and `START` →
    `bStartCycle`. 24 elements.

  The new VISU button reuses `TextID 1106`, orphaned when the Continuous
  checkbox was deleted on 2026-07-27 — verified unreferenced first; 1107 and
  1108 are live.

---

- **Sim-step flags for the `RECOVER_*` chain.** **IMPLEMENTED 2026-08-05, NOT
  YET COMPILED** — same build as the START split above.

  The `RECOVER_*` states shipped on 2026-08-05 **without** sim flags, which was
  an omission rather than a decision: all three are sensor-waiting states exactly
  like the `INIT_*` chain, which has them. The consequence was that a recovery
  could not be stepped at all on a bench with unwired sensors — the only options
  were setting `bNoSensors` or asserting the retract sensors over ADS by hand
  (which is what `tools/live_api_check.py` has to do).

  Three `bSimStep_Recover{Push,Sep,Grip}Ret` fields, three `R_TRIG`s, three guard
  terms, three FlowerPyHmi buttons (`REC PUSH RET` / `REC SEP RET` /
  `REC GRIP RET`, placed at the end of the sim row rather than in cycle order,
  because the chain is only reachable by RESET out of `ERR`).

  **Answering the question that prompted this:** FlowerPyHmi's sim buttons were
  *already* current — 14 buttons for the 15 flags the PLC declared, correctly
  omitting the retired `bSimStep_WaitPos2`. The gap was in the PLC, not the HMI.

  Guard edits had to be scoped to Section 4: Section 3's timer `CASE` groups the
  three `RECOVER_*` labels on one line, and its **last** label is followed by a
  colon too — so a whole-file search for `RECOVER_GRIP_RETR:` lands on the timer
  entry instead of the state body. Worth knowing for any future per-state edit.

  A new live check covers each flag where it cannot be confused with a sensor:
  emulator paused, push retract sensors withheld, chain stuck — so if it advances,
  the flag was honoured.

  **Label-only on the rename — do not rename the PLC symbol.** The field stays
  `stHmi.bStart`; only the button text becomes `ENABLE AUTO`. Same trap as
  `bSimStep_WaitPlate`, whose *state* was renamed while the symbol stayed put:
  renaming the symbol would break every binding, the contract check, and the
  robot-side nothing — for a caption.

  **The new START needs its own field. Do not re-add `fbTrigStart.Q` to `IDLE`'s
  exit condition.** `bStart` already means "home and arm" in `NOT_HOMED`; making
  the same field also mean "run a bulb" in `IDLE` gives one symbol two meanings
  that differ by state, which is precisely the shape that produced the
  green-before-orange lost-request defect fixed on 2026-08-05. Instead add a
  dedicated field (e.g. `bStartCycle`) and **OR it into `bExtStartPulse`
  alongside `bComboStartPulse`**, so the combo, the robot's `CMD:1` and the HMI
  button all arrive through the one path that `IDLE` consumes.

  Worth knowing: **the panel VISU has no bulb-start control today at all** —
  nothing on any `.TcVIS` binds `bSimStartAssembly`, so on the panel a bulb can
  only be started by the robot or the PB2+PB3 hold. FlowerPyHmi already has RUN
  BULB, which pulses `bSimStartAssembly`. Do **not** simply bind the VISU button
  to that flag: it is documented as the *bench stand-in* for the robot's `CMD:1`,
  and using it as a production control erases that distinction. The new field is
  what keeps "operator started a bulb" and "someone simulated the robot"
  separable in the log ring.


_(active TODOs land here; deferred items go under "Out of scope
(Future)" at the bottom.)_

---

- ~~update FB_MasterAutoCycle (items -1- to -4-)~~ **IMPLEMENTED 2026-08-05, NOT
  YET COMPILED.** Everything below is written and statically verified; a
  TwinCAT build + download is the next step.

  | Decision | What was done |
  |---|---|
  | no PAUSED | not implemented. `docs/auto-state-machine-pause.html` is now a **rejected** option, kept for the reasoning only |
  | no manual jog in any Auto state | the 2026-08-04 `bJogEnable` window is **removed** — input deleted from `FB_SolSpringPiston_2Pos`, `bErrJogEnable` deleted from `MAIN`, all 8 call sites back to `bManualMode AND bPbN` |
  | red PB1 held → STOP → NOT_HOMED | `tonPb1Stop` + `R_TRIG`, writes `stMasterAuto.bStop`; preset `tPbStopHoldMs` (1000 ms) |
  | PB3 stays START in NOT_HOMED | unchanged |
  | green+orange held → start from IDLE | `tonPbCombo` + `R_TRIG` → `bComboStartPulse`, OR-merged into `bExtStartPulse`; preset `tPbStartHoldMs` (1000 ms) |
  | never refuse robot CMD:2; orange can also Reset | no retry counter, no `bReset` split. `fbTrigPb2` writes `bReset` while `eStep = ERR` |
  | `RECOVER_*` states | `RECOVER_PUSH_RETR := 50` / `SEP := 51` / `GRIP := 52`, error codes **12/13/14**, own timer group entry, `RESET` from `ERR` now enters this chain and it always exits to `IDLE` |
  | Method that resets all commands | `FB_MasterAutoCycle.ResetAllCommands` — **20 call sites**, one at the top of every state |
  | rename WAIT_PLATE → CHECK_PLATE | done, 13 sites. **Wire value 20 unchanged** |

  Two things came along with it:

  - **The unsafe `CASE ELSE` is fixed** — it snapped any unhandled `eStep` to
    `IDLE` (wire 0, "send me a bulb") with pistons in unknown positions. Now
    `NOT_HOMED`.
  - **Every state now calls `ResetAllCommands()` then re-asserts only what it
    owns.** Behaviour-identical (each old body's net effect was already
    "everything FALSE except what it listed"), but the previous mix of explicit
    clears and commands-held-by-omission meant reading one branch in isolation
    could not tell you what the coils were doing.

  **Two operator-facing consequences worth knowing:**

  1. **Button order for the combo does not matter.** `START` in `IDLE` is
     ignored, so a stray green press cannot move the machine and the combo's
     pulse always lands in the branch that consumes it. That was not true until
     2026-08-05 — see the PANEL HARDWARE section for the defect it fixed.
  2. **PB1's LED blinks while the STOP hold counts**, so a hold-to-act button
     is not silent guesswork.

  Both presets are editable on `AutoMain` (added by
  `scripts/add_automain_pb_timers.py`, rows y=375/415 in the right column).

  **Built, activated and TESTED on the live PLC 2026-08-05:**

  - `scripts/pb_test/pb_test_procedure.py` — **57/57**. Group E is now inverted
    (jogs must be *refused* in `ERR`) and a new **group G** covers both hold
    gestures, including the under-duration press that must do nothing. `F0`
    exercises the whole `ERR → RECOVER_* → IDLE` chain by pressing PB2, so the
    new reset mapping is tested through the button rather than the field.
  - **`scripts/pb_test/cycle_trace.py` (new) — 10/10.** Runs one *complete* bulb
    with all eight pistons emulated (a follower makes each sensor agree with its
    coil after a travel delay) and checks the coil pattern of every state against
    what the source says it drives. This is the end-to-end evidence for the
    `ResetAllCommands` refactor; `pb_test` cannot cover it, because it asserts
    only the *retracted* sensors so a cycle stalls in `GRIP_EXTENDING` forever.
  - All four Python suites pass, contract **231/231** (the two new PB hold
    timers), VISU validator clean.

  **Three harness bugs were found and fixed while testing — all in the test
  code, none in the PLC.** Worth knowing because two of them produced red output
  that looked like PLC faults:

  1. The procedure **assumed it starts from a clean machine.** A previous run
     ending in `ERR` made group C fail for a reason unrelated to group C: `ERR`
     is excluded from the Manual re-park, so "Manual → Auto parks in
     `NOT_HOMED`" could not hold. It now normalises at entry and reports what it
     normalised from. Its teardown also could not clear `ERR`, because STOP is
     excluded from `ERR` by design — it now RESETs first.
  2. **`log_since()` raced the FB's own section ordering.** A state change is
     made in Section 4 but *logged* in Section 3, which runs earlier, so the
     entry appears one scan **after** `eStep` changes — and `wait_step()` returns
     inside that window. That is how `E0` reported "NO ERR entry" while the PLC
     had `eSev=3` / `sSevText='ERR'` recorded correctly. New `settle_log()`
     waits for the ring to stop growing.
  3. `cycle_trace` **tore its first snapshot**: commands become coils in `MAIN`
     but only reach `dOut` on the next 5 ms `IOmapTask`, and the eight coils are
     eight separate ADS reads — so the copy landed mid-snapshot and
     `SEP_EXTENDING` came back with Sep1/Sep2 old and Sep3 new. It now settles
     two IO cycles and re-confirms the state before trusting the sample.

  **The four diagram docs are regenerated and now carry status banners** saying
  where each stands: `current` is **as built** (19 states), `pause` is
  **rejected**, `retract-all` is **partly implemented**, `combined` is
  **superseded**. Read `docs/auto-state-machine-current.html` for the machine as
  it runs; the other three are the decision record.

---

- ~~The PB2+PB3 combo request can be silently lost~~ **FIXED 2026-08-05 by
  removing `START` in `IDLE`.** `bComboStartPulse` is still a one-scan pulse and
  `bExtStartPulse` is still consumed only by the `IDLE` branch — but nothing can
  now move the machine out of `IDLE` except a genuine start, so the pulse cannot
  land somewhere that ignores it. Fixed at the cause rather than by latching the
  pulse, which was the other option considered.

  Worth keeping in mind if a future change ever adds a way to leave `IDLE`
  without a start: the pulse would become droppable again, and the latch would
  then be the right fix.

---

- ~~**`FB_MasterAutoCycle`'s header block is stale.**~~ **DONE 2026-08-05**
  (`2fdb429`) — eight fixes, not six: sweeping for the AND pattern after
  fixing `CHECK_PLATE` and the two `GRIP` states turned up
  `INIT_GRIP_RETRACTING` with the same claim, which reading had missed.
  Verified programmatically rather than by eye: every error code the code
  assigns is now documented, every CASE branch has a header entry, and the
  only surviving “AND of all” lines are the six Sep/Push states that really
  do aggregate with AND. Comments only — no LineIds churn, `ProductVersion`
  still `3.1.4024.16`. Original list kept below for the record.

  <details><summary>the eight, as found</summary>

  Found 2026-08-05 while re-checking this list. The RECOVER chain shipped that
  day and the file's own documentation block was never updated with it, so the
  header now contradicts the code below it. No logic changes; every item is a
  comment.

  | # | What the header says | What the code does |
  |---|---|---|
  | 1 | error-code table stops at **11** | assigns **12/13/14** at lines 796/811/826 |
  | 2 | `ERR`: RESET "re-enters the **INIT** chain" | enters the **RECOVER** chain — actively wrong about the 2026-08-05 change |
  | 3 | sequence listing has **no `RECOVER_*` states** | three of them, values 50/51/52 |
  | 4 | sensorless covers "the **4** movement states", codes "**1/3/4/5**" | **12** states, codes **1/3/4/5/6/7/8/10/11/12/13/14** |
  | 5 | `CHECK_PLATE` waits "`bPlateSenL` **AND** `bPlateSenR`" (header line 61) and "Both plate sensors must confirm TRUE" (branch comment) | guard is `bPlateOk`, an **OR** — the documented field deviation |
  | 6 | `GRIP_EXTENDING` / `GRIP_RETRACTING` "wait **AND** of all" | also an OR, and the header does not flag it as a deviation |

  Items 5 and 6 are the same defect that was corrected in FlowerPyHmi's
  `main.html` on 2026-08-05 (it claimed both plate sensors were required); it
  sits in the PLC source too. Item 2 is the one that would actively mislead
  whoever debugs a failed recovery next, since it names the wrong chain.

  Item 4's count is worth stating precisely, because a naive grep gets it wrong:
  **thirteen** CASE branches mention `bNoSensors`, but `CHECK_PLATE`'s mention is
  inside a comment explaining that it deliberately does **not** apply. Twelve
  states actually carry the term.

  </details>

---

- ~~**`scripts/validate_automain.py` is stale**~~ — **DONE 2026-08-05**
  (`6ab9718`). The `Continuous` expectation is gone (that checkbox was
  deliberately deleted on 2026-07-27) and the validator now passes: 23 elements,
  all direct children, identities unique. Also added the **fourth checkbox**,
  `Bypass plate sensors`, which had been on the page since 2026-07-26 with no
  expectation covering it — the same silent coverage hole that let the
  `Continuous` row rot. Negative-tested by pointing the new row at a wrong symbol
  and confirming it reports the mismatch instead of passing.

---

- ~~**`FB_MasterAutoCycle`'s defensive `CASE ELSE` fails unsafe.**~~ **FIXED
  2026-08-05**, verified in the source: the default branch is now
  `ResetAllCommands(); stHmi.eStep := E_MasterAutoStep.NOT_HOMED;`. Kept for the
  reasoning, which is why the fix matters. It used to assign
  `stHmi.eStep := E_MasterAutoStep.IDLE` — wire value **0**, the one value that
  makes the robot send `CMD:1` — reached with the pistons in unknown positions.
  Reachable: `GVL_HMI` carries `TcHmiSymbol.AddSymbol` so `eStep` is ADS-writable,
  and `WAIT_POS2 (2)` is a declared enumerator with no branch today. Should be
  `NOT_HOMED`. Two lines, independent of everything else.

---

- ~~Create branch for the next task~~ **Done 2026-08-04** —
  `feat/err-manual-jog-and-io-docs`.

---

- ~~check the current Push Buttons actions~~ **Done 2026-08-04.** Behaviour
  was correct and matches the IO list; **four comments were not** and are
  fixed: `MAIN`'s PB block (still described PB1 as a cycle-start bypass),
  `MAIN` section 0 (still claimed power-up comes back in IDLE and a robot may
  start a cycle — the exact hazard closed on 2026-07-29), `PRG_IoMap`'s PB
  note, and `FB_MasterAutoCycle`'s Section 2 header. The **IO table in this
  file was wrong for all six Sep/Push pistons** since `fd49d4f` and is now
  rebuilt from `docs/167_01_SAAD_PinPush_IO_List.xlsx`.

---

- ~~Operator recovery from a mid-cycle grip fault~~ **Settled 2026-08-05.**
  The 2026-08-04 answer (PB jogs while latched in `ERR`) was **reversed** — no
  manual moves in any Automatic state. What shipped instead is the dedicated
  `RECOVER_*` chain: `ERR` → `RESET` (HMI, orange PB2, or robot `CMD:2`) →
  `RECOVER_PUSH_RETR` → `SEP` → `GRIP` → `IDLE`, with its own error codes
  12/13/14 so a failed recovery no longer looks identical to a failed arming.

  Recovery still runs a **fresh bulb**; resuming the interrupted one was not
  built and is still not possible — nothing durably records which step faulted
  (`ePrevStep` is overwritten with `ERR` on the transition scan, and only
  `iErrorCode` survives). To free a jam by hand, switch to **Manual**.

---

- ~~`Panel_PLC_HMI/License/` is untracked — commit or add to `.gitignore`.~~
  **Done** (`d123cac`) — verified ignored, with a `.gitignore` comment saying
  why: the files are bound to one target's System ID, so they are useless on
  any other machine.


### Records and superseded proposals

Finished work and rejected options. These read like open items because they are
written in the same shape as the rest of the list — they are not.

- **Operator + technician manuals, bilingual (2026-08-05).**
  `docs/operator-manual.html` (simple, panel-facing) and
  `docs/technician-manual.html` (sequence, error codes, settings, IO, robot
  protocol, diagnostics, deviations). Both carry **English + Hebrew** and a
  dark/light theme; both languages ship in the file and switch with CSS, so the
  pages work from a filesystem with no network.

  Generated by `python scripts/manuals/build_manuals.py` from one shared content
  model, so EN and HE cannot drift structurally — edit the `mn_*.py` modules,
  never the HTML.

  **RTL is handled properly, and the traps are real.** `dir` is set on `<html>`
  so the layout mirrors; spacing uses logical properties; and **any table cell
  or token without Hebrew letters gets `dir="ltr"`** — otherwise a run like
  `3 / 7 / 11` in the IO table renders as `11 / 7 / 3` under an RTL base
  direction. That was found by rendering, not by reading. There is a checker
  worth re-running after any Hebrew edit: scan the built HTML for cells that
  contain Hebrew *and* a `\d+[/,]\d+` run and are not isolated.

---

- **`docs/` is now split: current vs `docs/archive/`.** The archive holds the
  three superseded state-machine proposals plus four 2026-07-27 snapshots
  (`configuration`, `operation`, `open-issues`, the old markdown operator
  manual) and `robot-integration-options.md`. All of them predate the arming
  model — they mention `WAIT_PLATE` and never mention `NOT_HOMED`. Nothing
  generates them and nothing should be read from them.
  `docs/index.html` links everything with a status badge per entry.

---

- **FlowerPyHmi is caught up — separate repo, branch
  `feat/check-plate-recover-and-pb-hold-timers` (2026-08-05).** Everything the
  PLC changed today was visible there as a wrong label or a missing field:
  `CHECK_PLATE`, the three `RECOVER_*` names, error codes 12/13/14, and the two
  hold timers (now editable on `main.html` next to the step timers). Its mock's
  `bStart` was narrowed to `NOT_HOMED` only, because mirroring the *refusal*
  matters as much as the happy path — a mock that still re-homed from `IDLE`
  would make the web HMI look wrong against the real panel. Verified 84/84
  pytest, contract 231/231, and **21/21 on the new `tools/live_api_check.py`**.

  **Two things not to "fix" there:**

  - The sim-step key stays **`WaitPlate`** — only the *state* was renamed, the
    PLC symbol is still `bSimStep_WaitPlate`. The button's label reads
    `CHECK PLATE`; the key behind it must not.
  - `docs/validation-*.html` and `docs/bench-checklist.html` **keep** the old
    name. They are dated records of what was observed at the time.

  **`tools/live_api_check.py` is the new thing worth knowing about.** `pytest`
  there covers the mock only, and the mock is a Python reimplementation of this
  state machine — so it structurally cannot catch a renamed or retyped PLC
  symbol, which is exactly what today's work was. That failure mode shows up as
  a `?` in the step pill and only a live runtime reveals it. Two properties of
  that tool are load-bearing: it makes a state long-lived (by withholding the
  sensor it waits for) before asserting the state *renders*, because the poller
  is 100 ms and several states last ~30 ms; and its piston emulator's `pause()`
  waits for an acknowledgement rather than just clearing a flag — eight ADS
  writes per pass can still land ~10 ms after the flag drops, enough to restore
  the very sensor being withheld. That made one check pass then fail on
  consecutive runs.

  Two claims that app was making are also corrected: `main.html` said **both**
  plate sensors must be TRUE (it is an OR — see the field-deviation note), and
  its `operation.html` asserted `bBypassPlateSensors` **does not exist** in
  `ST_HmiMasterAutoCfg`. It does.

---

- **Update the Auto state machine.** Three decision documents are built and are
  the input for this — read them before touching `FB_MasterAutoCycle`:

  | Doc | Shows |
  |---|---|
  | `docs/auto-state-machine-current.html` | the 16 assigned states as the **source** implements them, plus six places the code and its own comments disagree |
  | `docs/auto-state-machine-pause.html` | per-step Pause/Continue on the orange PB2 |
  | `docs/auto-state-machine-retract-all.html` | Retract-all split from `ERR`, with the retry counter |
  | **`docs/auto-state-machine-combined.html`** | **the combined target — implement from this one** |

  Generated by `python scripts/statediagram/build_state_diagrams.py` (hand-laid-out
  inline SVG — no mermaid, so the pages open straight from the filesystem). Edit
  the `sm_*.py` spec, never the generated HTML. **Every state box is clickable**
  and shows the exact commands that state drives, what it holds by omission, its
  guard, its timer and — on the variant pages — what a pause there would mean.
  The command data is transcribed from Section 4's CASE bodies; if the ST
  changes, `sm_common.COMMANDS` must change with it.

  **Operator decisions taken 2026-08-04, which the docs now reflect:**

  - **Pause is per-step, not per-bulb.** Pause is available from every step and
    Continue resumes *that* step. The safe form is **hold at the step boundary**:
    the request takes effect the moment the current step's exit guard is
    satisfied, so every commanded motion has completed and been sensor-confirmed
    and nothing is ever held mid-stroke. `eStep` keeps holding the interrupted
    step; `PAUSED (41)` is emitted from `nStateOut`, never assigned to `eStep`.
    Two consequences worth knowing: the step timer **must** be stopped or the
    hold faults in 10 s with an error code that lies; and if a guard is never
    satisfied (a real jam) the pause never takes effect and the step times out
    into `ERR` — Pause is not an abort, STOP is.
  - **`DWELL_PUSH` is excluded from pause** — its guard is "dwell elapsed", so
    holding there keeps full pin load applied indefinitely. Pause takes effect
    one step later instead.
  - ~~Manual commands allowed in STOP and `ERR`~~ **REVERSED 2026-08-05** —
    no manual moves in any Automatic state. The `bJogEnable` window was deleted;
    see the PANEL HARDWARE section. This also makes the `PB3`-in-`NOT_HOMED`
    conflict moot, since nothing jogs there.

  **Superseded — read the PANEL HARDWARE and state-machine sections instead.**
  Of the three features analysed above, only the `RECOVER_*` chain shipped
  (2026-08-05). Pause was rejected outright, the manual-in-Auto window was
  reversed, and the retry counter + `bReset` split were ruled out because the
  robot only sends `CMD:2` when a human presses a button on its own panel — so
  it can never arrive unattended, which was the premise of that whole argument.
  The four diagram pages carry status banners saying which is which.

  **The recommended order to implement in** (from the analysis behind those docs;
  the reasoning is on the retract-all page):

  1. Fix the unsafe `CASE ELSE` — see the separate TODO below. Alone, first.
  2. `bHomeThenIdle : BOOL` → `eReturnTo : E_MasterAutoStep`. Zero wire risk, and
     it flips the fail-safe default: an uninitialised BOOL is FALSE = "go run a
     bulb", an uninitialised enum is 0 = `IDLE`.
  3. **One enum commit reserving every new wire value at once** — `PAUSED := 41`
     and `RECOVER_* := 50/51/52`. The robot contract then changes exactly once,
     so there is one verification trip against the real `src2.lua` instead of two.
     This is the single most valuable sequencing decision here.
  4. **Widen the manual-command window to `NOT_HOMED`** — one condition in
     `MAIN`, no wire risk, smallest useful change of the set.
  5. The `RECOVER_*` branches + error codes 12/13/14 + the rename to
     `RETRACT_ALL_*` (keeping 10/11/12) — **plus the retry counter and splitting
     `bReset` into operator-vs-robot**, without which it is a cosmetic change
     sold as a safety one.
  6. Per-step Pause/Continue last. Its resume point *is* `eStep`, so it needs no
     resume variable — but its pause flag must **not** reuse `eReturnTo`, which
     would repeat the `bHomeThenIdle` mistake one level up.

  **Why the three features are worth doing together** (the combined page argues
  this at length): separating `RECOVER_*` is what makes the manual window
  actually usable, because today the window is `eStep = ERR` and the robot resets
  `ERR` in about a second — with recovery in its own states, `ERR` stays latched
  as a real "stopped, waiting for a decision" state while the *motion* happens
  in `RECOVER_*`, where jogs are correctly off. The retry counter then stops even
  that window closing. And Pause gives a hands-on path that never involves a
  fault at all: Pause → STOP → manual work → START.

  Two hard constraints that came out of the analysis:
  - **Pause cannot stop a piston mid-stroke.** All eight actuators are
    single-coil spring-return, so the stroke in flight completes either way.
    Pause can only mean "finish the bulb, then hold at `IDLE`".
  - **No pause flag or resume step may live in `GVL_HmiPersistent`.** Every
    piston retracts on power loss, so a persisted pause would resume a sequence
    whose assumptions are all void. `GVL_HMI` scrubs it for free.

---

- **Two more stale-doc items found 2026-08-04, both now corrected above:**
  `bContinuous` is written ten times and read zero times (the PERSISTENT section
  claimed IDLE still tests it), and `bNoSensors` carries its term in **nine**
  states rather than four — so with that flag set, error codes
  1/3/4/5/6/7/8/10/11 are *all* unreachable. `bAnyRunning` is also dead: computed,
  never read, and its comment claims MAIN uses it. Error codes 2 and 99 are
  unreachable, correctly documented as retired.

## SHIPPED: robot integration architecture — TCP-only (2026-07-26)

Resolved. `FB_RobotTcpClient` (`Tc2_TcpIp` on TF6310) is the sole channel
between the PLC and the Dobot. The former discrete-I/O handshake
(`STAND_SEQ_DO`/`STAND_SEQ_DI`) is retired; the `DI[13]` / `DO[7]` channels
it freed now carry PB1 and its LED (rewired 2026-07-27).

The four original options in `docs/robot-integration-options.md` are now
historic; the file is kept for archaeology but does not describe current
behaviour. `RobotBridge/` (Python) is out of scope for the panel — kept
only as protocol reference (`Client_working_example/`). `FlowerPyHmi/`
remains engineering-side (runs on any developer laptop) and unaffected.


## DECISION: 167_01 panel solution — TCP-only robot comms + global Auto/Manual interlock

Scope: `Panel_PLC_HMI/167_01_Saad_PLC/` is the **only** PLC solution.

**`Flower_PLC_HMI/` was deleted 2026-07-26.** It held the dev PLC solution
(a byte-for-byte mirror for local PC testing) and the TwinCAT web HMI
`Flower_HMI/`. Both are retired — there is no mirror to keep in sync any
more, so PLC edits land in one place only. The engineering-side UI is now
`FlowerPyHmi` (separate git repo at `167_01_Saad_Flower/FlowerPyHmi`,
talks ADS to the panel; not a submodule, so nothing keeps its symbol
contract in step automatically — run `python scripts/check_pyhmi_contract.py`
after changing any HMI-facing GVL or DUT). Recover the old solution from
git history if ever needed.

**Global Auto/Manual hard interlock (2026-07-19).** A single machine-wide
BOOL `GVL_HmiPersistent.stMasterAutoCfg.bAutoMode` is the sole source of
truth for every piston's mode — "no option to double control". `MAIN` drives
it unconditionally each scan onto BOTH `eMode` and `bMode` of all eight
pistons (six Sep/Push + two Grip). `FB_SolSpringPiston_2Pos` edge-syncs the
two, so forcing only one would let a stray toggle propagate for a scan;
forcing both closes that gap. In Auto the MasterAutoCycle owns all eight
pistons — no per-piston auto tiles in the panel solution. In Manual the
master cycle is held IDLE and the operator jogs. `E_ControlMode`:
Manual=0, Automatic=1.

**Robot comms — TCP-only (2026-07-26).** `FB_RobotTcpClient` (native ST,
uses free-with-TF6310 `Tc2_TcpIp`) dials the robot server `:6001`. TF6310
is installed+running on the CP6606 — the documented exception to the
avoid-paid-libs rule. All start/stop/reset traffic goes through this
channel; the former discrete-I/O handshake (`STAND_SEQ_DO`/`STAND_SEQ_DI`)
is retired; the DI[13] / DO[7] channels it freed now carry PB1 + LED1.

- Protocol (raw ASCII, NO newline framing; one send → one reply — matches
  `RobotBridge/Client_working_example/tcp client.py` + `dummy_server.py`
  plus the new STATE/CMD frames):

  | PLC → robot | Robot → PLC | Purpose |
  |---|---|---|
  | `GET_SYNC` | `SYNC:NAME=VALUE,...` | Pull all 11 tuning params |
  | `NAME:VALUE` | `OK: SET NAME` | Set one tuning param |
  | `New_Bulb:1` | `OK: SET New_Bulb` | Start a fresh bulb |
  | `STATE:<n>` | `CMD:<m>` | State push + command receive |

- `STATE:<n>` (`n = INT` value of `E_MasterAutoStep`, or `MANUAL=30` when
  `bAutoMode=FALSE`). Sent on every change of `stParams.nStateOut` and
  every `IDLE_STATE_MS` (default 1000 ms) as keep-alive. Replaces the old
  `HEARTBEAT` frame.
- `CMD:<m>` (`m` ∈ {0,1,2}: 0=none, 1=start cycle, 2=reset error).
  `ParseCmd` writes it into `stParams.nRobotCmd`; `MAIN` consumes that
  field as a **level** and **clears it to 0 in the same scan**, feeding
  FB_MasterAutoCycle (`bExtStartPulse`) or the HMI's `bReset`. The PLC's
  clear is the acknowledgement — see "ROBOT CMD:1 DEADLOCK" below for why
  edge-detection here broke the machine.

- `DUTs/ST_RobotParams.TcDUT` — 11 INT tuning params + request flags
  (`bGetSync`, `bSetParam`/`sSetName`/`nSetVal`, `bTriggerNewBulb`, FB
  auto-clears each after ACK) + the two INTs `nStateOut` / `nRobotCmd`.
- `GVL_Robot`: `stParams`, `bTcpEnable`, plus a **`VAR_GLOBAL PERSISTENT`**
  block holding `sRobotHost` (factory default '192.168.1.11' since 2026-07-29,
  was '192.168.201.1'; **a new literal does not retarget an already-commissioned
  panel** — the stored value wins, so use the Robot page or Reset Origin) and
  `nRobotPort` (6001) — editable from the Robot page; see the PERSISTENT
  section for why those two persist and `bTcpEnable` does not. Status mirror in `stRobot`:
  `eConnState`/`sConnStateText`/`nPacketsRx`/`nPacketsTx`/
  `sLastMessage`/`sLastTxMessage`. `MAIN` calls `fbRobotTcp` each scan.
- Connection state machine: Disconnected → Connecting → Connected → (any
  socket error) close + reconnect after 3 s. Empty `sSrvNetId` targets
  the local TF6310 server. `CMD:0/1/2` verified against the robot
  2026-07-26.

**Tuning params are read/write (shadow-copy push, 2026-07-26).** They used
to be read-only in practice: `GET_SYNC` pulled values in, but the only way
to push one back was the `bSetParam`/`sSetName`/`nSetVal` triple, which
*nothing* ever set — no VISU page, no MAIN code, no HMI binding. Since
`GVL_Robot` is `AddSymbol`-exposed, an operator editing `stParams.J_SPEED`
saw the value change, nothing was sent, and the next reconnect's `GET_SYNC`
silently reverted it.

`FB_RobotTcpClient` now keeps `aShadow : ARRAY[1..11] OF INT`, re-baselined
by `SetShadowAll` after every `GET_SYNC` round-trip. Any live field that
diverges from its shadow slot is an operator edit and is pushed as
`NAME:VALUE`, one param per round-trip; `HandleReply` banks the value that
was *sent* (`nPendVal`), so an edit made mid-round-trip is re-sent rather
than swallowed. So an HMI NumericInput can bind straight to
`GVL_Robot.stParams.J_SPEED` and just work. The `bSetParam` triple survives
as a raw escape hatch for names that aren't struct fields.

Index↔name mapping lives in `ParamValue` / `ParamName` and **must** match
the robot's `SYNC_ORDER`. `bShadowValid` gates detection until the first
SYNC lands, so the compiled-in defaults are never mistaken for edits.

`IO_IDLE` priority order matters and is asserted by the tests:
1. post-connect one-shot `GET_SYNC` — a `STATE` reply can carry `CMD:1`,
   and a cycle must not start on unsynced params;
2. `STATE` on change — `CMD` frames ride back on `STATE` replies, so a
   write burst must not starve start/reset;
3. explicit `bSetParam` / `bTriggerNewBulb` / `bGetSync`;
4. detected edits;
5. `STATE` keep-alive.

*Known limitation:* `stParams` is both setpoint and actual, so an edit made
while the link is down is overwritten by the reconnect's `GET_SYNC`.
Separating desired-vs-actual needs a second struct — deferred.

`scripts/test_param_shadow_logic.py` ports the sequencer to Python and runs it
against the protocol (9 cases: no startup echo, edit pushed, all three
speeds, state preemption, CMD during write burst, mid-flight re-edit,
escape hatch, re-sync baseline, malformed SYNC). Run
`python scripts/test_param_shadow_logic.py`. It validates the *algorithm*, not
the ST build — a TwinCAT compile is still required.


## DECISION: FB_MasterAutoCycle drives the full-machine auto sequence

The machine's operator-facing cycle is implemented as `FB_MasterAutoCycle`
(commit `9ba7a14`, with mode-forcing added in `8a39fae`, and simplified
robot interface added 2026-07-10). It coordinates the 3 pairs of (SepSolN,
PushSolN) pistons in parallel with a single robot handshake signal. The
former "Pair count" runtime knob (`uiPairCount`) was removed 2026-07-12 —
pair count is fixed at 3.

**Robot interface (TCP-only, 2026-07-26):** all robot signals travel over
`FB_RobotTcpClient` (see the panel-solution decision above for the
protocol). No discrete-I/O handshake anymore.

| Direction | ST_RobotParams field | Wire | Semantic |
|---|---|---|---|
| PLC → Robot | `nStateOut : INT` | `STATE:<n>` frame | `TO_INT(eStep)` in Auto; `MANUAL=30` in Manual. The robot acts on exactly three values: **0** = armed, send `CMD:1`; **99** = faulted, send `CMD:2`; **anything else (incl. `NOT_HOMED=40`)** = wait, send `CMD:0`. |
| Robot → PLC | `nRobotCmd : INT` | `CMD:<m>` reply | 0=none, 1=start cycle (level → `bExtStartPulse`), 2=reset error (level → `stMasterAuto.bReset`). MAIN clears the field to 0 on consumption. |

The former `POS1/POS2/POS3` + `AUTO_STARTED/PUSH_DONE/PISTONS_ERROR` TCP
protocol and the `STAND_SEQ_DO`/`STAND_SEQ_DI` discrete-I/O handshake
are both retired. `WAIT_POS2` is retired too — the Dobot's
`PerformStandSequence` moves the arm clear of the stand *before* it
issues `CMD:1`, so no intermediate "robot moved away" wait is needed.

**TWO KINDS OF START, DIFFERENT OWNERS (2026-07-29).** See the ARMING MODEL
section below for the reasoning; the short version:

| Trigger | Means | Valid from |
|---|---|---|
| operator START (`stHmi.bStart`, HMI button or green **PB3** in Auto) | home the pistons and **arm** | `NOT_HOMED` only — ignored in `IDLE` since 2026-08-05 |
| robot `CMD:1` (`bExtStartPulse`) | run **one bulb cycle** | `IDLE` only |

**Sixteen-state state machine** (`E_MasterAutoStep`; `WAIT_POS2` value
still declared in the enum but unused — safe to remove once every HMI
page has stopped referring to it):

```
NOT_HOMED (40)          In Automatic but NOT armed. Entered on power-up (the
                        declared default of stHmi.eStep), on any time spent in
                        Manual, and on operator STOP. Nothing driven, no timer.
                        nStateOut = 40, which the robot answers CMD:0 (wait).
                        Exits ONLY on operator START -> INIT chain with
                        bHomeThenIdle TRUE.
IDLE (0)                Armed. Waits for bExtStartPulse (robot CMD:1) OR
                        bSimStartAssembly OR bSimStep_Idle -> INIT chain with
                        bHomeThenIdle FALSE (a bulb cycle). Operator START here
                        is IGNORED (2026-08-05) -- logged by Section 0b and
                        nothing else. It used to re-home and come back; that was
                        a no-op in outcome and it let a green-before-orange combo
                        press lose the bulb request. See the PANEL HARDWARE
                        section.
                        nStateOut = 0 so the robot sees "armed, send me a bulb".
                        NOTE fbTrigStart.Q and stCfg.bContinuous were both
                        REMOVED from this exit condition — that is what makes
                        the robot the only starter of a bulb.
INIT_PUSH_RETRACTING(10) Drive PushCmdRetract[1..3]; wait AND of all 3
                        PushIsRetracted. Auto-satisfies on the next scan
                        when push is already home.
INIT_SEP_RETRACTING (11) Drive SepCmdRetract[1..3]; wait AND of all 3
                        SepIsRetracted.
INIT_GRIP_RETRACTING(12) Drive GripCmdRetract[1..2]; wait AND of all
                        GripIsRetracted. Defensive symmetry with the INIT
                        Sep/Push states so a manual jog left extended does
                        not collide with the arriving plate.
                        THE ONE PLACE THE TWO CALLERS DIVERGE: exits to IDLE
                        when bHomeThenIdle (homing), else to CHECK_PLATE (bulb
                        cycle). Everything above is identical for both.
CHECK_PLATE (20)        Wait `bPlateSenL OR bPlateSenR` (robot has placed
                        the plate). Latched at start only; sensors not
                        monitored past this step. Timeout uses
                        `tPlateWaitTimeoutMs` (bounded by robot placement time).
                        `stCfg.bBypassPlateSensors` suppresses the timeout
                        ERROR only — see the plate-sensor section below.
GRIP_EXTENDING (21)     Drive GripCmdExtend[1..2]; wait AND of all
                        GripIsExtended. Plate clamped from both sides.
SEP_EXTENDING (1)       Drive SepCmdExtend[1..3]; wait AND of all
                        SepIsExtended. Grip stays extended for every state
                        below (held from GRIP_EXTENDING through SEP_RETRACTED_DWELL).
PUSH_EXTENDING (3)      Drive PushCmdExtend[1..3]; wait AND of all PushIsExtended.
DWELL_PUSH (4)          Hold both extended; wait tDwellPushMs (default 2000).
PUSH_RETRACTING (5)     Drive PushCmdRetract[1..3]; wait AND of all PushIsRetracted.
PUSH_RETRACTED_DWELL(6) Wait tPushRetractedDwellMs (default 500).
SEP_RETRACTING (7)      Drive SepCmdRetract[1..3]; wait AND of all SepIsRetracted.
SEP_RETRACTED_DWELL (8) Wait tSepRetractedDwellMs (default 500).
GRIP_RETRACTING (22)    Drive GripCmdRetract[1..2]; wait AND of all
                        GripIsRetracted. Releases the plate; increment
                        nCyclesCompleted; back to IDLE — still armed, so the
                        robot's next CMD:1 runs the next bulb.
ERR (99)                Latched. iErrorCode = step's fault code.
                        nStateOut = 99, on which the robot answers CMD:2.
                        RESET (that CMD:2, the HMI button, or the orange PB2)
                        clears the error and enters the RECOVER chain below —
                        NOT straight to IDLE. A fault leaves the pistons
                        anywhere, so advertising IDLE(0) would claim "ready"
                        while it is not; and RESET landing in IDLE with the
                        robot still asking made RESET itself a start button.
RECOVER_PUSH_RETR (50)  Fault-recovery retract chain, added 2026-08-05. Same
RECOVER_SEP_RETR  (51)  motion and the same collision ordering as the INIT
RECOVER_GRIP_RETR (52)  chain, but its own identity so a failed RECOVERY is
                        distinguishable from a failed ARMING: error codes
                        12/13/14 instead of 6/7/8, and its own sStepText.
                        Entered ONLY from ERR on RESET. RECOVER_GRIP_RETR
                        always exits to IDLE — at that point the machine really
                        is homed, so advertising STATE:0 is honest. The robot
                        needed no new branch: it acts on 0 and 99 and treats
                        everything else as "wait".
```

**FIELD DEVIATION: grip and plate aggregation is OR, not AND (since
`fd49d4f`, 2026-07-28; reaffirmed 2026-08-04).** Every "wait AND of all"
above is accurate for Sep and Push, and **wrong for grip and plate**.
`FB_MasterAutoCycle` Section 1 actually computes:

```
bAllGripExtended  := bGripIsExtended[1]  OR bGripIsExtended[2];
bAllGripRetracted := bGripIsRetracted[1] OR bGripIsRetracted[2];
bPlateOk          := bPlateSenL OR bPlateSenR;
```

**Why, and why it stays.** `GripSolR` has **no air supply** on the machine
and its sensors are not confirmed wired (see the IO section), so only the
left gripper actually works. Under AND, `GRIP_EXTENDING` and
`GRIP_RETRACTING` could never be satisfied and every cycle would fault.
Only one plate sensor is confirmed too. This is a deliberate operator
decision to keep the machine producing on one gripper — **not an oversight
to be "fixed"**.

**What it costs you, and it is not small.** With `fbGripSolR` driven again
(it was commented out when the OR went in), a *genuine* failure of one
gripper is now invisible: `GRIP_EXTENDING` advances on either sensor, so the
Sep/Push cycle can run on a plate clamped from one side only. Error 10 / 11
can fire **only when both grippers fail**. So a reported "gripper did not
reach the sensor, machine faulted" means *both* did — the single-gripper case
is silent by construction.

**Restore condition:** put the three ANDs back once `GripSolR` has air, its
two sensors are confirmed, and the second plate sensor is confirmed. Until
then, treat grip position as unverified in any fault analysis.

A 17th sentinel value **MANUAL (30)** exists in the enum but is never
assigned to `eStep`. `MAIN` reports it to the robot as `nStateOut = 30`
while `bAutoMode = FALSE` — the enum is the shared vocabulary between
PLC and robot, so this sentinel lives there rather than as a magic INT.
`NOT_HOMED (40)` by contrast *is* a real assigned state, and sits in the same
"not a sequence step" numeric class as 30 and 99.

**Every state resets its commands first (2026-08-05).** Each branch of Section 4
calls the new `ResetAllCommands` METHOD — 20 call sites — and then re-asserts
only the commands it owns. Before that, eight of sixteen states cleared the full
Sep/Push set and the rest inherited FALSE from whichever state ran previously, so
reading one branch in isolation could not tell you what the coils were doing.
Behaviour is unchanged, and `scripts/pb_test/cycle_trace.py` is what
demonstrates that rather than asserting it: it runs a complete bulb with all
eight pistons emulated and checks the coil pattern of all ten cycle states.

It clears **commands, not coils** — `FB_SolSpringPiston_2Pos` retains its coil
when no command branch matches, so clearing mid-stroke HOLDS the piston rather
than dropping it. That is exactly why each state must re-assert what it wants
every scan.

**The defensive `CASE ELSE` now lands on `NOT_HOMED`, not `IDLE` (2026-08-05).**
It used to snap any unhandled `eStep` to `IDLE` — wire value 0, the one value
that makes the robot send `CMD:1` — with the pistons in unknown positions.
Reachable, because `GVL_HMI` carries `TcHmiSymbol.AddSymbol` so `eStep` is
ADS-writable, and `WAIT_POS2 (2)` is a declared enumerator with no branch.

**Error codes** (`ST_HmiMasterAuto.iErrorCode : INT`, 0 = OK):

| Code | Meaning                            |
|------|------------------------------------|
| 0    | OK                                 |
| 1    | SEP_EXTENDING timeout              |
| 3    | PUSH_EXTENDING timeout             |
| 4    | PUSH_RETRACTING timeout            |
| 5    | SEP_RETRACTING timeout             |
| 6    | INIT_PUSH_RETRACTING timeout       |
| 7    | INIT_SEP_RETRACTING timeout        |
| 8    | INIT_GRIP_RETRACTING timeout       |
| 9    | CHECK_PLATE timeout (plate not present) — suppressed by `bBypassPlateSensors` |
| 10   | GRIP_EXTENDING timeout             |
| 11   | GRIP_RETRACTING timeout            |
| 12   | RECOVER_PUSH_RETR timeout — recovery, deliberately distinct from 6 |
| 13   | RECOVER_SEP_RETR timeout — distinct from 7 |
| 14   | RECOVER_GRIP_RETR timeout — distinct from 8 |
| 99   | **RETIRED** — was "Operator STOP while running". STOP now disarms to `NOT_HOMED` instead of faulting. Do not reuse the number: old log entries and CSV exports still carry it. |

(Code 2 was the retired `WAIT_POS2` timeout.)

**Master sensorless mode** (`stMasterAutoCfg.bNoSensors`, default FALSE) —
mirrors the per-piston `bNoSensors`. When TRUE, the **twelve** movement states
(both INIT sets, the three RECOVER states, both GRIP states, all 4 Sep/Push
states) ignore sensor feedback and advance when `tStepTimeoutMs` expires — the
timeout doubles as the fixed step duration, so error codes
**1/3/4/5/6/7/8/10/11/12/13/14 all become unreachable** while sensorless. Note
the doc used to say "the 4 movement states"; it was nine before the RECOVER
chain and is twelve now. Every bench run so far has had this flag set, which is
why no movement-timeout path has ever been exercised — see FLD6. `CHECK_PLATE` uses its own `tPlateWaitTimeoutMs`
and still requires both plate sensors TRUE (bNoSensors doesn't skip the
plate gate). Panel checkbox "No sensors (timed steps)" is the third
checkbox on `AutoMain.TcVIS` at (20,335), bound to `stCfg.bNoSensors`
— added 2026-07-26 by `scripts/add_nosensors_checkbox.py`, which clones the
existing "Auto Mode" checkbox block rather than authoring one. **Use that
cloning approach for any further classic-VISU element** — these files use
numeric-ID serialization and XAE silently drops elements it cannot parse,
so always open the page in TcXaeShell and confirm the element renders
before activating.

## PERSISTENT DATA: nothing was ever written to disk (2026-07-27)

An operator-edited `tPlateWaitTimeoutMs` reverted to its default after a
power cycle. `GVL_HmiPersistent` was correctly declared `VAR_GLOBAL
PERSISTENT` — the bug was that **`PERSISTENT` declares a durable storage
class, not an automatic save**. TwinCAT flushes RAM to
`Port_851.bootdata` on exactly three triggers:

| Trigger | Was it happening? |
|---|---|
| Clean PLC stop | No — cutting power to the CP6606 is not a clean stop |
| `FB_WritePersistentData` from PLC code | No — never called; `Tc2_Utilities` was not even referenced |
| TcXaeShell → *PLC → Save persistent data* | Manual, operator-only |

So every edit lived in RAM only and was lost on power-down; on restart the
declared defaults reloaded.

**Fix — `FB_PersistentAutoSave` (`PLC1/POUs/`), called last in `MAIN`.**
Watches all nine structs in `GVL_HmiPersistent` and flushes ~2 s after the
operator stops editing. Debounced rather than write-on-change because the
panel boots from Compact Flash — one edit of a 5-digit timeout would
otherwise be five writes.

It keeps **two** shadow sets, which is what makes "stopped editing"
detectable at all:
- `shSaved` — what we believe reached disk, refreshed only after a
  *successful* write. A difference means a flush is owed. After a failed
  write it is deliberately left alone, so the retry happens naturally.
- `shSeen` — what we saw last scan, refreshed every scan. A difference
  means the value changed *this* scan.

The quiet timer runs only while `dirty AND NOT changing`, so it restarts on
every keystroke. Comparison is `MEMCMP` because IEC has no struct `<>`.
Completion is the falling edge of `BUSY` — `FB_WritePersistentData` has no
`DONE` output. Each flush logs to `GVL_Log` (so it shows on the Logs page)
and a failure logs at ERR severity rather than failing silently.

**The safety half of this fix — do not remove one without the other.**
Making persistence work also makes the `stMasterAutoCfg` BOOLs survive a
power cycle. `MAIN` section 0 is a one-shot cold-boot block that clears
exactly one of them, and the split is deliberate:

- **`bContinuous` is cleared.** It *used* to be load-bearing: the IDLE branch
  tested it as a **level**, so a persisted TRUE would drive pistons within one
  scan of power-up with nothing external gating it.

  **Corrected 2026-08-04 — that is no longer true.** The arming-model change of
  2026-07-29 removed `stCfg.bContinuous` from IDLE's exit condition (see the
  ARMING MODEL section, which says so). Verified against the source: the FB
  **writes `bContinuous` ten times and reads it zero times** — there is no
  surviving code path by which it can start anything. The clear in MAIN section 0
  is now belt-and-braces rather than a safety interlock. Keep it (it costs one
  line and stops the field drifting TRUE for a future reader), but do not cite
  it as the thing preventing power-up motion — **`eStep`'s `NOT_HOMED` default
  is** what does that now.

- **`bAutoMode` is kept** (operator decision, 2026-07-27; the first version
  cleared it and that was wrong). The machine returns to Automatic and still
  needs a real start trigger.

  **Superseded 2026-07-29 — read this if you are chasing power-up behaviour.**
  This bullet used to end: *"in Auto the panel reports `nStateOut = 0` (IDLE),
  so a robot already running can request a cycle straight after power-up. That
  is the intended production behaviour."* It is no longer intended and no longer
  possible. `eStep` now defaults to **`NOT_HOMED (40)`**, so a persisted
  `bAutoMode = TRUE` brings the panel back in Automatic but **un-armed**,
  reporting 40 — which the robot answers `CMD:0`. An operator START is required
  before any motion. `bAutoMode` still persists; it is the *arming* that does
  not. See the ARMING MODEL section.

- The timers, `bNoSensors` and `bBypassPlateSensors` are not cleared either.
  They are operator config and persisting them is the point. Worth knowing
  that a bench flag left on now survives a reboot.

**`GVL_Robot` has its own persistent block (2026-07-27).** `sRobotHost` /
`nRobotPort` are commissioning values — the test for configuration is *"does
the correct value differ between installations?"*, not *"does it reset on
boot?"*. As plain `VAR_GLOBAL` they were re-applied from their literals on
every Activate Configuration, download and reset, silently discarding
whatever was typed on the Robot page, and **nothing reported an error**: the
write succeeded, the field really did change, and it really was reverted.

They are declared in a second block inside `GVL_Robot` rather than moved into
`GVL_HmiPersistent`, so the symbol paths `GVL_Robot.sRobotHost` /
`.nRobotPort` are unchanged — a GVL may hold both a volatile and a persistent
block. `FB_PersistentAutoSave` watches them explicitly (plain `<>`; they are
scalars, not structs). `bTcpEnable` stays volatile on purpose: a link
disabled for a bench session should come back enabled rather than leaving the
robot unreachable for no visible reason.

`FB_RobotTcpClient` now tears down a live session when the endpoint changes.
The connect call reads `sRemoteHost` once, so without that an edited IP would
sit in the field doing nothing until the socket happened to drop — the field
would look broken. The retarget routes through the same `Error`
close-and-retry path the disable request uses, and is baselined on the first
scan so it cannot force a pointless reconnect at startup.

The VISU field is a clone of the page's own editable numeric field with the
format set to `%s` and `InputBoxMin`/`InputBoxMax` **cleared** (numeric
bounds are meaningless on a STRING). `InputType` stays `"Default"`, which
derives the dialog from the bound variable's type — that is why a STRING gets
the alphanumeric keypad and no new element type had to be authored in the
IDE. Built by `scripts/add_robot_ip_field.py`.

That hazard was previously masked purely by persistence being broken. The
general rule: **`GVL_HmiPersistent` mixes tunables with runtime state, so
any new field there needs a decision — carry across a power cycle, or clear
in MAIN's cold-boot block.** `GVL_HMI` is plain `VAR_GLOBAL`, so piston
runtime and momentary commands are unaffected.

## CONTINUOUS DISABLED + STATUS LAMPS (2026-07-27)

**Continuous is off on the real machine.** Every cycle is started by the
operator or by the robot's `CMD:1`, so the checkbox was removed from
`AutoMain` (`scripts/remove_continuous_checkbox.py`; the remaining three
shifted up 40 px to close the gap) and `MAIN` section 0 forces
`stMasterAutoCfg.bContinuous := FALSE` **every scan**.

Forcing rather than merely deleting the control matters: a VISU page is one
of several writers. **FlowerPyHmi has its own Continuous checkbox on
`main.html` and `manual_control.html`** and writes the field over ADS.
Removing the panel checkbox alone would have hidden the control while
leaving the behaviour reachable. Consequence to be aware of: those
FlowerPyHmi checkboxes now visibly revert when ticked — worth removing there
too, but that is a separate repo.

The field is kept rather than deleted from `ST_HmiMasterAutoCfg` because
`FB_MasterAutoCycle` clears it on all ten ERR entries plus the STOP path, and
FlowerPyHmi polls it; forcing is the smaller, safer change.

**Status lamps — DO 12 green / DO 13 red.** Unlike the PB LEDs (dumb press
mirrors), these report machine state, driven by `MAIN` from the master
cycle:

| Lamp | DO | Behaviour |
|---|---|---|
| RED | `dOut[13]` | On while the master cycle is latched in `ERR`. |
| GREEN | `dOut[12]` | Auto + IDLE → steady. Auto + cycling → blink (400 ms on / 400 ms off). Manual, or ERR → off. |

Green is off in ERR so the two lamps cannot contradict each other — red lit
alongside green would read as "faulted but running". Green is off in Manual
because it means "the automatic cycle is live", which is exactly what Manual
is not.

The blink source is a self-resetting `TON` **toggling a BOOL**, not
`tonBlink.Q` directly: the bare `TON` pulses for a single scan per period,
which would be invisible rather than a blink.

## ROBOT CMD:1 DEADLOCK — found on the real machine (2026-07-28)

The robot issued `CMD:1`, the panel received it (`stRobot.sLastMessage` read
`CMD:1`, Rx/Tx counters climbing normally), the master cycle sat in Auto +
IDLE — and no cycle started, permanently.

**Root cause: a rising-edge trigger on a field that only the far end could
reset.** MAIN had `fbTrigRobotStart : R_TRIG` on `stParams.nRobotCmd = 1`,
and *nothing on the PLC side ever wrote `nRobotCmd`* — the protocol left
zeroing to the robot, which only zeroes once it sees the PLC leave IDLE via
a `STATE:<n>` push. So:

1. A `CMD:1` arrives while the panel is in Manual, or latched in `ERR`. The
   R_TRIG fires, `FB_MasterAutoCycle`'s IDLE branch correctly refuses it
   (gated on `bMachineAuto`; `ERR` is not `IDLE`). The pulse is discarded.
2. `nRobotCmd` stays at **1** forever.
3. The operator returns the machine to Auto/IDLE. The robot re-asserts
   `CMD:1` on every keep-alive reply — but re-sending a value that is
   *already* 1 produces **no rising edge**.
4. Deadlock: the robot waits for a state change, the PLC waits for an edge
   that cannot come. Nothing anywhere reports a fault.

**Fix — MAIN consumes the level and clears it** (`bRobotStartPulse`; the two
`R_TRIG`s are gone). The PLC's clear *is* the acknowledgement; the robot's
own zeroing became belt-and-braces. A request that cannot be honoured this
scan is dropped and the robot's next keep-alive re-asserts it ~1 s later —
self-healing instead of one-shot. Repeat pulses are harmless: only the IDLE
branch consumes `bExtStartPulse`, and it is gated on `bMachineAuto`.

**Consequence for diagnostics:** `nRobotCmd` now reads 0 almost always,
because it is consumed within a scan. The trace of a robot-initiated start
is the **`External start pulse` entry on the Logs page**; `sLastMessage`
still shows the raw `CMD:1` frame. That log entry is the decisive evidence
for this class of fault — present means the pulse fired and the FB refused
it (check `bAutoMode`), absent means the pulse never fired.

**Second defect fixed at the same time — `ParseCmd`.** The old parse was
`FIND(sRxMsg,'CMD:') = 1` plus `MID(sRxMsg, LEN(sRxMsg) - 4, 5)`, which
required the reply to be *exactly* `'CMD:'` + digits. The robot's Lua loop
writes on a 100 ms tick while the PLC reads once per round-trip, so two
replies can coalesce into one receive (`'CMD:0CMD:1'`) — the old MID window
straddled the boundary and `STRING_TO_INT` returned **0**, silently eating a
start request. `ParseCmd` now searches for the **last** `'CMD:'` and reads
exactly one validated digit, so coalesced frames, trailing whitespace and
stray newlines are all tolerated and the newest command wins.

`ParseCmd` returns `INT`: the command value, or **−1 when the reply carries no
usable CMD frame**. −1 rather than 0 because `CMD:0` (withdraw) is itself a
valid command, so "no frame" and "frame saying zero" have to stay
distinguishable — `HandleReply` writes `stParams.nRobotCmd` only when the
result is ≥ 0, which is what stops an `OK: SET ...` ACK or a `SYNC` reply from
clobbering a command MAIN has not consumed yet. The write lives in
`HandleReply` rather than inside `ParseCmd` so it sits next to the logging
that reports it.

**Note on the robot side.** `Robot/167-01-Saad/src2.lua` as committed has
**no `STATE`/`CMD` handling at all** — its generic `NAME:VALUE` branch
swallows `STATE:0` (it contains a colon) and answers `OK: SET STATE`, so the
command channel is one-way dead against that revision. The same is true of
the reference `dummy_server.py:73`. The machine runs a newer, **uncommitted**
`src2.lua` that does emit `CMD:1`. Commit it — the PLC-side protocol has no
counterpart in version control otherwise.

**Verified on the machine 2026-07-28:** built, downloaded, robot start works;
the Manual→Auto and ERR→RESET recovery tests both pass.

## ARMING MODEL: operator arms, robot runs bulbs (2026-07-29)

Commissioning showed the old start model did not match how the cell runs. **Any**
trigger — operator START, robot `CMD:1`, PB1, a stale `bContinuous` — ran the
whole bulb cycle, and `RESET` from `ERR` dropped straight to `IDLE`. Three
consequences:

- **Power-up could move the machine.** `bAutoMode` persists, so the panel booted
  into Auto reporting `STATE:0`; a running robot read that as "ready" and could
  command a cycle with the pistons anywhere and no operator present.
- **`RESET` was a start button.** Once the `CMD:1` deadlock was fixed, a robot
  holding a start request got it honoured ~1 s after the operator cleared a
  fault — the operator who may have just cleared a jam by hand.
- **Operator `STOP` self-recovered.** STOP latched `ERR 99`, the robot saw
  `STATE:99`, sent `CMD:2`, and the machine restarted itself within seconds.

Note the second and third only became reachable *because* the deadlock fix
worked. The latch bug had been masking them.

**The model now:**

| Trigger | Means | Valid from |
|---|---|---|
| operator START — `stHmi.bStart`, HMI button or green PB3 in Auto | home the pistons and **arm** | `NOT_HOMED` only — ignored in `IDLE` since 2026-08-05 |
| robot `CMD:1` — `bExtStartPulse` | run **one bulb cycle** | `IDLE` only |

So the machine cannot move after power-up, after Manual, or after a STOP until a
human presses START; and once armed, only the robot decides when a bulb runs.

**What makes each half true, mechanically:**

- **`NOT_HOMED (40)`** is a real assigned state, and `stHmi.eStep`'s *declared
  default*. `GVL_HMI` is plain `VAR_GLOBAL`, so that initialiser is re-applied on
  every cold boot and every download — no MAIN-side one-shot needed. It reports
  40, which the robot answers `CMD:0`.
- **`IDLE`'s exit condition dropped `fbTrigStart.Q` and `stCfg.bContinuous`.**
  That is the load-bearing edit: it removes every path by which a bulb can start
  without the robot. `bContinuous` is still force-cleared in MAIN section 0 and
  is now simply never consulted.
- **Manual parks in `NOT_HOMED`, not `IDLE`.** That *is* the implementation of
  "returning from Manual needs a START" — no edge detection anywhere, the state
  is already un-armed when Auto comes back.
- **`bHomeThenIdle`** picks which exit the shared `INIT_*` retract chain takes:
  `IDLE` when homing, `CHECK_PLATE` when it is the front of a bulb cycle. Set by
  whoever *enters* the chain, never from inside it — the three INIT states are
  shared and must not care which caller they serve.
- **STOP disarms rather than faults.** Error code 99 is retired. STOP now goes to
  `NOT_HOMED`, so the robot is told "wait" instead of "fault" and never tries to
  reset it. This also restores `ERR` to meaning *something went wrong* rather
  than *someone intervened*. STOP fires from `IDLE` too, giving the operator an
  explicit disarm.
- **RESET homes instead of jumping to `IDLE`.** A fault leaves the pistons in
  unknown positions, so `IDLE` would advertise "ready" while it is not.

**Error recovery is now entirely robot-driven and needs no operator:**
`ERR` → `STATE:99` → robot `CMD:2` → PLC clears the error and homes →
`STATE:0` → robot `CMD:1` → next bulb.

**The robot only ever acts on three values** — 0 (armed), 99 (faulted),
everything else (wait). So `NOT_HOMED = 40` needs **no new branch** robot-side;
it lands in the existing "wait". `dummy_server.py` implements exactly this
contract and is the reference for the real `src2.lua`.

`scripts/test_master_cycle_arming.py` ports Sections 2 and 4 of the FB and
asserts the arming transitions — 15 cases including "robot cannot start an
un-armed machine", "START never runs a bulb cycle", "STOP survives a robot still
asking", and "RESET does not jump to IDLE". Sensors are modelled as satisfied on
the next scan (the `bNoSensors` bench case), so it tests *which state comes
next*, not timing. Run `python scripts/test_master_cycle_arming.py`.

## ROBOT COMMS LOGGING (merged 2026-07-28)

`FB_RobotTcpClient` logged nothing; a dropped link left the Robot page reading
`Disconnected` with no record of when or why, and `sLastMessage` holds exactly
one frame — overwritten within a second by the 1 Hz keep-alive.

Lifecycle and protocol events now log at INFO/WARN/ERR; raw frames log at DBG,
which `F_LogEvent` drops unless `GVL_Log.bDebugMode` is set. Production stays
readable and ticking Debug turns the FB into a protocol tracer. New `Fail()`
method centralises teardown — six sites assigned `eState := Error` and none
said why; `eSev` is a parameter because two callers (operator clearing
`bTcpEnable`, endpoint retarget) reuse that close-and-redial path on purpose
and are not faults.

Three suppressions are deliberate, because the panel ring is only 20 entries
deep and a log that records everything is useless:

- The 1 Hz STATE keep-alive and its idle `CMD:0` reply are **not** traced. A
  state *change* is; its identical repeat is not. `SendState` takes
  `bKeepAlive` from its two call sites rather than deriving it, which would
  mean reading `nLastStateSent` after the method already overwrote it.
- Unanswered STATE is **edge**-logged (`bStateUnanswered`). A wedged robot
  leaves the socket open and the keep-alive re-fires every second, so a
  level-logged WARN would flush the ring in 20 seconds and hide the cause.
  One WARN in, one INFO out.
- Commands log **on change** (`nLastCmdLogged`), so a command repeated across
  replies is one entry. Note this is independent of MAIN's level-consume: the
  robot repeating `CMD:1` is now *acted on* every time but *logged* once.
  `CMD:0` re-baselines without logging, so a genuine repeat after an
  intervening zero still reports.

`bTraceTx` ordering is load-bearing: `StartSend` sets it TRUE for every frame
and `SendState` overrides it to FALSE for a keep-alive **after** calling
`StartSend`. The override must come second to win, and `StartSend` must set it
or a keep-alive's FALSE would leak into the next real frame and hide it.

Clamp logging happens **before** `ClampParam`'s write-back — the only moment
the operator's original value still exists anywhere.

## PLATE SENSORS: status on Main + bypass (2026-07-26)

**Status.** `Main.TcVIS` shows both plate sensors in the 110 px strip to the
right of the embedded AutoMain frame (which spans x −4…684): a "Plate" title
with `L` / `R` lamps at x=724, bound to `GVL_HMI.bPlateSenL` / `bPlateSenR`
(MAIN's mirror of `GVL_App.bPlateSen*`). On the home screen, so the operator
can see plate presence without opening a page.
Built by `scripts/add_main_plate_status.py`.

**Bypass.** `stCfg.bBypassPlateSensors` (default FALSE, 4th checkbox on
AutoMain at (20,375)). It removes **only the CHECK_PLATE timeout error**, not
the wait:

- the `bPlateSenL AND bPlateSenR` fast-path still advances the cycle, so
  with healthy sensors behaviour is completely unchanged;
- with unwired or faulty sensors, `tPlateWaitTimeoutMs` degrades into a
  fixed placement dwell and the cycle continues instead of raising error 9.

That shape was chosen over "ignore the sensors entirely" because the robot
still needs time to place the plate — a bypass that advanced instantly would
close the grippers on nothing.

It is deliberately **separate from `bNoSensors`**, which by long-standing
decision does not cover `CHECK_PLATE`. Skipping the plate gate is
safety-relevant and should be an explicit choice, not something inherited
from a bench-testing flag.

**Per-step simulate flags** on `ST_HmiMasterAuto.bSimStep_*` let a bench
operator advance any waiting step without physical sensors — rising-edge
triggered, FB auto-clears after consumption. `UC_MasterAutoCycle` renders
them as a vertical table (one row per state in chronological run order),
background highlights yellow when `eStep` matches the row's enum value,
red for the ERR row.

**External start pulse.** MAIN tests `stParams.nRobotCmd = 1` as a level,
clears the field, and feeds a one-scan `bRobotStartPulse` into
FB_MasterAutoCycle's `bExtStartPulse` VAR_INPUT. HMI checkbox "Sim bStartAssembly"
binds `ST_HmiMasterAuto.bSimStartAssembly` (TwoWay) — a bench sim flag consumed
by the FB's own R_TRIG and OR-merged inside the IDLE exit condition alongside the
external pulse. **The operator's START button is no longer in that condition**
(2026-07-29): START means "home and arm", so `bSimStartAssembly` is now the only
way to simulate a robot cycle start from the panel. The physical Start button is
**PB3** (green), and it drives `bStart`, not `bSimStartAssembly`.

**Logging.** `F_LogEvent` fires on every state transition (INFO for
normal `PREV -> NEW`, ERR for entries into ERR with `sMsg = sErrorText`),
on operator START/STOP/RESET edges, on Sim start edges, and on external
start pulses. `sSource = stHmi.Name`. Bench sim step advances are not
logged (would spam production).

## DECISION: per-piston auto tiles + sensorless mode

Every piston (SepSol1..3, PushSol1..3) has its own `FB_PistonAutoCycle`
instance in MAIN and a dedicated tile on `StartPage.content` (3×2 grid,
337×340 tiles: Sep row on top, Push row on bottom). Each tile binds to
`GVL_HMI.stXxxAuto` (runtime state) and `GVL_HmiPersistent.stXxxAutoCfg`
(PERSISTENT config). Callers wire each auto FB's `bCmdExtend` /
`bCmdRetract` outputs into the piston FB's `bAutoCmd*` inputs OR-merged
with `fbMasterAutoCycle.bXxxCmd*[i]`, so both the per-piston tile and
the master sequence can drive the same piston without stepping on each
other.

**Sensorless mode** (`ST_HmiPistonAutoCfg.bNoSensors`, default FALSE):
- FALSE — standard sensor-driven behavior. `tTimeoutExtendMs` /
  `tTimeoutRetractMs` are timeouts; expiry raises an error.
- TRUE — the state machine ignores sensor feedback and advances on
  timer expiry. Same fields become fixed extend/retract *durations*
  (relabelled in the UC as "Extend time (ms)" / "Retract time (ms)"). No
  feedback-mismatch check, no "sensor never arrived" error path. Use for
  bench cycling on pistons whose proximity switches aren't wired.

## DECISION: PLC is the TCP client; robot is the server

The robot comms live in `FB_RobotTcpClient` (`Panel_PLC_HMI/…/PLC1/POUs/`)
which uses the free-with-TF6310 `Tc2_TcpIp` library to dial the robot at
`GVL_Robot.sRobotHost:nRobotPort` (default `192.168.1.11:6001`). TF6310
is installed+running on the CP6606 — this is the documented exception
to the avoid-paid-libs rule (see project memory
`feedback_avoid_licensed_beckhoff_libs.md`).

The former Python bridge (`RobotBridge/`) is out of scope for the panel
solution because Windows Embedded Compact 7 on ARM has no supported
CPython+pyads. Kept only as protocol reference
(`Client_working_example/tcp client.py` and `dummy_server.py`).

Connection semantics:
- Persistent socket (one open TCP connection while up).
- 2-second timeout on connect / send / recv (per Tc2_TcpIp).
- On any error → close socket → wait 3 s → re-dial. Repeats forever
  while `bTcpEnable = TRUE`.
- `STATE:<n>` keep-alive every ~1 s serves the "is the socket alive?"
  role that a bare HEARTBEAT used to fill.

## PANEL VISU: page inventory + the numeric-entry constraint (2026-07-26)

Seven classic VISU pages, all registered in `PLC1.plcproj` with a
`<Compile Include>` + `<DependentUpon>VISU\VisualizationManager.TcVMO</...>`
block (a new `.TcVIS` is invisible to the build without one):

| Page | Contents | Reached from |
|---|---|---|
| `Main` | AutoMain embedded as a frame + 4 nav buttons + plate lamps | — |
| `AutoMain` | title, step/error fields, START/STOP/RESET, 3 checkboxes, 5 timers | embedded in Main |
| `PistonsManual` | 6 Piston frames (Sep/Push 1-3) | Main |
| `GripperManual` | 2 Piston frames (`stGripSolL` / `stGripSolR`) | Main |
| `Robot` | conn state, Rx/Tx counts, last Rx/Tx, nStateOut, nRobotCmd, Get Sync + New Bulb buttons, 11 tuning params, editable Robot IP | Main |
| `Logs` | 20 newest entries (Sev/Time/Message), Enabled + Debug checkboxes, write counter | Main |
| `Piston` | the reusable per-piston control, instanced via frames | — |

Each page's `<Visu Id>` GUID equals every `VisualElementOwningObjectGuid`
inside it — hold that invariant when cloning a page.

**A page name is an IEC identifier.** The compiler generates an FB and a
`<Page>__inp__vis` type from it, so it must not collide with a standard
function. The Logs page was first called `Log` and failed to compile with
`Identifier expected instead of "Log"` — `LOG` is an IEC 61131-3 standard
function (with `LN`, `EXP`, `ABS`, `SQRT`, `SEL`, `MUX`, `LEN`, `LEFT`,
`MID`, `FIND`).

**The same trap applies to ORDINARY VARIABLES, and the trig family is the one
that gets forgotten.** IEC identifiers are **case-insensitive**, so a parameter
named `sIn` *is* `SIN`. `FB_LogCsvWriter.Csv()` took one on 2026-08-10 and cost a
build cycle — and the diagnosis is actively misleading, because the compiler
blames every **call site** rather than the declaration:

```
'SIN' needs exactly '1' Operands
'(' expected instead of ':='
Unexpected Token 'sIn' found
```

Add `SIN COS TAN ASIN ACOS ATAN EXPT MIN MAX LIMIT TRUNC ROUND ADR SIZEOF
CONCAT INSERT DELETE REPLACE` to the list above and treat it as non-exhaustive.

**`python scripts/check_iec_names.py` is the guard** — it inspects only the
left-hand side of declarations plus POU/DUT/GVL/method names, so legitimate
*calls* to `LEN()` or `MID()` are ignored while a variable *named* `LEN` is
reported. Currently 513 declarations across 32 files, clean. Negative-tested by
reintroducing `sIn` and confirming it reports. Run it before a build rather than
after one — a grep cannot do this job, because these names appear all over the
code as calls. The *displayed* label is unconstrained: the page is named
`Logs` and its title and nav button both read "Log".

**Cloning a page copies a second identity layer — fixed 2026-07-27.**
Besides its elements, every page carries ~60 GUIDs naming the objects the
compiler generates for it: `VisuRegDesc.FbGuid`, `InputsPou.FbGuid` (this one
*becomes* `<Page>__inp__vis`), one GUID per generated method, the generated
GVLs, `VisuRegisterGvl`, `DialogDut`. `GripperManual` was cloned from
`PistonsManual` and duplicated all 61 of them; because the **first** `FbGuid`
happens to equal `<Visu Id>`, the page-GUID rewrite fixed exactly one and the
diff looked complete. Two visualizations then registered the same input POU
and the build failed with

```
Unknown type: 'PistonsManual__inp__vis'
```

— naming `PistonsManual`, which had not been touched since `f8ad512`. The
page rendered fine throughout, so only a build catches this.

The invariant, confirmed against the pristine IDE-authored pages: **outside
`<TypeList>`, no GUID is shared by any two `.TcVIS` files** — not one is
project-global (`<TypeList>` is the exception; it references VisualElem
plugin types that *are* identical everywhere). `scripts/validate_visu.py`
now enforces it, and `scripts/fix_visu_object_guids.py` re-issues a clone's
copies (uuid5-derived, so idempotent — rewrite the **clone**, never the
original).

**`Logs` page (2026-07-27, `scripts/build_log_page.py`).** 69 elements: a
20-row × 3-column grid over `GVL_Log.aRecent[0..19]` (`sSevText` / `sTime` /
`sMsg`), newest first — `F_LogEvent` shifts the slots down and writes
`aRecent[0]` on every accepted call, so the page needs no PLC-side work and
costs nothing per scan. Rows are display-only (asserted: no
`InputBoxInputAction` on any of the 60). Chrome: `bLogEnabled` and
`bDebugMode` checkboxes, an `nWriteIdx` counter, and a Main nav button; the
nav button *to* it sits at x=63 on Main's y=417 row.

**The Sev column binds `sSevText`, never the enum.** `{attribute 'to_string'}`
on `E_LogSev` makes `TO_STRING()` available **in ST only** — it does not make
the classic VISU text output resolve an enum to its enumerator name. Binding
`aRecent[i].eSev` renders `0`/`1`/`2`/`3`. This was assumed the other way
round and shipped wrong twice before being fixed on 2026-07-27; treat "the
classic VISU cannot stringify an enum" as settled, and note that it is why
every other page here carries a STRING mirror (`sStepText`, `sErrorText`).

So `ST_LogEntry` gained `sSevText : STRING(8)`, set by `F_LogEvent` via
`TO_STRING(eSev)` into both rings. `STRING(8)` rather than an exactly-sized
`STRING(4)` so a future severity name cannot truncate silently. `F_LogEvent`
needed no change to its shift loop — `aRecent[k] := aRecent[k-1]` copies whole
structs, so the new member rides along.

Widening `ST_LogEntry` turned out to be safe for FlowerPyHmi: it reads the
ring *per-field by symbol name* (`plc_log.py:29-31`), not as a packed struct,
so no symbol was removed — `check_pyhmi_contract.py` still resolved 229/229 at
the time (231/231 since the PB hold timers landed 2026-08-05).
It also keeps its own `SEV_NAMES` map and renders from `eSev`, so the 0..3 →
name mapping now exists in two places. Left that way deliberately: Python has
no need of the PLC's string, and coupling it would buy nothing.

Retarget script: `scripts/fix_logs_sev_column.py` (idempotent; asserts it
rewrote exactly 20 cells and left the other columns untouched).

**Time replaced Source in the middle column (2026-07-27).** `ST_LogEntry`
carried an explicit comment saying it deliberately had *no* timestamp,
because "Python assigns wall-clock time when it drains the ring". True, but
that only ever covered FlowerPyHmi — the panel has no drainer, so the page
had no way to show *when*. `sTime : STRING(8)` is now stamped by `F_LogEvent`
from `GVL_Log.sNow`.

`sNow` is refreshed by `MAIN` section 0a from
`Tc2_Utilities.FB_LocalSystemTime` (`dwCycle := 1`), rebuilt only when the
second rolls over. It lives in the GVL rather than inside `F_LogEvent`
because **a FUNCTION cannot own an FB instance** — functions are stateless,
so the cyclic tick has to happen in a POU that has one.

If `bValid` is FALSE the string reads `'--:--:--'` rather than a plausible
wrong time — the panel's RTC being unset should look like an unset clock, not
like events at 00:00:03. **The timestamps are only as good as the panel
RTC.**

`sSource` is untouched in the struct and the ring; FlowerPyHmi still reads
and renders it, and it still reaches the CSV. Only the panel column changed.
Column swap by `scripts/fix_logs_time_column.py`; layout is now Sev 20-80,
Time 84-174, Message 178-780.

**Numeric entry — resolved 2026-07-26.** The project originally had only two
input mechanisms (`Visu_TapInput` → BOOL, and `ChangeVisuInputAction`), so
there was nothing to clone for an editable number. The operator authored one
template in TcXaeShell (`GenElemInst_229` on `Robot`), and all 16 editable
fields are clones of it.

The template is a plain **`VisuFbElemTextfield`** whose `OnMouseClick`
carries an **`InputBoxInputAction`**; `UseTextOutputVariable=true` means it
writes back through the normal displayed-variable member (`2477733581L`).
So a display field and an edit field differ *only* by that action block —
which is exactly why it could not be invented and had to come from the IDE.

- `Robot` — 11 params at x 420-770, `GVL_Robot.stParams.<NAME>` (absolute:
  standalone page).
- `AutoMain` — 5 timers at x 500-780, `stCfg.<name>` (**interface-relative**:
  AutoMain is embedded as a frame in Main and declares
  `stCfg : ST_HmiMasterAutoCfg`; absolute paths would be wrong here).

Build/verify scripts, all idempotent and all cloning proven blocks rather
than authoring them: `scripts/build_grippermanual.py`,
`scripts/build_robot_page.py`, `scripts/add_main_nav.py`,
`scripts/add_nosensors_checkbox.py`, `scripts/build_log_page.py`,
`scripts/fix_visu_object_guids.py`, and
`scripts/validate_visu.py` (**run this after every VISU edit** — it asserts
each element is a direct child of `VisualElementList` and that no GUID is
shared between two pages, neither of which XML well-formedness gives you).

Static label text lives in `GlobalTextList.TcGTLO`, keyed by each element's
counter member `823443203L`. The scripts register their own entries; XAE
also adds missing ones on first open.


## PANEL HARDWARE: 3 push buttons + 3 LEDs (2026-07-26)

Three momentary-contact push buttons with integrated LEDs are wired to
the panel's DI/DO. Behaviour is gated by `bAutoMode`:

Button colours matter to the assignment: **PB1 red, PB2 orange, PB3 green.**

| PB | DI | LED (DO) | In Automatic | In Manual |
|---|---|---|---|---|
| PB1 | dIn[13] | dOut[7] | **Held `tPbStopHoldMs`** (default 1000 ms) → STOP: writes `stMasterAuto.bStop`, disarming to `NOT_HOMED`. LED1 **blinks** while the hold counts. | **Momentary**: held → both grip pistons extend, released → they retract. |
| PB2 | dIn[14] | dOut[8] | In `ERR`: **RESET** (rising edge → `bReset`). Otherwise: the other half of the start combo. | **Momentary**: held → all 3 SepSol pistons extend, released → they retract. |
| PB3 | dIn[15] | dOut[9] | **Operator START** — rising edge writes `stMasterAuto.bStart`, i.e. "home the pistons and arm". Green button for the go-ahead. | **Momentary**: held → all 3 PushSol pistons extend, released → they retract. |
| PB2 **+** PB3 | — | — | **Held `tPbStartHoldMs`** (default 1000 ms) from `IDLE` → run **one bulb**. The operator's parallel to the robot's `CMD:1`, OR-merged into the same `bExtStartPulse` input. | — |

**Why two of them are holds and not edges (2026-08-05).** Both are
consequential — one stops the machine, one starts a bulb — and a multi-second
hold cannot be triggered by a knock or a brushed sleeve the way an edge can.
Each `TON`'s `IN` *is* the gesture, so releasing the button resets the elapsed
time; `.Q` is a level, so each is edge-detected to fire once per press. Both
durations live in `stMasterAutoCfg` and are editable on `AutoMain` (rows y=375
and y=415, added by `scripts/add_automain_pb_timers.py`).

**BUTTON ORDER NO LONGER MATTERS — and removing the reason is why.** Until
2026-08-05, `START` in `IDLE` re-homed and came back. Pressing GREEN before
ORANGE therefore fired a START, and the combo's one-scan `bExtStartPulse` could
land while `eStep` was mid `INIT_*` chain — where **nothing consumes it** — so
the bulb request was **silently dropped**. Measured on the PLC: with homing
slowed to 2.33 s against a 1 s hold, the chain was `IDLE → INIT_* → IDLE` and no
cycle ran.

`START` in `IDLE` is now **ignored**, so a stray green press cannot move the
machine out of `IDLE` and the pulse always lands where something consumes it.
Either order works. `pb_test` `G5` is the regression guard.

MAIN still suppresses the standalone START edge while PB2 is held
(`AND NOT GVL_App.bPb2`). That is now only about keeping the log clean — one
combo press, no spurious `START pressed` entry.

**NO manual jog in ANY Automatic state (operator decision, 2026-08-05).** An
`ERR` jog window shipped on 2026-08-04 and was removed the next day: manual
moves belong in Manual mode. The `bJogEnable` input is gone from
`FB_SolSpringPiston_2Pos`, `bErrJogEnable` is gone from `MAIN`, and all eight
call sites are back to `bJogExtend := bManualMode AND GVL_App.bPbN`. The three
jog branches in the piston ladder are gated on `eMode = Manual` alone.

`scripts/test_piston_jog_gate.py` is now the **negative** guard on that removal:
a jog request in Automatic must do nothing, and the release edge must stay gated
off so a mode switch mid-press cannot drop a coil the master cycle owns.
`pb_test` group E does the same against the live PLC.

`scripts/test_piston_jog_gate.py` ports the ladder (Sections 0/1/1a/1c/2) and
asserts the Manual-only gate. Run `python scripts/test_piston_jog_gate.py`.

**End-to-end PB test against a live PLC: `scripts/pb_test/`** (see its README).
57 checks over ADS covering all three buttons in Manual, Auto/`NOT_HOMED`,
Auto/`IDLE`, Auto/`ERR` and recovery; writes `docs/pb-test-report.html`. Ran
57/57 on the local runtime 2026-08-04. Two things to know before using it:

- Presses are simulated by writing **`GVL_IO.dIn[13..15]`**, not
  `GVL_App.bPbN` — `PRG_IoMap.ReadInputs` overwrites the latter every 5 ms.
  This is the general technique for bench-driving any input on a target with
  the EtherCAT device disabled.
- **Transition paths must come from `GVL_Log`, never from polling `eStep`.**
  With retract sensors asserted the homing chain completes in ~3 scans (30 ms),
  faster than ADS can sample, so a poll loop sees only the endpoint. An early
  version of that script reported two false FAILures for exactly this reason.
  `FB_MasterAutoCycle` Section 3 logs every `PREV -> NEW` from inside the scan,
  so the ring is authoritative — with the one exception that entries *into*
  `ERR` log `sErrorText` instead of a transition.

**Know this before relying on it: the robot closes the window in about a
second.** `ERR` → `STATE:99` → robot `CMD:2` → the PLC clears the fault and
homes. In production `ERR` is transient, so the jog is genuinely useful only
with the robot stopped. What actually *holds* a fault open is switching to
**Manual**, where `nStateOut` reports `MANUAL (30)`, the robot answers `CMD:0`,
and `ERR` stays latched (the Manual re-park deliberately excludes `ERR`). If
operator-paced recovery is wanted in production, the `CMD:2` consumption in
`MAIN` needs an acknowledgement gate — not built.

**START moved PB1 → PB3 (2026-07-29)** for two reasons: PB3 is the green
button, and START changed meaning. It drives `bStart` (home + arm), **not**
`bSimStartAssembly` — that flag keeps its own distinct job as the bench
stand-in for the robot's `CMD:1`, so you can still test a bulb cycle without
the mock. PB3 therefore carries two mode-gated roles, exactly as PB1 did.

**PB3's LED is no longer a dumb mirror.** In Automatic it blinks while
`eStep = NOT_HOMED` — a "press me to arm" prompt — and is off otherwise. In
Manual it falls back to the raw press mirror, where PB3 is the Push jog and the
LED keeps its wiring-diagnostic role. PB1/PB2 LEDs stay dumb mirrors in both
modes. It is assigned *after* `bBlink` is refreshed in `MAIN`, not in the PB LED
block, so the blink is this scan's value rather than last scan's.

**PB jog is momentary; the HMI jog is not (2026-07-27).** Section 2 of
`FB_SolSpringPiston_2Pos` retains the coil when no branch matches, so
originally a PB press latched the piston extended and — the panel having no
jog-retract button — the only way back was walking to the HMI. An
`fbTrigJogRelease : F_TRIG` on `bJogExtend` now adds one release branch that
drives the coil FALSE, the single exception to the retain rule.

Its position in the ladder is load-bearing: **after** both jog branches, so a
held `stHmi.bManJogExtend` keeps the coil energised and the one-scan pulse is
ignored; **before** the `bTarget*` branches, so a latched HMI Extend
selection cannot re-energise the coil the moment the operator lets go.

The HMI jog deliberately keeps its latching behaviour — `bManJogRetract` sits
right next to it on the Piston page, so there is no stranding problem there.
Note the release branch is gated on Manual and MAIN forces `eMode` (line 108)
*before* calling the piston FBs, so the pulse produced by a Manual→Auto
switch is correctly ignored and the master cycle's INIT retract states take
the pistons home instead.

LEDs are dumb mirrors of the raw PB press state (`GVL_App.bLedPbN :=
GVL_App.bPbN`) — a wiring / hardware-health diagnostic, not a status
indicator. Room to repurpose later: swap the LED-write source (running,
error latched, TCP connected, etc.) without touching the DI wiring.

PB inputs live in `GVL_App` (not HMI-mapped). `PRG_IoMap.ReadInputs`
copies from `dIn[13..15]`; `PRG_IoMap.WriteOutputs` copies to
`dOut[7..9]`. MAIN's jog OR-merge into piston FBs uses the new
`FB_SolSpringPiston_2Pos.bJogExtend` VAR_INPUT so the HMI-owned
`stHmi.bManJogExtend` field is not mutated by MAIN.

## DECISION: HMI contract lives in any GVL with the `TcHmiSymbol.AddSymbol` pragma

Four GVLs expose symbols to the HMI today: `GVL_HMI`, `GVL_HmiPersistent`,
`GVL_Log`, `GVL_Robot`. Kept split by concern (piston state / persistent
config / diagnostics / robot bridge). The `{attribute 'TcHmiSymbol.AddSymbol'}`
pragma is the searchable marker — grep for it under `PLC1/GVLs/` and you
have the whole PLC↔HMI contract:

```
grep -l "TcHmiSymbol.AddSymbol" Panel_PLC_HMI/167_01_Saad_PLC/167_01_Saad_PLC/PLC1/GVLs/
```

**Rule for new HMI-facing symbols:** put them in the GVL whose concern
they match. Do not consolidate into `GVL_HMI`. Add the pragma so they
show up in the grep.

**Naming convention:** GVL names reflect *concern*, not HMI-facing status —
`GVL_Robot`, `GVL_Log`, `GVL_HmiPersistent`. The pragma is the marker, not
the `Hmi*` prefix. `GVL_HMI` (piston state) is a legacy name; it could be
renamed to `GVL_HmiPistons` for symmetry, but that's cosmetic churn — no
value if kept as-is. Do not rename `GVL_Robot`/`GVL_Log` to add an `Hmi`
prefix; their concern is more specific than "HMI-facing".

## DECISION: FB interface convention — VAR_INPUT / VAR_OUTPUT / VAR_IN_OUT

The `FB_MasterAutoCycle` / `FB_PistonAutoCycle` / `FB_SolSpringPiston_2Pos`
interfaces settled on this split — new FBs should follow it:

| Section | When to use | Rationale |
|---|---|---|
| `VAR_INPUT` | Read-once sensors, discrete signals, setpoints (`bSwitchExtended`, `bAtPos1`, per-scan raw values) | Copy-on-call semantics; caller passes a value, FB reads it and doesn't write back. Cheap for scalars. |
| `VAR_OUTPUT` | FB-produced per-scan signals that the caller reads (`bCmdExtend`, `bSepCmdExtend[]`, `bAnyRunning`, `iErrorCode`) | Caller reads via `.OutputName`. Enables OR-merge at the call site: `fbA.bCmdExtend OR fbB.bCmdExtend`. |
| `VAR_IN_OUT` | Large shared structs the FB both reads and writes (`stHmi`, `stAuto`, `stCfg`, `stRobot`) | Pass-by-reference under the hood — zero copy cost. Works with persistent structs (VAR_OUTPUT would reset each cold boot). |

**Alternatives considered and rejected:**
- All-`VAR_OUTPUT` for configs → copies large structs every scan; also
  breaks persistence (VAR_OUTPUT is not persistent-safe).
- All-`VAR_IN_OUT` (including for outputs) → breaks the OR-merge pattern
  at call sites; anyone with the ref can mutate what should be a produced
  signal.
- `POINTER TO` / `REFERENCE TO` → lower-level than `VAR_IN_OUT`, no
  init/bounds checks. Use only for array-of-refs situations; otherwise
  `VAR_IN_OUT` wins.

## DECISION: IO mapping architecture (Level 1 today; Level 2 for future)

**Current state (Level 1):** IO copy lives in a dedicated `PRG_IoMap`
PROGRAM with two actions — `PRG_IoMap.ReadInputs` and
`PRG_IoMap.WriteOutputs`. `PRG_IoMap`'s own implementation body is
`ReadInputs(); WriteOutputs();`, so both fire every time the task calls
`PRG_IoMap`. PRG_IoMap runs on a dedicated `IOmapTask` (5 ms cycle,
priority 15) which pre-empts `PlcTask` (10 ms, priority 20). MAIN sees
fresh sensor state when it starts, and command writes it makes to
`GVL_App.bValve*` land on the physical outputs within the next 5 ms
IOmapTask cycle. MAIN no longer touches `GVL_IO` directly.

**Do not call `PRG_IoMap.ReadInputs` / `.WriteOutputs` from MAIN** — that
would double-execute them on top of the task-driven call and break scan
ordering assumptions.

**Reference architecture (Level 2, future):** The Vacuum sister project
(`C:\Users\Natan.Moshkin\source\repos\Vacuum\KFM010_SCD_PLC`) uses a
richer pattern:

- A top-level `PROGRAM IO` with empty body acts as a namespace container.
- Its `VAR_OUTPUT` slots are per-station `IOModel` FBs.
- Each `IOModel` FB is `FUNCTION_BLOCK FINAL` with `VAR_OUTPUT` members of
  type `TC_Terminals.EL1008` / `TC_Terminals.EL2008` / `TC_Terminals.EL3078`
  etc. — typed Beckhoff terminal FBs from the free `TC_Terminals` library.
- Consumers reference `IO.Services.DI_01.Ch2` directly — compile-time
  typed access, no copy loop, no BOOL-index bookkeeping.
- Example: `Vacuum/.../IOModels/ServicesIOModel.TcPOU`,
  `.../MAIN.TcPOU` (declared but never called; TwinCAT auto-instantiates
  PROGRAM singletons and wires their internal AT % declarations).

**Do not adopt Level 2 blindly.** Verify `TC_Terminals` library
availability on the CP6606 WinCE 7 ARM target before committing — the
Vacuum project runs on a beefier CX-class controller. If unsupported,
Level 1 is the ceiling for this platform.

## DECISION: physical IO channel assignment

`GVL_IO.dIn` sized `ARRAY[1..24] OF BOOL`, `GVL_IO.dOut` sized
`ARRAY[1..16] OF BOOL`. Mapping lives in `PRG_IoMap.TcPOU`
(`ReadInputs` / `WriteOutputs` actions).

**Authority for this table is `docs/167_01_SAAD_PinPush_IO_List.xlsx`,
sheet `IO`, column `NEW`** — the as-rewired field assignment (added
2026-08-04). The `GVL_IO..[]` column in that sheet is the *old* pre-rewire
numbering; do not read it by mistake. Terminals: DO 1-16 = `EL2809`,
DI 1-16 = `EL1809-1`, DI 17-24 = `EL1008`.

| Actuator / signal | DI (Retract) | DI (Extend) | DO | Field status |
|---|---|---|---|---|
| SepSol1 | dIn[3] | dIn[4] | dOut[4] | ok |
| SepSol2 | dIn[7] | dIn[8] | dOut[5] | ok |
| SepSol3 | dIn[11] | dIn[12] | dOut[6] | ok |
| PushSol1 | dIn[1] | dIn[2] | dOut[1] | ok |
| PushSol2 | dIn[5] | dIn[6] | dOut[2] | ok |
| PushSol3 | dIn[9] | dIn[10] | dOut[3] | ok |
| PB1 (grip jog, **red**) | dIn[13] | — | dOut[7] LED1 | ok |
| PB2 (Sep jog, **orange**) | dIn[14] | — | dOut[8] LED2 | ok |
| PB3 (START / Push jog, **green**) | dIn[15] | — | dOut[9] LED3 | ok |
| free | dIn[16] | — | — | — |
| GripSolL | dIn[17] | dIn[18] | dOut[10] | ok |
| GripSolR | dIn[19] | dIn[20] | dOut[11] | **no air**; both sensors unconfirmed |
| PlateSen — sheet calls this **R** | dIn[21] | — | — | ok — but `PRG_IoMap` reads it into `bPlateSenL` |
| PlateSen — sheet calls this **L** | dIn[22] | — | — | unconfirmed — `PRG_IoMap` reads it into `bPlateSenR` |
| LED_GREEN (machine status) | — | — | dOut[12] | ok |
| LED_RED (machine status) | — | — | dOut[13] | ok |
| free | dIn[23..24] | — | dOut[14..16] | — |

Sep and Push are **interleaved on the input side** (Push on 1/2, 5/6, 9/10;
Sep on 3/4, 7/8, 11/12) and **swapped on the output side** (Push `dOut[1..3]`,
Sep `dOut[4..6]`). That is not a mistake to be tidied up — it is the physical
wiring. This table was wrong about all six of those pistons from the
2026-07-28 rewire (`fd49d4f`) until 2026-08-04.

`dIn[16]` is a deliberate gap so the grip sensors start on a terminal
boundary: `dIn[1..16]` is one 16-channel `EL1809-1` and `dIn[17]` is channel 1
of the `EL1008`.

**Two known wiring discrepancies — read before trusting a plate lamp or a
grip fault.**

1. **The plate sensors are swapped between the sheet and the code.** The sheet
   puts `PlateSensR` on DI 21 and `PlateSensL` on DI 22; `PRG_IoMap` does the
   opposite. Functionally invisible today because `bPlateOk` is an OR (see the
   grip/plate deviation note under FB_MasterAutoCycle), but the `L`/`R` lamps
   on `Main.TcVIS` are therefore mislabelled, and the sensor the sheet marks
   `ok` is the one the panel calls `L`. Settle which physical side is which
   before swapping either end — the sheet's L/R may be from the opposite
   viewpoint.
2. **`GripSolR` has no air**, so the right gripper cannot move regardless of
   what the PLC commands, and its two sensors (`dIn[19]`, `dIn[20]`) are not
   confirmed wired. This is the reason for the OR aggregation deviation, and
   it is a field condition, not a code state — `fbGripSolR` *is* called in
   `MAIN` and *is* driven.

Tag convention: `<Device>Sol<N>` = single Extend coil (SOL-Spring, spring
retracts). Retract sensors still exist on the DI side — the
retracted-position feedback is useful even without a retract coil.

To add a new actuator, extend `GVL_IO` (already sized DI[1..24] /
DO[1..16]; grow arrays if needed), add its GVL_App alias, wire it in
`PRG_IoMap.ReadInputs` / `WriteOutputs`, then finish the EtherCAT link
in the System Manager.

## SHIPPED: robot tuning parameters — VISU exposure + range limits (2026-07-26)

_All three items below are done. Kept for the traced ranges and the two
design points under item 1, which are load-bearing._

The 11 `ST_RobotParams` tuning values have **documented valid ranges that
nothing on the PLC side enforces**. Ranges and units were traced to the
robot repo (`167_01_Saad_Flower/Robot/167-01-Saad/`, which is neither this
repo nor FlowerPyHmi — easy to miss):

- **Units are percentages.** `global.lua:44-48` `Init()` calls
  `VelJ(J_SPEED)` / `VelL(L_SPEED)` — commented "Joint Speed %" / "Linear
  Speed %" — plus `SpeedFactor(FACTOR_SPEED)` with `FACTOR_SPEED = 80`
  scaling everything globally. `WAX_SPEED` / `WATER_SPEED` feed the `v=`
  velocity-ratio option of `MovL` (`src0.lua:112,114,144,152`).
- **Authoritative ranges**, from the vendor's own GUI which clamps to them
  (`Robot/167-01-Saad/tcp client.py:14-21`, clamp at `:90`; byte-identical
  copy at `RobotBridge/Client_working_example/tcp client.py`, pasted into
  `readme.txt:27-32`):

  | Param | Range |
  |---|---|
  | `J_SPEED`, `L_SPEED` | 1–100 |
  | `WAX_SPEED`, `WATER_SPEED` | 0–100 |
  | `REPEATS` | 1–10 |
  | `START_WAIT`, `WATER_WAIT`, `STAND_WAIT`, `END_WAIT`, `WAX_WAIT_TIME_OUT` | 10–10000 |
  | `WAX_WAIT_TIME_IN` | 0–10000 |

Nothing validates these anywhere in our stack: `src2.lua:44-54` assigns
`tonumber()` straight through with no clamp, `ST_RobotParams` is bare `INT`
defaults, and `FB_RobotTcpClient` only marshals name/value. FlowerPyHmi now
range-checks on write (rejects with a 400 rather than clamping silently, so
the operator sees what was refused) — but it is only one of several possible
writers.

**Current VISU state (updated 2026-07-26):** all 11 tuning values are now
editable on `PLC1/VISU/Robot.TcVIS`, each with `InputBoxMin`/`InputBoxMax`
set to the vendor range in the table above (`scripts/add_robot_params.py`).
So the panel is bounded — **but per-control limits only protect the control
they are set on**, which is why item 1 below still matters: FlowerPyHmi,
any future ADS client, and the `bSetParam` escape hatch all bypass them.

Note the comment in `ST_RobotParams` ("All INT so the classic VISU HMI binds
NumericInput directly") describes an intent that was never implemented.

To do, in preference order:

1. ~~Clamp in `FB_RobotTcpClient`.~~ **Done 2026-07-26.** `ClampParam` /
   `ParamMin` / `ParamMax` bound every writer that reaches the robot through
   this FB — the panel, FlowerPyHmi over ADS, any future ADS client, and the
   `bSetParam` escape hatch (via `ParamIndex` reverse lookup; unknown names
   pass through unclamped, which is the point of an escape hatch).

   Two design points worth not undoing:
   - The clamp **writes the bounded value back into `stParams`**
     (`SetParamValue`). It is not cosmetic: the shadow is updated to the
     value that was *sent*, so leaving an out-of-range number in the field
     would keep it permanently different from its shadow and the FB would
     re-send on every idle scan — a silent packet storm. Writing back
     converges, and the panel then shows what the robot actually got.
   - Clamping applies **only on the way out**, never to values arriving in a
     `SYNC` reply. Rewriting a robot-sourced value would push our table back
     at the robot, and if the table were ever wrong the two ends would fight.
2. ~~Add the NumericInputs to `Robot.TcVIS` with `min`/`max`.~~ **Done
   2026-07-26** — 11 editable fields, each range-clamped per the table.
   (The open question of whether a panel operator *should* be able to change
   robot speeds was answered by doing it; revisit if that turns out wrong.)
3. ~~Replace the stale `ST_RobotParams` comment with the real units and
   ranges.~~ **Done 2026-07-26** — the struct now documents percentages vs
   milliseconds, cites `global.lua` for the units, carries the range per
   field, and says outright that `INT` is an encoding detail. The old claim
   that it was "all INT so the classic VISU HMI binds NumericInput directly"
   described an intent that went unimplemented until the panel grid landed.

Keep `scripts/check_pyhmi_contract.py` in mind: if bounds move into the PLC,
FlowerPyHmi's copy in `flower_py_hmi/robot.py` (`ParamField.lo/hi`) becomes a
second source of truth that nothing keeps in step.

## Out of scope (Future)

- ~~**Review persistent vars**~~ **Done 2026-07-27** — the bench test was
  run and they did *not* survive. Root cause and fix in the PERSISTENT
  section above.
- **Reassign LEDs to functional statuses.** **Partly done 2026-07-29** —
  LED3 now blinks "press me to arm" while `eStep = NOT_HOMED` in Automatic
  (still a press mirror in Manual). LED1 and LED2 remain dumb press mirrors;
  remaining candidates are LED2 = error latched and LED1 = TCP connected.
  Deferred until operator preference is known — each is a one-line change in
  `MAIN.TcPOU`'s status-lamp section.
- ~~Delete deprecated fields in `ST_HmiRobot`.~~ **Done 2026-07-26** —
  `bAtPos1/2/3`, `bTx*` and `bRxResetError` removed. Nothing referenced them:
  no POU, no VISU page, and `scripts/check_pyhmi_contract.py` still resolves
  229/229 FlowerPyHmi symbols without them (231/231 since 2026-08-05).

- ~~**Remove `stBridgeCfg` / `ST_LogBridgeCfg` — spans both repos.**~~ **DONE
  2026-08-07.** The recipe below is kept because its ordering argument and its
  warning about `check_pyhmi_contract.py` both proved exactly right in practice.
  `GVL_Log.stBridgeCfg` (log dir, level, retention days/MB, poll ms) existed
  *solely* so the retired `RobotBridge/log_pump.py` could publish its own
  logger configuration for an HMI to display. With the bridge retired
  (2026-07-26) **nothing writes it**: it reads as empty strings and zeros, and
  FlowerPyHmi's Logs page renders a visibly blank "Log bridge config" block
  because of it. Confirmed dead by grep — no POU, no VISU page, no script
  assigns it.

  Not urgent (it is inert, not harmful), but it is the last structural
  leftover of the bridge and it makes a shipped page look broken.

  **Order matters: do FlowerPyHmi first, then the PLC.** Deleting the PLC
  symbol while the poller still asks for it sends `_read_bridge_cfg` down the
  1808 → probe-every-symbol → exclude path in `PyadsClient.read_many`. It
  recovers (it is its own `read_many` call, not part of the ~220-symbol cycle
  batch, so it degrades rather than taking the poll loop down) — but it costs a
  one-off probe and logs a "dropping N unresolvable symbol(s)" warning that
  will look like a real fault to whoever reads the log next.

  **FlowerPyHmi** (separate repo — 8 places):
  - `flower_py_hmi/plc_log.py` — `BRIDGE_CFG_ROOT`, `BRIDGE_CFG_FIELDS`,
    `bridge_cfg_symbol()`, and the module docstring line about it
  - `flower_py_hmi/state.py` — the two imports, `_plc_log_bridge_cfg` (init +
    the reconnect reset), the `if self._plc_log_bridge_cfg is None` block in
    `_read_plc_log`, `out["bridge_cfg"]`, and `_read_bridge_cfg()` itself
  - `flower_py_hmi/ads_client.py` — the five `GVL_Log.stBridgeCfg.*` seeds in
    `prime_plc_log()`
  - `flower_py_hmi/templates/logs.html` — the `bridge-cfg-title` heading and
    the `#plc-bridge-cfg` `<dl>`
  - `flower_py_hmi/static/logs.js` — the `pl.bridge_cfg` / `[data-cfg]` render
    block, and the `bridgeEl` lookup
  - `flower_py_hmi/static/settings.css` — `.bridge-cfg*` rules, if unused after
  - `flower_py_hmi/templates/docs/logs.html` — the "Log bridge config — dead"
    section (written 2026-07-27 to explain the blank block; delete it with the
    block)

  **This repo** (3 places):
  - `PLC1/GVLs/GVL_Log.TcGVL:45` — the `stBridgeCfg : ST_LogBridgeCfg;` field
    and its comment block
  - `PLC1/DUTs/ST_LogBridgeCfg.TcDUT` — delete the file
  - `PLC1/PLC1.plcproj:56` — remove its `<Compile Include>` entry, or the
    build will fail on a missing file

  Then run `pytest` in FlowerPyHmi. **`scripts/check_pyhmi_contract.py` will
  not notice this change either way** — it mirrors `_cycle_symbols()`, which
  never included the bridge-cfg symbols (nor the `aRecent` ring); both are read
  by their own separate `read_many` calls. So the resolved count stays put, and
  a green contract check is *not* evidence the removal is complete. Grep for
  `bridge_cfg` and `stBridgeCfg` across both repos instead — that is what
  confirms it.

  No other symbol path changes: FlowerPyHmi reads `GVL_Log` **per-field by
  symbol name**, not as a packed struct, so narrowing the GVL cannot shift an
  offset under anything else. (Same property that made widening `ST_LogEntry`
  with `sTime` / `sSevText` safe.)


## Playwright

- http://127.0.0.1:3003/liveview_64DA0B941E542F0480ED7063192BC500.html
- Put the screenshots to some temp folder