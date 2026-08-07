"""Panel push-button test procedure — runs against a LIVE PLC over ADS.

Covers every documented PB behaviour in CLAUDE.md's "PANEL HARDWARE" section.
Presses are simulated by writing GVL_IO.dIn[13..15]; see pb_io.py for why that
is the only way.

Group E is now a NEGATIVE group: manual jogs are refused in every Automatic
state (operator decision 2026-08-05), so it guards the removal of the ERR jog
window rather than the window itself. Group G covers the two hold gestures.

    python scripts/pb_test/pb_test_procedure.py                 # run + report
    python scripts/pb_test/pb_test_procedure.py --net 5.79.93.36.1.1

Writes docs/pb-test-report.html and scripts/pb_test/last_run.json.

REQUIRES a bench target: the local runtime, or a panel with no machine
attached. It energises solenoid coils and runs the master cycle. Do NOT point
it at the production panel with air connected.
"""

import argparse
import json
import os
import platform
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pb_io import (  # noqa: E402
    BOOL, UDINT, COIL_DO, PB_DI, PB_JOG_GROUP, Plc, SETTLE, has_sev,
    transitions,
)

PB_STOP_MS = "GVL_HmiPersistent.stMasterAutoCfg.tPbStopHoldMs"
PB_START_MS = "GVL_HmiPersistent.stMasterAutoCfg.tPbStartHoldMs"

HOMING = ["INIT_PUSH_RETRACTING", "INIT_SEP_RETRACTING", "INIT_GRIP_RETRACTING"]
RECOVER = ["RECOVER_PUSH_RETR", "RECOVER_SEP_RETR", "RECOVER_GRIP_RETR"]

RESULTS = []
_group = {"id": "", "title": "", "note": ""}


def group(gid, title, note=""):
    _group.update(id=gid, title=title, note=note)
    print(f"\n=== {gid}. {title}")


def record(cid, what, expected, actual, ok, evidence=""):
    RESULTS.append({
        "group": _group["id"], "group_title": _group["title"],
        "group_note": _group["note"], "id": cid, "what": what,
        "expected": str(expected), "actual": str(actual),
        "status": "PASS" if ok else "FAIL", "evidence": evidence,
    })
    print(f"  [{'PASS' if ok else 'FAIL'}] {cid}  {what}")
    if not ok:
        print(f"         expected {expected}\n         actual   {actual}")
    return ok


def check(cid, what, expected, actual, evidence=""):
    return record(cid, what, expected, actual, expected == actual, evidence)


# ---------------------------------------------------------------------------
# reusable assertions
# ---------------------------------------------------------------------------
def jog_group_moves(p, pb, cid_prefix, should_move, context):
    """Hold PB `pb`, check its own coil group, check the other six are
    untouched, release, check everything is home again.

    The release half is the important half: the solenoid ladder RETAINS the
    coil when no branch matches, so a missing release branch strands the
    piston extended."""
    names = PB_JOG_GROUP[pb]
    others = [n for n in COIL_DO if n not in names]

    p.press(pb)
    held = p.coils(names)
    held_others = p.coils(others)
    p.release(pb)
    after = p.coils(names)

    want = {n: should_move for n in names}
    check(f"{cid_prefix}a", f"PB{pb} held {context}: {'/'.join(names)} energise"
          if should_move else f"PB{pb} held {context}: {'/'.join(names)} stay off",
          want, held, evidence=f"dOut {{{', '.join(str(COIL_DO[n]) for n in names)}}}")

    check(f"{cid_prefix}b", f"PB{pb} held {context}: the other six coils untouched",
          {n: False for n in others}, held_others)

    check(f"{cid_prefix}c", f"PB{pb} released {context}: coils drop (momentary)",
          {n: False for n in names}, after)


