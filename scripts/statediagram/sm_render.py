"""Renders a state-machine spec to a self-contained HTML page with inline SVG.

Why hand-rolled SVG and not mermaid: these pages live in docs/ and must open
from the filesystem with no network. Mermaid means a CDN script, which is both
offline-hostile here and blocked outright in published Artifacts. Inline SVG
also lets the three variant diagrams share exact geometry, so the difference
between them is the only thing that moves on the page.

Layout is explicit, not automatic: every state carries its (col, row) and the
awkward edges carry waypoints. A generic layout engine would spend a lot of
code to produce a worse picture for a graph this shape.
"""

import html

# ---- geometry -------------------------------------------------------------
BOX_W, BOX_H = 216, 50
# ROW_DY - BOX_H is the vertical gap an edge label has to live in. At 94 that
# is 44 px, enough for a one-line label clear of both boxes. Keep vertical-edge
# labels to ONE line; anything longer belongs in the transition table.
COL_DX, ROW_DY = 340, 94
# PAD_X leaves room for two back-edge rails AND their right-anchored labels to
# the left of column 0.
PAD_X, PAD_Y = 215, 34
R = 9

# Shared lane geometry, so all three diagrams put the same thing in the same
# place and the only visual difference between pages is the actual change.
RAIL_A = 185          # inner left rail — short back edges
RAIL_B = 150          # outer left rail — the long cycle-return edge
BUS_X = 468           # fault bus, in the gap right of column 0 (ends at 431)
COL1_X = PAD_X + COL_DX

CLASSES = {
    # key        fill-var          stroke-var        text
    "arm":     ("c-arm-f", "c-arm-s", "c-arm-t"),
    "init":    ("c-init-f", "c-init-s", "c-init-t"),
    "cycle":   ("c-cyc-f", "c-cyc-s", "c-cyc-t"),
    "wait":    ("c-wait-f", "c-wait-s", "c-wait-t"),
    "fault":   ("c-flt-f", "c-flt-s", "c-flt-t"),
    "new":     ("c-new-f", "c-new-s", "c-new-t"),
    "ghost":   ("c-gho-f", "c-gho-s", "c-gho-t"),
}


class State:
    def __init__(self, key, label, value, cls, col, row, sub="", tag=""):
        self.key, self.label, self.value = key, label, value
        self.cls, self.col, self.row = cls, col, row
        self.sub, self.tag = sub, tag

    @property
    def x(self):
        return PAD_X + self.col * COL_DX

    @property
    def y(self):
        return PAD_Y + self.row * ROW_DY

    @property
    def cx(self):
        return self.x + BOX_W / 2

    @property
    def cy(self):
        return self.y + BOX_H / 2

    def port(self, side):
        return {
            "n": (self.cx, self.y),
            "s": (self.cx, self.y + BOX_H),
            "w": (self.x, self.cy),
            "e": (self.x + BOX_W, self.cy),
        }[side]


class Edge:
    """src/dst are state keys plus an exit/entry side, e.g. 'IDLE:s'.

    `via` is a list of absolute (x, y) waypoints; the polyline is
    src-port -> via... -> dst-port with no smoothing. `label` sits at the
    midpoint of the longest segment unless `label_at` overrides it.
    """

    def __init__(self, src, dst, label="", kind="seq", via=None, label_at=None,
                 label_side="r", arrow=True):
        self.src, self.dst, self.label, self.kind = src, dst, label, kind
        self.via = via or []
        self.label_at, self.label_side = label_at, label_side
        # Set False for the spurs of a shared "bus" — ten states faulting into
        # ERR would otherwise stack ten arrowheads on the same port.
        self.arrow = arrow


def _esc(s):
    return html.escape(str(s), quote=True)


def _points(states, edge):
    sk, ss = edge.src.split(":")
    dk, ds = edge.dst.split(":")
    p0 = states[sk].port(ss)
    p1 = states[dk].port(ds)
    return [p0] + list(edge.via) + [p1]


