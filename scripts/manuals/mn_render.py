"""Renderer for the bilingual operator / technician manuals.

Both documents come from one content model, so English and Hebrew cannot drift
structurally: every block carries both languages and the page ships both in the
DOM, switching with CSS. No build step at view time, no network, no fonts to
fetch — these open from the filesystem on a shop-floor laptop.

RTL is handled properly rather than cosmetically:
  * `dir` is set on <html>, so the whole layout mirrors, not just the text.
  * Spacing uses LOGICAL properties (padding-inline-start, border-inline-start),
    which flip automatically. Physical left/right would need a second stylesheet.
  * PLC identifiers stay Latin and are wrapped so they render LTR inside Hebrew
    sentences — otherwise a trailing bracket or colon jumps to the wrong end,
    which is the classic bidi bug in mixed technical text.
"""

import html
import re

# Hebrew block: used to decide whether a cell needs LTR direction.
_HEB = re.compile(r"[֐-׿]")


def has_hebrew(t):
    return bool(_HEB.search(t))


def cell_dir(t):
    """Cells with no Hebrew keep source order; RTL would reverse number runs."""
    return "" if has_hebrew(t) else ' dir="ltr"'


def ltr(t):
    """Isolate a Latin/numeric token inside Hebrew prose."""
    return f'<span class="ltr">{t}</span>' 

# ---------------------------------------------------------------- content DSL


def esc(s):
    return html.escape(str(s), quote=False)


class Block:
    def html(self):
        raise NotImplementedError


def _bi(en, he, tag, cls=""):
    """One block, both languages, each with its own lang/dir."""
    c = f' class="{cls}"' if cls else ""
    return (f'<{tag}{c} lang="en" dir="ltr" data-l="en">{en}</{tag}>'
            f'<{tag}{c} lang="he" dir="rtl" data-l="he">{he}</{tag}>')


class H(Block):
    def __init__(self, en, he, level=2, anchor=None):
        self.en, self.he, self.level, self.anchor = en, he, level, anchor

    def html(self):
        a = f' id="{self.anchor}"' if self.anchor else ""
        t = f"h{self.level}"
        return (f'<div class="hd"{a}>'
                f'<{t} lang="en" dir="ltr" data-l="en">{self.en}</{t}>'
                f'<{t} lang="he" dir="rtl" data-l="he">{self.he}</{t}></div>')


class P(Block):
    def __init__(self, en, he):
        self.en, self.he = en, he

    def html(self):
        return _bi(self.en, self.he, "p")


class UL(Block):
    def __init__(self, items, ordered=False):
        self.items, self.ordered = items, ordered

    def html(self):
        t = "ol" if self.ordered else "ul"
        en = "".join(f"<li>{a}</li>" for a, _ in self.items)
        he = "".join(f"<li>{b}</li>" for _, b in self.items)
        return (f'<{t} lang="en" dir="ltr" data-l="en">{en}</{t}>'
                f'<{t} lang="he" dir="rtl" data-l="he">{he}</{t}>')


class Table(Block):
    """head = [(en, he), ...]; rows = [[(en, he), ...], ...]"""

    def __init__(self, head, rows):
        self.head, self.rows = head, rows

    def _one(self, idx, lang, d):
        # Only the Hebrew rendering needs the per-cell direction fix; the
        # English one already has an LTR base.
        fix = (lambda t: cell_dir(t)) if lang == "he" else (lambda t: "")
        th = "".join(f"<th{fix(h[idx])}>{h[idx]}</th>" for h in self.head)
        tr = "".join("<tr>" + "".join(f"<td{fix(c[idx])}>{c[idx]}</td>"
                                      for c in r) + "</tr>"
                     for r in self.rows)
        return (f'<div class="tw" lang="{lang}" dir="{d}" data-l="{lang}">'
                f"<table><thead><tr>{th}</tr></thead><tbody>{tr}</tbody></table></div>")

    def html(self):
        return self._one(0, "en", "ltr") + self._one(1, "he", "rtl")


