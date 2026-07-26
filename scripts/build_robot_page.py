"""Checklist s5 (part 1): create Robot.TcVIS - status, state and triggers.

The 11 numeric parameter fields are NOT built here: the panel project has
no numeric-entry element to clone (only Visu_TapInput buttons and
ChangeVisu actions). Drop ONE numeric input on this page in TcXaeShell,
bind it to GVL_Robot.stParams.J_SPEED, save, then run
scripts/add_robot_params.py to clone it across the rest. The right-hand
column (x >= 420) is left empty for that grid.

Built by cloning proven blocks:
  * page skeleton + "Main" nav button  <- PistonsManual.TcVIS
  * static labels (VisuFbElemSimple)   <- AutoMain title
  * value fields (VisuFbElemTextfield) <- AutoMain step/error fields
  * trigger buttons (VisuFbElemButton) <- AutoMain START/STOP/RESET

Bindings are absolute GVL paths: this page is navigated to, not embedded
as a frame, so it needs no interface variables.

Run:  python scripts/build_robot_page.py
Then: python scripts/validate_visu.py Robot.TcVIS
"""

from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1] / (
    "Panel_PLC_HMI/167_01_Saad_PLC/167_01_Saad_PLC/PLC1")
VISU = ROOT / "VISU"
SKEL, DONOR = VISU / "PistonsManual.TcVIS", VISU / "AutoMain.TcVIS"
DST = VISU / "Robot.TcVIS"
GTL = ROOT / "GlobalTextList.TcGTLO"
PLCPROJ = next(ROOT.glob("*.plcproj"))

NEW_GUID = "{a1b2c3d4-0e5f-4a6b-9c7d-000000000102}"

M_LEFT, M_TOP = "1649127785L", "357335551L"
M_WIDTH, M_HEIGHT = "2422045748L", "2134141914L"
M_CX, M_CY = "550940142L", "1473355128L"
M_TEXT, M_COUNTER = "390574330L", "823443203L"
M_TEXTVAR, M_TAP = "2477733581L", "1186196937L"

INDENT_O, INDENT_C = "              <o>", "              </o>"

R = "GVL_Robot.stRobot."
P = "GVL_Robot.stParams."

# (label, y, format, variable)  -- left column only; x>=420 stays free.
ROWS = [
    ("Connection", 55,  "%s", R + "sConnStateText"),
    ("Packets Rx", 90,  "%d", R + "nPacketsRx"),
    ("Packets Tx", 125, "%d", R + "nPacketsTx"),
    ("Last Rx",    160, "%s", R + "sLastMessage"),
    ("Last Tx",    195, "%s", R + "sLastTxMessage"),
    ("State out",  230, "%d", P + "nStateOut"),
    ("Robot cmd",  265, "%d", P + "nRobotCmd"),
]
BUTTONS = [("Get Sync", 20, 330, P + "bGetSync"),
           ("New Bulb", 180, 330, P + "bTriggerNewBulb")]

LBL_X, LBL_W, VAL_X, VAL_W, ROW_H = 20, 145, 170, 220, 28
BTN_W, BTN_H = 150, 44

texts: list[tuple[int, str]] = []   # (TextID, default) for GlobalTextList


def block(lines, type_name, predicate=None):
    for i, l in enumerate(lines):
        if f'"{type_name}"' in l and "VisualElementTypeName" in l:
            s = i
            while lines[s].rstrip("\r\n") != INDENT_O:
                s -= 1
            e = i
            while lines[e].rstrip("\r\n") != INDENT_C:
                e += 1
            body = "".join(lines[s:e + 1])
            if predicate is None or predicate(body):
                return s, e, body
    raise SystemExit(f"no {type_name} block found")


def set_member(text, mid, value, required=True):
    pat = re.compile(r'(<v n="Id">' + re.escape(mid) +
                     r'</v>\s*\n\s*<v n="Value">)(.*?)(</v>)', re.DOTALL)
    out, n = pat.subn(lambda m: m.group(1) + value + m.group(3), text, count=1)
    if required and n != 1:
        raise SystemExit(f"member {mid}: expected 1 replacement, got {n}")
    return out


def identity(text, uid, guid_n):
    text = re.sub(r'(<v n="VisualElementIdentifier">")GenElemInst_\d+("</v>)',
                  lambda m: m.group(1) + f"GenElemInst_{uid}" + m.group(2), text, 1)
    # Namespace 1002 = this page. VisualElementIdentification must be unique
    # across the WHOLE project, not just this file -- a bare serial here
    # collided with add_main_nav.py's slots and broke the build. See
    # scripts/fix_visu_guids.py.
    text = re.sub(r'(<v n="VisualElementIdentification">)\{[0-9a-fA-F-]+\}(</v>)',
                  lambda m: m.group(1) +
                  "{a1b2c3d4-0e5f-4a6b-9c7d-1002%08d}" % guid_n + m.group(2), text, 1)
    text = re.sub(r'(<v n="VisualElementOwningObjectGuid">)\{[0-9a-fA-F-]+\}(</v>)',
                  lambda m: m.group(1) + NEW_GUID + m.group(2), text, 1)
    text = re.sub(r'(<v n="VisualElementId">)\d+(</v>)',
                  lambda m: m.group(1) + str(uid) + m.group(2), text, 1)
    return text


