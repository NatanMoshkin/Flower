167_01 Saad — Flower assembly stand
Status note, updated 2026-07-27.

For anything durable, read CLAUDE.md (decisions + open work) and
docs/operator-manual.md (shop-floor manual). This file is a short orientation
note, not a spec.


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
- Control separation: done. A single machine-wide
  GVL_HmiPersistent.stMasterAutoCfg.bAutoMode is the sole source of truth for
  every piston's mode -- "no option to double control". In Auto the
  MasterAutoCycle owns all 8 pistons; in Manual it is held IDLE and the
  operator jogs. FB_PistonAutoCycle still exists but is not on the panel.
- Panel GUI: 7 classic VISU pages -- Main (embeds AutoMain), PistonsManual,
  GripperManual, Robot, Logs, plus the reusable Piston control.
- Real IO: 24 DI / 16 DO wired. 8 pistons (3 Sep, 3 Push, 2 Grip), 2 plate
  sensors, 3 push-buttons + LEDs, 2 status lamps. Channel table in CLAUDE.md.
- 3 push buttons with LEDs: done. Behaviour is gated by bAutoMode -- in Auto
  PB1 starts a cycle; in Manual all three are momentary jog.
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
CMD:<m>    0 = none, 1 = start cycle, 2 = reset error. MAIN owns the R_TRIG.
           The robot zeroes it after the next state push acknowledges.

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


STATE MACHINE (E_MasterAutoStep) -- 15 states, was 12
-----------------------------------------------------
  IDLE                 := 0
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
  WAIT_PLATE           := 20
  GRIP_EXTENDING       := 21
  GRIP_RETRACTING      := 22
  MANUAL               := 30    sentinel; never assigned to eStep, only
                                reported to the robot via nStateOut
  ERR                  := 99

Run order:
  IDLE -> INIT_PUSH_RETRACTING -> INIT_SEP_RETRACTING -> INIT_GRIP_RETRACTING
       -> WAIT_PLATE -> GRIP_EXTENDING -> SEP_EXTENDING -> PUSH_EXTENDING
       -> DWELL_PUSH -> PUSH_RETRACTING -> PUSH_RETRACTED_DWELL
       -> SEP_RETRACTING -> SEP_RETRACTED_DWELL -> GRIP_RETRACTING -> IDLE

Continuous cycling is DISABLED on the real machine: the panel checkbox was
removed and MAIN forces stMasterAutoCfg.bContinuous := FALSE every scan.


THINGS THAT SURPRISE PEOPLE
---------------------------
- The panel log is RAM ONLY. No file I/O anywhere in the PLC. Every entry is
  lost on power cycle / reset / download; only the last 256 are kept. Use
  FlowerPyHmi if a durable record is needed.
- Log timestamps come from the panel RTC. Unset clock reads '--:--:--'.
- Persistent values flush ~2 s AFTER editing stops. Power off sooner and the
  edit is gone. Each flush is logged.
- bNoSensors and bBypassPlateSensors persist. A bench flag left on survives a
  reboot -- check both before a production run.
- Automatic survives a power cycle (deliberate). The machine comes back in Auto
  at IDLE, so a robot already running can request a cycle straight away.
- Never hand-edit a .TcVIS. Clone a proven block; XAE silently drops elements it
  cannot parse. Run scripts/validate_visu.py after every VISU edit.
- The classic VISU cannot stringify an enum. That is why every enum here has a
  STRING mirror (sStepText, sErrorText, sConnStateText, sSevText).
