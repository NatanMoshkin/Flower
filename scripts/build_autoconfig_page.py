"""Split AutoMain into an operator page + a standalone AutoConfig page.

TODO #1. AutoMain keeps what an operator uses while the machine runs -- step and
error text, ENABLE AUTO / START / STOP / RESET, and the Auto Mode checkbox -- and
every ``stCfg`` tuning control moves to a new ``AutoConfig`` page reached from
Main.

Why the split is worth doing: AutoMain is embedded as a frame in Main, so those
seven timers and two bench flags were on the *home screen*, where an operator
running bulbs has no reason to see them and every reason to mis-tap one.

Three things about this that are easy to get wrong:

  * **The bindings must change form.** AutoMain is frame-embedded and declares
    ``stCfg : ST_HmiMasterAutoCfg`` as an interface, so its controls bind to
    ``stCfg.tDwellPushMs``. AutoConfig is *navigated to*, and a navigated page
    receives no interface parameters -- so every moved control is retargeted to
    the absolute path ``GVL_HmiPersistent.stMasterAutoCfg.*``. Left relative they
    would bind to nothing.

  * **The Auto Mode checkbox does NOT move**, even though it looks like config.
    It stopped being part of ``stCfg`` on 2026-08-06 (it is now
    ``GVL_HMI.bAutoMode``, volatile, TRUE at boot) and it is a machine *mode*,
    not a tuning value -- an operator switching to Manual needs it on the screen
    they are already looking at.

  * **Page name.** ``AutoConfig`` is a legal, non-reserved IEC identifier. The
    compiler generates an FB and an ``AutoConfig__inp__vis`` type from it, so a
    name colliding with a standard function (``Log``, ``Min``, ``Left``, ...)
    fails the build at line 1 with a message that says nothing about page names.

Clones only: every element on the new page is a block moved verbatim from
AutoMain, or -- for the Back button, which needs a ``ChangeVisuInputAction`` that
AutoMain has no instance of -- one block imported from Main. Nothing is authored.

Run:  python scripts/build_autoconfig_page.py
Then: python scripts/fix_visu_object_guids.py AutoConfig   # MANDATORY
      python scripts/validate_visu.py
      python scripts/validate_automain.py
...and open both pages in TcXaeShell and rebuild. A render check catches a
dropped element; only a build catches a duplicated generated-object GUID.

ONE-WAY MIGRATION, not an idempotent builder. It reads the stCfg controls OUT
of AutoMain, and finish_autoconfig_page.py then deletes them from AutoMain --
so once both have run, the source elements no longer exist and this script
CANNOT rebuild the page. It bails out early if AutoConfig.TcVIS is present,
which is the safe behaviour; do not "fix" that by deleting the page first.
To rebuild from scratch, revert both pages to a commit before the split.
(Learned the hard way 2026-08-06: deleting AutoConfig to re-test the build
left nothing to rebuild from, since AutoMain was already stripped.)
"""

from __future__ import annotations

import pathlib
import re
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1] / (
    "Panel_PLC_HMI/167_01_Saad_PLC/167_01_Saad_PLC/PLC1")
VISU = ROOT / "VISU"
GTL = ROOT / "GlobalTextList.TcGTLO"

SRC, NEW = "AutoMain", "AutoConfig"

M_LEFT, M_TOP = "1649127785L", "357335551L"
M_WIDTH, M_HEIGHT = "2422045748L", "2134141914L"
M_CX, M_CY = "550940142L", "1473355128L"
M_TEXT, M_COUNTER = "390574330L", "823443203L"
M_BOOLVAR, M_TAP, M_TEXTVAR = "743958181L", "1186196937L", "2477733581L"

INDENT_O, INDENT_C = "              <o>", "              </o>"

CFG_ROOT = "GVL_HmiPersistent.stMasterAutoCfg"

# Rows on the new page, in the order the cycle uses them. The key is the stCfg
# field, which is how each control is identified -- the seven numeric fields all
# carry the label "%d", so geometry and binding are the only reliable handles.
ROWS = [
    "tDwellPushMs",
    "tPushRetractedDwellMs",
    "tSepRetractedDwellMs",
    "tStepTimeoutMs",
    "tPlateWaitTimeoutMs",
    "tPbStopHoldMs",
    "tPbStartHoldMs",
]
ROW_Y0, ROW_DY = 70, 40
LABEL_X, LABEL_W = 20, 260
FIELD_X, FIELD_W = 290, 115
CHK_X, CHK_Y0, CHK_DY = 20, 365, 40
BACK_X, BACK_Y, BACK_W, BACK_H = 600, 70, 150, 44
BACK_ID, BACK_COUNTER = 200, "1200"


