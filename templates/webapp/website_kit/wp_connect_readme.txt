{% autoescape off %}=== BookPilot Connect — {{ company }} ===
Contributors: bookpilot
Tags: booking, contact form, menu, jobs, crm
Requires at least: 5.0
Stable tag: 1.0.0
License: GPLv2 or later

Connects this WordPress site to {{ company }}'s BookPilot account. Everything is already filled in.

== Installation ==
1. Plugins → Add New → Upload Plugin → choose this zip → Install → Activate.
2. Add the shortcodes to your pages.

== Shortcodes ==
[bookpilot_enquiry]                       Contact / enquiry form → BookPilot CRM leads
[bookpilot_catalogue]                     Live menu / services / products / rooms / courses / jobs
[bookpilot_catalogue category="Drinks" limit="12"]
[bookpilot_info field="phone"]            name, phone, email, address, country, currency, vat_number
{% if booking_slug %}[bookpilot_booking]                       Online booking form (requests go to BookPilot → Booking requests)
{% endif %}{% if careers_slug %}[bookpilot_form]                          Detailed job application form (goes to BookPilot → Candidates)
{% endif %}All forms take lang="ar", thanks="https://your-site/thank-you", color="#0f766e".
{% endautoescape %}
