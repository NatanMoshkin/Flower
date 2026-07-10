# Robot ↔ PLC integration — architecture options

**Status:** open architectural decision, no commit yet. Written 2026-07-10 after discovering that the current design (`RobotBridge/` Python bridge + pyads) cannot run on the CP6606 (Windows Embedded Compact 7 ARM). Decision deferred until robot hardware capabilities are verified.

## The problem, restated

The CP6606-0001-0020 panel PC hosts both the TwinCAT PLC and the operator HMI. It runs Windows Embedded Compact 7 on ARM. That platform cannot host CPython or `pyads`, so the current `RobotBridge/robot_bridge.py` cannot execute on the panel itself.

At the same time, the project has committed to avoiding paid Beckhoff supplements (TF6310 TCP/IP, TF6100 OPC UA, etc.), so the PLC cannot open its own TCP socket to the robot without adding another paid module.

Four viable options, one rejected fallback, plus a "do nothing / keep the current design" baseline.

## Where each Python component lives — read this first

Two Python components are involved, and only one is production-critical on the machine floor:

- **`RobotBridge/`** — machine-side, always-on. Sits between the robot's TCP server and the PLC's ADS runtime. This is what all the options below are trying to place. Without it (or a hardware replacement — Options 1 and 4), the operator's HMI cannot show robot position updates and `FB_MasterAutoCycle` cannot progress.
- **`FlowerPyHmi/`** — engineering-side, on-demand. Runs on any developer's laptop when a diagnostic UI is needed. It talks ADS to the CP6606 exactly the same way the bridge does, but the operator never sees it. It doesn't need to be always-on. It does **not** need to live on any of the boxes discussed below. It is not part of the production critical path — a `pip install` on the engineering laptop, launched when convenient, dismissed between sessions.

**So only `RobotBridge/` is actually at stake in the decision below.** Any option that mentions "companion box hosts both bridge and PyHmi" is optional in the second half — you can always relegate PyHmi to the laptop and only put the bridge on the companion.

## Comparison at a glance

| # | Option | Bridge lives where | Extra HW | Effort | Latency | Reversibility |
|---|--------|-------------------|----------|--------|---------|---------------|
| 1 | Discrete I/O between robot and PLC (no bridge at all) | N/A | EL1xxx / EL2xxx terminals, wiring | 0.5–1 day PLC + robot config | Sub-millisecond | Easy to revert if robot HW supports both |
| 2 | Replace CP6606 with x86 Beckhoff (e.g., CX5340 + CP2xxx panel) | Same panel PC | New panel PC | 2–5 days migration | Same as today | Hard: capital HW swap |
| 3 | Add a companion box (RPi 4 Linux or industrial Windows NUC) | Companion box | +1 device | 1–2 days first cut | Same as today (TCP + ADS) | Easy: pull the box, plug it back in later |
| 4 | Serial (RS-232 or RS-485) between robot and PLC via EL6001 / EL6021 | N/A (PLC handles it directly via Tc2_SerialCom) | EL6001 or EL6021 terminal, serial cable | 1–2 days PLC + robot config | Milliseconds | Easy: unwire terminal |
| — | Rewrite bridge in C#/.NET CF 3.5 for CE 7 | CP6606 | None | 4–5 days | Same as today | Impractical, dead tooling |
| — | TF6310 (paid) on CP6606 | CP6606 | License fee | 1–2 days | Same | Money already spent |

---

## Option 1 — Discrete I/O between robot and PLC

Skip the entire TCP protocol. Wire the robot's digital outputs to EL1xxx input terminals on the CP6606, and (optionally) the PLC's digital outputs back to the robot's inputs via EL2xxx.

### Signal mapping (one possible encoding)

Robot → PLC (robot DO → PLC DI):

| Robot signal | PLC input | Replaces TCP frame |
|---|---|---|
| At-Pos-1 | `GVL_IO.dIn[?]` → `stRobot.bAtPos1` | `POS1` |
| At-Pos-2 | `GVL_IO.dIn[?]` → `stRobot.bAtPos2` | `POS2` |
| At-Pos-3 (optional, or derive as NOT (Pos1 OR Pos2)) | `GVL_IO.dIn[?]` → `stRobot.bAtPos3` | `POS3` |
| Reset-Error (optional) | `GVL_IO.dIn[?]` → `stRobot.bRxResetError` | `RESET_ERROR` |