def geom(t, left, top, w, h, centre):
    for mid, v in ((M_LEFT, left), (M_TOP, top), (M_WIDTH, w), (M_HEIGHT, h)):
        t = set_member(t, mid, str(v))
    if centre:
        t = set_member(t, M_CX, str(left + w // 2))
        t = set_member(t, M_CY, str(top + h // 2))
    return t


def main():
    if DST.exists():
        print(f"{DST.name} already exists - nothing to do.")
        return 0

    skel = SKEL.read_text(encoding="utf-8")
    old = re.search(r'<Visu Name="PistonsManual" Id="(\{[0-9a-fA-F-]+\})"',
                    skel).group(1)
    skel = skel.replace('<Visu Name="PistonsManual"', '<Visu Name="Robot"', 1)
    skel = skel.replace(old, NEW_GUID)

    lines = skel.splitlines(keepends=True)
    # Strip all six Piston frames; keep only the "Main" nav button.
    while True:
        try:
            s, e, _ = block(lines, "VisuFbFrame")
        except SystemExit:
            break
        del lines[s:e + 1]
    print(f"skeleton: frames stripped, "
          f"{sum('VisualElementTypeName' in l for l in lines)} element(s) left")

    donor = DONOR.read_text(encoding="utf-8").splitlines(keepends=True)
    SIMPLE = block(donor, "VisuFbElemSimple")[2]
    FIELD = block(donor, "VisuFbElemTextfield")[2]
    BUTTON = block(donor, "VisuFbElemButton")[2]

    out, uid, tid = [], 200, 600

    def add(t):
        nonlocal out
        out.append(t)

    # Title
    t = geom(SIMPLE, 20, 8, 260, 34, centre=True)
    t = set_member(t, M_TEXT, '"Robot"')
    t = set_member(t, M_COUNTER, f'"{tid}"')
    texts.append((tid, "Robot"))
    add(identity(t, uid, uid)); uid += 1; tid += 1

    for label, y, fmt, var in ROWS:
        t = geom(SIMPLE, LBL_X, y, LBL_W, ROW_H, centre=True)
        t = set_member(t, M_TEXT, f'"{label}"')
        t = set_member(t, M_COUNTER, f'"{tid}"')
        texts.append((tid, label))
        add(identity(t, uid, uid)); uid += 1; tid += 1

        t = geom(FIELD, VAL_X, y, VAL_W, ROW_H, centre=False)
        t = set_member(t, M_TEXT, f'"{fmt}"')
        t = set_member(t, M_TEXTVAR, f'"{var}"')
        t = set_member(t, M_COUNTER, f'"{tid}"')
        texts.append((tid, fmt))
        add(identity(t, uid, uid)); uid += 1; tid += 1
        print(f"  row {label:<12} -> {var}")

    for label, x, y, var in BUTTONS:
        t = geom(BUTTON, x, y, BTN_W, BTN_H, centre=True)
        t = set_member(t, M_TEXT, f'"{label}"')
        t = set_member(t, M_TAP, f'"{var}"')
        t = set_member(t, M_COUNTER, f'"{tid}"')
        texts.append((tid, label))
        add(identity(t, uid, uid)); uid += 1; tid += 1
        print(f"  button {label:<10} -> {var}")

    # Insert after the last existing element block (the Main nav button),
    # an exact sibling position derived from the scanner.
    last_end = max(block(lines, ty)[1] for ty in ("VisuFbElemSimple",))
    text = "".join(lines[:last_end + 1]) + "".join(out) + "".join(lines[last_end + 1:])

    # Merge any element types the donor blocks need into this page's TypeList.
    text = merge_typelist(text, DONOR.read_text(encoding="utf-8"))

    text = re.sub(r'(<v n="UniqueIdGenerator">")\d+("</v>)',
                  lambda m: m.group(1) + str(uid + 10) + m.group(2), text, 1)
    text = re.sub(r'(<v n="LastUsedIdForIdentifier">)\d+(</v>)',
                  lambda m: m.group(1) + str(uid + 10) + m.group(2), text, 1)

    DST.write_text(text, encoding="utf-8")
    print(f"wrote {DST.name} ({len(out)} injected elements)")

    register_plcproj()
    register_texts()
    return 0


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
        print(f"  TypeList: added {len(add)} missing type(s): "
              + ", ".join(re.search(r'n="([^"]+)"', a).group(1) for a in add))
    return dst_text[:c] + "".join(add) + dst_text[c:]


def register_plcproj():
    proj = PLCPROJ.read_text(encoding="utf-8")
    if "Robot.TcVIS" in proj:
        return
    anchor = ('    <Compile Include="VISU\\PistonsManual.TcVIS">\n'
              '      <SubType>Code</SubType>\n'
              '      <DependentUpon>VISU\\VisualizationManager.TcVMO</DependentUpon>\n'
              '    </Compile>\n')
    block_ = ('    <Compile Include="VISU\\Robot.TcVIS">\n'
              '      <SubType>Code</SubType>\n'
              '      <DependentUpon>VISU\\VisualizationManager.TcVMO</DependentUpon>\n'
              '    </Compile>\n')
    if anchor not in proj:
        raise SystemExit("plcproj anchor not found")
    PLCPROJ.write_text(proj.replace(anchor, anchor + block_, 1), encoding="utf-8")
    print(f"registered in {PLCPROJ.name}")


def register_texts():
    gtl = GTL.read_text(encoding="utf-8")
    anchor = '            <o>\n              <v n="TextID">"550"</v>'
    if anchor not in gtl:
        print("  WARNING: GlobalTextList anchor missing; XAE will fill these in")
        return
    entries = "".join(
        '            <o>\n'
        f'              <v n="TextID">"{tid}"</v>\n'
        f'              <v n="TextDefault">"{d}"</v>\n'
        '              <l n="LanguageTexts" t="ArrayList" />\n'
        '            </o>\n'
        for tid, d in texts if f'<v n="TextID">"{tid}"</v>' not in gtl)
    if entries:
        GTL.write_text(gtl.replace(anchor, entries + anchor, 1), encoding="utf-8")
        print(f"  registered {len(texts)} TextID(s) in GlobalTextList")


if __name__ == "__main__":
    sys.exit(main())
