"""Renders pb_test_procedure results to a self-contained HTML report.

Palette and theme handling deliberately match docs/bench-checklist-arming.html
so the two documents read as one set.
"""

import html


def _esc(s):
    return html.escape(str(s), quote=True)


CSS = """
:root {
  --ground:#eef1f2; --surface:#ffffff; --surface-2:#e4e9ea;
  --ink:#131a1e; --ink-2:#4a575d; --ink-3:#6f7c82; --rule:#cdd6d8;
  --accent:#0e8a45; --accent-soft:#d8ece0;
  --fault:#c4342c; --fault-soft:#f7dedc;
  --caution:#a8761a; --caution-soft:#f7ecd6;
  --mono: ui-monospace,"Cascadia Mono","Cascadia Code",Consolas,"SF Mono",Menlo,monospace;
  --sans: ui-sans-serif,system-ui,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
}
@media (prefers-color-scheme: dark) {
  :root {
    --ground:#141a1f; --surface:#1b2329; --surface-2:#232d34;
    --ink:#e7edef; --ink-2:#a9b7bd; --ink-3:#7d8b92; --rule:#2f3b43;
    --accent:#3fbb75; --accent-soft:#143724;
    --fault:#f2726a; --fault-soft:#3d1d1b;
    --caution:#d9a640; --caution-soft:#3a2c12;
  }
}
:root[data-theme="dark"] {
  --ground:#141a1f; --surface:#1b2329; --surface-2:#232d34;
  --ink:#e7edef; --ink-2:#a9b7bd; --ink-3:#7d8b92; --rule:#2f3b43;
  --accent:#3fbb75; --accent-soft:#143724;
  --fault:#f2726a; --fault-soft:#3d1d1b;
  --caution:#d9a640; --caution-soft:#3a2c12;
}
:root[data-theme="light"] {
  --ground:#eef1f2; --surface:#ffffff; --surface-2:#e4e9ea;
  --ink:#131a1e; --ink-2:#4a575d; --ink-3:#6f7c82; --rule:#cdd6d8;
  --accent:#0e8a45; --accent-soft:#d8ece0;
  --fault:#c4342c; --fault-soft:#f7dedc;
  --caution:#a8761a; --caution-soft:#f7ecd6;
}
* { box-sizing:border-box; }
html { -webkit-text-size-adjust:100%; }
body { margin:0; background:var(--ground); color:var(--ink);
       font:16px/1.6 var(--sans); font-variant-numeric:tabular-nums; }
.wrap { max-width:66rem; margin:0 auto; padding:0 1.25rem 5rem; }
header.mast { padding:2.5rem 0 1rem; }
.eyebrow { font:600 .7rem/1 var(--mono); letter-spacing:.14em;
           text-transform:uppercase; color:var(--accent); margin:0 0 .75rem; }
h1 { font-size:clamp(1.55rem,4vw,2.2rem); line-height:1.15; margin:0 0 .5rem;
     text-wrap:balance; letter-spacing:-.01em; }
.sub { color:var(--ink-2); margin:0; max-width:64ch; }
.meta { display:flex; flex-wrap:wrap; gap:.4rem 1.5rem; margin-top:1.1rem;
        font:.76rem/1.5 var(--mono); color:var(--ink-3); }
.meta b { color:var(--ink-2); font-weight:600; }

.verdict { display:flex; flex-wrap:wrap; align-items:center; gap:1rem;
  margin:1.5rem 0 2rem; padding:1.1rem 1.3rem; border-radius:10px;
  background:var(--surface); border:1px solid var(--rule);
  border-left:5px solid var(--accent); }
.verdict.bad { border-left-color:var(--fault); }
.tally { font:700 1.9rem/1 var(--mono); letter-spacing:-.02em; }
.tally .of { color:var(--ink-3); font-weight:400; font-size:1.1rem; }
.verdict p { margin:0; color:var(--ink-2); font-size:.92rem; max-width:58ch; }

.theme { position:fixed; top:.9rem; right:.9rem; z-index:5;
  background:var(--surface); color:var(--ink-2); border:1px solid var(--rule);
  border-radius:7px; padding:.35rem .6rem; font:.72rem var(--mono);
  cursor:pointer; }

section.grp { margin:0 0 2.25rem; }
h2 { font-size:1.06rem; margin:0 0 .3rem; letter-spacing:-.005em; }
h2 .gid { font:700 .74rem var(--mono); color:var(--accent);
          padding:.15rem .45rem; border-radius:4px;
          background:var(--accent-soft); margin-right:.55rem;
          vertical-align:.08em; }
.gnote { margin:0 0 .85rem; color:var(--ink-3); font-size:.86rem;
         max-width:70ch; }

.tblwrap { overflow-x:auto; border:1px solid var(--rule); border-radius:9px;
           background:var(--surface); }
table { width:100%; border-collapse:collapse; min-width:44rem; }
th, td { text-align:left; padding:.55rem .7rem; border-bottom:1px solid var(--rule);
         vertical-align:top; font-size:.86rem; }
th { background:var(--surface-2); font:600 .7rem/1.3 var(--mono);
     letter-spacing:.07em; text-transform:uppercase; color:var(--ink-2);
     white-space:nowrap; }
tr:last-child td { border-bottom:0; }
td.cid { font:600 .8rem var(--mono); color:var(--ink-3); white-space:nowrap; }
td.val { font:.78rem/1.45 var(--mono); color:var(--ink-2); }
.pill { display:inline-block; font:700 .68rem/1 var(--mono); letter-spacing:.06em;
        padding:.3rem .45rem; border-radius:4px; }
.pill.PASS { color:var(--accent); background:var(--accent-soft); }
.pill.FAIL { color:var(--fault); background:var(--fault-soft); }
tr.fail td { background:var(--fault-soft); }
.ev { display:block; margin-top:.3rem; font:.72rem/1.4 var(--mono);
      color:var(--ink-3); word-break:break-word; }
.ev.trace { letter-spacing:.02em; color:var(--accent); }

.logbox { border:1px solid var(--rule); border-radius:9px; background:var(--surface);
          overflow-x:auto; }
.logbox table { min-width:34rem; }
.sev-ERR { color:var(--fault); font-weight:700; }
.sev-WARN { color:var(--caution); font-weight:700; }
.sev-INFO { color:var(--ink-3); }
.sev-DBG { color:var(--ink-3); opacity:.7; }

.callout { margin:1.5rem 0; padding:1rem 1.2rem; border-radius:9px;
  background:var(--caution-soft); border:1px solid var(--rule);
  border-left:5px solid var(--caution); font-size:.9rem; }
.callout h3 { margin:0 0 .4rem; font-size:.94rem; }
.callout p { margin:.45rem 0 0; color:var(--ink-2); }
code { font:.86em var(--mono); background:var(--surface-2);
       padding:.1em .32em; border-radius:3px; }
footer { margin-top:3rem; padding-top:1.2rem; border-top:1px solid var(--rule);
         color:var(--ink-3); font-size:.8rem; }
"""

