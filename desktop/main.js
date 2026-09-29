// BookPilot desktop: the BookPilot web app in its own window (no browser
// address bar or tabs), with silent receipt printing to system printers and
// the offline POS working exactly as in Chrome.
const { app, BrowserWindow, Menu, ipcMain, session, shell } = require("electron");
const fs = require("fs");
const path = require("path");
const { pathToFileURL } = require("url");

const CONFIG = (() => {
  try { return JSON.parse(fs.readFileSync(path.join(__dirname, "app-config.json"), "utf8")); }
  catch (_) { return { serverUrl: "https://bookpilot-web.onrender.com" }; }
})();
const SETTINGS_FILE = () => path.join(app.getPath("userData"), "settings.json");
const PAGES = path.join(__dirname, "pages");
const ICON = path.join(__dirname, "pages", "icon.png");
const EXTERNAL_SCHEMES = new Set(["http:", "https:", "mailto:", "tel:", "whatsapp:"]);

let settings = loadSettings();
let mainWindow = null;
let settingsWindow = null;

function loadSettings() {
  let saved = {};
  try { saved = JSON.parse(fs.readFileSync(SETTINGS_FILE(), "utf8")); } catch (_) { /* first run */ }
  return { serverUrl: CONFIG.serverUrl, startFullscreen: false, zoom: 1, window: null, ...saved };
}

function saveSettings() {
  try {
    fs.mkdirSync(path.dirname(SETTINGS_FILE()), { recursive: true });
    fs.writeFileSync(SETTINGS_FILE(), JSON.stringify(settings, null, 2));
  } catch (err) { console.error("Could not save settings", err); }
}

function originOf(url) {
  try { return new URL(url).origin; } catch (_) { return null; }
}

const serverOrigin = () => originOf(settings.serverUrl);
const isServer = (url) => originOf(url) === serverOrigin();
const PAGES_URL = pathToFileURL(PAGES + path.sep).href;
const isLocalPage = (url) => typeof url === "string" && url.startsWith(PAGES_URL);

function validServerUrl(value) {
  let url;
  try { url = new URL(String(value || "").trim()); } catch (_) { return null; }
  const local = /^(localhost|127\.|10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.)/.test(url.hostname);
  if (url.protocol !== "https:" && !(url.protocol === "http:" && local)) return null;
  return url.origin + url.pathname.replace(/\/+$/, "");
}

function openExternal(url) {
  try {
    if (EXTERNAL_SCHEMES.has(new URL(url).protocol)) shell.openExternal(url);
  } catch (_) { /* ignore malformed links */ }
}

function loadServer(win = mainWindow) {
  if (win && !win.isDestroyed()) win.loadURL(settings.serverUrl).catch(() => { /* handled by did-fail-load */ });
}

function showOffline(win, errorDescription) {
  win.loadFile(path.join(PAGES, "offline.html"), {
    query: { server: settings.serverUrl, error: errorDescription || "" },
  }).catch(() => { /* replaced by another navigation */ });
}

function createMainWindow() {
  const bounds = settings.window || { width: 1320, height: 840 };
  mainWindow = new BrowserWindow({
    ...bounds,
    minWidth: 360,
    minHeight: 480,
    show: false,
    title: "BookPilot",
    icon: ICON,
    backgroundColor: "#f4f6fb",
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      sandbox: true,
      nodeIntegration: false,
      spellcheck: true,
    },
  });
  mainWindow.setMenuBarVisibility(false);
  if (settings.maximized) mainWindow.maximize();
  if (settings.startFullscreen) mainWindow.setFullScreen(true);
  mainWindow.once("ready-to-show", () => mainWindow.show());

  const remember = () => {
    if (mainWindow.isDestroyed()) return;
    settings.maximized = mainWindow.isMaximized();
    if (!settings.maximized && !mainWindow.isFullScreen()) settings.window = mainWindow.getBounds();
    settings.zoom = mainWindow.webContents.getZoomFactor();
    saveSettings();
  };
  mainWindow.on("close", remember);
  mainWindow.on("closed", () => { mainWindow = null; });

  wireContents(mainWindow.webContents, mainWindow);
  mainWindow.webContents.on("did-finish-load", () => mainWindow.webContents.setZoomFactor(settings.zoom || 1));
  mainWindow.webContents.on("did-fail-load", (_e, code, description, url, isMainFrame) => {
    // -3 is an aborted load (e.g. a redirect), not an error
    if (isMainFrame && code !== -3 && !isLocalPage(url)) showOffline(mainWindow, description);
  });
  loadServer();
}

