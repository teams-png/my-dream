"""Renders every poster in posters.html to PNG. Needs Playwright with Chromium (set CHROME to its path if it is not found). Run: python3 render.py"""
import os, urllib.request
from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "posters.html")
OUT = os.path.dirname(HERE)
FONT_URL = ("https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap")
fontcss = urllib.request.urlopen(urllib.request.Request(FONT_URL, headers={"User-Agent": "Mozilla/5.0 Chrome/120"})).read()
cache = {}


def gs(route):
    u = route.request.url
    if u not in cache:
        cache[u] = urllib.request.urlopen(u).read()
    route.fulfill(body=cache[u], content_type="font/ttf")


with sync_playwright() as p:
    b = p.chromium.launch(**({"executable_path": os.environ["CHROME"]} if os.environ.get("CHROME") else {}))
    pg = b.new_page(viewport={"width": 1400, "height": 1000})
    pg.route("https://fonts.googleapis.com/**", lambda r: r.fulfill(body=fontcss, content_type="text/css"))
    pg.route("https://fonts.gstatic.com/**", gs)
    pg.goto("file://" + SRC)
    pg.wait_for_load_state("networkidle")
    pg.evaluate("document.fonts.ready")
    pg.wait_for_timeout(600)
    for el in pg.query_selector_all(".poster"):
        pid = el.get_attribute("id")
        el.screenshot(path=os.path.join(OUT, pid + ".png"))
        print("png", pid)
    b.close()
