"""Split the panel's START into ENABLE AUTO + START on AutoMain.TcVIS.

Two edits, both driven by the arming model:

  * the existing button bound to ``stMasterAutoCycle.bStart`` is relabelled
    **ENABLE AUTO**, because that is what it does -- home the pistons and arm.
    Only the caption changes; the PLC symbol stays ``bStart``. Renaming the
    symbol would break every binding, the FlowerPyHmi contract and the tests,
    for a caption.
  * a new button bound to ``stMasterAutoCycle.bStartCycle`` is added, labelled
    **START**, which runs one bulb from IDLE -- the HMI parallel to holding the
    orange PB2 + green PB3 combo, and to the robot's CMD:1.

``bStartCycle`` is a separate PLC field on purpose. ``bStart`` means "arm" and
is accepted in NOT_HOMED only; overloading it to also mean "run a bulb" in IDLE
would give one symbol two state-dependent meanings, which is the shape that let
a green-before-orange combo press silently lose its bulb request (fixed
2026-08-05 by removing START from IDLE -- do not put it back).

Clones AutoMain's own STOP button rather than authoring an element. These files
use numeric-ID serialization and XAE silently drops anything it cannot parse, so
cloning a block already proven on this page is the only safe way to add one.

Geometry: (300, 255) 120x50 -- directly under RESET, inside the command cluster.
Verified free before choosing it: the checkbox rows below the buttons span
x=20..260 only, and the timer column starts at x=500, so x=300..420 / y=255..305
is empty. There is deliberately no room on the button row itself: a fourth
button at x=440 would run to 560 and collide with the tDwellPushMs caption.

Idempotent -- re-running is a no-op.

Run:  python scripts/add_automain_start_cycle_button.py
Then: python scripts/validate_visu.py AutoMain.TcVIS
      python scripts/validate_automain.py
"""

from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1] / (
    "Panel_PLC_HMI/167_01_Saad_PLC/167_01_Saad_PLC/PLC1")
PAGE = ROOT / "VISU/AutoMain.TcVIS"
GTL = ROOT / "GlobalTextList.TcGTLO"

M_LEFT, M_TOP = "1649127785L", "357335551L"
M_WIDTH, M_HEIGHT = "2422045748L", "2134141914L"
M_CX, M_CY = "550940142L", "1473355128L"
M_TEXT, M_COUNTER = "390574330L", "823443203L"
M_TAP = "1186196937L"

INDENT_O, INDENT_C = "              <o>", "              </o>"

# Deterministic identity, so re-running cannot mint a second element.
NEW_ID = 106
# 1106 is the TextID orphaned when remove_continuous_checkbox.py deleted the
# Continuous checkbox on 2026-07-27. Verified unreferenced by any element on any
# page before reuse -- grep '"1106"' across VISU/ returns this page only. 1107
# and 1108 are live, which is why this reuses an orphan rather than taking the
# next number.
NEW_COUNTER = "1106"
NEW_GUID = "{a1b2c3d4-0e5f-4a6b-9c7d-000000000301}"
NEW_LEFT, NEW_TOP = 300, 255
NEW_LABEL = "START"
NEW_TAP = "stMasterAutoCycle.bStartCycle"

ARM_LABEL = "ENABLE AUTO"
ARM_TAP = "stMasterAutoCycle.bStart"


def set_member(text: str, member_id: str, value: str) -> str:
    pat = re.compile(
        r'(<v n="Id">' + re.escape(member_id) + r'</v>\s*\n\s*<v n="Value">)(.*?)(</v>)',
        re.DOTALL)
    out, n = pat.subn(lambda m: m.group(1) + value + m.group(3), text, count=1)
    if n != 1:
        raise SystemExit(f"member {member_id}: expected 1 replacement, got {n}")
    return out


def tap_of(body: str) -> str | None:
    """The tap binding, quotes stripped -- member values are stored quoted."""
    v = get_member(body, M_TAP)
    return v.strip('"') if v is not None else None


def get_member(text: str, member_id: str) -> str | None:
    m = re.search(r'<v n="Id">' + re.escape(member_id) +
                  r'</v>\s*\n\s*<v n="Value">(.*?)</v>', text, re.DOTALL)
    return m.group(1) if m else None


def blocks(lines: list[str], type_name: str):
    """Yield (start, end, body) for each element of the given type."""
    for i, l in enumerate(lines):
        if f'"{type_name}"' in l and "VisualElementTypeName" in l:
            s = i
            while lines[s].rstrip("\r\n") != INDENT_O:
                s -= 1
            e = i
            while lines[e].rstrip("\r\n") != INDENT_C:
                e += 1
            yield s, e, "".join(lines[s:e + 1])


