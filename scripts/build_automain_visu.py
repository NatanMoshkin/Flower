#!/usr/bin/env python3
"""Author the AutoMain.TcVIS control screen by cloning proven, version-matched
element blocks from the sibling VISU files and rewriting only leaf values
(coords, text, variable bindings, identifiers, GUIDs). Byte structure of each
proven element is preserved so XAE loads it without a "repair" (silent drop).

AutoMain is embedded as a control object on Main (no Back button). Elements,
all bound to absolute globals:
  - Title            "Auto Main"                     (VisuFbElemSimple, static)
  - Step textfield   GVL_HMI.stMasterAuto.sStepText  (VisuFbElemTextfield)
  - Error textfield  GVL_HMI.stMasterAuto.sErrorText (VisuFbElemTextfield)
  - START button     GVL_HMI.stMasterAuto.bStart     (VisuFbElemButton, tap)
  - STOP  button     GVL_HMI.stMasterAuto.bStop      (VisuFbElemButton, tap)
  - RESET button     GVL_HMI.stMasterAuto.bReset     (VisuFbElemButton, tap)
  - Continuous chk   GVL_HmiPersistent.stMasterAutoCfg.bContinuous (VisuFbCheckbox)
  - Auto Mode chk    GVL_HmiPersistent.stMasterAutoCfg.bAutoMode   (VisuFbCheckbox)

Run against the pristine committed stub (empty VisualElementList); the script
does not know how to de-dupe a prior injection, so restore first:
  git checkout HEAD -- .../VISU/AutoMain.TcVIS
"""
import re
import pathlib

VISU_DIR = pathlib.Path(__file__).resolve().parents[1] / (
    "Panel_PLC_HMI/167_01_Saad_PLC/167_01_Saad_PLC/PLC1/VISU"
)
SIMPLE_SRC = VISU_DIR / "PistonsManual.TcVIS"   # VisuFbElemSimple
WIDGET_SRC = VISU_DIR / "Piston.TcVIS"          # Button / Textfield / Checkbox
DST = VISU_DIR / "AutoMain.TcVIS"

AUTOMAIN_OWNING_GUID = "{5cb01f7a-eb2a-41a3-a05b-192e39796768}"

# Member ids (leaf keys) shared across element types.
M_LEFT, M_TOP, M_WIDTH, M_HEIGHT = "1649127785L", "357335551L", "2422045748L", "2134141914L"
M_CX, M_CY = "550940142L", "1473355128L"        # only Simple + Button carry a center
M_TEXT = "390574330L"                            # static text / label / format string
M_COUNTER = "823443203L"                         # per-element serial counter
# Variable-binding members, per type:
M_TAP = "1186196937L"                            # Button: Visu_TapInput bool var
M_TEXTVAR = "2477733581L"                        # Textfield: displayed variable
M_BOOLVAR = "743958181L"                         # Checkbox: toggled bool var

INDENT_O = "              <o>"
INDENT_C = "              </o>"


def extract_block(path, type_name):
    """Return the first <o>..</o> element of the given VisualElementTypeName."""
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    ti = next(i for i, l in enumerate(lines)
              if f'"{type_name}"' in l and "VisualElementTypeName" in l)
    s = ti
    while lines[s].rstrip("\r\n") != INDENT_O:
        s -= 1
    e = ti
    while lines[e].rstrip("\r\n") != INDENT_C:
        e += 1
    return "".join(lines[s:e + 1])


def set_member(text, member_id, new_value, required=True):
    """Rewrite the <v n="Value">..</v> that follows <v n="Id">member_id</v>."""
    pat = re.compile(
        r'(<v n="Id">' + re.escape(member_id) + r'</v>\s*\n\s*<v n="Value">)'
        r'(.*?)(</v>)',
        re.DOTALL,
    )
    new_text, n = pat.subn(lambda m: m.group(1) + new_value + m.group(3), text, count=1)
    if required:
        assert n == 1, f"member {member_id} not found/replaced once (got {n})"
    return new_text


