"""Builds the Auto state-machine diagram docs into docs/.

    python scripts/statediagram/build_state_diagrams.py

One renderer, three specs, so the variants stay geometrically comparable — the
only thing that moves between pages is what the variant actually changes.
"""

import importlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)

# (module, filename, subdir under docs/). The as-built page is a live document;
# the other three are decision records and live in docs/archive/.
SPECS = [
    ("sm_current", "auto-state-machine-current.html", ""),
    ("sm_pause", "auto-state-machine-pause.html", "archive"),
    ("sm_retract", "auto-state-machine-retract-all.html", "archive"),
    ("sm_combined", "auto-state-machine-combined.html", "archive"),
]


def main():
    out_dir = os.path.join(REPO, "docs")
    built = []
    for mod_name, filename, subdir in SPECS:
        try:
            mod = importlib.import_module(mod_name)
        except ModuleNotFoundError:
            print(f"  skip {filename} (no {mod_name}.py yet)")
            continue
        html = mod.build()
        target = os.path.join(out_dir, subdir) if subdir else out_dir
        os.makedirs(target, exist_ok=True)
        path = os.path.join(target, filename)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(html)
        rel = f"docs/{subdir}/{filename}" if subdir else f"docs/{filename}"
        print(f"  wrote {rel}  ({len(html):,} bytes)")
        built.append(filename)
    if not built:
        print("nothing built")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
