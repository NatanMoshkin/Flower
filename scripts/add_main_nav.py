"""Checklist s6: add a nav button to Main.TcVIS.

Clones Main's existing "Pistons Manual" button -- a VisuFbElemSimple whose
VisualElementInputActions carries a ChangeVisuInputAction -- and rewrites
the label, the nav target (Assign33), geometry, and the identity fields.
Also registers the label in GlobalTextList.TcGTLO, keyed by the element's
counter member, which is how classic VISU resolves static text.

Only ever point at a visu that already exists; a dangling ChangeVisu target
breaks the build.

Run:  python scripts/add_main_nav.py "Gripper Manual" GripperManual 423
      python scripts/add_main_nav.py "Robot" Robot 243
Then: python scripts/validate_visu.py Main.TcVIS
"""

from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1] / (
    "Panel_PLC_HMI/167_01_Saad_PLC/167_01_Saad_PLC/PLC1")
MAIN = ROOT / "VISU/Main.TcVIS"
VISU_DIR = ROOT / "VISU"
GTL = ROOT / "GlobalTextList.TcGTLO"

M_LEFT, M_TOP = "1649127785L", "357335551L"
M_WIDTH, M_HEIGHT = "2422045748L", "2134141914L"
M_CX, M_CY = "550940142L", "1473355128L"
M_TEXT, M_COUNTER = "390574330L", "823443203L"

INDENT_O, INDENT_C = "              <o>", "              </o>"

# Deterministic identities per target, so re-running is stable.
SLOTS = {
    "GripperManual": (10, 551, "{a1b2c3d4-0e5f-4a6b-9c7d-000000000201}"),
    "Robot":         (11, 552, "{a1b2c3d4-0e5f-4a6b-9c7d-000000000202}"),
}


def set_member(text, member_id, value):
    pat = re.compile(
        r'(<v n="Id">' + re.escape(member_id) + r'</v>\s*\n\s*<v n="Value">)(.*?)(</v>)',
        re.DOTALL)
    out, n = pat.subn(lambda m: m.group(1) + value + m.group(3), text, count=1)
    if n != 1:
        raise SystemExit(f"member {member_id}: expected 1 replacement, got {n}")
    return out


def get_member(text, member_id):
    m = re.search(r'<v n="Id">' + re.escape(member_id) +
                  r'</v>\s*\n\s*<v n="Value">(.*?)</v>', text, re.DOTALL)
    return m.group(1) if m else None


def main(argv):
    if len(argv) != 3:
        raise SystemExit(__doc__)
    label, target, left = argv[0], argv[1], int(argv[2])

    if not (VISU_DIR / f"{target}.TcVIS").exists():
        raise SystemExit(f"nav target {target}.TcVIS does not exist - "
                         f"a dangling ChangeVisu breaks the build")
    if target not in SLOTS:
        raise SystemExit(f"no identity slot defined for {target!r}")
    elem_id, counter, guid = SLOTS[target]

    text = MAIN.read_text(encoding="utf-8")
    if f'<v n="Assign33">"{target}"</v>' in text:
        print(f"nav button to {target} already present - nothing to do.")
        return 0

    lines = text.splitlines(keepends=True)
    src = None
    for i, l in enumerate(lines):
        if '"VisuFbElemSimple"' in l and "VisualElementTypeName" in l:
            s = i
            while lines[s].rstrip("\r\n") != INDENT_O:
                s -= 1
            e = i
            while lines[e].rstrip("\r\n") != INDENT_C:
                e += 1
            body = "".join(lines[s:e + 1])
            if "ChangeVisuInputAction" in body:
                src = (s, e, body)
                break
    if src is None:
        raise SystemExit("no VisuFbElemSimple with a ChangeVisu action to clone")
    s, e, body = src
    print(f"cloning nav button at lines {s+1}-{e+1} "
          f"(label {get_member(body, M_TEXT)}, target "
          f"{re.search(r'Assign33.>(.*?)</v>', body).group(1)})")

    top = int(get_member(body, M_TOP))
    w, h = int(get_member(body, M_WIDTH)), int(get_member(body, M_HEIGHT))
    # Sanity-check the centre convention before relying on it.
    cx, cy = int(get_member(body, M_CX)), int(get_member(body, M_CY))
    old_left = int(get_member(body, M_LEFT))
    if (cx, cy) != (old_left + w // 2, top + h // 2):
        raise SystemExit(f"unexpected centre convention: ({cx},{cy}) vs "
                         f"({old_left + w//2},{top + h//2})")

    new = body
    for mid, val in ((M_LEFT, str(left)), (M_TOP, str(top)),
                     (M_WIDTH, str(w)), (M_HEIGHT, str(h)),
                     (M_CX, str(left + w // 2)), (M_CY, str(top + h // 2)),
                     (M_TEXT, f'"{label}"'), (M_COUNTER, f'"{counter}"')):
        new = set_member(new, mid, val)
    new = re.sub(r'(<v n="Assign33">)"[^"]*"(</v>)',
                 lambda m: m.group(1) + f'"{target}"' + m.group(2), new, count=1)
    new = re.sub(r'(<v n="VisualElementIdentifier">")GenElemInst_\d+("</v>)',
                 lambda m: m.group(1) + f"GenElemInst_{elem_id}" + m.group(2),
                 new, count=1)
    new = re.sub(r'(<v n="VisualElementIdentification">)\{[0-9a-fA-F-]+\}(</v>)',
                 lambda m: m.group(1) + guid + m.group(2), new, count=1)
    new = re.sub(r'(<v n="VisualElementId">)\d+(</v>)',
                 lambda m: m.group(1) + str(elem_id) + m.group(2), new, count=1)
    if guid in text:
        raise SystemExit(f"GUID {guid} already used")

    # Sibling insert immediately after the cloned block -- an exact position,
    # not a search for the collection's closing tag.
    out = "".join(lines[:e + 1]) + new + "".join(lines[e + 1:])

    # Keep the id generators above anything we used.
    out = re.sub(r'(<v n="UniqueIdGenerator">")\d+("</v>)',
                 lambda m: m.group(1) + "50" + m.group(2), out, count=1)
    out = re.sub(r'(<v n="LastUsedIdForIdentifier">)\d+(</v>)',
                 lambda m: m.group(1) + "50" + m.group(2), out, count=1)
    MAIN.write_text(out, encoding="utf-8")
    print(f"added nav button {label!r} -> {target} at ({left},{top}) {w}x{h}")

    # Static text lives in GlobalTextList keyed by the counter member.
    gtl = GTL.read_text(encoding="utf-8")
    if f'<v n="TextID">"{counter}"</v>' not in gtl:
        anchor = '            <o>\n              <v n="TextID">"550"</v>'
        if anchor not in gtl:
            print("  WARNING: GlobalTextList anchor not found; XAE will add "
                  "the entry on first open")
        else:
            entry = ('            <o>\n'
                     f'              <v n="TextID">"{counter}"</v>\n'
                     f'              <v n="TextDefault">"{label}"</v>\n'
                     '              <l n="LanguageTexts" t="ArrayList" />\n'
                     '            </o>\n')
            GTL.write_text(gtl.replace(anchor, entry + anchor, 1), encoding="utf-8")
            print(f"  registered TextID {counter} = {label!r} in GlobalTextList")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