function wireContents(contents, win) {
  // Only the BookPilot server (and the app's own pages) open inside the app;
  // WhatsApp, maps, payment receipts on other sites... open in the browser.
  contents.on("will-navigate", (event, url) => {
    if (!isServer(url) && !isLocalPage(url)) {
      event.preventDefault();
      openExternal(url);
    }
  });
  contents.setWindowOpenHandler(({ url }) => {
    if (isServer(url)) {
      return {
        action: "allow",
        overrideBrowserWindowOptions: {
          autoHideMenuBar: true, icon: ICON, width: 900, height: 800,
          webPreferences: { preload: path.join(__dirname, "preload.js"), contextIsolation: true, sandbox: true },
        },
      };
    }
    openExternal(url);
    return { action: "deny" };
  });
  contents.on("did-create-window", (child) => {
    child.setMenuBarVisibility(false);
    wireContents(child.webContents, child);
  });
  contents.on("before-input-event", (event, input) => {
    if (input.type !== "keyDown") return;
    const mod = input.control || input.meta;
    const key = input.key.toLowerCase();
    const handled = () => event.preventDefault();
    if (input.key === "F11") { win.setFullScreen(!win.isFullScreen()); handled(); }
    else if (input.key === "F5" || (mod && key === "r")) {
      if (input.shift) contents.reloadIgnoringCache(); else contents.reload();
      handled();
    }
    else if (mod && (key === "=" || key === "+")) { contents.setZoomFactor(Math.min(3, contents.getZoomFactor() + 0.1)); handled(); }
    else if (mod && key === "-") { contents.setZoomFactor(Math.max(0.5, contents.getZoomFactor() - 0.1)); handled(); }
    else if (mod && key === "0") { contents.setZoomFactor(1); handled(); }
    else if (mod && key === ",") { openSettings(); handled(); }
    else if (input.alt && input.key === "ArrowLeft" && contents.navigationHistory.canGoBack()) { contents.navigationHistory.goBack(); handled(); }
    else if (input.key === "F12" || (mod && input.shift && key === "i")) { contents.toggleDevTools(); handled(); }
  });
  contents.on("context-menu", (_e, params) => {
    const items = [];
    if (params.isEditable) items.push({ role: "cut" }, { role: "copy" }, { role: "paste" }, { type: "separator" }, { role: "selectAll" });
    else if (params.selectionText) items.push({ role: "copy" });
    if (params.linkURL) items.push({ label: "Open link in browser", click: () => openExternal(params.linkURL) });
    if (items.length) items.push({ type: "separator" });
    items.push(
      { label: "Back", enabled: contents.navigationHistory.canGoBack(), click: () => contents.navigationHistory.goBack() },
      { label: "Reload", click: () => contents.reload() },
      { label: "Full screen", type: "checkbox", checked: win.isFullScreen(), click: () => win.setFullScreen(!win.isFullScreen()) },
      { label: "Settings…", click: openSettings },
    );
    Menu.buildFromTemplate(items).popup({ window: win });
  });
}

function openSettings() {
  if (settingsWindow && !settingsWindow.isDestroyed()) { settingsWindow.focus(); return; }
  settingsWindow = new BrowserWindow({
    width: 520, height: 560, resizable: false, minimizable: false, maximizable: false,
    parent: mainWindow || undefined, modal: !!mainWindow, show: false, title: "BookPilot settings",
    icon: ICON, autoHideMenuBar: true, backgroundColor: "#f4f6fb",
    webPreferences: { preload: path.join(__dirname, "preload.js"), contextIsolation: true, sandbox: true },
  });
  settingsWindow.setMenuBarVisibility(false);
  settingsWindow.once("ready-to-show", () => settingsWindow.show());
  settingsWindow.on("closed", () => { settingsWindow = null; });
  settingsWindow.loadFile(path.join(PAGES, "settings.html"));
}

/* ------------------------------------------------------------- printing */

function printPage(url, { printer, allowScripts }) {
  return new Promise((resolve, reject) => {
    const win = new BrowserWindow({
      show: false,
      webPreferences: { sandbox: true, contextIsolation: true, javascript: !!allowScripts },
    });
    const done = (err) => { if (!win.isDestroyed()) win.destroy(); err ? reject(err) : resolve(true); };
    win.webContents.once("did-fail-load", (_e, _c, description) => done(new Error("Could not load the page to print: " + description)));
    win.webContents.once("did-finish-load", () => {
      // give fonts and images a moment to render
      setTimeout(() => {
        win.webContents.print(
          { silent: true, deviceName: printer || "", printBackground: true, margins: { marginType: "none" } },
          (ok, reason) => done(ok ? null : new Error("Printing failed: " + reason)),
        );
      }, 250);
    });
    win.loadURL(url).catch(() => { /* reported by did-fail-load */ });
  });
}

function fromServerPage(event) {
  const url = event.senderFrame && event.senderFrame.url;
  if (!isServer(url)) throw new Error("Not allowed");
}