class Note(Block):
    """kind: info | warn | danger | ok"""

    def __init__(self, kind, title_en, title_he, body_en, body_he):
        self.kind = kind
        self.te, self.th, self.be, self.bh = title_en, title_he, body_en, body_he

    def html(self):
        return (f'<div class="note {self.kind}">'
                f'<div lang="en" dir="ltr" data-l="en">'
                f"<b>{self.te}</b><p>{self.be}</p></div>"
                f'<div lang="he" dir="rtl" data-l="he">'
                f"<b>{self.th}</b><p>{self.bh}</p></div></div>")


class Steps(Block):
    """Numbered procedure. items = [(en, he), ...]"""

    def __init__(self, items):
        self.items = items

    def html(self):
        def one(idx, lang, d):
            li = "".join(f'<li><div>{s[idx]}</div></li>' for s in self.items)
            return (f'<ol class="steps" lang="{lang}" dir="{d}" data-l="{lang}">'
                    f"{li}</ol>")
        return one(0, "en", "ltr") + one(1, "he", "rtl")


class Raw(Block):
    def __init__(self, h):
        self.h = h

    def html(self):
        return self.h


class Links(Block):
    """A list of documents. Each entry:
         (href, title_en, title_he, desc_en, desc_he, badge_kind, badge_en, badge_he)
    badge_kind: live | ref | archive | data | "" """

    def __init__(self, items):
        self.items = items

    def _one(self, lang, d, ti, di, bi):
        out = [f'<div class="links" lang="{lang}" dir="{d}" data-l="{lang}">']
        for it in self.items:
            href, badge_kind = it[0], it[5]
            badge = it[bi]
            b = (f'<span class="badge {badge_kind}">{badge}</span>'
                 if badge else "")
            out.append(f'<a class="lk" href="{href}">'
                       f'<span class="lk-t">{it[ti]}{b}</span>'
                       f'<span class="lk-d">{it[di]}</span></a>')
        out.append("</div>")
        return "".join(out)

    def html(self):
        return self._one("en", "ltr", 1, 3, 6) + self._one("he", "rtl", 2, 4, 7)


# ------------------------------------------------------------------- chrome

