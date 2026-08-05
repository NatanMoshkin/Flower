"""Builds the bilingual operator and technician manuals into docs/.

    python scripts/manuals/build_manuals.py

Both languages ship inside each file and switch with CSS, so the pages work from
the filesystem with no network and no build step at view time.
"""

import importlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)

SPECS = [("mn_index", "index.html"),
         ("mn_operator", "operator-manual.html"),
         ("mn_technician", "technician-manual.html")]


def main():
    out_dir = os.path.join(REPO, "docs")
    for mod_name, filename in SPECS:
        mod = importlib.import_module(mod_name)
        html = mod.build()
        path = os.path.join(out_dir, filename)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(html)
        print(f"  wrote docs/{filename}  ({len(html):,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
