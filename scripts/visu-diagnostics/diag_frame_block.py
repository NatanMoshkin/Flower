"""Diagnostic: how does a VisuFbFrame in PistonsManual bind its Piston?"""
import pathlib, re

V = pathlib.Path(__file__).resolve().parents[1] / (
    "Panel_PLC_HMI/167_01_Saad_PLC/167_01_Saad_PLC/PLC1/VISU/PistonsManual.TcVIS")
lines = V.read_text(encoding="utf-8").splitlines(keepends=True)
O, C = "              <o>", "              </o>"

frames = []
for i, l in enumerate(lines):
    if '"VisuFbFrame"' in l and "VisualElementTypeName" in l:
        s = i
        while lines[s].rstrip("\r\n") != O: s -= 1
        e = i
        while lines[e].rstrip("\r\n") != C: e += 1
        frames.append((s, e, "".join(lines[s:e+1])))

print(f"{len(frames)} frames; line spans: " +
      ", ".join(f"{s+1}-{e+1}" for s, e, _ in frames))

# What distinguishes frame 1 from frame 2?
import difflib
d = [l for l in difflib.unified_diff(
        frames[0][2].splitlines(True), frames[1][2].splitlines(True), n=0)
     if l.startswith(('+', '-')) and not l.startswith(('+++', '---'))]
print(f"\n=== frame[0] vs frame[1]: {len(d)} differing lines ===")
print("".join(d))

# Also show the Simple (Back button) element's ChangeVisu action.
for i, l in enumerate(lines):
    if '"VisuFbElemSimple"' in l and "VisualElementTypeName" in l:
        s = i
        while lines[s].rstrip("\r\n") != O: s -= 1
        e = i
        while lines[e].rstrip("\r\n") != C: e += 1
        body = "".join(lines[s:e+1])
        print(f"=== Simple element lines {s+1}-{e+1}: ChangeVisu action ===")
        m = re.search(r'<d n="VisualElementInputActions".*?</d>', body, re.S)
        print(m.group(0)[:900] if m else "(none)")
        break
