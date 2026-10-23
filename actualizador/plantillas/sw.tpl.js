/* Generado automaticamente por actualizar.py - no editar a mano */
const BUILD='/*BUILD*/';
const CACHE='biblia';
const SHELL=['./','index.html','manifest.webmanifest','icon-192.png','icon-512.png'];
const CORE=[/*CORE*/];
const DOCV=/*DOCV*/;
const isData=u=>/\/(data|docs)\//.test(u.pathname);
self.addEventListener('install',e=>{e.waitUntil((async()=>{const c=await caches.open(CACHE);
  for(const u of SHELL){try{await c.put(u,await fetch(u,{cache:'reload'}))}catch(_){}}
  for(const u of CORE){if(!(await c.match(u))){try{await c.add(u)}catch(_){}}}
  await self.skipWaiting()})())});
self.addEventListener('activate',e=>{e.waitUntil((async()=>{
  for(const k of await caches.keys())if(k!==CACHE)await caches.delete(k);
  const c=await caches.open(CACHE);const core=new Set(CORE.map(u=>new URL(u,self.location).href));
  for(const r of await c.keys()){const u=new URL(r.url);if(!isData(u))continue;
    let ok=core.has(u.href);const m=/\/docs\/([^/]+)\//.exec(u.pathname);
    if(m&&DOCV[m[1]]&&u.searchParams.get('v')===DOCV[m[1]])ok=true;
    if(!ok)await c.delete(r)}
  await self.clients.claim()})())});
self.addEventListener('fetch',e=>{const r=e.request;if(r.method!=='GET')return;const u=new URL(r.url);if(u.origin!==location.origin)return;
  e.respondWith((async()=>{const c=await caches.open(CACHE);const hit=await c.match(r,{ignoreSearch:!isData(u)});if(hit)return hit;
    try{const res=await fetch(r);if(res.ok)c.put(r,res.clone());return res}catch(err){if(r.mode==='navigate'){const i=await c.match('index.html');if(i)return i}return new Response('Sin conexión',{status:503})}})())});
