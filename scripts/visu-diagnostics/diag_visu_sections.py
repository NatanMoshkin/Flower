"""Diagnostic: what lives OUTSIDE VisualElementList in each page?"""
import pathlib, re

V = pathlib.Path(__file__).resolve().parents[1] / (
    "Panel_PLC_HMI/167_01_Saad_PLC/167_01_Saad_PLC/PLC1/VISU")

for name in ("PistonsManual", "GripperManual", "Robot", "AutoMain"):
    p = V / f"{name}.TcVIS"
    if not p.exists():
        continue
    s = p.read_text(encoding="utf-8")
    # Everything after the VisualElementList closes.
    o = s.index('n="VisualElementList"')
    depth, i = 0, o
    # find matching close of that <l>
    m = re.search(r'\n(\s*)</l>\n', s[o:])
    tail_start = s.index("</l>", o)
    tail = s[tail_start:]
    print(f"\n########## {name} ##########  (tail {len(tail)} chars)")
    # Named containers in the tail
    for mm in re.finditer(r'<([oldnav]) n="([^"]+)"(?: t="([^"]+)")?', tail):
        print(f"   <{mm.group(1)}> {mm.group(2)}"
              + (f"  t={mm.group(3)}" if mm.group(3) else ""))
    # Any TextDocument lines (interface declarations)
    decls = re.findall(r'<v n="Text">"([^"]*)"</v>', tail)
    if decls:
        print("   -- interface TextDocument lines --")
        for d in decls:
            print(f"      {d!r}")
    # Placeholder / instance references
    for tok in ("instvar", "__inp__vis", "Placeholder", "VisuRef", "Reference"):
        n = tail.count(tok)
        if n:
            print(f"   token {tok!r}: {n}")
