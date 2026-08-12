"""Add a 'Failed connects' readout to PLC1/VISU/Robot.TcVIS.

    python scripts/add_robot_connfails_readout.py

Shows GVL_Robot.stRobot.nConnectFails -- consecutive failed connect attempts in the
current outage, cleared when a connect succeeds. FlowerPyHmi has shown this since
2026-08-10; the panel has not, which is the gap this closes.

WHY THE FIELD EXISTS AT ALL, because it explains why showing it matters:
FB_RobotTcpClient used to log an ERR on every ~3 s re-dial, which filled all 20
slots of GVL_Log.aRecent and made the first CSV 95% one message. The log is now
edge-guarded -- one ERR per outage -- and the count moved into this symbol. So
without a readout the suppression would just be a way of not being told the link
is down.

CLONES TWO existing elements on the same page and rewrites leaves only:

    label  <- the 'Packets Tx' VisuFbElemSimple
    value  <- the VisuFbElemTextfield bound to nPacketsTx

The 'Packets Tx' label is the right donor and 'Main' is NOT: both are
VisuFbElemSimple, but 'Main' carries a ChangeVisuInputAction, so cloning it would
produce a caption that navigates away when touched. Asserted below rather than
assumed.

TEXTIDs -- the asymmetry here is easy to get wrong. TextID 604 is the FORMAT
STRING "%d" and is shared by all 15 numeric fields on this page, so the value clone
REUSES it. Only the label needs a new one (1305; 1304 became 'File log' on the Logs
page). Allocating a fresh TextID for the value would leave a "%d" entry duplicated
in GlobalTextList for no reason.

GEOMETRY, measured rather than guessed. The left status column runs
label x 20 w 145 / value x 170 w 220, rows 28 px tall:

    y  55 Connection   y 160 Last Rx     y 265 Robot cmd
    y  90 Packets Rx   y 195 Last Tx     y 330 buttons (h 44)
    y 125 Packets Tx   y 230 State out   y 385 Robot IP

Robot cmd ends at 293 and the buttons start at 330, so y=298 is the one free
28 px slot in that column. It sits below the other counters rather than beside
Rx/Tx, because inserting at y=125 would mean shifting six rows down -- a much
larger and riskier edit for a cosmetic gain.

Idempotent: re-running is a no-op once the binding is present.
"""
import io
import os
import re
import sys

BASE = os.path.join("Panel_PLC_HMI", "167_01_Saad_PLC", "167_01_Saad_PLC", "PLC1")
VISU = os.path.join(BASE, "VISU", "Robot.TcVIS")
GTL = os.path.join(BASE, "GlobalTextList.TcGTLO")

DONOR_LABEL = '"Packets Tx"'
DONOR_VALUE = "GVL_Robot.stRobot.nPacketsTx"
NEW_BIND = "GVL_Robot.stRobot.nConnectFails"
NEW_LABEL = "Failed connects"
LABEL_TEXTID = "1305"
LABEL_ID, VALUE_ID = "403", "404"
LABEL_GUID = "{a1b2c3d4-0e5f-4a6b-9c7d-100200000403}"
VALUE_GUID = "{a1b2c3d4-0e5f-4a6b-9c7d-100200000404}"
ROW_Y = 298
LABEL_X, LABEL_W = 20, 145
VALUE_X, VALUE_W = 170, 220
ROW_H = 28

M_LEFT, M_TOP, M_W, M_H = "1649127785L", "357335551L", "2422045748L", "2134141914L"
M_LABEL, M_TEXTID, M_DISPVAR = "390574330L", "823443203L", "2477733581L"
M_CX, M_CY = "550940142L", "1473355128L"

INDENT_O, INDENT_C = "              <o>", "              </o>"


def die(msg):
    sys.exit(f"ERROR: {msg}")


def blocks(lines):
    for i, line in enumerate(lines):
        if "VisualElementTypeName" in line:
            s = i
            while lines[s].rstrip("\r\n") != INDENT_O:
                s -= 1
            e = i
            while lines[e].rstrip("\r\n") != INDENT_C:
                e += 1
            yield s, e, "".join(lines[s:e + 1])


def find(lines, needle, must_lack=None):
    hits = [(s, e, b) for s, e, b in blocks(lines) if needle in b]
    if len(hits) != 1:
        die(f"expected exactly 1 block containing {needle}, found {len(hits)}")
    s, e, b = hits[0]
    if must_lack and must_lack in b:
        die(f"donor for {needle} carries {must_lack} -- wrong donor, the clone "
            "would inherit it")
    return s, e, b


def set_member(text, member_id, value, what):
    pat = re.compile(r'(<v n="Id">' + re.escape(member_id) +
                     r'</v>\s*\n\s*<v n="Value">)(.*?)(</v>)', re.DOTALL)
    out, n = pat.subn(lambda m: m.group(1) + value + m.group(3), text, count=1)
    if n != 1:
        die(f"{what} (member {member_id}): expected 1 replacement, got {n}")
    return out


def has(text, member_id):
    return re.search(r'<v n="Id">' + member_id + r'</v>', text) is not None