# ---------------------------------------------------------------------------
def run(net_id):
    started = time.strftime("%Y-%m-%d %H:%M:%S")
    with Plc(net_id) as p:
        # ---------------- snapshot everything we touch ------------------
        # Volatile GVL_HMI since 2026-08-06, not the persistent cfg struct.
        # It no longer survives a power cycle -- the panel always boots
        # Automatic -- but this procedure still saves and restores it, because
        # it is the machine mode and leaving it flipped would surprise the next
        # person at the panel.
        AUTO = "GVL_HMI.bAutoMode"
        PLATE_TMO = "GVL_HmiPersistent.stMasterAutoCfg.tPlateWaitTimeoutMs"
        TCP = "GVL_Robot.bTcpEnable"
        NOSENS = "GVL_HmiPersistent.stMasterAutoCfg.bNoSensors"
        BYPASS = "GVL_HmiPersistent.stMasterAutoCfg.bBypassPlateSensors"
        orig_auto = p.save(AUTO, BOOL)
        p.save(PLATE_TMO, UDINT)
        p.save(TCP, BOOL)
        # Both are PERSISTENT, so they survive a power cycle AND a rebuild --
        # see below for why that broke a whole run.
        orig_nosens = p.save(NOSENS, BOOL)
        orig_bypass = p.save(BYPASS, BOOL)
        for i in range(1, 25):
            p.save(f"GVL_IO.dIn[{i}]", BOOL)

        # The robot is not on this network, so FB_RobotTcpClient logs a
        # connect failure every 3 s and would flush the 20-entry ring before
        # we could read it. Disabling the link also keeps ERR stable, which is
        # what makes the fault
        # ERR observable long enough to test, since nothing sends CMD:2.
        p.w(TCP, False, BOOL)
        p.release_all_pbs()
        p.park_all_home()
        p.set_plate(True)

        # NORMALISE before asserting anything. The procedure used to assume it
        # started from a clean machine, so a previous run that ended in ERR made
        # group C fail for a reason that had nothing to do with group C: ERR is
        # excluded from the Manual re-park, so "Manual -> Auto parks in
        # NOT_HOMED" could not hold. Clear a latched fault, then disarm.
        # ...and normalise the two bench flags, which is not optional. Both are
        # PERSISTENT. Left TRUE by an earlier session they invalidate most of
        # this procedure, and NOT by failing honestly:
        #   bBypassPlateSensors suppresses the CHECK_PLATE timeout ERROR, so the
        #     E/F groups cannot provoke error 9 at all -- the cycle carries on
        #     into GRIP_EXTENDING instead of latching ERR;
        #   bNoSensors then advances every movement state on tStepTimeoutMs
        #     rather than on sensors, so the machine walks the whole bulb on
        #     timers and the coil assertions see the master cycle driving, not
        #     the jog they were testing.
        # Observed 2026-08-05: 14 of 58 checks failed this way after a rebuild,
        # with symptoms (coils energised in Auto/IDLE, PUSH_EXTENDING where IDLE
        # was expected) that read exactly like PLC faults. Same lesson as the
        # eStep normalisation below -- assume nothing about the machine we
        # inherit, and report what was changed.
        p.w(NOSENS, False, BOOL)
        p.w(BYPASS, False, BOOL)
        time.sleep(SETTLE)
        if orig_nosens or orig_bypass:
            print("  normalised: bNoSensors=%s bBypassPlateSensors=%s -> both FALSE"
                  % (orig_nosens, orig_bypass))

        entry_step = p.step_name()
        if p.step() == 99:
            p.w("GVL_HMI.stMasterAuto.bReset", True, BOOL)
            p.wait_step(0, timeout=10)
        p.w(AUTO, True, BOOL)
        time.sleep(SETTLE)
        p.w("GVL_HMI.stMasterAuto.bStop", True, BOOL)
        time.sleep(0.3)
        if p.step_name() != "NOT_HOMED":
            raise RuntimeError(
                "could not normalise to NOT_HOMED (entered as %s, now %s)"
                % (entry_step, p.step_name()))
        print("  normalised: %s -> NOT_HOMED" % entry_step)

        env = {
            "started": started, "net_id": net_id, "ams_port": 851,
            "host": platform.node(), "python": platform.python_version(),
            "step_at_entry": entry_step,
            "auto_at_entry": orig_auto,
            "nosensors_at_entry": orig_nosens,
            "bypass_plate_at_entry": orig_bypass,
            "tcp_disabled_for_run": True,
        }

        # ================================================================
        group("A", "LED wiring — dumb press mirrors",
              "LED1/LED2 mirror the raw press in every state. LED3 does not: "
              "it is a state prompt in Auto, tested in groups C and D.")
        p.w(AUTO, False, BOOL)          # Manual
        time.sleep(SETTLE)
        check("A0", "machine reports Manual", 30,
              p.r("GVL_Robot.stParams.nStateOut", pyads_int()))

        for pb in (1, 2, 3):
            p.press(pb)
            on = p.led(pb)
            p.release(pb)
            off = p.led(pb)
            check(f"A{pb}", f"PB{pb} press/release drives LED{pb} (dOut"
                            f"[{6 + pb}]) in Manual", (True, False), (on, off))

        # ================================================================
        group("B", "Manual jogs — the operator's normal use",
              "Held extends the group, released retracts it. PB1 grip, "
              "PB2 Sep, PB3 Push.")
        for pb in (1, 2, 3):
            jog_group_moves(p, pb, f"B{pb}", True, "in Manual")

        # ================================================================
        group("C", "Automatic + NOT_HOMED — un-armed, PB3 is START",
              "The power-up state. Nothing may move; PB3's LED prompts and "
              "PB1/PB2 are ignored.")
        p.w(AUTO, True, BOOL)
        time.sleep(0.3)
        check("C0", "Manual -> Auto parks in NOT_HOMED", "NOT_HOMED", p.step_name())

        blink = p.sample(f"GVL_IO.dOut[9]", 1.7)
        ok_blink = (True in blink) and (False in blink)
        record("C1", "PB3 LED blinks 'press me to arm' (unpressed)",
               "both ON and OFF observed", f"ON x{blink.count(True)}, "
               f"OFF x{blink.count(False)} over {len(blink)} samples @50ms",
               ok_blink, evidence="".join("#" if b else "." for b in blink))

        lam = p.lamps()
        check("C2", "status lamps: green OFF (not armed), red OFF (no fault)",
              {"green": False, "red": False}, lam)

        jog_group_moves(p, 1, "C3", False, "in Auto/NOT_HOMED")
        jog_group_moves(p, 2, "C4", False, "in Auto/NOT_HOMED")

        idx0 = p.log_idx()
        p.press(3)
        p.release(3)
        reached = p.wait_step(0)
        entries = p.log_since(idx0)
        want = ["NOT_HOMED"] + HOMING + ["IDLE"]
        got = transitions(entries)
        record("C5", "PB3 press = operator START: homes, then arms",
               " -> ".join(want), " -> ".join(got) or "(no transition logged)",
               reached and got == want, evidence=fmt_log(entries))

        check("C6", "PB3 LED off once armed (prompt withdrawn)", False, p.led(3))
        check("C7", "green lamp steady in IDLE", {"green": True, "red": False},
              p.lamps())

        # ================================================================
        group("D", "Automatic + IDLE — armed, still no PB jog",
              "Only the robot's CMD:1 may start a bulb. PB jogs must stay "
              "shut here, and in every other Automatic state.")
        jog_group_moves(p, 1, "D1", False, "in Auto/IDLE")
        jog_group_moves(p, 2, "D2", False, "in Auto/IDLE")
        jog_group_moves(p, 3, "D3", False, "in Auto/IDLE")

        # START in IDLE is IGNORED since 2026-08-05 -- it used to re-home. The
        # press is still logged, so "logged but no transition" is the pass.
        idx0 = p.log_idx()
        p.press(3)
        p.release(3)
        time.sleep(0.4)
        entries = p.log_since(idx0)
        got = transitions(entries)
        logged = any("START" in e["msg"].upper() for e in entries)
        record("D4", "PB3 in IDLE does NOTHING (no re-home, no bulb)",
               "IDLE throughout, press logged",
               f"{p.step_name()}, transitions: "
               f"{' -> '.join(got) if got else 'none'}, "
               f"logged: {logged}",
               p.step_name() == "IDLE" and not got and logged,
               evidence=fmt_log(entries))

        # ================================================================
        group("E", "Automatic + ERR — manual moves must be REFUSED",
              "Fault raised for real: a bulb cycle is started with both plate "
              "sensors clear, so CHECK_PLATE times out with error 9. The jog "
              "window that briefly existed here is gone -- these guard that.")
        p.w(PLATE_TMO, 700, UDINT)
        p.set_plate(False)
        idx0 = p.log_idx()
        p.w("GVL_HMI.stMasterAuto.bSimStartAssembly", True, BOOL)
        reached = p.wait_step(99, timeout=12)
        entries = p.log_since(idx0)
        got = transitions(entries)
        # An ERR arrival logs sErrorText, not 'PREV -> NEW', so the chain stops
        # at CHECK_PLATE and the fault shows as a separate ERR-severity entry.
        want = ["IDLE"] + HOMING + ["CHECK_PLATE"]
        record("E0", "a bulb cycle with no plate faults at CHECK_PLATE",
               " -> ".join(want) + " + ERR entry",
               " -> ".join(got) + (" + ERR entry" if has_sev(entries, "ERR")
                                   else " + NO ERR entry"),
               reached and got == want and has_sev(entries, "ERR"),
               evidence=fmt_log(entries))
        check("E1", "error code 9 = plate never arrived", 9, p.err_code())
        check("E2", "status lamps: red ON, green OFF",
              {"green": False, "red": True}, p.lamps())

        # Manual moves are NOT available in any Automatic state (operator
        # decision 2026-08-05). These are the regression guard on that removal:
        # the ERR jog window that used to make them pass is gone.
        jog_group_moves(p, 1, "E3", False, "in Auto/ERR")
        jog_group_moves(p, 3, "E4", False, "in Auto/ERR")

        check("E5", "PB3 LED stays off in ERR", (False, False),
              (led_on_press(p, 3), p.led(3)))
        check("E6", "PB3 in ERR does not clear the fault", ("ERR", 9),
              (p.step_name(), p.err_code()))

        # ================================================================
        group("F", "Recovery — RESET homes, it does not jump to IDLE",
              "A fault leaves the pistons anywhere, so IDLE would advertise "
              "'ready' while it is not.")
        p.set_plate(True)
        p.park_all_home()
        idx0 = p.log_idx()
        # PB2 is the operator RESET in ERR now, so press the button rather than
        # writing the field -- that way the new mapping is what gets tested.
        p.press(2)
        p.release(2)
        reached = p.wait_step(0, timeout=8)
        entries = p.log_since(idx0)
        want = ["ERR"] + RECOVER + ["IDLE"]
        got = transitions(entries)
        record("F0", "PB2 in ERR = RESET, and recovery runs its own chain",
               " -> ".join(want), " -> ".join(got) or "(no transition logged)",
               reached and got == want, evidence=fmt_log(entries))
        check("F1", "error cleared", 0, p.err_code())
        check("F2", "lamps back to armed-idle", {"green": True, "red": False},
              p.lamps())
        jog_group_moves(p, 1, "F3", False, "back in Auto/IDLE")

        # ================================================================
        group("G", "The two Automatic hold gestures",
              "PB1 held disarms. PB2+PB3 held runs one bulb, the operator's "
              "parallel to the robot's CMD:1. Both durations are read live "
              "from stMasterAutoCfg.")
        hold_stop = p.r(PB_STOP_MS, UDINT) / 1000.0
        hold_start = p.r(PB_START_MS, UDINT) / 1000.0

        short = max(0.05, hold_stop * 0.4)
        p.press(1, settle=short)
        early = p.step_name()
        p.release(1)
        check("G0", "PB1 held %.2fs (under the %.2fs preset) does nothing"
              % (short, hold_stop), "IDLE", early)

        idx0 = p.log_idx()
        p.press(1, settle=hold_stop + 0.4)
        p.release(1)
        check("G1", "PB1 held %.2fs disarms to NOT_HOMED" % hold_stop,
              "NOT_HOMED", p.step_name())
        record("G2", "and it DISARMS rather than faulting", "iErrorCode 0",
               "iErrorCode %d" % p.err_code(), p.err_code() == 0,
               evidence=fmt_log(p.log_since(idx0)))

        p.press(3)
        p.release(3)
        assert p.wait_step(0), "could not re-arm with PB3"

        # PB3 alone must not move the machine. THAT is what makes the combo
        # reliable: a green-before-orange press cannot leave IDLE, so the
        # combo's one-scan pulse always lands where something consumes it.
        idx0 = p.log_idx()
        p.press(3)
        p.release(3)
        time.sleep(0.4)
        got = transitions(p.log_since(idx0))
        record("G3", "PB3 alone from IDLE does nothing — no state change",
               "IDLE, no transitions", f"{p.step_name()}, "
               f"{' -> '.join(got) if got else 'no transitions'}",
               p.step_name() == "IDLE" and not got)

        # The claim under test is "the combo starts a BULB, not a re-home".
        # Entering CHECK_PLATE is exactly that claim: it is the bulb-cycle exit
        # of the retract chain, and G3 has just shown PB3 alone takes the other
        # exit back to IDLE. Running the bulb to completion is NOT tested here
        # -- the harness only asserts the retracted sensors, so the cycle would
        # stall in GRIP_EXTENDING waiting for an extend sensor that never comes
        # (that is field check FLD6, on real sensors).
        p.set_plate(True)
        idx0 = p.log_idx()
        p.w("GVL_IO.dIn[%d]" % PB_DI[2], True, BOOL)
        p.w("GVL_IO.dIn[%d]" % PB_DI[3], True, BOOL)
        time.sleep(hold_start + 0.4)
        p.release_all_pbs()
        reached = p.wait_step([20, 21], timeout=15)
        entries = p.log_since(idx0)
        got = transitions(entries)
        want = ["IDLE"] + HOMING + ["CHECK_PLATE"]
        record("G4", "PB2+PB3 held starts a BULB from IDLE, not a re-home",
               " -> ".join(want) + " ...", " -> ".join(got) or "(none)",
               reached and got[:len(want)] == want, evidence=fmt_log(entries))

        # G5 -- the regression that removing START-in-IDLE was for. Pressing
        # GREEN first used to fire a re-home, and the combo pulse could then
        # land mid-chain where nothing consumes it, silently losing the bulb.
        p.release_all_pbs()
        p.park_all_home()
        p.set_plate(True)
        if p.step() == 99:
            p.w("GVL_HMI.stMasterAuto.bReset", True, BOOL)
            p.wait_step(0, timeout=10)
        if p.step_name() != "IDLE":
            p.w("GVL_HMI.stMasterAuto.bStop", True, BOOL)
            time.sleep(0.3)
            p.press(3)
            p.release(3)
            p.wait_step(0, timeout=10)
        idx0 = p.log_idx()
        p.w("GVL_IO.dIn[%d]" % PB_DI[3], True, BOOL)     # GREEN first
        time.sleep(0.2)
        p.w("GVL_IO.dIn[%d]" % PB_DI[2], True, BOOL)     # then ORANGE
        time.sleep(hold_start + 0.4)
        p.release_all_pbs()
        reached = p.wait_step([20, 21], timeout=15)
        entries = p.log_since(idx0)
        got = transitions(entries)
        record("G5", "GREEN-before-ORANGE still starts the bulb (no lost request)",
               "reaches CHECK_PLATE with no spurious re-home first",
               " -> ".join(got) or "(none)",
               reached and got[:1] == ["IDLE"] and "CHECK_PLATE" in got,
               evidence=fmt_log(entries))

        log_tail = p.log_head(20)

        # ---------------- restore ---------------------------------------
        print("\n--- restoring PLC state ---")
        p.release_all_pbs()
        # STOP is excluded from ERR by design, so a latched fault has to be
        # RESET first or the panel is left sitting in ERR. G4 deliberately
        # leaves the cycle mid-bulb, which then times out, so this matters.
        p.park_all_home()
        if p.step() == 99:
            p.w("GVL_HMI.stMasterAuto.bReset", True, BOOL)
            p.wait_step(0, timeout=8)
        p.w("GVL_HMI.stMasterAuto.bStop", True, BOOL)   # disarm to NOT_HOMED
        time.sleep(0.3)
        p.restore()
        time.sleep(0.3)
        p.release_all_pbs()
        # FB_PersistentAutoSave flushes ~2 s after the last edit; wait for it
        # so the restored persistent values actually reach bootdata.
        time.sleep(3.5)
        env["step_at_exit"] = p.step_name()
        env["auto_at_exit"] = p.r(AUTO, BOOL)
        env["finished"] = time.strftime("%Y-%m-%d %H:%M:%S")
        print(f"  step={env['step_at_exit']}  bAutoMode={env['auto_at_exit']}"
              f"  err={p.err_code()}")

    return env, log_tail


