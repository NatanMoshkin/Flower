"""Retarget the Logs page Sev column from the enum to its STRING mirror.

The column was originally bound to `GVL_Log.aRecent[i].eSev` on the
assumption that {attribute 'to_string'} would make the classic VISU print
the enumerator name. It does not -- to_string only enables TO_STRING() in
ST -- so the column rendered 0..3. `ST_LogEntry.sSevText` now carries the
text, set by F_LogEvent.

This only rewrites the displayed-variable member (2477733581L) on the 20
cells already bound to `.eSev`. It touches no geometry, no identity field
and no other column, which is why it is a plain retarget rather than a
rebuild -- build_log_page.py refuses to run once Logs.TcVIS exists.

Idempotent: bails out if the page already binds sSevText.

Run:  python scripts/fix_logs_sev_column.py
Then: python scripts/validate_visu.py
      python scripts/check_pyhmi_contract.py
      ...and rebuild in TcXaeShell.
"""

from __future__ import annotations

import pathlib
import re
import sys

DST = pathlib.Path(__file__).resolve().parents[1] / (
    "Panel_PLC_HMI/167_01_Saad_PLC/167_01_Saad_PLC/PLC1/VISU/Logs.TcVIS")

M_TEXTVAR = "2477733581L"
ROWS = 20


def main():
    text = DST.read_text(encoding="utf-8")
    if "sSevText" in text:
        print("Sev column already bound to sSevText - nothing to do.")
        return 0

    # Anchor on the member id so we rewrite the *displayed variable* and not
    # some other member that happens to hold the same string.
    pat = re.compile(
        r'(<v n="Id">' + re.escape(M_TEXTVAR) + r'</v>\s*\n\s*<v n="Value"[^>]*>"'
        r'GVL_Log\.aRecent\[(\d+)\]\.)eSev("</v>)')
    seen = []

    def sub(m):
        seen.append(int(m.group(2)))
        return m.group(1) + "sSevText" + m.group(3)

    out, n = pat.subn(sub, text)
    if n != ROWS:
        raise SystemExit(f"expected {ROWS} Sev cells, rewrote {n} - aborting "
                         f"without writing (indices found: {sorted(seen)})")
    if sorted(seen) != list(range(ROWS)):
        raise SystemExit(f"expected aRecent[0..{ROWS - 1}], got {sorted(seen)}")

    DST.write_text(out, encoding="utf-8")
    print(f"retargeted {n} Sev cells: aRecent[0..{ROWS - 1}].eSev "
          f"-> .sSevText")

    # The other two columns must be untouched.
    for member, count in (("sSource", ROWS), ("sMsg", ROWS)):
        got = out.count(f".{member}")
        if got != count:
            raise SystemExit(f"{member}: expected {count} bindings, found {got}")
    print("verified: Source and Message columns unchanged")
    return 0


if __name__ == "__main__":
    sys.exit(main())
