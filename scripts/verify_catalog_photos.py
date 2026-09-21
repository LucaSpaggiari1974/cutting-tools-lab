#!/usr/bin/env python3
"""Runtime verification of catalog photo URLs and photo policy."""

import json
import mimetypes
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone

CATALOG="catalog.json"
REPORT="data/photo-runtime-verification.json"
HEADERS={"User-Agent":"Cutting-Tools-LAB-photo-verifier/1.0"}

MAKERS={
"ISCAR":["iscar.com","webshop.iscaritalia.it","webshop.iscar.in","webshop.iscar.de"],
"Ingersoll":["ingersoll-imc.com"],"Kennametal":["kennametal.com"],
"Sandvik Coromant":["sandvik.coromant.com"],"Walter":["walter-tools.com"],
"Seco Tools":["secotools.com"],"Tungaloy":["tungaloy.com"],
"Sumitomo Electric Hardmetal":["sumitomotool.com"],"KORLOY":["korloy.com"],
"Kyocera":["kyocera.com"],"NTK Cutting Tools":["ntkcuttingtools.com"],
"Dormer Pramet":["dormerpramet.com"],"Guhring":["guhring.com"],
"ZCC Cutting Tools":["zccct.com"],"TaeguTec":["taegutec.com"],
"Ceratizit":["ceratizit.com"],"ISO":[],"ISO / produttore":[]
}

def host_ok(url, domains):
    host=(urllib.parse.urlparse(url).hostname or "").lower()
    return any(host==d or host.endswith("."+d) for d in domains)

def probe(url):
    req=urllib.request.Request(url,headers=HEADERS,method="GET")
    with urllib.request.urlopen(req,timeout=20) as r:
        data=r.read(64)
        return r.status, r.geturl(), r.headers.get("Content-Type",""), len(data)

def main():
    with open(CATALOG,encoding="utf-8") as f: cat=json.load(f)
    items=cat.get("items",[])
    errors=[]; checked=0; loaded=0; missing_status=0; generic=0

    for i,x in enumerate(items):
        if not x.get("photoStatus"): missing_status+=1
        if x.get("genericPhotoUrl"): generic+=1
        url=str(x.get("photoUrl","")).strip()
        if not url: continue
        checked+=1
        maker=str(x.get("maker","")).strip()
        domains=MAKERS.get(maker,[])
        if domains and not host_ok(url,domains):
            errors.append({"index":i,"code":x.get("code"),"maker":maker,"error":"photoUrl outside official manufacturer domains","url":url})
            continue
        try:
            status,final_url,ctype,n=probe(url)
            if status < 200 or status >= 400:
                raise RuntimeError("HTTP "+str(status))
            if not ctype.lower().startswith("image/"):
                raise RuntimeError("not an image: "+ctype)
            loaded+=1
        except Exception as e:
            errors.append({"index":i,"code":x.get("code"),"maker":maker,"error":str(e),"url":url})

    report={
      "runAt":datetime.now(timezone.utc).isoformat(),
      "records":len(items),
      "photoUrlsChecked":checked,
      "photoUrlsReachable":loaded,
      "photoUrlsFailed":len(errors),
      "recordsMissingPhotoStatus":missing_status,
      "genericPhotoFields":generic,
      "policy":"manufacturer-exact-only; unavailable is explicit when no verified official photo exists",
      "errors":errors[:200]
    }
    os.makedirs(os.path.dirname(REPORT),exist_ok=True)
    with open(REPORT,"w",encoding="utf-8") as f: json.dump(report,f,ensure_ascii=False,indent=2); f.write("\n")
    print(json.dumps(report,ensure_ascii=False))
    raise SystemExit(1 if errors or missing_status or generic else 0)

if __name__=="__main__": main()