PLC → Robot (PLC DO → robot DI):

| PLC output | Robot input | Replaces TCP frame |
|---|---|---|
| Auto-started | `GVL_IO.dOut[?]` | `AUTO_STARTED` |
| Push-done | `GVL_IO.dOut[?]` | `PUSH_DONE` |
| Pistons-error | `GVL_IO.dOut[?]` | `PISTONS_ERROR` |

Minimum viable is **2 DI + 3 DO** if we can live without POS3 and RESET_ERROR (the robot could reset its own error internally). Comfortable is **4 DI + 3 DO**.

### What changes in the codebase

- `RobotBridge/` becomes obsolete. Retire it.
- `GVL_Robot.stRobot` shrinks. `eConnState`, `nPacketsRx`, `sLastMessage`, `nPacketsTx`, `sLastTxMessage` are no longer meaningful — discrete I/O has no "connection state" the operator needs to see, just "input signals present or not."
- `FB_MasterAutoCycle`'s outbound transitions (`bTxAutoStarted`, `bTxPushDone`, `bTxPistonsError`) map directly onto EL2xxx outputs — no rising-edge latching needed, just tie the state-machine flag to the physical output.
- `FB_MasterAutoCycle`'s inbound transitions look at DI edges instead of TCP messages. Rising-edge on `bAtPos1` = same trigger as `POS1` today.

### Pros

- **Deterministic and hard-real-time.** No socket buffers, no reconnect delay, no half-open failure mode. A rising edge on the PLC input is seen within one scan cycle (10 ms).
- **No auxiliary hardware.** No RPi, no NUC, no CX. Just wiring.
- **No new failure surface.** No middleware to crash. No AMS routes to misconfigure. No CSV log to rotate.
- **Free.** No licenses, no PC hardware. Costs are the EL terminals (already probably on the panel) plus wire.
- **Wire diagnostics are trivial.** LED on each channel of the EL card shows exactly what's happening. No `netstat`, no bridge log tail.
- **Operator training is easier.** "Is the AtPos1 light on?" beats "Is the eConnState reading Connected?"

### Cons

- **Semantically thin.** Discrete I/O carries a boolean, not a string. Custom diagnostic messages (`FOO` unknown-frame handling in the current bridge) can't be transmitted. If the robot ever needs to send a status code or a diagnostic byte, we'd need to widen the interface (byte-parallel with a strobe, or fall back to serial/TCP).
- **Requires robot DO/DI capability.** Not verified yet. Older or lower-end robots may lack discrete I/O, or may charge extra for the I/O option module. **This is the gating question for this option.**
- **Cabling.** Physical wires between robot and panel. If they're far apart, that's a real cable pull. If they're already in the same enclosure or adjacent, negligible.
- **No richer future features.** If a stakeholder later asks for "capture the robot's last error code in the HMI log," that's a wire we don't have. TCP would just be one more field.

### Cost & effort

- **Hardware:** 1× EL1008 (8-ch DI) if not already fitted ≈ €80; 1× EL2008 (8-ch DO) ≈ €80. Wire and ferrules negligible.
- **Wiring:** half a day for an electrician if the panel and robot are close.
- **PLC changes:** rewire `stRobot` fields to `GVL_IO.dIn[]`/`GVL_IO.dOut[]` mappings. Simplify `FB_MasterAutoCycle` — remove the connection-state gate, remove the `bTx*` latching (or keep as pass-through). Estimate 0.5 day of code + testing.
- **Robot config:** map internal signals to physical outputs on the robot's I/O module. Robot-vendor-specific. Typically an hour or two in the robot's teach pendant / config tool.

### Reversibility

Medium-good. If we later decide we need TCP after all (e.g., for richer diagnostics), the discrete I/O can coexist — leave the wires in as a fast-path handshake and add TCP for metadata. Or unwire and revert. The main sunk cost is the wiring labor.

### Open questions blocking this option

1. **Does the target robot support discrete I/O outputs of the kind we need?** (24V sinking/sourcing at ≥ 4 channels.) Need to check the robot's spec sheet or an integrator.
2. **Does the robot's motion controller expose "at Pos-N" as a discrete output natively, or does the robot programmer have to script it?** Latter is fine but adds a line to the robot program.
3. **How is the robot's reset button wired today?** If it's already a physical button on the robot's teach pendant, `RESET_ERROR` may just need to be a discrete output from that same button — no new logic on the robot side.

