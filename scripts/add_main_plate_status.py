"""Add plate-sensor status lamps to Main.TcVIS.

Main embeds AutoMain as a frame spanning x -4..684, y 3..407, with the nav
buttons on the y=417 row. That leaves a clear 110 px strip at x 690..800,
which is where the plate status goes -- visible on the operator's home
screen without opening a page.

Cross-file clone: VisuFbElemLamp only exists on Piston.TcVIS, so each lamp
needs its VisualElementOwningObjectGuid rewritten to Main's object GUID and
Main's TypeList topped up. Labels clone Main's own nav button (a
VisuFbElemSimple) with its ChangeVisu action stripped -- otherwise every
label would navigate somewhere when touched.

Lamps bind absolute to GVL_HMI.bPlateSen*, the MAIN-driven mirror of
GVL_App.bPlateSen*. Member 743958181L carries the bool for a lamp, same as
for a checkbox.

Idempotent: refuses to run twice.

Run:  python scripts/add_main_plate_status.py
Then: python scripts/validate_visu.py
      ...and open Main in TcXaeShell to confirm it renders.
"""

from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1] / (
    "Panel_PLC_HMI/167_01_Saad_PLC/167_01_Saad_PLC/PLC1")
DST = ROOT / "VISU/Main.TcVIS"
LAMP_SRC = ROOT / "VISU/Piston.TcVIS"
GTL = ROOT / "GlobalTextList.TcGTLO"

M_LEFT, M_TOP = "1649127785L", "357335551L"
M_WIDTH, M_HEIGHT = "2422045748L", "2134141914L"
M_CX, M_CY = "550940142L", "1473355128L"
M_TEXT, M_COUNTER = "390574330L", "823443203L"
M_BOOLVAR = "743958181L"      # lamp bool AND checkbox bool

INDENT_O, INDENT_C = "              <o>", "              </o>"
NS = "1003"                    # Main's GUID namespace
GUID_FMT = "{a1b2c3d4-0e5f-4a6b-9c7d-" + NS + "%08d}"

ROWS = [("L", "GVL_HMI.bPlateSenL"), ("R", "GVL_HMI.bPlateSenR")]

TITLE = (692, 8, 104, 26)
LBL_X, LBL_W = 692, 26
LAMP_X, LAMP_W, LAMP_H = 724, 29, 27
TOP0, STEP = 44, 38

UID0, TID0 = 20, 670


def blocks(lines, type_name=None):
    for i, l in enumerate(lines):
        if "VisualElementTypeName" in l and (type_name is None
                                             or f'"{type_name}"' in l):
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


