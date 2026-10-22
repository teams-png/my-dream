# Loop Technologies website

A multi-page static website (HTML + Bootstrap 5, no build step) for Loop Technologies, with BookPilot as the main product.

## Pages
| File | Page |
|---|---|
| `index.html` | Home: hero, BookPilot spotlight, services, AI, clients, process |
| `bookpilot.html` | BookPilot: features, screens, industries, ₹ pricing, FAQ |
| `services.html` | Web, software, mobile apps, UI/UX & design, marketing, cloud, IT support |
| `ai.html` | AI chatbots, WhatsApp assistant, automation, document AI, insights |
| `work.html` | Clients and BookPilot case studies |
| `about.html` | Story, mission, values |
| `contact.html` | Contact tiles + enquiry form that opens WhatsApp |

## Change your details
- **`config.js`**: phone, WhatsApp, email, domain, address, hours, social links and the BookPilot app link. Every page updates itself; empty values are hidden.
- **`clients.js`**: add one line per client (name, logo, website, work done, place). Put logos in `assets/clients/`. Until the list has clients, the site shows a "Your business could be here" box.
- The menu and footer for all pages are in `js/layout.js`.
- Prices are on `bookpilot.html` (pricing section) and in the BookPilot band on `index.html`.

## Upload
Upload the whole folder to any web host (Hostinger, cPanel, Netlify, GitHub Pages, Render static site) and point `looptechnologies.in` to it. Bootstrap and the icons are included in `vendor/`, so only the Google Fonts load from outside.
