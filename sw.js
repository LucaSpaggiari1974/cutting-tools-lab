const CACHE="cutting-tools-lab-v2";
self.addEventListener("install",e=>e.waitUntil(self.skipWaiting()));
self.addEventListener("activate",e=>e.waitUntil(
 caches.keys().then(keys=>Promise.all(keys.filter(k=>k!==CACHE).map(k=>caches.delete(k)))).then(()=>self.clients.claim())
));
self.addEventListener("fetch",e=>{
 if(e.request.method!=="GET") return;
 const u=new URL(e.request.url);
 if(u.pathname.endsWith("/catalog.json")){
  e.respondWith(fetch(e.request,{cache:"no-store"}).catch(()=>caches.match(e.request)));
  return;
 }
 if(e.request.mode==="navigate"||u.pathname.endsWith("/index.html")){
  e.respondWith(fetch(e.request,{cache:"no-store"}).catch(()=>caches.match("./index.html")));
  return;
 }
 e.respondWith(fetch(e.request).catch(()=>caches.match(e.request)));
});