# BookPilot posters · a product of MMM Technologie

Ready-to-post designs for BookPilot. Every poster carries the BookPilot logo, the "A product of MMM Technologie" badge,
the WhatsApp number +974 3398 2304 and a QR code that opens a WhatsApp chat.

| File | Size | Use |
|---|---|---|
| `01-bookpilot-main.png` | 1080×1350 | Main poster: all-in-one business software |
| `02-restaurant.png` | 1080×1350 | Restaurants & cafés |
| `03-salon-spa.png` | 1080×1350 | Salons, spas & beauty |
| `04-supermarket-grocery.png` | 1080×1350 | Supermarkets & grocery |
| `05-mobile-computer-shop.png` | 1080×1350 | Mobile & computer shops |
| `06-fashion-retail.png` | 1080×1350 | Fashion & retail shops |
| `07-free-demo.png` | 1080×1350 | Free trial / free demo, 12 business types |
| `01-bookpilot-main-story.png` | 1080×1920 | Instagram / WhatsApp status story |
| `01-bookpilot-main-a4.pdf` / `.png` | A4 | Print flyer |

1080×1350 is the portrait size for Instagram and Facebook posts; it also looks good on WhatsApp.

## Changing a poster

The text, colours and screenshots are in `src/generate.py` (one entry per poster) and the style in `src/posters.css`.
Run `python3 src/generate.py` to rebuild `src/posters.html` (open it in a browser to see every poster), then
`python3 src/render.py` to export the PNGs and the PDF. The screenshots in `src/img` are real BookPilot demo screens.
