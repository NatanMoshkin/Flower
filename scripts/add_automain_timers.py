"""Add the 5 ST_HmiMasterAutoCfg timers to AutoMain.TcVIS's free column.

Cross-file clone: the numeric-input template lives on Robot.TcVIS, so each
copy needs its VisualElementOwningObjectGuid rewritten to AutoMain's object
GUID, and AutoMain's TypeList topped up with anything the donor block needs.

Bindings are INTERFACE-relative (stCfg.tDwellPushMs), not absolute. AutoMain
is embedded as a frame in Main and declares
    VAR_IN_OUT  stMasterAutoCycle : ST_HmiMasterAuto;
                stCfg : ST_HmiMasterAutoCfg;
so absolute GVL paths would be wrong here even though they are right on the
standalone Robot page.

Layout: AutoMain's existing content stops at x=480 / y=365 on the 800x480
panel, so the timers occupy x 500-780 on the same 40 px row rhythm as the
checkboxes.

InputBoxMin/Max are deliberately left empty. The robot tuning params have
vendor-documented ranges; these cycle timers do not, and inventing process
limits for a machine we cannot observe would be worse than leaving them
open. Set them once sane bounds are known.

Idempotent: refuses to run twice.

Run:  python scripts/add_automain_timers.py
Then: python scripts/validate_visu.py
      ...and open AutoMain in TcXaeShell, rebuild, confirm it renders.
"""

from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1] / (
    "Panel_PLC_HMI/167_01_Saad_PLC/167_01_Saad_PLC/PLC1")
DST = ROOT / "VISU/AutoMain.TcVIS"
DONOR = ROOT / "VISU/Robot.TcVIS"
GTL = ROOT / "GlobalTextList.TcGTLO"

M_LEFT, M_TOP = "1649127785L", "357335551L"
M_WIDTH, M_HEIGHT = "2422045748L", "2134141914L"
M_CX, M_CY = "550940142L", "1473355128L"
M_TEXT, M_COUNTER = "390574330L", "823443203L"
M_TEXTVAR = "2477733581L"

INDENT_O, INDENT_C = "              <o>", "              </o>"
NS = "1004"
GUID_FMT = "{a1b2c3d4-0e5f-4a6b-9c7d-" + NS + "%08d}"

TIMERS = ["tDwellPushMs", "tPushRetractedDwellMs", "tSepRetractedDwellMs",
          "tStepTimeoutMs", "tPlateWaitTimeoutMs"]

LBL_X, LBL_W = 500, 160
VAL_X, VAL_W = 665, 115
TOP0, ROW_H, STEP = 175, 28, 40

UID0, TID0 = 130, 640     # AutoMain uses 100..108 / TextIDs elsewhere


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
        raise SystemExit(f"member {mid}: expected 1 replacement, got {n}")
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
                  lambda m: m.group(1) + f"GenElemInst_{n}" + m.group(2), text, 1)
    text = re.sub(r'(<v n="VisualElementIdentification">)\{[0-9a-fA-F-]+\}(</v>)',
                  lambda m: m.group(1) + GUID_FMT % n + m.group(2), text, 1)
    text = re.sub(r'(<v n="VisualElementOwningObjectGuid">)\{[0-9a-fA-F-]+\}(</v>)',
                  lambda m: m.group(1) + owning + m.group(2), text, 1)
    text = re.sub(r'(<v n="VisualElementId">)\d+(</v>)',
                  lambda m: m.group(1) + str(n) + m.group(2), text, 1)
    return text


def merge_typelist(dst_text, donor_text):
    o = dst_text.index("      <TypeList>")
    c = dst_text.index("      </TypeList>", o)
    body = dst_text[o:c]
    src = {}
    for m in re.finditer(r'<Type n="([^"]+)">([^<]*)</Type>', donor_text):
        src.setdefault(m.group(1), m.group(2))
    add = [f'        <Type n="{n}">{v}</Type>\n'
           for n, v in src.items() if f'<Type n="{n}">' not in body]
    if add:
        print(f"  TypeList: added {len(add)} type(s): "
              + ", ".join(re.search(r'n="([^"]+)"', a).group(1) for a in add))
    return dst_text[:c] + "".join(add) + dst_text[c:]


def main():
    text = DST.read_text(encoding="utf-8")
    if "stCfg.tDwellPushMs" in text:
        print("timers already present - nothing to do.")
        return 0

    owning = re.search(r'<Visu Name="AutoMain" Id="(\{[0-9a-fA-F-]+\})"',
                       text).group(1)
    print(f"AutoMain owning GUID {owning}")

    donor_lines = DONOR.read_text(encoding="utf-8").splitlines(keepends=True)
    tmpl = next(b for s, e, b in blocks(donor_lines)
                if "InputBoxInputAction" in b and "stParams.J_SPEED" in b)
    print("cloned the J_SPEED numeric field from Robot.TcVIS as the template")

    lines = text.splitlines(keepends=True)
    label_src = next(b for s, e, b in blocks(lines)
                     if '"VisuFbElemSimple"' in b)

    uid, tid, texts, out = UID0, TID0, [], []
    for i, name in enumerate(TIMERS):
        top = TOP0 + i * STEP

        lbl = geom(label_src, LBL_X, top, LBL_W, ROW_H)
        lbl = set_member(lbl, M_TEXT, f'"{name}"')
        lbl = set_member(lbl, M_COUNTER, f'"{tid}"')
        texts.append((tid, name)); tid += 1
        out.append(identity(lbl, uid, owning)); uid += 1

        fld = geom(tmpl, VAL_X, top, VAL_W, ROW_H)
        fld = set_member(fld, M_TEXTVAR, f'"stCfg.{name}"')
        fld = set_member(fld, M_COUNTER, '"604"')      # shared "%d" text
        # Clear the robot ranges inherited from the template.
        for tag in ("InputBoxMin", "InputBoxMax"):
            fld = re.sub(r'(<v n="' + tag + r'">)"[^"]*"(</v>)',
                         lambda m: m.group(1) + '""' + m.group(2), fld, count=1)
        out.append(identity(fld, uid, owning)); uid += 1
        print(f"  {name:<24} y={top}")

    last = max(e for s, e, b in blocks(lines))
    result = "".join(lines[:last + 1]) + "".join(out) + "".join(lines[last + 1:])
    result = merge_typelist(result, DONOR.read_text(encoding="utf-8"))
    result = re.sub(r'(<v n="UniqueIdGenerator">")\d+("</v>)',
                    lambda m: m.group(1) + str(uid + 10) + m.group(2), result, 1)
    result = re.sub(r'(<v n="LastUsedIdForIdentifier">)\d+(</v>)',
                    lambda m: m.group(1) + str(uid + 10) + m.group(2), result, 1)
    DST.write_text(result, encoding="utf-8")
    print(f"\nwrote {DST.name}: +{len(out)} elements (5 labels + 5 fields)")

    gtl = GTL.read_text(encoding="utf-8")
    anchor = '            <o>\n              <v n="TextID">"550"</v>'
    entries = "".join(
        '            <o>\n'
        f'              <v n="TextID">"{t}"</v>\n'
        f'              <v n="TextDefault">"{d}"</v>\n'
        '              <l n="LanguageTexts" t="ArrayList" />\n'
        '            </o>\n'
        for t, d in texts if f'<v n="TextID">"{t}"</v>' not in gtl)
    if entries and anchor in gtl:
        GTL.write_text(gtl.replace(anchor, entries + anchor, 1), encoding="utf-8")
        print(f"registered {len(texts)} TextID(s) in GlobalTextList")
    return 0


if __name__ == "__main__":
    sys.exit(main())