# --------------------------------------------------------------------------- #
def set_member(text, member_id, value, required=True):
    pat = re.compile(
        r'(<v n="Id">' + re.escape(member_id) + r'</v>\s*\n\s*<v n="Value">)(.*?)(</v>)',
        re.DOTALL)
    out, n = pat.subn(lambda m: m.group(1) + value + m.group(3), text, count=1)
    if n != 1:
        if not required:
            return text
        raise SystemExit(f"member {member_id}: expected 1 replacement, got {n}")
    return out


def get_member(text, member_id):
    m = re.search(r'<v n="Id">' + re.escape(member_id) +
                  r'</v>\s*\n\s*<v n="Value">(.*?)</v>', text, re.DOTALL)
    return m.group(1).strip('"') if m else None


def elements(text):
    """(start, end, body, type) for every typed visual element, in file order."""
    lines = text.splitlines(keepends=True)
    out = []
    for i, line in enumerate(lines):
        if "VisualElementTypeName" in line and '"Visu' in line:
            s = i
            while lines[s].rstrip("\r\n") != INDENT_O:
                s -= 1
            e = i
            while lines[e].rstrip("\r\n") != INDENT_C:
                e += 1
            ty = re.search(r'VisualElementTypeName">"(.*?)"', line).group(1)
            out.append((s, e, "".join(lines[s:e + 1]), ty))
    return lines, out


def binding(body):
    """Whichever bound-variable member this element carries, if any."""
    for mid in (M_BOOLVAR, M_TAP, M_TEXTVAR):
        v = get_member(body, mid)
        if v:
            return v
    return None


def describe(body, ty):
    return (f"{ty:20s} x={get_member(body, M_LEFT):>4} y={get_member(body, M_TOP):>4} "
            f"{str(get_member(body, M_TEXT))[:24]:26s} -> {binding(body)}")


def drop(lines, spans):
    """Remove element spans, LAST FIRST so earlier indices stay valid."""
    for s, e in sorted(spans, reverse=True):
        del lines[s:e + 1]
    return lines


def gtl_register(counter, label):
    gtl = GTL.read_text(encoding="utf-8")
    if f'<v n="TextID">"{counter}"</v>' in gtl:
        pat = re.compile(r'(<v n="TextID">"' + re.escape(counter) +
                         r'"</v>\s*\n\s*<v n="TextDefault">")(.*?)(")')
        cur = pat.search(gtl)
        if cur and cur.group(2) != label:
            GTL.write_text(pat.sub(lambda m: m.group(1) + label + m.group(3), gtl, 1),
                           encoding="utf-8")
            print(f"    GlobalTextList: {counter} {cur.group(2)!r} -> {label!r}")
        return
    anchor = '            <o>\n              <v n="TextID">"550"</v>'
    if anchor not in gtl:
        print("    WARNING: GlobalTextList anchor missing; XAE will add it")
        return
    entry = ('            <o>\n'
             f'              <v n="TextID">"{counter}"</v>\n'
             f'              <v n="TextDefault">"{label}"</v>\n'
             '              <l n="LanguageTexts" t="ArrayList" />\n'
             '            </o>\n')
    GTL.write_text(gtl.replace(anchor, entry + anchor, 1), encoding="utf-8")
    print(f"    GlobalTextList: registered {counter} = {label!r}")


