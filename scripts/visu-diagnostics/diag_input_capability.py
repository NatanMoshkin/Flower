"""Diagnostic: is there ANY proven input-capable element to clone?

Decides whether the Robot page's 11 numeric fields and the Auto-mode timer
fields can be scripted (clone-and-retarget) or must be authored in TcXaeShell.
"""
import pathlib, re, collections

V = pathlib.Path(__file__).resolve().parents[1] / (
    "Panel_PLC_HMI/167_01_Saad_PLC/167_01_Saad_PLC/PLC1/VISU")
O, C = "              <o>", "              </o>"

print("=== VisualElementInputActions: empty vs populated, per file/type ===")
for f in sorted(V.glob("*.TcVIS")):
    lines = f.read_text(encoding="utf-8").splitlines(keepends=True)
    stats = collections.Counter()
    for i, l in enumerate(lines):
        if "VisualElementTypeName" in l:
            typ = re.search(r'"([^"]+)"', l.split(">", 1)[1]).group(1)
            s = i
            while lines[s].rstrip("\r\n") != O: s -= 1
            e = i
            while lines[e].rstrip("\r\n") != C: e += 1
            body = "".join(lines[s:e+1])
            empty = '<d n="VisualElementInputActions" t="Hashtable" />' in body
            stats[(typ, "empty" if empty else "POPULATED")] += 1
    print(f"  {f.name}")
    for (typ, kind), n in sorted(stats.items()):
        print(f"      {n} x {typ:<22} inputActions={kind}")

print("\n=== what action classes appear anywhere? ===")
acts = collections.Counter()
for f in V.glob("*.TcVIS"):
    t = f.read_text(encoding="utf-8")
    for m in re.finditer(r'cet="([^"]*Action[^"]*)"|<o t="([A-Za-z]*Action[A-Za-z]*)"', t):
        acts[m.group(1) or m.group(2)] += 1
    for m in re.finditer(r'"(Visu_[A-Za-z]+)"', t):
        acts[m.group(1)] += 1
for k, n in sorted(acts.items()):
    print(f"  {n:>4} x {k}")

print("\n=== textfield: any 'input'/'write'/'edit' member names? ===")
t = (V / "Piston.TcVIS").read_text(encoding="utf-8")
for m in re.finditer(r'"(Visu[A-Za-z_]*(?:Input|Write|Edit)[A-Za-z_]*)"', t):
    print("  ", m.group(1))
hits = set(re.findall(r'<v n="([A-Za-z]*(?:Input|Write|Edit)[A-Za-z]*)">', t))
print("  attr names:", sorted(hits) or "(none)")