---

## Option 2 — Replace the CP6606 with an x86 Beckhoff platform

Swap the CP6606 (ARM + WinCE 7) for a Beckhoff device running full Windows 10 IoT LTSC. This lets us keep the "one box" architecture principle intact while unblocking Python + pyads on the panel itself.

### Concrete candidates

| Model | Class | Notes |
|---|---|---|
| **CX5340** | DIN-rail Embedded PC | Intel Celeron J1900 x86, Windows 10 IoT. Needs a separate CP touch panel for operator display. |
| **CX5140** | Newer DIN-rail | Intel Atom E3940, Windows 10 IoT. Similar story. |
| **CP2xxx series** | Modern Panel PCs | x86, Windows 10 IoT, built-in touch display. Direct drop-in for the CP6606 form factor. Model choice depends on screen size. |
| **CP6606-0001-002x** revisions | Panel PC | Some newer CP66xx revisions ship with x86 CPUs and Windows 10 IoT; check current Beckhoff catalog. |

### What changes in the codebase

- Nothing.
- Really — `RobotBridge/` and `FlowerPyHmi/` both run as-is on Windows 10. The AMS Net ID probably changes (new panel PC has its own), but that's a `config.yaml` edit on the RPi… wait, there is no RPi. Just `config.yaml` edits on the same box.
- The existing PLC HMI (Beckhoff TcHmi web runtime) needs a re-license check — Beckhoff HMI runtime licenses are tied to hardware serial number.

### Pros

- **Preserves single-box architecture.** No auxiliary device. Fewer things to power, fewer things to monitor.
- **Full desktop Windows toolchain.** Any Python code you develop on your laptop drops directly onto the panel. No cross-compile, no CF 3.5 dead-tooling.
- **Modern OS.** Windows 10 IoT LTSC has security patch coverage until at least 2029; WinCE 7 has been in extended support hell for years already.
- **HMI runtime licensed properly.** Beckhoff TcHmi is licensed per device; a new device gets a fresh, currently-supported license.
- **Room to grow.** Any future feature that needs a modern runtime (Node.js dashboards, InfluxDB, MQTT broker, whatever) can just be installed.

### Cons

- **Capital cost.** A new panel PC is €1000–3000 depending on model.
- **Downtime.** Swapping the physical panel is an outage. Plan for a few hours minimum. If the CP6606 is deployed at a customer site, this becomes a scheduled service call.
- **Cutout / mechanical fit.** Panel-mount cutouts differ between models. If the CP6606 is already installed in a machine door, verify the replacement has the same or smaller cutout before ordering.
- **Re-commissioning.** New Ethernet MAC, new AMS Net ID, new hardware fingerprint. TwinCAT license needs to be re-activated on the new hardware, HMI license re-issued.
- **PLC application code needs a **full re-test** on the new hardware.** The CPU is a different family; timing behavior, task cycle jitter, and any hardware-specific quirks all need re-verification.

### Cost & effort

- **Hardware:** €1000–3000 for the new panel, plus any adapters/cables.
- **Downtime:** half a day to a day for the physical swap and initial bring-up.
- **Software:** 2–3 days of re-commissioning (license activation, HMI runtime deploy, application re-flash, verification testing).
- **Total:** 3–5 person-days if nothing goes wrong.

### Reversibility

Poor. Once you've bought the new panel and swapped it, going back means owning two panels. Hardware decisions in an industrial setting are typically one-way doors.

### Open questions

1. **What's the exact model?** CX5340 + CP touch panel? Or an integrated CP2xxx? Depends on operator ergonomics and cutout.
2. **Is the existing operator HMI (Beckhoff TcHmi) going to be re-licensed automatically, or is there a paperwork step with Beckhoff?**
3. **Does the customer / stakeholder accept a service window for the swap?**

---

## Option 3 — Add a companion box (RPi 4 Linux or industrial Windows NUC)

Keep the CP6606 exactly as-is. Add a small dedicated device on the plant subnet whose sole job is to host `RobotBridge/` and `FlowerPyHmi/`. Detailed sketch in the conversation transcript from 2026-07-10; summary here.

