"""
Customer Guide — multi-language site builder (English / Malayalam / Arabic)
1) Edit CONFIG in engine.py (BRAND, APP_URL, WHATSAPP, EMAIL)
2) Run:  python3 build.py
Output: ./site  (pure HTML + CSS — upload the whole folder to any hosting)
"""
import os, shutil, html, sys
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.getcwd())
import engine
from engine import *
from i18n import UI, GROUPS, GUIDE_META, BT, LANG_META
import verticals_a, verticals_b, verticals_c, verticals_d, features, tr_ml_d, common, common_ml, common_ar, tr_ml, tr_ar

# Built pages are served by the app at /guide/ (apps/webapp/guide_views.py).
OUT = os.environ.get("GUIDE_OUT") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "apps", "webapp", "guide_site")
SLUG_GROUP = {
  "mobile-shop":"Retail & product shops","textile":"Retail & product shops","sports-shop":"Retail & product shops",
  "cycle-shop":"Retail & product shops","medical-shop":"Retail & product shops","protein-shop":"Retail & product shops","retail-shop":"Retail & product shops",
  "gym":"Fitness & wellness",
  "spa":"Beauty & wellness","saloon":"Beauty & wellness","beauty-parlour":"Beauty & wellness",
  "service-appointments":"Appointments & services","vehicle-wash":"Appointments & services",
  "construction":"Projects & contracting","project-agency":"Projects & contracting",
  "jewellery":"Retail & product shops","sell-by-weight":"Retail & product shops",
  "restaurant":"Restaurants & food","bookings":"Bookings & rentals",
  "education":"Education & property","property":"Education & property","recruitment":"Projects & contracting",
  "quotes-orders":"Tools for every business","purchases-suppliers":"Tools for every business","stock":"Tools for every business",
  "customers-money":"Tools for every business","finance":"Tools for every business","staff-hr":"Tools for every business",
  "website-online":"Tools for every business","devices-apps":"Tools for every business","security-settings":"Tools for every business",
}
ORDER = ["restaurant",
         "mobile-shop","textile","sports-shop","cycle-shop","medical-shop","protein-shop","retail-shop","sell-by-weight","jewellery",
         "bookings","education","property",
         "gym","spa","saloon","beauty-parlour","service-appointments","vehicle-wash","construction","project-agency","recruitment",
         "quotes-orders","purchases-suppliers","stock","customers-money","finance","staff-hr","website-online","devices-apps","security-settings"]
GROUP_ORDER = ["Restaurants & food","Retail & product shops","Bookings & rentals","Education & property","Fitness & wellness","Beauty & wellness",
               "Appointments & services","Projects & contracting","Tools for every business"]

EN = {v["slug"]: v for v in verticals_a.VERTICALS + verticals_b.VERTICALS + verticals_c.VERTICALS + verticals_d.VERTICALS + features.VERTICALS}
assert set(ORDER) == set(EN)
for s, v in EN.items(): v["group"] = SLUG_GROUP[s]

tr_ml.VERT.update(tr_ml_d.VERT)

LANGS = {
  "en": dict(common=common, tr={}),
  "ml": dict(common=common_ml, tr=tr_ml.VERT),
  "ar": dict(common=common_ar, tr=tr_ar.VERT),
}

def L(): return engine.CUR["lang"]

def vdata(slug):
    """Guide data for the current language (falls back to English fields only for structural keys)."""
    v = dict(EN[slug])
    tr = LANGS[L()]["tr"].get(slug)
    if tr: v.update(tr)
    return v

def has_tr(slug, lang=None):
    lang = lang or L()
    return lang == "en" or slug in LANGS[lang]["tr"]

def gname(slug):
    if L() == "en": return EN[slug]["name"]
    return GUIDE_META[L()].get(slug, (EN[slug]["name"], ""))[0]
def gtag(slug):
    if L() == "en": return EN[slug]["tag"]
    return GUIDE_META[L()].get(slug, ("", EN[slug]["tag"]))[1]
def ghref(slug):
    return f"guide-{slug}.html" if has_tr(slug) else f"../en/guide-{slug}.html"
def en_badge(slug):
    return "" if has_tr(slug) else f' <span class="badge-en" title="{T("english_only")}">{T("en_only")}</span>'
def btname(c):
    if L() == "en": return c
    return BT[L()].get(c, c)

def write(lang, name, content):
    d = os.path.join(OUT, lang); os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, name), "w", encoding="utf-8") as f: f.write(content)

def switch_for(fname, slug=None):
    sw = {}
    for code in LANGS:
        ok = True
        if slug: ok = has_tr(slug, code)
        sw[code] = f"../{code}/{fname}" if ok else f"../{code}/index.html"
    return sw

def task_from(t):
    title, items = t[0], t[1]
    kw = t[2] if len(t) > 2 and isinstance(t[2], dict) else {}
    return task(title, items, open_=True, **kw)

