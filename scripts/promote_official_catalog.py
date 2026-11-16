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
    "Tornitura · Finitura", "Tornitura · Media", "Tornitura · Sgrossatura", "Tornitura · Impiego da verificare",
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
    """Mostra solo forma e raggio; elimina parole di impiego e intestazioni estratte dai PDF."""
    text = technical_italian(value)
    text = re.sub(r"\s+", " ", text).strip(" ·|")
    low = text.casefold()
    junk = ("part number", "numero parte", "series ", "serie ", "no. of", "number of",
            "cutting dia", "diametro di taglio", "thickness", "spessore", "grade", "grades",
            "insert length", "insert width", "corner radius", "wiper radius", "profile radius",
            "geometry.", "geometria.", "relief angle", "angle of", "products", "metric",
            "ing ersoll", "ingersoll-imc.com", "apmx", "pfrad", "bsr", "re2")
    if not text or any(token in low for token in junk) or len(text) > 90:
        text = ""
    # L’impiego (finitura/media/sgrossatura) va nel campo dedicato, non nella geometria.
    text = re.sub(r"\b(finitura|media|sgrossatura|finitura/media|media/finitura|universale|profilatura)\b", "", text, flags=re.I)
    text = re.sub(r"\s*[·|/]+\s*", " · ", text)
    text = re.sub(r"\s+", " ", text).strip(" ·")
    # Conserva solo forma e raggio punta, se presenti.
    shape_match = re.search(r"(Rombo 80°|Rombo 55°|Rombo 35°|Rombo 86°|Trigon 80°|Quadrato 90°|Triangolo 60°|Tondo|Pentagonale|Parallelogramma|Rettangolo)", text, re.I)
    radius_match = re.search(r"\bR\s*([0-9]+(?:[,.][0-9]+)?)\b", text, re.I)
    parts = []
    if shape_match: parts.append(shape_match.group(1))
    if radius_match: parts.append("R" + radius_match.group(1).replace(".", ","))
    if parts: return " · ".join(parts)
    if not text:
        compact_code = re.sub(r"\s+", "", str(code or "").upper())
        iso_prefix = re.match(r"^(CNMG|DNMG|SNMG|TNMG|VNMG|WNMG|CCMT|CCGT|DCMT|DCGT|TCMT|TCGT|VCMT|VCGT|VBMT|VBGT|SCMT|SPMT|WCMX|SPMX|SCMX|CNGA|DNGA|TNGA|VNGA|WNGA)", compact_code)
        shape = {"C":"Rombo 80°", "D":"Rombo 55°", "V":"Rombo 35°", "W":"Trigon 80°", "S":"Quadrato 90°", "T":"Triangolo 60°", "R":"Tondo"}.get(iso_prefix.group(1)[0]) if iso_prefix else None
        return shape or ""
    return text[:50]
def clean_application(value):
    """Restituisce un impiego breve e coerente, senza intestazioni o frasi copiate dal PDF."""
    text = technical_italian(value).casefold()
    operation = ""
    if re.search(r"\b(threading|thread insert|thread mill|filettatura)\b", text): operation = "Filettatura"
    elif re.search(r"\b(drilling|holemaking|deep hole|reaming|foratura|alesatura)\b", text): operation = "Foratura"
    elif re.search(r"\b(milling|lens type|chamfer barrel|barrel type|fresatura)\b", text): operation = "Fresatura"
    elif re.search(r"\b(grooving|parting|scanalatura|troncatura)\b", text): operation = "Scanalatura"
    elif re.search(r"\b(turning|tornitura|profiling|profilatura)\b", text): operation = "Tornitura"
    phase = ""
    if re.search(r"\b(finishing|finish|finitura)\b", text): phase = "Finitura"
    elif re.search(r"\b(roughing|rough|sgrossatura)\b", text): phase = "Sgrossatura"
    elif re.search(r"\b(medium|media)\b", text): phase = "Media"
    if operation and phase: return operation + " · " + phase
    return operation or phase
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

    if source_category == "Tornitura · Impiego da verificare":
        return source_category

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

