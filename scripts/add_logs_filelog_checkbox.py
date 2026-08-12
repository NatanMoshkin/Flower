"""Add a 'File log' enable checkbox to PLC1/VISU/Logs.TcVIS.

    python scripts/add_logs_filelog_checkbox.py

Binds GVL_HmiPersistent.stLogFileCfg.bEnabled -- the durable CSV log's master
switch (Phase 1 of docs/plans/log-csv-file.md). Operator-requested: turning file
logging on and off has to be possible from the panel itself, not only over ADS.

CLONES the page's own 'Debug' checkbox and rewrites leaves only. Nothing here is
authored: this format is a numeric-ID object graph with no schema, a valid XML
parse proves nothing, and the two ways it breaks are both silent or point at an
innocent file. See the TwinCAT_Classic_VISU_Editing skill.

Identity values, each verified absent before use rather than assumed -- the first
three obvious guesses were ALL taken:

    TextID           1304   (the whole 1200-1267 Logs band is full; AutoConfig
                             took 1302/1303 on 2026-08-06)
    VisualElementId   368   (the page already uses 299..367)
    Identifier        GenElemInst_368
    GUID             {a1b2c3d4-0e5f-4a6b-9c7d-100500000368}
                             -- the page's own -1005 namespace, so it cannot
                             collide with another page's counter

GEOMETRY. The top row was measured, not guessed:

    x  20..130  Main nav        x 240..360  'Enabled'  (bLogEnabled)
    x 140..220  'Log' title     x 370..480  'Debug'    (bDebugMode)
    x 490..570  'Writes'        x 575..685  nWriteIdx
    x 685..800  <- 115 px free, which is where this goes

Idempotent: re-running is a no-op once the binding is present.
"""
import io
import os
import re
import sys

VISU = os.path.join("Panel_PLC_HMI", "167_01_Saad_PLC", "167_01_Saad_PLC",
                    "PLC1", "VISU", "Logs.TcVIS")
GTL = os.path.join("Panel_PLC_HMI", "167_01_Saad_PLC", "167_01_Saad_PLC",
                   "PLC1", "GlobalTextList.TcGTLO")

DONOR_BOOL = "GVL_Log.bDebugMode"          # the checkbox we clone
NEW_BOOL = "GVL_HmiPersistent.stLogFileCfg.bEnabled"
NEW_LABEL = "File log"
NEW_TEXTID = "1304"
NEW_ELEMID = "368"
NEW_GUID = "{a1b2c3d4-0e5f-4a6b-9c7d-100500000368}"
LEFT, TOP, WIDTH, HEIGHT = 688, 8, 110, 28

M_LEFT, M_TOP, M_W, M_H = "1649127785L", "357335551L", "2422045748L", "2134141914L"
M_LABEL, M_TEXTID, M_BOOL = "390574330L", "823443203L", "743958181L"
M_CX, M_CY = "550940142L", "1473355128L"

INDENT_O, INDENT_C = "              <o>", "              </o>"


def die(msg):
    sys.exit(f"ERROR: {msg}")


def find_block(lines, bound_bool):
    """Locate the <o>..</o> span of the checkbox bound to bound_bool.

    Derived from a BLOCK SCAN, never from an indentation search: a deeper-indented
    '</o>' contains the shallower one as a substring, so a text search can splice
    the new element inside another one -- still valid XML, silently dropped.
    """
    for i, line in enumerate(lines):
        if '"VisuFbCheckbox"' in line and "VisualElementTypeName" in line:
            s = i
            while lines[s].rstrip("\r\n") != INDENT_O:
                s -= 1
            e = i
            while lines[e].rstrip("\r\n") != INDENT_C:
                e += 1
            body = "".join(lines[s:e + 1])
            if f'"{bound_bool}"' in body:
                return s, e, body
    die(f"no VisuFbCheckbox bound to {bound_bool}")


def set_member(text, member_id, value, what):
    pat = re.compile(r'(<v n="Id">' + re.escape(member_id) + r'</v>\s*\n\s*<v n="Value">)(.*?)(</v>)',
                     re.DOTALL)
    out, n = pat.subn(lambda m: m.group(1) + value + m.group(3), text, count=1)
    # A silent zero-replacement would leave the clone pointing at the DONOR's
    # variable -- far worse than a crash, because it looks fine and writes to the
    # wrong symbol.
    if n != 1:
        die(f"{what} (member {member_id}): expected 1 replacement, got {n}")
    return out


