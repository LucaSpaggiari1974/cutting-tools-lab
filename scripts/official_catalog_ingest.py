#!/usr/bin/env python3
import json
import re
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "official-catalog-extracted.json"

# Primary official catalog sources. This file is deliberately a staging extractor:
# candidates are NEVER promoted to the visible catalog until the order-line/code
# has been normalized and verified against the current official source.
SOURCES = [
    {"maker":"Sumitomo Electric Hardmetal","url":"https://www.sumitool.com/en/downloads/cutting-tools/general-catalog/assets/pdf/b.pdf","scope":"inserts","category":"Tornitura · Inserto ufficiale"},
    {"maker":"Sumitomo Electric Hardmetal","url":"https://www.sumitool.com/en/downloads/cutting-tools/general-catalog/assets/pdf/h1.pdf","scope":"milling-cutters","category":"Fresatura · Utensili completi"},
    {"maker":"Sumitomo Electric Hardmetal","url":"https://www.sumitool.com/en/downloads/cutting-tools/general-catalog/assets/pdf/i.pdf","scope":"endmills","category":"Fresatura · Utensili completi"},
    {"maker":"Sumitomo Electric Hardmetal","url":"https://www.sumitool.com/en/downloads/cutting-tools/general-catalog/assets/pdf/j.pdf","scope":"drills-reamers","category":"Foratura · Utensili completi"},
    {"maker":"Sumitomo Electric Hardmetal","url":"https://www.sumitool.com/en/downloads/cutting-tools/general-catalog/assets/pdf/j.pdf","scope":"inserts","category":"Foratura · Inserto ufficiale"},
    {"maker":"Sumitomo Electric Hardmetal","url":"https://www.sumitool.com/en/downloads/cutting-tools/general-catalog/assets/pdf/f3.pdf","scope":"inserts","category":"Filettatura · Inserto ufficiale"},
    {"maker":"KORLOY","url":"https://www.korloy.com/en/ebook/2025-2026%20TURNING%28EI%29/assets/contents/download.pdf","scope":"inserts","category":"Tornitura · Inserto ufficiale"},
    {"maker":"KORLOY","url":"https://korloy.com/en/ebook/Cutting%20Tools_Solid%202025-2026/assets/contents/download.pdf","scope":"solid-tools","category":"Fresatura · Utensili completi"},
]

# ISO-style indexable-insert ordering codes. The blank between shape and size is
# intentional: current catalogs commonly print codes such as CNMG 120408N-LU.
INSERT_RE = re.compile(
    r"(?<![A-Z0-9])(?P<shape>[A-Z]{2,5})\s+"
    r"(?P<body>[0-9][0-9A-Z]{4,10}(?:-[0-9A-Z]{1,10})?)(?![A-Z0-9])"
)
# Some official catalogs use a compact code without a space. Keep this pattern
# narrow enough to avoid swallowing grade names/material labels.
COMPACT_INSERT_RE = re.compile(
    r"(?<![A-Z0-9])(?P<code>[CDSNTRVWP][A-Z]{1,4}[0-9][0-9A-Z]{4,10}(?:-[0-9A-Z]{1,10})?)(?![A-Z0-9])"
)
# Complete-tool candidate extraction is intentionally restricted to order/catalog
# contexts. It is still a staging candidate, not a verified product.
TOOL_CODE_RE = re.compile(
    r"(?<![A-Z0-9])([A-Z0-9][A-Z0-9./_-]{4,34})(?![A-Z0-9])"
)

BAD_TOKENS = {
    "CAT","NO","PAGE","PDF","TYPE","TABLE","NOTE","DIMENSIONS","APPLICATION",
    "RANGE","SUMIBORON","SUMIDIA","CUTTING","TOOLS","INSERT","INSERTS",
    "MATERIAL","GRADE","GRADES","STANDARD","OPTION","OPTIONS","STOCK",
    "CVD","PVD","CBN","PCD"
}

