const CACHE="cutting-tools-lab-v17";
const APP=["./","./index.html"];

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
  if(event.request.method!=="GET")return;
  const url=new URL(event.request.url);
  if(url.origin!==location.origin)return;

  // I database JSON sono dinamici e possono essere molto grandi:
  // non devono mai dipendere dalla Cache Storage.
  const isDatabase=/\/(catalog|complete-tools|update-status)\.json$/i.test(url.pathname);
  if(isDatabase){
    event.respondWith(fetch(event.request,{cache:"no-store"}));
    return;
  }

  event.respondWith((async()=>{
    try{
      const response=await fetch(event.request,{cache:"no-store"});
      if(response.ok){
        try{
          const c=await caches.open(CACHE);
          await c.put(event.request,response.clone());
        }catch(_){}
      }
      return response;
    }catch(_){
      return caches.match(event.request)||caches.match("./index.html");
    }
  })());
});