def _arrow_head(p_prev, p_end, size=7):
    """Triangle at p_end pointing along p_prev -> p_end (axis-aligned only)."""
    x0, y0 = p_prev
    x1, y1 = p_end
    if abs(x1 - x0) < 0.5:                      # vertical
        d = 1 if y1 > y0 else -1
        return f"{x1},{y1} {x1 - size * .62},{y1 - d * size} {x1 + size * .62},{y1 - d * size}"
    d = 1 if x1 > x0 else -1
    return f"{x1},{y1} {x1 - d * size},{y1 - size * .62} {x1 - d * size},{y1 + size * .62}"


def render_svg(states_list, edges, width=None, height=None):
    states = {s.key: s for s in states_list}
    w = width or (PAD_X * 2 + (max(s.col for s in states_list) + 1) * COL_DX)
    h = height or (PAD_Y * 2 + (max(s.row for s in states_list) + 1) * ROW_DY)

    o = [f'<svg class="smsvg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" '
         f'role="img" xmlns="http://www.w3.org/2000/svg">']

    # edges first so boxes paint over the ends
    for e in edges:
        pts = _points(states, e)
        poly = " ".join(f"{x},{y}" for x, y in pts)
        o.append(f'<polyline class="e e-{e.kind}" points="{poly}"/>')
        if e.arrow:
            o.append(f'<polygon class="ah ah-{e.kind}" '
                     f'points="{_arrow_head(pts[-2], pts[-1])}"/>')
        if e.label:
            if e.label_at:
                lx, ly = e.label_at
            else:                                # midpoint of longest segment
                best, bi = -1, 0
                for i in range(len(pts) - 1):
                    d = abs(pts[i + 1][0] - pts[i][0]) + abs(pts[i + 1][1] - pts[i][1])
                    if d > best:
                        best, bi = d, i
                lx = (pts[bi][0] + pts[bi + 1][0]) / 2
                ly = (pts[bi][1] + pts[bi + 1][1]) / 2
            anchor = {"r": "start", "l": "end", "c": "middle"}[e.label_side]
            dx = {"r": 8, "l": -8, "c": 0}[e.label_side]
            for ln, part in enumerate(e.label.split("\n")):
                o.append(f'<text class="el el-{e.kind}" x="{lx + dx}" '
                         f'y="{ly + 4 + ln * 13}" text-anchor="{anchor}">'
                         f"{_esc(part)}</text>")

    for s in states_list:
        f, st, tx = CLASSES[s.cls]
        o.append(f'<g class="n n-{s.cls}">')
        o.append(f'<rect x="{s.x}" y="{s.y}" width="{BOX_W}" height="{BOX_H}" '
                 f'rx="{R}" ry="{R}" fill="var(--{f})" stroke="var(--{st})"/>')
        ty = s.cy + (- 4 if s.sub else 5)
        o.append(f'<text class="nl" x="{s.x + 13}" y="{ty}" '
                 f'fill="var(--{tx})">{_esc(s.label)}</text>')
        if s.sub:
            o.append(f'<text class="ns" x="{s.x + 13}" y="{s.cy + 13}">'
                     f"{_esc(s.sub)}</text>")
        if s.value is not None:
            o.append(f'<text class="nv" x="{s.x + BOX_W - 11}" y="{s.cy + 4}" '
                     f'text-anchor="end">{_esc(s.value)}</text>')
        if s.tag:
            o.append(f'<text class="nt" x="{s.x + BOX_W - 11}" y="{s.y - 6}" '
                     f'text-anchor="end">{_esc(s.tag)}</text>')
        o.append("</g>")

    o.append("</svg>")
    return "\n".join(o), w, h


