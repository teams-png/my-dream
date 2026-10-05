{% autoescape off %}=== BookPilot Connect — {{ company }} ===
Contributors: bookpilot
Tags: booking, contact form, menu, jobs, crm
Requires at least: 5.0
Stable tag: 1.2.0
License: GPLv2 or later

Connects this WordPress site to {{ company }}'s BookPilot account. Everything is already filled in.

== Installation ==
1. Plugins → Add New → Upload Plugin → choose this zip → Install → Activate.
2. Add the shortcodes to your pages.

== Shortcodes ==
[bookpilot_enquiry]                       Contact / enquiry form → BookPilot CRM leads
[bookpilot_catalogue]                     Live menu / services / products / rooms / courses / jobs
[bookpilot_catalogue category="Drinks" limit="12"]
[bookpilot_catalogue hide_sold_out="yes"]  Hide items marked not available in the POS
[bookpilot_catalogue order="no"]           Menu without the "+ Add" cart buttons
[bookpilot_offers]                        Offers running today
[bookpilot_info field="phone"]            name, phone, email, address, country, currency, vat_number
{% if booking_slug %}[bookpilot_booking]                       Online booking form (requests go to BookPilot → Booking requests)
{% endif %}{% if careers_slug %}[bookpilot_form]                          Detailed job application form (goes to BookPilot → Candidates)
{% endif %}Online orders (restaurants): when "Take orders from my website" is switched on in BookPilot →
Online orders, the menu shows "+ Add" buttons and a cart. Orders arrive in BookPilot → Online orders.
If you use a page cache (LiteSpeed Cache on Hostinger), purge it after switching ordering on or off.

All forms take lang="ar", thanks="https://your-site/thank-you", color="#0f766e".
{% endautoescape %}