def make_standalone(text):
    """Strip the cloned interface and set the panel's resolution.

    THIS IS NOT OPTIONAL, and retargeting the bindings is not a substitute. A
    page that declares VAR_IN_OUT parameters is a REFERENCE -- meant to be
    embedded in a frame, which is how a caller supplies them. It cannot be
    navigated to at all, because a ChangeVisu has nothing to pass. Cloning
    AutoMain brings its two declarations along, and the result builds,
    validates and renders perfectly while being unreachable. Found on the
    panel 2026-08-06, after a clean build and activate.

    Target shape is Robot.TcVIS's, which is a working standalone page:
    VAR_IN_OUT / <tab> / END_VAR.

    Size too: a page cloned from a frame-embedded one inherits the FRAME's
    designer size (700x400 here), not the panel's 800x480.
    """
    # One <o> block per interface line, matched whole so a removal cannot
    # leave half an element behind.
    block = (r'[ \t]*<o>\s*<v n="Id">\d+L</v>\s*<n n="Tag" />\s*'
             r'<v n="Text">"\t[A-Za-z_]\w*[^"]*:[^"]*"</v>\s*</o>\r?\n')
    decls = re.findall(block, text)
    if not decls:
        print("  interface: already standalone")
    else:
        # Keep the first block, blanked to a bare tab (Robot's shape); drop
        # the rest, so the list is never left completely empty.
        first = decls[0]
        blank = re.sub(r'(<v n="Text">")\t[^"]*(")',
                       lambda m: m.group(1) + "\t" + m.group(2), first)
        text = text.replace(first, blank, 1)
        for d in decls[1:]:
            text = text.replace(d, "", 1)
        print(f"  interface: removed {len(decls)} declaration(s) -> "
              f"VAR_IN_OUT / <tab> / END_VAR")
    for axis, want in (("X", 800), ("Y", 480)):
        m = re.search(r'<v n="Size' + axis + r'">(\d+)</v>', text)
        if m and int(m.group(1)) != want:
            text = text.replace(m.group(0), f'<v n="Size{axis}">{want}</v>', 1)
            print(f"  Size{axis}: {m.group(1)} -> {want}")
    return text

# --------------------------------------------------------------------------- #
def classify(text):
    """Split AutoMain's elements into (config, keep).

    Config = anything bound to a stCfg field, plus the caption sitting to its
    left. Captions carry no binding, so they are matched by row geometry: the
    tuning column starts at x=500 and nothing else on the page does.
    """
    _lines, els = elements(text)
    cfg, keep = [], []
    for s, e, body, ty in els:
        bind = binding(body) or ""
        x = int(get_member(body, M_LEFT))
        is_cfg_bound = bind.startswith("stCfg.")
        is_caption = ty == "VisuFbElemSimple" and x >= 500
        # The Auto Mode checkbox binds GVL_HMI.bAutoMode, not stCfg -- it stays.
        (cfg if (is_cfg_bound or is_caption) else keep).append((s, e, body, ty))
    return cfg, keep