def crumb_for(group=None):
    s = T("crumb_sep")
    c = f'<a href="index.html">{T("crumb_home")}</a> {s} <a href="index.html#guides">{T("crumb_guides")}</a>'
    if group: c += f" {s} " + GROUPS[L()][group]
    return c

def vertical_page(i, slug):
    v = vdata(slug); name = gname(slug)
    sections = []
    cards = "".join(f'<div class="mini"><b>{t}</b><span>{d}</span></div>' for t, d in v["glance"])
    covers = ""
    if len(EN[slug]["covers"]) > 1:
        covers = f"<h3>{T('covers_h')}</h3><div class='pilllist'>" + "".join(f"<span>{btname(c)}</span>" for c in EN[slug]["covers"]) + "</div>"
    sections.append(("overview", T("s_overview"), f'<p class="sub">{v["lead"]}</p><div class="grid g2">{cards}</div><h3>{T("routine")}</h3>{flow(v["flow"])}{covers}', "✨"))
    where = ('<div class="mock">' + mock(v["menu_title"], v["menu"]) + f'<div class="expl"><h3 style="margin-top:0">{T("where_h")}</h3>'
             f'<p>{T("where_tool" if EN[slug]["group"] == "Tools for every business" else "where_p1").format(m=v["menu_title"])}</p><p>{T("where_p2")}</p></div></div>')
    sections.append(("where", T("s_where"), where, "🧭"))
    sections.append(("setup", T("s_setup"), f"<p class='sub'>{T('setup_sub')}</p>" + "".join(task_from(t) for t in v["setup"]), "🚀"))
    sections.append(("daily", T("s_daily"), f"<p class='sub'>{T('daily_sub')}</p>" + "".join(task_from(t) for t in v["tasks"]), "🛠️"))
    sections.append(("auto", T("s_auto"), ticks(v["auto"]), "⚙️"))
    sections.append(("reports", T("s_reports"), table([T("rep_h1"), T("rep_h2")], [[a, b] for a, b in v["reports"]]) + f'<p>{T("analytics_p")}</p>', "📈"))
    if v["statuses"]:
        sections.append(("status", T("s_status"), table([T("st_h1"), T("st_h2")], [[badge(a, k), m] for a, k, m in v["statuses"]]), "🏷️"))
    sections.append(("faq", T("s_faq"), "".join(faq(q, a) for q, a in v["faq"]), "❓"))

    prev_ = ORDER[i-1] if i > 0 else None
    next_ = ORDER[i+1] if i < len(ORDER)-1 else None
    pg = '<div class="pager">'
    pg += (f'<a href="{ghref(prev_)}"><small>{T("prev")}</small>{EN[prev_]["icon"]} {gname(prev_)}{en_badge(prev_)}</a>' if prev_ else '<span></span>')
    pg += (f'<a class="r" href="{ghref(next_)}"><small>{T("next")}</small>{gname(next_)}{en_badge(next_)} {EN[next_]["icon"]}</a>' if next_ else '<span></span>')
    pg += '</div>'
    extra = helpbox() + "<div style='height:18px'></div>" + pg
    body = hero(EN[slug]["icon"], name, v["lead"], v["chips"], crumb_for(EN[slug]["group"])) + doc(sections, extra)
    engine.CUR["switch"] = switch_for(f"guide-{slug}.html", slug)
    return page(name, body, cur="index.html#guides", desc=gtag(slug))

def index_page():
    engine.CUR["switch"] = switch_for("index.html")
    start = f'''<div class="grid g3">
<a class="card" href="getting-started.html"><div class="ci">🚀</div><h3>{T("c1_h")}</h3><p>{T("c1_p")}</p><span class="go">{T("c1_go")}</span></a>
<a class="card" href="#guides"><div class="ci">📘</div><h3>{T("c2_h")}</h3><p>{T("c2_p")}</p><span class="go">{T("c2_go")}</span></a>
<a class="card" href="help.html"><div class="ci">🛟</div><h3>{T("c3_h")}</h3><p>{T("c3_p")}</p><span class="go">{T("c3_go")}</span></a>
</div>'''
    groups = ""
    for g in GROUP_ORDER:
        cards = "".join(f'<a class="card" href="{ghref(s)}"><div class="ci">{EN[s]["icon"]}</div><h3>{gname(s)}{en_badge(s)}</h3><p>{gtag(s)}</p><span class="go">{T("read_guide")}</span></a>'
                        for s in ORDER if EN[s]["group"] == g)
        groups += f'<div class="sect-title"><h2>{GROUPS[L()][g]}</h2></div><div class="grid g3">{cards}</div>'
    rows = []
    for s in ORDER:
        if EN[s]["group"] == "Tools for every business": continue
        for c in EN[s]["covers"]:
            rows.append([btname(c), f'<a href="{ghref(s)}">{gname(s)}</a>{en_badge(s)}'])
    rows.sort(key=lambda r: html.unescape(r[0]).lower())
    which = table([T("which_c1"), T("which_c2")], rows)
    how = f'''<div class="grid g3">
<div class="mini"><b>{T("how1_h")}</b><span>{T("how1_p")}</span></div>
<div class="mini"><b>{T("how2_h")}</b><span>{T("how2_p")}</span></div>
<div class="mini"><b>{T("how3_h")}</b><span>{T("how3_p")}</span></div></div>'''
    body = hero("📘", T("idx_title"), T("idx_lead"), T("idx_chips"), cta=True)
    body += f'''<div class="wrap" style="padding-top:34px;padding-bottom:50px">
<div class="sect-title"><h2>{T("start_h")}</h2><span>{T("start_sub")}</span></div>{start}
<div class="sect-title" id="guides"><h2>{T("choose_h")}</h2><span>{T("n_guides").format(n=len(ORDER))}</span></div>{groups}
<div class="sect-title"><h2>{T("how_h")}</h2></div>{how}
<div class="sect-title"><h2>{T("which_h")}</h2><span>{T("which_sub")}</span></div>{which}
<div style="height:22px"></div>{helpbox()}</div>'''
    return page(T("idx_title"), body, cur="index.html", desc=T("idx_lead"))

