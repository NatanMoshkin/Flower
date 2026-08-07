167_01 Saad — Flower assembly stand
Status note, updated 2026-08-07.

For anything durable, read CLAUDE.md (decisions + open work) and
docs/operator-manual.html (shop-floor manual). This file is a short orientation
note, not a spec.


READING THE DOCS
----------------
serve-docs.bat               DOUBLE-CLICK THIS, in the repo root. Serves the
                             repo root on http://127.0.0.1:8765 and opens the
                             docs index. Ctrl+C or close the window to stop.

  Docs index   http://127.0.0.1:8765/docs/index.html
  CLAUDE.md    http://127.0.0.1:8765/docs/viewer.html?doc=../CLAUDE.md

A server is needed because docs/viewer.html renders markdown by fetch()ing it,
and browsers block fetch() for file:// URLs -- so double-clicking viewer.html
will always fail. The server must also be rooted at the REPO ROOT, not at docs/:
the ?doc=../CLAUDE.md parameter reaches outside docs/, and a docs-rooted server
refuses that. serve-docs.bat gets both right.

The operator and technician manuals are plain self-contained HTML and need no
server -- double-click them. Both are bilingual (EN/HE) with a dark/light
toggle.


SOLUTIONS
---------
167_01_Saad_PLC.sln          The ONLY PLC solution. Real CP6606 panel.
                             Panel_PLC_HMI/167_01_Saad_PLC/

Flower_PLC_HMI.sln           REMOVED 2026-07-26. Was the develop/test solution
                             for the local PC and the temporary PLC, and carried
                             the TwinCAT web HMI (Flower_HMI). Both retired.
                             There is no mirror to keep in sync any more, so PLC
                             edits land in one place only. Recoverable from git
                             history if ever needed.

FlowerPyHmi                  Engineering-side UI. SEPARATE REPO at
                             167_01_Saad_Flower/FlowerPyHmi. Runs on any
                             developer laptop, talks ADS to the panel. Not a
                             submodule, so nothing keeps its symbol contract in
                             step -- run scripts/check_pyhmi_contract.py after
                             changing any HMI-facing GVL or DUT.


WHAT IS DONE
------------
- Robot comms: TCP/IP from the PLC itself. FB_RobotTcpClient uses Tc2_TcpIp
  (TF6310, installed on the CP6606 -- the one documented exception to the
  avoid-paid-libs rule). The Python bridge in RobotBridge/ is RETIRED; see
  RobotBridge/README.md for what is still kept there as protocol reference.
- Control separation: done. A single machine-wide GVL_HMI.bAutoMode is the sole
  source of truth for every piston's mode -- "no option to double control". In
  Auto the MasterAutoCycle owns all 8 pistons; in Manual it is held in
  NOT_HOMED and the operator jogs. FB_PistonAutoCycle still exists as a POU but
  is never instantiated in MAIN, so per-piston auto cycling does not run.
- Panel GUI: 8 classic VISU pages -- Main (embeds AutoMain), AutoConfig,
  PistonsManual, GripperManual, Robot, Logs, plus the reusable Piston control.
- Real IO: 24 DI / 16 DO wired. 8 pistons (3 Sep, 3 Push, 2 Grip), 2 plate
  sensors, 3 push-buttons + LEDs, 2 status lamps. Channel table in CLAUDE.md;
  the authority is docs/167_01_SAAD_PinPush_IO_List.xlsx, sheet IO, column NEW.
- 3 push buttons with LEDs: done, gated by bAutoMode. In Auto: red PB1 HELD 1 s
  = STOP, orange PB2 = RESET while faulted, green PB3 = ENABLE AUTO (home and
  arm), PB2+PB3 held 1 s = run one bulb. In Manual all three are momentary jog.
- Arming is separate from running: an operator ENABLE AUTO homes and arms; only
  the robot's CMD:1 (or the PB2+PB3 hold, or START on an HMI) runs a bulb.
- Extended TCP to set robot parameters: done, read/write, clamped in the PLC.
- Persistent data actually reaches disk: done (FB_PersistentAutoSave).


ROBOT PROTOCOL (raw ASCII, NO newline framing; one send -> one reply)
---------------------------------------------------------------------
  PLC -> robot        Robot -> PLC              Purpose
  GET_SYNC            SYNC:NAME=VALUE,...       pull all 11 tuning params
  NAME:VALUE          OK: SET NAME              set one tuning param
  New_Bulb:1          OK: SET New_Bulb          start a fresh bulb
  STATE:<n>           CMD:<m>                   state push + command receive

STATE:<n>  n = INT value of E_MasterAutoStep, or MANUAL=30 when bAutoMode is
           FALSE. Sent on every change and every ~1000 ms as keep-alive.
CMD:<m>    0 = none, 1 = start cycle, 2 = reset error. MAIN consumes it as a
           LEVEL and clears it to 0 in the same scan -- that clear IS the
           acknowledgement. Do not re-introduce an R_TRIG here; that is what
           caused the 2026-07-28 deadlock.

WARNING: the src2.lua committed under Robot/167-01-Saad/ does NOT implement
STATE/CMD at all -- its generic NAME:VALUE branch swallows STATE:0 and answers
"OK: SET STATE". The machine runs a newer, UNCOMMITTED revision that does emit
CMD:1. Committing it is an open item in CLAUDE.md.

