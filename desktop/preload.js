// Small, safe bridge between the web pages and the desktop app. The main
// process checks which page is calling before doing anything.
const { contextBridge, ipcRenderer } = require("electron");

const onAppPage = location.protocol === "file:";

contextBridge.exposeInMainWorld("bookpilotDesktop", {
  isDesktop: true,
  platform: process.platform,
  printers: () => ipcRenderer.invoke("bp:printers"),
  printHtml: (html, options = {}) => ipcRenderer.invoke("bp:print-html", { html, printer: options.printer }),
  printUrl: (url, options = {}) => ipcRenderer.invoke("bp:print-url", { url, printer: options.printer }),
  openSettings: () => ipcRenderer.invoke("bp:open-settings"),
});

if (onAppPage) {
  contextBridge.exposeInMainWorld("bookpilotShell", {
    getSettings: () => ipcRenderer.invoke("bp:get-settings"),
    saveSettings: (values) => ipcRenderer.invoke("bp:save-settings", values),
    retry: () => ipcRenderer.invoke("bp:retry"),
  });
}
