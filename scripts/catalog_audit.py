#!/usr/bin/env python3
"""Create a transparent catalog coverage and cutting-parameter audit."""
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
catalog = json.loads((ROOT / "catalog.json").read_text(encoding="utf-8"))
items = catalog.get("items", [])
makers = [
    "Sumitomo Electric Hardmetal", "Sandvik Coromant", "ISCAR", "Walter",
    "Seco Tools", "Tungaloy", "Ingersoll", "Kennametal", "TaeguTec",
    "Mitsubishi Materials", "Kyocera", "Ceratizit", "Dormer Pramet", "NTK", "ZCC"
]
by_maker = defaultdict(list)
for item in items:
    by_maker[str(item.get("maker", "UNKNOWN")).strip()].append(item)

def has_parameter(item, keys):
    for key in keys:
        value = item.get(key)
        if value not in (None, "", [], {}):
            return True
    return False

report = {
    "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
    "catalogUpdatedAt": catalog.get("updatedAt"),
    "totalItems": len(items),
    "manufacturers": {},
    "categories": dict(Counter(str(x.get("category", "UNKNOWN")) for x in items)),
    "notes": [
        "Counts describe records currently in catalog.json, not the entire manufacturer catalog.",
        "Parameter coverage is schema-based; it does not independently certify values against the source.",
        "KORLOY is intentionally excluded per catalog scope."
    ]
}
for maker in makers:
    rows = by_maker.get(maker, [])
    report["manufacturers"][maker] = {
        "items": len(rows),
        "withRecommendedConditions": sum(bool(x.get("recommendedConditions")) for x in rows),
        "withVc": sum(has_parameter(x, ["vc", "Vc", "cuttingSpeed", "recommendedVc"]) for x in rows),
        "withFeed": sum(has_parameter(x, ["f", "fz", "feed", "feedRate", "recommendedFeed"]) for x in rows),
        "withAp": sum(has_parameter(x, ["ap", "depthOfCut", "recommendedAp"]) for x in rows),
        "missingRecommendedConditions": sum(not bool(x.get("recommendedConditions")) for x in rows),
    }
(ROOT / "catalog-audit.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"Catalog audit: {len(items)} records")
for maker, stats in report["manufacturers"].items():
    print(f'{maker}: items={stats["items"]}, recommendedConditions={stats["withRecommendedConditions"]}, missing={stats["missingRecommendedConditions"]}')
