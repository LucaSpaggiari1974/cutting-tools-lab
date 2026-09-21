#!/usr/bin/env python3
"""Smart, manufacturer-only product photo enrichment.

Rules:
- A photo is accepted only when the product code is found on the manufacturer
  domain and the page exposes an og:image (or twitter:image) on that same
  manufacturer domain.
- Distributor/marketplace/generic family images are never accepted.
- If an exact manufacturer photo cannot be verified, photoUrl is left empty.
"""

import html
import json
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

CATALOG = "catalog.json"
REPORT = "data/manufacturer-photo-sync-report.json"

# Conservative official domains. A record is enriched only from its own maker.
MAKERS = {
    "ISCAR": ["iscar.com", "webshop.iscaritalia.it", "webshop.iscar.in", "webshop.iscar.de"],
    "Ingersoll": ["ingersoll-imc.com"],
    "Kennametal": ["kennametal.com"],
    "Sandvik Coromant": ["sandvik.coromant.com"],
    "Walter": ["walter-tools.com"],
    "Seco Tools": ["secotools.com"],
    "Tungaloy": ["tungaloy.com"],
    "Sumitomo Electric Hardmetal": ["sumitomotool.com"],
    "KORLOY": ["korloy.com"],
    "Kyocera": ["kyocera.com"],
    "NTK Cutting Tools": ["ntkcuttingtools.com"],
    "Dormer Pramet": ["dormerpramet.com"],
    "Guhring": ["guhring.com"],
    "ZCC Cutting Tools": ["zccct.com"],
    "TaeguTec": ["taegutec.com"],
    "Ceratizit": ["ceratizit.com"],
    "ISO": [],
    "ISO / produttore": [],
}

HEADERS = {"User-Agent": "Mozilla/5.0 cutting-tools-lab manufacturer-photo-sync/1.0"}

def norm(s):
    s = str(s or "").upper().replace("–", "-")
    return re.sub(r"[^A-Z0-9]+", "", s)

def host_ok(url, domains):
    try:
        host = (urllib.parse.urlparse(url).hostname or "").lower()
        return any(host == d or host.endswith("." + d) for d in domains)
    except Exception:
        return False

def fetch(url, timeout=20):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.geturl(), r.read().decode("utf-8", "ignore")

def meta_image(page, base_url):
    patterns = [
        r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
        r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']twitter:image["\']',
    ]
    for p in patterns:
        m = re.search(p, page, re.I)
        if m:
            return urllib.parse.urljoin(base_url, html.unescape(m.group(1).strip()))
    return None

def search_official(code, domains):
    # Bing is used only as a discovery mechanism. Acceptance still requires
    # the resulting page and image to belong to the manufacturer's domain and
    # the exact normalized code to be present in the page.
    domain_query = " OR ".join("site:" + d for d in domains)
    q = urllib.parse.quote('"{}" ({})'.format(code, domain_query))
    url = "https://www.bing.com/search?q=" + q
    try:
        _, page = fetch(url, timeout=20)
    except Exception:
        return None

    links = re.findall(r'<a[^>]+href=["\'](https?://[^"\']+)', page, re.I)
    target = norm(code)
    for link in links:
        if not host_ok(link, domains):
            continue
        try:
            final_url, product_page = fetch(link, timeout=20)
        except Exception:
            continue
        if target not in norm(html.unescape(re.sub("<[^>]+>", " ", product_page))):
            continue
        image = meta_image(product_page, final_url)
        if image and host_ok(image, domains):
            return {
                "productUrl": final_url,
                "photoUrl": image,
                "photoSource": "manufacturer official website",
                "photoVerified": True,
                "photoVerifiedAt": datetime.now(timezone.utc).isoformat(),
            }
    return None


OFFICIAL_DOMAINS = sorted({d for ds in MAKERS.values() for d in ds})

def exact_code_in_page(code, page):
    target = norm(code)
    text = norm(html.unescape(re.sub("<[^>]+>", " ", page)))
    return bool(target) and target in text

def verify_product_url(item, domains):
    url = str(item.get("productUrl", "")).strip()
    if not url or not domains or not host_ok(url, domains): return None
    try: final_url, page = fetch(url, timeout=25)
    except Exception: return None
    if not exact_code_in_page(item.get("code", ""), page): return None
    image = meta_image(page, final_url)
    if image and host_ok(image, domains):
        return {"productUrl": final_url, "photoUrl": image, "photoSource": "manufacturer official website", "photoVerified": True, "photoVerifiedAt": datetime.now(timezone.utc).isoformat(), "photoNote": "Foto ufficiale verificata sulla pagina prodotto con corrispondenza esatta del codice."}
    return None

def main():
    with open(CATALOG, encoding="utf-8") as f:
        catalog = json.load(f)
    items = catalog.get("items", [])
    now = datetime.now(timezone.utc).isoformat()
    checked = 0
    updated = 0
    cleared = 0
    found = 0

    for item in items:
        maker = str(item.get("maker", "")).strip()
        domains = MAKERS.get(maker)
        checked += 1 if maker in MAKERS else 0
        if not domains:
            url = str(item.get("productUrl", "")).strip()
            domains = [d for d in OFFICIAL_DOMAINS if host_ok(url, [d])]
            if not domains:
                item["photoStatus"] = "unavailable"
                item["photoNote"] = "Anteprima non disponibile: nessuna fonte ufficiale verificabile associata al produttore."
                continue
        source = str(item.get("photoSource", "")).lower(); warning = str(item.get("photoWarning", "")).lower()
        if "distributor" in source or warning or item.get("photoVerified") is False:
            for k in ("photoUrl","photoWarning","photoVerified","photoVerifiedAt","photoSource"): item.pop(k,None)
            cleared += 1
        code = str(item.get("code", "")).strip()
        if not code: continue
        result = verify_product_url(item, domains)
        if result:
            if item.get("photoUrl") != result["photoUrl"] or not item.get("photoVerified"): updated += 1
            item.update(result); item["photoStatus"] = "available"; found += 1; time.sleep(0.10); continue
        result = search_official(code, domains)
        if result:
            item.update(result); item["photoStatus"] = "available"; item["photoNote"] = "Foto ufficiale verificata tramite corrispondenza esatta del codice."; found += 1; updated += 1
        else:
            for k in ("photoUrl","photoSource","photoVerified","photoVerifiedAt"): item.pop(k,None)
            item["photoStatus"] = "unavailable"
            item["photoNote"] = "Anteprima non disponibile: nessuna foto ufficiale verificata per il codice esatto."
        time.sleep(0.15)

    catalog["updatedAt"] = now
    catalog["photoPolicy"] = {
        "mode": "manufacturer-exact-only",
        "rule": "Solo foto ufficiali del produttore collegate a una pagina che contiene il codice esatto.",
        "lastRun": now,
    }
    with open(CATALOG, "w", encoding="utf-8") as f:
        json.dump(catalog, f, ensure_ascii=False, indent=2)
        f.write("\n")

    report = {
        "runAt": now,
        "recordsChecked": checked,
        "officialPhotosFound": found,
        "recordsUpdated": updated,
        "nonManufacturerPhotosCleared": cleared,
        "policy": catalog["photoPolicy"],
    }
    with open(REPORT, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(json.dumps(report, ensure_ascii=False))

if __name__ == "__main__":
    main()
