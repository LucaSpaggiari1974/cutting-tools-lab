#!/usr/bin/env python3
"""
Conservative daily catalog verifier.

This job NEVER invents or auto-adds catalog records. It:
- validates that every record is an allowed cutting insert category;
- removes only generic/non-insert/duplicate records that are unambiguously invalid;
- keeps existing valid records;
- sorts the catalog by requested category order, manufacturer and code;
- checks official manufacturer source URLs;
- refreshes a photo only when the exact catalog code is exposed by Product JSON-LD
  on an already-associated official product page;
- maintains per-manufacturer source, verification date and completeness state.

New insert codes must be added only after an official source has been explicitly
classified as an insert record. Generic Product JSON-LD pages are never enough.
"""
import json, re, urllib.request, urllib.parse, urllib.error
from datetime import datetime, timezone
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT=Path(__file__).resolve().parents[1]
CATALOG=ROOT/"catalog.json"
MANUFACTURERS=ROOT/"manufacturers.json"
BACKUP=ROOT/"backups/catalog-latest.json"
STATUS=ROOT/"update-status.json"
UA="Cutting-Tools-LAB-Daily-Verifier/2.0 (+https://cutting-tools-lab.pages.dev/)"

ALLOWED=[
    "Tornitura · Finitura",
    "Tornitura · Media",
    "Tornitura · Sgrossatura",
    "Fresatura",
    "Foratura",
    "Filettatura",
]
CATEGORY_ORDER={v:i for i,v in enumerate(ALLOWED)}
CANONICAL={"Ingersoll Cutting Tools":"Ingersoll","Kyocera Cutting Tools":"Kyocera",
           "NTK Cutting Tools":"NTK","ZCC Cutting Tools":"ZCC"}

def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00","Z")

def norm(s):
    return re.sub(r"[^A-Z0-9]","",str(s or "").upper())

def clean_url(u, base):
    if not u: return ""
    u=urllib.parse.urljoin(base,str(u).strip())
    p=urllib.parse.urlsplit(u)
    if p.scheme not in ("http","https"): return ""
    return urllib.parse.urlunsplit((p.scheme,p.netloc,p.path,p.query,""))

