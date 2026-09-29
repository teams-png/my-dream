from django.db import connection
from django.http import JsonResponse, HttpResponse


def health(request):
    return JsonResponse({"status": "ok", "service": "bookpilot-accounting"})


def readiness(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:
        return JsonResponse({"status": "not_ready", "database": "unavailable"}, status=503)
    return JsonResponse({"status": "ready", "service": "bookpilot-accounting", "database": "ok"})


def pwa_manifest(request):
    return JsonResponse({
        "name": "BookPilot Business Suite", "short_name": "BookPilot",
        "start_url": "/", "display": "standalone", "background_color": "#f4f6fb",
        "theme_color": "#14532d", "description": "Accounting, POS and business management",
    })


def service_worker(request):
    # Static files: cache-first. The offline restaurant POS page, its menu data
    # and menu photos are saved by that page itself (Cache API) and served here
    # when the network is down. Other pages still show a plain offline notice;
    # financial pages are never cached.
    script = """const CACHE='bookpilot-shell-v2',POS='bp-offline-pos-v1',POS_PAGE='/restaurant/offline/';
self.addEventListener('install',e=>self.skipWaiting());
self.addEventListener('activate',e=>e.waitUntil(caches.keys().then(ks=>Promise.all(ks.filter(k=>k.startsWith('bookpilot-shell-')&&k!==CACHE).map(k=>caches.delete(k)))).then(()=>self.clients.claim())));
self.addEventListener('fetch',e=>{
  if(e.request.method!=='GET')return;
  const u=new URL(e.request.url);
  if(u.origin!==location.origin)return;
  if(u.pathname.startsWith('/static/')){e.respondWith(caches.match(e.request).then(hit=>hit||fetch(e.request).then(r=>{if(r.ok){const copy=r.clone();caches.open(CACHE).then(c=>c.put(e.request,copy))}return r})));return}
  if(u.pathname.startsWith('/media/')){e.respondWith(fetch(e.request).catch(()=>caches.match(e.request,{ignoreSearch:true}).then(hit=>hit||Response.error())));return}
  if(e.request.mode==='navigate'){
    e.respondWith(fetch(e.request).catch(()=>{
      if(u.pathname.startsWith('/restaurant/'))return caches.open(POS).then(c=>c.match(POS_PAGE)).then(hit=>hit||offline(true));
      return offline(false);
    }));
  }
});
function offline(pos){return new Response('<!doctype html><meta name=viewport content="width=device-width,initial-scale=1"><title>BookPilot · offline</title><body style="font-family:system-ui;padding:40px;text-align:center"><h1>📴 BookPilot is offline</h1><p>Reconnect to continue. Financial pages are never cached on this device.</p>'+(pos?'':'<p><a href="/restaurant/offline/">Open the offline restaurant POS</a></p>')+'</body>',{headers:{'Content-Type':'text/html; charset=utf-8'}})}"""
    response = HttpResponse(script, content_type="application/javascript")
    response["Service-Worker-Allowed"] = "/"
    response["Cache-Control"] = "no-cache"
    return response
