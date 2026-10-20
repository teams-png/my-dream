"""Writes posters.html from the poster list below: every BookPilot poster on one page, each a fixed-size box. Run: python3 generate.py"""
import html
import os

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "posters.html")
PHONE = "+974 3398 2304"

STAR = ('<svg viewBox="0 0 64 64" aria-hidden="true"><defs><linearGradient id="bpg{n}" x1="0" y1="0" x2="1" y2="1">'
        '<stop offset="0" stop-color="#2f7bff"/><stop offset="1" stop-color="#0197ab"/></linearGradient></defs>'
        '<rect width="64" height="64" rx="16" fill="url(#bpg{n})"/>'
        '<path d="M32 9 L37 27 L55 32 L37 37 L32 55 L27 37 L9 32 L27 27 Z" fill="#fff"/></svg>')


def head(n):
    return (f'<div class="top"><div class="bp-logo">{STAR.format(n=n)}<span>Book<b>Pilot</b></span></div>'
            '<div class="by"><img src="img/mmm-mark-white.png" alt=""><div><small>A product of</small><span>MMM <b>Technologie</b></span></div></div></div>')


def foot(cta="Book your free demo"):
    return ('<div class="foot"><div class="wa"><i class="bi bi-whatsapp"></i><div><small>' + cta + '</small>'
            f'<b dir="ltr">{PHONE}</b></div></div>'
            '<div class="qr"><img src="img/qr-whatsapp.svg" alt="WhatsApp QR code"><small>Scan to<br>chat</small></div></div>')


def feats(items):
    return '<ul class="feats">' + "".join(f'<li><i class="bi {i}"></i>{t}</li>' for i, t in items) + "</ul>"


def browser(img, title, cls=""):
    return (f'<div class="browser {cls}"><div class="bar"><i></i><i></i><i></i><span>{title}</span></div>'
            f'<img src="img/{img}" alt=""></div>')


def chip(icon, b, s, cls):
    return f'<div class="float {cls}"><i class="bi {icon}"></i><div><b>{b}</b><small>{s}</small></div></div>'


