"""Run ONE complete bulb cycle on a bench PLC and check the coil pattern of
every state against what the source says it drives.

This is the end-to-end check on the ResetAllCommands refactor (2026-08-05),
which rewrote all twelve motion CASE bodies from "explicit clears mixed with
commands held by omission" to "reset everything, then re-assert what I own".
That change is claimed to be behaviour-identical; this is what demonstrates it.

pb_test_procedure.py cannot do this: it only ever asserts the RETRACTED sensors,
so a cycle stalls in GRIP_EXTENDING waiting for an extend sensor that never
arrives. Here a background follower emulates all eight pistons -- when a coil
energises, its extended sensor makes shortly after; when it drops, its retracted
sensor makes -- so the sequence runs to completion the way it would on air.

    python scripts/pb_test/cycle_trace.py [--net 5.79.93.36.1.1]

Bench targets only: it drives coils and runs the master cycle.
Exit 0 = every observed pattern matched, 1 = a mismatch, 2 = aborted.
"""

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pb_io import BOOL, UDINT, COIL_DO, SENSOR_DI, Plc, SETTLE  # noqa: E402

# Coil truth per state, read off FB_MasterAutoCycle Section 4.
# A coil is TRUE only while an EXTEND command is asserted; a retract command or
# no command at all leaves it FALSE (the ladder retains, and every one of these
# states was reached from a state that had already dropped it).
SEP, PUSH, GRIP = ["Sep1", "Sep2", "Sep3"], ["Push1", "Push2", "Push3"], ["GripL", "GripR"]
EXPECT = {
    "CHECK_PLATE":          ([], "nothing driven; waiting for the plate"),
    "GRIP_EXTENDING":       (GRIP, "clamp the plate"),
    "SEP_EXTENDING":        (SEP + GRIP, "separators out, clamp held"),
    "PUSH_EXTENDING":       (SEP + PUSH + GRIP, "the force stroke"),
    "DWELL_PUSH":           (SEP + PUSH + GRIP, "everything held out"),
    "PUSH_RETRACTING":      (SEP + GRIP, "push retracting, sep still out"),
    "PUSH_RETRACTED_DWELL": (SEP + GRIP, "push home, sep out, clamped"),
    "SEP_RETRACTING":       (GRIP, "sep retracting, plate still clamped"),
    "SEP_RETRACTED_DWELL":  (GRIP, "sep and push home, clamp only"),
    "GRIP_RETRACTING":      ([], "releasing the plate"),
}
ORDER = list(EXPECT)