# ---- page chrome ----------------------------------------------------------
CSS = """
:root{
  --ground:#eef1f2; --surface:#ffffff; --surface-2:#e4e9ea;
  --ink:#131a1e; --ink-2:#4a575d; --ink-3:#6f7c82; --rule:#cdd6d8;
  --accent:#0e8a45; --accent-soft:#d8ece0;
  --fault:#c4342c; --fault-soft:#f7dedc;
  --caution:#a8761a; --caution-soft:#f7ecd6;
  --c-arm-f:#dfe6e9;  --c-arm-s:#93a5ad;  --c-arm-t:#1e2a30;
  --c-init-f:#f7ecd6; --c-init-s:#c79a3f; --c-init-t:#4a3608;
  --c-cyc-f:#d8ece0;  --c-cyc-s:#5aa87b;  --c-cyc-t:#10371f;
  --c-wait-f:#dae5f2; --c-wait-s:#7396c4; --c-wait-t:#152a45;
  --c-flt-f:#f7dedc;  --c-flt-s:#c4342c;  --c-flt-t:#4d100c;
  --c-new-f:#e7dcf3;  --c-new-s:#8360b8;  --c-new-t:#2b1550;
  --c-gho-f:#eceff0;  --c-gho-s:#b8c3c7;  --c-gho-t:#6f7c82;
  --mono:ui-monospace,"Cascadia Mono",Consolas,"SF Mono",Menlo,monospace;
  --sans:ui-sans-serif,system-ui,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
}
@media (prefers-color-scheme:dark){:root{
  --ground:#141a1f; --surface:#1b2329; --surface-2:#232d34;
  --ink:#e7edef; --ink-2:#a9b7bd; --ink-3:#7d8b92; --rule:#2f3b43;
  --accent:#3fbb75; --accent-soft:#143724;
  --fault:#f2726a; --fault-soft:#3d1d1b;
  --caution:#d9a640; --caution-soft:#3a2c12;
  --c-arm-f:#2b363d;  --c-arm-s:#6d8189;  --c-arm-t:#dbe4e7;
  --c-init-f:#3a2c12; --c-init-s:#c79a3f; --c-init-t:#f0dcae;
  --c-cyc-f:#143724;  --c-cyc-s:#3fbb75; --c-cyc-t:#c7ecd6;
  --c-wait-f:#17273b; --c-wait-s:#5f88bd; --c-wait-t:#cfe0f4;
  --c-flt-f:#3d1d1b;  --c-flt-s:#f2726a; --c-flt-t:#f9d5d2;
  --c-new-f:#2a1c42;  --c-new-s:#a382d6; --c-new-t:#e3d5f7;
  --c-gho-f:#20282e;  --c-gho-s:#3f4c54; --c-gho-t:#7d8b92;
}}
:root[data-theme="dark"]{
  --ground:#141a1f; --surface:#1b2329; --surface-2:#232d34;
  --ink:#e7edef; --ink-2:#a9b7bd; --ink-3:#7d8b92; --rule:#2f3b43;
  --accent:#3fbb75; --accent-soft:#143724;
  --fault:#f2726a; --fault-soft:#3d1d1b;
  --caution:#d9a640; --caution-soft:#3a2c12;
  --c-arm-f:#2b363d;  --c-arm-s:#6d8189;  --c-arm-t:#dbe4e7;
  --c-init-f:#3a2c12; --c-init-s:#c79a3f; --c-init-t:#f0dcae;
  --c-cyc-f:#143724;  --c-cyc-s:#3fbb75; --c-cyc-t:#c7ecd6;
  --c-wait-f:#17273b; --c-wait-s:#5f88bd; --c-wait-t:#cfe0f4;
  --c-flt-f:#3d1d1b;  --c-flt-s:#f2726a; --c-flt-t:#f9d5d2;
  --c-new-f:#2a1c42;  --c-new-s:#a382d6; --c-new-t:#e3d5f7;
  --c-gho-f:#20282e;  --c-gho-s:#3f4c54; --c-gho-t:#7d8b92;
}
:root[data-theme="light"]{
  --ground:#eef1f2; --surface:#ffffff; --surface-2:#e4e9ea;
  --ink:#131a1e; --ink-2:#4a575d; --ink-3:#6f7c82; --rule:#cdd6d8;
  --accent:#0e8a45; --accent-soft:#d8ece0;
  --fault:#c4342c; --fault-soft:#f7dedc;
  --caution:#a8761a; --caution-soft:#f7ecd6;
  --c-arm-f:#dfe6e9;  --c-arm-s:#93a5ad;  --c-arm-t:#1e2a30;
  --c-init-f:#f7ecd6; --c-init-s:#c79a3f; --c-init-t:#4a3608;
  --c-cyc-f:#d8ece0;  --c-cyc-s:#5aa87b;  --c-cyc-t:#10371f;
  --c-wait-f:#dae5f2; --c-wait-s:#7396c4; --c-wait-t:#152a45;
  --c-flt-f:#f7dedc;  --c-flt-s:#c4342c;  --c-flt-t:#4d100c;
  --c-new-f:#e7dcf3;  --c-new-s:#8360b8;  --c-new-t:#2b1550;
  --c-gho-f:#eceff0;  --c-gho-s:#b8c3c7;  --c-gho-t:#6f7c82;
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--ground);color:var(--ink);
     font:16px/1.6 var(--sans);font-variant-numeric:tabular-nums}
.wrap{max-width:74rem;margin:0 auto;padding:0 1.25rem 5rem}
.theme{position:fixed;top:.9rem;right:.9rem;z-index:5;background:var(--surface);
  color:var(--ink-2);border:1px solid var(--rule);border-radius:7px;
  padding:.35rem .6rem;font:.72rem var(--mono);cursor:pointer}
header.mast{padding:2.4rem 0 .5rem}
.eyebrow{font:600 .7rem/1 var(--mono);letter-spacing:.14em;text-transform:uppercase;
  color:var(--accent);margin:0 0 .7rem}
h1{font-size:clamp(1.5rem,3.6vw,2.1rem);line-height:1.15;margin:0 0 .5rem;
   text-wrap:balance;letter-spacing:-.01em}
.sub{color:var(--ink-2);margin:0;max-width:66ch}
nav.views{display:flex;flex-wrap:wrap;gap:.5rem;margin:1.4rem 0 0}
nav.views a{font:.8rem var(--sans);text-decoration:none;color:var(--ink-2);
  background:var(--surface);border:1px solid var(--rule);border-radius:999px;
  padding:.32rem .8rem}
nav.views a.here{background:var(--accent-soft);color:var(--accent);
  border-color:var(--accent);font-weight:600}
h2{font-size:1.08rem;margin:2.2rem 0 .3rem;letter-spacing:-.005em}
h3{font-size:.95rem;margin:1.5rem 0 .3rem}
p{margin:.6rem 0}
.diagram{margin:1.2rem 0 0;padding:1rem;background:var(--surface);
  border:1px solid var(--rule);border-radius:11px;overflow-x:auto}
.smsvg{display:block;max-width:100%;height:auto}
.e{fill:none;stroke:var(--ink-3);stroke-width:1.6}
.e-seq{stroke:var(--ink-2)}
.e-fault{stroke:var(--fault);stroke-dasharray:5 4}
.e-recover{stroke:var(--caution);stroke-dasharray:5 4}
.e-op{stroke:var(--accent)}
.e-new{stroke:var(--c-new-s);stroke-width:2.3}
.ah{stroke:none;fill:var(--ink-2)}
.ah-fault{fill:var(--fault)} .ah-recover{fill:var(--caution)}
.ah-op{fill:var(--accent)} .ah-new{fill:var(--c-new-s)}
.el{font:11px var(--mono);fill:var(--ink-3)}
.el-fault{fill:var(--fault)} .el-recover{fill:var(--caution)}
.el-op{fill:var(--accent)} .el-new{fill:var(--c-new-s)}
.nl{font:600 13px var(--sans)}
.ns{font:10.5px var(--mono);fill:var(--ink-3)}
.nv{font:700 11px var(--mono);fill:var(--ink-3)}
.nt{font:600 9.5px var(--mono);fill:var(--c-new-s);letter-spacing:.08em}
.legend{display:flex;flex-wrap:wrap;gap:.45rem .9rem;margin:.9rem 0 0;
  font:.76rem var(--mono);color:var(--ink-3)}
.legend span{display:inline-flex;align-items:center;gap:.35rem}
.sw{width:.85rem;height:.85rem;border-radius:3px;display:inline-block}
.ln{width:1.5rem;height:0;border-top-width:2px;display:inline-block}
.tblwrap{overflow-x:auto;border:1px solid var(--rule);border-radius:9px;
  background:var(--surface);margin:.9rem 0}
table{width:100%;border-collapse:collapse;min-width:40rem}
th,td{text-align:left;padding:.5rem .7rem;border-bottom:1px solid var(--rule);
  vertical-align:top;font-size:.85rem}
th{background:var(--surface-2);font:600 .68rem/1.3 var(--mono);
  letter-spacing:.07em;text-transform:uppercase;color:var(--ink-2);white-space:nowrap}
tr:last-child td{border-bottom:0}
td.m,.mono{font:.78rem var(--mono);color:var(--ink-2)}
code{font:.86em var(--mono);background:var(--surface-2);padding:.1em .32em;
  border-radius:3px}
.callout{margin:1.3rem 0;padding:.95rem 1.15rem;border-radius:9px;
  background:var(--surface);border:1px solid var(--rule);
  border-left:5px solid var(--caution);font-size:.9rem}
.callout.bad{border-left-color:var(--fault)}
.callout.good{border-left-color:var(--accent)}
.callout h3{margin:0 0 .3rem;font-size:.93rem}
.callout p{margin:.4rem 0 0;color:var(--ink-2)}
ul{margin:.5rem 0;padding-left:1.3rem}
li{margin:.3rem 0;color:var(--ink-2)}
footer{margin-top:3rem;padding-top:1.1rem;border-top:1px solid var(--rule);
  color:var(--ink-3);font-size:.79rem}
"""

