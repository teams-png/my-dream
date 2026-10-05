import re, html
from i18n import UI, LANG_META

# ------------------------------------------------------------------ config
# The guide is served by the app itself at /guide/, so links to the app are relative.
# The __TOKENS__ are filled in when a page is served, from the SUPPORT_* / LEGAL_* settings,
# so contact details can change on the server without rebuilding the guide.
CONFIG = {
    "BRAND": "BookPilot",
    "COMPANY": "__COMPANY__",
    "APP_URL": "",
    "WHATSAPP": "__SUPPORT_WHATSAPP__",
    "EMAIL": "__SUPPORT_EMAIL__",
}

CUR = {"lang": "en", "switch": {}}
def T(k): return UI[CUR["lang"]][k]

def fmt(s):
    """[[Button]] -> ui chip ; [[[Menu]]] -> brand chip ; keep raw html."""
    s = re.sub(r"\[\[\[(.+?)\]\]\]", r'<span class="ui g">\1</span>', s)
    s = re.sub(r"\[\[(.+?)\]\]", r'<span class="ui">\1</span>', s)
    return s

def steps(items):
    out = ['<ol class="steps">']
    for it in items:
        if isinstance(it, tuple):
            t, d = it
            out.append(f'<li><b class="t">{fmt(t)}</b>{fmt(d)}</li>')
        else:
            out.append(f'<li>{fmt(it)}</li>')
    out.append('</ol>')
    return "\n".join(out)

def callouts(tip=None, note=None, warn=None):
    o = ""
    if tip:  o += f'<div class="tip"><b>{T("tip")}</b> {fmt(tip)}</div>'
    if note: o += f'<div class="note"><b>{T("note")}</b> {fmt(note)}</div>'
    if warn: o += f'<div class="warn"><b>{T("warn")}</b> {fmt(warn)}</div>'
    return o

def task(title, items, tip=None, note=None, warn=None, intro=None, kind=None, open_=True):
    k = f'<span class="k">{kind}</span>' if kind else ""
    body = (f"<p>{fmt(intro)}</p>" if intro else "") + steps(items) + callouts(tip, note, warn)
    return f'<details class="task"{" open" if open_ else ""}><summary>{k}{fmt(title)}</summary><div class="body">{body}</div></details>'

def faq(q, a):
    return f'<details class="faq"><summary>{fmt(q)}</summary><div class="body"><p>{fmt(a)}</p></div></details>'

def table(head, rows):
    h = "".join(f"<th>{fmt(x)}</th>" for x in head)
    r = "".join("<tr>" + "".join(f"<td>{fmt(c)}</td>" for c in row) + "</tr>" for row in rows)
    return f'<div class="tw"><table><thead><tr>{h}</tr></thead><tbody>{r}</tbody></table></div>'

def badge(text, kind="grey"):
    return f'<span class="badge b-{kind}">{text}</span>'

def ticks(items):
    return '<ul class="tick">' + "".join(f"<li>{fmt(i)}</li>" for i in items) + "</ul>"

def flow(items):
    out = ['<ol class="flow">']
    for it in items:
        if isinstance(it, tuple):
            out.append(f"<li>{fmt(it[0])}<small>{fmt(it[1])}</small></li>")
        else:
            out.append(f"<li>{fmt(it)}</li>")
    out.append("</ol>")
    return "".join(out)

def mock(biz_title, items, icon=""):
    """Mock of the APP sidebar. The app itself is in English, so labels stay English in every language."""
    common = ["Overview", "Sales", "Purchases", "Finance", "People", "Business", "Settings"]
    s = ['<div class="sb"><div class="top"><i></i>Business Console</div>']
    s.append('<div class="l plain act">Overview</div>')
    for c in common[1:]:
        s.append(f'<div class="l">{c}</div>')
    s.append(f'<div class="grp">{html.escape(biz_title)}</div>')
    for i in items:
        s.append(f'<div class="sub">{html.escape(i)}</div>')
    s.append("</div>")
    return "".join(s)