CSS = """
:root{
  --ground:#eef1f2; --surface:#ffffff; --surface-2:#e4e9ea;
  --ink:#131a1e; --ink-2:#44515700; --ink-2:#445157; --ink-3:#6f7c82;
  --rule:#cdd6d8;
  --accent:#0e8a45; --accent-soft:#d8ece0;
  --fault:#c4342c; --fault-soft:#f7dedc;
  --caution:#a8761a; --caution-soft:#f7ecd6;
  --info:#2c6ca8; --info-soft:#dde8f4;
  --mono:ui-monospace,"Cascadia Mono",Consolas,"SF Mono",Menlo,monospace;
  --sans:ui-sans-serif,system-ui,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  --heb:"Segoe UI","Arial Hebrew","Noto Sans Hebrew",Arial,sans-serif;
}
@media (prefers-color-scheme:dark){:root{
  --ground:#141a1f; --surface:#1b2329; --surface-2:#232d34;
  --ink:#e7edef; --ink-2:#a9b7bd; --ink-3:#7d8b92; --rule:#2f3b43;
  --accent:#3fbb75; --accent-soft:#143724;
  --fault:#f2726a; --fault-soft:#3d1d1b;
  --caution:#d9a640; --caution-soft:#3a2c12;
  --info:#6ba7dd; --info-soft:#16283a;
}}
:root[data-theme="dark"]{
  --ground:#141a1f; --surface:#1b2329; --surface-2:#232d34;
  --ink:#e7edef; --ink-2:#a9b7bd; --ink-3:#7d8b92; --rule:#2f3b43;
  --accent:#3fbb75; --accent-soft:#143724;
  --fault:#f2726a; --fault-soft:#3d1d1b;
  --caution:#d9a640; --caution-soft:#3a2c12;
  --info:#6ba7dd; --info-soft:#16283a;
}
:root[data-theme="light"]{
  --ground:#eef1f2; --surface:#ffffff; --surface-2:#e4e9ea;
  --ink:#131a1e; --ink-2:#445157; --ink-3:#6f7c82; --rule:#cdd6d8;
  --accent:#0e8a45; --accent-soft:#d8ece0;
  --fault:#c4342c; --fault-soft:#f7dedc;
  --caution:#a8761a; --caution-soft:#f7ecd6;
  --info:#2c6ca8; --info-soft:#dde8f4;
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--ground);color:var(--ink);
     font:16px/1.65 var(--sans);font-variant-numeric:tabular-nums}
:root[data-lang="he"] body{font-family:var(--heb)}

/* ---- language switching: both languages ship in the DOM ---- */
[data-l="he"]{display:none}
:root[data-lang="he"] [data-l="en"]{display:none}
:root[data-lang="he"] [data-l="he"]{display:revert}

.wrap{max-width:56rem;margin:0 auto;padding:0 1.25rem 5rem}
.bar{position:sticky;top:0;z-index:10;background:var(--ground);
  border-bottom:1px solid var(--rule);padding:.55rem 0;margin-bottom:1.5rem}
.bar .in{max-width:56rem;margin:0 auto;padding:0 1.25rem;display:flex;
  gap:.5rem;align-items:center;flex-wrap:wrap}
.bar .sp{flex:1}
button.sw{background:var(--surface);color:var(--ink-2);border:1px solid var(--rule);
  border-radius:7px;padding:.35rem .7rem;font:.78rem var(--mono);cursor:pointer}
button.sw[aria-pressed="true"]{background:var(--accent-soft);color:var(--accent);
  border-color:var(--accent);font-weight:700}
.docnav a{font:.78rem var(--sans);text-decoration:none;color:var(--ink-2);
  background:var(--surface);border:1px solid var(--rule);border-radius:999px;
  padding:.3rem .75rem;margin-inline-end:.35rem}
.docnav a.here{background:var(--accent-soft);color:var(--accent);
  border-color:var(--accent);font-weight:600}

header.mast{padding:.5rem 0 .5rem}
.eyebrow{font:600 .7rem/1 var(--mono);letter-spacing:.14em;text-transform:uppercase;
  color:var(--accent);margin:0 0 .6rem;direction:ltr;unicode-bidi:isolate;
  text-align:start}
h1{font-size:clamp(1.5rem,4vw,2.15rem);line-height:1.15;margin:0 0 .4rem;
   text-wrap:balance}
.hd h2{font-size:1.2rem;margin:2.2rem 0 .4rem;padding-bottom:.3rem;
  border-bottom:2px solid var(--accent-soft)}
.hd h3{font-size:1rem;margin:1.6rem 0 .3rem}
p{margin:.65rem 0}
ul,ol{margin:.6rem 0;padding-inline-start:1.4rem}
li{margin:.35rem 0}
.ltr{direction:ltr;unicode-bidi:isolate;display:inline-block}
code{font:.86em var(--mono);background:var(--surface-2);padding:.1em .34em;
  border-radius:3px;direction:ltr;unicode-bidi:isolate;white-space:nowrap}
kbd{font:.8em var(--mono);border:1px solid var(--rule);border-bottom-width:2px;
  border-radius:4px;padding:.12em .4em;background:var(--surface);
  direction:ltr;unicode-bidi:isolate}
strong{color:var(--ink)}

.tw{overflow-x:auto;border:1px solid var(--rule);border-radius:9px;
  background:var(--surface);margin:1rem 0}
table{width:100%;border-collapse:collapse;min-width:30rem}
th,td{text-align:start;padding:.55rem .7rem;border-bottom:1px solid var(--rule);
  vertical-align:top;font-size:.9rem}
th{background:var(--surface-2);font:600 .72rem/1.35 var(--mono);
  letter-spacing:.06em;text-transform:uppercase;color:var(--ink-2)}
:root[data-lang="he"] th{font-family:var(--heb);text-transform:none;
  letter-spacing:0;font-size:.8rem}
tr:last-child td{border-bottom:0}

.note{margin:1.2rem 0;padding:.85rem 1.1rem;border-radius:9px;
  background:var(--surface);border:1px solid var(--rule);
  border-inline-start:5px solid var(--info);font-size:.93rem}
.note.info{border-inline-start-color:var(--info);background:var(--info-soft)}
.note.ok{border-inline-start-color:var(--accent);background:var(--accent-soft)}
.note.warn{border-inline-start-color:var(--caution);background:var(--caution-soft)}
.note.danger{border-inline-start-color:var(--fault);background:var(--fault-soft)}
.note b{display:block;margin-bottom:.2rem}
.note p{margin:.3rem 0 0;color:var(--ink-2)}

ol.steps{list-style:none;padding-inline-start:0;counter-reset:s}
ol.steps>li{counter-increment:s;position:relative;
  padding-inline-start:2.6rem;margin:.85rem 0;min-height:1.9rem}
ol.steps>li::before{content:counter(s);position:absolute;inset-inline-start:0;
  top:0;width:1.85rem;height:1.85rem;border-radius:50%;
  background:var(--accent-soft);color:var(--accent);
  font:700 .85rem/1.85rem var(--mono);text-align:center}

.lamp{display:inline-block;width:.85rem;height:.85rem;border-radius:50%;
  margin-inline-end:.4rem;vertical-align:-.1em;border:1px solid rgba(0,0,0,.25)}
.lamp.g{background:#2ecc71}.lamp.r{background:#e74c3c}
.lamp.o{background:#e8a33d}.lamp.off{background:var(--surface-2)}
.pb{display:inline-block;font:700 .74rem var(--mono);border-radius:5px;
  padding:.16em .45em;border:1px solid rgba(0,0,0,.2);direction:ltr;
  unicode-bidi:isolate;white-space:nowrap}
.pb.r{background:#e74c3c;color:#fff}
.pb.o{background:#e8a33d;color:#3a2600}
.pb.g{background:#2ecc71;color:#04361b}

.links{display:grid;gap:.6rem;margin:1rem 0}
a.lk{display:block;text-decoration:none;background:var(--surface);
  border:1px solid var(--rule);border-radius:10px;padding:.7rem .9rem;
  border-inline-start:4px solid var(--rule)}
a.lk:hover{border-color:var(--accent);border-inline-start-color:var(--accent)}
.lk-t{display:block;color:var(--ink);font-weight:600;font-size:.97rem}
.lk-d{display:block;color:var(--ink-3);font-size:.85rem;margin-top:.15rem}
.badge{display:inline-block;margin-inline-start:.5rem;font:700 .62rem/1 var(--mono);
  letter-spacing:.08em;text-transform:uppercase;padding:.25em .45em;
  border-radius:4px;vertical-align:.1em}
:root[data-lang="he"] .badge{font-family:var(--heb);text-transform:none;
  letter-spacing:0;font-size:.68rem}
.badge.live{background:var(--accent-soft);color:var(--accent)}
.badge.ref{background:var(--info-soft);color:var(--info)}
.badge.archive{background:var(--surface-2);color:var(--ink-3)}
.badge.data{background:var(--caution-soft);color:var(--caution)}

footer{margin-top:3rem;padding-top:1.2rem;border-top:1px solid var(--rule);
  color:var(--ink-3);font-size:.8rem}
@media print{
  .bar{display:none} body{background:#fff}
  .note,.tw{break-inside:avoid}
}
"""

