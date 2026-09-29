// Writes app-config.json with the server the app opens by default.
// Set BOOKPILOT_URL when building, e.g. BOOKPILOT_URL=https://app.example.com npm run dist
const fs = require("fs");
const path = require("path");

const url = (process.env.BOOKPILOT_URL || "https://bookpilot-web.onrender.com").trim().replace(/\/+$/, "");
new URL(url); // fails loudly on a typo
fs.writeFileSync(path.join(__dirname, "..", "app-config.json"), JSON.stringify({ serverUrl: url }, null, 2) + "\n");
console.log("BookPilot desktop will open", url);
