# BookPilot apps: installable web app, desktop and mobile

All three open the same BookPilot server, so every feature, update and
language is the same everywhere. None of them shows a browser address
bar or tabs.

| | What it is | Where it comes from |
|---|---|---|
| **Installable web app** | Install BookPilot from Chrome / Edge / Safari; it opens in its own window. | Nothing to build. Use the **⬇ Install app** button, or iPhone: Share → *Add to Home Screen*. |
| **Desktop app** (`desktop/`) | Windows `.exe` installer, macOS `.dmg`, Linux `.AppImage`. Adds silent receipt printing to any installed printer. | GitHub Actions → **apps** workflow |
| **Android app** (`mobile/android`) | `.apk` to install directly; `.aab` for Google Play. | GitHub Actions → **apps** workflow |
| **iOS app** (`mobile/ios`) | iPhone / iPad app for the App Store. | Xcode on a Mac, with an Apple Developer account |

## 1. Which server the apps open

The apps open `https://bookpilot-web.onrender.com` by default. To use your
own domain:

1. In GitHub, go to **Settings → Secrets and variables → Actions → Variables**.
2. Add a variable `BOOKPILOT_URL`, e.g. `https://app.yourcompany.com`.

The desktop app can also be pointed at another server from its
**Settings** window (Ctrl+,).

## 2. Getting the installers

1. In GitHub, open **Actions → apps → Run workflow**. The workflow also
   runs by itself when `desktop/` or `mobile/` change, or when you push a
   tag such as `app-v1.0.1`.
2. When the run finishes, download from its **Artifacts** section:
   - `BookPilot-desktop-Windows`, `-macOS` and `-Linux`
   - `BookPilot-android`
   - `BookPilot-ios-simulator` (this only proves the iOS app compiles)

The installers are not code-signed yet:

- **Windows** shows "Windows protected your PC". Click *More info → Run
  anyway*.
- **macOS**: right-click the app and choose *Open* the first time.
- To remove these warnings, buy a code-signing certificate (Windows) or an
  Apple Developer ID (macOS) and add it to electron-builder's settings.

## 3. Desktop app features

- Opens straight to sign-in, then the dashboard. It remembers the window
  size.
- **F11** switches full screen. Settings can also start the app full
  screen, which suits a POS till.
- **Silent printing**: on **Devices**, choose *Any printer*, then pick the
  receipt or kitchen printer in *Printer (desktop app)*. Receipts and KOTs
  then print straight away, with no print window.
- USB and serial receipt printers, the cash drawer, barcode scanners and
  the customer display work as they do in Chrome.
- The offline POS works when the internet is down, as in Chrome.
- WhatsApp, maps and other outside links open in the normal browser.
- If the server can't be reached, a "Can't reach BookPilot" screen shows
  and retries by itself.

Run it locally:

```bash
cd desktop
npm install
BOOKPILOT_URL=http://localhost:8000 npm start
```

## 4. Android: publishing on Google Play

1. Create a Google Play developer account (one-time fee of USD 25).
2. Create an upload key once:
   ```bash
   keytool -genkey -v -keystore bookpilot-upload.jks -alias bookpilot -keyalg RSA -keysize 2048 -validity 10000
   ```
   Keep this file and its passwords safe. You need them for every update.
3. Add these GitHub repository **secrets**:
   - `ANDROID_KEYSTORE_BASE64`: the output of `base64 -w0 bookpilot-upload.jks`
   - `ANDROID_KEYSTORE_PASSWORD`, `ANDROID_KEY_ALIAS` (`bookpilot`) and
     `ANDROID_KEY_PASSWORD`
4. Run the workflow. Then upload `app-release.aab` from the
   `BookPilot-android` artifact in the Play Console.
5. The version code goes up by itself with every workflow run.

To try the app before publishing, install `app-debug.apk` on a phone.
You need to allow "install unknown apps".

## 5. iOS: publishing on the App Store

Apple only allows signing and uploading from a Mac.

1. Join the Apple Developer Program (USD 99 per year).
2. On a Mac with Xcode, run:
   ```bash
   cd mobile
   npm install
   BOOKPILOT_URL=https://your-domain npm run ios
   ```
   This opens Xcode.
3. In Xcode, under **Signing & Capabilities**, choose your team. Then use
   **Product → Archive** and **Distribute App** to send it to App Store
   Connect.

Apple reviews every app. Apps that only wrap a website can be rejected,
but this one adds native printing (AirPrint), offline selling, a native
splash screen and icons. In the review notes, give Apple a demo login.

## 6. Mobile app behaviour

- **Opening**: the app opens on sign-in, with a green splash screen and
  the BookPilot icon.
- **No connection**: a "No connection" screen shows and retries
  automatically. The offline POS keeps working once it has been opened
  online.
- **Printing**: receipts and invoices go through the phone's print
  service (Android printer apps, Wi-Fi printers, AirPrint, Save as PDF).
  Bluetooth thermal printers that pair directly with the phone would need
  an extra native plugin.
- **Android back button**: closes an open dialog or goes back one page.
  It exits the app only on the first page.

## 7. Updating the apps

- **Website changes**: the apps load the server, so a deploy updates them
  all at once. There is nothing to republish.
- **Changes in `desktop/` or `mobile/`** (icons, native features): rebuild
  and publish the app again. For desktop, send the new installer. For
  mobile, upload a new version to the stores.

Regenerate all icons after changing the logo:

```bash
python scripts/make_app_icons.py
cd mobile
npm run assets
```