JS = """
(function(){
  var r=document.documentElement;
  var tb=document.getElementById('tg'), lb=document.getElementById('lg');

  function applyLang(l){
    r.setAttribute('data-lang', l);
    r.setAttribute('lang', l);
    // dir on <html> so the whole layout mirrors, not only the text
    r.setAttribute('dir', l === 'he' ? 'rtl' : 'ltr');
    lb.setAttribute('aria-pressed', l === 'he' ? 'true' : 'false');
    lb.textContent = l === 'he' ? 'אנגלית / EN' : 'עברית / HE';
  }
  function applyTheme(t){
    if(t){ r.setAttribute('data-theme', t); } else { r.removeAttribute('data-theme'); }
    tb.textContent = 'theme: ' + (t || 'auto');
    tb.setAttribute('aria-pressed', t ? 'true' : 'false');
  }

  tb.addEventListener('click', function(){
    var cur = r.getAttribute('data-theme');
    var next = cur === 'dark' ? 'light' : (cur === 'light' ? null : 'dark');
    try{ next ? localStorage.setItem('mnTheme', next)
              : localStorage.removeItem('mnTheme'); }catch(e){}
    applyTheme(next);
  });
  lb.addEventListener('click', function(){
    var next = r.getAttribute('data-lang') === 'he' ? 'en' : 'he';
    try{ localStorage.setItem('mnLang', next); }catch(e){}
    applyLang(next);
  });

  var t=null, l='en';
  try{ t = localStorage.getItem('mnTheme'); l = localStorage.getItem('mnLang') || 'en'; }catch(e){}
  applyTheme(t); applyLang(l);
})();
"""

