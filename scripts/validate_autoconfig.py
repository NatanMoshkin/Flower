"""Structural + binding validator for AutoConfig.TcVIS.

The sibling of validate_automain.py, for the page the stCfg tuning controls moved
to on 2026-08-06. Same reasoning: XML well-formedness proves nothing about a
classic VISU, because a complete <o>..</o> nested inside another element is still
valid XML and XAE then silently drops it.

This page has one hazard validate_automain does not: **every binding here must be
ABSOLUTE.** AutoConfig is navigated to, not frame-embedded, so it receives no
interface parameters -- a leftover `stCfg.xxx` binding would resolve to nothing
and the field would sit there looking fine and reading zero. That is the check
worth having, and it is why the expected table spells each path out in full
rather than deriving it from a root constant.

Run:  python scripts/validate_autoconfig.py
Exit: 0 = sound, 1 = problem.
"""

from __future__ import annotations

import pathlib
import sys
import xml.etree.ElementTree as ET

P = pathlib.Path(__file__).resolve().parents[1] / (
    "Panel_PLC_HMI/167_01_Saad_PLC/167_01_Saad_PLC/PLC1/VISU/AutoConfig.TcVIS")

M_TEXT, M_TOP = "390574330L", "357335551L"
M_BOOLVAR = "743958181L"      # Checkbox: toggled bool
M_TEXTVAR = "2477733581L"     # Textfield: displayed variable
M_LEFT = "1649127785L"

CFG = "GVL_HmiPersistent.stMasterAutoCfg"

# The seven numeric fields all carry the label "%d", so they cannot be keyed by
# label like AutoMain's controls -- they are checked as a set of bindings instead.
EXPECTED_FIELD_BINDINGS = {
    f"{CFG}.tDwellPushMs",
    f"{CFG}.tPushRetractedDwellMs",
    f"{CFG}.tSepRetractedDwellMs",
    f"{CFG}.tStepTimeoutMs",
    f"{CFG}.tPlateWaitTimeoutMs",
    f"{CFG}.tPbStopHoldMs",
    f"{CFG}.tPbStartHoldMs",
}
EXPECTED_CHECKBOXES = {
    "No sensors (timed steps)": f"{CFG}.bNoSensors",
    "Bypass plate sensors":     f"{CFG}.bBypassPlateSensors",
}
EXPECTED_NAV = {"Back": "Main"}

problems: list[str] = []


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


def nav_of(elem):
    for v in elem.iter("v"):
        if v.get("n") == "Assign33":
            return (v.text or "").strip('"')
    return None


def main() -> int:
    if not P.exists():
        print(f"FAIL: {P.name} does not exist -- run build_autoconfig_page.py")
        return 1
    root = ET.parse(P).getroot()

    lists = [l for l in root.iter("l") if l.get("n") == "VisualElementList"]
    if len(lists) != 1:
        print(f"FAIL: expected exactly 1 VisualElementList, found {len(lists)}")
        return 1
    vlist = lists[0]

    direct = [o for o in vlist.findall("o")
              if o.find("./v[@n='VisualElementTypeName']") is not None]
    nested = [o for o in vlist.iter("o")
              if o.find("./v[@n='VisualElementTypeName']") is not None]
    print(f"VisualElementList: {len(direct)} direct typed elements, "
          f"{len(nested)} anywhere in the subtree")
    if len(direct) != len(nested):
        problems.append(
            f"{len(nested) - len(direct)} element(s) are NOT direct children of "
            f"VisualElementList -- spliced inside another element; XAE will "
            f"silently drop them")

    fields, checks, navs, others = set(), {}, {}, []
    print("\nelements:")
    for o in sorted(direct, key=lambda e: int(member(e, M_TOP) or 0)):
        ty = (o.findtext("./v[@n='VisualElementTypeName']") or "").strip('"')
        label = (member(o, M_TEXT) or "").strip('"')
        bind = ((member(o, M_BOOLVAR) or member(o, M_TEXTVAR) or "").strip('"')) or None
        nav = nav_of(o)
        print(f"  y={member(o, M_TOP):>4} x={member(o, M_LEFT):>4}  {ty:20s} "
              f"{label!r:28s}" + (f" -> {bind}" if bind else "")
              + (f"  [nav {nav}]" if nav else ""))
        if nav:
            navs[label] = nav
        elif ty == "VisuFbCheckbox":
            checks[label] = bind
        elif ty == "VisuFbElemTextfield":
            fields.add(bind)
        else:
            others.append(label)

    # THE check for this page: nothing may still be interface-relative.
    for b in list(fields) + list(checks.values()):
        if b and b.startswith("stCfg."):
            problems.append(
                f"binding {b!r} is still interface-relative -- AutoConfig is "
                f"navigated to, so it has no stCfg and this reads nothing")

    if fields != EXPECTED_FIELD_BINDINGS:
        for miss in sorted(EXPECTED_FIELD_BINDINGS - fields):
            problems.append(f"no numeric field bound to {miss}")
        for extra in sorted(fields - EXPECTED_FIELD_BINDINGS):
            problems.append(f"unexpected numeric field bound to {extra}")

    for label, want in EXPECTED_CHECKBOXES.items():
        if label not in checks:
            problems.append(f"missing checkbox {label!r}")
        elif checks[label] != want:
            problems.append(f"{label!r}: bound to {checks[label]!r} != {want!r}")

    for label, want in EXPECTED_NAV.items():
        if label not in navs:
            problems.append(f"missing nav button {label!r}")
        elif navs[label] != want:
            problems.append(f"{label!r}: navigates to {navs[label]!r} != {want!r}")

    for key, name in (("VisualElementId", "id"),
                      ("VisualElementIdentification", "guid"),
                      ("VisualElementIdentifier", "uid")):
        vals = [o.findtext(f"./v[@n='{key}']") for o in direct]
        if len(vals) != len(set(vals)):
            problems.append(f"duplicate {name} within the page: {vals}")

    print()
    if problems:
        print(f"FAIL -- {len(problems)} problem(s):")
        for p in problems:
            print(f"  - {p}")
        return 1
    print(f"OK -- {len(direct)} elements, {len(fields)} timers + "
          f"{len(checks)} checkboxes + {len(navs)} nav, all bindings absolute.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
