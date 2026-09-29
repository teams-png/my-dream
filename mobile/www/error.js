// Shown by Capacitor when the BookPilot server can't be reached.
const serverUrl = window.BOOKPILOT_URL || "";
function retry() {
  if (serverUrl) location.href = serverUrl; else history.back();
}
document.getElementById("retry").addEventListener("click", retry);
addEventListener("online", retry);
setInterval(() => { if (navigator.onLine) retry(); }, 15000);
