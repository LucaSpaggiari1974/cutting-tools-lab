#!/usr/bin/env python3
"""
Daily manufacturer updater for Cutting Tools LAB.

Safe rules:
- GitHub remains the source of truth for the main catalog.
- Existing manually entered fields are preserved.
- Product pages already referenced by the catalog are checked first.
- Official og:image / twitter:image / JSON-LD Product images can refresh photos.
- New products are added only when an official source exposes a clear Product
  JSON-LD record with sku/mpn + name + image; uncertain pages are reported,
  not invented.
- A complete catalog snapshot is written before every run.
"""
import json, re, sys, hashlib, urllib.request, urllib.parse, urllib.error
from datetime import datetime, timezone
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT=Path(__file__).resolve().parents[1]
CATALOG=ROOT/"catalog.json"
MANUFACTURERS=ROOT/"manufacturers.json"
BACKUP=ROOT/"backups/catalog-latest.json"
STATUS=ROOT/"update-status.json"
UA="Cutting-Tools-LAB-Daily-Updater/1.0 (+https://cutting-tools-lab.vercel.app/)"

def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00","Z")

def get(url, timeout=18, max_bytes=900_000):
    req=urllib.request.Request(url, headers={"User-Agent":UA,"Accept":"text/html,application/xhtml+xml,application/json,*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data=r.read(max_bytes+1)
        if len(data)>max_bytes: data=data[:max_bytes]
        return r.geturl(), r.headers.get("content-type",""), data

def clean_url(u, base):
    if not u: return ""
    u=urllib.parse.urljoin(base,u.strip())
    p=urllib.parse.urlsplit(u)
    if p.scheme not in ("http","https"): return ""
    return urllib.parse.urlunsplit((p.scheme,p.netloc,p.path,p.query,""))

def html_image(html, base):
    candidates=[]
    for pat in [
        r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image',
        r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']twitter:image',
    ]:
        candidates += re.findall(pat, html, re.I)
    for x in candidates:
        u=clean_url(x,base)
        if u: return u
    return ""

def jsonld_products(html, base):
    out=[]
    blocks=re.findall(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',html,re.I|re.S)
    for raw in blocks:
        raw=re.sub(r'<!--[\s\S]*?-->','',raw).strip()
        try: obj=json.loads(raw)
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
                    "name":str(x.get("name") or "").strip(),
                    "sku":str(x.get("sku") or "").strip(),
                    "mpn":str(x.get("mpn") or "").strip(),
                    "image":clean_url(str(img),base) if img else "",
                    "url":clean_url(str(x.get("url") or ""),base),
                })
            for key in ("@graph","mainEntity","itemListElement"):
                y=x.get(key)
                if isinstance(y,list): stack.extend(y)
                elif isinstance(y,dict): stack.append(y)
    return out

def extract_products(url, maker):
    try:
        final,ctype,data=get(url)
        html=data.decode("utf-8","ignore")
        products=jsonld_products(html,final)
        img=html_image(html,final)
        return {"url":url,"maker":maker,"ok":True,"final":final,"image":img,"products":products,
                "hash":hashlib.sha256(data).hexdigest()[:16]}
    except Exception as e:
        return {"url":url,"maker":maker,"ok":False,"error":str(e)[:240],"products":[],"image":""}

def same_code(a,b):
    def norm(s): return re.sub(r"[^A-Z0-9]","",str(s).upper())
    return norm(a)==norm(b) and bool(norm(a))

def main():
    started=now()
    catalog=json.loads(CATALOG.read_text(encoding="utf-8"))
    manufacturers=json.loads(MANUFACTURERS.read_text(encoding="utf-8"))
    items=catalog.get("items",[])
    old=json.dumps(catalog,ensure_ascii=False,sort_keys=True)

    BACKUP.parent.mkdir(parents=True,exist_ok=True)
    BACKUP.write_text(json.dumps(catalog,ensure_ascii=False,indent=2),encoding="utf-8")

    # Check every existing product URL, but in parallel.
    jobs=[]
    for i,x in enumerate(items):
        u=x.get("productUrl")
        if u and u.startswith(("http://","https://")):
            jobs.append((i,u,x.get("maker","")))
    results=[]
    with ThreadPoolExecutor(max_workers=12) as ex:
        futs=[ex.submit(extract_products,u,m) for _,u,m in jobs]
        for (i,u,m),f in zip(jobs,futs):
            try: results.append((i,f.result()))
            except Exception as e: results.append((i,{"ok":False,"error":str(e)}))

    photos_changed=0
    page_checked=0
    failed=0
    for i,r in results:
        x=items[i]
        if not r.get("ok"):
            failed+=1; continue
        page_checked+=1
        products=r.get("products") or []
        image=r.get("image") or ""
        matched=None
        for p in products:
            if same_code(p.get("sku"),x.get("code")) or same_code(p.get("mpn"),x.get("code")):
                matched=p; break
        candidate=(matched or {}).get("image") or image
        if candidate and candidate != x.get("photoUrl"):
            # Only trust images discovered on the same official product page
            # already stored in the catalog.
            x["photoUrl"]=candidate
            x["photoSource"]="manufacturer"
            x["photoNote"]="Foto ufficiale rilevata automaticamente dalla scheda prodotto."
            x.pop("photoWarning",None)
            x["photoUpdatedAt"]=started
            photos_changed+=1

    # Monitor the official manufacturer source pages. We do not fabricate
    # catalog rows from generic catalog pages; JSON-LD Product rows are eligible
    # only when they contain a clear code and image.
    source_results=[]
    for m in manufacturers.get("groups",[]):
        u=m.get("catalog")
        if not u: continue
        r=extract_products(u,m.get("name",""))
        source_results.append(r)

    discovered=[]
    existing_codes=[x.get("code","") for x in items]
    for r in source_results:
        for p in r.get("products",[]):
            code=p.get("sku") or p.get("mpn")
            if not code or not p.get("name") or not p.get("image"): continue
            if any(same_code(code,c) for c in existing_codes): continue
            # Conservative auto-add: code must look like a machining product
            # code (letters/numbers, at least 5 chars). No invented cutting data.
            norm=re.sub(r"[^A-Z0-9]","",code.upper())
            if len(norm)<5: continue
            discovered.append({
                "category":"Nuovo prodotto · da catalogo ufficiale",
                "code":code,
                "geom":p.get("name",""),
                "material":"da catalogo produttore",
                "vc":"da catalogo produttore",
                "f":"da catalogo produttore",
                "ap":"da catalogo produttore",
                "maker":r.get("maker",""),
                "photoUrl":p.get("image"),
                "photoSource":"manufacturer",
                "photoNote":"Nuovo prodotto rilevato automaticamente da dati Product ufficiali; parametri da verificare nel catalogo.",
                "productUrl":p.get("url") or r.get("final") or r.get("url"),
                "autoDiscoveredAt":started
            })
    # De-duplicate discoveries by normalized code.
    seen=set()
    for x in discovered:
        k=re.sub(r"[^A-Z0-9]","",x["code"].upper())
        if k in seen: continue
        seen.add(k); items.append(x)
    new_count=len(seen)

    catalog["items"]=items
    catalog["updatedAt"]=started
    catalog["version"]=str(catalog.get("version","2.5"))+"-auto"
    new=json.dumps(catalog,ensure_ascii=False,sort_keys=True)
    changed=(new!=old)

    status={
        "updatedAt":started,
        "run":"daily",
        "changed":changed,
        "pagesChecked":page_checked,
        "pagesFailed":failed,
        "photosUpdated":photos_changed,
        "newProducts":new_count,
        "catalogItems":len(items),
        "backup":"backups/catalog-latest.json",
        "sourcesChecked":len(source_results),
        "note":"Gli aggiornamenti automatici usano solo dati rilevati da pagine/cataloghi ufficiali. Parametri di taglio non verificati non vengono inventati.",
        "errors":[r.get("error","") for r in source_results if not r.get("ok")][:20]
    }

    if changed:
        CATALOG.write_text(json.dumps(catalog,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    STATUS.write_text(json.dumps(status,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(status,ensure_ascii=False))

if __name__=="__main__":
    main()
