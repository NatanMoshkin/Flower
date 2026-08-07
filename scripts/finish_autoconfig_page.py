"""Finish the AutoConfig split: Back button, strip AutoMain, register the page.

Second half of scripts/build_autoconfig_page.py. Separate so each half can be
re-run and diffed on its own.

  1. Import a Back button into AutoConfig. This is the one CROSS-FILE clone in
     the job: a nav button is a VisuFbElemSimple carrying a
     ChangeVisuInputAction, and AutoMain -- which AutoConfig was cloned from --
     has no instance of one to copy. Main does. Checked first: both pages'
     TypeLists already map ChangeVisuInputAction to the SAME plugin GUID
     ({b4c3a27b-...}), so no TypeList merge is needed; element bodies reference
     types by name, not by GUID.

  2. Strip the 16 stCfg controls out of AutoMain, last-first so earlier line
     indices stay valid.

  3. Add a Main -> AutoConfig nav button, and re-space that row from four
     buttons to five.

  4. Register AutoConfig in PLC1.plcproj. Without the <Compile Include> the page
     is invisible to the build -- it will render in the IDE and simply not exist
     when the project compiles.

Run AFTER build_autoconfig_page.py, then:
      python scripts/fix_visu_object_guids.py AutoConfig   # MANDATORY
      python scripts/validate_visu.py
      python scripts/validate_automain.py
"""

from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1] / (
    "Panel_PLC_HMI/167_01_Saad_PLC/167_01_Saad_PLC/PLC1")
VISU = ROOT / "VISU"
GTL = ROOT / "GlobalTextList.TcGTLO"
PLCPROJ = ROOT / "PLC1.plcproj"

M_LEFT, M_TOP = "1649127785L", "357335551L"
M_WIDTH, M_HEIGHT = "2422045748L", "2134141914L"
M_CX, M_CY = "550940142L", "1473355128L"
M_TEXT, M_COUNTER = "390574330L", "823443203L"
M_BOOLVAR, M_TAP, M_TEXTVAR = "743958181L", "1186196937L", "2477733581L"
INDENT_O, INDENT_C = "              <o>", "              </o>"

# Back button on AutoConfig
BACK = dict(left=600, top=365, width=150, height=44, label="Back",
            target="Main", elem_id=200, counter="1200",
            guid="{a1b2c3d4-0e5f-4a6b-9c7d-100200000001}")

# Main's nav row, re-spaced from 4 buttons to 5.
NAV_Y, NAV_W, NAV_H, NAV_X0, NAV_PITCH = 417, 150, 44, 20, 153
NAV_ORDER = ["AutoConfig", "Logs", "Robot", "GripperManual", "PistonsManual"]
NEW_NAV = dict(label="Auto Config", target="AutoConfig", elem_id=12,
               counter="1201", guid="{a1b2c3d4-0e5f-4a6b-9c7d-100200000002}")


def set_member(text, mid, value, required=True):
    pat = re.compile(
        r'(<v n="Id">' + re.escape(mid) + r'</v>\s*\n\s*<v n="Value">)(.*?)(</v>)',
        re.DOTALL)
    out, n = pat.subn(lambda m: m.group(1) + value + m.group(3), text, count=1)
    if n != 1:
        if not required:
            return text
        raise SystemExit(f"member {mid}: expected 1 replacement, got {n}")
    return out


def get_member(text, mid):
    m = re.search(r'<v n="Id">' + re.escape(mid) + r'</v>\s*\n\s*<v n="Value">(.*?)</v>',
                  text, re.DOTALL)
    return m.group(1).strip('"') if m else None


def elements(text):
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
            out.append((s, e, "".join(lines[s:e + 1]),
                        re.search(r'VisualElementTypeName">"(.*?)"', line).group(1)))
    return lines, out


def binding(body):
    for mid in (M_BOOLVAR, M_TAP, M_TEXTVAR):
        v = get_member(body, mid)
        if v:
            return v
    return None


def nav_target(body):
    m = re.search(r'<v n="Assign33">"(.*?)"</v>', body)
    return m.group(1) if m else None


