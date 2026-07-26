"""Checklist s5 (part 2): the 11 robot tuning params on Robot.TcVIS.

Clones the numeric-input template authored in TcXaeShell (a
VisuFbElemTextfield whose OnMouseClick carries an InputBoxInputAction) once
per parameter, and a label per row cloned from the page's existing labels.

Range clamping: the template ships with InputBoxMin/Max empty, so a typo
goes straight to the robot. The ranges below are the vendor's own, traced to
Robot/167-01-Saad/'tcp client.py' (which clamps to them) and mirrored in
readme.txt -- see the CLAUDE.md TODO. Setting them per control is the
belt-and-braces half; clamping in FB_RobotTcpClient where bSetParam is
consumed is the half that bounds *every* writer, and is still to do.

The template itself is repositioned into row 8 (WATER_SPEED, what it is
already bound to) rather than left floating.

Idempotent: refuses to run twice.

Run:  python scripts/add_robot_params.py
Then: python scripts/validate_visu.py
      ...and open Robot in TcXaeShell, rebuild, confirm the grid renders.
"""

from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1] / (
    "Panel_PLC_HMI/167_01_Saad_PLC/167_01_Saad_PLC/PLC1")
DST = ROOT / "VISU/Robot.TcVIS"
GTL = ROOT / "GlobalTextList.TcGTLO"

TEMPLATE_UID = "GenElemInst_229"

M_LEFT, M_TOP = "1649127785L", "357335551L"
M_WIDTH, M_HEIGHT = "2422045748L", "2134141914L"
M_CX, M_CY = "550940142L", "1473355128L"
M_TEXT, M_COUNTER = "390574330L", "823443203L"
M_TEXTVAR = "2477733581L"

INDENT_O, INDENT_C = "              <o>", "              </o>"
NS = "1002"                      # this page's GUID namespace
GUID_FMT = "{a1b2c3d4-0e5f-4a6b-9c7d-" + NS + "%08d}"

# (name, min, max) -- vendor ranges, see module docstring.
PARAMS = [
    ("J_SPEED",            1,   100),
    ("L_SPEED",            1,   100),
    ("REPEATS",            1,    10),
    ("START_WAIT",        10, 10000),
    ("WATER_WAIT",        10, 10000),
    ("STAND_WAIT",        10, 10000),
    ("END_WAIT",          10, 10000),
    ("WATER_SPEED",        0,   100),
    ("WAX_WAIT_TIME_IN",   0, 10000),
    ("WAX_WAIT_TIME_OUT", 10, 10000),
    ("WAX_SPEED",          0,   100),
]

# Right-hand column, deliberately left empty by build_robot_page.py.
LBL_X, LBL_W = 420, 150
VAL_X, VAL_W = 575, 195
TOP0, ROW_H, STEP = 56, 28, 32

UID0 = 230          # existing: 200..217 (mine) + 219 (IDE template)
TID0 = 620          # existing: 600..616


def blocks(lines):
    for i, l in enumerate(lines):
        if "VisualElementTypeName" in l:
            s = i
            while lines[s].rstrip("\r\n") != INDENT_O:
                s -= 1
            e = i
            while lines[e].rstrip("\r\n") != INDENT_C:
                e += 1
            yield s, e, "".join(lines[s:e + 1])


def set_member(text, mid, value):
    pat = re.compile(r'(<v n="Id">' + re.escape(mid) +
                     r'</v>\s*\n\s*<v n="Value"[^>]*>)(.*?)(</v>)', re.DOTALL)
    out, n = pat.subn(lambda m: m.group(1) + value + m.group(3), text, count=1)
    if n != 1:
        raise SystemExit(f"member {mid}: expected 1 replacement, got {n}")
    return out


def has_member(text, mid):
    return re.search(r'<v n="Id">' + re.escape(mid) + r'</v>', text) is not None


def identity(text, n):
    text = re.sub(r'(<v n="VisualElementIdentifier">")GenElemInst_\d+("</v>)',
                  lambda m: m.group(1) + f"GenElemInst_{n}" + m.group(2), text, 1)
    text = re.sub(r'(<v n="VisualElementIdentification">)\{[0-9a-fA-F-]+\}(</v>)',
                  lambda m: m.group(1) + GUID_FMT % n + m.group(2), text, 1)
    text = re.sub(r'(<v n="VisualElementId">)\d+(</v>)',
                  lambda m: m.group(1) + str(n) + m.group(2), text, 1)
    return text


