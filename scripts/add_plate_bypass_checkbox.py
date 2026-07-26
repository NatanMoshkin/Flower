"""Add the "Bypass plate sensors" checkbox to AutoMain.TcVIS.

Clones AutoMain's own "No sensors (timed steps)" checkbox -- same file, same
version, already proven to render -- and rewrites geometry, label, bound
variable, counter and the three identity fields.

Sits as the fourth checkbox, keeping the 40 px rhythm
(Continuous 255, Auto Mode 295, No sensors 335, Bypass plate 375).

Idempotent: refuses to run twice.

Run:  python scripts/add_plate_bypass_checkbox.py
Then: python scripts/validate_visu.py
      ...and open AutoMain in TcXaeShell to confirm it renders.
"""

from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1] / (
    "Panel_PLC_HMI/167_01_Saad_PLC/167_01_Saad_PLC/PLC1")
DST = ROOT / "VISU/AutoMain.TcVIS"
GTL = ROOT / "GlobalTextList.TcGTLO"

M_LEFT, M_TOP = "1649127785L", "357335551L"
M_WIDTH, M_HEIGHT = "2422045748L", "2134141914L"
M_TEXT, M_COUNTER, M_BOOLVAR = "390574330L", "823443203L", "743958181L"

INDENT_O, INDENT_C = "              <o>", "              </o>"

CLONE_FROM = "No sensors (timed steps)"
LABEL = "Bypass plate sensors"
VAR = "stCfg.bBypassPlateSensors"
LEFT, TOP, WIDTH, HEIGHT = 20, 375, 240, 30

# AutoMain namespace 1004 is in use by the timer grid (serials 130+);
# take a clear slot well above it.
NEW_UID = 160
NEW_GUID = "{a1b2c3d4-0e5f-4a6b-9c7d-100400000160}"
NEW_TID = 660


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


def main():
    text = DST.read_text(encoding="utf-8")
    if "bBypassPlateSensors" in text:
        print("bypass checkbox already present - nothing to do.")
        return 0
    if NEW_GUID in text:
        raise SystemExit(f"GUID {NEW_GUID} already used")

    lines = text.splitlines(keepends=True)
    src = next((b for b in blocks(lines, "VisuFbCheckbox")
                if f'"{CLONE_FROM}"' in b[2]), None)
    if src is None:
        raise SystemExit(f"could not find the {CLONE_FROM!r} checkbox to clone")
    s, e, body = src
    print(f"cloning {CLONE_FROM!r} at lines {s+1}-{e+1}")

    new = body
    for mid, val in ((M_LEFT, str(LEFT)), (M_TOP, str(TOP)),
                     (M_WIDTH, str(WIDTH)), (M_HEIGHT, str(HEIGHT)),
                     (M_TEXT, f'"{LABEL}"'), (M_BOOLVAR, f'"{VAR}"'),
                     (M_COUNTER, f'"{NEW_TID}"')):
        new = set_member(new, mid, val)
    new = re.sub(r'(<v n="VisualElementIdentifier">")GenElemInst_\d+("</v>)',
                 lambda m: m.group(1) + f"GenElemInst_{NEW_UID}" + m.group(2),
                 new, count=1)
    new = re.sub(r'(<v n="VisualElementIdentification">)\{[0-9a-fA-F-]+\}(</v>)',
                 lambda m: m.group(1) + NEW_GUID + m.group(2), new, count=1)
    new = re.sub(r'(<v n="VisualElementId">)\d+(</v>)',
                 lambda m: m.group(1) + str(NEW_UID) + m.group(2), new, count=1)

    # Sibling insert straight after the cloned block.
    out = "".join(lines[:e + 1]) + new + "".join(lines[e + 1:])
    DST.write_text(out, encoding="utf-8")
    print(f"added {LABEL!r} -> {VAR} at ({LEFT},{TOP}) {WIDTH}x{HEIGHT}")

    gtl = GTL.read_text(encoding="utf-8")
    anchor = '            <o>\n              <v n="TextID">"550"</v>'
    if f'<v n="TextID">"{NEW_TID}"</v>' not in gtl and anchor in gtl:
        entry = ('            <o>\n'
                 f'              <v n="TextID">"{NEW_TID}"</v>\n'
                 f'              <v n="TextDefault">"{LABEL}"</v>\n'
                 '              <l n="LanguageTexts" t="ArrayList" />\n'
                 '            </o>\n')
        GTL.write_text(gtl.replace(anchor, entry + anchor, 1), encoding="utf-8")
        print(f"registered TextID {NEW_TID} in GlobalTextList")
    return 0


if __name__ == "__main__":
    sys.exit(main())
