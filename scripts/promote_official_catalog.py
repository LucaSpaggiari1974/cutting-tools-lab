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
TURNING = re.compile(r"^(CNMG|DNMG|SNMG|TNMG|VNMG|WNMG|CCMT|DCMT|TCMT|VCMT|VBMT|VBGT|CCGT|DCGT|TCGT|VCGT|CNGA|DNGA|TNGA|VNGA|WNGA)\b", re.I)
MILLING = re.compile(r"^(APMT|APKT|SEHT|SEKT|RDMW|RPMT|SPMT|SOMT|XPMT|LNMU|ADMX|SDMT|SDXT|ONHU|ODMX|XDET|LOGX)\b", re.I)
DRILLING = re.compile(r"^(WCMX|SPMX|SCMX|SOMX|XCMT|XOMX|WCMT)\b", re.I)
THREADING = re.compile(r"^(16ER|16IR|11ER|11IR|22ER|22IR|27ER|27IR|08ER|08IR|06ER|06IR)\b", re.I)

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
    # Normalize the parameter schema on legacy complete-tool rows without inventing values.
    for x in tool_items:
        if x.get("toolType") == "complete-tool":
            x.setdefault("parameterStatus", "pending-official-exact")
            x.setdefault("cuttingConditions", "")
    BACKUP.parent.mkdir(parents=True, exist_ok=True)
    BACKUP.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    TOOLS_BACKUP.write_text(json.dumps(tools_pack, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    existing = {(str(x.get("maker","")).strip().lower(), norm(x.get("code"))) for x in items}
    existing_tools = {(str(x.get("maker","")).strip().lower(), norm(x.get("code"))) for x in tool_items}
    promoted, promoted_tools, skipped, duplicates, tool_duplicates = [], [], [], 0, 0

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
        maker = str(cand.get("maker","")).strip()
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
            promoted.append({"maker": maker, "code": code, "category": category, "sourcePage": cand.get("sourcePage")})
            continue

        if not maker or len(code) < 5 or not re.search(r"[A-Z0-9]", code):
            skipped.append({"code": code, "reason": "weak-tool-code"})
            continue
        tool_category = category or (
            "Foratura · Utensili completi" if any(w in str(cand.get("category","")).lower() for w in ("drill","foratura","hole"))
            else "Fresatura · Utensili completi"
        )
        if tool_category not in {
            "Fresatura · Utensili completi","Foratura · Utensili completi",
            "Alesatura · Utensili completi","Filettatura · Utensili completi",
            "Tornitura · Utensili completi","Scanalatura · Utensili completi"
        }:
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
        "duplicates": duplicates,
        "completeToolDuplicates": tool_duplicates,
        "skipped": len(skipped),
        "catalogItemsAfter": len(items),
        "completeToolsAfter": len(tool_items),
        "policy": "Solo codici forti provenienti da scope inserts ufficiale; ambigui mantenuti in staging.",
        "promotedSample": promoted[:50],
        "promotedCompleteToolsSample": promoted_tools[:50],
        "skippedReasons": {r: sum(1 for x in skipped if x["reason"] == r) for r in sorted({x["reason"] for x in skipped})}
    }
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))

if __name__ == "__main__":
    main()