JS = """
(function(){
  var r=document.documentElement,b=document.getElementById('t');
  function lbl(){var m=r.getAttribute('data-theme');
    b.textContent=m?('theme: '+m):'theme: auto';}
  b.addEventListener('click',function(){
    var m=r.getAttribute('data-theme');
    var next=m==='dark'?'light':(m==='light'?null:'dark');
    if(next){r.setAttribute('data-theme',next);}else{r.removeAttribute('data-theme');}
    try{next?localStorage.setItem('pbtheme',next):localStorage.removeItem('pbtheme');}catch(e){}
    lbl();});
  try{var s=localStorage.getItem('pbtheme'); if(s){r.setAttribute('data-theme',s);}}catch(e){}
  lbl();
})();
"""


def write_report(payload, out_path):
    env = payload["env"]
    res = payload["results"]
    summ = payload["summary"]
    bad = summ["fail"] > 0

    # group in first-seen order
    order, groups = [], {}
    for r in res:
        if r["group"] not in groups:
            order.append(r["group"])
            groups[r["group"]] = {"title": r["group_title"],
                                  "note": r["group_note"], "rows": []}
        groups[r["group"]]["rows"].append(r)

    p = []
    p.append("<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">")
    p.append('<meta name="viewport" content="width=device-width, initial-scale=1">')
    p.append("<title>167_01 Push-Button Test Report</title>")
    p.append(f"<style>{CSS}</style>\n</head>\n<body>")
    p.append('<button class="theme" id="t">theme: auto</button>')
    p.append('<div class="wrap">')

    p.append('<header class="mast">')
    p.append('<p class="eyebrow">167_01 Saad — Flower · panel hardware</p>')
    p.append("<h1>Push-button test report</h1>")
    p.append('<p class="sub">Every documented behaviour of the three panel '
             'push buttons and their LEDs, exercised against a live PLC over '
             'ADS. Presses are simulated by writing the raw input channels '
             '<code>GVL_IO.dIn[13..15]</code>; every other value is read back '
             'from the PLC, including the solenoid coil outputs.</p>')
    p.append('<div class="meta">')
    for k, v in [("run", f"{env['started']} → {env.get('finished','?')}"),
                 ("target", f"{env['net_id']}:{env['ams_port']}"),
                 ("host", env["host"]), ("python", env["python"]),
                 ("state on entry", f"{env['step_at_entry']}, "
                                    f"bAutoMode={env['auto_at_entry']}"),
                 ("state on exit", f"{env.get('step_at_exit','?')}, "
                                   f"bAutoMode={env.get('auto_at_exit','?')}")]:
        p.append(f"<span><b>{_esc(k)}</b> {_esc(v)}</span>")
    p.append("</div></header>")

    p.append(f'<div class="verdict{" bad" if bad else ""}">')
    p.append(f'<div class="tally">{summ["pass"]}<span class="of"> / '
             f'{summ["total"]}</span></div>')
    if bad:
        p.append(f"<p><strong>{summ['fail']} check(s) failed.</strong> "
                 "Failing rows are highlighted below.</p>")
    else:
        p.append("<p>All checks passed. This covers the LED wiring, the three "
                 "Manual jogs, the un-armed and armed Automatic states, the "
                 "ERR jog window, and recovery — including the negative cases, "
                 "which are the ones that prove the gates actually gate.</p>")
    p.append("</div>")

    p.append('<div class="callout">')
    p.append("<h3>What this run cannot tell you</h3>")
    p.append("<p><strong>No physical I/O.</strong> The EtherCAT device is "
             "disabled on this bench target, so a &ldquo;press&rdquo; is a "
             "memory write and a &ldquo;coil&rdquo; is a memory read. The "
             "button contacts, the LED lamps, the valve wiring and the air "
             "circuit are all still unverified — that is field checks FLD1 "
             "&ndash; FLD4 in <code>docs/bench-checklist-arming.html</code>.</p>")
    p.append("<p><strong>The ERR jog window is wider here than on the "
             "machine.</strong> This run disables <code>GVL_Robot.bTcpEnable</code>, "
             "so nothing answers <code>STATE:99</code> with <code>CMD:2</code> and "
             "ERR stays latched indefinitely. With a live robot the PLC clears "
             "the fault and homes about a second after entering ERR, so group E "
             "proves the jog <em>works</em>, not that an operator will get the "
             "chance to use it.</p>")
    p.append("</div>")

    for gid in order:
        g = groups[gid]
        p.append('<section class="grp">')
        p.append(f'<h2><span class="gid">{_esc(gid)}</span>{_esc(g["title"])}</h2>')
        if g["note"]:
            p.append(f'<p class="gnote">{_esc(g["note"])}</p>')
        p.append('<div class="tblwrap"><table><thead><tr>'
                 "<th>#</th><th>Check</th><th>Expected</th><th>Observed</th>"
                 "<th>Result</th></tr></thead><tbody>")
        for r in g["rows"]:
            cls = ' class="fail"' if r["status"] == "FAIL" else ""
            ev = ""
            if r["evidence"]:
                trace = set(r["evidence"]) <= {"#", "."} and len(r["evidence"]) > 4
                ev = (f'<span class="ev{" trace" if trace else ""}">'
                      f'{_esc(r["evidence"])}</span>')
            p.append(f"<tr{cls}><td class=\"cid\">{_esc(r['id'])}</td>"
                     f"<td>{_esc(r['what'])}{ev}</td>"
                     f"<td class=\"val\">{_esc(r['expected'])}</td>"
                     f"<td class=\"val\">{_esc(r['actual'])}</td>"
                     f"<td><span class=\"pill {r['status']}\">{r['status']}</span></td></tr>")
        p.append("</tbody></table></div></section>")

    if payload.get("log_tail"):
        p.append('<section class="grp">')
        p.append('<h2><span class="gid">LOG</span>PLC event ring at end of run</h2>')
        p.append('<p class="gnote">Newest first, straight from '
                 "<code>GVL_Log.aRecent[0..19]</code> — the same 20 entries the "
                 "panel&rsquo;s Log page shows. Timestamps come from the panel "
                 "RTC.</p>")
        p.append('<div class="logbox"><table><thead><tr><th>Sev</th>'
                 "<th>Time</th><th>Message</th></tr></thead><tbody>")
        for e in payload["log_tail"]:
            if not (e["msg"] or e["time"]):
                continue
            sev = e["sev"].strip() or "—"
            p.append(f'<tr><td class="sev-{_esc(sev)}">{_esc(sev)}</td>'
                     f'<td class="val">{_esc(e["time"])}</td>'
                     f"<td>{_esc(e['msg'])}</td></tr>")
        p.append("</tbody></table></div></section>")

    p.append("<footer>Generated by "
             "<code>scripts/pb_test/pb_test_procedure.py</code>. Raw results in "
             "<code>scripts/pb_test/last_run.json</code>. Channel map authority: "
             "<code>docs/167_01_SAAD_PinPush_IO_List.xlsx</code> (sheet IO, "
             "column NEW).</footer>")
    p.append(f"</div>\n<script>{JS}</script>\n</body>\n</html>")

    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(p))