def gs_page():
    engine.CUR["switch"] = switch_for("getting-started.html")
    secs = LANGS[L()]["common"].getting_started()
    body = hero("🚀", T("gs_title"), T("gs_lead"), T("gs_chips"), crumb_for() + f" {T('crumb_sep')} {T('gs_title')}")
    first = [s for s in ORDER if True][:6]
    extra = f'<div class="sect-title"><h2>{T("next_h")}</h2></div><div class="grid g3">' + "".join(
        f'<a class="card" href="{ghref(s)}"><div class="ci">{EN[s]["icon"]}</div><h3>{gname(s)}{en_badge(s)}</h3></a>' for s in first) + \
        f'</div><p style="margin-top:14px"><a href="index.html#guides"><b>{T("all_guides")}</b></a></p><div style="height:14px"></div>' + helpbox()
    return page(T("gs_title"), body + doc(secs, extra), cur="getting-started.html", desc=T("gs_lead"))

def help_page():
    engine.CUR["switch"] = switch_for("help.html")
    secs = LANGS[L()]["common"].help_sections()
    body = hero("🛟", T("help_title"), T("help_lead"), [], crumb_for() + f" {T('crumb_sep')} {T('nav_help')}", cta=False)
    return page(T("help_title"), body + doc(secs, helpbox()), cur="help.html", desc=T("help_lead"))

def chooser():
    cards = "".join(f'<a href="{c}/index.html" lang="{c}" dir="{LANG_META[c]["dir"]}"><b>{LANG_META[c]["name"]}</b><span>{ {"en":"Read this guide in English","ml":"മലയാളത്തിൽ വായിക്കൂ","ar":"اقرأ الدليل بالعربية"}[c] }</span></a>' for c in ("en","ml","ar"))
    return f'''<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>User Guide · {CONFIG["BRAND"]}</title><link rel="stylesheet" href="style.css">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin><link href="https://fonts.googleapis.com/css2?family=Noto+Sans+Malayalam:wght@600;700&family=Noto+Sans+Arabic:wght@600;700&display=swap" rel="stylesheet"></head>
<body><section class="hero"><div class="in" style="text-align:center;padding:64px 20px 70px"><div class="ico" style="margin:0 auto 16px">📘</div>
<h1 style="max-width:900px;margin-inline:auto">{CONFIG["BRAND"]} – Complete User Guide</h1><p class="lead" style="margin-inline:auto">{CONFIG["BRAND"]} · English · മലയാളം · العربية</p></div></section>
<div class="wrap" style="padding-top:36px;padding-bottom:60px"><div class="sect-title"><h2>Choose your language · ഭാഷ തിരഞ്ഞെടുക്കൂ · اختر لغتك</h2></div>
<div class="langpick">{cards}</div></div></body></html>'''

if os.path.exists(OUT): shutil.rmtree(OUT)
os.makedirs(OUT)
shutil.copy("style.css", os.path.join(OUT, "style.css"))
with open(os.path.join(OUT, "index.html"), "w", encoding="utf-8") as f: f.write(chooser())
count = 0
for lang in ("en", "ml", "ar"):
    engine.CUR["lang"] = lang
    write(lang, "index.html", index_page())
    write(lang, "getting-started.html", gs_page())
    write(lang, "help.html", help_page())
    count += 3
    for i, slug in enumerate(ORDER):
        if has_tr(slug):
            write(lang, f"guide-{slug}.html", vertical_page(i, slug)); count += 1
print("built", count, "pages")
for l in ("en","ml","ar"): print(l, len(os.listdir(os.path.join(OUT,l))), "files")
