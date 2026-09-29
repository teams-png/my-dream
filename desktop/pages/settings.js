const $ = (id) => document.getElementById(id);
let defaults = "";
window.bookpilotShell.getSettings().then((s) => {
  $("url").value = s.serverUrl;
  $("fullscreen").checked = s.startFullscreen;
  defaults = s.defaultServerUrl;
  $("ver").textContent = "BookPilot desktop " + s.version;
});
$("reset").addEventListener("click", () => { $("url").value = defaults; });
$("form").addEventListener("submit", async (e) => {
  e.preventDefault();
  $("err").textContent = "";
  try {
    await window.bookpilotShell.saveSettings({ serverUrl: $("url").value, startFullscreen: $("fullscreen").checked });
  } catch (err) {
    $("err").textContent = String(err.message || err).replace(/^Error invoking remote method '[^']+': (Error: )?/, "");
  }
});