POSTERS = [
    dict(id="01-bookpilot-main", accent="#22d3e6", eyebrow="All-in-one business software",
         h='Run your whole business from <em>one app.</em>',
         sub="Billing, stock, staff, accounts and VAT for shops, restaurants, salons and service companies.",
         visual=browser("mobile_shop-pos.webp", "BookPilot · Point of sale", "b-main") + '<img class="phone" src="img/bookpilot-phone.webp" alt="">'
         + chip("bi-receipt", "Bill in seconds", "POS · barcode · WhatsApp", "f1") + chip("bi-wifi-off", "Works offline", "Syncs when back online", "f2"),
         feats=[("bi-upc-scan", "POS & billing"), ("bi-box-seam", "Stock & branches"), ("bi-calculator", "Accounts & VAT"),
                ("bi-person-badge", "Staff & payroll"), ("bi-bar-chart-line", "Reports"), ("bi-translate", "Arabic & English")]),
    dict(id="02-restaurant", accent="#ffa94d", eyebrow="For restaurants & cafés",
         h='From order to kitchen to bill, <em>in one tap.</em>',
         sub="Tables, KOT, kitchen screen, quick sale counter and monthly mess, all in BookPilot.",
         visual=browser("restaurant-pos.webp", "BookPilot · Restaurant POS", "b-main")
         + chip("bi-fire", "KOT sent to kitchen", "Table 4 · 3 items", "f1") + chip("bi-whatsapp", "Bill on WhatsApp", "QAR 39.50 · paid", "f2"),
         feats=[("bi-grid-3x3-gap", "Tables & orders"), ("bi-printer", "Kitchen tickets"), ("bi-lightning-charge", "Quick sale"),
                ("bi-calendar2-week", "Mess plans"), ("bi-wifi-off", "Works offline"), ("bi-graph-up", "Daily reports")]),
    dict(id="03-salon-spa", accent="#f783ac", eyebrow="For salons, spas & beauty",
         h='Book, serve and bill <em>beautifully.</em>',
         sub="Appointments, services, staff commission, packages and customer reminders on WhatsApp.",
         visual=browser("saloon-pos.webp", "BookPilot · Salon billing", "b-main")
         + chip("bi-calendar-check", "Appointment booked", "Today · 4:30 PM", "f1") + chip("bi-person-check", "Done by: Ahmed", "Staff commission tracked", "f2"),
         feats=[("bi-calendar3", "Appointments"), ("bi-scissors", "Services & packages"), ("bi-people", "Staff & commission"),
                ("bi-whatsapp", "WhatsApp reminders"), ("bi-gift", "Loyalty points"), ("bi-globe2", "Online booking")]),
    dict(id="04-supermarket-grocery", accent="#69db7c", eyebrow="For supermarkets & grocery",
         h='Fast counters. <em>Full shelves.</em>',
         sub="Barcode billing, weighing scales, offers and low-stock alerts across every branch.",
         visual=browser("supermarket-pos.webp", "BookPilot · Supermarket POS", "b-main")
         + chip("bi-upc-scan", "Scanned & billed", "4 items · 2 seconds", "f1") + chip("bi-exclamation-triangle", "Low stock alert", "Fresh milk · reorder now", "f2"),
         feats=[("bi-upc-scan", "Barcode billing"), ("bi-speedometer", "Weighing scale"), ("bi-tags", "Offers & coupons"),
                ("bi-box-seam", "Stock alerts"), ("bi-diagram-3", "Many branches"), ("bi-cart-check", "Online orders")]),
    dict(id="05-mobile-computer-shop", accent="#74c0fc", eyebrow="For mobile & computer shops",
         h='Every phone, every repair, <em>tracked.</em>',
         sub="IMEI stock, repair job cards with WhatsApp status, warranty, trade-in and instalments.",
         visual=browser("bookpilot-repairs.webp", "BookPilot · Repair job cards", "b-main") + '<img class="phone" src="img/bookpilot-phone.webp" alt="">'
         + chip("bi-tools", "Repair ready", "Customer told on WhatsApp", "f1") + chip("bi-upc", "IMEI recorded", "Samsung A15 · sold", "f2"),
         feats=[("bi-upc", "IMEI stock"), ("bi-tools", "Repair job cards"), ("bi-shield-check", "Warranty claims"),
                ("bi-arrow-left-right", "Trade-in"), ("bi-cash-coin", "Instalments"), ("bi-laptop", "Computer shop too")]),
    dict(id="06-fashion-retail", accent="#b197fc", eyebrow="For fashion & retail shops",
         h='Sizes, colours and stock, <em>sorted.</em>',
         sub="Variants by size and colour, barcode labels, offers and an online shop linked to your real stock.",
         visual=browser("clothing_store-pos.webp", "BookPilot · Fashion POS", "b-main")
         + chip("bi-tag", "Barcode labels", "Printed in one click", "f1") + chip("bi-bag-check", "Online order", "Added to today's sales", "f2"),
         feats=[("bi-palette", "Size & colour"), ("bi-upc", "Barcode labels"), ("bi-percent", "Offers"),
                ("bi-shop", "Online shop"), ("bi-people", "Loyalty"), ("bi-bar-chart", "Best sellers")]),
    dict(id="07-free-demo", accent="#22d3e6", eyebrow="Free trial · Free demo",
         h='See BookPilot running <em>your</em> business.',
         sub="We'll show you BookPilot set up for your kind of business, online or at your shop. No card, no obligation.",
         visual='<div class="demo-grid">' + "".join(
             f'<div class="tile"><i class="bi {i}"></i><b>{t}</b></div>' for i, t in [
                 ("bi-cup-hot", "Restaurants"), ("bi-basket2", "Supermarkets"), ("bi-phone", "Mobile shops"), ("bi-scissors", "Salons & spas"),
                 ("bi-bag-heart", "Fashion"), ("bi-heart-pulse", "Clinics & pharmacy"), ("bi-wrench-adjustable", "Services"), ("bi-person-workspace", "Recruitment"),
                 ("bi-car-front", "Garages"), ("bi-building", "Hotels & rentals"), ("bi-mortarboard", "Training"), ("bi-gem", "Jewellery")])
         + '</div><div class="big-count"><b>100+</b><span>business types ready to go</span></div>',
         feats=[("bi-check2-circle", "Free trial, no card"), ("bi-cloud-arrow-up", "Data moved for you"), ("bi-mortarboard", "Staff training"),
                ("bi-headset", "Local support"), ("bi-translate", "Arabic & English"), ("bi-phone", "Web · Windows · Android · iOS")]),
]


def poster(p, n, size="feed"):
    return (f'<section class="poster {size}" id="{p["id"]}{"" if size == "feed" else "-" + size}" style="--acc:{p["accent"]}">'
            '<div class="glow"></div><div class="grid"></div>' + head(f"{n}{size}") +
            f'<div class="copy"><span class="eyebrow"><span class="dot"></span>{html.escape(p["eyebrow"])}</span>'
            f'<h1>{p["h"]}</h1><p class="sub">{html.escape(p["sub"])}</p></div>'
            f'<div class="visual">{p["visual"]}</div>' + feats(p["feats"]) + foot() + "</section>")


CSS = open(os.path.join(HERE, "posters.css")).read()
body = "\n".join(poster(p, i) for i, p in enumerate(POSTERS))
body += "\n" + poster(POSTERS[0], 0, "story") + "\n" + poster(POSTERS[0], 0, "a4")
open(OUT, "w").write(f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>BookPilot posters · MMM Technologie</title>
<!-- BookPilot posters. Open this file in a browser to see every poster; each <section class="poster"> is one design.
     Feed posters are 1080×1350 (Instagram / Facebook / WhatsApp), the story is 1080×1920, the flyer is A4. -->
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@500;700&family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<link href="vendor/bootstrap-icons.min.css" rel="stylesheet">
<style>
{CSS}
</style>
</head>
<body>
{body}
</body>
</html>
""")
print("wrote", OUT)