def main():
    if not os.path.exists(VISU):
        die(f"{VISU} not found -- run from the repo root")

    text = io.open(VISU, encoding="utf-8", newline="").read()
    if NEW_BOOL in text:
        print("already present -- nothing to do")
        return 0

    lines = text.splitlines(keepends=True)
    s, e, donor = find_block(lines, DONOR_BOOL)
    print(f"cloning the {DONOR_BOOL} checkbox at lines {s + 1}-{e + 1}")

    # -- sanity-check the donor before trusting the member ids ---------------- #
    got = {}
    for mid, name in ((M_LEFT, "left"), (M_TOP, "top"), (M_W, "w"), (M_H, "h")):
        m = re.search(r'<v n="Id">' + mid + r'</v>\s*\n\s*<v n="Value">(.*?)</v>', donor, re.S)
        got[name] = int(m.group(1))
    cx = re.search(r'<v n="Id">' + M_CX + r'</v>\s*\n\s*<v n="Value">(.*?)</v>', donor, re.S)
    if cx:
        want = got["left"] + got["w"] // 2
        if int(cx.group(1)) != want:
            die(f"donor centre-x is {cx.group(1)} but left+w/2 is {want} -- "
                "the member-id assumption is wrong, stop and re-read the file")
        print(f"  donor geometry consistent (cx = left + w/2 = {want})")

    for guard, why in (
        (NEW_GUID in text, f"GUID {NEW_GUID} already in this page"),
        (f'"{NEW_ELEMID}"' in text and f'GenElemInst_{NEW_ELEMID}' in text,
         f"VisualElementId {NEW_ELEMID} already used"),
        (f'<v n="Value">"{NEW_TEXTID}"</v>' in text, f"TextID {NEW_TEXTID} already used here"),
    ):
        if guard:
            die(why)

    # -- rewrite leaves + identity ------------------------------------------- #
    new = donor
    new = set_member(new, M_LEFT, str(LEFT), "left")
    new = set_member(new, M_TOP, str(TOP), "top")
    new = set_member(new, M_W, str(WIDTH), "width")
    new = set_member(new, M_H, str(HEIGHT), "height")
    new = set_member(new, M_LABEL, f'"{NEW_LABEL}"', "label")
    new = set_member(new, M_TEXTID, f'"{NEW_TEXTID}"', "TextID")
    new = set_member(new, M_BOOL, f'"{NEW_BOOL}"', "bound BOOL")
    if cx:
        new = set_member(new, M_CX, str(LEFT + WIDTH // 2), "centre x")
        new = set_member(new, M_CY, str(TOP + HEIGHT // 2), "centre y")

    for pat, val, what in (
        (r'(<v n="VisualElementIdentification">)\{[0-9a-fA-F-]+\}', NEW_GUID, "GUID"),
        (r'(<v n="VisualElementId">)\d+', NEW_ELEMID, "VisualElementId"),
        (r'(<v n="VisualElementIdentifier">")GenElemInst_\d+', f"GenElemInst_{NEW_ELEMID}",
         "Identifier"),
    ):
        new, n = re.subn(pat, lambda m: m.group(1) + val, new, count=1)
        if n != 1:
            die(f"{what}: expected 1 replacement, got {n}")

    # The donor is a checkbox, not a nav button, so it carries no
    # ChangeVisuInputAction to strip. Assert that rather than assume it.
    if "ChangeVisuInputAction" in new:
        die("the clone carries a ChangeVisuInputAction -- it would navigate when "
            "touched; strip it before inserting")

    # -- insert as a SIBLING, immediately after the donor's end line ---------- #
    out = "".join(lines[:e + 1]) + new + "".join(lines[e + 1:])
    io.open(VISU, "w", encoding="utf-8", newline="").write(out)
    print(f"  inserted after line {e + 1} as a sibling of the donor")

    # -- GlobalTextList entry for the counter -------------------------------- #
    g = io.open(GTL, encoding="utf-8", newline="").read()
    if f'<v n="TextID">"{NEW_TEXTID}"</v>' in g:
        print(f"  GlobalTextList already has TextID {NEW_TEXTID}")
    else:
        anchor = '<v n="TextID">"1303"</v>'
        if anchor not in g:
            die("cannot find the 1303 entry to anchor the new GlobalTextList entry")
        # \r?\n throughout: these files are CRLF and are read with newline="" so the
        # \r survives. A bare \n in the pattern silently fails to match.
        blk = re.search(r'( *)<o>\r?\n\s*<v n="TextID">"1303"</v>.*?</o>\r?\n', g, re.S)
        if not blk:
            die("cannot read the shape of the 1303 GlobalTextList entry")
        donor_entry = blk.group(0)
        new_entry = (donor_entry
                     .replace('"1303"', f'"{NEW_TEXTID}"')
                     .replace(re.search(r'<v n="TextDefault">"([^"]*)"', donor_entry).group(0),
                              f'<v n="TextDefault">"{NEW_LABEL}"'))
        g = g.replace(donor_entry, donor_entry + new_entry, 1)
        io.open(GTL, "w", encoding="utf-8", newline="").write(g)
        print(f"  GlobalTextList: TextID {NEW_TEXTID} = {NEW_LABEL!r}")

    print("\nNow run scripts/validate_visu.py, then OPEN Logs.TcVIS IN TcXaeShell")
    print("and REBUILD. Both checks are needed and they catch different things:")
    print("rendering catches a structural splice, the build catches a GUID clash.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
