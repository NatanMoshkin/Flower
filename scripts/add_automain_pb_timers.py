"""Add the two panel push-button HOLD durations to AutoMain.TcVIS.

    tPbStopHoldMs   -- how long RED PB1 must be held in Auto to STOP
    tPbStartHoldMs  -- how long GREEN PB3 + ORANGE PB2 must be held to start a bulb

Both are operator-tunable by decision (2026-08-05), so they need to be on the
panel rather than compiled in.

Same-file clone, which makes this simpler than scripts/add_automain_timers.py:
that one had to pull its numeric-input template across from Robot.TcVIS and top
up AutoMain's TypeList. AutoMain now already HAS five of these field pairs, so
the donor is one of its own -- no TypeList merge, no cross-file GUID risk.

Layout continues the existing right-column rhythm: the five cycle timers sit at
y = 175/215/255/295/335 in the x 500-780 column, so these take y = 375 and 415.
The 800x480 panel leaves room (415 + 28 = 443).

InputBoxMin/Max are left as the donor has them (empty). A hold that is too short
is a usability problem, not a hazard, and the FB's TON simply does what it is
told; inventing bounds for a machine we cannot observe would be worse.

Idempotent: refuses to run twice.

Run:  python scripts/add_automain_pb_timers.py
Then: python scripts/validate_visu.py && python scripts/validate_automain.py
      ...and open AutoMain in TcXaeShell, rebuild, confirm both fields render.
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
M_CX, M_CY = "550940142L", "1473355128L"
M_TEXT, M_COUNTER = "390574330L", "823443203L"
M_TEXTVAR = "2477733581L"

INDENT_O, INDENT_C = "              <o>", "              </o>"
# Distinct namespace from add_automain_timers.py's 1004 so the two scripts can
# never mint the same VisualElementIdentification.
GUID_FMT = "{a1b2c3d4-0e5f-4a6b-9c7d-1005%08d}"

NEW = [("tPbStopHoldMs", "PB1 hold STOP (ms)"),
       ("tPbStartHoldMs", "PB2+PB3 hold (ms)")]

LBL_X, LBL_W = 500, 160
VAL_X, VAL_W = 665, 115
ROW_H, STEP = 28, 40
TOP0 = 375                 # continues after the 5 cycle timers (last at 335)

UID0, TID0 = 150, 650      # add_automain_timers.py used 130..139 / 640..644


def blocks(lines):
    for i, l in enumerate(lines):
        if "VisualElementTypeName" in l:
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
        raise SystemExit("member %s: expected 1 replacement, got %d" % (mid, n))
    return out


def has_member(text, mid):
    return re.search(r'<v n="Id">' + re.escape(mid) + r'</v>', text) is not None


def geom(t, left, top, w, h):
    for mid, v in ((M_LEFT, left), (M_TOP, top), (M_WIDTH, w), (M_HEIGHT, h)):
        t = set_member(t, mid, str(v))
    if has_member(t, M_CX):
        t = set_member(t, M_CX, str(left + w // 2))
        t = set_member(t, M_CY, str(top + h // 2))
    return t


def identity(text, n, owning):
    text = re.sub(r'(<v n="VisualElementIdentifier">")GenElemInst_\d+("</v>)',
                  lambda m: m.group(1) + "GenElemInst_%d" % n + m.group(2), text, 1)
    text = re.sub(r'(<v n="VisualElementIdentification">)\{[0-9a-fA-F-]+\}(</v>)',
                  lambda m: m.group(1) + GUID_FMT % n + m.group(2), text, 1)
    text = re.sub(r'(<v n="VisualElementOwningObjectGuid">)\{[0-9a-fA-F-]+\}(</v>)',
                  lambda m: m.group(1) + owning + m.group(2), text, 1)
    text = re.sub(r'(<v n="VisualElementId">)\d+(</v>)',
                  lambda m: m.group(1) + str(n) + m.group(2), text, 1)
    return text


def main():
    text = DST.read_text(encoding="utf-8")
    if "stCfg.tPbStopHoldMs" in text:
        print("PB hold timers already present - nothing to do.")
        return 0
    if "stCfg.tDwellPushMs" not in text:
        raise SystemExit("AutoMain has no cycle timers to clone from -- run "
                         "scripts/add_automain_timers.py first.")

    owning = re.search(r'<Visu Name="AutoMain" Id="(\{[0-9a-fA-F-]+\})"',
                       text).group(1)
    print("AutoMain owning GUID %s" % owning)

    lines = text.splitlines(keepends=True)

    # Donor pair, both from AutoMain itself: the tStepTimeoutMs value field
    # (a textfield carrying an InputBoxInputAction) and any simple label.
    fld_src = next(b for s, e, b in blocks(lines)
                   if "InputBoxInputAction" in b and "stCfg.tStepTimeoutMs" in b)
    lbl_src = next(b for s, e, b in blocks(lines) if '"VisuFbElemSimple"' in b)
    print("cloned the tStepTimeoutMs field + a simple label from AutoMain itself")

    uid, tid, texts, out = UID0, TID0, [], []
    for i, (name, label) in enumerate(NEW):
        top = TOP0 + i * STEP

        lbl = geom(lbl_src, LBL_X, top, LBL_W, ROW_H)
        lbl = set_member(lbl, M_TEXT, '"%s"' % label)
        lbl = set_member(lbl, M_COUNTER, '"%d"' % tid)
        texts.append((tid, label))
        tid += 1
        out.append(identity(lbl, uid, owning))
        uid += 1

        fld = geom(fld_src, VAL_X, top, VAL_W, ROW_H)
        fld = set_member(fld, M_TEXTVAR, '"stCfg.%s"' % name)
        out.append(identity(fld, uid, owning))
        uid += 1
        print("  %-16s y=%d   label %r" % (name, top, label))

    last = max(e for s, e, b in blocks(lines))
    result = "".join(lines[:last + 1]) + "".join(out) + "".join(lines[last + 1:])
    result = re.sub(r'(<v n="UniqueIdGenerator">")\d+("</v>)',
                    lambda m: m.group(1) + str(uid + 10) + m.group(2), result, 1)
    result = re.sub(r'(<v n="LastUsedIdForIdentifier">)\d+(</v>)',
                    lambda m: m.group(1) + str(uid + 10) + m.group(2), result, 1)
    DST.write_text(result, encoding="utf-8")
    print("\nwrote %s: +%d elements (2 labels + 2 fields)" % (DST.name, len(out)))

    gtl = GTL.read_text(encoding="utf-8")
    anchor = '            <o>\n              <v n="TextID">"550"</v>'
    entries = "".join(
        '            <o>\n'
        '              <v n="TextID">"%s"</v>\n'
        '              <v n="TextDefault">"%s"</v>\n'
        '              <l n="LanguageTexts" t="ArrayList" />\n'
        '            </o>\n' % (t, d)
        for t, d in texts if '<v n="TextID">"%s"</v>' % t not in gtl)
    if entries and anchor in gtl:
        GTL.write_text(gtl.replace(anchor, entries + anchor, 1), encoding="utf-8")
        print("registered %d TextID(s) in GlobalTextList" % len(texts))
    else:
        print("!! GlobalTextList anchor not found - register the TextIDs by hand")
    return 0


if __name__ == "__main__":
    sys.exit(main())
