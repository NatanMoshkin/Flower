"""Panel push-button test procedure — runs against a LIVE PLC over ADS.

Covers every documented PB behaviour in CLAUDE.md's "PANEL HARDWARE" section,
including the ERR jog window added 2026-08-04. Presses are simulated by
writing GVL_IO.dIn[13..15]; see pb_io.py for why that is the only way.

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
    BOOL, UDINT, COIL_DO, PB_JOG_GROUP, Plc, SETTLE, has_sev, transitions,
)

HOMING = ["INIT_PUSH_RETRACTING", "INIT_SEP_RETRACTING", "INIT_GRIP_RETRACTING"]

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
        AUTO = "GVL_HmiPersistent.stMasterAutoCfg.bAutoMode"
        PLATE_TMO = "GVL_HmiPersistent.stMasterAutoCfg.tPlateWaitTimeoutMs"
        TCP = "GVL_Robot.bTcpEnable"
        orig_auto = p.save(AUTO, BOOL)
        p.save(PLATE_TMO, UDINT)
        p.save(TCP, BOOL)
        for i in range(1, 25):
            p.save(f"GVL_IO.dIn[{i}]", BOOL)

        # The robot is not on this network, so FB_RobotTcpClient logs a
        # connect failure every 3 s and would flush the 20-entry ring before
        # we could read it. Disabling the link also keeps ERR stable: with no
        # robot there is no CMD:2, which is exactly the condition the ERR jog
        # window needs. On the real machine the robot closes it in ~1 s.
        p.w(TCP, False, BOOL)
        p.release_all_pbs()
        p.park_all_home()
        p.set_plate(True)

        env = {
            "started": started, "net_id": net_id, "ams_port": 851,
            "host": platform.node(), "python": platform.python_version(),
            "step_at_entry": p.step_name(),
            "auto_at_entry": orig_auto,
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
              "shut here; this is the regression guard on bJogEnable.")
        jog_group_moves(p, 1, "D1", False, "in Auto/IDLE")
        jog_group_moves(p, 2, "D2", False, "in Auto/IDLE")
        jog_group_moves(p, 3, "D3", False, "in Auto/IDLE")

        idx0 = p.log_idx()
        p.press(3)
        p.release(3)
        reached = p.wait_step(0, timeout=5)
        entries = p.log_since(idx0)
        want = ["IDLE"] + HOMING + ["IDLE"]
        got = transitions(entries)
        record("D4", "PB3 in IDLE re-homes, it does NOT run a bulb cycle",
               " -> ".join(want), " -> ".join(got) or "(no transition logged)",
               reached and got == want, evidence=fmt_log(entries))

        # ================================================================
        group("E", "Automatic + ERR — the new jog window (2026-08-04)",
              "Fault raised for real: a bulb cycle is started with both plate "
              "sensors clear, so WAIT_PLATE times out with error 9.")
        p.w(PLATE_TMO, 700, UDINT)
        p.set_plate(False)
        idx0 = p.log_idx()
        p.w("GVL_HMI.stMasterAuto.bSimStartAssembly", True, BOOL)
        reached = p.wait_step(99, timeout=12)
        entries = p.log_since(idx0)
        got = transitions(entries)
        # An ERR arrival logs sErrorText, not 'PREV -> NEW', so the chain stops
        # at WAIT_PLATE and the fault shows as a separate ERR-severity entry.
        want = ["IDLE"] + HOMING + ["WAIT_PLATE"]
        record("E0", "a bulb cycle with no plate faults at WAIT_PLATE",
               " -> ".join(want) + " + ERR entry",
               " -> ".join(got) + (" + ERR entry" if has_sev(entries, "ERR")
                                   else " + NO ERR entry"),
               reached and got == want and has_sev(entries, "ERR"),
               evidence=fmt_log(entries))
        check("E1", "error code 9 = plate never arrived", 9, p.err_code())
        check("E2", "status lamps: red ON, green OFF",
              {"green": False, "red": True}, p.lamps())

        # The three jogs that did nothing in group D must work here.
        jog_group_moves(p, 1, "E3", True, "in Auto/ERR")
        jog_group_moves(p, 2, "E4", True, "in Auto/ERR")
        jog_group_moves(p, 3, "E5", True, "in Auto/ERR")

        check("E6", "PB3 LED reverts to a press mirror in ERR (jog feedback)",
              (True, False), (led_on_press(p, 3), p.led(3)))

        idx0 = p.log_idx()
        p.press(3)
        p.release(3)
        time.sleep(0.3)
        entries = p.log_since(idx0)
        started_logged = any("START" in e["msg"].upper() for e in entries)
        record("E7", "PB3 in ERR does NOT log a spurious 'START pressed'",
               "no START entry", "START entry present" if started_logged
               else "none", not started_logged, evidence=fmt_log(entries))
        check("E8", "PB3 in ERR does not clear the fault", ("ERR", 9),
              (p.step_name(), p.err_code()))
        check("E9", "bStart was never written", False,
              p.r("GVL_HMI.stMasterAuto.bStart", BOOL))

        # ================================================================
        group("F", "Recovery — RESET homes, it does not jump to IDLE",
              "A fault leaves the pistons anywhere, so IDLE would advertise "
              "'ready' while it is not.")
        p.set_plate(True)
        p.park_all_home()
        idx0 = p.log_idx()
        p.w("GVL_HMI.stMasterAuto.bReset", True, BOOL)
        reached = p.wait_step(0, timeout=8)
        entries = p.log_since(idx0)
        want = ["ERR"] + HOMING + ["IDLE"]
        got = transitions(entries)
        record("F0", "RESET homes; it does NOT jump straight to IDLE",
               " -> ".join(want), " -> ".join(got) or "(no transition logged)",
               reached and got == want, evidence=fmt_log(entries))
        check("F1", "error cleared", 0, p.err_code())
        check("F2", "lamps back to armed-idle", {"green": True, "red": False},
              p.lamps())
        jog_group_moves(p, 1, "F3", False, "back in Auto/IDLE")

        log_tail = p.log_head(20)

        # ---------------- restore ---------------------------------------
        print("\n--- restoring PLC state ---")
        p.release_all_pbs()
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
