#!/usr/bin/env python3
"""Promote only strong official-catalog candidates into the visible insert catalog.

Staging remains the source of truth for candidates. This promoter:
- never invents codes;
- promotes only insert-shaped codes from official insert sources;
- deduplicates by manufacturer + normalized code;
- classifies turning by ISO geometry/context and otherwise uses context;
- preserves source evidence;
- leaves ambiguous candidates in staging.
"""
import json, re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STAGING = ROOT / "official-catalog-extracted.json"
CATALOG = ROOT / "catalog.json"
TOOLS = ROOT / "complete-tools.json"
BACKUP = ROOT / "backups" / "catalog-before-promotion.json"
TOOLS_BACKUP = ROOT / "backups" / "complete-tools-before-promotion.json"
REPORT = ROOT / "official-catalog-promotion-report.json"

ALLOWED = [
    "Tornitura · Finitura", "Tornitura · Media", "Tornitura · Sgrossatura",
    "Fresatura", "Foratura", "Filettatura"
]

# Allow registered manufacturers except KORLOY, excluded by the user's catalog scope.
ALLOWED_MAKERS = {
    "ingersoll": "Ingersoll", "ingersoll cutting tools": "Ingersoll",
    "iscar": "ISCAR",
    "kennametal": "Kennametal",
    "sandvik": "Sandvik Coromant", "sandvik coromant": "Sandvik Coromant",
    "seco": "Seco Tools", "seco tools": "Seco Tools",
    "sumitomo": "Sumitomo Electric Hardmetal",
    "sumitomo electric": "Sumitomo Electric Hardmetal",
    "sumitomo electric hardmetal": "Sumitomo Electric Hardmetal",
    "tungaloy": "Tungaloy",
    "walter": "Walter", "walter tools": "Walter",
    "taegutec": "TaeguTec",
    "mitsubishi": "Mitsubishi Materials", "mitsubishi materials": "Mitsubishi Materials",
    "kyocera": "Kyocera", "ceratizit": "Ceratizit",
    "dormer pramet": "Dormer Pramet", "ntk": "NTK",
    "zcc": "ZCC", "zcc cutting tools": "ZCC",
}
def canonical_maker(value):
    raw = str(value or "").strip()
    if not raw or raw.casefold() == "iso":
        return ""
    return ALLOWED_MAKERS.get(raw.casefold(), "")

TURNING = re.compile(r"^(CNMG|DNMG|SNMG|TNMG|VNMG|WNMG|CCMT|DCMT|TCMT|VCMT|VBMT|VBGT|CCGT|DCGT|TCGT|VCGT|CNGA|DNGA|TNGA|VNGA|WNGA)\b", re.I)
MILLING = re.compile(r"^(APMT|APKT|SEHT|SEKT|RDMW|RPMT|SPMT|SOMT|XPMT|LNMU|ADMX|SDMT|SDXT|ONHU|ODMX|XDET|LOGX)\b", re.I)
DRILLING = re.compile(r"^(WCMX|SPMX|SCMX|SOMX|XCMT|XOMX|WCMT)\b", re.I)
THREADING = re.compile(r"^(16ER|16IR|11ER|11IR|22ER|22IR|27ER|27IR|08ER|08IR|06ER|06IR)\b", re.I)

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

def clean_geometry(value, code=""):
    """Return a short, useful geometry label; never show extracted table headers as geometry."""
    text = technical_italian(value)
    text = re.sub(r"\\s*\\|\\s*", " · ", text)
    text = re.sub(r"\\s+", " ", text).strip(" ·|")
    junk = (
        "part number", "numero parte", "series ", "serie ", "no. of", "number of",
        "cutting dia", "diametro di taglio", "thickness", "spessore", "grade",
        "grades", "insert length", "insert width", "corner radius", "wiper radius",
        "profile radius", "geometry.", "geometria.", "relief angle", "angle of",
        "products", "metric", "ing ersoll", "ingersoll-imc.com",
    )
    low = text.casefold()
    if not text or any(token in low for token in junk) or len(text) > 90 or text.count("·") >= 3:
        text = ""
    if not text:
        # ISO insert-shape codes are a safe shape/angle description, not a cutting parameter.
        prefix = re.match(r"^\\s*([CDEHKLMP RSTUVW])", str(code or "").upper().replace(" ", ""))
        shape = {"C":"Rombo 80°", "D":"Rombo 55°", "V":"Rombo 35°", "W":"Trigon 80°", "S":"Quadrato 90°", "T":"Triangolo 60°", "R":"Tondo", "P":"Pentagonale", "K":"Parallelogramma", "L":"Rettangolo", "M":"Rombo 86°"}.get(prefix.group(1)) if prefix else None
        return shape or ""
    return text[:90]

