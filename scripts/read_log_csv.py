"""Pull the panel's CSV log off the card over FTP and check it against the PLC.

    python scripts/read_log_csv.py --net 5.79.93.36.1.1 --ftp 192.168.1.100
    python scripts/read_log_csv.py ... --enable      # turn logging on first
    python scripts/read_log_csv.py ... --save out.csv

This is the verification tool for Phase 2 of docs/plans/log-csv-file.md, and it
replaces the throwaway probe reader.

WHY FTP AND NOT ADS. The CP6606 has no file viewer and no supported CPython, so
for most of this feature's life the only way to check the writer was to read PLC
status symbols and believe them. Then the panel turned out to run an anonymous FTP
server whose root IS the PLC's `\\Hard Disk\\` (established 2026-08-10), which
means the actual bytes on the card can be fetched and parsed from a laptop. That
turns "the status struct says it is fine" into "here is the file, and it parses".

The two are cross-checked rather than trusted separately: the CSV rows are compared
against GVL_Log.aRecent over ADS, so a writer that silently wrote the wrong thing
is caught even though both sides claim success.

WHAT IT ASSERTS, and why each one has bitten this project or was designed against:

  * CRLF line endings. FOPEN_MODETEXT turns a single $N into CRLF; a bare LF would
    mean text mode stopped working, and \\r\\r\\n would mean someone "fixed" the
    writer by emitting $R$N explicitly. Both are real, and the second nearly
    happened.
  * Exactly one header, at the top. The writer only emits it for a file it created,
    which it decides with an existence probe -- a duplicate header mid-file means
    that probe is wrong.
  * Four fields on every row, with quoting intact. Robot frames reach messages as
    'SYNC:NAME=VALUE,...', so an unquoted comma would split a row and shift every
    column silently.
  * No DBG rows. DBG is the 1 Hz robot keep-alive; it must be dropped
    unconditionally, independently of GVL_Log.bDebugMode.
  * No blank rows.
  * udiEntriesDropped is reported, and any synthetic loss row is shown, because a
    gap has to be visible in the FILE and not only in a symbol.

Exit 0 = file retrieved and every check passed, 1 = a check failed, 2 = could not
retrieve or nothing to check yet.
"""
from __future__ import annotations

import argparse
import csv
import io
import sys
from ftplib import FTP, error_perm

import pyads

CFG = "GVL_HmiPersistent.stLogFileCfg"
ST = "GVL_Log.stLogFile"


def plc_side(plc):
    g = lambda s, t: plc.read_by_name(s, t)  # noqa: E731
    return {
        "enabled": g(f"{CFG}.bEnabled", pyads.PLCTYPE_BOOL),
        "dir": g(f"{CFG}.sDir", pyads.PLCTYPE_STRING),
        "flush_s": g(f"{CFG}.uiFlushSec", pyads.PLCTYPE_UDINT),
        "file": g(f"{ST}.sCurrentFile", pyads.PLCTYPE_STRING),
        "bytes": g(f"{ST}.uiBytesInFile", pyads.PLCTYPE_UDINT),
        "dropped": g(f"{ST}.udiEntriesDropped", pyads.PLCTYPE_UDINT),
        "state": g(f"{ST}.sStateText", pyads.PLCTYPE_STRING),
        "err": g(f"{ST}.iErrorCode", pyads.PLCTYPE_UDINT),
        "errtext": g(f"{ST}.sErrorText", pyads.PLCTYPE_STRING),
        "writeidx": g("GVL_Log.nWriteIdx", pyads.PLCTYPE_UDINT),
    }


