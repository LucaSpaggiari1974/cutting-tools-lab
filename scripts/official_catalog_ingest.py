#!/usr/bin/env python3
import json, re, subprocess, tempfile
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "official-catalog-extracted.json"

SOURCES = [
  {
    "maker":"Sumitomo Electric Hardmetal",
    "url":"https://www.sumitool.com/en/downloads/cutting-tools/general-catalog/assets/pdf/b.pdf",
    "scope":"inserts",
    "category":"Tornitura · Inserto ufficiale",
  },
  {
    "maker":"Sumitomo Electric Hardmetal",
    "url":"https://www.sumitool.com/en/downloads/cutting-tools/general-catalog/assets/pdf/h1.pdf",
    "scope":"milling-cutters",
    "category":"Fresatura · Utensili completi",
  },
  {
    "maker":"Sumitomo Electric Hardmetal",
    "url":"https://www.sumitool.com/en/downloads/cutting-tools/general-catalog/assets/pdf/i.pdf",
    "scope":"endmills",
    "category":"Fresatura · Utensili completi",
  },
  {
    "maker":"Sumitomo Electric Hardmetal",
    "url":"https://www.sumitool.com/en/downloads/cutting-tools/general-catalog/assets/pdf/j.pdf",
    "scope":"drills-reamers",
    "category":"Foratura · Utensili completi",
  },
]

# Conservative product-code candidates. The extractor never claims completeness:
# every row retains its exact official source URL and an extraction status.
CODE_RE = re.compile(r"(?<![A-Z0-9])([A-Z][A-Z0-9/._-]{3,}[0-9][A-Z0-9/._-]{0,})(?![A-Z0-9])")
BAD = {"CAT","NO","PAGE","PDF","TYPE","TABLE","NOTE","DIMENSIONS","APPLICATION","RANGE","SUMIBORON","SUMIDIA"}

def pdf_text(url):
    with tempfile.TemporaryDirectory() as td:
        pdf = Path(td) / "catalog.pdf"
        txt = Path(td) / "catalog.txt"
        req = Request(url, headers={"User-Agent":"cutting-tools-lab official catalog indexer"})
        with urlopen(req, timeout=120) as r:
            pdf.write_bytes(r.read())
        subprocess.run(["pdftotext","-layout",str(pdf),str(txt)], check=True, timeout=180)
        return txt.read_text(errors="ignore")

items = []
seen = set()
source_stats = []

for src in SOURCES:
    try:
        text = pdf_text(src["url"])
        candidates = []
        for line in text.splitlines():
            line = " ".join(line.split())
            for m in CODE_RE.finditer(line):
                code = m.group(1).strip(".,;:()[]")
                if code.upper() in BAD or len(code) > 80:
                    continue
                # Reject obvious prose fragments and standalone grade/material labels.
                if code.count("-") > 6 or code.isdigit() or code.upper() in {"CVD","PVD","CBN","PCD"}:
                    continue
                candidates.append(code)
        unique = sorted(set(candidates))
        added = 0
        for code in unique:
            key = (src["maker"], src["scope"], code)
            if key in seen:
                continue
            seen.add(key)
            items.append({
                "category": src["category"],
                "code": code,
                "maker": src["maker"],
                "toolType": "insert" if src["scope"] == "inserts" else "complete-tool",
                "verificationStatus": "official-catalog-extracted",
                "sourceOfficial": src["url"],
                "sourceType": "official-current-catalog-2025-2026",
                "photoStatus": "unavailable",
                "sourceNote": "Codice estratto automaticamente dal catalogo ufficiale corrente; richiede normalizzazione/controllo della riga ordine prima di essere marcato come fully-verified."
            })
            added += 1
        source_stats.append({**src, "status":"ok","candidateCount":len(unique),"added":added})
    except Exception as e:
        source_stats.append({**src, "status":"error","error":str(e)})

payload = {
  "version":"1.0-official-catalog-extraction",
  "updatedAt":__import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
  "status":"official-catalog-extraction-in-progress",
  "policy":"Candidates are extracted only from official current manufacturer PDFs. Extraction does not imply complete order-code verification.",
  "sources":source_stats,
  "items":items
}
OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
print(json.dumps({"output":str(OUT),"items":len(items),"sources":source_stats}, ensure_ascii=False))
