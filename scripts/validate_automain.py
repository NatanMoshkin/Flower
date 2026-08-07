"""Structural validator for AutoMain.TcVIS.

XML well-formedness is NOT enough for classic VISU files: a complete
<o>..</o> element spliced into the middle of ANOTHER element is still
valid XML, and XAE then silently drops it. That exact bug shipped on
2026-07-26. This validates the thing that actually matters -- that every
visual element is a DIRECT child of the VisualElementList collection --
plus identity uniqueness.

Run:  python scripts/validate_automain.py
Exit: 0 = structurally sound, 1 = problem.
"""

from __future__ import annotations

import pathlib
import sys
import xml.etree.ElementTree as ET

P = pathlib.Path(__file__).resolve().parents[1] / (
    "Panel_PLC_HMI/167_01_Saad_PLC/167_01_Saad_PLC/PLC1/VISU/AutoMain.TcVIS")

M_TEXT, M_TOP = "390574330L", "357335551L"
M_BOOLVAR = "743958181L"   # Checkbox: toggled bool
M_TAP = "1186196937L"      # Button: tap input bool

# label -> (element type, bound variable or None, member id holding it)
EXPECTED = {
    "Auto Main":                ("VisuFbElemSimple", None,                       None),
    # START was split in two on 2026-08-05. The caption moved, the symbol did
    # not: bStart still means "home and arm" and is accepted in NOT_HOMED only,
    # so the button that writes it now reads ENABLE AUTO. The button captioned
    # START writes the new bStartCycle and runs one bulb from IDLE.
    "ENABLE AUTO":              ("VisuFbElemButton", "stMasterAutoCycle.bStart", M_TAP),
    "START":                    ("VisuFbElemButton", "stMasterAutoCycle.bStartCycle", M_TAP),
    "STOP":                     ("VisuFbElemButton", "stMasterAutoCycle.bStop",  M_TAP),
    "RESET":                    ("VisuFbElemButton", "stMasterAutoCycle.bReset", M_TAP),
    # No "Continuous" row. That checkbox was deliberately deleted on 2026-07-27
    # by remove_continuous_checkbox.py -- bContinuous is dead twice over (MAIN
    # force-clears it every scan, and FB_MasterAutoCycle dropped it from IDLE's
    # cycle-start condition), so a control that visibly reverted when ticked was
    # worse than no control. This validator kept expecting it and failed for
    # nine days on a change that was correct.
    # bAutoMode moved OUT of ST_HmiMasterAutoCfg on 2026-08-06 into plain
    # GVL_HMI (volatile, initialised TRUE) so every boot comes up Automatic.
    # The binding is therefore ABSOLUTE now, not interface-relative like the
    # stCfg.* rows -- AutoMain is embedded as a frame in Main and declares
    # stCfg, but GVL_HMI is reached globally.
    "Auto Mode":                ("VisuFbCheckbox",   "GVL_HMI.bAutoMode",        M_BOOLVAR),
    # The two bench checkboxes and all seven timer rows MOVED to AutoConfig on
    # 2026-08-06 (TODO #1): AutoMain is embedded as a frame in Main, so tuning
    # controls were sitting on the home screen where an operator running bulbs
    # has no reason to see them. They are checked by validate_autoconfig.py now.
    # Auto Mode deliberately stayed -- it is a machine MODE, not a tuning value,
    # and it is no longer part of stCfg at all.
}

problems: list[str] = []


def member(elem, member_id):
    """Value of the <o><v n='Id'>ID</v><v n='Value'>..</v></o> member."""
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


def main():
    root = ET.parse(P).getroot()

    lists = [l for l in root.iter("l") if l.get("n") == "VisualElementList"]
    if len(lists) != 1:
        print(f"FAIL: expected exactly 1 VisualElementList, found {len(lists)}")
        return 1
    vlist = lists[0]

    # THE check the old validator missed: direct children only.
    direct = vlist.findall("o")
    nested = [o for o in vlist.iter("o")
              if o.find("./v[@n='VisualElementTypeName']") is not None]
    typed_direct = [o for o in direct
                    if o.find("./v[@n='VisualElementTypeName']") is not None]

    print(f"VisualElementList: {len(direct)} direct children, "
          f"{len(typed_direct)} of them typed visual elements")
    print(f"typed visual elements anywhere in the subtree: {len(nested)}")
    if len(typed_direct) != len(nested):
        problems.append(
            f"{len(nested) - len(typed_direct)} visual element(s) are NOT direct "
            f"children of VisualElementList -- spliced inside another element. "
            f"XAE will silently drop them.")

    found = {}
    for o in typed_direct:
        label = (member(o, M_TEXT) or "").strip('"')
        found[label] = {
            "type": o.findtext("./v[@n='VisualElementTypeName']", "").strip('"'),
            "var": ((member(o, M_BOOLVAR) or member(o, M_TAP) or "")
                    .strip('"') or None),
            "top": member(o, M_TOP),
            "id": o.findtext("./v[@n='VisualElementId']"),
            "guid": o.findtext("./v[@n='VisualElementIdentification']"),
            "uid": o.findtext("./v[@n='VisualElementIdentifier']"),
        }

    print("\nelements found (direct children):")
    for label, d in sorted(found.items(), key=lambda kv: int(kv[1]["top"] or 0)):
        print(f"  y={d['top']:>4}  {d['type']:<20} {label!r}"
              + (f" -> {d['var']}" if d["var"] else ""))

    for label, (typ, var, _mid) in EXPECTED.items():
        if label not in found:
            problems.append(f"missing element {label!r}")
            continue
        if found[label]["type"] != typ:
            problems.append(f"{label!r}: type {found[label]['type']} != {typ}")
        if var and found[label]["var"] != var:
            problems.append(f"{label!r}: bound to {found[label]['var']!r} != {var!r}")

    for key in ("id", "guid", "uid"):
        vals = [d[key] for d in found.values()]
        if len(vals) != len(set(vals)):
            problems.append(f"duplicate {key} among elements: {vals}")

    print()
    if problems:
        print(f"FAIL -- {len(problems)} problem(s):")
        for p in problems:
            print(f"  - {p}")
        return 1
    # len(found) undercounts: it is keyed by label and the two textfields
    # share the label "%s". typed_direct is the real element count.
    print(f"OK -- {len(typed_direct)} elements, all direct children, "
          f"identities unique.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