JS = """
(function(){var r=document.documentElement,b=document.getElementById('t');
function lbl(){var m=r.getAttribute('data-theme');b.textContent='theme: '+(m||'auto');}
b.addEventListener('click',function(){var m=r.getAttribute('data-theme');
var n=m==='dark'?'light':(m==='light'?null:'dark');
if(n){r.setAttribute('data-theme',n);}else{r.removeAttribute('data-theme');}
try{n?localStorage.setItem('smtheme',n):localStorage.removeItem('smtheme');}catch(e){}
lbl();});
try{var s=localStorage.getItem('smtheme');if(s)r.setAttribute('data-theme',s);}catch(e){}
lbl();})();
"""

VIEWS = [
    ("auto-state-machine-current.html", "Current"),
    ("auto-state-machine-pause.html", "+ Pause / Continue"),
    ("auto-state-machine-retract-all.html", "+ Separate Retract-all"),
]

LEGEND = [
    ("sw", "c-arm-f", "c-arm-s", "not a sequence step"),
    ("sw", "c-init-f", "c-init-s", "retract / home chain"),
    ("sw", "c-wait-f", "c-wait-s", "waiting on something external"),
    ("sw", "c-cyc-f", "c-cyc-s", "bulb-cycle motion"),
    ("sw", "c-flt-f", "c-flt-s", "fault"),
    ("sw", "c-new-f", "c-new-s", "proposed / new"),
    ("ln", None, "ink-2", "normal advance"),
    ("ln", None, "accent", "operator action"),
    ("ln", None, "fault", "fault path"),
    ("ln", None, "caution", "recovery"),
]