def reid(body, elem_id, guid):
    body = re.sub(r'(<v n="VisualElementIdentifier">")GenElemInst_\d+("</v>)',
                  lambda m: m.group(1) + f"GenElemInst_{elem_id}" + m.group(2),
                  body, count=1)
    body = re.sub(r'(<v n="VisualElementIdentification">)\{[0-9a-fA-F-]+\}(</v>)',
                  lambda m: m.group(1) + guid + m.group(2), body, count=1)
    body = re.sub(r'(<v n="VisualElementId">)\d+(</v>)',
                  lambda m: m.group(1) + str(elem_id) + m.group(2), body, count=1)
    return body


def place(body, x, y, w, h):
    body = set_member(body, M_LEFT, str(x))
    body = set_member(body, M_TOP, str(y))
    body = set_member(body, M_WIDTH, str(w))
    body = set_member(body, M_HEIGHT, str(h))
    body = set_member(body, M_CX, str(x + w // 2), required=False)
    body = set_member(body, M_CY, str(y + h // 2), required=False)
    return body


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


# --------------------------------------------------------------------------- #
def donor_nav_button():
    """A working nav button from Main, to clone. Type compatibility checked."""
    main = (VISU / "Main.TcVIS").read_text(encoding="utf-8")
    cfgp = (VISU / "AutoConfig.TcVIS").read_text(encoding="utf-8")
    for name in ("ChangeVisuInputAction",):
        gm = re.search(r'<Type n="' + name + r'">\{([0-9a-f-]+)\}', main)
        gc = re.search(r'<Type n="' + name + r'">\{([0-9a-f-]+)\}', cfgp)
        if not (gm and gc):
            raise SystemExit(f"{name}: missing from a TypeList - cannot import")
        if gm.group(1) != gc.group(1):
            raise SystemExit(
                f"{name}: TypeList GUIDs differ (Main {gm.group(1)} vs "
                f"AutoConfig {gc.group(1)}) - a merge would be needed")
    _lines, els = elements(main)
    for _s, _e, body, ty in els:
        if ty == "VisuFbElemSimple" and nav_target(body):
            return body
    raise SystemExit("no nav button on Main to clone")


def add_back_button():
    path = VISU / "AutoConfig.TcVIS"
    text = path.read_text(encoding="utf-8")
    if f'<v n="Assign33">"{BACK["target"]}"</v>' in text:
        print("  Back button already present")
        return
    donor = donor_nav_button()
    body = place(donor, BACK["left"], BACK["top"], BACK["width"], BACK["height"])
    body = set_member(body, M_TEXT, f'"{BACK["label"]}"')
    body = set_member(body, M_COUNTER, f'"{BACK["counter"]}"')
    body = re.sub(r'(<v n="Assign33">)"[^"]*"(</v>)',
                  lambda m: m.group(1) + f'"{BACK["target"]}"' + m.group(2),
                  body, count=1)
    body = reid(body, BACK["elem_id"], BACK["guid"])
    # The owning GUID travels with the donor and must become this page's.
    own = re.search(r'<Visu Name="AutoConfig" Id="(\{[0-9a-fA-F-]+\})"', text)
    if not own:
        raise SystemExit("cannot read AutoConfig's own page GUID")
    body = re.sub(r'(<v n="VisualElementOwningObjectGuid">)\{[0-9a-fA-F-]+\}(</v>)',
                  lambda m: m.group(1) + own.group(1) + m.group(2), body)

    lines, els = elements(text)
    last_end = max(e for _s, e, _b, _t in els)
    text = "".join(lines[:last_end + 1]) + body + "".join(lines[last_end + 1:])
    path.write_text(text, encoding="utf-8")
    gtl_register(BACK["counter"], BACK["label"])
    print(f"  imported Back button -> {BACK['target']} at "
          f"({BACK['left']},{BACK['top']})")


def strip_automain():
    path = VISU / "AutoMain.TcVIS"
    text = path.read_text(encoding="utf-8")
    lines, els = elements(text)
    spans = []
    for s, e, body, ty in els:
        bind = binding(body) or ""
        x = int(get_member(body, M_LEFT))
        if bind.startswith("stCfg.") or (ty == "VisuFbElemSimple" and x >= 500):
            spans.append((s, e))
    if not spans:
        print("  AutoMain already stripped")
        return
    print(f"  stripping {len(spans)} stCfg element(s) from AutoMain")
    for s, e in sorted(spans, reverse=True):
        del lines[s:e + 1]
    path.write_text("".join(lines), encoding="utf-8")
    _l, left = elements("".join(lines))
    print(f"  AutoMain now has {len(left)} elements")


def main_nav():
    path = VISU / "Main.TcVIS"
    text = path.read_text(encoding="utf-8")
    if f'<v n="Assign33">"{NEW_NAV["target"]}"</v>' not in text:
        _lines, els = elements(text)
        donor = next(b for _s, _e, b, t in els
                     if t == "VisuFbElemSimple" and nav_target(b))
        body = set_member(donor, M_TEXT, f'"{NEW_NAV["label"]}"')
        body = set_member(body, M_COUNTER, f'"{NEW_NAV["counter"]}"')
        body = re.sub(r'(<v n="Assign33">)"[^"]*"(</v>)',
                      lambda m: m.group(1) + f'"{NEW_NAV["target"]}"' + m.group(2),
                      body, count=1)
        body = reid(body, NEW_NAV["elem_id"], NEW_NAV["guid"])
        lines, els = elements(text)
        last_end = max(e for _s, e, _b, _t in els)
        text = "".join(lines[:last_end + 1]) + body + "".join(lines[last_end + 1:])
        path.write_text(text, encoding="utf-8")
        gtl_register(NEW_NAV["counter"], NEW_NAV["label"])
        print(f"  added Main -> {NEW_NAV['target']} nav button")

    # re-space the row so five buttons fit where four used to
    text = path.read_text(encoding="utf-8")
    lines, els = elements(text)
    navs = {nav_target(b): (s, e, b) for s, e, b, t in els if nav_target(b)}
    missing = [t for t in NAV_ORDER if t not in navs]
    if missing:
        raise SystemExit(f"nav buttons missing from Main: {missing}")
    rewritten = {}
    for i, target in enumerate(NAV_ORDER):
        s, e, body = navs[target]
        x = NAV_X0 + i * NAV_PITCH
        rewritten[(s, e)] = place(body, x, NAV_Y, NAV_W, NAV_H)
        print(f"    nav {i}: x={x:<4} -> {target}")
    for (s, e), body in sorted(rewritten.items(), reverse=True):
        lines[s:e + 1] = [body]
    path.write_text("".join(lines), encoding="utf-8")


def register_plcproj():
    text = PLCPROJ.read_text(encoding="utf-8")
    if "VISU\\AutoConfig.TcVIS" in text:
        print("  AutoConfig already registered in PLC1.plcproj")
        return
    anchor = re.search(
        r'[ \t]*<Compile Include="VISU\\AutoMain\.TcVIS">.*?</Compile>\r?\n',
        text, re.DOTALL)
    if not anchor:
        raise SystemExit("no AutoMain <Compile Include> block to model on")
    block = anchor.group(0).replace("AutoMain.TcVIS", "AutoConfig.TcVIS")
    text = text[:anchor.end()] + block + text[anchor.end():]
    PLCPROJ.write_text(text, encoding="utf-8")
    print("  registered AutoConfig.TcVIS in PLC1.plcproj")


def main() -> int:
    if not (VISU / "AutoConfig.TcVIS").exists():
        raise SystemExit("run build_autoconfig_page.py first")
    print("1. Back button")
    add_back_button()
    print("2. strip AutoMain")
    strip_automain()
    print("3. Main navigation")
    main_nav()
    print("4. plcproj")
    register_plcproj()
    print("\nNOW RUN: python scripts/fix_visu_object_guids.py AutoConfig")
    return 0


if __name__ == "__main__":
    sys.exit(main())
