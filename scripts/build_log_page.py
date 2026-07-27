"""Create Logs.TcVIS -- the 20 newest log entries -- and its nav button on Main.

`GVL_Log.aRecent[0..19]` already exists for exactly this purpose: F_LogEvent
shifts the slots down on every accepted call, so aRecent[0] is the newest and
the page can bind the array in display order with no PLC-side work.

Layout (the panel is 800x480):

    Main | Log | [x] Enabled  [x] Debug   Writes [ nWriteIdx ]
    Sev   Time      Message
    ...20 rows of aRecent[i], newest first...

Severity binds to `aRecent[i].sSevText`, NOT to the eSev enum. Binding the
enum renders 0..3 -- {attribute 'to_string'} makes TO_STRING() available in
ST, it does not make the classic VISU text output resolve an enum. F_LogEvent
fills sSevText via TO_STRING(eSev), the same mirror pattern ST_HmiMasterAuto
uses for sStepText. (Verified the wrong way round on the panel first, twice.)

Built by cloning proven blocks, never authoring them:
  * page skeleton + "Main" nav button  <- PistonsManual.TcVIS
  * labels (VisuFbElemSimple)          <- AutoMain title
  * value fields (VisuFbElemTextfield) <- AutoMain step-text field
  * checkboxes (VisuFbCheckbox)        <- AutoMain "Continuous"
  * Main's new nav button              <- Main's own "Robot" nav button

Two identity layers get re-issued, both of which have broken this build
before:
  1. every element's VisualElementIdentification -> namespace 1005, because
     the skeleton's kept nav button would otherwise duplicate
     PistonsManual's;
  2. the ~60 generated-object GUIDs (VisuRegDesc / InputsPou / methods /
     generated GVLs), via fix_visu_object_guids -- copying a page copies
     these too, and duplicating InputsPou.FbGuid fails the build against
     the ORIGINAL page.

Idempotent: refuses to run twice.

Run:  python scripts/build_log_page.py
Then: python scripts/validate_visu.py
      ...and open Logs + Main in TcXaeShell and rebuild.
"""

from __future__ import annotations

import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import fix_visu_object_guids as objguid          # noqa: E402

# A page name becomes an IEC identifier (the compiler generates an FB and a
# <Page>__inp__vis type from it), so it must not collide with a standard
# function. "Log" fails with `Identifier expected instead of "Log"` because
# LOG is an IEC 61131-3 standard function, alongside LN / EXP / ABS / SQRT /
# SEL / MUX / LEN / LEFT / MID / FIND. "Logs" is safe and matches the
# vocabulary GVL_Log's own comments already use ("HMI Logs page").
# The visible label stays "Log" -- display text is not an identifier.
PAGE, LABEL = "Logs", "Log"

ROOT = pathlib.Path(__file__).resolve().parents[1] / (
    "Panel_PLC_HMI/167_01_Saad_PLC/167_01_Saad_PLC/PLC1")
VISU = ROOT / "VISU"
SKEL, DONOR = VISU / "PistonsManual.TcVIS", VISU / "AutoMain.TcVIS"
MAIN, DST = VISU / "Main.TcVIS", VISU / f"{PAGE}.TcVIS"
GTL = ROOT / "GlobalTextList.TcGTLO"
PLCPROJ = next(ROOT.glob("*.plcproj"))

PAGE_GUID = "{a1b2c3d4-0e5f-4a6b-9c7d-000000000103}"
NS, MAIN_NS = "1005", "1003"          # 1001-1004 already taken

M_LEFT, M_TOP = "1649127785L", "357335551L"
M_WIDTH, M_HEIGHT = "2422045748L", "2134141914L"
M_CX, M_CY = "550940142L", "1473355128L"
M_TEXT, M_COUNTER = "390574330L", "823443203L"
M_TEXTVAR, M_BOOL = "2477733581L", "743958181L"

INDENT_O, INDENT_C = "              <o>", "              </o>"

L = "GVL_Log."
ROWS, ROW_TOP0, ROW_STEP, ROW_H = 20, 66, 20, 19
COLS = [("Sev", 20, 60, "%s", "sSevText"),
        ("Time", 84, 90, "%s", "sTime"),
        ("Message", 178, 602, "%s", "sMsg")]
HDR_TOP, HDR_H = 44, 20

NAV_ON_MAIN = (63, 417, 177, 44)      # next free slot; siblings at 243/423/603

texts: list[tuple[int, str]] = []


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


