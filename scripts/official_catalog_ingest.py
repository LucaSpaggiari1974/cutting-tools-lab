#!/usr/bin/env python3
import json
import re
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
import urllib.parse

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "official-catalog-extracted.json"

# Primary official catalog sources. This file is deliberately a staging extractor:
# candidates are NEVER promoted to the visible catalog until the order-line/code
# has been normalized and verified against the current official source.
SOURCES = [
    # Prima passata controllata: Ingersoll, catalogo generale e famiglie specialistiche.
    # I cataloghi più ampi sono estratti una sola volta per evitare duplicazioni e tempi eccessivi.
    {"maker":"Ingersoll","url":"https://ssl.ingersoll-imc.com/resources/pdf/cat-031-1_winsfeed_new_products_catalog_2024.pdf","scope":"milling-cutters","category":"Fresatura · Utensili completi"},
    {"maker":"Ingersoll","url":"https://ssl.ingersoll-imc.com/resources/pdf/cat-031-1_winsfeed_new_products_catalog_2024.pdf","scope":"inserts","category":"Tornitura · Inserto ufficiale"},
    {"maker":"Ingersoll","url":"https://ssl.ingersoll-imc.com/resources/pdf/CAT-032-Ingersoll-Precision-Boring.pdf","scope":"drills-reamers","category":"Alesatura · Utensili completi"},
    {"maker":"Ingersoll","url":"https://ssl.ingersoll-imc.com/resources/pdf/cat-30-3-cbn-inserts-catalog.pdf","scope":"inserts","category":"Tornitura · Inserto ufficiale"},
    {"maker":"Ingersoll","url":"https://ssl.ingersoll-imc.com/resources/pdf/it.te.di.-pcd-iso-inserts-catalog.pdf","scope":"inserts","category":"Tornitura · Inserto ufficiale"},
    {"maker":"Ingersoll","url":"https://ssl.ingersoll-imc.com/resources/pdf/new-127-2-rapid-thread-straight-flute-indexable.pdf","scope":"inserts","category":"Filettatura · Inserto ufficiale"},
    {"maker":"Ingersoll","url":"https://ssl.ingersoll-imc.com/resources/pdf/NEW-260-1_T-Thread_ISO26623-1.pdf","scope":"milling-cutters","category":"Filettatura · Utensili completi"},
    {"maker":"Ingersoll","url":"https://ssl.ingersoll-imc.com/resources/pdf/new-399-1-gold-flex-extra-wide-inserts.pdf","scope":"inserts","category":"Scanalatura · Inserto ufficiale"},
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

PDF_CACHE = {}

def pdf_text(url):
    if url in PDF_CACHE:
        return PDF_CACHE[url]
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
        value = txt.read_text(errors="ignore")
        PDF_CACHE[url] = value
        return value

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
    for line_index, raw in enumerate(page_text.splitlines()):
        line = " ".join(raw.split())
        if not line:
            continue
        for m in INSERT_RE.finditer(line):
            code = clean_code(f"{m.group('shape')} {m.group('body')}")
            if not is_grade_or_noise(code):
                found.append((code, line, line_index))
        for m in COMPACT_INSERT_RE.finditer(line):
            code = clean_code(m.group("code"))
            if not is_grade_or_noise(code):
                found.append((code, line, line_index))
    return found

def extract_tool_candidates(page_text):
    found = []
    # Strong order-number cues reduce prose false positives.
    order_context = re.compile(r"\b(cat\.?\s*no\.?|order\s*(no\.?|code)|part\s*no\.?|catalog\s*(no\.?|number))\b", re.I)
    for line_index, raw in enumerate(page_text.splitlines()):
        line = " ".join(raw.split())
        if not line or not order_context.search(line):
            continue
        for m in TOOL_CODE_RE.finditer(line):
            code = clean_code(m.group(1))
            if not is_grade_or_noise(code):
                found.append((code, line, line_index))
    return found

def normalize_lines(page_text):
    return [" ".join(x.split()) for x in page_text.splitlines() if x.strip()]

def _all_matches(pattern, text):
    return [m.group(1).replace(",", ".").strip() for m in re.finditer(pattern, text or "", re.I)]

def extract_recommended_conditions_from_lines(lines, center=None, radius=65):
    """Extract condition tables from a bounded local window.
    The window is deliberately local to the SKU candidate to avoid mixing
    neighbouring products on the same PDF page.
    """
    if center is None:
        lo, hi = 0, len(lines)
    else:
        lo, hi = max(0, center-radius), min(len(lines), center+radius+1)
    window = lines[lo:hi]
    blocks = []
    headings = (
        "recommended cutting conditions", "cutting conditions",
        "cutting speed", "feed rate", "feed per tooth", "feed per revolution",
        "vc", "fz", "ap"
    )
    vc_pat = r"(?:(?:vc|cutting\s*speed)\s*[:=]?\s*)?([0-9]+(?:[.,][0-9]+)?(?:\s*(?:-|–|to)\s*[0-9]+(?:[.,][0-9]+)?)?)\s*(?:m/min|m\/min)"
    f_pat = r"(?:(?:fz|feed\s*(?:rate|per\s*tooth)|feed\s*per\s*revolution|feed)\s*[:=]?\s*)?([0-9]+(?:[.,][0-9]+)?(?:\s*(?:-|–|to)\s*[0-9]+(?:[.,][0-9]+)?)?)\s*(?:mm\/(?:rev|t|tooth)|mm\/rev|mm\/tooth|mm/t)"
    ap_pat = r"(?:(?:ap|depth\s*of\s*cut)\s*[:=]?\s*)?([0-9]+(?:[.,][0-9]+)?(?:\s*(?:-|–|to)\s*[0-9]+(?:[.,][0-9]+)?)?)\s*mm"
    for j, line in enumerate(window):
        low=line.lower()
        if not any(k in low for k in headings):
            continue
        bstart=max(0,j-2); bend=min(len(window),j+42)
        raw=" | ".join(x for x in window[bstart:bend] if x)
        if not raw or any(b["raw"]==raw for b in blocks):
            continue
        blocks.append({
            "raw": raw[:12000],
            "vc": list(dict.fromkeys(_all_matches(vc_pat,raw))),
            "f": list(dict.fromkeys(_all_matches(f_pat,raw))),
            "ap": list(dict.fromkeys(_all_matches(ap_pat,raw))),
        })
    return blocks[:10]

def extract_parameter_rows_from_lines(lines, center, radius=48):
    """Keep raw parameter rows locally tied to the candidate; do not synthesize values."""
    lo=max(0, center-radius); hi=min(len(lines), center+radius+1)
    rows=[]
    for line in lines[lo:hi]:
        low=line.lower()
        if not re.search(r"\b(?:vc|cutting\s*speed|feed|fz|feed\s*rate|ap|depth\s*of\s*cut)\b|m/min|mm/(?:rev|t|tooth)|mm/t", low):
            continue
        if line not in rows:
            rows.append(line)
    return rows[:80]

def extract_cutting_condition_context_from_blocks(blocks):
    return " || ".join(b["raw"] for b in blocks)[:12000]

def extract_application_metadata_from_lines(lines, center=None, radius=55):
    if center is None:
        window=lines
    else:
        window=lines[max(0,center-radius):min(len(lines),center+radius+1)]
    materials=[]; geometries=[]; operations=[]
    for line in window:
        low=line.lower()
        if re.search(r"\b(workpiece|work material|material)\b", low):
            materials.append(line)
        if re.search(r"\b(machining types?|application|chip breaker|geometry|relief angle|rake angle|cutting edge)\b", low):
            geometries.append(line)
        if re.search(r"\b(turning|finishing|medium|roughing|profiling|grooving|parting|threading|milling|drilling|reaming)\b", low):
            operations.append(line)
    def uniq(rows, limit=30):
        out=[]
        for x in rows:
            if x not in out: out.append(x)
        return " | ".join(out[:limit])[:7000]
    return {"material":uniq(materials),"geom":uniq(geometries),"application":uniq(operations)}

def extract_explicit_parameter_values(context):
    """Only accept labelled values; table values stay in recommendedConditions."""
    t=" ".join(str(context or "").split())
    out={}
    patterns={
        "vc":r"\b(?:vc|cutting\s*speed)\s*[:=]\s*([0-9]+(?:[.,][0-9]+)?(?:\s*(?:-|–|to)\s*[0-9]+(?:[.,][0-9]+)?)?)\s*(?:m/min)?",
        "f":r"\b(?:fz|feed\s*rate|feed)\s*[:=]\s*([0-9]+(?:[.,][0-9]+)?(?:\s*(?:-|–|to)\s*[0-9]+(?:[.,][0-9]+)?)?)\s*(?:mm/(?:rev|t|tooth)|mm/rev|mm/t)?",
        "ap":r"\b(?:ap|depth\s*of\s*cut)\s*[:=]\s*([0-9]+(?:[.,][0-9]+)?(?:\s*(?:-|–|to)\s*[0-9]+(?:[.,][0-9]+)?)?)\s*(?:mm)?"
    }
    for key,pat in patterns.items():
        m=re.search(pat,t,re.I)
        if m: out[key]=m.group(1).replace(",",".")
    return out



TECHNICAL_IT = [
    ("recommended cutting conditions", "condizioni di taglio consigliate"),
    ("cutting conditions", "condizioni di taglio"),
    ("workpiece material", "materiale del pezzo"),
    ("work material", "materiale da lavorare"),
    ("stainless steel", "acciaio inossidabile"),
    ("nickel-based alloys", "leghe a base nichel"),
    ("non-ferrous materials", "materiali non ferrosi"),
    ("non-ferrous", "non ferrosi"),
    ("solid carbide", "metallo duro integrale"),
    ("feed per revolution", "avanzamento per giro"),
    ("feed per tooth", "avanzamento per dente"),
    ("depth of cut", "profondità di passata"),
    ("cutting speed", "velocità di taglio"),
    ("chip breaker", "rompitruciolo"),
    ("cutting edge", "tagliente"),
    ("relief angle", "angolo di spoglia"),
    ("rake angle", "angolo di spoglia frontale"),
    ("tool holder", "portautensile"),
    ("end mill", "fresa integrale"),
    ("face mill", "fresa a spianare"),
    ("boring bar", "barra di alesatura"),
    ("cast iron", "ghisa"),
    ("aluminum", "alluminio"),
    ("aluminium", "alluminio"),
    ("titanium", "titanio"),
    ("superalloys", "superleghe"),
    ("workpiece", "pezzo in lavorazione"),
    ("recommended", "consigliato"),
    ("application", "impiego"),
    ("geometry", "geometria"),
    ("material", "materiale"),
    ("turning", "tornitura"),
    ("finishing", "finitura"),
    ("roughing", "sgrossatura"),
    ("profiling", "profilatura"),
    ("grooving", "scanalatura"),
    ("parting", "troncatura"),
    ("threading", "filettatura"),
    ("milling", "fresatura"),
    ("drilling", "foratura"),
    ("reaming", "alesatura"),
    ("steel", "acciaio"),
    ("stainless", "inossidabile"),
    ("feed rate", "avanzamento"),
    ("feed", "avanzamento"),
    ("inserts", "inserti"),
    ("insert", "inserto"),
    ("drill", "punta"),
]
def technical_italian(value):
    text = str(value or "")
    for source, target in sorted(TECHNICAL_IT, key=lambda pair: len(pair[0]), reverse=True):
        text = re.sub(r"(?<![A-Za-z])" + re.escape(source) + r"(?![A-Za-z])", target, text, flags=re.I)
    return text


def classify_local_category(scope, default_category, context):
    """Classify by the closest specific operation heading before using a broad fallback."""
    text = str(context or "").casefold()
    label = str(default_category or "").casefold()
    if re.search(r"\b(threading|thread milling|thread turning|thread insert|filettatura)\b", text) or "filettatura" in label or "thread" in label:
        return "Filettatura" if scope == "inserts" else "Filettatura · Utensili completi"
    if re.search(r"\b(drilling insert|drill insert|holemaking|deep hole|drilling|reaming|reamer|foratura|alesatura)\b", text) or any(w in label for w in ("foratura", "drill", "ream", "alesatura")):
        return "Foratura" if scope == "inserts" else ("Alesatura · Utensili completi" if re.search(r"\b(precision boring|boring and reaming|reamer|reaming|alesatura)\b", text) else "Foratura · Utensili completi")
    if re.search(r"\b(grooving|parting|part-off|parting-off|scanalatura|troncatura)\b", text) or any(w in label for w in ("scanalatura", "grooving", "parting")):
        return "Tornitura · Media" if scope == "inserts" else "Scanalatura · Utensili completi"
    if re.search(r"\b(milling insert|indexable milling|face mill|shoulder mill|milling|end mill|lens type|chamfer barrel type|fresatura)\b", text) or "fresatura" in label or "mill" in label:
        return "Fresatura" if scope == "inserts" else "Fresatura · Utensili completi"
    if re.search(r"\b(finishing|finish|finitura)\b", text) or "finitura" in label or "finish" in label:
        return "Tornitura · Finitura" if scope == "inserts" else "Tornitura · Utensili completi"
    if re.search(r"\b(roughing|rough|sgrossatura)\b", text) or "sgrossatura" in label or "rough" in label:
        return "Tornitura · Sgrossatura" if scope == "inserts" else "Tornitura · Utensili completi"
    if re.search(r"\b(turning insert|turning|boring bar|turning grade|tornitura)\b", text) or "tornitura" in label or "turn" in label:
        return "Tornitura · Media" if scope == "inserts" else "Tornitura · Utensili completi"
    if re.search(r"\b(gear production|gear cutting|dentatura)\b", text):
        return "Dentatura · Utensili completi"
    return "Tornitura · Media" if scope == "inserts" else default_category

source_stats = []

def discover_official_pdf_sources():
    """Discover current PDF catalog links on registered official manufacturer domains.
    Discovery is bounded per maker and never treats a homepage as a product record.
    """
    registry_path = ROOT / "official-catalog-sources.json"
    try:
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
    except Exception:
        return []
    known = {(x["maker"], x["url"]) for x in SOURCES}
    discovered = []
    excluded = {"korloy", "korloy inc."}
    ua = "Cutting-Tools-LAB official catalog indexer"
    for entry in registry.get("sources", []):
        maker = str(entry.get("maker", "")).strip()
        base = str(entry.get("catalog", "")).strip()
        # Procedura sequenziale richiesta: completare Ingersoll prima di passare agli altri produttori.
        if not maker or maker.casefold() in excluded or maker.casefold() != "ingersoll" or not base:
            continue
        try:
            req = Request(base, headers={"User-Agent": ua, "Accept": "text/html,application/pdf,*/*"})
            with urlopen(req, timeout=25) as response:
                final_url = response.geturl()
                ctype = response.headers.get("content-type", "").lower()
                first = response.read(1_000_000)
            if "pdf" in ctype or final_url.lower().split("?", 1)[0].endswith(".pdf"):
                links = [(final_url, maker, "official catalog PDF")]
            else:
                html = first.decode("utf-8", errors="ignore")
                links = []
                for match in re.finditer(r'''href\s*=\s*["']([^"']+)["']''', html, re.I):
                    href = match.group(1).replace("&amp;", "&")
                    url = urllib.parse.urljoin(final_url, href)
                    parsed = urllib.parse.urlparse(url)
                    if parsed.scheme not in ("http", "https") or not parsed.path.lower().endswith(".pdf"):
                        continue
                    # Stay on the official domain (allow subdomains), never crawl arbitrary linked hosts.
                    host = parsed.hostname or ""
                    base_host = urllib.parse.urlparse(final_url).hostname or ""
                    if not (host == base_host or host.endswith("." + base_host) or base_host.endswith("." + host)):
                        continue
                    label = (href + " " + match.group(0)).lower()
                    if not any(k in label for k in ("catalog", "turn", "mill", "drill", "thread", "cutting", "tool", "insert", "boring", "ream")):
                        continue
                    links.append((url, maker, href))
            added_for_maker = 0
            for url, source_maker, label in links:
                if (source_maker, url) in known:
                    continue
                low = (url + " " + label).lower()
                if any(k in low for k in ("drill", "ream")):
                    scope, category = "drills-reamers", "Foratura · Utensili completi"
                elif any(k in low for k in ("mill", "endmill")):
                    scope, category = "milling-cutters", "Fresatura · Utensili completi"
                elif "thread" in low:
                    scope, category = "inserts", "Filettatura · Inserto ufficiale"
                else:
                    scope, category = "inserts", "Tornitura · Inserto ufficiale"
                discovered.append({"maker": source_maker, "url": url, "scope": scope, "category": category})
                known.add((source_maker, url))
                added_for_maker += 1
                # Catalog portals often expose separate PDFs for turning, milling,
                # drilling, threading and toolholding. Three links per manufacturer
                # systematically under-indexed every brand except those with hand-added
                # PDFs above. Expand the bounded discovery budget while keeping every
                # source on the registered manufacturer's official domain.
                if added_for_maker >= 4:
                    break
        except Exception as exc:
            source_stats.append({"maker": maker, "url": base, "status": "discovery-error", "error": str(exc)[:300]})
    return discovered


# Supplement the hand-verified PDFs with current PDFs linked by each registered official catalog.
# KORLOY is deliberately excluded, in accordance with the project requirement.
SOURCES.extend(discover_official_pdf_sources())
# Prima passata: non mescolare estrazioni di altri marchi alla verifica Ingersoll.
SOURCES = [src for src in SOURCES if str(src.get("maker","")).casefold() == "ingersoll"]

items = []
seen = set()

for src in SOURCES:
    try:
        text = pdf_text(src["url"])
        pages = text.split("\f")
        candidates = []
        page_cache = {}
        for page_no, page in enumerate(pages, start=1):
            lines = normalize_lines(page)
            page_cache[page_no] = lines
            # Candidate offsets MUST use the same normalized line array as
            # parameter extraction below. Previously the candidates were found
            # on raw PDF lines (including blanks) while metadata was read from
            # normalized lines (blanks removed), shifting the lookup window and
            # attaching empty or unrelated conditions to product codes.
            candidate_text = "\n".join(lines)
            if src["scope"] == "inserts":
                page_candidates = extract_insert_candidates(candidate_text)
            else:
                page_candidates = extract_tool_candidates(candidate_text)
            for code, context, line_index in page_candidates:
                candidates.append((code, page_no, context[:1200], line_index))

        unique = {}
        for code, page_no, context, line_index in candidates:
            unique.setdefault(code, (page_no, context, line_index))

        added = 0
        for code, (page_no, context, line_index) in sorted(unique.items()):
            key = (src["maker"], src["scope"], code)
            if key in seen:
                continue
            seen.add(key)
            lines = page_cache[page_no]
            local_meta = extract_application_metadata_from_lines(lines, line_index, 55)
            local_meta = {k: technical_italian(v) for k, v in local_meta.items()}
            local_recommended = extract_recommended_conditions_from_lines(lines, line_index, 65)
            local_recommended = [
                {**block, "raw": technical_italian(block.get("raw", ""))}
                for block in local_recommended
            ]
            local_parameter_rows = [
                technical_italian(v) for v in extract_parameter_rows_from_lines(lines, line_index, 48)
            ]
            local_conditions = extract_cutting_condition_context_from_blocks(local_recommended)
            local_context = " | ".join(lines[max(0,line_index-15):min(len(lines),line_index+66)])[:3500]
            explicit = extract_explicit_parameter_values(local_context)
            recommended = local_recommended
            conditions = local_conditions
            nearby_context = " | ".join(lines[max(0,line_index-10):min(len(lines),line_index+11)])[:1800]
            resolved_category = classify_local_category(src["scope"], src["category"], nearby_context)
            items.append({
                "category": resolved_category,
                "code": code,
                "maker": src["maker"],
                "toolType": "insert" if src["scope"] == "inserts" else "complete-tool",
                "verificationStatus": "official-catalog-extracted",
                "sourceOfficial": src["url"],
                "sourceType": "catalogo-ufficiale-estratto-da-verificare",
                "sourcePage": page_no,
                "sourceContext": local_context,
                "geom": local_meta.get("geom",""),
                "material": local_meta.get("material",""),
                "application": local_meta.get("application",""),
                "cuttingConditions": conditions,
                "recommendedConditions": recommended,
                "parameterRows": local_parameter_rows,
                "parameterStatus": "explicit-order-line" if explicit else ("official-local-conditions-available" if conditions else "not-found"),
                "vc": explicit.get("vc", "—"),
                "f": explicit.get("f", "—"),
                "ap": explicit.get("ap", "—"),
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
    "version": "2.3-fast-precise-local-parameter-rows",
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
