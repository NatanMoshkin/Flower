"""Diagnostic: dissect one element so it can be cloned.

Usage: python diag_template_element.py <page.TcVIS> <GenElemInst_NNN>

Prints the element's type, every member id -> value, its input-action
structure, and which members differ from a sibling of the same type. That
last part is what tells you which leaves a clone must rewrite.
"""
import pathlib, re, sys

O, C = "              <o>", "              </o>"


def blocks(lines):
    for i, l in enumerate(lines):
        if "VisualElementTypeName" in l:
            s = i
            while lines[s].rstrip("\r\n") != O: s -= 1
            e = i
            while lines[e].rstrip("\r\n") != C: e += 1
            yield s, e, "".join(lines[s:e + 1])


def members(body):
    return re.findall(
        r'<v n="Id">(\w+)</v>\s*\n\s*<v n="Value"[^>]*>(.*?)</v>', body, re.S)


def main(page, uid):
    p = pathlib.Path(page)
    if not p.exists():
        p = (pathlib.Path(__file__).resolve().parents[2]
             / "Panel_PLC_HMI/167_01_Saad_PLC/167_01_Saad_PLC/PLC1/VISU" / page)
    lines = p.read_text(encoding="utf-8").splitlines(keepends=True)

    target = None
    for s, e, body in blocks(lines):
        if f'"{uid}"' in body:
            target = (s, e, body)
            break
    if not target:
        raise SystemExit(f"{uid} not found in {p.name}")
    s, e, body = target
    typ = re.search(r'<v n="VisualElementTypeName">"([^"]+)"', body).group(1)
    print(f"{uid}: {typ}   lines {s+1}-{e+1}  ({e-s+1} lines)")
    print(f"  GUID {re.search(r'VisualElementIdentification.>(.*?)</v>', body).group(1)}")
    print(f"  ElemId {re.search(r'VisualElementId.>(\d+)</v>', body).group(1)}")

    print("\n  === members (id -> value) ===")
    for mid, val in members(body):
        v = val.strip()
        if len(v) > 90:
            v = v[:90] + "..."
        print(f"    {mid:<14} {v}")

    print("\n  === input actions ===")
    m = re.search(r'<d n="VisualElementInputActions".*?</d>', body, re.S)
    if m and "/>" not in m.group(0)[:60]:
        print("    " + m.group(0).replace("\n", "\n    ")[:1600])
    else:
        print("    (empty)")

    # Compare with another element of the same type, if present.
    others = [b for ss, ee, b in blocks(lines)
              if f'"{typ}"' in b and f'"{uid}"' not in b]
    if others:
        a, b2 = dict(members(body)), dict(members(others[0]))
        diff = [k for k in a if a.get(k) != b2.get(k)]
        print(f"\n  === differs from a sibling {typ} in {len(diff)} member(s) ===")
        for k in diff:
            print(f"    {k:<14} {str(a[k])[:60]!r}  vs  {str(b2.get(k))[:60]!r}")
    else:
        print(f"\n  (no other {typ} on this page to compare against)")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    main(sys.argv[1], sys.argv[2])
