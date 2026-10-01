export default async function handler(req,res){
  try{
    const raw=req.query?.url;
    if(!raw)return res.status(400).send("Missing url");
    const target=new URL(raw);
    if(target.protocol!=="https:")return res.status(400).send("HTTPS only");
    const allowed=[
      "iscar.com","www.iscar.com","iscaritalia.it","webshop.iscaritalia.it",
      "sandvik.coromant.com","www.sandvik.coromant.com",
      "walter-tools.com","www.walter-tools.com",
      "kennametal.com","www.kennametal.com",
      "secotools.com","www.secotools.com",
      "sumitool.com","www.sumitool.com",
      "tungaloy.com","www.tungaloy.com",
      "korloy.com","www.korloy.com",
      "kyocera.com","www.kyocera.com","tool-global.kyocera.com",
      "ntkcuttingtools.com","www.ntkcuttingtools.com",
      "dormerpramet.com","www.dormerpramet.com",
      "guhring.com","www.guhring.com",
      "zccct.com","www.zccct.com",
      "taegutec.com","www.taegutec.com",
      "ceratizit.com","www.ceratizit.com",
      "ingersoll-imc.com","www.ingersoll-imc.com"
    ];
    if(!allowed.some(d=>target.hostname===d||target.hostname.endsWith("."+d)))return res.status(403).send("Manufacturer domain not allowed");
    const page=await fetch(target,{headers:{"user-agent":"Mozilla/5.0 (compatible; CuttingToolsLAB/1.0)","accept":"text/html,application/xhtml+xml"}});
    if(!page.ok)return res.status(502).send("Manufacturer page unavailable");
    const html=await page.text();
    const candidates=[];
    const patterns=[
      /<meta[^>]+property=["']og:image["'][^>]+content=["']([^"']+)["']/i,
      /<meta[^>]+content=["']([^"']+)["'][^>]+property=["']og:image["']/i,
      /<meta[^>]+name=["']twitter:image["'][^>]+content=["']([^"']+)["']/i,
      /<meta[^>]+content=["']([^"']+)["'][^>]+name=["']twitter:image["']/i
    ];
    for(const p of patterns){const m=html.match(p);if(m)candidates.push(m[1]);}
    if(!candidates.length){
      const imgs=[...html.matchAll(/<img[^>]+(?:src|data-src)=["']([^"']+)["']/gi)].map(m=>m[1]);
      candidates.push(...imgs.filter(x=>/\.(?:png|jpe?g|webp)(?:\?|$)/i.test(x)).slice(0,10));
    }
    for(const value of candidates){
      try{
        const imageUrl=new URL(value,target).toString();
        const ir=await fetch(imageUrl,{headers:{"user-agent":"Mozilla/5.0","accept":"image/avif,image/webp,image/apng,image/*,*/*;q=0.8"}});
        const ct=ir.headers.get("content-type")||"";
        if(ir.ok&&ct.startsWith("image/")){
          const buf=Buffer.from(await ir.arrayBuffer());
          res.setHeader("Cache-Control","public, max-age=86400, s-maxage=604800, stale-while-revalidate=2592000");
          res.setHeader("Content-Type",ct);
          return res.status(200).send(buf);
        }
      }catch(_){}
    }
    return res.status(404).send("No product image found");
  }catch(e){return res.status(500).send("Image lookup failed");}
}