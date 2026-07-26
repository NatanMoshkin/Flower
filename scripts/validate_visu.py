"""Generic structural validator for any classic VISU (.TcVIS) page.

The invariant that matters: every typed visual element must be a DIRECT
child of the single <l n="VisualElementList">. An element spliced inside
another element is still well-formed XML -- xml.dom.minidom parses it
happily -- and XAE then silently drops it with no error. That bug shipped
on 2026-07-26; this is the check that catches it.

Also verifies the object GUID is self-consistent (Visu Id == every
VisualElementOwningObjectGuid) and that element identities are unique.

Run:  python scripts/validate_visu.py <file.TcVIS> [more.TcVIS ...]
      python scripts/validate_visu.py            # all panel VISUs
Exit: 0 = sound, 1 = problem.
"""

from __future__ import annotations

import pathlib
import re
import sys
import xml.etree.ElementTree as ET

VISU_DIR = pathlib.Path(__file__).resolve().parents[1] / (
    "Panel_PLC_HMI/167_01_Saad_PLC/167_01_Saad_PLC/PLC1/VISU")

M_TEXT, M_TOP, M_LEFT = "390574330L", "357335551L", "1649127785L"
M_BOOLVAR, M_TAP = "743958181L", "1186196937L"


def member(elem, member_id):
    for lst in elem.iter("l"):
        if lst.get("n") != "VisualElemMemberList":
            continue
        for o in lst.findall("o"):
            vs = o.findall("v")
            if vs and vs[0].get("n") == "Id" and vs[0].text == member_id:
                for v in vs[1:]:
                    if v.get("n") == "Value":
                        return v.text
    return None


def check(path: pathlib.Path) -> list[str]:
    problems: list[str] = []
    raw = path.read_text(encoding="utf-8")
    root = ET.parse(path).getroot()

    lists = [l for l in root.iter("l") if l.get("n") == "VisualElementList"]
    if len(lists) != 1:
        return [f"expected exactly 1 VisualElementList, found {len(lists)}"]
    vlist = lists[0]

    typed = "./v[@n='VisualElementTypeName']"
    direct = [o for o in vlist.findall("o") if o.find(typed) is not None]
    subtree = [o for o in vlist.iter("o") if o.find(typed) is not None]

    print(f"\n=== {path.name} ===")
    print(f"  {len(direct)} direct children / {len(subtree)} in subtree")
    if len(direct) != len(subtree):
        problems.append(
            f"{len(subtree) - len(direct)} element(s) NOT direct children of "
            f"VisualElementList -- spliced inside another element; XAE will "
            f"silently drop them")

    # Object GUID self-consistency.
    m = re.search(r'<Visu Name="([^"]+)" Id="(\{[0-9a-fA-F-]+\})"', raw)
    if not m:
        problems.append("could not read <Visu Name=.. Id=..> header")
    else:
        name, guid = m.group(1), m.group(2)
        if name != path.stem:
            problems.append(f"Visu Name {name!r} != filename {path.stem!r}")
        owning = set(re.findall(
            r'<v n="VisualElementOwningObjectGuid">(\{[0-9a-fA-F-]+\})</v>', raw))
        stray = owning - {guid}
        if stray:
            problems.append(f"owning GUID(s) {stray} != this object's {guid}")

    for o in direct:
        t = (o.findtext(typed) or "").strip('"')
        label = (member(o, M_TEXT) or "").strip('"')
        var = ((member(o, M_BOOLVAR) or member(o, M_TAP) or "").strip('"')
               or _frame_target(o))
        nav = o.findtext(".//v[@n='Assign33']")
        print(f"    {t:<20} {label[:28]:<28}"
              + (f" -> {var}" if var else "")
              + (f"  [nav {nav}]" if nav else ""))

    for key, xp in (("id", "./v[@n='VisualElementId']"),
                    ("guid", "./v[@n='VisualElementIdentification']"),
                    ("uid", "./v[@n='VisualElementIdentifier']")):
        vals = [o.findtext(xp) for o in direct]
        dupes = {v for v in vals if vals.count(v) > 1 and v is not None}
        if dupes:
            problems.append(f"duplicate {key}: {sorted(dupes)}")
    return problems


def _frame_target(o):
    for v in o.iter("v"):
        if v.get("n") == "BasicTypeNodeValue" and v.text and "GVL_" in v.text:
            return v.text.strip('"')
    return None


def cross_page_guids():
    """VisualElementIdentification must be unique across the WHOLE project.

    VisualElementId is page-scoped and legitimately repeats -- do not check
    it globally. Cloning a page copies its elements' GUIDs verbatim, which
    the compiler reports far from the cause as
    "Unknown type: '<Page>__inp__vis'" / "Lazy-typed variable 'instvar_0'
    could not be resolved". Per-page uniqueness does not catch it.
    """
    seen: dict[str, str] = {}
    problems = []
    for p in sorted(VISU_DIR.glob("*.TcVIS")):
        for guid in re.findall(
                r'<v n="VisualElementIdentification">(\{[0-9a-fA-F-]+\})</v>',
                p.read_text(encoding="utf-8")):
            if guid in seen and seen[guid] != p.stem:
                problems.append(f"element GUID {guid} used by both "
                                f"{seen[guid]} and {p.stem}")
            seen[guid] = p.stem
    print(f"\n=== cross-page ===\n  {len(seen)} distinct element GUIDs "
          f"across {len(list(VISU_DIR.glob('*.TcVIS')))} pages")
    return problems


def main(argv):
    paths = ([pathlib.Path(a) for a in argv]
             if argv else sorted(VISU_DIR.glob("*.TcVIS")))
    total = []
    for p in paths:
        if not p.exists():
            p = VISU_DIR / p.name
        total += [(p.name, x) for x in check(p)]
    total += [("<project>", x) for x in cross_page_guids()]
    print()
    if total:
        print(f"FAIL -- {len(total)} problem(s):")
        for f, x in total:
            print(f"  - [{f}] {x}")
        return 1
    print(f"OK -- {len(paths)} page(s) structurally sound.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
