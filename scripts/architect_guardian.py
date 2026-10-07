#!/usr/bin/env python3
"""Cutting Tools LAB - independent architecture guardian.

Read-only safety gate. It never edits catalog data.
It validates:
- JSON integrity and required structure
- duplicate maker+code records
- allowed insert categories
- presence of turning/foratura/fresatura/filettatura
- anomalous catalog shrink vs previous commit
- public Cloudflare catalog.json and complete-tools.json
- online version/timestamp/item counts against the checked-out commit
- public application availability
"""
import json, os, subprocess, sys, time
from collections import Counter
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PUBLIC=os.environ.get("PUBLIC_BASE_URL","https://cutting-tools-lab.spaggiari.workers.dev").rstrip("/")
CATALOG=os.path.join(ROOT,"catalog.json")
TOOLS=os.path.join(ROOT,"complete-tools.json")
REPORT=os.path.join(ROOT,"architect-guardian-report.json")

ALLOWED=[
    "Tornitura · Finitura","Tornitura · Media","Tornitura · Sgrossatura",
    "Fresatura","Foratura","Filettatura"
]

def load(path):
    with open(path,encoding="utf-8") as f: return json.load(f)

def online_json(url, retries=6):
    last=""
    for n in range(retries):
        try:
            req=Request(url,headers={"User-Agent":"Cutting-Tools-LAB-Architect-Guardian/1.0","Cache-Control":"no-cache"})
            with urlopen(req,timeout=20) as r:
                data=r.read()
                return json.loads(data.decode("utf-8")), r.status
        except Exception as e:
            last=str(e)
            if n < retries-1: time.sleep(10)
    return None,last

def git_previous_count(path):
    rel=os.path.relpath(path,ROOT)
    try:
        raw=subprocess.check_output(["git","show",f"HEAD^:{rel}"],stderr=subprocess.DEVNULL,text=True)
        return len(json.loads(raw).get("items",[]))
    except Exception:
        return None

def main():
    checks=[]
    errors=[]
    warnings=[]

    # Local database integrity
    try:
        cat=load(CATALOG); checks.append(("catalog-json-valid",True))
    except Exception as e:
        errors.append(f"catalog.json non valido: {e}"); cat={}
    try:
        tools=load(TOOLS); checks.append(("complete-tools-json-valid",True))
    except Exception as e:
        errors.append(f"complete-tools.json non valido: {e}"); tools={}

    items=cat.get("items",[])
    if not isinstance(items,list) or not items:
        errors.append("catalog.json non contiene una lista items valida/non vuota")
    keys=[(str(x.get("maker","")).strip().lower(),str(x.get("code","")).strip().upper()) for x in items if isinstance(x,dict)]
    dup=sum(v-1 for v in Counter(keys).values() if v>1)
    if dup: errors.append(f"{dup} duplicati maker+code nel catalogo")
    else: checks.append(("no-duplicate-inserts",True))

    badcats=sorted({x.get("category") for x in items if x.get("category") not in ALLOWED})
    if badcats: errors.append("Categorie inserti non ammesse: "+", ".join(map(str,badcats[:10])))
    else: checks.append(("insert-categories-valid",True))

    counts=Counter(x.get("category") for x in items)
    for c in ALLOWED:
        if counts[c]==0:
            if c in ("Foratura","Filettatura"):
                errors.append(f"Categoria obbligatoria senza record: {c}")
            else:
                warnings.append(f"Categoria senza record: {c}")
    if sum(counts.get(c,0) for c in ALLOWED[:3])==0:
        errors.append("Sono sparite tutte le categorie di tornitura")

    prev=git_previous_count(CATALOG)
    current=len(items)
    if prev and current < prev*0.90:
        errors.append(f"Calo anomalo catalogo inserti: {prev} -> {current} (>10%)")
    elif prev:
        checks.append(("catalog-shrink-within-safety-limit",True))

    # Online production verification
    online_cat,status=online_json(PUBLIC+"/catalog.json")
    if online_cat is None:
        errors.append(f"catalogo online non raggiungibile: {status}")
    else:
        if online_cat.get("updatedAt") != cat.get("updatedAt"):
            errors.append(f"catalogo online non allineato: online {online_cat.get('updatedAt')} != GitHub {cat.get('updatedAt')}")
        if len(online_cat.get("items",[])) != current:
            errors.append(f"conteggio online non allineato: online {len(online_cat.get('items',[]))} != GitHub {current}")
        else: checks.append(("online-catalog-matches-github",True))

    local_tools_count=len(tools.get("items",[])) if isinstance(tools,dict) else 0
    online_tools,status2=online_json(PUBLIC+"/complete-tools.json")
    if online_tools is None:
        errors.append(f"complete-tools online non raggiungibile: {status2}")
    else:
        if online_tools.get("updatedAt") != tools.get("updatedAt"):
            errors.append(f"complete-tools online non allineato: online {online_tools.get('updatedAt')} != GitHub {tools.get('updatedAt')}")
        if len(online_tools.get("items",[])) != local_tools_count:
            errors.append(f"conteggio complete-tools online non allineato: online {len(online_tools.get('items',[]))} != GitHub {local_tools_count}")
        else: checks.append(("online-complete-tools-matches-github",True))

    # Application smoke test
    try:
        req=Request(PUBLIC+"/",headers={"User-Agent":"Cutting-Tools-LAB-Architect-Guardian/1.0"})
        with urlopen(req,timeout=20) as r:
            body=r.read(200000).decode("utf-8","ignore")
            if r.status != 200: errors.append(f"homepage HTTP {r.status}")
            elif "Cutting Tools LAB" not in body: warnings.append("homepage raggiungibile ma titolo applicazione non rilevato")
            else: checks.append(("online-homepage",True))
    except Exception as e:
        errors.append(f"homepage online non raggiungibile: {e}")

    report={
        "status":"PASS" if not errors else "BLOCKED",
        "checkedAt":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),
        "role":"independent-read-only-architect-guardian",
        "githubCatalogItems":current,
        "githubCompleteToolsItems":local_tools_count,
        "previousCatalogItems":prev,
        "categoryCounts":dict(counts),
        "checksPassed":[x[0] for x in checks],
        "warnings":warnings,
        "errors":errors,
        "publicBaseUrl":PUBLIC,
        "rule":"Il Guardian non modifica dati; in caso di errore blocca il passaggio e richiede verifica."
    }
    with open(REPORT,"w",encoding="utf-8") as f: json.dump(report,f,ensure_ascii=False,indent=2)
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return 0 if not errors else 1

if __name__=="__main__":
    sys.exit(main())
