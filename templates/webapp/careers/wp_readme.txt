{% autoescape off %}=== BookPilot Recruitment Form ===
Contributors: bookpilot
Tags: recruitment, jobs, careers, application form, cv
Requires at least: 5.0
Stable tag: 1.0.0
License: GPLv2 or later

A detailed job application form for {{ company|cut:'*/' }}. Every application (with CV) goes straight to the BookPilot recruitment dashboard.

== Installation ==
1. WordPress admin → Plugins → Add New → Upload Plugin → choose bookpilot-recruitment-form.zip → Install → Activate.
2. Edit your Careers page and add the shortcode:  [bookpilot_form]
3. Publish. Done.

== Shortcode options ==
[bookpilot_form job="Electrician"]            pre-selects a job (title or BookPilot job id)
[bookpilot_form lang="ar"]                    Arabic form
[bookpilot_form color="#0f766e"]              button / heading colour
[bookpilot_form thanks="https://site/thanks"] go to your own thank-you page after sending
{% endautoescape %}