def geom(t, left, top, w, h):
    for mid, v in ((M_LEFT, left), (M_TOP, top), (M_WIDTH, w), (M_HEIGHT, h)):
        t = set_member(t, mid, str(v))
    if has_member(t, M_CX):
        t = set_member(t, M_CX, str(left + w // 2))
        t = set_member(t, M_CY, str(top + h // 2))
    return t


def identity(t, n, owning):
    t = re.sub(r'(<v n="VisualElementIdentifier">")GenElemInst_\d+("</v>)',
               lambda m: m.group(1) + f"GenElemInst_{n}" + m.group(2), t, 1)
    t = re.sub(r'(<v n="VisualElementIdentification">)\{[0-9a-fA-F-]+\}(</v>)',
               lambda m: m.group(1) + GUID_FMT % n + m.group(2), t, 1)
    t = re.sub(r'(<v n="VisualElementOwningObjectGuid">)\{[0-9a-fA-F-]+\}(</v>)',
               lambda m: m.group(1) + owning + m.group(2), t, 1)
    t = re.sub(r'(<v n="VisualElementId">)\d+(</v>)',
               lambda m: m.group(1) + str(n) + m.group(2), t, 1)
    return t


def strip_actions(t):
    """A label must not navigate when touched.

    Match the cvt attribute generically: it is the concrete action type, so
    Main's nav button carries cvt="ChangeVisuInputAction[]" while other
    donors use cvt="IInputAction[]". Hardcoding one of them makes this a
    silent no-op and every label inherits the donor's navigation -- touching
    the plate status would jump to another page. Hence the assert.
    """
    out, n = re.subn(
        r'<d n="VisualElementInputActions" t="Hashtable"[^/>]*?>.*?</d>',
        '<d n="VisualElementInputActions" t="Hashtable" />', t, count=1,
        flags=re.DOTALL)
    if n != 1 or "Assign33" in out:
        raise SystemExit("failed to strip the donor's input action - the label "
                         "would navigate when touched")
    return out


def merge_typelist(dst_text, donor_text):
    o = dst_text.index("      <TypeList>")
    c = dst_text.index("      </TypeList>", o)
    body = dst_text[o:c]
    src = {}
    for m in re.finditer(r'<Type n="([^"]+)">([^<]*)</Type>', donor_text):
        src.setdefault(m.group(1), m.group(2))
    add = [f'        <Type n="{n}">{v}</Type>\n'
           for n, v in src.items() if f'<Type n="{n}">' not in body]
    if add:
        print(f"  TypeList: added {len(add)} type(s): "
              + ", ".join(re.search(r'n="([^"]+)"', a).group(1) for a in add))
    return dst_text[:c] + "".join(add) + dst_text[c:]


def main():
    text = DST.read_text(encoding="utf-8")
    if "bPlateSenL" in text:
        print("plate status already present - nothing to do.")
        return 0
    owning = re.search(r'<Visu Name="Main" Id="(\{[0-9a-fA-F-]+\})"',
                       text).group(1)
    print(f"Main owning GUID {owning}")

    lamp = next(blocks(LAMP_SRC.read_text(encoding="utf-8").splitlines(True),
                       "VisuFbElemLamp"))[2]
    lines = text.splitlines(keepends=True)
    label_src = strip_actions(next(blocks(lines, "VisuFbElemSimple"))[2])
    print("cloned a lamp from Piston.TcVIS and a label from Main's nav button")

    uid, tid, texts, out = UID0, TID0, [], []

    t = geom(label_src, *TITLE)
    t = set_member(t, M_TEXT, '"Plate"')
    t = set_member(t, M_COUNTER, f'"{tid}"')
    texts.append((tid, "Plate")); tid += 1
    out.append(identity(t, uid, owning)); uid += 1

    for i, (name, var) in enumerate(ROWS):
        top = TOP0 + i * STEP
        t = geom(label_src, LBL_X, top, LBL_W, LAMP_H)
        t = set_member(t, M_TEXT, f'"{name}"')
        t = set_member(t, M_COUNTER, f'"{tid}"')
        texts.append((tid, name)); tid += 1
        out.append(identity(t, uid, owning)); uid += 1

        t = geom(lamp, LAMP_X, top, LAMP_W, LAMP_H)
        t = set_member(t, M_BOOLVAR, f'"{var}"')
        out.append(identity(t, uid, owning)); uid += 1
        print(f"  lamp {name} -> {var} at ({LAMP_X},{top})")

    last = max(e for s, e, b in blocks(lines))
    result = "".join(lines[:last + 1]) + "".join(out) + "".join(lines[last + 1:])
    result = merge_typelist(result, LAMP_SRC.read_text(encoding="utf-8"))
    result = re.sub(r'(<v n="UniqueIdGenerator">")\d+("</v>)',
                    lambda m: m.group(1) + str(uid + 10) + m.group(2), result, 1)
    result = re.sub(r'(<v n="LastUsedIdForIdentifier">)\d+(</v>)',
                    lambda m: m.group(1) + str(uid + 10) + m.group(2), result, 1)
    DST.write_text(result, encoding="utf-8")
    print(f"wrote {DST.name}: +{len(out)} elements")

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
