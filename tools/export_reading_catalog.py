#!/usr/bin/env python3
"""Export a searchable offline HTML title list from an installed Lastbook pack."""
import argparse
import html
import json
from pathlib import Path

READING_KINDS = {"pdf", "html", "pptx"}


def export(catalog_path, output_path):
    records = json.loads(Path(catalog_path).read_text(encoding="utf-8"))
    if not isinstance(records, list):
        raise ValueError("catalog.json must contain a list of records")
    entries = []
    for record in records:
        if not isinstance(record, dict):
            continue
        kind = record.get("kind")
        if not isinstance(kind, str) or kind not in READING_KINDS:
            continue
        title = record.get("title")
        if not isinstance(title, str) or not title.strip():
            continue
        collection = record.get("collection")
        publisher = record.get("publisher")
        entries.append((
            collection.strip() if isinstance(collection, str) and collection.strip() else "Other",
            title.strip(),
            record["kind"].upper(),
            publisher.strip() if isinstance(publisher, str) else "",
        ))
    entries.sort(key=lambda row: (row[0].casefold(), row[1].casefold()))
    rows = "\n".join(
        "<tr>" + "".join("<td>" + html.escape(value, quote=True) + "</td>" for value in entry) + "</tr>"
        for entry in entries
    )
    page = """<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Lastbook reading catalog</title>
<style>
body{font:16px system-ui,sans-serif;max-width:1100px;margin:2rem auto;padding:0 1rem}
input,select{font:inherit;padding:.6rem;box-sizing:border-box}
input{width:min(100%,35rem)}
.controls{display:flex;flex-wrap:wrap;gap:1rem;align-items:end}
.controls label{display:block;margin-bottom:.25rem}
table{width:100%;border-collapse:collapse;margin-top:1rem}
th,td{text-align:left;padding:.6rem;border-bottom:1px solid #8885}
tr[hidden]{display:none}
@media(max-width:650px){th:last-child,td:last-child{display:none}}
</style>
<h1>Lastbook reading catalog</h1>
<p>Titles from one installed library pack. This is a listing, not a download service. No network connection is used.</p>
<div class="controls"><div><label for="q">Search titles and collections</label>
<input id="q" type="search" placeholder="Search"></div>
<div><label for="type">Format</label>
<select id="type"><option value="">All formats</option><option value="PDF">PDF</option><option value="HTML">HTML</option><option value="PPTX">PPTX</option></select></div>
<div><label for="letter">Title starts with</label>
<select id="letter"><option value="">All titles</option></select></div></div>
<p id="count" role="status" aria-live="polite"></p>
<table><thead><tr><th>Collection</th><th>Title</th><th>Type</th><th>Publisher</th></tr></thead>
<tbody>""" + rows + """</tbody></table>
<script>
const q=document.getElementById('q'),type=document.getElementById('type'),letter=document.getElementById('letter'),rs=[...document.querySelectorAll('tbody tr')],count=document.getElementById('count');
const initials=[...new Set(rs.map(r=>r.cells[1].textContent.trim().charAt(0).toLocaleUpperCase()).filter(Boolean))].sort();
for(const initial of initials){const option=document.createElement('option');option.value=initial;option.textContent=initial;letter.appendChild(option)}
function filter(){const v=q.value.toLocaleLowerCase();let n=0;
for(const r of rs){const title=r.cells[1].textContent.trim();r.hidden=!(r.textContent.toLocaleLowerCase().includes(v)&&(!type.value||r.cells[2].textContent===type.value)&&(!letter.value||title.charAt(0).toLocaleUpperCase()===letter.value));if(!r.hidden)n++}
count.textContent=n+' of '+rs.length+' titles';}
for(const control of [q,type,letter])control.addEventListener(control===q?'input':'change',filter);filter();
</script></html>"""
    Path(output_path).write_text(page, encoding="utf-8")
    return len(entries)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True, help="Folder containing library-data/catalog.json")
    parser.add_argument("--output", type=Path, required=True, help="Output HTML file")
    args = parser.parse_args()
    try:
        count = export(args.data / "library-data" / "catalog.json", args.output)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.exit(1, f"Cannot export reading catalog: {exc}\n")
    print(f"Exported {count} titles to {args.output}")


if __name__ == "__main__":
    main()