def block(lines, type_name, predicate=None):
    for s, e, body in blocks(lines, type_name):
        if predicate is None or predicate(body):
            return s, e, body
    raise SystemExit(f"no matching {type_name} block found")


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


def identity(t, uid, ns, owning):
    t = re.sub(r'(<v n="VisualElementIdentifier">")GenElemInst_\d+("</v>)',
               lambda m: m.group(1) + f"GenElemInst_{uid}" + m.group(2), t, 1)
    t = re.sub(r'(<v n="VisualElementIdentification">)\{[0-9a-fA-F-]+\}(</v>)',
               lambda m: m.group(1) +
               "{a1b2c3d4-0e5f-4a6b-9c7d-%s%08d}" % (ns, uid) + m.group(2), t, 1)
    t = re.sub(r'(<v n="VisualElementOwningObjectGuid">)\{[0-9a-fA-F-]+\}(</v>)',
               lambda m: m.group(1) + owning + m.group(2), t, 1)
    t = re.sub(r'(<v n="VisualElementId">)\d+(</v>)',
               lambda m: m.group(1) + str(uid) + m.group(2), t, 1)
    return t


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
        print(f"  TypeList: +{len(add)} type(s): "
              + ", ".join(re.search(r'n="([^"]+)"', a).group(1) for a in add))
    return dst_text[:c] + "".join(add) + dst_text[c:]


def build_page():
    skel = SKEL.read_text(encoding="utf-8")
    old = re.search(r'<Visu Name="PistonsManual" Id="(\{[0-9a-fA-F-]+\})"',
                    skel).group(1)
    skel = skel.replace('<Visu Name="PistonsManual"',
                        f'<Visu Name="{PAGE}"', 1)
    skel = skel.replace(old, PAGE_GUID)

    lines = skel.splitlines(keepends=True)
    while True:                                   # strip the 6 Piston frames
        try:
            s, e, _ = block(lines, "VisuFbFrame")
        except SystemExit:
            break
        del lines[s:e + 1]
    kept = sum("VisualElementTypeName" in l for l in lines)
    if kept != 1:
        raise SystemExit(f"expected only the Main nav button left, got {kept}")

    donor = DONOR.read_text(encoding="utf-8").splitlines(keepends=True)
    SIMPLE = block(donor, "VisuFbElemSimple")[2]
    # Must be a DISPLAY field: AutoMain also holds 5 editable timer fields
    # carrying an InputBoxInputAction, and log text must not be editable.
    FIELD = block(donor, "VisuFbElemTextfield",
                  lambda b: "InputBoxInputAction" not in b)[2]
    CHECK = block(donor, "VisuFbCheckbox")[2]

    out, uid, tid = [], 300, 1200

    def add(t):
        out.append(identity(t, len(out) + uid, NS, PAGE_GUID))

    def label(text_, x, y, w, h):
        nonlocal tid
        t = set_member(geom(SIMPLE, x, y, w, h), M_TEXT, f'"{text_}"')
        t = set_member(t, M_COUNTER, f'"{tid}"')
        texts.append((tid, text_)); tid += 1
        add(t)

    def field(fmt, var, x, y, w, h):
        nonlocal tid
        t = set_member(geom(FIELD, x, y, w, h), M_TEXT, f'"{fmt}"')
        t = set_member(t, M_TEXTVAR, f'"{var}"')
        t = set_member(t, M_COUNTER, f'"{tid}"')
        texts.append((tid, fmt)); tid += 1
        add(t)

    def check(text_, var, x, y, w, h):
        nonlocal tid
        t = set_member(geom(CHECK, x, y, w, h), M_TEXT, f'"{text_}"')
        t = set_member(t, M_BOOL, f'"{var}"')
        t = set_member(t, M_COUNTER, f'"{tid}"')
        texts.append((tid, text_)); tid += 1
        add(t)

    label(LABEL, 140, 6, 80, 32)
    check("Enabled", L + "bLogEnabled", 240, 8, 120, 28)
    check("Debug", L + "bDebugMode", 370, 8, 110, 28)
    label("Writes", 490, 8, 80, 28)
    field("%d", L + "nWriteIdx", 575, 8, 110, 28)

    for name, x, w, _fmt, _member in COLS:
        label(name, x, HDR_TOP, w, HDR_H)

    for i in range(ROWS):
        y = ROW_TOP0 + i * ROW_STEP
        for _name, x, w, fmt, member in COLS:
            field(fmt, f"{L}aRecent[{i}].{member}", x, y, w, ROW_H)
    print(f"  {ROWS} rows x {len(COLS)} columns + "
          f"{len(out) - ROWS * len(COLS)} chrome element(s)")

    last_end = block(lines, "VisuFbElemSimple")[1]      # the kept nav button
    text = ("".join(lines[:last_end + 1]) + "".join(out)
            + "".join(lines[last_end + 1:]))
    text = merge_typelist(text, DONOR.read_text(encoding="utf-8"))

    # Reposition the inherited nav button and re-GUID it: it still carries
    # PistonsManual's element GUID, which must not exist in two files.
    nav = block(text.splitlines(keepends=True), "VisuFbElemSimple")[2]
    fixed = identity(geom(nav, 20, 6, 110, 32), 299, NS, PAGE_GUID)
    text = text.replace(nav, fixed, 1)

    n = uid + len(out) + 10
    text = re.sub(r'(<v n="UniqueIdGenerator">")\d+("</v>)',
                  lambda m: m.group(1) + str(n) + m.group(2), text, 1)
    text = re.sub(r'(<v n="LastUsedIdForIdentifier">)\d+(</v>)',
                  lambda m: m.group(1) + str(n) + m.group(2), text, 1)
    DST.write_text(text, encoding="utf-8")
    print(f"wrote {DST.name}: {len(out) + 1} elements")