### Concrete candidates

| Box | ~Price | OS | Notes |
|---|---|---|---|
| Raspberry Pi 4 (2 GB) | $50–70 | Debian 12 ARM64 | Cheapest usable. USB SSD strongly recommended (SD wears out). Lab / dev / non-critical deployments. |
| Intel N100 mini-PC (generic) | $150–250 | Debian 12 or Windows 10 IoT | Best value; fanless models exist. |
| DIN-rail industrial PC (Advantech ARK, Kontron KBox, IEI DRPC-x) | $500–1500 | Debian 12 or Windows 10 IoT | -40..+70 °C rated, wide-input PSU, watchdog. Production floor spec. |
| Beckhoff CX9020 | €500–1500 | Windows Embedded Standard 7 (x86) | Ironic: "a CP6606 but with a real Windows." Beckhoff support if that matters. |

### Network topology

```
                  Plant subnet 192.168.201.0/24
    ┌──────────┐  ┌───────────────┐  ┌──────────┐  ┌──────────────┐
    │  CP6606  │  │ Companion box │  │  Robot   │  │ Eng. laptop  │
    │   .10    │──│      .20      │──│   .1     │──│  DHCP        │
    └──────────┘  └───────────────┘  └──────────┘  └──────────────┘
      PLC +        RobotBridge         TCP server    Web browser
      TcHmi        + FlowerPyHmi                     → :8000
```

### What changes in the codebase

- Nothing in `RobotBridge/` or `FlowerPyHmi/` — they already assume they're not on the CP6606.
- `RobotBridge/config.yaml` and `FlowerPyHmi/config.yaml` both point at the CP6606's AMS Net ID (`192.168.201.10.1.1`) instead of loopback.
- An AMS route must exist on both ends (companion → CP6606, CP6606 → companion). Configured once, then persisted.
- Two systemd units (Linux) or two Windows services (via NSSM) supervise the two Python processes with auto-restart.

### Pros

- **Zero code change.** Existing bridge and web HMI keep working.
- **Cheap first cut.** RPi + SD card + a Cat6 cable is under $100. Prove the architecture end-to-end for pocket change.
- **Update ergonomics improve.** Bridge and PyHmi can be updated (git pull + systemctl restart) without touching the PLC or TwinCAT. No PLC downtime for a comms tweak.
- **CP6606 stays the machine of record.** If the companion box dies, the PLC keeps running its state machine — the robot integration just goes offline. The machine can be designed to halt safely in that case (see the "companion box down → safe stop" note in the transcript).
- **Reversible.** If you later choose Option 1 or 2, unplug the companion and retire it.

### Cons

- **Extra device to own and monitor.** One more IP, one more power draw, one more thing to patch.
- **Log location changes.** Bridge logs move off the CP6606 onto the companion. Operators who currently pull logs from the panel PC need a new procedure.
- **Two production-critical devices instead of one.** Weakens the "one CP6606 is the whole system" principle. The mitigation is designing the PLC to safely halt when `eConnState = Disconnected`.
- **AMS routing is a moving part.** Wrong route = mysterious "TargetPortNotFound" errors. Documented, but a real footgun during commissioning.
- **Hardware choice matters more than it seems.** An RPi 4 on a domestic USB-C wall wart is not production-grade. If this option ships, budget for a proper DIN-rail industrial mini-PC.

### Cost & effort

- **Hardware:** $50 (RPi) up to $1500 (industrial DIN-rail).
- **Setup:** 1 day for a first working RPi bring-up (OS install, libads, venv, systemd units, AMS routes, smoke test). A second day if you're going to make it survive a plant power cycle unattended (bootloader tuning, log persistence, service dependency ordering).
- **Total:** 1–2 person-days for a working prototype, +1 day for hardening.

### Reversibility

Excellent. It's an extra box on the network. Nothing else has to change to add or remove it.

### Open questions

1. **Which specific hardware?** RPi for the lab, industrial DIN-rail for production is a reasonable answer.
2. **Is there a service the customer accepts for maintenance of a non-Beckhoff box on the plant floor?** Some customers push back on non-Beckhoff hardware in a Beckhoff automation footprint.
3. **AMS route persistence:** on the CP6606 side, is the route defined via TwinCAT XAE (which persists) or ad-hoc through the CE Router UI (which does *not* persist across reboots)?

