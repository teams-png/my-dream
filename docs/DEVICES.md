# Devices & Hardware

Open **Settings → Devices & Printers** on each till, kitchen screen or waiter tablet.
Settings are saved in that browser, so every device can use different hardware.

| Device | How it connects | Browser |
|---|---|---|
| Any installed printer (A4, thermal, PDF) | Normal print window ("Any printer") | All |
| USB thermal printer (ESC/POS) | WebUSB, press **Connect printer** | Chrome / Edge (Windows, Mac, Linux, Android) |
| Serial / USB-serial / Bluetooth-serial printer | Web Serial | Chrome / Edge on a computer |
| Network (LAN / Wi-Fi) printer, port 9100 | Local print agent (below) | All |
| Cash drawer | RJ11 cable into the receipt printer's DK port; opened with ESC/POS | Needs USB, serial or network receipt printer |
| Barcode scanner | Keyboard mode (USB or Bluetooth HID); matches product SKU | All |
| Customer display | Second monitor: **Open customer display**, drag it over, press F11 | All (same browser) |
| Order alarm | Built-in chime/bell/beep; tap "enable sound" once on the kitchen screen | All |

## Automatic printing
- **POS: print KOT when sent**: prints each kitchen round from the till.
- **Kitchen screen: print every new ticket**: prints on the kitchen PC when tickets arrive.
  Turn on only one of the two to avoid double tickets.
- **Print receipt when paid**: prints the bill (and opens the drawer for cash).

## Network printers: print agent
Browsers cannot talk to network printers directly. On the till computer run:

```bash
python scripts/print_agent.py --origin https://<your-app>.onrender.com
```

It listens on `http://127.0.0.1:8719`, accepts jobs only for printers on the
local network, and needs no extra packages. Put the printer's IP address on the
Devices page and press **Test print**.

## Silent printing without the dialog
For "Any printer" mode, start Chrome with `--kiosk-printing` so receipts print
immediately on the default printer.