def clean_application(value):
    text = technical_italian(value)
    parts = [re.sub(r"\\s+", " ", p).strip(" ·|,") for p in re.split(r"\\s*[|]\\s*", text)]
    allowed = (
        ("turning", "tornitura"), ("tornitura", "tornitura"),
        ("finishing", "finitura"), ("finitura", "finitura"),
        ("medium", "media"), ("media", "media"),
        ("roughing", "sgrossatura"), ("sgrossatura", "sgrossatura"),
        ("profiling", "profilatura"), ("profilatura", "profilatura"),
        ("grooving", "scanalatura"), ("scanalatura", "scanalatura"),
        ("parting", "troncatura"), ("troncatura", "troncatura"),
        ("threading", "filettatura"), ("filettatura", "filettatura"),
        ("milling", "fresatura"), ("fresatura", "fresatura"),
        ("drilling", "foratura"), ("foratura", "foratura"),
        ("reaming", "alesatura"), ("alesatura", "alesatura"),
        ("finishing insert", "inserto da finitura"),
    )
    result=[]
    for part in parts:
        low=part.casefold()
        for token, label in allowed:
            if token in low and label not in result:
                result.append(label)
    return " · ".join(result[:2])

def translate_row_fields(row):
    code = row.get("code", row.get("itemCode", ""))
    for field in ("material", "cuttingConditions"):
        if isinstance(row.get(field), str):
            row[field] = technical_italian(row[field])
    if isinstance(row.get("geom"), str):
        row["geom"] = clean_geometry(row["geom"], code)
    if isinstance(row.get("application"), str):
        row["application"] = clean_application(row["application"])
    # Preserve source evidence, but do not expose noisy dimension-table headers as cutting parameters.
    if isinstance(row.get("recommendedConditions"), list):
        for block in row["recommendedConditions"]:
            if isinstance(block, dict) and isinstance(block.get("raw"), str):
                block["raw"] = technical_italian(block["raw"])
    if isinstance(row.get("parameterRows"), list):
        row["parameterRows"] = [technical_italian(v) for v in row["parameterRows"] if isinstance(v, str) and len(v) < 180]
    return row


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00","Z")

def norm(s):
    return re.sub(r"[^A-Z0-9]", "", str(s or "").upper())

def clean_code(s):
    return re.sub(r"\s+", " ", str(s or "").strip())

def classify(code, context, source_category=""):
    c = clean_code(code).upper()
    t = str(context or "").lower()
    sc = str(source_category or "").lower()

    # The official Sumitomo insert catalog labels its pages as
    # "Tornitura · Inserto ufficiale". Treat that explicit source
    # classification as authoritative instead of requiring English
    # keywords to appear in the extracted page context.
    if "tornitura" in sc or "turning" in sc:
        if any(w in t for w in ("finish", "finishing", "finitura")):
            return "Tornitura · Finitura"
        if any(w in t for w in ("rough", "roughing", "sgross")):
            return "Tornitura · Sgrossatura"
        return "Tornitura · Media"

    if "filettatura" in sc or "thread" in sc:
        return "Filettatura"
    if "foratura" in sc or "drill" in sc:
        return "Foratura"
    if "fresatura" in sc or "mill" in sc:
        return "Fresatura"

    if TURNING.match(c):
        if any(w in t for w in ("finish", "finishing", "finitura")):
            return "Tornitura · Finitura"
        if any(w in t for w in ("rough", "roughing", "sgross")):
            return "Tornitura · Sgrossatura"
        return "Tornitura · Media"
    if THREADING.match(c) or any(w in t for w in ("threading insert", "filettatura", "thread insert")):
        return "Filettatura"
    if DRILLING.match(c) or any(w in t for w in ("drilling insert", "drill insert", "foratura")):
        return "Foratura"
    if MILLING.match(c) or any(w in t for w in ("milling insert", "milling cutter", "fresatura")):
        return "Fresatura"
    return None