# Product types checked against the official WinSFeed order and hardware tables.
WIN_S_FEED = "https://ssl.ingersoll-imc.com/resources/pdf/cat-031-1_winsfeed_new_products_catalog_2024.pdf"
VERIFIED_INGERSOLL_MILLS = {
    **{f"DG6G{d}R00": "https://www.ingersoll-imc.com/product-family/5356507" for d in ("050","063","080","100")},
    **{f"DJ5R{d}R00": "https://ingersoll-imc.com/product-family/5348409" for d in ("040","063","080","100","125")},
    **{f"DJ6R{d}R00": "https://ingersoll-imc.com/product-family/5348409" for d in ("050","063","080","100","125")},
    **{f"{series}{diameter}R00": WIN_S_FEED for series, diameters in {
        "DN5G": ("040", "050", "063", "080", "100", "125", "160"),
        "DN6G": ("040", "050", "063", "080", "100", "125", "160"),
        "DN5K": ("050", "063", "080", "100", "125", "160", "200"),
        "DN6K": ("050", "063", "080", "100", "125", "160", "200"),
        "DG6K": ("063", "080", "100", "125"),
    }.items() for diameter in diameters},
}
INGERSOLL_NON_CUTTING_CODES = {
    "IL61108", "TS35110IL", "SHM16X2X35", "SHM16X2X35C",
    "SHLM16X2X35", "SHLM16X2X35C", "DIN6987140", "DIN6987150",
    "TS35083I", "TSTV210510", "SHM6X1X16", "TSZ140310", "SO35124I",
    "TS5035062S", "SO35080I", "TS18049", "TS20055I", "TS40F120A",
}
INGERSOLL_CODE_ALIASES = {"CGM101R001": "CGM101R001-ML", "CGX101R001": "CGX101R001-M"}

def verified_mill_source(maker, code):
    return VERIFIED_INGERSOLL_MILLS.get(norm(code)) if canonical_maker(maker) == "Ingersoll" else None

def verified_turning_holder(maker, code):
    return maker == "Ingersoll" and norm(code) == "LVJBR1616K16SH"

PCD_SOURCE = "https://ssl.ingersoll-imc.com/resources/pdf/it.te.di.-pcd-iso-inserts-catalog.pdf"
PCD_CONDITIONS = [
    {"material": m, "operation": o, "vc": v, "fn": f, "ap": a}
    for m, o, v, f, a in [
        ("Alluminio, Si <12%", "Sgrossatura", "800–3000", "0,1–0,6", "0,3–5,0"),
        ("Alluminio, Si <12%", "Finitura", "800–3000", "0,03–0,2", "0,05–1,0"),
        ("Alluminio, Si >12%", "Sgrossatura", "300–900", "0,1–0,4", "0,1–2,5"),
        ("Alluminio, Si >12%", "Finitura", "300–900", "0,03–0,2", "0,05–0,08"),
        ("Rame, bronzo, ottone, zinco e leghe di magnesio", "Sgrossatura", "600–1200", "0,1–0,4", "0,5–2,0"),
        ("Rame, bronzo, ottone, zinco e leghe di magnesio", "Finitura", "700–1500", "0,05–0,4", "0,05–0,5"),
        ("Metallo duro", "Sgrossatura", "20–25", "0,1–0,3", "0,1–0,5"),
        ("Metallo duro", "Finitura", "20–30", "0,05–0,2", "0,05–0,2"),
    ]
]