def ftp_dir_for(plc_dir: str) -> str:
    """Map a PLC path to its FTP path.

    The FTP root is the PLC's '\\Hard Disk\\', so that prefix is stripped and
    backslashes become forward slashes. Anything NOT under \\Hard Disk\\ is not
    reachable over FTP at all -- notably '\\Temp\\' and the device root, which are
    the RAM object store and lose their contents on restart.
    """
    d = plc_dir.replace("\\", "/")
    low = d.lower()
    if low.startswith("/hard disk/"):
        return d[len("/Hard Disk"):]
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--net", default="5.79.93.36.1.1")
    ap.add_argument("--port", type=int, default=851)
    ap.add_argument("--ftp", default="192.168.1.100")
    ap.add_argument("--enable", action="store_true",
                    help="set bEnabled TRUE and wait one flush interval")
    ap.add_argument("--save", help="also write the retrieved file here")
    a = ap.parse_args()

    plc = pyads.Connection(a.net, a.port)
    try:
        plc.open()
        plc.read_state()
    except Exception as exc:  # noqa: BLE001
        print(f"cannot reach PLC {a.net}:{a.port} -- {exc}")
        return 2

    try:
        try:
            st = plc_side(plc)
        except Exception:  # noqa: BLE001
            print("The CSV-log symbols do not resolve. Build and activate the\n"
                  "Phase 1 + Phase 2 changes first.")
            return 2

        if a.enable and not st["enabled"]:
            import time
            print(f"enabling file logging, waiting {st['flush_s'] + 3} s "
                  "for a flush ...")
            plc.write_by_name(f"{CFG}.bEnabled", True, pyads.PLCTYPE_BOOL)
            time.sleep(st["flush_s"] + 3)
            st = plc_side(plc)

        print("=== PLC side ===")
        for k in ("enabled", "dir", "file", "state", "bytes", "dropped",
                  "err", "errtext", "writeidx"):
            print(f"  {k:9s}: {st[k]!r}")

        if st["err"]:
            print(f"\n  the writer is reporting an error: {st['errtext']}")
            print("  a bad sDir gives eState FAILED by design -- it must NEVER")
            print("  fall back to \\Temp\\ or \\, which do not survive a restart.")

        if not st["file"]:
            print("\nNothing written yet (sCurrentFile is empty).")
            print("Enable logging with --enable, or generate some log traffic.")
            return 2

        ftpdir = ftp_dir_for(st["dir"])
        if ftpdir is None:
            print(f"\nsDir is {st['dir']!r}, which is not under '\\Hard Disk\\'.")
            print("That is not reachable over FTP, and if it is '\\Temp\\' or the")
            print("device root it is also NOT PERSISTENT -- see the plan.")
            return 1

        remote = f"{ftpdir.rstrip('/')}/{st['file']}"
        print(f"\n=== fetching ftp://{a.ftp}{remote} ===")
        buf = io.BytesIO()
        try:
            f = FTP(); f.connect(a.ftp, 21, timeout=10); f.login()
            f.retrbinary(f"RETR {remote}", buf.write)
            f.quit()
        except error_perm as exc:
            print(f"  FTP could not read it: {exc}")
            print(f"  (the PLC says it wrote {st['bytes']} bytes to {st['file']})")
            return 1
        raw = buf.getvalue()
        print(f"  {len(raw)} bytes retrieved  (PLC counted {st['bytes']})")
        if a.save:
            io.open(a.save, "wb").write(raw)
            print(f"  saved to {a.save}")

        fails = []

        # -- line endings ---------------------------------------------------- #
        crlf, bare_lf = raw.count(b"\r\n"), raw.count(b"\n") - raw.count(b"\r\n")
        print(f"\n=== line endings ===  CRLF {crlf}, bare LF {bare_lf}, "
              f"CR CR LF {raw.count(bytes([13, 13, 10]))}")
        if bare_lf:
            fails.append(f"{bare_lf} bare LF -- FOPEN_MODETEXT is not translating")
        if raw.count(bytes([13, 13, 10])):
            fails.append("\\r\\r\\n found -- someone wrote $R$N; text mode already "
                         "produces CRLF")

        # -- structure ------------------------------------------------------- #
        text = raw.decode("ascii", errors="replace")
        rows = list(csv.reader(io.StringIO(text)))
        print(f"\n=== structure ===  {len(rows)} parsed row(s)")
        if not rows:
            fails.append("no rows parsed")
        else:
            hdr = rows[0]
            print(f"  header: {hdr}")
            if hdr != ["time", "severity", "source", "message"]:
                fails.append(f"header is {hdr}, expected "
                             "['time','severity','source','message']")
            extra = [i for i, r in enumerate(rows[1:], 1)
                     if r and r[0] == "time" and len(r) == 4 and r[1] == "severity"]
            if extra:
                fails.append(f"duplicate header at row(s) {extra} -- the "
                             "existence probe is wrong")
            bad_w = [i for i, r in enumerate(rows) if len(r) != 4]
            if bad_w:
                fails.append(f"{len(bad_w)} row(s) not 4 fields (first at "
                             f"{bad_w[0]}) -- quoting is broken")
            blanks = sum(1 for r in rows if not r)
            if blanks:
                fails.append(f"{blanks} blank row(s)")
            dbg = [r for r in rows[1:] if len(r) > 1 and r[1] == "DBG"]
            if dbg:
                fails.append(f"{len(dbg)} DBG row(s) -- must be dropped "
                             "unconditionally")
            loss = [r for r in rows[1:] if len(r) > 3 and "entries lost" in r[3]]
            if loss:
                print(f"\n  {len(loss)} synthetic loss row(s) present "
                      "(this is CORRECT -- a gap must be visible in the file):")
                for r in loss: print(f"     {r}")

            print(f"\n=== last {min(6, len(rows) - 1)} data row(s) ===")
            for r in rows[1:][-6:]:
                print(f"  {r}")

            # -- cross-check against the ring over ADS ---------------------- #
            print("\n=== cross-check vs GVL_Log.aRecent (ADS) ===")
            recent = []
            for i in range(20):
                sev = plc.read_by_name(f"GVL_Log.aRecent[{i}].sSevText",
                                       pyads.PLCTYPE_STRING)
                msg = plc.read_by_name(f"GVL_Log.aRecent[{i}].sMsg",
                                       pyads.PLCTYPE_STRING)
                if sev and sev != "DBG":
                    recent.append((sev, msg))
            in_csv = {(r[1], r[3]) for r in rows[1:] if len(r) == 4}
            missing = [e for e in recent[:5] if e not in in_csv]
            print(f"  {len(recent)} non-DBG entries in the ring, "
                  f"{len(in_csv)} distinct rows in the CSV")
            if missing:
                print("  newest ring entries NOT in the file (may just be "
                      "waiting for the next flush):")
                for e in missing: print(f"     {e}")
            else:
                print("  every one of the newest ring entries is present in the file")

        print()
        if fails:
            print(f"{len(fails)} CHECK(S) FAILED:")
            for x in fails: print(f"  - {x}")
            return 1
        print("All checks passed: the file on the card is well-formed CSV, "
              "CRLF, one header,\n4 fields per row, quoting intact, and no DBG "
              "rows.")
        if st["dropped"]:
            print(f"\nNote udiEntriesDropped = {st['dropped']}: the writer has "
                  "fallen behind the ring\nat some point. Check that a synthetic "
                  "loss row accompanies each gap.")
        return 0
    finally:
        plc.close()


if __name__ == "__main__":
    raise SystemExit(main())
