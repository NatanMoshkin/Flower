"""Remove the "Continuous" checkbox from AutoMain.TcVIS.

The production machine never free-runs -- every cycle is started by the
operator or by the robot's CMD:1 -- so the control is removed rather than
left on screen doing something nobody should use.

Removing the checkbox is only the cosmetic half. MAIN forces
stMasterAutoCfg.bContinuous FALSE every scan, because a VISU page is one of
several writers: FlowerPyHmi has its own Continuous checkbox on two of its
pages and reaches the field over ADS. Deleting this element without that
force would hide the control while leaving the behaviour reachable.

The remaining three checkboxes shift up 40 px each to close the gap, keeping
the rhythm the page already uses (255 / 295 / 335).

Deletes last-first so earlier line indices stay valid while removing, then
re-reads to apply the shift -- mixing deletion and renumbering in one pass
is how off-by-one corruption gets in.

Idempotent: bails out if the checkbox is already gone.

Run:  python scripts/remove_continuous_checkbox.py
Then: python scripts/validate_visu.py
      ...and open AutoMain in TcXaeShell and rebuild.
"""

from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1] / (
    "Panel_PLC_HMI/167_01_Saad_PLC/167_01_Saad_PLC/PLC1")
DST = ROOT / "VISU/AutoMain.TcVIS"

M_TOP, M_CY = "357335551L", "1473355128L"
M_BOOL = "743958181L"

INDENT_O, INDENT_C = "              <o>", "              </o>"

TARGET = "stCfg.bContinuous"
SHIFT_UP = 40
# Checkboxes that move up, in the order they appear down the page.
SHIFTED = ("stCfg.bAutoMode", "stCfg.bNoSensors", "stCfg.bBypassPlateSensors")


def blocks(lines):
    for i, line in enumerate(lines):
        if "VisualElementTypeName" in line:
            s = i
            while lines[s].rstrip("\r\n") != INDENT_O:
                s -= 1
            e = i
            while lines[e].rstrip("\r\n") != INDENT_C:
                e += 1
            yield s, e, "".join(lines[s:e + 1])


def _pat(mid):
    return re.compile(r'(<v n="Id">' + re.escape(mid) +
                      r'</v>\s*\n\s*<v n="Value"[^>]*>)(.*?)(</v>)', re.DOTALL)


def get_member(body, mid):
    m = _pat(mid).search(body)
    return m.group(2) if m else None


def set_member(text, mid, value):
    out, n = _pat(mid).subn(lambda m: m.group(1) + value + m.group(3),
                            text, count=1)
    if n != 1:
        raise SystemExit(f"member {mid}: expected 1 replacement, got {n}")
    return out


def main():
    text = DST.read_text(encoding="utf-8")
    if TARGET not in text:
        print("Continuous checkbox already removed - nothing to do.")
        return 0

    # --- pass 1: delete -----------------------------------------------------
    lines = text.splitlines(keepends=True)
    victim = [(s, e) for s, e, b in blocks(lines)
              if (get_member(b, M_BOOL) or "").strip('"') == TARGET]
    if len(victim) != 1:
        raise SystemExit(f"expected exactly 1 {TARGET} checkbox, "
                         f"found {len(victim)}")
    s, e = victim[0]
    print(f"removing the Continuous checkbox (lines {s + 1}-{e + 1})")
    del lines[s:e + 1]
    DST.write_text("".join(lines), encoding="utf-8")

    # --- pass 2: shift the survivors up -------------------------------------
    lines = DST.read_text(encoding="utf-8").splitlines(keepends=True)
    out, prev, moved = [], 0, 0
    for s, e, body in blocks(lines):
        out.append("".join(lines[prev:s]))
        prev = e + 1
        var = (get_member(body, M_BOOL) or "").strip('"')
        if var in SHIFTED:
            top = int(get_member(body, M_TOP))
            body = set_member(body, M_TOP, str(top - SHIFT_UP))
            if get_member(body, M_CY) is not None:
                cy = int(get_member(body, M_CY))
                body = set_member(body, M_CY, str(cy - SHIFT_UP))
            print(f"  {var:32} y {top} -> {top - SHIFT_UP}")
            moved += 1
        out.append(body)
    out.append("".join(lines[prev:]))

    if moved != len(SHIFTED):
        raise SystemExit(f"expected to shift {len(SHIFTED)} checkboxes, "
                         f"moved {moved}")
    DST.write_text("".join(out), encoding="utf-8")
    print(f"wrote {DST.name}: -1 element, {moved} shifted up {SHIFT_UP} px")
    return 0


if __name__ == "__main__":
    sys.exit(main())
