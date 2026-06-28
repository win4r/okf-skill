"""okf_graph — turn an OKF bundle into a link graph (JSON, Mermaid, or self-contained HTML).

The HTML output is a single offline file: an interactive force-directed graph rendered with
vanilla JS + SVG, no backend, no CDN, no build step. Nodes are concepts colored by ``type``;
edges are cross-links (dashed = broken target).
"""
from __future__ import annotations

import json
import os
import posixpath
import re
import sys
from typing import Dict, List, Optional

import okf_core as core


def build_graph(bundle: core.Bundle) -> Dict[str, object]:
    ids = {d.rel_path for d in bundle.documents}
    nodes = []
    node_index = {}
    for doc in sorted(bundle.concepts, key=lambda d: d.rel_path):
        fm = doc.frontmatter or {}
        node_index[doc.rel_path] = len(nodes)
        nodes.append({
            "id": doc.concept_id,
            "path": doc.rel_path,
            "title": (fm.get("title") if isinstance(fm.get("title"), str) else None) or doc.concept_id,
            "type": fm.get("type") if isinstance(fm.get("type"), str) else "untyped",
            "tags": fm.get("tags") if isinstance(fm.get("tags"), list) else [],
        })

    edges = []
    for doc in bundle.concepts:
        for link in doc.links:
            if link.is_external or link.is_anchor_only or not link.anchorless.endswith(".md"):
                continue
            target = link.anchorless
            if link.is_absolute:
                resolved = posixpath.normpath(target.lstrip("/"))
            else:
                base = posixpath.dirname(doc.rel_path)
                resolved = posixpath.normpath(posixpath.join(base, target))
            edges.append({
                "source": doc.rel_path,
                "target": resolved,
                "broken": resolved not in ids,
            })
    return {"nodes": nodes, "edges": edges}


def _mermaid_label(text: str) -> str:
    # mermaid node labels are fragile around quotes and brackets; neutralize them.
    return text.replace('"', "'").replace("[", "(").replace("]", ")")


def to_mermaid(graph) -> str:
    lines = ["graph LR"]
    alias = {}
    for i, n in enumerate(graph["nodes"]):
        a = "n%d" % i
        alias[n["path"]] = a
        lines.append('  %s["%s"]' % (a, _mermaid_label(n["title"])))
    # Deterministically id each missing (dangling) target; define each node exactly once.
    missing = {}
    for e in graph["edges"]:
        if e["target"] not in alias and e["target"] not in missing:
            mid = "m%d" % len(missing)
            missing[e["target"]] = mid
            lines.append('  %s["%s (missing)"]:::broken' % (mid, _mermaid_label(e["target"])))
    for e in graph["edges"]:
        src = alias.get(e["source"])
        if src is None:
            continue
        tgt = alias.get(e["target"]) or missing.get(e["target"])
        arrow = "-.->" if e["broken"] else "-->"
        lines.append("  %s %s %s" % (src, arrow, tgt))
    lines.append("  classDef broken stroke-dasharray: 4 4,stroke:#c00;")
    return "\n".join(lines)


