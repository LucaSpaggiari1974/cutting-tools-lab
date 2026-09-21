#!/usr/bin/env python3
import json, os, re, urllib.request
from datetime import datetime, timezone

CATALOG="catalog.json"
SOURCE_URL="https://www.iscar.com/Catalogs/Publication/russia_33/TURNING_CATALOG_RUSSIA_121-254/TURNING_CATALOG_RUSSIA_121-254.pdf"
OUT="data/iscar-sync-report.json"

def norm(s):
    return re.sub(r"\s+", " ", s.upper().replace("–","-")).strip()

def main():
    os.makedirs("data", exist_ok=True)
    with urllib.request.urlopen(SOURCE_URL, timeout=60) as r:
        pdf=r.read()
    open("/tmp/iscar-turning.pdf","wb").write(pdf)

    # PyMuPDF is installed by the workflow. It gives considerably better text
    # extraction than shell utilities for ISCAR's multi-column catalogues.
    import fitz
    doc=fitz.open("/tmp/iscar-turning.pdf")
    text="\n".join(page.get_text("text") for page in doc)
    open("/tmp/iscar-turning.txt","w",encoding="utf-8").write(text)

    with open(CATALOG,encoding="utf-8") as f:
        catalog=json.load(f)

    # Capture exact ISO insert designations appearing in the official catalogue.
    # We intentionally do not overwrite cutting data automatically: only fields
    # that are unambiguous from the source are enriched.
    patterns=re.findall(r"\b(?:CNMG|DNMG|VNMG|WNMG|SNMG|TNMG|CCMT|DCMT|VCMT|TCMT|SCMT|RCMT|DNMX|CNMX|WNMX)\s+\d{2,3}\s*\d{3,4}(?:-[A-Z0-9]+)+\b", text, flags=re.I)
    official=set(norm(x) for x in patterns)

    changed=0
    verified=0
    for item in catalog.get("items",[]):
        if str(item.get("maker","")).upper()!="ISCAR":
            continue
        code=norm(item.get("code",""))
        if code in official:
            verified += 1
            before=item.get("officialCatalogVerified")
            item["officialCatalogVerified"]=True
            item["officialCatalogSource"]=SOURCE_URL
            item["officialCatalogVerifiedAt"]=datetime.now(timezone.utc).isoformat()
            if before is not True:
                changed += 1

    catalog["updatedAt"]=datetime.now(timezone.utc).isoformat()
    catalog["sync"]= {
        "mode":"official-source-validation",
        "source":"ISCAR Turning Catalogue",
        "sourceUrl":SOURCE_URL,
        "lastRun":datetime.now(timezone.utc).isoformat(),
        "matchedExistingISCARRecords":verified
    }

    with open(CATALOG,"w",encoding="utf-8") as f:
        json.dump(catalog,f,ensure_ascii=False,indent=2)
        f.write("\n")

    report={"runAt":datetime.now(timezone.utc).isoformat(),
            "source":SOURCE_URL,
            "officialInsertDesignationsFound":len(official),
            "matchedExistingISCARRecords":verified,
            "recordsChanged":changed}
    with open(OUT,"w",encoding="utf-8") as f:
        json.dump(report,f,ensure_ascii=False,indent=2)
        f.write("\n")
    print(json.dumps(report,ensure_ascii=False))

if __name__=="__main__":
    main()
