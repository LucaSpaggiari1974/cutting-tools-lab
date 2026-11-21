#!/usr/bin/env python3
"""Audit read-only del catalogo compresso; nessuna promozione automatica."""
import argparse
import gzip
import json
from collections import Counter
from pathlib import Path

def flatten(obj):
    if isinstance(obj, dict):
        yield obj
        for value in obj.values():
            if isinstance(value, (dict, list)):
                yield from flatten(value)
    elif isinstance(obj, list):
        for value in obj:
            yield from flatten(value)

def norm(value):
    return "".join(ch for ch in str(value or "").upper() if ch.isalnum())

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("catalog", type=Path, help="catalog.json.gz")
    parser.add_argument("--output", type=Path, help="JSON report (default: stdout)")
    args = parser.parse_args()
    with gzip.open(args.catalog, "rt", encoding="utf-8") as fh:
        catalog = json.load(fh)
    # Never count every nested object as an insert: locate the actual items array.
    if isinstance(catalog, list):
        items = catalog
    elif isinstance(catalog, dict) and isinstance(catalog.get("items"), list):
        items = catalog["items"]
    else:
        raise ValueError("Struttura inattesa: impossibile identificare items senza ipotesi")
    records = [x for x in items if isinstance(x, dict)]
    keys = ("code", "codice", "isoCode", "iso_code", "designation", "name", "sku")
    grade_keys = ("grade", "grado", "quality")
    def fields(rec, names):
        return [str(rec[k]) for k in names if k in rec and isinstance(rec[k], (str, int))]
    targets = ["SPGX110708WG", "SPGX140512WG"]
    matches = {}
    for target in targets:
        hits = []
        for index, rec in enumerate(records):
            candidates = fields(rec, keys)
            if any(norm(target) == norm(s) or (norm(s).startswith(norm(target)) and norm(s)[len(norm(target)):] in {"IN2505"}) for s in candidates):
                hits.append({"index": index, "codes": candidates, "grades": fields(rec, grade_keys),
                             "record": rec})
        matches[target] = hits
    # Separate exact code+grade evidence from code-only candidates. A missing grade is not IN2505.
    exact_grade_matches = {
        target: [hit for hit in hits if ((hit["grades"] and all(norm(g) == "IN2505" for g in hit["grades"]))
                 or (not hit["grades"] and any(norm(c) == norm(target) + "IN2505" for c in hit["codes"])))]
        for target, hits in matches.items()
    }
    # Duplicate candidates only: keys may not be unique across grades/variants.
    identities = []
    for rec in records:
        codes = fields(rec, keys)
        grades = fields(rec, grade_keys)
        if codes:
            identities.append((norm(codes[0]), norm(grades[0]) if grades else ""))
    repeated = [{"code": code, "grade": grade, "count": count}
                for (code, grade), count in Counter(identities).items() if count > 1]
    report = {
        "catalog": str(args.catalog), "items": len(items),
        "nonObjectItems": len(items) - len(records),
        "spgxCandidates": matches,
        "spgxExactIN2505Candidates": exact_grade_matches,
        "duplicateIdentityCandidates": repeated,
        "warning": "Corrispondenze candidate, non certificazione: verificare schema, codice, grado, EDP e fonti ufficiali. Non attribuire VC/FN/FZ/AP generali agli articoli."
    }
    result = json.dumps(report, ensure_ascii=False, indent=2, default=str)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(result + "\n", encoding="utf-8")
    else:
        print(result)

if __name__ == "__main__":
    main()
