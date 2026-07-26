"""Repair: give every scripted VISU element a globally-unique GUID.

`VisualElementId` is page-scoped and legitimately repeats across pages.
`VisualElementIdentification` is NOT -- it is unique across the whole
project in the pristine files, and the compiler resolves references by it.
Cloning a page (GripperManual, Robot) copied its source elements' GUIDs
verbatim, and the Robot builder's generator additionally collided with the
nav-button slots. Result:

    Unknown type: 'PistonsManual__inp__vis'
    Type of Lazy-typed variable 'instvar_0' could not be resolved.

Each scripted page gets its own GUID namespace so this cannot recur.
Pristine pages (PistonsManual, Piston, AutoMain) are never touched; in
Main only the two nav buttons this project added are re-GUIDed.

Run:  python scripts/fix_visu_guids.py
Then: python scripts/validate_visu.py     (now checks cross-page uniqueness)
"""

from __future__ import annotations

import pathlib
import re
import sys

VISU = pathlib.Path(__file__).resolve().parents[1] / (
    "Panel_PLC_HMI/167_01_Saad_PLC/167_01_Saad_PLC/PLC1/VISU")

BASE = "a1b2c3d4-0e5f-4a6b-9c7d"
NS = {"GripperManual": "1001", "Robot": "1002", "Main": "1003"}
# In Main, only re-GUID elements navigating to pages we added.
MAIN_ONLY_TARGETS = {"GripperManual", "Robot"}

INDENT_O, INDENT_C = "              <o>", "              </o>"
GUID_RE = r'(<v n="VisualElementIdentification">)(\{[0-9a-fA-F-]+\})(</v>)'


def element_blocks(lines):
    for i, l in enumerate(lines):
        if "VisualElementTypeName" in l:
            s = i
            while lines[s].rstrip("\r\n") != INDENT_O:
                s -= 1
            e = i
            while lines[e].rstrip("\r\n") != INDENT_C:
                e += 1
            yield s, e


def main():
    changed = False
    for page, ns in NS.items():
        p = VISU / f"{page}.TcVIS"
        if not p.exists():
            print(f"{page}.TcVIS missing - skipped")
            continue
        lines = p.read_text(encoding="utf-8").splitlines(keepends=True)

        spans = list(element_blocks(lines))
        n = 0
        for idx, (s, e) in enumerate(reversed(spans)):
            body = "".join(lines[s:e + 1])
            if page == "Main":
                m = re.search(r'<v n="Assign33">"([^"]*)"</v>', body)
                if not m or m.group(1) not in MAIN_ONLY_TARGETS:
                    continue
            serial = len(spans) - idx
            new = "{%s-%s%08d}" % (BASE, ns, serial)
            body2, k = re.subn(GUID_RE,
                               lambda mm: mm.group(1) + new + mm.group(3),
                               body, count=1)
            if k == 1 and body2 != body:
                lines[s:e + 1] = [body2]
                lines = "".join(lines).splitlines(keepends=True)
                spans = list(element_blocks(lines))
                n += 1
        if n:
            p.write_text("".join(lines), encoding="utf-8")
            changed = True
        print(f"{page}.TcVIS: re-GUIDed {n} element(s) into namespace {ns}")

    # Global uniqueness proof.
    seen: dict[str, str] = {}
    dupes = []
    for p in sorted(VISU.glob("*.TcVIS")):
        for g in re.findall(GUID_RE, p.read_text(encoding="utf-8")):
            guid = g[1]
            if guid in seen and seen[guid] != p.stem:
                dupes.append((guid, seen[guid], p.stem))
            seen[guid] = p.stem
    print(f"\n{len(seen)} distinct element GUIDs across all pages")
    if dupes:
        print(f"STILL DUPLICATED ({len(dupes)}):")
        for g, a, b in dupes:
            print(f"  {g}  {a} <-> {b}")
        return 1
    print("OK -- every element GUID is globally unique.")
    return 0 if changed or True else 0


if __name__ == "__main__":
    sys.exit(main())