def normalize_ingersoll_insert(row):
    if row.get("sourceOfficial") == PCD_SOURCE:
        row["familyConditions"] = PCD_CONDITIONS
        row["familyConditionsSource"] = PCD_SOURCE + "#page=35"
        row["familyConditionsNote"] = "Guida generale PCD in condizioni ottimali. Verificare grado e geometria. Le geometrie FI/RO richiedono anche le indicazioni specifiche della stessa pagina."

    code = norm(row.get("code"))
    if code in INGERSOLL_NON_CUTTING_CODES or code in INGERSOLL_CODE_ALIASES:
        return False
    # NEW-221-5 (2016), pp. 5–7: exact GoldTwin codes and system conditions.
    # Do not infer other SPGX codes or confuse axial hole depth with ap.
    gold_sizes = {"SPGX060204WG": 0, "SPGX07T308WG": 1,
                  "SPGX090408WG": 2, "SPGX110408WG": 3}
    if code in gold_sizes:
        source = "https://ssl.ingersoll-imc.com/resources/pdf/NEW-221-5_Gold-Twin.pdf"
        idx = gold_sizes[code]
        diameters = ["26–28,9", "29–32,9", "33–36,9", "37–43,9", "44–45,9"]
        # Original SFM and inch/rev, converted to metric; preserve diameter bands.
        groups = [
            ("Acciai non legati ricotti, 125–190 HB", 390, 650, [(8,11,14),(10,12,14),(8,12,16),(10,13,16),(11,15,18)]),
            ("Acciai non legati, 220–300 HB", 425, 625, [(8,11,14),(10,12,14),(8,12,16),(10,13,16),(11,15,18)]),
            ("Acciai basso legati, 200–350 HB", 325, 650, [(8,11,13),(10,11,13),(10,12,14),(10,12,14),(10,13,16)]),
            ("Acciai alto legati e da utensili, 200–325 HB", 325, 525, [(8,11,13),(10,11,13),(10,12,14),(10,12,14),(10,13,16)]),
            ("Inossidabili, 180–240 HB", 260, 460, [(5,8,10),(6,8,10),(6,8,10),(7,9,11),(7,10,12)]),
            ("Ghise, 130–260 HB", 325, 825, [(10,14,18),(10,14,18),(12,16,20),(12,16,20),(14,18,22)]),
            ("Leghe di alluminio e rame, 60–130 HB", 525, 850, [(12,16,20),(12,16,20),(14,18,22),(14,18,22),(16,20,24)]),
            ("Superleghe ferrose ricotte, 200 HB", 100, 200, [(4,5,6),(4,6,7),(6,7,8),(6,7,9),(6,8,9)]),
            ("Altre superleghe e titanio (vedere condizioni fonte)", 100, 265, [(4,5,6),(4,6,7),(6,7,8),(6,7,9),(6,8,9)]),
        ]
        def metric(value, factor, decimals):
            return f"{value * factor:.{decimals}f}".replace(".", ",")
        row.update(category="Foratura", application="Foratura GoldTwin", material="Acciai; inossidabili; ghise; leghe non ferrose; superleghe", geom="Quadrato a 4 taglienti, wiper", grade="IN2505")
        row["familyConditions"] = [
            {"material": material, "operation": "Foratura Ø " + diameters[j] + " mm",
             "vc": metric(lo, .3048, 1) + "–" + metric(hi, .3048, 1),
             "fn": " / ".join(metric(v, .0254, 3) for v in feeds[j]), "ap": ""}
            for j in ([3, 4] if idx == 3 else [idx])
            for material, lo, hi, feeds in groups
        ]
        row["familyConditionsSource"] = source + "#page=7"
        row["familyConditionsNote"] = "Condizioni del sistema GoldTwin IN2505 per diametro; VC in m/min, FN in mm/giro (tre valori tabellati). Profondità del foro dipendente dal corpo, AP non applicabile. Consultare durezza e condizioni esatte nella fonte."
        row.setdefault("parameterSources", {}).update({
            "geom": {"url": source + "#page=2"},
            "grade": {"url": source + "#page=6"},
            "material": {"url": source + "#page=7"}
        })
    if "Tornitura" in str(row.get("category")) and row.get("verificationStatus") in {
        "official-catalog-code-extracted-needs-technical-verification", "official-catalog-extracted"
    }:
        row["category"] = "Tornitura · Impiego da verificare"
        row["application"] = "Tornitura · Impiego da verificare"
    # Exact MT order variants; grade-specific VC from OPG-007-1 (2025).
    mt_grades = {
        "TT8105B": (6212536, "P01–P15", [(1015,1900),(885,1740),(755,1605),(820,1640),(690,1540),(755,1805),(590,1080),(525,985),(490,920),(690,1380),(330,655)]),
        "TT8115B": (6212574, "P05–P20", [(920,1740),(785,1575),(655,1445),(720,1475),(590,1380),(655,1640),(490,920),(425,820),(395,755),(625,1245),(295,590)]),
        "TT8125B": (6213016, "P15–P30", [(755,1575),(655,1380),(525,1245),(625,1310),(490,1150),(560,1310),(460,820),(395,755),(360,655),(460,920),(230,425)]),
    }
    for grade, (edp, iso_range, speeds) in mt_grades.items():
        if code != norm("CNMG160612MT " + grade):
            continue
        product = "https://www.ingersoll-imc.com/product/" + str(edp)
        guide = "https://ssl.ingersoll-imc.com/resources/pdf/opg-007-1_iso-turning.pdf"
        grade_source = "https://www.ingersoll-imc.com/product-lines/tt81xx-turning-grades"
        row.update(category="Tornitura · Media", application="Tornitura media", grade=grade,
                   material="Acciai (ISO " + iso_range + ")", geom="Rombo 80° · R1,2",
                   f="0,229–0,559", ap="2,007–6,502")
        row["familyConditions"] = [
            {"material": "Acciai · gruppo VDI 3323 " + str(i),
             "operation": "Tornitura ISO · grado " + grade,
             "vc": (f"{lo * .3048:.1f}–{hi * .3048:.1f}").replace(".", ","),
             "fn": "", "ap": ""}
            for i, (lo, hi) in enumerate(speeds, 1)
        ]
        row["familyConditionsSource"] = guide
        row["familyConditionsNote"] = "VC in m/min per grado e gruppo VDI 3323; identificare il gruppo esatto nella guida. FN e AP della scheda articolo sono intervalli geometrici, non condizioni simultanee garantite."
        row.setdefault("parameterSources", {}).update({
            "f": {"url": product, "unit": "mm/giro"},
            "ap": {"url": product, "unit": "mm"},
            "geom": {"url": product},
            "grade": {"url": product},
            "material": {"url": grade_source}
        })
        row["parameterStatus"] = "official-item-feed-depth-and-grade-speed-verified"
        row["verificationStatus"] = "official-product-verified"
        break
    # Additional exact MT variants; VDI groups are explicit (blank cells omitted).
    mt_additional = {
        "TT5100": (5515314, [[1,655,1475],[2,560,1280],[3,425,1150],[4,525,1215],[5,395,1050],[6,460,1215],[7,360,720],[8,295,655],[9,260,560],[10,360,820],[11,130,330]]),
        "TT8020": (5515896, [[1,330,985],[2,330,885],[3,260,655],[4,295,690],[5,260,590],[6,260,655],[7,130,395],[8,130,295],[9,100,295],[10,195,525],[11,130,260],[12,330,820],[13,330,755],[14,260,655],[31,65,230],[32,35,165],[33,35,130],[34,35,100],[35,35,65],[36,230,490],[37,65,130]]),
        "TT5080": (5523019, [[12,525,1280],[13,525,920],[14,330,820],[31,165,590],[32,130,525],[33,150,330],[34,115,295],[35,100,260],[36,360,655],[37,165,330]]),
        "TT9080": (6100877, [[12,395,950],[13,395,885],[14,295,785],[31,130,525],[32,100,425],[33,115,260],[34,100,230],[35,100,195],[36,295,590],[37,130,260]]),
    }
    for grade, (edp, speeds) in mt_additional.items():
        if code != norm("CNMG160612MT " + grade):
            continue
        product = "https://www.ingersoll-imc.com/product/" + str(edp)
        guide = "https://ssl.ingersoll-imc.com/resources/pdf/opg-007-1_iso-turning.pdf"
        def mt_material(i):
            return "Acciai" if i <= 11 else "Inossidabili" if i <= 14 else "Titanio e leghe di titanio" if i >= 36 else "Superleghe"
        row.update(category="Tornitura · Media", application="Tornitura media", grade=grade,
                   material="; ".join(dict.fromkeys(mt_material(i) for i, lo, hi in speeds)),
                   geom="Rombo 80° · R1,2", f="0,229–0,559", ap="2,007–6,502")
        row["familyConditions"] = [
            {"material": mt_material(i) + " · gruppo VDI 3323 " + str(i),
             "operation": "Tornitura ISO · grado " + grade,
             "vc": (f"{lo * .3048:.1f}–{hi * .3048:.1f}").replace(".", ","),
             "fn": "", "ap": ""}
            for i, lo, hi in speeds
        ]
        row["familyConditionsSource"] = guide
        row["familyConditionsNote"] = "VC in m/min per grado e gruppo VDI; verificare compatibilità geometria/materiale e condizioni reali. FN e AP della scheda articolo non sono condizioni simultanee garantite."
        row.setdefault("parameterSources", {}).update({
            "f": {"url": product, "unit": "mm/giro"},
            "ap": {"url": product, "unit": "mm"},
            "geom": {"url": product},
            "grade": {"url": product},
            "material": {"url": guide}
        })
        row["parameterStatus"] = "official-item-feed-depth-and-grade-speed-verified"
        row["verificationStatus"] = "official-product-verified"
        break
    # CAT-30-3, pages 7 and 51: chipbreaker-specific application and depth.
    # These values do not determine the workpiece material or CBN grade.
    if str(row.get("sourceOfficial", "")).endswith("/cat-30-3-cbn-inserts-catalog.pdf"):
        chipbreaker = re.search(r"([FMR]1)", code)
        if chipbreaker:
            profiles = {
                "F1": ("Tornitura · Finitura", "Finitura e lavorazione media", "0,04–0,10"),
                "M1": ("Tornitura · Media", "Lavorazione media", "0,10–0,20"),
                "R1": ("Tornitura · Sgrossatura", "Sgrossatura", "0,20–0,40"),
            }
            category, application, depth = profiles[chipbreaker.group(1)]
            row.update(category=category, application=application, ap=depth)
            row["parameterStatus"] = "official-chipbreaker-depth-verified"
            row["parameterSources"] = {"ap": {
                "url": row["sourceOfficial"] + "#page=51",
                "page": 51, "chipbreaker": chipbreaker.group(1), "unit": "mm"
            }}
    return True

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
            "geom", "grade", "material", "application", "cuttingConditions",
            "parameterSources", "familyConditions", "familyConditionsSource", "familyConditionsNote",
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

    items = [row for row in items if row["maker"] != "Ingersoll" or normalize_ingersoll_insert(row)]
    tool_items = [row for row in tool_items if row["maker"] != "Ingersoll" or (
        norm(row.get("code")) not in INGERSOLL_NON_CUTTING_CODES
        and norm(row.get("code")) not in INGERSOLL_CODE_ALIASES
    )]
    items, duplicate_catalog_rows_removed, duplicate_catalog_fields_merged = deduplicate_rows(items)
    tool_items, duplicate_tool_rows_removed, duplicate_tool_fields_merged = deduplicate_rows(tool_items)

    # Move verified complete mills out of the insert catalog, preserving their records.
    reclassified = []
    tool_keys = {(x.get("maker"), norm(x.get("code"))) for x in tool_items}
    retained = []
    for row in items:
        source = verified_mill_source(row.get("maker"), row.get("code"))
        turning_holder = verified_turning_holder(row.get("maker"), row.get("code"))
        if turning_holder:
            source = WIN_S_FEED
        if not source:
            retained.append(row)
            continue
        key = (row.get("maker"), norm(row.get("code")))
        if key not in tool_keys:
            operation = "Tornitura" if turning_holder else "Fresatura"
            tool_items.append(dict(row, category=f"{operation} · Utensili completi",
                toolType="complete-tool", sourceUrl=source, productUrl=source,
                geom="", material="", vc="—", f="—", ap="—",
                cuttingConditions="", recommendedConditions=[], parameterRows=[],
                application=operation, parameterStatus="pending-official-exact",
                verificationStatus="official-product-type-verified"))
            tool_keys.add(key)
        reclassified.append(row.get("code"))
    items = retained

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
        cand = translate_row_fields(dict(cand))
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
        if maker == "Ingersoll" and not normalize_ingersoll_insert(cand):
            skipped.append({"code": code, "reason": "non-cutting-or-incomplete-code"})
            continue
        category = classify(code, cand.get("sourceContext",""), cand.get("category",""))

        turning_holder = verified_turning_holder(maker, code)
        if turning_holder or verified_mill_source(maker, code):
            is_insert_candidate = False
            cand["category"] = "Tornitura" if turning_holder else "Fresatura"
            cand["sourceOfficial"] = WIN_S_FEED if turning_holder else verified_mill_source(maker, code)
            for field in ("geom", "material", "cuttingConditions", "recommendedConditions", "parameterRows", "vc", "f", "ap"):
                cand.pop(field, None)
            cand["application"] = cand["category"]
            cand["parameterStatus"] = "pending-official-exact"
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
                        if isinstance(v, (list, dict)):
                            return bool(v)
                        return True
                    field_map = (
                        "geom","grade","material","application","cuttingConditions",
                        "recommendedConditions","parameterRows","vc","f","ap","sourceOfficial",
                        "sourceType","sourcePage","sourceContext","sourceUrl",
                        "parameterStatus", "parameterSources", "familyConditions", "familyConditionsSource", "familyConditionsNote"
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
                    # Aggiorna la categoria quando la classificazione ufficiale è più specifica.
                    if cand.get("category") in ALLOWED and target.get("category") != cand.get("category"):
                        target["category"] = cand["category"]
                    changed_fields = [k for k in field_map if target.get(k) != before.get(k)]
                    if target.get("category") != before.get("category"):
                        changed_fields.append("category")
                    if changed_fields:
                        enriched.append({"maker": maker, "code": code, "fields": changed_fields})
                        enriched_fields += len(changed_fields)
                continue
            row = {
                "category": category,
                "code": code,
                "maker": maker,
                "verificationStatus": ("official-order-code-verified"
                    if cand.get("verificationStatus") == "official-order-code-verified"
                    else "official-catalog-code-extracted-needs-technical-verification"),
                "sourceOfficial": cand.get("sourceOfficial", True),
                "sourceType": cand.get("sourceType", "official-catalog"),
                "sourcePage": cand.get("sourcePage"),
                "sourceContext": cand.get("sourceContext",""),
                "geom": cand.get("geom",""),
                "grade": cand.get("grade",""),
                "material": cand.get("material",""),
                "application": cand.get("application",""),
                "cuttingConditions": cand.get("cuttingConditions",""),
                "recommendedConditions": cand.get("recommendedConditions", []),
                "parameterRows": cand.get("parameterRows", []),
                "parameterStatus": cand.get("parameterStatus","not-found"),
                "parameterSources": cand.get("parameterSources", {}),
                "familyConditions": cand.get("familyConditions", []),
                "familyConditionsSource": cand.get("familyConditionsSource", ""),
                "familyConditionsNote": cand.get("familyConditionsNote", ""),
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
        "reclassifiedVerifiedMills": reclassified,
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

