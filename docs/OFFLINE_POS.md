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