def reident(text, guid, elem_id, what):
    for pat, val in (
        (r'(<v n="VisualElementIdentification">)\{[0-9a-fA-F-]+\}', guid),
        (r'(<v n="VisualElementId">)\d+', elem_id),
        (r'(<v n="VisualElementIdentifier">")GenElemInst_\d+', f"GenElemInst_{elem_id}"),
    ):
        text, n = re.subn(pat, lambda m: m.group(1) + val, text, count=1)
        if n != 1:
            die(f"{what}: identity replacement expected 1, got {n}")
    return text


def geom(text, x, w, what):
    text = set_member(text, M_LEFT, str(x), f"{what} left")
    text = set_member(text, M_TOP, str(ROW_Y), f"{what} top")
    text = set_member(text, M_W, str(w), f"{what} width")
    text = set_member(text, M_H, str(ROW_H), f"{what} height")
    # Centres exist on some element types and not others. Keep them consistent
    # where present -- a stale centre after a move renders in the wrong place.
    if has(text, M_CX):
        text = set_member(text, M_CX, str(x + w // 2), f"{what} centre x")
        text = set_member(text, M_CY, str(ROW_Y + ROW_H // 2), f"{what} centre y")
    return text


def main():
    if not os.path.exists(VISU):
        die(f"{VISU} not found -- run from the repo root")
    text = io.open(VISU, encoding="utf-8", newline="").read()
    if NEW_BIND in text:
        print("already present -- nothing to do")
        return 0

    for guard, why in ((LABEL_GUID in text, f"{LABEL_GUID} already present"),
                       (VALUE_GUID in text, f"{VALUE_GUID} already present"),
                       (f'<v n="Value">"{LABEL_TEXTID}"</v>' in text,
                        f"TextID {LABEL_TEXTID} already used on this page")):
        if guard:
            die(why)

    lines = text.splitlines(keepends=True)
    ls, le, donor_label = find(lines, DONOR_LABEL, must_lack="ChangeVisuInputAction")
    vs, ve, donor_value = find(lines, DONOR_VALUE)
    print(f"label donor: lines {ls + 1}-{le + 1}  (no nav action, checked)")
    print(f"value donor: lines {vs + 1}-{ve + 1}")

    new_label = geom(donor_label, LABEL_X, LABEL_W, "label")
    new_label = set_member(new_label, M_LABEL, f'"{NEW_LABEL}"', "label text")
    new_label = set_member(new_label, M_TEXTID, f'"{LABEL_TEXTID}"', "label TextID")
    new_label = reident(new_label, LABEL_GUID, LABEL_ID, "label")

    new_value = geom(donor_value, VALUE_X, VALUE_W, "value")
    new_value = set_member(new_value, M_DISPVAR, f'"{NEW_BIND}"', "displayed variable")
    new_value = reident(new_value, VALUE_GUID, VALUE_ID, "value")
    # TextID deliberately NOT touched: 604 is the shared "%d" format string.
    if f'"{M_TEXTID}"' in new_value and '"604"' not in new_value:
        die("the value clone lost its 604 format TextID")

    for blk, name in ((new_label, "label"), (new_value, "value")):
        if "ChangeVisuInputAction" in blk:
            die(f"the {name} clone carries a nav action")
    if DONOR_VALUE in new_value:
        die("the value clone is still bound to nPacketsTx")

    # Insert both after the LAST of the two donor blocks, so they land as
    # siblings of a known-good element. Position from the block scan, never a text
    # search: a deeper-indented '</o>' contains the shallower one as a substring.
    anchor = max(le, ve)
    out = "".join(lines[:anchor + 1]) + new_label + new_value + "".join(lines[anchor + 1:])
    io.open(VISU, "w", encoding="utf-8", newline="").write(out)
    print(f"  inserted both after line {anchor + 1}")

    # GlobalTextList entry for the label only. \r?\n because these files are CRLF
    # and are read with newline="" -- a bare \n silently fails to match.
    g = io.open(GTL, encoding="utf-8", newline="").read()
    if f'<v n="TextID">"{LABEL_TEXTID}"</v>' in g:
        print(f"  GlobalTextList already has {LABEL_TEXTID}")
    else:
        m = re.search(r' *<o>\r?\n\s*<v n="TextID">"1304"</v>.*?</o>\r?\n', g, re.S)
        if not m:
            die("cannot find the 1304 entry to anchor the new GlobalTextList entry")
        donor_entry = m.group(0)
        new_entry = (donor_entry.replace('"1304"', f'"{LABEL_TEXTID}"')
                     .replace('"File log"', f'"{NEW_LABEL}"'))
        if new_entry == donor_entry:
            die("GlobalTextList clone did not change -- check the donor's shape")
        io.open(GTL, "w", encoding="utf-8", newline="").write(
            g.replace(donor_entry, donor_entry + new_entry, 1))
        print(f"  GlobalTextList: TextID {LABEL_TEXTID} = {NEW_LABEL!r}")

    print("\nRun scripts/validate_visu.py, then OPEN Robot.TcVIS IN TcXaeShell and")
    print("REBUILD -- rendering catches a structural splice, the build catches a")
    print("GUID clash, and neither substitutes for the other.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