def get(url, timeout=20, max_bytes=1200000):
    req=urllib.request.Request(url, headers={"User-Agent":UA,"Accept":"text/html,application/xhtml+xml,application/json,*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data=r.read(max_bytes+1)
        return r.geturl(),r.headers.get("content-type",""),data[:max_bytes]

def jsonld_products(html, base):
    out=[]
    blocks=re.findall(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',html,re.I|re.S)
    for raw in blocks:
        try: obj=json.loads(re.sub(r'<!--|-->','',raw).strip())
        except Exception: continue
        stack=obj if isinstance(obj,list) else [obj]
        while stack:
            x=stack.pop()
            if isinstance(x,list): stack.extend(x); continue
            if not isinstance(x,dict): continue
            typ=x.get("@type")
            if typ=="Product" or (isinstance(typ,list) and "Product" in typ):
                img=x.get("image")
                if isinstance(img,list): img=img[0] if img else ""
                if isinstance(img,dict): img=img.get("url","")
                out.append({
                    "sku":str(x.get("sku") or "").strip(),
                    "mpn":str(x.get("mpn") or "").strip(),
                    "name":str(x.get("name") or "").strip(),
                    "image":clean_url(img,base) if img else "",
                })
            for key in ("@graph","mainEntity","itemListElement"):
                y=x.get(key)
                if isinstance(y,list): stack.extend(y)
                elif isinstance(y,dict): stack.append(y)
    return out

def check_url(url):
    try:
        final,ctype,data=get(url)
        return {"ok":True,"url":url,"final":final,"contentType":ctype,"bytes":len(data),"error":""}
    except Exception as e:
        return {"ok":False,"url":url,"final":url,"contentType":"","bytes":0,"error":str(e)[:240]}

def exact_product_image(url, code):
    try:
        final,ctype,data=get(url)
        html=data.decode("utf-8","ignore")
        for p in jsonld_products(html,final):
            if norm(p["sku"])==norm(code) or norm(p["mpn"])==norm(code):
                image=p.get("image","")
                if image and not re.search(r"(logo|brand|hero|catcover)",image,re.I):
                    return image
    except Exception:
        pass
    return ""

def main():
    started=now()
    catalog=json.loads(CATALOG.read_text(encoding="utf-8"))
    manufacturers=json.loads(MANUFACTURERS.read_text(encoding="utf-8"))
    old=json.dumps(catalog,ensure_ascii=False,sort_keys=True)
    BACKUP.parent.mkdir(parents=True,exist_ok=True)
    BACKUP.write_text(json.dumps(catalog,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

    # Remove only unambiguous generic/non-insert records and exact duplicates.
    before=len(catalog.get("items",[]))
    removed=[]
    items=[]
    seen=set()
    for x in catalog.get("items",[]):
        if x.get("maker")=="ISO" or x.get("category") not in ALLOWED or not x.get("code"):
            removed.append({"maker":x.get("maker"),"code":x.get("code"),"reason":"generic/non-insert"})
            continue
        key=norm(x.get("maker"))+"|"+norm(x.get("code"))
        if key in seen:
            removed.append({"maker":x.get("maker"),"code":x.get("code"),"reason":"duplicate"})
            continue
        seen.add(key)
        # Never expose a generic manufacturer cover/logo as an insert photo.
        if x.get("photoSource")=="manufacturer" and re.search(r"(catcover|logo|brand|hero)",str(x.get("photoUrl") or ""),re.I):
            x.pop("photoUrl",None); x.pop("photoSource",None)
            x.pop("photoUpdatedAt",None); x.pop("photoVerifiedAt",None)
            x["photoStatus"]="unavailable"
            x["photoNote"]="Foto ufficiale del codice esatto non verificata; nessuna immagine generica usata."
        items.append(x)

    items.sort(key=lambda x:(CATEGORY_ORDER.get(x.get("category"),99),str(x.get("maker","")).casefold(),norm(x.get("code"))))
    catalog["items"]=items

    # Official manufacturer source audit. This is verification, not auto-indexing.
    source_jobs=[]
    for g in manufacturers.get("groups",[]):
        if g.get("name")=="ISO": continue
        u=g.get("catalog")
        if u: source_jobs.append((g.get("name",""),u))
    source_results={}
    with ThreadPoolExecutor(max_workers=8) as ex:
        futures={ex.submit(check_url,u):(name,u) for name,u in source_jobs}
        for f in as_completed(futures):
            name,u=futures[f]
            try: source_results[name]=f.result()
            except Exception as e: source_results[name]={"ok":False,"url":u,"error":str(e)[:240]}

    # Exact-page photo refresh only. Never replace a reference image with a generic page image.
    photo_updates=0
    photo_jobs=[]
    for i,x in enumerate(items):
        u=x.get("productUrl")
        if u and u.startswith(("http://","https://")):
            photo_jobs.append((i,u,x.get("code","")))
    with ThreadPoolExecutor(max_workers=8) as ex:
        futures={ex.submit(exact_product_image,u,code):(i,code) for i,u,code in photo_jobs}
        for f in as_completed(futures):
            i,code=futures[f]
            try: image=f.result()
            except Exception: image=""
            if image and image != items[i].get("photoUrl"):
                items[i]["photoUrl"]=image
                items[i]["photoSource"]="manufacturer"
                items[i]["photoStatus"]="available"
                items[i]["photoNote"]="Foto reale del codice esatto rilevata dalla scheda ufficiale."
                items[i]["photoUpdatedAt"]=started
                photo_updates+=1

    counts={}
    for x in items: counts[x["maker"]]=counts.get(x["maker"],0)+1

    registry=[]
    for g in manufacturers.get("groups",[]):
        if g.get("name")=="ISO": continue
        maker=CANONICAL.get(g.get("name"),g.get("name"))
        src=source_results.get(g.get("name"),{})
        registry.append({
            "maker":maker,
            "status":"indexed-incrementally" if counts.get(maker,0) else "pending-official-index",
            "completeness":"not-complete",
            "verifiedAt":started,
            "sourceOfficial":g.get("catalog") or None,
            "sourceType":g.get("catalogLabel") or "official manufacturer source",
            "sourceReachable":bool(src.get("ok")),
            "sourceCheckedUrl":src.get("final") or src.get("url") or g.get("catalog") or None,
            "indexedItemCount":counts.get(maker,0),
            "rule":"Solo codici inserto effettivamente verificati da fonte ufficiale; nessun utensile completo, portautensile, famiglia generica o diametro utensile."
        })

    catalog["version"]="3.5-insert-only-pipeline-hardened"
    catalog["updatedAt"]=started
    catalog["coverage"]["itemCount"]=len(items)
    catalog["coverage"]["lastRun"]=started
    catalog["coverage"]["manufacturerRegistry"]=registry
    catalog["manufacturerRegistry"]=registry

    new=json.dumps(catalog,ensure_ascii=False,sort_keys=True)
    changed=(new!=old)
    if changed:
        CATALOG.write_text(json.dumps(catalog,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

    status={
        "updatedAt":started,
        "run":"daily",
        "changed":changed,
        "catalogItems":len(items),
        "removedInvalidOrDuplicate":len(removed),
        "removedDetails":removed[:100],
        "photosUpdated":photo_updates,
        "sourcesChecked":len(source_results),
        "sourcesReachable":sum(1 for x in source_results.values() if x.get("ok")),
        "sourcesFailed":sum(1 for x in source_results.values() if not x.get("ok")),
        "newProducts":0,
        "autoIndexing":"disabled-by-policy",
        "note":"Il job non aggiunge mai automaticamente Product JSON-LD non classificati: nuovi codici devono essere verificati come inserti da fonte ufficiale prima dell'indicizzazione.",
        "backup":"backups/catalog-latest.json",
        "errors":[{"maker":k,"error":v.get("error","")} for k,v in source_results.items() if not v.get("ok")][:30]
    }
    STATUS.write_text(json.dumps(status,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(status,ensure_ascii=False))

if __name__=="__main__":
    main()
