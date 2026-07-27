"""Add an editable "Robot IP" field to Robot.TcVIS.

Clones one of the page's own editable parameter fields -- itself a clone of
the template the operator authored in TcXaeShell -- and rebinds it to
GVL_Robot.sRobotHost.

Three things change beyond geometry and the bound variable:

  * format "%d" -> "%s". The field displays a STRING now.
  * InputBoxMin / InputBoxMax are CLEARED. They are numeric bounds; leaving
    "1"/"100" on a string field is meaningless at best.
  * InputBoxDialogTitle is set, because an IP address is the one field here
    where the operator needs to know what is being asked before the keypad
    covers the page.

InputType stays "Default", which is what makes this work at all: the dialog
type is derived from the bound variable, so a STRING gets the alphanumeric
keypad rather than the numpad. That is why no new element type had to be
authored in the IDE for this -- verify it on the panel anyway, since a
numpad appearing instead would mean Default is resolving on the format
string rather than the variable.

Placed below the Get Sync / New Bulb buttons (which end at y=374) rather
than squeezed into the 2 px gap left above them.

Idempotent: refuses to run twice.

Run:  python scripts/add_robot_ip_field.py
Then: python scripts/validate_visu.py
      ...and open Robot in TcXaeShell and rebuild.
"""

from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1] / (
    "Panel_PLC_HMI/167_01_Saad_PLC/167_01_Saad_PLC/PLC1")
DST = ROOT / "VISU/Robot.TcVIS"
GTL = ROOT / "GlobalTextList.TcGTLO"

M_LEFT, M_TOP = "1649127785L", "357335551L"
M_WIDTH, M_HEIGHT = "2422045748L", "2134141914L"
M_CX, M_CY = "550940142L", "1473355128L"
M_TEXT, M_COUNTER, M_TEXTVAR = "390574330L", "823443203L", "2477733581L"

INDENT_O, INDENT_C = "              <o>", "              </o>"

NS = "1002"                       # Robot page's GUID namespace
VAR = "GVL_Robot.sRobotHost"
LABEL, TITLE = "Robot IP", "Robot IP address"

LBL = (20, 385, 145, 28)
FLD = (170, 385, 220, 28)

UID_LBL, UID_FLD = 401, 402       # page uids run ~200-260; 400+ is clear
TID_LBL, TID_FLD = 1300, 1301


def blocks(lines, type_name):
    for i, l in enumerate(lines):
        if f'"{type_name}"' in l and "VisualElementTypeName" in l:
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


def set_action(text, key, value):
    pat = re.compile(r'(<v n="' + re.escape(key) + r'">)(.*?)(</v>)')
    out, n = pat.subn(lambda m: m.group(1) + value + m.group(3), text, count=1)
    if n != 1:
        raise SystemExit(f"action field {key}: expected 1 replacement, got {n}")
    return out


def geom(t, left, top, w, h):
    for mid, v in ((M_LEFT, left), (M_TOP, top), (M_WIDTH, w), (M_HEIGHT, h)):
        t = set_member(t, mid, str(v))
    if has_member(t, M_CX):
        t = set_member(t, M_CX, str(left + w // 2))
        t = set_member(t, M_CY, str(top + h // 2))
    return t


def identity(t, uid):
    t = re.sub(r'(<v n="VisualElementIdentifier">")GenElemInst_\d+("</v>)',
               lambda m: m.group(1) + f"GenElemInst_{uid}" + m.group(2), t, 1)
    t = re.sub(r'(<v n="VisualElementIdentification">)\{[0-9a-fA-F-]+\}(</v>)',
               lambda m: m.group(1) +
               "{a1b2c3d4-0e5f-4a6b-9c7d-%s%08d}" % (NS, uid) + m.group(2), t, 1)
    t = re.sub(r'(<v n="VisualElementId">)\d+(</v>)',
               lambda m: m.group(1) + str(uid) + m.group(2), t, 1)
    return t


def main():
    text = DST.read_text(encoding="utf-8")
    if "sRobotHost" in text:
        print("Robot IP field already present - nothing to do.")
        return 0
    lines = text.splitlines(keepends=True)

    # Donors, both from this page: a plain label, and an EDITABLE field.
    label_src = next(b for _s, _e, b in blocks(lines, "VisuFbElemSimple")
                     if "Assign33" not in b)      # not the Main nav button
    field_src = next(b for _s, _e, b in blocks(lines, "VisuFbElemTextfield")
                     if "InputBoxInputAction" in b)
    print("cloned a static label and an editable field from Robot.TcVIS")

    out = []

    t = geom(label_src, *LBL)
    t = set_member(t, M_TEXT, f'"{LABEL}"')
    t = set_member(t, M_COUNTER, f'"{TID_LBL}"')
    out.append(identity(t, UID_LBL))

    t = geom(field_src, *FLD)
    t = set_member(t, M_TEXT, '"%s"')
    t = set_member(t, M_TEXTVAR, f'"{VAR}"')
    t = set_member(t, M_COUNTER, f'"{TID_FLD}"')
    t = set_action(t, "InputBoxVariable", "")
    t = set_action(t, "InputBoxMin", "")       # numeric bounds are meaningless
    t = set_action(t, "InputBoxMax", "")       # on a STRING
    t = set_action(t, "InputBoxDialogTitle", TITLE)
    if '<v n="InputType">"Default"</v>' not in t:
        raise SystemExit("donor InputType is not Default - a STRING would not "
                         "get the alphanumeric keypad")
    out.append(identity(t, UID_FLD))
    print(f"  field -> {VAR} at {FLD}, min/max cleared, title {TITLE!r}")

    last = max(e for _s, e, _b in blocks(lines, "VisuFbElemTextfield"))
    result = "".join(lines[:last + 1]) + "".join(out) + "".join(lines[last + 1:])
    DST.write_text(result, encoding="utf-8")
    print(f"wrote {DST.name}: +2 elements")

    gtl = GTL.read_text(encoding="utf-8")
    anchor = '            <o>\n              <v n="TextID">"550"</v>'
    entries = "".join(
        '            <o>\n'
        f'              <v n="TextID">"{tid}"</v>\n'
        f'              <v n="TextDefault">"{d}"</v>\n'
        '              <l n="LanguageTexts" t="ArrayList" />\n'
        '            </o>\n'
        for tid, d in ((TID_LBL, LABEL), (TID_FLD, "%s"))
        if f'<v n="TextID">"{tid}"</v>' not in gtl)
    if entries and anchor in gtl:
        GTL.write_text(gtl.replace(anchor, entries + anchor, 1), encoding="utf-8")
        print("registered 2 TextID(s) in GlobalTextList")
    return 0


if __name__ == "__main__":
    sys.exit(main())
