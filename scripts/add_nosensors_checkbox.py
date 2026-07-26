"""Checklist s3: add the "No sensors (timed steps)" checkbox to AutoMain.TcVIS.

Classic VISU files use numeric-ID serialization, so this does NOT author an
element from scratch. It clones the "Auto Mode" checkbox that already lives
in AutoMain -- same file, same TwinCAT version, already proven to load in
XAE -- and rewrites only the leaf values: geometry, label, bound variable,
and the identity/counter fields that must be unique.

Idempotent: refuses to run twice.

Run:  python scripts/add_nosensors_checkbox.py
Then: open AutoMain in TcXaeShell and confirm the element renders before
      activating. XAE silently drops elements it cannot parse.
"""

from __future__ import annotations

import pathlib
import re
import sys

DST = pathlib.Path(__file__).resolve().parents[1] / (
    "Panel_PLC_HMI/167_01_Saad_PLC/167_01_Saad_PLC/PLC1/VISU/AutoMain.TcVIS"
)

# Member ids, as established by Temp/build_automain_visu.py which authored
# these very blocks.
M_LEFT, M_TOP = "1649127785L", "357335551L"
M_WIDTH, M_HEIGHT = "2422045748L", "2134141914L"
M_TEXT = "390574330L"        # label
M_COUNTER = "823443203L"     # per-element serial
M_BOOLVAR = "743958181L"     # checkbox: toggled bool variable

INDENT_O, INDENT_C = "              <o>", "              </o>"

# New element identity. 100..107 are taken by the existing eight elements;
# UniqueIdGenerator sits at 120, so 108 collides with nothing.
NEW_UID = 108
NEW_ELEM_ID = 108
NEW_COUNTER = 1108
NEW_GUID = "{7e1c9a10-0a01-4b21-9c31-0000000000b9}"

LABEL = "No sensors (timed steps)"
VAR = "stCfg.bNoSensors"
# Existing rhythm: Continuous y=255, Auto Mode y=295. Keep the 40 px step.
LEFT, TOP, WIDTH, HEIGHT = 20, 335, 240, 30


def blocks(lines, type_name):
    """Yield (start, end, body) for each <o>..</o> of the given element type.

    Boundaries are matched on WHOLE LINES at the element indent. Never use
    text.index('            </l>') to find the collection close: str.index
    is substring matching, so a deeper-indented '</l>' contains the
    12-space one and matches first. Doing that spliced the element inside
    another element on 2026-07-26 -- still valid XML, silently dropped by
    XAE.
    """
    for i, line in enumerate(lines):
        if f'"{type_name}"' in line and "VisualElementTypeName" in line:
            s = i
            while lines[s].rstrip("\r\n") != INDENT_O:
                s -= 1
            e = i
            while lines[e].rstrip("\r\n") != INDENT_C:
                e += 1
            yield s, e, "".join(lines[s:e + 1])


def set_member(text, member_id, value):
    pat = re.compile(
        r'(<v n="Id">' + re.escape(member_id) + r'</v>\s*\n\s*<v n="Value">)(.*?)(</v>)',
        re.DOTALL,
    )
    out, n = pat.subn(lambda m: m.group(1) + value + m.group(3), text, count=1)
    if n != 1:
        raise SystemExit(f"member {member_id}: expected 1 replacement, got {n}")
    return out


def main():
    text = DST.read_text(encoding="utf-8")

    if "bNoSensors" in text:
        print("bNoSensors already present in AutoMain.TcVIS - nothing to do.")
        return 0

    lines = text.splitlines(keepends=True)
    found = list(blocks(lines, "VisuFbCheckbox"))
    print(f"found {len(found)} existing checkbox element(s)")
    src = next((b for b in found if '<v n="Value">"Auto Mode"</v>' in b[2]), None)
    if src is None:
        raise SystemExit("could not locate the 'Auto Mode' checkbox to clone")
    src_start, src_end, _ = src
    print(f"cloning the 'Auto Mode' block at lines {src_start+1}-{src_end+1}")

    new = src[2]
    for mid, val in (
        (M_LEFT, str(LEFT)), (M_TOP, str(TOP)),
        (M_WIDTH, str(WIDTH)), (M_HEIGHT, str(HEIGHT)),
        (M_TEXT, f'"{LABEL}"'), (M_BOOLVAR, f'"{VAR}"'),
        (M_COUNTER, f'"{NEW_COUNTER}"'),
    ):
        new = set_member(new, mid, val)

    new = re.sub(r'(<v n="VisualElementIdentifier">")GenElemInst_\d+("</v>)',
                 lambda m: m.group(1) + f"GenElemInst_{NEW_UID}" + m.group(2),
                 new, count=1)
    new = re.sub(r'(<v n="VisualElementIdentification">)\{[0-9a-fA-F-]+\}(</v>)',
                 lambda m: m.group(1) + NEW_GUID + m.group(2), new, count=1)
    new = re.sub(r'(<v n="VisualElementId">)\d+(</v>)',
                 lambda m: m.group(1) + str(NEW_ELEM_ID) + m.group(2), new, count=1)

    if NEW_GUID in text:
        raise SystemExit(f"GUID {NEW_GUID} already used in the file")

    # Insert as the SIBLING immediately after the cloned block. This is an
    # exact line position derived from the block scanner, so the new element
    # lands as a direct child of VisualElementList by construction -- no
    # searching for the collection's closing tag.
    out = "".join(lines[:src_end + 1]) + new + "".join(lines[src_end + 1:])

    DST.write_text(out, encoding="utf-8")
    print(f"added '{LABEL}' -> {VAR} at ({LEFT},{TOP}) {WIDTH}x{HEIGHT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