HTML_TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>__TITLE__</title>
<style>
  :root { color-scheme: light dark; }
  body { margin:0; font:13px/1.4 system-ui,sans-serif; background:#0f1117; color:#e6e6e6; }
  #bar { position:fixed; top:0; left:0; right:0; padding:8px 12px; background:#171a23;
         border-bottom:1px solid #2a2f3a; display:flex; gap:12px; align-items:center; z-index:10; }
  #bar b { font-size:14px; } #bar input { background:#0f1117; color:#e6e6e6; border:1px solid #2a2f3a;
         border-radius:6px; padding:4px 8px; } #legend { display:flex; gap:10px; flex-wrap:wrap; }
  .lg { display:flex; gap:4px; align-items:center; } .sw { width:12px; height:12px; border-radius:3px; }
  svg { position:fixed; top:42px; left:0; width:100vw; height:calc(100vh - 42px); }
  .edge { stroke:#3a4252; stroke-width:1.2px; } .edge.broken { stroke:#d9534f; stroke-dasharray:4 4; }
  .node circle { stroke:#0f1117; stroke-width:1.5px; cursor:grab; }
  .node text { fill:#cfd6e4; pointer-events:none; font-size:11px; }
  .node.dim { opacity:0.15; } .edge.dim { opacity:0.05; }
  #tip { position:fixed; pointer-events:none; background:#000c; border:1px solid #2a2f3a; padding:6px 8px;
         border-radius:6px; max-width:300px; display:none; z-index:20; }
</style></head>
<body>
<div id="bar"><b>__TITLE__</b>
  <input id="q" placeholder="filter nodes…" autocomplete="off">
  <span id="counts"></span><div id="legend"></div>
</div>
<svg id="g"></svg><div id="tip"></div>
<script>
const DATA = __DATA__;
const PALETTE = ["#6ab0ff","#7ee787","#ffa657","#d2a8ff","#ff7b72","#79c0ff","#f2cc60","#56d4dd","#ff9bce","#a5d6ff"];
const types = [...new Set(DATA.nodes.map(n=>n.type))].sort();
const color = t => PALETTE[types.indexOf(t) % PALETTE.length];
const byPath = new Map(DATA.nodes.map((n,i)=>[n.path,i]));
const svg = document.getElementById('g');
let W = svg.clientWidth, H = svg.clientHeight;
const nodes = DATA.nodes.map((n,i)=>({...n, x: W/2 + Math.cos(i)*120 + (i%7)*9, y: H/2 + Math.sin(i)*120 + (i%5)*9, vx:0, vy:0}));
const links = DATA.edges.map(e=>({...e, s: byPath.get(e.source), t: e.target!==undefined?byPath.get(e.target):undefined}))
                        .filter(l=>l.s!==undefined);
const NS='http://www.w3.org/2000/svg';
const gEdges=document.createElementNS(NS,'g'), gNodes=document.createElementNS(NS,'g');
svg.append(gEdges,gNodes);
const edgeEls = links.map(l=>{const e=document.createElementNS(NS,'line'); e.setAttribute('class','edge'+(l.broken?' broken':'')); gEdges.append(e); return e;});
const nodeEls = nodes.map((n,i)=>{
  const g=document.createElementNS(NS,'g'); g.setAttribute('class','node');
  const c=document.createElementNS(NS,'circle'); const deg=links.filter(l=>l.s===i||l.t===i).length;
  c.setAttribute('r', 5 + Math.min(deg,8)); c.setAttribute('fill', color(n.type));
  const tx=document.createElementNS(NS,'text'); tx.setAttribute('x',9); tx.setAttribute('y',4); tx.textContent=n.title;
  g.append(c,tx); gNodes.append(g);
  g.addEventListener('mousemove',ev=>showTip(ev,n)); g.addEventListener('mouseleave',hideTip);
  g.addEventListener('mousedown',ev=>startDrag(ev,i));
  return g;
});
function showTip(ev,n){const t=document.getElementById('tip'); t.style.display='block';
  t.style.left=(ev.clientX+12)+'px'; t.style.top=(ev.clientY+12)+'px';
  t.innerHTML='<b>'+esc(n.title)+'</b><br>type: '+esc(n.type)+'<br>'+esc(n.path)+(n.tags&&n.tags.length?'<br>tags: '+n.tags.map(esc).join(', '):'');}
function hideTip(){document.getElementById('tip').style.display='none';}
function esc(s){return String(s).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));}
let drag=null;
function startDrag(ev,i){drag={i,fx:true}; nodes[i].fixed=true; ev.preventDefault();}
window.addEventListener('mousemove',ev=>{if(drag){const r=svg.getBoundingClientRect(); nodes[drag.i].x=ev.clientX-r.left; nodes[drag.i].y=ev.clientY-r.top; nodes[drag.i].vx=nodes[drag.i].vy=0;}});
window.addEventListener('mouseup',()=>{if(drag){nodes[drag.i].fixed=false; drag=null;}});
function tick(){
  for(let a=0;a<nodes.length;a++)for(let b=a+1;b<nodes.length;b++){
    let dx=nodes[a].x-nodes[b].x, dy=nodes[a].y-nodes[b].y, d2=dx*dx+dy*dy||1, f=900/d2;
    let d=Math.sqrt(d2); dx/=d; dy/=d; nodes[a].vx+=dx*f; nodes[a].vy+=dy*f; nodes[b].vx-=dx*f; nodes[b].vy-=dy*f;
  }
  for(const l of links){if(l.t===undefined)continue; const s=nodes[l.s],t=nodes[l.t];
    let dx=t.x-s.x, dy=t.y-s.y, d=Math.sqrt(dx*dx+dy*dy)||1, f=(d-90)*0.01;
    dx/=d; dy/=d; s.vx+=dx*f; s.vy+=dy*f; t.vx-=dx*f; t.vy-=dy*f;}
  for(const n of nodes){ n.vx+=(W/2-n.x)*0.0008; n.vy+=(H/2-n.y)*0.0008;
    if(!n.fixed){ n.x+=(n.vx*=0.85); n.y+=(n.vy*=0.85);} }
  for(let i=0;i<nodeEls.length;i++) nodeEls[i].setAttribute('transform',`translate(${nodes[i].x},${nodes[i].y})`);
  for(let i=0;i<edgeEls.length;i++){const l=links[i],s=nodes[l.s],t=l.t!==undefined?nodes[l.t]:s;
    edgeEls[i].setAttribute('x1',s.x);edgeEls[i].setAttribute('y1',s.y);edgeEls[i].setAttribute('x2',t.x);edgeEls[i].setAttribute('y2',t.y);}
  requestAnimationFrame(tick);
}
tick();
document.getElementById('counts').textContent = DATA.nodes.length+' concepts · '+DATA.edges.length+' links';
const lg=document.getElementById('legend');
types.forEach(t=>{const d=document.createElement('div'); d.className='lg';
  d.innerHTML='<span class="sw" style="background:'+color(t)+'"></span>'+esc(t); lg.append(d);});
