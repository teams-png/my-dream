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
    """Makes the site installable (Chrome/Edge/Android "Install app", iOS "Add to Home Screen")."""
    from django.templatetags.static import static

    icons = [{"src": static(f"icons/icon-{n}.png"), "sizes": f"{n}x{n}", "type": "image/png", "purpose": "any"}
             for n in (48, 72, 96, 144, 192, 256, 384, 512)]
    icons += [{"src": static(f"icons/maskable-{n}.png"), "sizes": f"{n}x{n}", "type": "image/png", "purpose": "maskable"}
              for n in (192, 512)]
    shortcut_icon = [{"src": static("icons/icon-96.png"), "sizes": "96x96", "type": "image/png"}]
    response = JsonResponse({
        "id": "/", "name": "BookPilot Business Suite", "short_name": "BookPilot",
        "description": "Accounting, POS and business management",
        "start_url": "/?source=app", "scope": "/", "display": "standalone", "display_override": ["standalone"],
        "orientation": "any", "background_color": "#f4f6fb", "theme_color": "#14532d",
        "categories": ["business", "finance", "productivity"], "icons": icons,
        "shortcuts": [
            {"name": "Point of Sale", "short_name": "POS", "url": "/pos/", "icons": shortcut_icon},
            {"name": "Restaurant orders", "short_name": "Restaurant", "url": "/restaurant/", "icons": shortcut_icon},
            {"name": "Dashboard", "short_name": "Dashboard", "url": "/", "icons": shortcut_icon},
        ],
    })
    response["Content-Type"] = "application/manifest+json"
    return response


def service_worker(request):
    # Static files: cache-first. The retail POS (/pos/) is saved on each
    # successful visit and served from the cache when the network is down
    # (so is the restaurant quick sale counter, /restaurant/quick/);
    # the offline restaurant POS page, its menu data and menu photos are saved
    # by that page itself (Cache API). Other pages show a plain offline
    # notice that links to whichever POS this device has; financial pages are
    # never cached.
    script = """const CACHE='bookpilot-shell-v4',POS='bp-offline-pos-v1',POS_PAGE='/restaurant/offline/',SHOP='/pos/',QUICK='/restaurant/quick/';
self.addEventListener('install',e=>self.skipWaiting());
self.addEventListener('activate',e=>e.waitUntil(caches.keys().then(ks=>Promise.all(ks.filter(k=>k.startsWith('bookpilot-shell-')&&k!==CACHE).map(k=>caches.delete(k)))).then(()=>self.clients.claim())));
self.addEventListener('fetch',e=>{
  if(e.request.method!=='GET')return;
  const u=new URL(e.request.url);
  if(u.origin!==location.origin)return;
  if(u.pathname.startsWith('/static/')){e.respondWith(caches.match(e.request).then(hit=>hit||fetch(e.request).then(r=>{if(r.ok){const copy=r.clone();caches.open(CACHE).then(c=>c.put(e.request,copy))}return r})));return}
  if(u.pathname.startsWith('/media/')){e.respondWith(fetch(e.request).catch(()=>caches.match(e.request,{ignoreSearch:true}).then(hit=>hit||Response.error())));return}
  if(e.request.mode==='navigate'){
    if(u.pathname===SHOP||u.pathname===QUICK){
      const key=u.pathname;
      e.respondWith(fetch(e.request).then(r=>{if(r.ok&&!r.redirected){const copy=r.clone();caches.open(POS).then(c=>c.put(key,copy))}return r}).catch(()=>caches.open(POS).then(c=>c.match(key)).then(hit=>hit||offline())));
      return;
    }
    e.respondWith(fetch(e.request).catch(()=>{
      if(u.pathname.startsWith('/restaurant/'))return caches.open(POS).then(c=>c.match(POS_PAGE)).then(hit=>hit||offline());
      return offline();
    }));
  }
});
function offline(){return caches.open(POS).then(c=>Promise.all([c.match(SHOP),c.match(POS_PAGE),c.match(QUICK)])).catch(()=>[]).then(([shop,rest,quick])=>new Response('<!doctype html><meta name=viewport content="width=device-width,initial-scale=1"><title>BookPilot · offline</title><body style="font-family:system-ui;padding:40px;text-align:center"><h1>📴 BookPilot is offline</h1><p>Reconnect to continue. Financial pages are never cached on this device.</p>'+(shop?'<p><a href="/pos/">Open the offline shop POS</a></p>':'')+(rest?'<p><a href="/restaurant/offline/">Open the offline restaurant POS</a></p>':'')+(quick?'<p><a href="/restaurant/quick/">Open the quick sale counter</a></p>':'')+'</body>',{headers:{'Content-Type':'text/html; charset=utf-8'}}))}"""
    response = HttpResponse(script, content_type="application/javascript")
    response["Service-Worker-Allowed"] = "/"
    response["Cache-Control"] = "no-cache"
    return response
