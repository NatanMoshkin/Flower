"""Give a cloned .TcVIS page its own generated-object GUIDs.

Cloning a visualization page copies far more identity than the element
GUIDs that `fix_visu_guids.py` handles. Each page also carries ~60 GUIDs
naming the objects the compiler will *generate* for it:

    <Visu Id>                         the page object
    VisuRegDesc.FbGuid                its registration FB
    InputsPou.FbGuid                  its input-handler POU  <-- __inp__vis
    FbMethods[...]                    one GUID per generated method
    GeneratedGlobalVisuVarsGuid       its generated GVLs
    VisuRegisterGvl, DialogDut, ...

Replacing only the page GUID (which happens to equal the *first* FbGuid)
leaves the rest duplicated. Two visualizations then register the same
generated objects, the compiler emits one and the other's name lookup
fails:

    Unknown type: 'PistonsManual__inp__vis'

...reported against the ORIGINAL page, which was never touched. That is
the trap: the error names the victim, not the clone.

The invariant this restores, verified against the pristine pages: outside
`<TypeList>`, no GUID is shared by any two `.TcVIS` files. There is not a
single project-global GUID among them -- every page owns all of its own.

Replacements are uuid5-derived from (page name, old GUID), so the script is
deterministic and idempotent: re-running finds nothing left to change.

Run:  python scripts/fix_visu_object_guids.py [PageToRewrite]
Then: python scripts/validate_visu.py
      ...and rebuild in TcXaeShell -- a render check will NOT catch this.
"""

from __future__ import annotations

import collections
import pathlib
import re
import sys
import uuid

VISU = pathlib.Path(__file__).resolve().parents[1] / (
    "Panel_PLC_HMI/167_01_Saad_PLC/167_01_Saad_PLC/PLC1/VISU")

# Namespace is arbitrary but must stay fixed, or a re-run would produce
# different GUIDs and churn the file.
NS = uuid.UUID("6f1d0c2a-4b83-4f1e-9a77-2c5d8e0b41aa")

GUID_RE = re.compile(
    r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-'
    r'[0-9a-fA-F]{4}-[0-9a-fA-F]{12}')
NULL_GUID = "00000000-0000-0000-0000-000000000000"

# The page whose copies get rewritten. It must be the CLONE, never the
# original: the original's GUIDs were authored by the IDE and may be
# referenced by its own generated code.
DEFAULT_TARGET = "GripperManual"


def page_guids(text):
    """Every GUID outside <TypeList>, lowercased.

    TypeList holds references to VisualElem plugin types -- those are
    legitimately identical across pages and must not be touched.
    """
    body = re.sub(r'<TypeList>.*?</TypeList>', '', text, flags=re.DOTALL)
    return {g.lower() for g in GUID_RE.findall(body)} - {NULL_GUID}


def main(argv):
    target = argv[1] if len(argv) > 1 else DEFAULT_TARGET
    files = sorted(VISU.glob("*.TcVIS"))
    texts = {f.stem: f.read_text(encoding="utf-8") for f in files}
    if target not in texts:
        raise SystemExit(f"no such page: {target}")

    owners = collections.defaultdict(list)
    for stem, t in texts.items():
        for g in page_guids(t):
            owners[g].append(stem)

    shared = sorted(g for g, ps in owners.items()
                    if len(ps) > 1 and target in ps)
    if not shared:
        print(f"{target}: no GUIDs shared with another page - nothing to do.")
        return 0

    others = sorted({p for g in shared for p in owners[g] if p != target})
    print(f"{target} shares {len(shared)} GUID(s) with: {', '.join(others)}")

    taken = {g for g, ps in owners.items()}
    text = texts[target]
    for old in shared:
        new = str(uuid.uuid5(NS, f"{target}:{old}"))
        if new in taken:                      # astronomically unlikely
            raise SystemExit(f"derived GUID {new} already in use")
        taken.add(new)
        # Case-insensitive: these appear lowercase, but do not assume it.
        text, n = re.subn(re.escape(old), new, text, flags=re.IGNORECASE)
        if n == 0:
            raise SystemExit(f"{old}: expected >=1 replacement, got 0")
        print(f"  {old} -> {new}  ({n}x)")

    pathlib.Path(VISU / f"{target}.TcVIS").write_text(text, encoding="utf-8")
    print(f"\nwrote {target}.TcVIS")

    # Re-verify from disk rather than trusting the in-memory edit.
    texts[target] = (VISU / f"{target}.TcVIS").read_text(encoding="utf-8")
    again = collections.defaultdict(list)
    for stem, t in texts.items():
        for g in page_guids(t):
            again[stem].append(g)
    dupes = collections.defaultdict(list)
    for stem, gs in again.items():
        for g in gs:
            dupes[g].append(stem)
    bad = {g: ps for g, ps in dupes.items() if len(ps) > 1}
    if bad:
        raise SystemExit(f"still {len(bad)} cross-page GUID(s) shared: "
                         f"{list(bad)[:5]}")
    print("verified: no GUID shared between any two pages.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
