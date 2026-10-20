# MMM Technologie website

A one-page Bootstrap 5 website for MMM Technologie: BookPilot, the industries it serves, IT services, how we work,
FAQ and a contact form. No build step: upload the folder as it is to any web host.

## Add your contact details

Open `config.js` and fill in `phone`, `whatsapp` (numbers only, with country code), `email` and `domain`.
Every place on the page updates itself; anything left empty stays hidden. The enquiry form opens WhatsApp
(or email when there is no WhatsApp number) with the visitor's message already written.

`bookpilot_url` is where BookPilot runs. The "Try BookPilot free", "See plans", demo and "Sign in" buttons open it.

## Put it online

- **Hostinger / cPanel:** File Manager → `public_html` → upload everything in this folder (`index.html` at the top).
- **Netlify / Cloudflare Pages:** drag this folder onto the site, then add your domain.
- **GitHub Pages:** publish this folder.

## Files

- `index.html`: the page
- `config.js`: your phone, WhatsApp, email, domain, address, hours
- `css/style.css`: colours from the logo (navy `#0b2a57`, teal `#0197ab`)
- `js/main.js`: fills in the details, menu, scroll effects, enquiry form
- `assets/`: logo (transparent PNG, white version for dark backgrounds), favicon and BookPilot screenshots