function fromAppPage(event) {
  const url = event.senderFrame && event.senderFrame.url;
  if (!isLocalPage(url)) throw new Error("Not allowed");
}

ipcMain.handle("bp:printers", async (event) => {
  fromServerPage(event);
  const printers = await event.sender.getPrintersAsync();
  return printers.map((p) => ({ name: p.name, displayName: p.displayName || p.name, isDefault: !!p.isDefault }));
});

ipcMain.handle("bp:print-html", async (event, { html, printer }) => {
  fromServerPage(event);
  if (typeof html !== "string" || html.length > 2_000_000) throw new Error("Nothing to print.");
  // receipts built on the device: static HTML, scripts off
  return printPage("data:text/html;charset=utf-8," + encodeURIComponent(html), { printer, allowScripts: false });
});

ipcMain.handle("bp:print-url", async (event, { url, printer }) => {
  fromServerPage(event);
  if (!isServer(url)) throw new Error("Only BookPilot pages can be printed.");
  // server print pages call window.print() themselves; keep scripts off so no dialog appears
  return printPage(url, { printer, allowScripts: false });
});

ipcMain.handle("bp:open-settings", (event) => {
  const url = event.senderFrame && event.senderFrame.url;
  if (!isServer(url) && !isLocalPage(url)) throw new Error("Not allowed");
  openSettings();
});

ipcMain.handle("bp:get-settings", (event) => {
  fromAppPage(event);
  return { serverUrl: settings.serverUrl, defaultServerUrl: CONFIG.serverUrl, startFullscreen: !!settings.startFullscreen, version: app.getVersion() };
});

ipcMain.handle("bp:save-settings", (event, values) => {
  fromAppPage(event);
  const url = validServerUrl(values && values.serverUrl);
  if (!url) throw new Error("Enter the full address, starting with https://");
  const changed = url !== settings.serverUrl;
  settings.serverUrl = url;
  settings.startFullscreen = !!(values && values.startFullscreen);
  saveSettings();
  if (settingsWindow && !settingsWindow.isDestroyed()) settingsWindow.close();
  if (mainWindow) {
    mainWindow.setFullScreen(settings.startFullscreen || mainWindow.isFullScreen());
    if (changed || isLocalPage(mainWindow.webContents.getURL())) loadServer();
  }
  return true;
});

ipcMain.handle("bp:retry", (event) => {
  fromAppPage(event);
  loadServer();
});

/* ------------------------------------------------------------- app */

if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on("second-instance", () => {
    if (!mainWindow) return;
    if (mainWindow.isMinimized()) mainWindow.restore();
    mainWindow.focus();
  });

  app.whenReady().then(() => {
    app.setAppUserModelId("com.bookpilot.desktop");
    const ses = session.defaultSession;
    ses.setUserAgent(`${ses.getUserAgent()} BookPilotApp/${app.getVersion()} (desktop)`);

    // Camera (barcode), notifications, USB / serial printers: BookPilot server only.
    const allowed = new Set(["media", "notifications", "clipboard-sanitized-write", "fullscreen", "serial", "usb", "hid"]);
    ses.setPermissionRequestHandler((wc, permission, callback, details) => {
      callback(allowed.has(permission) && isServer(details.requestingUrl || wc.getURL()));
    });
    ses.setPermissionCheckHandler((wc, permission, requestingOrigin) => allowed.has(permission) && requestingOrigin === serverOrigin());
    ses.setDevicePermissionHandler((details) => details.origin === serverOrigin());
    // Chrome shows a device picker for USB / serial printers; here we pick the only (or first) one.
    ses.on("select-serial-port", (event, portList, _wc, callback) => {
      event.preventDefault();
      callback(portList.length ? portList[0].portId : "");
    });
    ses.on("select-usb-device", (event, details, callback) => {
      event.preventDefault();
      callback(details.deviceList.length ? details.deviceList[0].deviceId : undefined);
    });

    if (process.platform === "darwin") {
      // macOS needs a menu for Cmd+C / Cmd+V / Cmd+Q to work
      Menu.setApplicationMenu(Menu.buildFromTemplate([
        { role: "appMenu" },
        { role: "editMenu" },
        { label: "View", submenu: [{ role: "reload" }, { role: "togglefullscreen" }, { role: "zoomIn" }, { role: "zoomOut" }, { role: "resetZoom" }, { type: "separator" }, { label: "Settings…", accelerator: "Cmd+,", click: openSettings }] },
        { role: "windowMenu" },
      ]));
    } else {
      Menu.setApplicationMenu(null);
    }
    createMainWindow();
    app.on("activate", () => { if (!BrowserWindow.getAllWindows().length) createMainWindow(); });
  });

  app.on("window-all-closed", () => {
    if (process.platform !== "darwin") app.quit();
  });
}