def gtl_register(counter: str, label: str) -> None:
    gtl = GTL.read_text(encoding="utf-8")
    if f'<v n="TextID">"{counter}"</v>' in gtl:
        # already there -- make sure it says what we want
        pat = re.compile(r'(<v n="TextID">"' + re.escape(counter) +
                         r'"</v>\s*\n\s*<v n="TextDefault">")(.*?)(")')
        cur = pat.search(gtl)
        if cur and cur.group(2) != label:
            GTL.write_text(pat.sub(lambda m: m.group(1) + label + m.group(3), gtl, 1),
                           encoding="utf-8")
            print(f"  GlobalTextList: TextID {counter} {cur.group(2)!r} -> {label!r}")
        return
    anchor = '            <o>\n              <v n="TextID">"550"</v>'
    if anchor not in gtl:
        print("  WARNING: GlobalTextList anchor not found; XAE will add the "
              "entry on first open")
        return
    entry = ('            <o>\n'
             f'              <v n="TextID">"{counter}"</v>\n'
             f'              <v n="TextDefault">"{label}"</v>\n'
             '              <l n="LanguageTexts" t="ArrayList" />\n'
             '            </o>\n')
    GTL.write_text(gtl.replace(anchor, entry + anchor, 1), encoding="utf-8")
    print(f"  GlobalTextList: registered TextID {counter} = {label!r}")


def main() -> int:
    text = PAGE.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)

    arm = stop = None
    for s, e, body in blocks(lines, "VisuFbElemButton"):
        tap = tap_of(body)
        if tap == ARM_TAP:
            arm = (s, e, body)
        elif tap == "stMasterAutoCycle.bStop":
            stop = (s, e, body)
    if arm is None:
        raise SystemExit(f"no button bound to {ARM_TAP} -- wrong page?")
    if stop is None:
        raise SystemExit("no STOP button to clone")

    already = f'"{NEW_TAP}"' in text
    changed = False

    # ---- 1. relabel the arming button --------------------------------------
    s, e, body = arm
    arm_counter = get_member(body, M_COUNTER).strip('"')
    if get_member(body, M_TEXT) != f'"{ARM_LABEL}"':
        new_arm = set_member(body, M_TEXT, f'"{ARM_LABEL}"')
        lines[s:e + 1] = [new_arm]
        text = "".join(lines)
        lines = text.splitlines(keepends=True)
        changed = True
        print(f"relabelled the {ARM_TAP} button -> {ARM_LABEL!r}")
    else:
        print(f"the {ARM_TAP} button already reads {ARM_LABEL!r}")
    gtl_register(arm_counter, ARM_LABEL)

    # ---- 2. add the cycle-start button -------------------------------------
    if already:
        print(f"a button bound to {NEW_TAP} is already present")
    else:
        # re-locate STOP: line numbers may have shifted after the relabel
        stop = None
        for s, e, body in blocks(lines, "VisuFbElemButton"):
            if tap_of(body) == "stMasterAutoCycle.bStop":
                stop = (s, e, body)
        s, e, body = stop
        w = int(get_member(body, M_WIDTH))
        h = int(get_member(body, M_HEIGHT))
        # Confirm the centre convention on THIS block before relying on it.
        cx, cy = int(get_member(body, M_CX)), int(get_member(body, M_CY))
        ol, ot = int(get_member(body, M_LEFT)), int(get_member(body, M_TOP))
        if (cx, cy) != (ol + w // 2, ot + h // 2):
            raise SystemExit(f"unexpected centre convention: ({cx},{cy}) vs "
                             f"({ol + w // 2},{ot + h // 2})")
        if NEW_GUID in text:
            raise SystemExit(f"GUID {NEW_GUID} already used")

        new = body
        for mid, val in ((M_LEFT, str(NEW_LEFT)), (M_TOP, str(NEW_TOP)),
                         (M_CX, str(NEW_LEFT + w // 2)),
                         (M_CY, str(NEW_TOP + h // 2)),
                         (M_TEXT, f'"{NEW_LABEL}"'),
                         (M_COUNTER, f'"{NEW_COUNTER}"'),
                         (M_TAP, f'"{NEW_TAP}"')):
            new = set_member(new, mid, val)
        new = re.sub(r'(<v n="VisualElementIdentifier">")GenElemInst_\d+("</v>)',
                     lambda m: m.group(1) + f"GenElemInst_{NEW_ID}" + m.group(2),
                     new, count=1)
        new = re.sub(r'(<v n="VisualElementIdentification">)\{[0-9a-fA-F-]+\}(</v>)',
                     lambda m: m.group(1) + NEW_GUID + m.group(2), new, count=1)
        new = re.sub(r'(<v n="VisualElementId">)\d+(</v>)',
                     lambda m: m.group(1) + str(NEW_ID) + m.group(2), new, count=1)

        # Sibling insert immediately after the cloned block -- an exact
        # position, not a search for the collection's closing tag.
        text = "".join(lines[:e + 1]) + new + "".join(lines[e + 1:])
        text = re.sub(r'(<v n="UniqueIdGenerator">")\d+("</v>)',
                      lambda m: m.group(1) + "150" + m.group(2), text, count=1)
        text = re.sub(r'(<v n="LastUsedIdForIdentifier">)\d+(</v>)',
                      lambda m: m.group(1) + "150" + m.group(2), text, count=1)
        changed = True
        print(f"added {NEW_LABEL!r} button -> {NEW_TAP} "
              f"at ({NEW_LEFT},{NEW_TOP}) {w}x{h}")
        gtl_register(NEW_COUNTER, NEW_LABEL)

    if changed:
        PAGE.write_text(text, encoding="utf-8")
    else:
        print("nothing to do.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