def pyads_int():
    import pyads
    return pyads.PLCTYPE_INT


def led_on_press(p, pb):
    p.press(pb)
    v = p.led(pb)
    p.release(pb)
    return v


def fmt_log(entries):
    return " | ".join(f"{e['sev']} {e['time']} {e['msg']}" for e in entries)


# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--net", default="127.0.0.1.1.1",
                    help="target AmsNetId (default: local runtime)")
    ap.add_argument("--no-html", action="store_true")
    a = ap.parse_args()

    here = os.path.dirname(os.path.abspath(__file__))
    repo = os.path.abspath(os.path.join(here, "..", ".."))

    try:
        env, log_tail = run(a.net)
    except Exception as e:                              # noqa: BLE001
        print(f"\nABORTED: {type(e).__name__}: {e}")
        return 2

    npass = sum(r["status"] == "PASS" for r in RESULTS)
    nfail = len(RESULTS) - npass
    payload = {"env": env, "results": RESULTS, "log_tail": log_tail,
               "summary": {"total": len(RESULTS), "pass": npass, "fail": nfail}}

    with open(os.path.join(here, "last_run.json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    if not a.no_html:
        from pb_report import write_report
        out = os.path.join(repo, "docs", "pb-test-report.html")
        write_report(payload, out)
        print(f"\nreport: {out}")

    print(f"\n{npass}/{len(RESULTS)} checks passed"
          + (f", {nfail} FAILED" if nfail else ""))
    return 1 if nfail else 0


if __name__ == "__main__":
    raise SystemExit(main())