def legend_html(show_new=True):
    o = ['<div class="legend">']
    for kind, fill, stroke, label in LEGEND:
        if not show_new and label == "proposed / new":
            continue
        if kind == "sw":
            o.append(f'<span><i class="sw" style="background:var(--{fill});'
                     f'border:1px solid var(--{stroke})"></i>{_esc(label)}</span>')
        else:
            o.append(f'<span><i class="ln" style="border-top:2px solid '
                     f'var(--{stroke})"></i>{_esc(label)}</span>')
    o.append("</div>")
    return "\n".join(o)


def page(title, eyebrow, lede, here, body_html):
    nav = ['<nav class="views">']
    for fn, label in VIEWS:
        cls = ' class="here"' if fn == here else ""
        nav.append(f'<a href="{fn}"{cls}>{_esc(label)}</a>')
    nav.append("</nav>")
    return "\n".join([
        "<!DOCTYPE html>", '<html lang="en">', "<head>", '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>{_esc(title)}</title>", f"<style>{CSS}</style>", "</head>", "<body>",
        '<button class="theme" id="t">theme: auto</button>', '<div class="wrap">',
        '<header class="mast">', f'<p class="eyebrow">{_esc(eyebrow)}</p>',
        f"<h1>{_esc(title)}</h1>", f'<p class="sub">{lede}</p>', "\n".join(nav),
        "</header>", body_html,
        '<footer>Generated by <code>scripts/statediagram/build_state_diagrams.py</code>. '
        "Diagrams are hand-laid-out inline SVG — no external scripts, so these pages "
        "open straight from the filesystem.</footer>",
        "</div>", f"<script>{JS}</script>", "</body>", "</html>",
    ])
