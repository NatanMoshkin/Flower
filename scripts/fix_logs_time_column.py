"""Swap the Logs page middle column from Source to Time.

The page shipped with Sev / Source / Message. Source stays valuable in the
CSV FlowerPyHmi drains, but on a 20-row panel view a wall-clock stamp earns
the column better -- most entries come from one or two sources anyway, and
"when" is what an operator correlating with the robot actually needs.

sSource is NOT removed from ST_LogEntry: FlowerPyHmi still reads and renders
it and the ring still records it. Only the panel column changes.

Rewrites, all block-scoped:
  * the 20 cell bindings, aRecent[i].sSource -> .sTime
  * the header element's own text member, "Source" -> "Time"
  * that header's GlobalTextList entry, so the runtime's text-list lookup
    agrees with the design-time text instead of silently overriding it
  * geometry: Time 150 -> 90 px, Message shifted left and widened to take
    the 60 px back, since HH:MM:SS needs far less room than a source name

Everything is done per ELEMENT BLOCK. An earlier version located each
geometry member by searching backwards from the matched binding string; that
lands in whichever nested <o> happens to be nearest, not the element's own,
and it failed loudly on the first run. The block scanner is correct by
construction -- see the TwinCAT_Classic_VISU_Editing skill.

Idempotent: bails out if the page already binds sTime.

Run:  python scripts/fix_logs_time_column.py
Then: python scripts/validate_visu.py
      ...and rebuild in TcXaeShell.
"""

from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1] / (
    "Panel_PLC_HMI/167_01_Saad_PLC/167_01_Saad_PLC/PLC1")
DST = ROOT / "VISU/Logs.TcVIS"
GTL = ROOT / "GlobalTextList.TcGTLO"

M_TEXTVAR, M_TEXT, M_COUNTER = "2477733581L", "390574330L", "823443203L"
M_LEFT, M_WIDTH = "1649127785L", "2422045748L"
ROWS = 20

TIME_W = 90              # was 150
MSG_X, MSG_W = 178, 602  # was 238 / 542 -- reclaim the 60 px

INDENT_O, INDENT_C = "              <o>", "              </o>"


def blocks(lines):
    """(start, end, body) for every element block."""
    for i, line in enumerate(lines):
        if "VisualElementTypeName" in line:
            s = i
            while lines[s].rstrip("\r\n") != INDENT_O:
                s -= 1
            e = i
            while lines[e].rstrip("\r\n") != INDENT_C:
                e += 1
            yield s, e, "".join(lines[s:e + 1])


def _member_pat(mid, value_re=r'(.*?)'):
    return re.compile(r'(<v n="Id">' + re.escape(mid) +
                      r'</v>\s*\n\s*<v n="Value"[^>]*>)' + value_re +
                      r'(</v>)', re.DOTALL)


def set_member(text, mid, value):
    out, n = _member_pat(mid).subn(
        lambda m: m.group(1) + value + m.group(3), text, count=1)
    if n != 1:
        raise SystemExit(f"member {mid}: expected 1 replacement, got {n}")
    return out


def get_member(body, mid):
    m = _member_pat(mid).search(body)
    return m.group(2) if m else None


def main():
    text = DST.read_text(encoding="utf-8")
    if "sTime" in text:
        print("Time column already present - nothing to do.")
        return 0

    lines = text.splitlines(keepends=True)
    out, rebound, resized, tid = [], 0, 0, None
    prev = 0

    for s, e, body in blocks(lines):
        out.append("".join(lines[prev:s]))
        prev = e + 1

        var = (get_member(body, M_TEXTVAR) or "").strip('"')
        lab = (get_member(body, M_TEXT) or "").strip('"')

        if re.fullmatch(r"GVL_Log\.aRecent\[\d+\]\.sSource", var):
            body = set_member(body, M_TEXTVAR,
                              '"' + var.replace(".sSource", ".sTime") + '"')
            body = set_member(body, M_WIDTH, str(TIME_W))
            rebound += 1
        elif re.fullmatch(r"GVL_Log\.aRecent\[\d+\]\.sMsg", var):
            body = set_member(body, M_LEFT, str(MSG_X))
            body = set_member(body, M_WIDTH, str(MSG_W))
            resized += 1
        elif lab == "Source":
            body = set_member(body, M_TEXT, '"Time"')
            body = set_member(body, M_WIDTH, str(TIME_W))
            tid = (get_member(body, M_COUNTER) or "").strip('"')
        elif lab == "Message":
            body = set_member(body, M_LEFT, str(MSG_X))
            body = set_member(body, M_WIDTH, str(MSG_W))

        out.append(body)
    out.append("".join(lines[prev:]))

    if rebound != ROWS or resized != ROWS:
        raise SystemExit(f"expected {ROWS} of each, got rebound={rebound} "
                         f"resized={resized} - aborting without writing")
    if not tid:
        raise SystemExit('no "Source" header element found')

    DST.write_text("".join(out), encoding="utf-8")
    print(f"rebound {rebound} cells .sSource -> .sTime (width {TIME_W})")
    print(f"reflowed {resized} Message cells to x={MSG_X} w={MSG_W}")
    print(f'header -> "Time" (TextID {tid})')

    gtl = GTL.read_text(encoding="utf-8")
    pat = re.compile(r'(<v n="TextID">"' + tid +
                     r'"</v>\s*\n\s*<v n="TextDefault">")Source("</v>)')
    gtl, n = pat.subn(lambda m: m.group(1) + "Time" + m.group(2), gtl, count=1)
    if n != 1:
        print(f"  WARNING: no GlobalTextList entry for TextID {tid}; "
              f"XAE will fill it in on first open")
    else:
        GTL.write_text(gtl, encoding="utf-8")
        print(f"GlobalTextList TextID {tid}: Source -> Time")
    return 0


if __name__ == "__main__":
    sys.exit(main())