DOCS = [("index.html", "All docs", "כל המסמכים"),
        ("operator-manual.html", "Operator", "מדריך מפעיל"),
        ("technician-manual.html", "Technician", "מדריך טכנאי"),
        ("auto-state-machine-current.html", "State machine", "מכונת מצבים")]


def page(here, title_en, title_he, lede_en, lede_he, blocks,
         eyebrow="167_01 Saad — Flower"):
    nav = []
    for fn, en, he in DOCS:
        cls = ' class="here"' if fn == here else ""
        nav.append(f'<a href="{fn}"{cls}>'
                   f'<span data-l="en">{en}</span>'
                   f'<span data-l="he">{he}</span></a>')
    body = "\n".join(b.html() for b in blocks)
    return "\n".join([
        "<!DOCTYPE html>",
        '<html lang="en" dir="ltr" data-lang="en">',
        "<head>", '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>{esc(title_en)} — {esc(title_he)}</title>",
        f"<style>{CSS}</style>", "</head>", "<body>",
        '<div class="bar"><div class="in">',
        f'<span class="docnav">{"".join(nav)}</span>',
        '<span class="sp"></span>',
        '<button class="sw" id="lg" type="button" aria-pressed="false">עברית / HE</button>',
        '<button class="sw" id="tg" type="button" aria-pressed="false">theme: auto</button>',
        "</div></div>",
        '<div class="wrap">',
        '<header class="mast">',
        f'<p class="eyebrow" dir="ltr">{esc(eyebrow)}</p>',
        f'<h1 lang="en" dir="ltr" data-l="en">{title_en}</h1>',
        f'<h1 lang="he" dir="rtl" data-l="he">{title_he}</h1>',
        f'<p lang="en" dir="ltr" data-l="en">{lede_en}</p>',
        f'<p lang="he" dir="rtl" data-l="he">{lede_he}</p>',
        "</header>", body,
        '<footer><span data-l="en" dir="ltr">Generated by '
        '<code>scripts/manuals/build_manuals.py</code>. Both languages ship in '
        'this file — no network needed.</span>'
        '<span data-l="he" dir="rtl">נוצר על ידי '
        '<code>scripts/manuals/build_manuals.py</code>. שתי השפות כלולות בקובץ '
        'זה — אין צורך בחיבור לרשת.</span></footer>',
        "</div>", f"<script>{JS}</script>", "</body>", "</html>",
    ])