---

---

## Option 4 — Serial communication (RS-232 or RS-485) between robot and PLC

Wire the robot's serial port to a Beckhoff serial terminal on the PLC's EtherCAT bus. Use the exact same ASCII-line protocol we've been walking through (`POS1\n`, `AUTO_STARTED\n`, etc.), but over a serial link instead of TCP. The PLC parses frames itself using the free `Tc2_SerialCom` library — no Python middleware, no companion box.

This option sits between Option 1 (discrete I/O, dumb but rock-solid) and Option 3 (bridged TCP, rich but complicated). It keeps the "same-string protocol" richness while removing the middleware.

### Concrete hardware

| Terminal | Signal | Channels | ~Price | Notes |
|---|---|---|---|---|
| **EL6001** | RS-232 (V.24) | 1 | ~€150 | Point-to-point. Distance ≤ ~15 m. Simplest. |
| **EL6021** | RS-422 / RS-485 | 1 | ~€180 | Half or full-duplex. Distance up to ~1200 m at low baud. Good if the panel and robot are far apart. |
| **EL6002** | RS-232 | 2 | ~€250 | Two channels on one terminal if we ever want a second peer. |
| **EL6022** | RS-422 / RS-485 | 2 | ~€300 | Two-channel RS-485. |

The **Tc2_SerialCom** library (bundled free with TwinCAT) provides `SerialLineControl_EL6inData22B` / `SerialLineControl_EL6outData22B` for the transmit/receive buffer handshake, plus `SendString` / `ReceiveString` FBs for the ASCII-line layer. This is Beckhoff-supported, non-licensed, and well-documented — the "boring path" for serial comms on TwinCAT.

### What changes in the codebase

- `RobotBridge/` becomes obsolete. Retire it, same as Option 1.
- Add a new FB, `FB_RobotSerialLink`, that owns the `SerialLineControl` handshake and the `SendString` / `ReceiveString` calls. Runs in `MAIN` alongside `FB_MasterAutoCycle`.
- `GVL_Robot.stRobot` mostly keeps its shape — `bAtPos1..3`, `bTxAutoStarted`, `bTxPushDone`, `bTxPistonsError`, `bRxResetError` still exist. Only the fields that make sense specifically for TCP (`eConnState`, `nPacketsRx`/`Tx`, `sLastMessage`/`sLastTxMessage`) get replaced by their serial equivalents:
  - `eLinkState` — Idle / Rx / Tx / Error (a small enum for the EL6001 state)
  - `nBytesRx`, `nBytesTx` — same idea, byte counts
  - `sLastMessage`, `sLastTxMessage` — unchanged in role, just filled from serial line-parser instead of TCP
- `FB_MasterAutoCycle`'s protocol semantics don't change. It still pulses `bTxAutoStarted := TRUE` on state transitions; `FB_RobotSerialLink` picks that up and calls `SendString('AUTO_STARTED')`. Its inbound handling still watches `stRobot.bAtPos1` rising, which `FB_RobotSerialLink` sets when it parses `POS1` off the line.

### Pros

- **Free.** `Tc2_SerialCom` ships with TwinCAT, no license. Hardware cost is one EL terminal.
- **Runs entirely on the CP6606.** No companion box, no external Python, no AMS routes to a second host. Preserves single-box architecture.
- **Same protocol semantics as TCP.** Arbitrary ASCII strings, so future features (diagnostic codes, error text) can be added without re-wiring.
- **Well-understood, boring technology.** Serial links have been standard on industrial gear for 40 years. Wire diagnostics are trivial (USB-serial adapter + a terminal window).
- **Deterministic on the PLC side.** Line accumulator lives in PLC scan time — bounded latency, no OS jitter, no TCP retransmit.
- **Simpler failure model than Options 3.** No "half-open connection," no reconnect state machine — a broken cable shows up as `SerialLineControl` reporting `bError = TRUE` on the very next scan. `FB_MasterAutoCycle` can gate on `stRobot.eLinkState = Ok`.

### Cons

