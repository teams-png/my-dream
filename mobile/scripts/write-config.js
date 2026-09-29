// Writes capacitor.config.json: which BookPilot server the app opens.
// BOOKPILOT_URL=https://app.example.com npm run sync
const fs = require("fs");
const path = require("path");

const serverUrl = (process.env.BOOKPILOT_URL || "https://bookpilot-web.onrender.com").trim().replace(/\/+$/, "");
const host = new URL(serverUrl).host;
const config = {
  appId: "com.bookpilot.app",
  appName: "BookPilot",
  webDir: "www",
  appendUserAgent: "BookPilotApp/1.0 (mobile)",
  backgroundColor: "#f4f6fb",
  server: {
    url: serverUrl,
    cleartext: serverUrl.startsWith("http://"),
    allowNavigation: [host],
    errorPath: "error.html",
  },
  android: { allowMixedContent: false, captureInput: true },
  // app-bound domains let iOS run the service worker (offline POS)
  ios: { contentInset: "automatic", scrollEnabled: true, limitsNavigationsToAppBoundDomains: true },
  plugins: {
    SplashScreen: { launchShowDuration: 900, backgroundColor: "#14532d", showSpinner: false },
    StatusBar: { style: "DARK", backgroundColor: "#14532d", overlaysWebView: false },
  },
};
fs.writeFileSync(path.join(__dirname, "..", "capacitor.config.json"), JSON.stringify(config, null, 2) + "\n");
// the offline page needs to know where to go back to
fs.writeFileSync(path.join(__dirname, "..", "www", "app-config.js"), `window.BOOKPILOT_URL = ${JSON.stringify(serverUrl)};\n`);

// iOS: list the server as an app-bound domain in Info.plist
const plist = path.join(__dirname, "..", "ios", "App", "App", "Info.plist");
if (fs.existsSync(plist)) {
  let xml = fs.readFileSync(plist, "utf8").replace(/\s*<key>WKAppBoundDomains<\/key>\s*<array>[\s\S]*?<\/array>/, "");
  const hostname = new URL(serverUrl).hostname;
  xml = xml.replace(/<\/dict>\s*<\/plist>\s*$/, `\t<key>WKAppBoundDomains</key>\n\t<array>\n\t\t<string>${hostname}</string>\n\t</array>\n</dict>\n</plist>\n`);
  fs.writeFileSync(plist, xml);
}
console.log("BookPilot mobile will open", serverUrl);