Tuning params and their vendor ranges (authoritative source is the vendor's own
GUI, which clamps to them: RobotBridge/Client_working_example/tcp client.py).
Units: the four speeds are PERCENTAGES, the waits are MILLISECONDS.

  ("J_SPEED", 1, 100), ("L_SPEED", 1, 100),
  ("WAX_SPEED", 0, 100), ("WATER_SPEED", 0, 100),
  ("REPEATS", 1, 10),
  ("START_WAIT", 10, 10000), ("WATER_WAIT", 10, 10000),
  ("WAX_WAIT_TIME_IN", 0, 10000), ("WAX_WAIT_TIME_OUT", 10, 10000),
  ("STAND_WAIT", 10, 10000), ("END_WAIT", 10, 10000)

FB_RobotTcpClient clamps all of these on the way out, so the panel, FlowerPyHmi
and any future ADS client are all bounded. ParamValue / ParamName index order
MUST match the robot's SYNC_ORDER.


STATE MACHINE (E_MasterAutoStep) -- 19 assigned states
------------------------------------------------------
  IDLE                 := 0     armed, waiting for a bulb request
  SEP_EXTENDING        := 1
  WAIT_POS2            := 2     RETIRED -- declared but never assigned
  PUSH_EXTENDING       := 3
  DWELL_PUSH           := 4
  PUSH_RETRACTING      := 5
  PUSH_RETRACTED_DWELL := 6
  SEP_RETRACTING       := 7
  SEP_RETRACTED_DWELL  := 8
  INIT_PUSH_RETRACTING := 10
  INIT_SEP_RETRACTING  := 11
  INIT_GRIP_RETRACTING := 12
  CHECK_PLATE          := 20    renamed from WAIT_PLATE; wire value unchanged
  GRIP_EXTENDING       := 21
  GRIP_RETRACTING      := 22
  MANUAL               := 30    sentinel; never assigned to eStep, only
                                reported to the robot via nStateOut
  NOT_HOMED            := 40    in Auto but NOT armed. eStep's declared default,
                                so this is where every power-up lands.
  RECOVER_PUSH_RETR    := 50    the RESET-out-of-ERR retract chain. Error codes
  RECOVER_SEP_RETR     := 51    12/13/14, so a failed RECOVERY is
  RECOVER_GRIP_RETR    := 52    distinguishable from a failed ARMING (6/7/8).
  ERR                  := 99

The robot acts on exactly three values: 0 = armed so send CMD:1, 99 = faulted so
send CMD:2, anything else = wait. NOT_HOMED needs no robot-side branch.

Arm:   NOT_HOMED --ENABLE AUTO--> INIT_PUSH -> INIT_SEP -> INIT_GRIP -> IDLE
Bulb:  IDLE --CMD:1 / START--> INIT_PUSH -> INIT_SEP -> INIT_GRIP -> CHECK_PLATE
            -> GRIP_EXTENDING -> SEP_EXTENDING -> PUSH_EXTENDING -> DWELL_PUSH
            -> PUSH_RETRACTING -> PUSH_RETRACTED_DWELL -> SEP_RETRACTING
            -> SEP_RETRACTED_DWELL -> GRIP_RETRACTING -> IDLE
Fault: ERR --RESET--> RECOVER_PUSH -> RECOVER_SEP -> RECOVER_GRIP -> IDLE

Continuous cycling does not exist. The checkbox went on 2026-07-27 and the
bContinuous field itself was deleted from ST_HmiMasterAutoCfg on 2026-08-06 --
it was written 15 times and read zero times. NOTE the per-piston
ST_HmiPistonAutoCfg.bContinuous is a DIFFERENT field and is still live.


THINGS THAT SURPRISE PEOPLE
---------------------------
- The panel log is RAM ONLY. No file I/O anywhere in the PLC. Every entry is
  lost on power cycle / reset / download; aLog keeps the last 256 and the Logs
  page shows the newest 20. Use FlowerPyHmi if a durable record is needed.
- Log timestamps come from the panel RTC. Unset clock reads '--:--:--'.
- Persistent values flush ~2 s AFTER editing stops. Power off sooner and the
  edit is gone. Each flush is logged.
- bNoSensors and bBypassPlateSensors persist. A bench flag left on survives a
  reboot -- check both before a production run. With bNoSensors set, all twelve
  movement-timeout error codes are unreachable.
- The machine ALWAYS boots in Automatic (GVL_HMI.bAutoMode is volatile and
  initialised TRUE since 2026-08-06) but NEVER armed: eStep defaults to
  NOT_HOMED, which the robot reads as "wait". Nothing moves until someone
  presses ENABLE AUTO. A technician who selects Manual to jog and then
  power-cycles comes back in Automatic, where the PB jogs are off by design.
- Grip and plate sensors aggregate with OR, not AND -- a deliberate field
  deviation, because GripSolR has no air and only one plate sensor is confirmed.
  Cost: a single-gripper failure is INVISIBLE; error 10/11 fire only if both
  fail. Treat grip position as unverified in any fault analysis.
- Never hand-edit a .TcVIS. Clone a proven block; XAE silently drops elements it
  cannot parse. Run scripts/validate_visu.py after every VISU edit -- and if you
  clone a whole page, scripts/fix_visu_object_guids.py on the CLONE as well.
- The classic VISU cannot stringify an enum. That is why every enum here has a
  STRING mirror (sStepText, sErrorText, sConnStateText, sSevText).
- A page that declares VAR_IN_OUT parameters is a frame REFERENCE and cannot be
  navigated to. AutoConfig was unreachable for exactly that reason until
  2026-08-06 -- retargeting its bindings was not enough.
- Four files in Panel_PLC_HMI/ are permanently modified for Local + TC 4026
  bench work and must NEVER be merged: the .sln, the .tsproj, PLC1.plcproj and
  VisualizationManager.TcVMO. PLC1.plcproj is the awkward one -- it is also
  where new VISU pages get registered, so it needs hunk-level care.