- **Requires robot HW support.** Not every robot has a spare RS-232 or RS-485 port. Older robots often do; some modern robots have dropped serial in favor of Ethernet-only. Verify like Option 1.
- **Distance limit.** RS-232 is ~15 m max, and shorter is more reliable. RS-485 pushes that to ~1200 m at low baud, so it covers most factory-floor layouts, but you'll want twisted pair and termination resistors done right.
- **One-to-one link.** RS-232 is strictly point-to-point. RS-485 supports multi-drop but our use case is a single robot, so that's not a win.
- **Baud rate is a shared choice.** Robot and PLC have to agree on baud, parity, stop bits, flow control. Not hard, but easy to get wrong and confusing to debug.
- **Framing is still on you.** The `\n` terminator convention has to be enforced on both sides — same story as TCP but without the OS's TCP stack helping.
- **No richer parallelism.** If a stakeholder later wants multiple concurrent status streams, that's what TCP is naturally good at; serial isn't.

### Cost & effort

- **Hardware:** EL6001 (~€150) or EL6021 (~€180), plus a serial cable (null-modem RS-232 or a twisted pair for RS-485). Cabling is cheap.
- **PLC changes:** write `FB_RobotSerialLink` (a few hundred lines around `Tc2_SerialCom`), simplify `GVL_Robot.stRobot`, adjust `FB_MasterAutoCycle` to read from the new fields. Estimate 1–1.5 days including bench testing.
- **Robot config:** enable serial output on the robot, set the same baud/parity/stops, wire the frames the robot is already sending. Robot-vendor-specific. A few hours typically.
- **Total:** 1–2 person-days.

### Reversibility

Excellent. Terminal comes off the DIN rail, cable comes off, PLC code reverts. Zero sunk cost beyond the (recoverable) terminal.

### Open questions

1. **Does the target robot have a serial port (RS-232 or RS-485), and if so which?** This is the gating question — same shape as Option 1's discrete-I/O question.
2. **What baud rate and framing (parity, stop bits) does the robot expect?** Usually configurable, but confirm.
3. **How far apart are the robot and the panel physically?** Answers whether RS-232 (EL6001) or RS-485 (EL6021) is the right terminal.

---

## Rejected / not recommended

### Rewrite the bridge in C# / .NET Compact Framework 3.5 for CE 7

Technically possible but not recommended. Requires Visual Studio 2008 (Microsoft's last CF 3.5 IDE), the CP6606's CE 7 SDK from Beckhoff, and TwinCAT for CE. Dev cycle is ~4–5 days *if* the tooling cooperates. Ships onto a platform Microsoft ended support for years ago. Every future update forces you back into a 2008-era IDE.

Only worth doing if Option 3 is somehow ruled out and the customer will not accept Option 2.

### TF6310 (paid TCP/IP supplement) on the CP6606

Rejected by explicit project preference — see `memory/feedback_avoid_licensed_beckhoff_libs.md`. Included here only so the option is not "forgotten" in a future review.

---

## Decision framework

Rough guidance for picking, once open questions are answered:

- **If the robot supports discrete I/O with enough channels →** Option 1. Simplest, fastest, most reliable. Nothing else beats no software for uptime.
- **If the robot has a serial port (RS-232 / RS-485) but not discrete I/O, or you want richer messages than boolean pins allow →** Option 4. Same "one-box, no middleware" property as Option 1, but with the full ASCII-frame semantics of Option 3. Best middle ground.
- **If the robot exposes neither discrete I/O nor serial, and this machine is a one-off or low-volume →** Option 3 with an RPi. Cheapest way to unblock the current TCP design.
- **If the robot exposes neither, and this design will ship to multiple customers →** Option 2. The capital cost is amortized across units; the software and support story is dramatically cleaner than shipping a companion RPi to every customer.
- **If the customer explicitly forbids non-Beckhoff hardware →** Options 1, 4, or 2 (all-Beckhoff paths). Option 3 with a Beckhoff CX9020 companion is a fallback that keeps the plant-floor logo Beckhoff-only.

Note: Options 1 and 4 both retire `RobotBridge/`. Options 2 and 3 keep it. Whichever way this lands, `FlowerPyHmi/` is unaffected — it stays on the engineering laptop.

## Next step

Verify robot HW capabilities: **discrete I/O** (unlocks Option 1) and **serial port availability** (unlocks Option 4). Answers to those two questions eliminate most of the option space in one go. Everything else can wait behind that check.
