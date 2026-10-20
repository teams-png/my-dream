# MMM Technologie website

A five-page Bootstrap 5 website for MMM Technologie. No build step: upload the folder as it is to any web host.

| Page | What's on it |
|---|---|
| `index.html` | Home: animated network hero, typing terminal, tech marquee, counters, what we do, BookPilot spotlight, services, process |
| `bookpilot.html` | BookPilot: features, screen tabs, 100+ industries with live demos, platforms & security, FAQ |
| `services.html` | IT services: circuit-line hero with service orbit, 9 services, engineering, IT support plans |
| `about.html` | About: story, mission & values, a timeline that fills as you scroll, why us |
| `contact.html` | Contact: WhatsApp / call tiles, enquiry form that opens WhatsApp, map, quick answers |

## Your contact details

Open `config.js`: phone, WhatsApp, email, domain, address and working hours live there. Every page updates itself;
anything left empty stays hidden. The enquiry form opens WhatsApp with the visitor's message already written.

`bookpilot_url` is where BookPilot runs. "Start free trial", "See plans", live demos and "Sign in" open it.

## Menu and footer

They are written once in `js/layout.js` and shared by every page.

## Animations

Network canvas (reacts to the mouse), typing terminal and word rotator, orbiting service icons, circuit lines,
gradient-border cards, 3D tilt, counters, reveal on scroll, scroll progress bar and a short logo preloader
(`js/main.js`, `css/style.css`). Visitors whose device asks for reduced motion get a calm, still version.

## Put it online

- **Hostinger / cPanel:** File Manager → `public_html` → upload everything in this folder.
- **Netlify / Cloudflare Pages:** drag this folder onto the site, then add your domain.
