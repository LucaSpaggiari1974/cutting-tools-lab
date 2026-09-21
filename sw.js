const CACHE="cutting-tools-lab-v4";
self.addEventListener("install",e=>e.waitUntil(self.skipWaiting()));
self.addEventListener("activate",e=>e.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>k!==CACHE).map(k=>caches.delete(k)))).then(()=>self.clients.claim())));
self.addEventListener("fetch",e=>{
 if(e.request.method!=="GET") return;
 const u=new URL(e.request.url);
 if(u.pathname.endsWith("/catalog.json")||u.pathname.endsWith("/index.html")||u.pathname.endsWith("/manifest.webmanifest")||u.pathname.endsWith("/sw.js")){
   e.respondWith(fetch(e.request,{cache:"no-store"}).then(r=>{if(r.ok&&u.origin===location.origin&&u.pathname.endsWith("/catalog.json"))caches.open(CACHE).then(c=>c.put(e.request,r.clone()));return r}).catch(()=>caches.match(e.request)));
   return;
 }
 e.respondWith(fetch(e.request).catch(()=>caches.match(e.request)));
});