def pdf_text(url):
    with tempfile.TemporaryDirectory() as td:
        pdf = Path(td) / "catalog.pdf"
        txt = Path(td) / "catalog.txt"
        req = Request(url, headers={"User-Agent": "cutting-tools-lab official catalog indexer"})
        with urlopen(req, timeout=180) as r:
            pdf.write_bytes(r.read())
        subprocess.run(
            ["pdftotext", "-layout", str(pdf), str(txt)],
            check=True,
            timeout=300,
        )
        return txt.read_text(errors="ignore")

def clean_code(code):
    return code.strip(".,;:()[]{}<>|")

def is_grade_or_noise(code):
    u = code.upper()
    if u in BAD_TOKENS or len(code) > 60:
        return True
    if code.isdigit():
        return True
    # Standalone grade/material labels are not order codes.
    if re.fullmatch(r"[A-Z]{1,4}[0-9]{2,6}[A-Z]?", u) and " " not in code:
        return True
    return False

def extract_insert_candidates(page_text):
    found = []
    for raw in page_text.splitlines():
        line = " ".join(raw.split())
        if not line:
            continue
        for m in INSERT_RE.finditer(line):
            code = clean_code(f"{m.group('shape')} {m.group('body')}")
            if not is_grade_or_noise(code):
                found.append((code, line))
        for m in COMPACT_INSERT_RE.finditer(line):
            code = clean_code(m.group("code"))
            if not is_grade_or_noise(code):
                found.append((code, line))
    return found

def extract_tool_candidates(page_text):
    found = []
    # Strong order-number cues reduce prose false positives.
    order_context = re.compile(r"\b(cat\.?\s*no\.?|order\s*(no\.?|code)|part\s*no\.?|catalog\s*(no\.?|number))\b", re.I)
    for raw in page_text.splitlines():
        line = " ".join(raw.split())
        if not line or not order_context.search(line):
            continue
        for m in TOOL_CODE_RE.finditer(line):
            code = clean_code(m.group(1))
            if not is_grade_or_noise(code):
                found.append((code, line))
    return found

items = []
seen = set()
source_stats = []

for src in SOURCES:
    try:
        text = pdf_text(src["url"])
        pages = text.split("\f")
        candidates = []
        for page_no, page in enumerate(pages, start=1):
            if src["scope"] == "inserts":
                page_candidates = extract_insert_candidates(page)
            else:
                page_candidates = extract_tool_candidates(page)
            for code, context in page_candidates:
                candidates.append((code, page_no, context[:500]))

        unique = {}
        for code, page_no, context in candidates:
            unique.setdefault(code, (page_no, context))

        added = 0
        for code, (page_no, context) in sorted(unique.items()):
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
                "sourcePage": page_no,
                "sourceContext": context,
                "photoStatus": "unavailable",
                "sourceNote": (
                    "Codice estratto dal catalogo ufficiale corrente; "
                    "richiede verifica della riga ordine e normalizzazione prima "
                    "di essere promosso a official-order-code-verified."
                ),
            })
            added += 1

        source_stats.append({
            **src,
            "status": "ok",
            "pageCount": len(pages),
            "candidateCount": len(unique),
            "added": added,
        })
    except Exception as e:
        source_stats.append({**src, "status":"error", "error":str(e)})

payload = {
    "version": "2.0-official-catalog-extraction",
    "updatedAt": datetime.now(timezone.utc).isoformat(),
    "status": "official-catalog-extraction-in-progress",
    "rule": (
        "Importare articolo per articolo dai cataloghi ufficiali correnti. "
        "Nessun codice viene inventato; nessuna famiglia viene considerata "
        "completa finché i relativi articoli non sono stati indicizzati."
    ),
    "policy": (
        "Questo file è staging. Le righe estratte non diventano visibili come "
        "articoli verificati finché codice, contesto d'ordine e fonte ufficiale "
        "non sono stati normalizzati e controllati."
    ),
    "sources": source_stats,
    "items": items,
}
OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
print(json.dumps({"output": str(OUT), "items": len(items), "sources": source_stats}, ensure_ascii=False))
