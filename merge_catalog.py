import json
from pathlib import Path
from datetime import datetime, timezone

base_path=Path("catalog.json")
extra_path=Path("catalog-memory.json")
base=json.loads(base_path.read_text(encoding="utf-8"))
extra=json.loads(extra_path.read_text(encoding="utf-8"))

items=base.get("items",[])
index={(str(x.get("maker","")).strip().lower(),str(x.get("code","")).strip().lower()):x for x in items}

for x in extra.get("items",[]):
    key=(str(x.get("maker","")).strip().lower(),str(x.get("code","")).strip().lower())
    if key in index:
        old=index[key]
        for k,v in x.items():
            if v not in ("",None) and (k not in old or old.get(k) in ("",None)):
                old[k]=v
    else:
        items.append(x)
        index[key]=x

base["items"]=items
base["updatedAt"]=datetime.now(timezone.utc).isoformat().replace("+00:00","Z")
base["source"]="Cutting Tools LAB · catalogo principale + database memoria importato"
base["memoryImportVersion"]=extra.get("version")
base_path.write_text(json.dumps(base,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
print(f"Catalogo unificato: {len(items)} record")