def set_identity(text, *, uid, guid, elem_id):
    text = re.sub(r'(<v n="VisualElementIdentifier">")GenElemInst_\d+("</v>)',
                  lambda m: m.group(1) + f"GenElemInst_{uid}" + m.group(2), text, count=1)
    text = re.sub(r'(<v n="VisualElementIdentification">)\{[0-9a-fA-F-]+\}(</v>)',
                  lambda m: m.group(1) + guid + m.group(2), text, count=1)
    text = re.sub(r'(<v n="VisualElementOwningObjectGuid">)\{[0-9a-fA-F-]+\}(</v>)',
                  lambda m: m.group(1) + AUTOMAIN_OWNING_GUID + m.group(2), text, count=1)
    text = re.sub(r'(<v n="VisualElementId">)\d+(</v>)',
                  lambda m: m.group(1) + str(elem_id) + m.group(2), text, count=1)
    return text


def geometry(text, *, left, top, width, height, with_center):
    text = set_member(text, M_LEFT, str(left))
    text = set_member(text, M_TOP, str(top))
    text = set_member(text, M_WIDTH, str(width))
    text = set_member(text, M_HEIGHT, str(height))
    if with_center:
        text = set_member(text, M_CX, str(left + width // 2))
        text = set_member(text, M_CY, str(top + height // 2))
    return text


# --- Proven source blocks --------------------------------------------------
SIMPLE = extract_block(SIMPLE_SRC, "VisuFbElemSimple")
BUTTON = extract_block(WIDGET_SRC, "VisuFbElemButton")
TEXTFIELD = extract_block(WIDGET_SRC, "VisuFbElemTextfield")
CHECKBOX = extract_block(WIDGET_SRC, "VisuFbCheckbox")


def make_title(left, top, width, height, label, *, uid, guid, elem_id, counter):
    t = SIMPLE
    t = geometry(t, left=left, top=top, width=width, height=height, with_center=True)
    t = set_member(t, M_TEXT, '"' + label + '"')
    t = set_member(t, M_COUNTER, '"' + str(counter) + '"')
    t = set_identity(t, uid=uid, guid=guid, elem_id=elem_id)
    # Strip the ChangeVisu input action -> empty hashtable (title is display-only).
    t = re.sub(
        r'<d n="VisualElementInputActions" t="Hashtable" ckt="String" cvt="IInputAction\[\]">.*?</d>',
        '<d n="VisualElementInputActions" t="Hashtable" />',
        t, count=1, flags=re.DOTALL)
    return t


def make_button(left, top, width, height, label, var, *, uid, guid, elem_id, counter):
    t = BUTTON
    t = geometry(t, left=left, top=top, width=width, height=height, with_center=True)
    t = set_member(t, M_TEXT, '"' + label + '"')
    t = set_member(t, M_TAP, '"' + var + '"')
    t = set_member(t, M_COUNTER, '"' + str(counter) + '"')
    t = set_identity(t, uid=uid, guid=guid, elem_id=elem_id)
    return t


def make_textfield(left, top, width, height, var, *, uid, guid, elem_id, counter):
    t = TEXTFIELD
    t = geometry(t, left=left, top=top, width=width, height=height, with_center=False)
    t = set_member(t, M_TEXTVAR, '"' + var + '"')
    t = set_member(t, M_COUNTER, '"' + str(counter) + '"')
    t = set_identity(t, uid=uid, guid=guid, elem_id=elem_id)
    return t


def make_checkbox(left, top, width, height, label, var, *, uid, guid, elem_id, counter):
    t = CHECKBOX
    t = geometry(t, left=left, top=top, width=width, height=height, with_center=False)
    t = set_member(t, M_TEXT, '"' + label + '"')
    t = set_member(t, M_BOOLVAR, '"' + var + '"')
    t = set_member(t, M_COUNTER, '"' + str(counter) + '"')
    t = set_identity(t, uid=uid, guid=guid, elem_id=elem_id)
    return t


# Distinct GUIDs for the eight elements (arbitrary but unique).
G = ["{7e1c9a10-0a01-4b21-9c31-0000000000b%d}" % i for i in range(1, 9)]

# Bindings are interface-relative: state controls -> the ST_HmiMasterAuto
# VAR_IN_OUT (stMasterAutoCycle); config checkboxes -> the ST_HmiMasterAutoCfg
# VAR_IN_OUT (stCfg). Main wires both refs (stMasterAutoCycle ->
# GVL_HMI.stMasterAuto, stCfg -> GVL_HmiPersistent.stMasterAutoCfg).
STATE = "stMasterAutoCycle"
CFG = "stCfg"

elements = "".join([
    make_title(250, 10, 200, 40, "Auto Main",
               uid=100, guid=G[0], elem_id=100, counter=1100),
    make_textfield(20, 70, 300, 34, STATE + ".sStepText",
                   uid=101, guid=G[1], elem_id=101, counter=1101),
    make_textfield(20, 112, 460, 34, STATE + ".sErrorText",
                   uid=102, guid=G[2], elem_id=102, counter=1102),
    make_button(20, 175, 120, 50, "START", STATE + ".bStart",
                uid=103, guid=G[3], elem_id=103, counter=1103),
    make_button(160, 175, 120, 50, "STOP", STATE + ".bStop",
                uid=104, guid=G[4], elem_id=104, counter=1104),
    make_button(300, 175, 120, 50, "RESET", STATE + ".bReset",
                uid=105, guid=G[5], elem_id=105, counter=1105),
    make_checkbox(20, 255, 240, 30, "Continuous", CFG + ".bContinuous",
                  uid=106, guid=G[6], elem_id=106, counter=1106),
    make_checkbox(20, 295, 240, 30, "Auto Mode", CFG + ".bAutoMode",
                  uid=107, guid=G[7], elem_id=107, counter=1107),
])

# --- Inject into AutoMain.TcVIS -------------------------------------------
dst_text = DST.read_text(encoding="utf-8")

empty_list = '            <l n="VisualElementList" t="VisualElemCollection" />'
populated = (
    '            <l n="VisualElementList" t="VisualElemCollection" cet="GenericVisualElem">\n'
    + elements
    + '            </l>'
)
assert empty_list in dst_text, "empty VisualElementList marker not found (restore stub first)"
dst_text = dst_text.replace(empty_list, populated, 1)

# Ensure every type name used by the cloned blocks exists in AutoMain's first
# (XmlArchive/Data) TypeList. Copy any missing name->GUID from Piston.TcVIS,
# but never overwrite an existing mapping (preserves AutoMain's
# CaseInsensitiveHashtable -> {7df88604}).
def typelist_span(text, marker="      <TypeList>"):
    o = text.index(marker)
    c = text.index("      </TypeList>", o)
    return o, c

src_types = {}
for m in re.finditer(r'<Type n="([^"]+)">([^<]*)</Type>',
                     WIDGET_SRC.read_text(encoding="utf-8")):
    src_types.setdefault(m.group(1), m.group(2))

o, c = typelist_span(dst_text)
body = dst_text[o:c]
add = [f'        <Type n="{n}">{v}</Type>\n'
       for n, v in src_types.items() if f'<Type n="{n}">' not in body]
dst_text = dst_text[:c] + "".join(add) + dst_text[c:]

# Bump the counters above anything we used.
dst_text = dst_text.replace('<v n="UniqueIdGenerator">"7"</v>',
                            '<v n="UniqueIdGenerator">"120"</v>', 1)
dst_text = dst_text.replace('<v n="LastUsedIdForIdentifier">13</v>',
                            '<v n="LastUsedIdForIdentifier">120</v>', 1)

# The committed stub declares the interface as a whole-FB in_out
# (fbMasterAutoCycle : FB_MasterAutoCycle), but an FB does not expose its own
# VAR_IN_OUT members to the visu. Replace it with the state struct the element
# bindings actually resolve against.
old_iface = '<v n="Text">"\tfbMasterAutoCycle : FB_MasterAutoCycle;"</v>'
new_iface = '<v n="Text">"\tstMasterAutoCycle : ST_HmiMasterAuto;"</v>'
assert dst_text.count(old_iface) == 1, "interface FB in_out TextLine not found uniquely"
dst_text = dst_text.replace(old_iface, new_iface, 1)

# Add the second interface VAR_IN_OUT (stCfg : ST_HmiMasterAutoCfg) as a new
# TextLine just before END_VAR in the visu interface TextDocument.
cfg_line = (
    '              <o>\n'
    '                <v n="Id">8L</v>\n'
    '                <n n="Tag" />\n'
    '                <v n="Text">"\tstCfg : ST_HmiMasterAutoCfg;"</v>\n'
    '              </o>\n'
)
end_var_block = (
    '              <o>\n'
    '                <v n="Id">1L</v>\n'
    '                <n n="Tag" />\n'
    '                <v n="Text">"END_VAR"</v>\n'
    '              </o>\n'
)
assert dst_text.count(end_var_block) == 1, "interface END_VAR TextLine not found uniquely"
dst_text = dst_text.replace(end_var_block, cfg_line + end_var_block, 1)

DST.write_text(dst_text, encoding="utf-8")
print("OK: wrote", DST)
print("types added:", [a.strip() for a in add])
