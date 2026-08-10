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

import pyads

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

# Stretched for the duration of the run, then restored. ONE entry, deliberately.
#
# CHECK_PLATE is the one state this script cannot observe at the shipped value,
# and the reason is structural rather than a matter of speed: the plate is
# deliberately withheld so the state is reachable at all, and it is released only
# once the state has been *sampled*, so a plate wait shorter than one sampling
# pass faults with error 9 before the sample can happen. No amount of ADS
# batching removes that ordering. It was invisible before 2026-08-10 only because
# every previous run had bBypassPlateSensors set, which suppresses exactly error 9.
#
# Everything else runs at its configured value on purpose. The movement timeout
# and the three dwells were stretched here for one afternoon while the emulator
# still cost 2.2 s per pass; with it down to ~80-210 ms the shipped 500-1000 ms
# states are comfortably observable, and stretching them would mean the check no
# longer exercises the timings the machine actually runs.
STRETCH = {
    "tPlateWaitTimeoutMs": 15000,
}


def snapshot_coils(p):
    """All eight coils from ONE array read.

    Sampling used to be eight separate `p.coil()` calls. At ~90 ms per round trip
    on the panel that is 720 ms spent *inside* the state being sampled, which on
    its own overruns the 1000 ms step timeout -- GRIP_EXTENDING faulted with error
    10 purely because the observer was too slow, having already been sampled
    correctly. Reading the array once also makes the sample atomic, which is the
    other thing eight separate reads could not promise (see the tear note below).
    """
    dout = p.c.read_by_name("GVL_IO.dOut", pyads.PLCTYPE_BOOL * 16)
    return {n: bool(dout[COIL_DO[n] - 1]) for n in COIL_DO}


def follow(p, lag):
    """One pass of the piston emulator: make each piston's sensors agree with
    its coil after `lag` seconds of travel.

    ONE ROUND TRIP IN, ONE OUT. Measured 2026-08-10, an ADS round trip costs
    ~0.02 ms to a local runtime but **~90 ms to the CP6606 over the LAN**. Done
    naively -- eight coil reads plus sixteen sensor writes -- a pass costs 2.2 s
    on the panel, which made this script's sampling period longer than a state's
    duration and aliased seven of the ten states away. So:

      * all eight coils arrive in a single array read of `GVL_IO.dOut`
        (contiguous ARRAY[1..16] OF BOOL), 78 ms for the lot;
      * every sensor changing this pass goes out as ONE sum-up write, 130 ms for
        all sixteen channels against 1496 ms for sixteen separate calls;
      * a sensor already holding the wanted value is not written at all.

    Sum-up rather than a block write to `GVL_IO.dIn`: a by-name handle to
    `dIn[1]` is one BOOL so a span write is rejected (ADS 1797), and writing the
    whole array would clobber the PB, plate and free channels this does not own.
    """
    dout = p.c.read_by_name("GVL_IO.dOut", pyads.PLCTYPE_BOOL * 16)
    batch = {}
    for name, (ret_di, ext_di) in SENSOR_DI.items():
        energised = bool(dout[COIL_DO[name] - 1])       # dOut is 1-based
        moving_to = "ext" if energised else "ret"
        prev = p._travel.get(name)
        if prev != moving_to:
            p._travel[name] = moving_to
            p._since[name] = time.time()
            want = (False, False)      # in transit: neither sensor made
        elif time.time() - p._since.get(name, 0) >= lag:
            want = (not energised, energised)
        else:
            continue                   # still travelling, nothing to say
        if p._wrote.get(name) != want:
            batch[f"GVL_IO.dIn[{ret_di}]"] = want[0]
            batch[f"GVL_IO.dIn[{ext_di}]"] = want[1]
            p._wrote[name] = want
    if batch:
        p.c.write_list_by_name(batch)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--net", default="127.0.0.1.1.1")
    ap.add_argument("--lag", type=float, default=0.08,
                    help="emulated piston travel time, seconds")
    a = ap.parse_args()

    seen, bad = {}, []
    with Plc(a.net) as p:
        p._travel, p._since, p._wrote = {}, {}, {}
        # Volatile GVL_HMI since 2026-08-06, not the persistent cfg struct.
        AUTO = "GVL_HMI.bAutoMode"
        TCP = "GVL_Robot.bTcpEnable"
        NOSENS = "GVL_HmiPersistent.stMasterAutoCfg.bNoSensors"
        BYPASS = "GVL_HmiPersistent.stMasterAutoCfg.bBypassPlateSensors"
        p.save(AUTO, BOOL)
        p.save(TCP, BOOL)
        p.save(NOSENS, BOOL)
        p.save(BYPASS, BOOL)
        for t in STRETCH:
            p.save(f"GVL_HmiPersistent.stMasterAutoCfg.{t}", UDINT)
        for i in range(1, 25):
            p.save(f"GVL_IO.dIn[{i}]", BOOL)

        # NORMALISE THE TWO BENCH FLAGS, and say what they were. Both are
        # PERSISTENT and survive a power cycle, so a previous session leaves them
        # set -- and pb_test's own teardown restores them to whatever it found.
        # bNoSensors TRUE makes every movement state advance on tStepTimeoutMs
        # INSTEAD of on sensors, which silently bypasses this script's whole
        # reason for existing: the piston emulator below would be driving sensors
        # that nothing consults, and --lag would have no effect whatsoever. That
        # is a false pass, not a pass. pb_test learned this on 2026-08-05; this
        # script did not get the same treatment until 2026-08-10.
        was = {k: p.r(k, BOOL) for k in (NOSENS, BYPASS)}
        if any(was.values()):
            print("  normalised: bNoSensors=%s bBypassPlateSensors=%s -> both FALSE"
                  % (was[NOSENS], was[BYPASS]))
        p.w(NOSENS, False, BOOL)
        p.w(BYPASS, False, BOOL)
        for t, ms in STRETCH.items():
            p.w(f"GVL_HmiPersistent.stMasterAutoCfg.{t}", ms, UDINT)

        p.w(TCP, False, BOOL)
        p.release_all_pbs()
        p.park_all_home()
        p.set_plate(True)
        p._wrote.clear()   # park_all_home wrote sensors behind the cache's back

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
                    seen[st] = snapshot_coils(p)
                    # Release the plate in the SAME iteration it was sampled, not
                    # the next one. A loop pass costs a few hundred ms over the
                    # network, and CHECK_PLATE is on a timeout.
                    if st == "CHECK_PLATE" and not plate_given:
                        p.set_plate(True)
                        plate_given = True
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