document.getElementById('q').addEventListener('input',e=>{const q=e.target.value.toLowerCase();
  nodes.forEach((n,i)=>{const hit=!q||(n.title+' '+n.type+' '+n.path).toLowerCase().includes(q);
    nodeEls[i].classList.toggle('dim',!hit);});
  links.forEach((l,i)=>{const hit=!q||(nodes[l.s].title.toLowerCase().includes(q)); edgeEls[i].classList.toggle('dim',!!q&&!hit);});});
window.addEventListener('resize',()=>{W=svg.clientWidth;H=svg.clientHeight;});
</script></body></html>
"""


def _json_for_script(obj) -> str:
    """JSON safe to embed inside a <script> block: neutralize '</script>' breakout and the
    U+2028/U+2029 line separators that are invalid in JS string literals. The escapes are
    still valid JSON, so the data round-trips intact."""
    return (json.dumps(obj, ensure_ascii=False)
            .replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
            .replace(" ", "\\u2028").replace(" ", "\\u2029"))


def to_html(graph, title: str) -> str:
    subs = {"__DATA__": _json_for_script(graph), "__TITLE__": _esc(title)}
    # Single pass over the template so inserted values are never re-scanned for markers
    # (a concept literally named "__DATA__" cannot corrupt the output).
    return re.sub("__DATA__|__TITLE__", lambda m: subs[m.group(0)], HTML_TEMPLATE)


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def run(args) -> int:
    bundle = core.load_bundle(args.path)
    graph = build_graph(bundle)
    title = args.title or os.path.basename(os.path.abspath(args.path)) or "OKF Bundle"

    if args.format == "json":
        out = json.dumps(graph, indent=2, ensure_ascii=False)
    elif args.format == "mermaid":
        out = to_mermaid(graph)
    else:
        out = to_html(graph, title)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(out)
        print(f"wrote {args.output} ({len(graph['nodes'])} nodes, {len(graph['edges'])} edges)")
    else:
        print(out)
    return 0


def add_arguments(parser):
    parser.add_argument("path", help="Path to the OKF bundle root")
    parser.add_argument("--format", choices=["html", "json", "mermaid"], default="html")
    parser.add_argument("--output", "-o", help="Write to file instead of stdout")
    parser.add_argument("--title", default="")


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(prog="okf graph", description=__doc__)
    add_arguments(parser)
    args = parser.parse_args(argv)
    try:
        return run(args)
    except Exception as e:  # noqa: BLE001
        print(f"okf graph: error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
