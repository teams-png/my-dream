# BookPilot posters · Loop Technologies

Two feed posters (1080×1350) for Instagram and Facebook, in the Loop Technologies colours (purple `#4523bc`, charcoal `#262a30`).

| File | Poster |
|---|---|
| `01-bookpilot-loop-main.png` | Run your whole business from one app: dashboard, phone, six features |
| `02-bookpilot-loop-free-trial.png` | One app for every kind of business: business types, 100+ types, 3 steps to start |

Both show WhatsApp **+91 98475 54224** and a QR code that opens a WhatsApp chat with that number.

## Changing them

- Text, number and layout: `src/posters.html`
- QR code: `src/img/qr-whatsapp.svg`, made with `segno` for `https://wa.me/919847554224`
- Logo: `src/img/loop-logo.png` (cut out from the logo with a transparent background)

Render again with `python3 src/render.py` (needs Playwright with Chromium; set `CHROME` to its path if it is not found).
