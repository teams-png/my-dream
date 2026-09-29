const q = new URLSearchParams(location.search);
document.getElementById("server").textContent = q.get("server") || "";
document.getElementById("detail").textContent = q.get("error") || "";
const retry = () => window.bookpilotShell.retry();
document.getElementById("retry").addEventListener("click", retry);
document.getElementById("settings").addEventListener("click", () => window.bookpilotDesktop.openSettings());
addEventListener("online", retry);
setInterval(() => { if (navigator.onLine) retry(); }, 15000);
