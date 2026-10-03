{% autoescape off %}=== BookPilot Booking Form ===
Contributors: bookpilot
Tags: booking, appointment, reservation, rooms, table booking
Requires at least: 5.0
Stable tag: 1.0.0
License: GPLv2 or later

Online booking form for {{ company|cut:'*/' }}. Every booking request goes straight to BookPilot (Booking requests and the dashboard), where staff confirm it.

== Installation ==
1. WordPress admin → Plugins → Add New → Upload Plugin → choose bookpilot-booking-form.zip → Install → Activate.
2. Edit your booking / contact page and add the shortcode:  [bookpilot_booking]
3. Publish. Done.

== Shortcode options ==
[bookpilot_booking item="Haircut"]              pre-selects a service / room / vehicle (name or BookPilot id)
[bookpilot_booking lang="ar"]                   Arabic form
[bookpilot_booking color="#0f766e"]             button colour
[bookpilot_booking thanks="https://site/thanks"] go to your own thank-you page after sending
{% endautoescape %}