def follow(p, lag):
    """One pass of the piston emulator: make each piston's sensors agree with
    its coil after `lag` seconds of travel."""
    for name, (ret_di, ext_di) in SENSOR_DI.items():
        energised = p.coil(name)
        moving_to = "ext" if energised else "ret"
        prev = p._travel.get(name)
        if prev != moving_to:
            p._travel[name] = moving_to
            p._since[name] = time.time()
            # leave the fixture: neither sensor made while in transit
            p.w(f"GVL_IO.dIn[{ret_di}]", False)
            p.w(f"GVL_IO.dIn[{ext_di}]", False)
        elif time.time() - p._since.get(name, 0) >= lag:
            p.w(f"GVL_IO.dIn[{ext_di}]", energised)
            p.w(f"GVL_IO.dIn[{ret_di}]", not energised)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--net", default="127.0.0.1.1.1")
    ap.add_argument("--lag", type=float, default=0.08,
                    help="emulated piston travel time, seconds")
    a = ap.parse_args()

    seen, bad = {}, []
    with Plc(a.net) as p:
        p._travel, p._since = {}, {}
        # Volatile GVL_HMI since 2026-08-06, not the persistent cfg struct.
        AUTO = "GVL_HMI.bAutoMode"
        TCP = "GVL_Robot.bTcpEnable"
        p.save(AUTO, BOOL)
        p.save(TCP, BOOL)
        p.save("GVL_HmiPersistent.stMasterAutoCfg.tPlateWaitTimeoutMs", UDINT)
        for i in range(1, 25):
            p.save(f"GVL_IO.dIn[{i}]", BOOL)

        p.w(TCP, False, BOOL)
        p.release_all_pbs()
        p.park_all_home()
        p.set_plate(True)

        # normalise: clear any latched fault, then arm
        if p.step() == 99:
            p.w("GVL_HMI.stMasterAuto.bReset", True, BOOL)
            p.wait_step(0, timeout=10)
        p.w(AUTO, True, BOOL)
        time.sleep(SETTLE)
        p.w("GVL_HMI.stMasterAuto.bStop", True, BOOL)
        time.sleep(0.3)
        p.w("GVL_HMI.stMasterAuto.bStart", True, BOOL)
        if not p.wait_step(0, timeout=10):
            print(f"ABORT: could not arm (stuck at {p.step_name()})")
            return 2
        print(f"armed at {p.step_name()}; running one bulb with a "
              f"{a.lag*1000:.0f} ms emulated travel time\n")

        cycles0 = p.r("GVL_HMI.stMasterAuto.nCyclesCompleted", UDINT)
        # Hold the plate off so CHECK_PLATE is actually observable -- with the
        # plate already present it passes in a single scan.
        p.set_plate(False)
        p.w("GVL_HMI.stMasterAuto.bSimStartAssembly", True, BOOL)
        plate_given = False

        deadline = time.time() + 60
        while time.time() < deadline:
            follow(p, a.lag)
            st = p.step_name()
            if st == "CHECK_PLATE" and st in seen and not plate_given:
                p.set_plate(True)          # release it once sampled
                plate_given = True
            if st in EXPECT and st not in seen:
                # SETTLE FIRST. The commands are written by MAIN, the piston FBs
                # turn them into coils, and only then does the 5 ms IOmapTask
                # copy them to dOut. Sampling the instant eStep changes reads
                # dOut from the PREVIOUS scan -- and because the eight coils are
                # eight separate ADS calls, the copy can land mid-way and tear
                # the snapshot. Wait two IO cycles, then confirm the state has
                # not moved on before trusting the sample.
                time.sleep(0.03)
                if p.step_name() == st:
                    seen[st] = {n: p.coil(n) for n in COIL_DO}
            if st == "ERR":
                print(f"ABORT: faulted with error {p.err_code()} "
                      f"after seeing {len(seen)} states")
                break
            if st == "IDLE" and len(seen) >= 2:
                break
            time.sleep(0.02)

        cycles1 = p.r("GVL_HMI.stMasterAuto.nCyclesCompleted", UDINT)
        end_step = p.step_name()

        print("--- restoring ---")
        p.release_all_pbs()
        p.park_all_home()
        if p.step() == 99:
            p.w("GVL_HMI.stMasterAuto.bReset", True, BOOL)
            p.wait_step(0, timeout=8)
        p.w("GVL_HMI.stMasterAuto.bStop", True, BOOL)
        time.sleep(0.3)
        p.restore()
        time.sleep(3.5)
        print(f"  left at {p.step_name()}\n")

    print(f"{'state':<22} {'expected coils':<34} result")
    print("-" * 78)
    for st in ORDER:
        want_on, why = EXPECT[st]
        if st not in seen:
            print(f"{st:<22} {'(never observed)':<34} SKIP")
            continue
        got = seen[st]
        want = {n: (n in want_on) for n in COIL_DO}
        ok = got == want
        label = ", ".join(want_on) if want_on else "none"
        print(f"{st:<22} {label[:34]:<34} {'ok' if ok else 'MISMATCH'}   {why}")
        if not ok:
            for n in COIL_DO:
                if got[n] != want[n]:
                    print(f"{'':<22}   {n}: got {got[n]}, expected {want[n]}")
            bad.append(st)

    print(f"\nstates observed : {len(seen)}/{len(ORDER)}")
    print(f"cycle counter   : {cycles0} -> {cycles1}")
    print(f"ended at        : {end_step}")
    if bad:
        print(f"\n{len(bad)} MISMATCH: " + ", ".join(bad))
        return 1
    if len(seen) < len(ORDER):
        print("\nIncomplete: some states were never observed (raise --lag so the "
              "sampler cannot skip past a state).")
        return 1
    print("\nevery state drove exactly the coils the source says it drives")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