def main() -> int:
    src_path, new_path = VISU / f"{SRC}.TcVIS", VISU / f"{NEW}.TcVIS"
    src = src_path.read_text(encoding="utf-8")

    if new_path.exists():
        print(f"{NEW}.TcVIS already exists - nothing to do.")
        print("  (delete it and re-run to rebuild from scratch)")
        return 0

    cfg, keep = classify(src)
    print(f"{SRC}: {len(cfg) + len(keep)} elements -> "
          f"{len(cfg)} to {NEW}, {len(keep)} stay")
    print(f"\n  MOVING to {NEW}:")
    for _s, _e, b, t in cfg:
        print("   ", describe(b, t))
    print(f"\n  STAYING on {SRC}:")
    for _s, _e, b, t in keep:
        print("   ", describe(b, t))

    expect_cfg = 2 * len(ROWS) + 2          # caption+field per row, +2 checkboxes
    if len(cfg) != expect_cfg:
        raise SystemExit(
            f"expected {expect_cfg} config elements ({len(ROWS)} rows x2 + 2 "
            f"checkboxes), classified {len(cfg)} - refusing to guess")

    # ---------------------------------------------------------------- the clone
    shutil.copyfile(src_path, new_path)
    text = new_path.read_text(encoding="utf-8")
    text = text.replace(f'<Visu Name="{SRC}"', f'<Visu Name="{NEW}"', 1)
    text = make_standalone(text)
    if f'"{SRC}"' in text.split("<VisualElementList>")[0]:
        print(f"\n  note: '{SRC}' still appears in the clone's header region")

    # Drop everything that is NOT config, except the title -- which is reused as
    # this page's own heading rather than cloned, so it keeps its counter.
    lines, els = elements(text)
    title_span = None
    drop_spans = []
    for s, e, body, ty in els:
        bind = binding(body) or ""
        x = int(get_member(body, M_LEFT))
        if bind.startswith("stCfg.") or (ty == "VisuFbElemSimple" and x >= 500):
            continue
        if ty == "VisuFbElemSimple" and get_member(body, M_TEXT) == "Auto Main":
            title_span = (s, e, body)
            continue
        drop_spans.append((s, e))
    if title_span is None:
        raise SystemExit("no 'Auto Main' title element to reuse")
    print(f"\n  dropping {len(drop_spans)} non-config element(s) from {NEW}")
    lines = drop(lines, drop_spans)
    text = "".join(lines)

    # retitle, retarget and re-lay-out what remains
    lines, els = elements(text)
    by_field = {}
    captions, checkboxes = [], []
    for s, e, body, ty in els:
        bind = binding(body) or ""
        if bind.startswith("stCfg."):
            field = bind.split(".", 1)[1]
            if ty == "VisuFbCheckbox":
                checkboxes.append((s, e, body, field))
            else:
                by_field[field] = (s, e, body)
        elif ty == "VisuFbElemSimple" and get_member(body, M_TEXT) == "Auto Main":
            pass
        elif ty == "VisuFbElemSimple":
            captions.append((s, e, body))

    missing = [f for f in ROWS if f not in by_field]
    if missing:
        raise SystemExit(f"no control found for: {missing}")
    if len(captions) != len(ROWS):
        raise SystemExit(f"expected {len(ROWS)} captions, found {len(captions)}")

    # Captions are matched to rows by their original y, which is the only thing
    # that ties a caption to the field beside it.
    captions.sort(key=lambda t: int(get_member(t[2], M_TOP)))
    field_order = sorted(by_field.items(), key=lambda kv: int(get_member(kv[1][2], M_TOP)))

    new_bodies = {}          # span -> rewritten body
    for i, ((field, (fs, fe, fbody)), (cs, ce, cbody)) in enumerate(
            zip(field_order, captions)):
        y = ROW_Y0 + i * ROW_DY
        c = set_member(cbody, M_LEFT, str(LABEL_X))
        c = set_member(c, M_TOP, str(y))
        c = set_member(c, M_WIDTH, str(LABEL_W))
        c = set_member(c, M_CX, str(LABEL_X + LABEL_W // 2), required=False)
        c = set_member(c, M_CY, str(y + int(get_member(cbody, M_HEIGHT)) // 2),
                       required=False)
        new_bodies[(cs, ce)] = c

        f = set_member(fbody, M_LEFT, str(FIELD_X))
        f = set_member(f, M_TOP, str(y))
        f = set_member(f, M_WIDTH, str(FIELD_W))
        f = set_member(f, M_CX, str(FIELD_X + FIELD_W // 2), required=False)
        f = set_member(f, M_CY, str(y + int(get_member(fbody, M_HEIGHT)) // 2),
                       required=False)
        f = set_member(f, M_TEXTVAR, f'"{CFG_ROOT}.{field}"')
        new_bodies[(fs, fe)] = f
        print(f"    row {i}: y={y:<4} {field:24s} -> {CFG_ROOT}.{field}")

    checkboxes.sort(key=lambda t: int(get_member(t[2], M_TOP)))
    for i, (s, e, body, field) in enumerate(checkboxes):
        y = CHK_Y0 + i * CHK_DY
        b = set_member(body, M_LEFT, str(CHK_X))
        b = set_member(b, M_TOP, str(y))
        b = set_member(b, M_BOOLVAR, f'"{CFG_ROOT}.{field}"')
        new_bodies[(s, e)] = b
        print(f"    chk {i}: y={y:<4} {field:24s} -> {CFG_ROOT}.{field}")

    ts, te, tbody = title_span
    t = set_member(tbody, M_TEXT, '"Auto Config"')
    new_bodies[(ts, te)] = t
    gtl_register(get_member(tbody, M_COUNTER), "Auto Config")

    for (s, e), body in sorted(new_bodies.items(), reverse=True):
        lines[s:e + 1] = [body]
    text = "".join(lines)
    new_path.write_text(text, encoding="utf-8")
    print(f"\n  wrote {NEW}.TcVIS ({len(elements(text)[1])} elements)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
