"""Checklist s4: create GripperManual.TcVIS (2 grip pistons) from PistonsManual.

Clones the whole proven PistonsManual page -- same project, same TwinCAT
version -- then:
  * renames the object and gives it a fresh, self-consistent GUID
    (Visu Id == every VisualElementOwningObjectGuid, as all four existing
    pages do),
  * keeps the first two Piston frames and retargets them to
    GVL_HMI.stGripSolL / stGripSolR,
  * deletes the other four frames,
  * keeps the "Main" nav button untouched,
  * registers the file in PLC1.plcproj.

Element blocks are never authored, only cloned/deleted/retargeted at leaf
values. Never locate structure with a substring search on indentation --
see scripts/validate_visu.py for why.

Idempotent: refuses to run if the page already exists.

Run:  python scripts/build_grippermanual.py
Then: python scripts/validate_visu.py GripperManual.TcVIS
      ...and open it in TcXaeShell to confirm it renders.
"""

from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1] / (
    "Panel_PLC_HMI/167_01_Saad_PLC/167_01_Saad_PLC/PLC1")
SRC = ROOT / "VISU/PistonsManual.TcVIS"
DST = ROOT / "VISU/GripperManual.TcVIS"
PLCPROJ = next(ROOT.glob("*.plcproj"))

NEW_GUID = "{a1b2c3d4-0e5f-4a6b-9c7d-000000000101}"
KEEP = ["GVL_HMI.stGripSolL", "GVL_HMI.stGripSolR"]

INDENT_O, INDENT_C = "              <o>", "              </o>"


def frame_blocks(lines):
    """(start, end, target) for each VisuFbFrame, in document order."""
    out = []
    for i, l in enumerate(lines):
        if '"VisuFbFrame"' in l and "VisualElementTypeName" in l:
            s = i
            while lines[s].rstrip("\r\n") != INDENT_O:
                s -= 1
            e = i
            while lines[e].rstrip("\r\n") != INDENT_C:
                e += 1
            body = "".join(lines[s:e + 1])
            m = re.search(r'<v n="BasicTypeNodeValue">"(GVL_[\w.]+)"</v>', body)
            out.append((s, e, m.group(1) if m else None))
    return out


def main():
    if DST.exists():
        print(f"{DST.name} already exists - nothing to do.")
        return 0

    text = SRC.read_text(encoding="utf-8")

    m = re.search(r'<Visu Name="PistonsManual" Id="(\{[0-9a-fA-F-]+\})"', text)
    if not m:
        raise SystemExit("could not read the source <Visu> header")
    old_guid = m.group(1)
    if NEW_GUID.lower() in text.lower():
        raise SystemExit(f"{NEW_GUID} already present in the source")

    # Rename + re-GUID. old_guid appears as the Visu Id and as every
    # element's VisualElementOwningObjectGuid; both must move together.
    text = text.replace('<Visu Name="PistonsManual"', '<Visu Name="GripperManual"', 1)
    n_guid = text.count(old_guid)
    text = text.replace(old_guid, NEW_GUID)
    print(f"re-GUIDed {n_guid} occurrence(s): {old_guid} -> {NEW_GUID}")

    lines = text.splitlines(keepends=True)
    frames = frame_blocks(lines)
    print(f"source has {len(frames)} frames: {[f[2] for f in frames]}")
    if len(frames) != 6:
        raise SystemExit(f"expected 6 frames in the source, found {len(frames)}")

    # Retarget the two we keep (both spots per frame: the type-node value and
    # the plain member value).
    for (s, e, target), new_target in zip(frames[:2], KEEP):
        body = "".join(lines[s:e + 1])
        hits = body.count(f'"{target}"')
        if hits != 2:
            raise SystemExit(f"{target}: expected 2 binding spots, found {hits}")
        lines[s:e + 1] = [body.replace(f'"{target}"', f'"{new_target}"')]
        print(f"  retargeted {target} -> {new_target}")
        # Re-scan: the slice above collapsed a range into one string element.
        lines = "".join(lines).splitlines(keepends=True)
        frames = frame_blocks(lines)

    # Delete the remaining four frames, last first so indices stay valid.
    for s, e, target in reversed(frames[2:]):
        del lines[s:e + 1]
        print(f"  removed frame {target}")

    DST.write_text("".join(lines), encoding="utf-8")
    print(f"wrote {DST.name}")

    # Register in the PLC project (plain named-attribute XML, safe to edit).
    proj = PLCPROJ.read_text(encoding="utf-8")
    if "GripperManual.TcVIS" not in proj:
        anchor = ('    <Compile Include="VISU\\PistonsManual.TcVIS">\n'
                  '      <SubType>Code</SubType>\n'
                  '      <DependentUpon>VISU\\VisualizationManager.TcVMO</DependentUpon>\n'
                  '    </Compile>\n')
        if anchor not in proj:
            raise SystemExit("could not find the PistonsManual <Compile> anchor")
        block = ('    <Compile Include="VISU\\GripperManual.TcVIS">\n'
                 '      <SubType>Code</SubType>\n'
                 '      <DependentUpon>VISU\\VisualizationManager.TcVMO</DependentUpon>\n'
                 '    </Compile>\n')
        PLCPROJ.write_text(proj.replace(anchor, anchor + block, 1), encoding="utf-8")
        print(f"registered in {PLCPROJ.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