# ------------------------------------------------------------------ page shell
def header(cur):
    nav = [("index.html", T("nav_home")), ("getting-started.html", T("nav_gs")), ("index.html#guides", T("nav_guides")), ("help.html", T("nav_help"))]
    links = ""
    for href, label in nav:
        c = ' class="cur"' if href == cur else ""
        links += f'<a href="{href}"{c}>{label}</a>'
    sw = ""
    for code in ("en", "ml", "ar"):
        on = ' class="on"' if code == CUR["lang"] else ""
        sw += f'<a href="{CUR["switch"].get(code, "../"+code+"/index.html")}"{on} lang="{code}" hreflang="{code}">{LANG_META[code]["name"]}</a>'
    return f'''<header class="site-header"><div class="in">
<a class="brand" href="index.html"><span class="mark">{html.escape(CONFIG["BRAND"][:1].upper())}</span><span>{CONFIG["BRAND"]}<small>{T("sub_brand")}</small></span></a>
<nav class="site-nav">{links}<a class="btn" href="{CONFIG["APP_URL"]}/login/" target="_blank" rel="noopener">{T("open_app")}</a><span class="lang">{sw}</span></nav>
</div></header>'''

def footer():
    return f'''<footer class="site-footer"><div class="in">
<div><b>{CONFIG["BRAND"]}</b><br>{T("footer_tag")}{("<br><small style='opacity:.75'>" + T("powered").format(c=CONFIG["COMPANY"]) + "</small>") if CONFIG.get("COMPANY") else ""}</div>
<div><b>{T("footer_help")}</b><br>{T("footer_call")}: <span dir="ltr">{CONFIG["WHATSAPP"]}</span><br>{T("footer_email")}: <a href="mailto:{CONFIG["EMAIL"]}">{CONFIG["EMAIL"]}</a></div>
<div><b>{T("footer_quick")}</b><br><a href="getting-started.html">{T("q_gs")}</a> · <a href="help.html">{T("q_help")}</a> · <a href="index.html#guides">{T("q_all")}</a><br><a href="/">{T("q_site")}</a> · <a href="/terms/">{T("q_terms")}</a> · <a href="/privacy/">{T("q_privacy")}</a> · <a href="/refund-policy/">{T("q_refund")}</a></div>
</div></footer>'''

def helpbox():
    return f'''<div class="helpbox"><div><h3>{T("help_h")}</h3><p>{T("help_p").format(wa=CONFIG["WHATSAPP"])}</p></div>
<a class="btn light" href="help.html">{T("help_btn")}</a></div>'''

def page(title, body, cur="", desc=""):
    lang = CUR["lang"]; meta = LANG_META[lang]
    fonts = ""
    if lang in ("ml", "ar"):
        fonts = '<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin><link href="https://fonts.googleapis.com/css2?family=Noto+Sans+Malayalam:wght@400;600;700;800&family=Noto+Sans+Arabic:wght@400;600;700;800&display=swap" rel="stylesheet">'
    return f'''<!DOCTYPE html>
<html lang="{meta["lang"]}" dir="{meta["dir"]}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(html.unescape(title))} · {CONFIG["BRAND"]}</title>
<meta name="description" content="{html.escape(html.unescape(desc or title))}">
{fonts}<link rel="stylesheet" href="../style.css">
</head><body>
{header(cur)}
{body}
{footer()}
</body></html>'''

def hero(icon, title, lead, chips=(), crumb=None, cta=True):
    cr = f'<div class="crumb">{crumb}</div>' if crumb else ""
    ch = '<div class="chips">' + "".join(f'<span class="chip">{c}</span>' for c in chips) + "</div>" if chips else ""
    ct = f'<div class="cta"><a class="btn light" href="{CONFIG["APP_URL"]}/login/" target="_blank" rel="noopener">{T("open_app")}</a><a class="btn ghost" style="color:#fff!important;border-color:rgba(255,255,255,.4)" href="getting-started.html">{T("new_here")}</a></div>' if cta else ""
    ic = f'<div class="ico">{icon}</div>' if icon else ""
    return f'<section class="hero"><div class="in">{cr}{ic}<h1>{title}</h1><p class="lead">{lead}</p>{ch}{ct}</div></section>'

def doc(sections, extra_after=""):
    toc = f'<aside class="toc"><h4>{T("on_page")}</h4>' + "".join(f'<a href="#{i}">{t}</a>' for i, t, _, _ in sections) + "</aside>"
    blocks = ""
    for n, (i, t, inner, ic) in enumerate(sections, 1):
        blocks += f'<section class="blk" id="{i}"><h2><span class="n">{ic or n}</span>{t}</h2>{inner}</section>\n'
    return f'<div class="wrap"><div class="doc">{toc}<main>{blocks}{extra_after}</main></div></div>'
