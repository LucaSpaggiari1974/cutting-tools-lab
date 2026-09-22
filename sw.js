const CACHE="cutting-tools-lab-v23";
const APP=["./","./index.html","./manifest.webmanifest","./icon.svg","./catalog.json","./manufacturers.json"];

self.addEventListener("install",event=>{
  event.waitUntil((async()=>{
    const c=await caches.open(CACHE);
    await c.addAll(APP);
    await self.skipWaiting();
  })());
});

self.addEventListener("activate",event=>{
  event.waitUntil((async()=>{
    const keys=await caches.keys();
    await Promise.all(keys.filter(k=>k!==CACHE).map(k=>caches.delete(k)));
    await self.clients.claim();
  })());
});

self.addEventListener("fetch",event=>{
  if(event.request.method!=="GET") return;
  const url=new URL(event.request.url);
  if(url.origin!==location.origin) return;
  event.respondWith((async()=>{
    try{
      const response=await fetch(event.request,{cache:"no-store"});
      if(response.ok){
        const c=await caches.open(CACHE);
        await c.put(event.request,response.clone());
      }
      return response;
    }catch(_){
      const cached=await caches.match(event.request);
      return cached||caches.match("./index.html");
    }
  })());
});