def strong_insert_code(code):
    c = clean_code(code).upper()
    # ISO-like insert: shape + 5-11 alphanumeric body, optionally chipbreaker suffix.
    iso_ok = bool(re.fullmatch(r"[A-Z]{2,5} [0-9][0-9A-Z]{4,10}(?:-[0-9A-Z]{1,10})?", c) or
                  re.fullmatch(r"[A-Z]{2,5}[0-9][0-9A-Z]{4,10}(?:-[0-9A-Z]{1,10})?", c))
    # Threading catalogs often use order codes such as 16ER A60-CB.
    thread_ok = bool(re.fullmatch(r"(?:06|08|11|16|22|27|32|L?16)[EI]R?\s+[A-Z0-9]{2,8}(?:-[A-Z0-9]{1,10})?", c))
    if not (iso_ok or thread_ok):
        return False
    # Reject obvious grade/material labels.
    if c in {"SUMIBORON","SUMIDIA","SUMICRYSTAL"} or re.fullmatch(r"[A-Z]{1,5}[0-9]{2,6}[A-Z]?", c):
        return False
    return True

def main():
    staging = json.loads(STAGING.read_text(encoding="utf-8"))
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    tools_pack = json.loads(TOOLS.read_text(encoding="utf-8"))
    items = list(catalog.get("items", []))
    tool_items = list(tools_pack.get("items", []))
    # Porta in italiano i campi descrittivi mostrati a schermo, preservando codici e valori numerici.
    items = [translate_row_fields(dict(x)) for x in items if isinstance(x, dict)]
    tool_items = [translate_row_fields(dict(x)) for x in tool_items if isinstance(x, dict)]
    # Filter and canonicalize existing records; backups below retain the full pre-change data.
    items = [dict(x, maker=canonical_maker(x.get("maker"))) for x in items if canonical_maker(x.get("maker"))]
    tool_items = [dict(x, maker=canonical_maker(x.get("maker"))) for x in tool_items if canonical_maker(x.get("maker"))]

    # Remove pre-existing duplicates by canonical manufacturer + normalized item code.
    # Keep the first stable row and merge only meaningful fields from duplicate rows.
    def meaningful_value(v):
        if v is None:
            return False
        if isinstance(v, str):
            return bool(v.strip()) and v.strip() not in {"—", "-", "N/A", "n/a", "null"}
        if isinstance(v, (list, dict)):
            return bool(v)
        return True

    def deduplicate_rows(rows):
        unique = []
        index = {}
        removed = 0
        merged_fields = 0
        mergeable = (
            "geom", "material", "application", "cuttingConditions",
            "recommendedConditions", "parameterRows", "vc", "f", "ap",
            "sourceOfficial", "sourceType", "sourcePage", "sourceContext",
            "sourceUrl", "parameterStatus", "verificationStatus"
        )
        for row in rows:
            code_key = norm(row.get("code"))
            maker_key = str(row.get("maker", "")).strip().casefold()
            if not code_key or not maker_key:
                unique.append(row)
                continue
            key = (maker_key, code_key)
            if key not in index:
                index[key] = row
                unique.append(row)
                continue
            removed += 1
            target = index[key]
            for field in mergeable:
                incoming = row.get(field)
                current = target.get(field)
                if not meaningful_value(incoming):
                    continue
                if not meaningful_value(current):
                    target[field] = incoming
                    merged_fields += 1
                elif field == "recommendedConditions" and isinstance(incoming, list) and isinstance(current, list) and len(incoming) > len(current):
                    target[field] = incoming
                    merged_fields += 1
                elif field == "parameterRows" and isinstance(incoming, list) and isinstance(current, list) and len(incoming) > len(current):
                    target[field] = incoming
                    merged_fields += 1
                elif field == "cuttingConditions" and isinstance(incoming, str) and isinstance(current, str) and len(incoming) > len(current):
                    target[field] = incoming
                    merged_fields += 1
            # Prefer the more informative category if the retained row has none.
            if not target.get("category") and row.get("category"):
                target["category"] = row["category"]
        return unique, removed, merged_fields

    items, duplicate_catalog_rows_removed, duplicate_catalog_fields_merged = deduplicate_rows(items)
    tool_items, duplicate_tool_rows_removed, duplicate_tool_fields_merged = deduplicate_rows(tool_items)

    # Preserve verified product image metadata; technical cleanup must not strip photos.
    # Normalize the parameter schema on legacy complete-tool rows without inventing values.
    for x in tool_items:
        if x.get("toolType") == "complete-tool":
            x.setdefault("parameterStatus", "pending-official-exact")
            x.setdefault("cuttingConditions", "")
    BACKUP.parent.mkdir(parents=True, exist_ok=True)
    BACKUP.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    TOOLS_BACKUP.write_text(json.dumps(tools_pack, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # Index existing rows once. A linear scan for every duplicate made the
    # promotion step quadratic and could stall the hourly publication pipeline.
    existing_rows = {(str(x.get("maker","")).strip().lower(), norm(x.get("code"))): x for x in items}
    existing = set(existing_rows)
    existing_tools = {(str(x.get("maker","")).strip().lower(), norm(x.get("code"))) for x in tool_items}
    promoted, promoted_tools, skipped, duplicates, tool_duplicates = [], [], [], 0, 0
    enriched, enriched_fields = [], 0

    for cand in staging.get("items", []):
        candidate_scope = str(cand.get("scope","")).lower()
        candidate_type = str(cand.get("toolType","")).lower()
        candidate_category = str(cand.get("category","")).lower()
        is_insert_candidate = (
            candidate_scope == "inserts"
            or candidate_type == "insert"
            or "inserto" in candidate_category
            or candidate_category.strip() == "inserts"
        )
        code = clean_code(cand.get("code"))
        maker = canonical_maker(cand.get("maker"))
        if not maker:
            skipped.append({"code": code, "reason": "manufacturer-not-in-selected-seven"})
            continue
        category = classify(code, cand.get("sourceContext",""), cand.get("category",""))

        if is_insert_candidate:
            if not maker or not strong_insert_code(code):
                skipped.append({"code": code, "reason": "weak-code"})
                continue
            if not category:
                skipped.append({"code": code, "reason": "category-ambiguous"})
                continue
            key = (maker.lower(), norm(code))
            if key in existing:
                duplicates += 1
                # Existing rows may predate the richer official extractor.
                # Do not leave a verified code permanently "empty": merge every
                # non-empty official field into the visible row, without inventing
                # values or overwriting stronger existing evidence with blanks.
                target = existing_rows.get(key)
                if target is not None:
                    before = dict(target)
                    def meaningful(v):
                        if v is None:
                            return False
                        if isinstance(v, str):
                            return bool(v.strip()) and v.strip() not in {"—", "-", "N/A", "n/a"}
                        if isinstance(v, list):
                            return bool(v)
                        return True
                    field_map = (
                        "geom","material","application","cuttingConditions",
                        "recommendedConditions","parameterRows","vc","f","ap","sourceOfficial",
                        "sourceType","sourcePage","sourceContext","sourceUrl",
                        "parameterStatus"
                    )
                    for field in field_map:
                        incoming = cand.get(field)
                        if meaningful(incoming):
                            current = target.get(field)
                            if (not meaningful(current)) or (
                                field == "recommendedConditions"
                                and isinstance(incoming, list)
                                and len(incoming) > (len(current) if isinstance(current, list) else 0)
                            ) or (
                                field == "cuttingConditions"
                                and isinstance(incoming, str)
                                and len(incoming) > len(str(current or ""))
                            ):
                                target[field] = incoming
                    changed_fields = [k for k in field_map if target.get(k) != before.get(k)]
                    if changed_fields:
                        enriched.append({"maker": maker, "code": code, "fields": changed_fields})
                        enriched_fields += len(changed_fields)
                continue
            row = {
                "category": category,
                "code": code,
                "maker": maker,
                "verificationStatus": "official-order-code-verified",
                "sourceOfficial": cand.get("sourceOfficial", True),
                "sourceType": cand.get("sourceType", "official-catalog"),
                "sourcePage": cand.get("sourcePage"),
                "sourceContext": cand.get("sourceContext",""),
                "geom": cand.get("geom",""),
                "material": cand.get("material",""),
                "application": cand.get("application",""),
                "cuttingConditions": cand.get("cuttingConditions",""),
                "recommendedConditions": cand.get("recommendedConditions", []),
                "parameterRows": cand.get("parameterRows", []),
                "parameterStatus": cand.get("parameterStatus","not-found"),
                "vc": cand.get("vc","—"),
                "f": cand.get("f","—"),
                "ap": cand.get("ap","—"),
                "photoStatus": "unavailable",
                "photoNote": "Foto esatta non ancora verificata; nessun logo o immagine generica usata."
            }
            if cand.get("sourceUrl"):
                row["sourceUrl"] = cand["sourceUrl"]
            items.append(row)
            existing.add(key)
            existing_rows[key] = row
            promoted.append({"maker": maker, "code": code, "category": category, "sourcePage": cand.get("sourcePage")})
            continue

        if not maker or len(code) < 5 or not re.search(r"[A-Z0-9]", code):
            skipped.append({"code": code, "reason": "weak-tool-code"})
            continue
        # Classifica gli utensili completi dalla famiglia della fonte ufficiale,
        # evitando che alesatori e utensili di filettatura finiscano in fresatura.
        source_label = str(cand.get("category","")).casefold()
        if any(w in source_label for w in ("alesatura", "ream", "boring")):
            tool_category = "Alesatura · Utensili completi"
        elif any(w in source_label for w in ("filettatura", "thread")):
            tool_category = "Filettatura · Utensili completi"
        elif any(w in source_label for w in ("scanalatura", "grooving", "parting")):
            tool_category = "Scanalatura · Utensili completi"
        elif any(w in source_label for w in ("tornitura", "turning")):
            tool_category = "Tornitura · Utensili completi"
        elif any(w in source_label for w in ("foratura", "drill", "holemaking")):
            tool_category = "Foratura · Utensili completi"
        elif any(w in source_label for w in ("dentatura", "gear")):
            tool_category = "Dentatura · Utensili completi"
        else:
            tool_category = "Fresatura · Utensili completi"
        tkey = (maker.lower(), norm(code))
        if tkey in existing_tools:
            tool_duplicates += 1
            continue
        tool_items.append({
            "category": tool_category,
            "code": code,
            "geom": "Utensile completo — dati da catalogo ufficiale",
            "material": "—",
            "vc": "—",
            "f": "—",
            "ap": "—",
            "maker": maker,
            "productUrl": cand.get("sourceOfficial"),
            "sourceOfficial": cand.get("sourceOfficial"),
            "sourcePage": cand.get("sourcePage"),
            "sourceContext": cand.get("sourceContext",""),
            "geom": cand.get("geom",""),
            "material": cand.get("material",""),
            "application": cand.get("application",""),
            "cuttingConditions": cand.get("cuttingConditions",""),
            "recommendedConditions": cand.get("recommendedConditions", []),
            "parameterRows": cand.get("parameterRows", []),
            "parameterStatus": cand.get("parameterStatus","not-found"),
            "vc": cand.get("vc","—"),
            "f": cand.get("f","—"),
            "ap": cand.get("ap","—"),
            "photoNote": "Nessuna foto reale verificata per il codice esatto; nessuna immagine generica usata.",
            "photoStatus": "unavailable",
            "toolType": "complete-tool",
            "verificationStatus": "official-catalog-extracted",
            "sourceNote": "Codice importato articolo per articolo dal catalogo ufficiale; resta marcato come estratto finché la riga ordine esatta non viene verificata."
        })
        existing_tools.add(tkey)
        promoted_tools.append({"maker": maker, "code": code, "category": tool_category, "sourcePage": cand.get("sourcePage")})

    def sort_key(x):
        return (ALLOWED.index(x.get("category")) if x.get("category") in ALLOWED else 99,
                str(x.get("maker","")).lower(), norm(x.get("code")))

    items.sort(key=sort_key)
    catalog["items"] = items
    catalog["version"] = "4.2-official-staging-promotion-all-items"
    catalog["updatedAt"] = now()
    tools_pack["items"] = tool_items
    tools_pack["version"] = "1.1-official-catalog-item-import"
    tools_pack["updatedAt"] = now()
    tools_pack["status"] = "official-catalog-item-import-in-progress"
    catalog["source"] = "Catalogo globale: promozione conservativa da cataloghi ufficiali correnti; nessun codice inventato."
    CATALOG.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    TOOLS.write_text(json.dumps(tools_pack, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    report = {
        "updatedAt": now(),
        "stagingItems": len(staging.get("items", [])),
        "promoted": len(promoted),
        "promotedCompleteTools": len(promoted_tools),
        "enrichedExisting": len(enriched),
        "enrichedFields": enriched_fields,
        "enrichedSample": enriched[:50],
        "duplicates": duplicates,
        "completeToolDuplicates": tool_duplicates,
        "existingCatalogDuplicatesRemoved": duplicate_catalog_rows_removed,
        "existingCatalogDuplicateFieldsMerged": duplicate_catalog_fields_merged,
        "existingCompleteToolDuplicatesRemoved": duplicate_tool_rows_removed,
        "existingCompleteToolDuplicateFieldsMerged": duplicate_tool_fields_merged,
        "skipped": len(skipped),
        "catalogItemsAfter": len(items),
        "completeToolsAfter": len(tool_items),
        "policy": "Codici e utensili completi estratti da fonti ufficiali; famiglie distinte, ambigui mantenuti in staging e parametri mancanti non inventati.",
        "promotedSample": promoted[:50],
        "promotedCompleteToolsSample": promoted_tools[:50],
        "skippedReasons": {r: sum(1 for x in skipped if x["reason"] == r) for r in sorted({x["reason"] for x in skipped})}
    }
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))

if __name__ == "__main__":
    main()

