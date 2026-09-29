# Offline restaurant POS

Keeps the counter running when the internet drops.

## How it works
1. While online, the restaurant dashboard, POS and kitchen pages quietly save the
   **Offline POS** page, the menu (with photos) and prices on the device.
2. If the connection drops, a red banner offers **Open offline POS**. Opening any
   restaurant page without internet also shows it automatically.
3. Bills are stored on the device (IndexedDB) with numbers like `OFF-4K2P-0007`.
   KOTs and receipts print locally; cash drawer and customer display keep working.
4. When the internet returns, bills are sent automatically (or press **Sync now**):
   - paid bills become paid orders with invoices (same prices and tax as charged);
   - open dine-in bills become open orders you continue in the normal POS.
   Re-sending is safe: every bill has a unique id, so duplicates are impossible.
5. If the server cannot finish a paid bill (for example the payment does not match
   the total, or recipe stock is missing) the sale is kept and shown on the
   restaurant dashboard under **Offline bills that need attention**.

## Limits
- Open the restaurant dashboard or POS once while online on each device first.
- Another device's kitchen screen does not receive orders while offline; use a
  kitchen printer (USB/serial, or LAN with the print agent) for KOTs.
- The user must still be signed in when the internet returns; otherwise the page
  asks to sign in again and then syncs. Bills are never lost from the device.

## Shop / retail POS (`/pos/`)

The shop till works offline in the same way, with no separate page:

1. **Keep it ready.** Open `/pos/` once while online on each till. The
   service worker saves the page (products, prices, customers) every time
   it loads online, so it always has the latest catalogue.
2. **Selling offline.** If the internet or the server is down, `/pos/` still
   opens from the device. Scan or tap products and take **cash, card or
   bank** payments as normal. The sale is saved in the browser (IndexedDB
   `bookpilot-retail`), the receipt prints from the device (or the browser
   print dialog), and the cash drawer opens. The top bar shows
   "⏳ N waiting to sync".
   Coupons, credit and instalment sales need the internet.
3. **Back online.** The till sends the saved sales to
   `/pos/offline/sync/` by itself (also every 30 s, or tap the chip). Each
   sale becomes a normal invoice dated the day it was sold, with stock and
   accounts updated.
4. **No double billing.** Every sale carries a `client_id`. If the answer
   to a normal checkout is lost (timeout, dropped Wi-Fi), the till keeps the
   sale for sync under the same id, and the server returns the invoice it
   already made instead of creating a second one.
5. **Needs attention.** If the server can no longer accept a sale (for
   example the item or IMEI was sold elsewhere meanwhile), it is kept under
   **POS → Offline sales → Needs attention** with the reason. Fix the cause
   and press **Retry**, or **Mark handled** after sorting it out by hand.

Other POS improvements: category rail, stock badges, IMEI picker, held
(parked) sales per till, quick-cash buttons with change, keyboard shortcuts
(F2 search, F9 pay), customer display and printer support from Devices.
