#!/usr/bin/env python3
"""
Generates docs/index.html from translation_audit.json.
Run automatically by the GitHub Actions workflow after each crawl.
"""

import json
import os
from datetime import datetime

INPUT_JSON  = "translation_audit.json"
OUTPUT_HTML = os.path.join("docs", "index.html")

def load_data(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)

def status_badge(status):
    badges = {
        "fully_translated":    ('<span class="badge full">Fully translated</span>', "full"),
        "partially_translated":('<span class="badge partial">Partial</span>', "partial"),
        "not_translated":      ('<span class="badge none">Not translated</span>', "none"),
        "error":               ('<span class="badge error">Error / 404</span>', "error"),
    }
    return badges.get(status, ('<span class="badge error">Unknown</span>', "error"))

def make_html(data):
    pages    = data.get("pages", [])
    gen_at   = data.get("generated_at", "")
    base_url = data.get("base_url", "")

    try:
        dt = datetime.fromisoformat(gen_at.replace("Z", "+00:00"))
        generated = dt.strftime("%-d %B %Y at %H:%M UTC")
    except Exception:
        generated = gen_at

    counts = {"fully_translated": 0, "partially_translated": 0, "not_translated": 0, "error": 0}
    for p in pages:
        counts[p.get("translation_status", "error")] = counts.get(p.get("translation_status", "error"), 0) + 1

    rows_json = json.dumps([{
        "status":  p.get("translation_status", "error"),
        "url":     p.get("final_url", ""),
        "title":   p.get("title", ""),
        "found":   ", ".join(p.get("translated_languages", [])) if isinstance(p.get("translated_languages"), list) else p.get("translated_languages", ""),
        "missing": ", ".join(p.get("missing_languages", [])) if isinstance(p.get("missing_languages"), list) else p.get("missing_languages", ""),
    } for p in pages], ensure_ascii=False)

    total = len(pages)
    pct_full    = round(counts["fully_translated"]    / total * 100) if total else 0
    pct_partial = round(counts["partially_translated"]/ total * 100) if total else 0
    pct_none    = round(counts["not_translated"]      / total * 100) if total else 0

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Translation Audit — {base_url}</title>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f5f5f0;color:#1a1a1a;font-size:15px;line-height:1.6}}
  header{{background:#fff;border-bottom:1px solid #e5e5e0;padding:1.25rem 2rem;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px}}
  header h1{{font-size:18px;font-weight:600;color:#1a1a1a}}
  header .meta{{font-size:13px;color:#888}}
  .inner{{max-width:1100px;margin:0 auto;padding:1.5rem 1.5rem}}
  .summary{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin-bottom:1.5rem}}
  .card{{background:#fff;border:1px solid #e5e5e0;border-radius:10px;padding:1rem 1.25rem;text-align:center}}
  .card .num{{font-size:30px;font-weight:600;margin-top:4px}}
  .card .lbl{{font-size:12px;color:#888;text-transform:uppercase;letter-spacing:.04em}}
  .green{{color:#2d7a2d}}.amber{{color:#b06000}}.red{{color:#c0392b}}.gray{{color:#888}}
  .bars{{background:#fff;border:1px solid #e5e5e0;border-radius:10px;padding:1.25rem 1.5rem;margin-bottom:1.5rem}}
  .bar-row{{display:flex;align-items:center;gap:10px;margin-bottom:8px}}
  .bar-row:last-child{{margin-bottom:0}}
  .bar-label{{font-size:13px;color:#666;width:100px;flex-shrink:0}}
  .bar-track{{flex:1;height:14px;background:#f0f0eb;border-radius:99px;overflow:hidden}}
  .bar-fill{{height:100%;border-radius:99px;transition:width .5s ease}}
  .bar-val{{font-size:13px;font-weight:600;width:36px;text-align:right}}
  .controls{{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:1rem}}
  .pill{{font-size:13px;padding:5px 14px;border-radius:99px;border:1px solid #ddd;background:#fff;cursor:pointer;color:#555;transition:all .15s}}
  .pill:hover{{background:#f0f0eb}}
  .pill.active{{background:#1a1a1a;color:#fff;border-color:#1a1a1a}}
  input[type=text]{{font-size:13px;padding:6px 12px;border-radius:8px;border:1px solid #ddd;width:240px;outline:none}}
  input[type=text]:focus{{border-color:#888}}
  .table-wrap{{background:#fff;border:1px solid #e5e5e0;border-radius:10px;overflow:hidden}}
  table{{width:100%;border-collapse:collapse;font-size:13px}}
  th{{text-align:left;padding:10px 14px;color:#888;font-weight:500;font-size:12px;text-transform:uppercase;letter-spacing:.04em;border-bottom:1px solid #e5e5e0;background:#fafaf8}}
  td{{padding:10px 14px;border-bottom:1px solid #f0f0eb;vertical-align:top}}
  tr:last-child td{{border-bottom:none}}
  tr:hover td{{background:#fafaf8}}
  .badge{{display:inline-block;font-size:11px;padding:3px 9px;border-radius:99px;font-weight:500}}
  .full{{background:#e6f4e6;color:#2d7a2d}}
  .partial{{background:#fef3e0;color:#b06000}}
  .none{{background:#fdecea;color:#c0392b}}
  .error{{background:#f0f0eb;color:#888}}
  .page-title{{font-weight:500;color:#1a1a1a;margin-bottom:2px}}
  .page-url{{font-size:11px;color:#aaa;word-break:break-all}}
  .count{{font-size:13px;color:#888;margin-bottom:.75rem}}
  footer{{text-align:center;padding:2rem;font-size:12px;color:#bbb}}
  @media(max-width:600px){{.summary{{grid-template-columns:repeat(2,1fr)}}.bar-label{{width:70px}}input[type=text]{{width:100%}}.controls{{flex-direction:column;align-items:stretch}}}}
</style>
</head>
<body>

<header>
  <h1>Translation Audit — Vapaaehtoistieto</h1>
  <span class="meta">Last updated: {generated}</span>
</header>

<div class="inner">

  <div class="summary">
    <div class="card"><div class="lbl">Total pages</div><div class="num">{total}</div></div>
    <div class="card"><div class="lbl">Fully translated</div><div class="num green">{counts["fully_translated"]}</div></div>
    <div class="card"><div class="lbl">Partial</div><div class="num amber">{counts["partially_translated"]}</div></div>
    <div class="card"><div class="lbl">Not translated</div><div class="num red">{counts["not_translated"]}</div></div>
  </div>

  <div class="bars">
    <div class="bar-row">
      <span class="bar-label">Fully</span>
      <div class="bar-track"><div class="bar-fill" style="width:{pct_full}%;background:#4caf50"></div></div>
      <span class="bar-val green">{counts["fully_translated"]}</span>
    </div>
    <div class="bar-row">
      <span class="bar-label">Partial</span>
      <div class="bar-track"><div class="bar-fill" style="width:{pct_partial}%;background:#ff9800"></div></div>
      <span class="bar-val amber">{counts["partially_translated"]}</span>
    </div>
    <div class="bar-row">
      <span class="bar-label">Not translated</span>
      <div class="bar-track"><div class="bar-fill" style="width:{pct_none}%;background:#e53935"></div></div>
      <span class="bar-val red">{counts["not_translated"]}</span>
    </div>
  </div>

  <div class="controls">
    <button class="pill active" onclick="setFilter('all',this)">All ({total})</button>
    <button class="pill" onclick="setFilter('fully_translated',this)">Fully translated ({counts["fully_translated"]})</button>
    <button class="pill" onclick="setFilter('partially_translated',this)">Partial ({counts["partially_translated"]})</button>
    <button class="pill" onclick="setFilter('not_translated',this)">Not translated ({counts["not_translated"]})</button>
    <button class="pill" onclick="setFilter('error',this)">Errors ({counts["error"]})</button>
    <input type="text" id="search" placeholder="Search title or URL..." oninput="render()">
  </div>

  <div class="count" id="count"></div>

  <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th style="width:42%">Page</th>
          <th style="width:16%">Status</th>
          <th style="width:18%">Languages found</th>
          <th style="width:16%">Missing</th>
        </tr>
      </thead>
      <tbody id="tbody"></tbody>
    </table>
  </div>

</div>

<footer>Auto-generated by the Optimizely Translation Audit crawler &mdash; runs every Monday</footer>

<script>
const pages = {rows_json};
let filter = 'all';

function setFilter(f, btn) {{
  filter = f;
  document.querySelectorAll('.pill').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  render();
}}

function render() {{
  const q = document.getElementById('search').value.toLowerCase();
  const filtered = pages.filter(p => {{
    if (filter !== 'all' && p.status !== filter) return false;
    if (q && !p.title.toLowerCase().includes(q) && !p.url.toLowerCase().includes(q)) return false;
    return true;
  }});
  document.getElementById('count').textContent = 'Showing ' + filtered.length + ' of ' + pages.length + ' pages';
  document.getElementById('tbody').innerHTML = filtered.map(p => `
    <tr>
      <td>
        <div class="page-title">${{p.title || '(no title)'}}</div>
        <div class="page-url"><a href="${{p.url}}" target="_blank" style="color:#aaa">${{p.url}}</a></div>
      </td>
      <td><span class="badge ${{badgeClass(p.status)}}">${{badgeLabel(p.status)}}</span></td>
      <td style="color:#666">${{p.found || '—'}}</td>
      <td style="color:#666">${{p.missing || '—'}}</td>
    </tr>`).join('');
}}

function badgeClass(s) {{
  return {{fully_translated:'full',partially_translated:'partial',not_translated:'none',error:'error'}}[s]||'error';
}}
function badgeLabel(s) {{
  return {{fully_translated:'Fully translated',partially_translated:'Partial',not_translated:'Not translated',error:'Error / 404'}}[s]||s;
}}

render();
</script>
</body>
</html>"""

def main():
    if not os.path.exists(INPUT_JSON):
        print(f"ERROR: {INPUT_JSON} not found. Run the crawler first.")
        raise SystemExit(1)

    os.makedirs("docs", exist_ok=True)
    data = load_data(INPUT_JSON)
    html = make_html(data)

    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Dashboard written to {OUTPUT_HTML} ({len(data.get('pages',[]))} pages)")

if __name__ == "__main__":
    main()
