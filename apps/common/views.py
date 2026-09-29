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
    script = """const CACHE='bookpilot-shell-v1';
self.addEventListener('install',e=>self.skipWaiting());
self.addEventListener('activate',e=>e.waitUntil(self.clients.claim()));
self.addEventListener('fetch',e=>{if(e.request.method!=='GET')return;const u=new URL(e.request.url);if(u.origin===location.origin&&u.pathname.startsWith('/static/')){e.respondWith(caches.match(e.request).then(hit=>hit||fetch(e.request).then(r=>{const copy=r.clone();caches.open(CACHE).then(c=>c.put(e.request,copy));return r})));return}if(e.request.mode==='navigate'){e.respondWith(fetch(e.request).catch(()=>new Response('<h1>BookPilot is offline</h1><p>Reconnect to continue. Financial pages are never cached on this device.</p>',{headers:{'Content-Type':'text/html'}})))}});"""
    response = HttpResponse(script, content_type="application/javascript")
    response["Service-Worker-Allowed"] = "/"
    response["Cache-Control"] = "no-cache"
    return response