def geom(t, left, top, w, h):
    for mid, v in ((M_LEFT, left), (M_TOP, top), (M_WIDTH, w), (M_HEIGHT, h)):
        t = set_member(t, mid, str(v))
    if has_member(t, M_CX):
        t = set_member(t, M_CX, str(left + w // 2))
        t = set_member(t, M_CY, str(top + h // 2))
    return t


def set_range(t, lo, hi):
    """InputBoxMin/Max live in the input action, not the member list."""
    for tag, val in (("InputBoxMin", lo), ("InputBoxMax", hi)):
        pat = re.compile(r'(<v n="' + tag + r'">)"[^"]*"(</v>)')
        t, n = pat.subn(lambda m: m.group(1) + f'"{val}"' + m.group(2), t, count=1)
        if n != 1:
            raise SystemExit(f"{tag}: expected 1 replacement, got {n}")
    return t


def main():
    text = DST.read_text(encoding="utf-8")
    if '"GVL_Robot.stParams.J_SPEED"' in text:
        print("param grid already present - nothing to do.")
        return 0

    lines = text.splitlines(keepends=True)
    spans = list(blocks(lines))

    tmpl = next((b for b in spans if f'"{TEMPLATE_UID}"' in b[2]), None)
    if tmpl is None:
        raise SystemExit(f"{TEMPLATE_UID} not found - author the numeric input "
                         f"template in TcXaeShell first")
    if "InputBoxInputAction" not in tmpl[2]:
        raise SystemExit(f"{TEMPLATE_UID} has no InputBoxInputAction; it is not "
                         f"an editable field")
    label_src = next(b for b in spans
                     if '"VisuFbElemSimple"' in b[2] and '"Connection"' in b[2])
    print(f"template  {TEMPLATE_UID} at lines {tmpl[0]+1}-{tmpl[1]+1}")
    print(f"label src at lines {label_src[0]+1}-{label_src[1]+1}")

    uid, tid, texts, out = UID0, TID0, [], []
    tmpl_row = None

    for i, (name, lo, hi) in enumerate(PARAMS):
        top = TOP0 + i * STEP

        lbl = geom(label_src[2], LBL_X, top, LBL_W, ROW_H)
        lbl = set_member(lbl, M_TEXT, f'"{name}"')
        lbl = set_member(lbl, M_COUNTER, f'"{tid}"')
        texts.append((tid, name)); tid += 1
        out.append(identity(lbl, uid)); uid += 1

        fld = geom(tmpl[2], VAL_X, top, VAL_W, ROW_H)
        fld = set_member(fld, M_TEXTVAR, f'"GVL_Robot.stParams.{name}"')
        fld = set_range(fld, lo, hi)
        if name == "WATER_SPEED":
            # Reuse the operator's own element for the row it already binds.
            tmpl_row = identity(fld, int(re.search(
                r'VisualElementId.>(\d+)</v>', tmpl[2]).group(1)))
            tmpl_row = re.sub(
                r'(<v n="VisualElementIdentifier">")GenElemInst_\d+("</v>)',
                lambda m: m.group(1) + TEMPLATE_UID + m.group(2), tmpl_row, 1)
            tmpl_row = re.sub(
                r'(<v n="VisualElementIdentification">)\{[0-9a-fA-F-]+\}(</v>)',
                lambda m: m.group(1) + re.search(
                    r'VisualElementIdentification.>(\{[0-9a-fA-F-]+\})</v>',
                    tmpl[2]).group(1) + m.group(2), tmpl_row, 1)
        else:
            out.append(identity(fld, uid)); uid += 1
        print(f"  {name:<18} y={top:<4} range {lo}..{hi}")

    # Replace the template in place with its repositioned self, then append
    # the new rows as siblings straight after it.
    lines[tmpl[0]:tmpl[1] + 1] = [tmpl_row]
    lines = "".join(lines).splitlines(keepends=True)
    end = next(e for s, e, b in blocks(lines) if f'"{TEMPLATE_UID}"' in b)
    result = "".join(lines[:end + 1]) + "".join(out) + "".join(lines[end + 1:])

    result = re.sub(r'(<v n="UniqueIdGenerator">")\d+("</v>)',
                    lambda m: m.group(1) + str(uid + 10) + m.group(2), result, 1)
    result = re.sub(r'(<v n="LastUsedIdForIdentifier">)\d+(</v>)',
                    lambda m: m.group(1) + str(uid + 10) + m.group(2), result, 1)
    DST.write_text(result, encoding="utf-8")
    print(f"\nwrote {DST.name}: +{len(out)} elements "
          f"(11 labels + 10 fields; WATER_SPEED reuses {TEMPLATE_UID})")

    gtl = GTL.read_text(encoding="utf-8")
    anchor = '            <o>\n              <v n="TextID">"550"</v>'
    entries = "".join(
        '            <o>\n'
        f'              <v n="TextID">"{t}"</v>\n'
        f'              <v n="TextDefault">"{d}"</v>\n'
        '              <l n="LanguageTexts" t="ArrayList" />\n'
        '            </o>\n'
        for t, d in texts if f'<v n="TextID">"{t}"</v>' not in gtl)
    if entries and anchor in gtl:
        GTL.write_text(gtl.replace(anchor, entries + anchor, 1), encoding="utf-8")
        print(f"registered {len(texts)} TextID(s) in GlobalTextList")
    return 0


if __name__ == "__main__":
    sys.exit(main())
