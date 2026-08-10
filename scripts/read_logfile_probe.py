"""Run and read FB_LogFileSpike -- the Phase 0 gate of docs/plans/log-csv-file.md.

    python scripts/read_logfile_probe.py --net 5.79.93.36.1.1 --run
    python scripts/read_logfile_probe.py --net 5.79.93.36.1.1          # read only

THROWAWAY, like the FB it reads. Delete both once the gate has been answered.

It exists because the CP6606 has no way to show a file: WinCE 7 has no viewer and
no supported CPython. So the only way to find out whether the panel can write a
file, and where, is to have the PLC try and report back over ADS. That is the
whole of Phase 0.

WHAT TO CONCLUDE FROM THE OUTPUT, which is the part worth getting right:

  * candidate 1 (PATH_BOOTPATH) OK  -> file I/O works on this target. Proceed.
    Any further OK just tells you where an operator could more conveniently
    reach the file.
  * candidate 1 FAILS, others OK    -> unexpected; trust the others but say so,
    because PATH_BOOTPATH is the one location known to be writable already.
  * NOTHING OK                      -> the gate has failed. Do NOT start Phase 1.
    Read nOpenErr on candidate 1: a real ADS/file error number means the blocks
    are there and refusing, whereas 0 with bOpened FALSE means the call never
    completed and the FB or the task is the problem, not the filesystem.

Exit 0 = at least one candidate worked, 1 = none did, 2 = could not run.
"""
from __future__ import annotations

import argparse
import sys
import time

import pyads

ROOT = "GVL_Log"
N_CAND = 6
PATH_SEL = {0: "PATH_GENERIC", 1: "PATH_BOOTPATH", 2: "PATH_USERPATH1"}


def rd(plc, sym, typ):
    return plc.read_by_name(f"{ROOT}.{sym}", typ)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--net", default="127.0.0.1.1.1",
                    help="AMS net id; the panel is 5.79.93.36.1.1")
    ap.add_argument("--port", type=int, default=851)
    ap.add_argument("--run", action="store_true",
                    help="trigger a fresh sweep instead of reading the last one")
    ap.add_argument("--timeout", type=float, default=60.0)
    a = ap.parse_args()

    plc = pyads.Connection(a.net, a.port)
    try:
        plc.open()
        plc.read_state()
    except Exception as exc:  # noqa: BLE001
        print(f"cannot reach {a.net}:{a.port} -- {exc}")
        return 2

    try:
        # Resolve one probe symbol first, so "not built yet" is reported as
        # itself rather than as a mysterious zero-filled table.
        try:
            rd(plc, "bLogFileProbeDone", pyads.PLCTYPE_BOOL)
        except Exception:  # noqa: BLE001
            print("GVL_Log.bLogFileProbeDone does not resolve.\n"
                  "The probe is committed but this runtime has not been built and\n"
                  "activated with it yet -- do that first.")
            return 2

        if a.run:
            print("triggering a sweep ...")
            plc.write_by_name(f"{ROOT}.bLogFileProbeRun", True, pyads.PLCTYPE_BOOL)
            end = time.time() + a.timeout
            while time.time() < end:
                if rd(plc, "bLogFileProbeDone", pyads.PLCTYPE_BOOL):
                    break
                time.sleep(0.1)
            else:
                busy = rd(plc, "bLogFileProbeBusy", pyads.PLCTYPE_BOOL)
                print(f"timed out after {a.timeout:.0f}s (busy={busy}). "
                      "A file call may be blocking; read the table anyway.")

        if not rd(plc, "bLogFileProbeDone", pyads.PLCTYPE_BOOL):
            print("No completed sweep on this runtime. Re-run with --run.")
            return 2

        n_ok = rd(plc, "nLogFileProbeOk", pyads.PLCTYPE_INT)
        first = rd(plc, "iLogFileProbeFirst", pyads.PLCTYPE_INT)

        print(f"\n{'#':>2}  {'ok':<4}{'open':<6}{'write':<7}{'close':<7}"
              f"{'ePath':<15}path")
        print("-" * 100)
        rows = []
        for i in range(1, N_CAND + 1):
            g = lambda f, t: plc.read_by_name(  # noqa: E731
                f"{ROOT}.aLogFileProbe[{i}].{f}", t)
            r = {
                "what": g("sWhat", pyads.PLCTYPE_STRING),
                "path": g("sPathName", pyads.PLCTYPE_STRING),
                "sel": g("nPath", pyads.PLCTYPE_INT),
                "op": g("bOpened", pyads.PLCTYPE_BOOL),
                "wr": g("bWrote", pyads.PLCTYPE_BOOL),
                "cl": g("bClosed", pyads.PLCTYPE_BOOL),
                "eo": g("nOpenErr", pyads.PLCTYPE_UDINT),
                "ew": g("nWriteErr", pyads.PLCTYPE_UDINT),
                "ec": g("nCloseErr", pyads.PLCTYPE_UDINT),
                "ok": g("bOk", pyads.PLCTYPE_BOOL),
            }
            rows.append(r)
            f = lambda flag, err: (  # noqa: E731
                "yes" if flag and not err else (f"e{err}" if err else "no"))
            print(f"{i:>2}  {'OK' if r['ok'] else '--':<4}"
                  f"{f(r['op'], r['eo']):<6}{f(r['wr'], r['ew']):<7}"
                  f"{f(r['cl'], r['ec']):<7}"
                  f"{PATH_SEL.get(r['sel'], '?'):<15}{r['path']}")
        print()
        for i, r in enumerate(rows, 1):
            print(f"  {i}. {r['what']}")

        print(f"\n{n_ok} of {N_CAND} candidates fully worked; first = {first}")

        if n_ok == 0:
            eo = rows[0]["eo"]
            print("\nGATE FAILED -- do not start Phase 1.")
            print(f"Candidate 1 (PATH_BOOTPATH) openErr = {eo}.")
            print("  nonzero -> the file blocks exist and are refusing; that error"
                  " number is the\n             real finding, look it up before"
                  " changing anything.")
            print("  zero    -> the call never completed. Suspect the FB or the"
                  " task, not the\n             filesystem.")
            return 1

        print("\nGATE PASSED -- file I/O works on this target.")
        if not rows[0]["ok"]:
            print("NOTE candidate 1 (PATH_BOOTPATH) did NOT work, which is"
                  " unexpected: that is\nthe one directory already known to be"
                  " writable. Trust the passes below it,\nbut treat this as worth"
                  " understanding.")
        print(f"Carry this into stLogFileCfg.sDir in Phase 1:"
              f"  {rows[first - 1]['path']}")
        print(f"  (via {PATH_SEL.get(rows[first - 1]['sel'], '?')})")
        return 0
    finally:
        plc.close()


if __name__ == "__main__":
    raise SystemExit(main())