def add_main_nav():
    text = MAIN.read_text(encoding="utf-8")
    if f'<v n="Assign33">"{PAGE}"</v>' in text:
        print(f"Main already has a {PAGE} nav button.")
        return
    owning = re.search(r'<Visu Name="Main" Id="(\{[0-9a-fA-F-]+\})"',
                       text).group(1)
    lines = text.splitlines(keepends=True)
    s, e, src = block(lines, "VisuFbElemSimple",
                      lambda b: '"Robot"' in b and "Assign33" in b)

    tid = 1199
    t = geom(src, *NAV_ON_MAIN)
    t = set_member(t, M_TEXT, f'"{LABEL}"')
    t = set_member(t, M_COUNTER, f'"{tid}"')
    texts.append((tid, LABEL))
    t, n = re.subn(r'(<v n="Assign33">")[^"]+("</v>)',
                   lambda m: m.group(1) + PAGE + m.group(2), t, count=1)
    if n != 1:
        raise SystemExit("nav target not rewritten - the button would still "
                         "navigate to Robot")
    t = identity(t, 40, MAIN_NS, owning)

    MAIN.write_text("".join(lines[:e + 1]) + t + "".join(lines[e + 1:]),
                    encoding="utf-8")
    print(f"Main: added 'Log' nav button at {NAV_ON_MAIN}")


def register_plcproj():
    proj = PLCPROJ.read_text(encoding="utf-8")
    if f"{PAGE}.TcVIS" in proj:
        return
    anchor = ('    <Compile Include="VISU\\PistonsManual.TcVIS">\n'
              '      <SubType>Code</SubType>\n'
              '      <DependentUpon>VISU\\VisualizationManager.TcVMO'
              '</DependentUpon>\n    </Compile>\n')
    if anchor not in proj:
        raise SystemExit("plcproj anchor not found")
    new = anchor.replace("PistonsManual.TcVIS", f"{PAGE}.TcVIS")
    PLCPROJ.write_text(proj.replace(anchor, anchor + new, 1), encoding="utf-8")
    print(f"registered {PAGE}.TcVIS in {PLCPROJ.name}")


def register_texts():
    gtl = GTL.read_text(encoding="utf-8")
    anchor = '            <o>\n              <v n="TextID">"550"</v>'
    if anchor not in gtl:
        print("  WARNING: GlobalTextList anchor missing; XAE will fill these in")
        return
    entries = "".join(
        '            <o>\n'
        f'              <v n="TextID">"{tid}"</v>\n'
        f'              <v n="TextDefault">"{d}"</v>\n'
        '              <l n="LanguageTexts" t="ArrayList" />\n'
        '            </o>\n'
        for tid, d in texts if f'<v n="TextID">"{tid}"</v>' not in gtl)
    if entries:
        GTL.write_text(gtl.replace(anchor, entries + anchor, 1), encoding="utf-8")
        print(f"registered {len(texts)} TextID(s) in GlobalTextList")


def main():
    if DST.exists():
        print(f"{DST.name} already exists - nothing to do.")
        return 0
    build_page()
    add_main_nav()
    register_plcproj()
    register_texts()
    # Second identity layer: the skeleton copy also duplicated PistonsManual's
    # generated-object GUIDs. Nothing else re-issues these.
    print()
    objguid.main(["", PAGE])
    return 0


if __name__ == "__main__":
    sys.exit(main())
