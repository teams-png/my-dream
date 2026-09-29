/*
 * BookPilot devices — talks to hardware attached to this till, from the browser.
 *
 *  Printers   : browser print dialog, USB (WebUSB), Serial/USB-serial (Web Serial),
 *               or a LAN printer through the local print agent (scripts/print_agent.py).
 *  Cash drawer: kicked through the receipt printer (ESC p).
 *  Scanner    : USB/Bluetooth barcode scanners in keyboard mode.
 *  Display    : a second window/monitor (customer display) fed via BroadcastChannel.
 *  Alarm      : synthesised chimes for new kitchen orders / ready orders.
 *
 * Settings are per till, so they live in this browser's localStorage.
 */
(function () {
  "use strict";
  const KEY = "bp.devices.v1";
  const DEFAULTS = {
    receipt: { mode: "browser", width: 48, host: "", port: 9100, baud: 9600, usb: null, serial: null },
    kitchen: { mode: "browser", width: 48, host: "", port: 9100, baud: 9600, usb: null, serial: null },
    autoPrintReceipt: false,
    autoPrintKot: false,
    kdsAutoPrint: false,
    drawer: { enabled: false, pin: 0 },
    scanner: { enabled: true },
    display: { enabled: false },
    alarm: { enabled: true, sound: "chime", volume: 0.8, repeat: 2 },
    agentUrl: "http://127.0.0.1:8719",
  };

  function load() {
    let saved = {};
    try { saved = JSON.parse(localStorage.getItem(KEY) || "{}"); } catch (e) { saved = {}; }
    const cfg = JSON.parse(JSON.stringify(DEFAULTS));
    for (const k of Object.keys(saved)) {
      cfg[k] = (typeof DEFAULTS[k] === "object" && DEFAULTS[k] !== null && !Array.isArray(DEFAULTS[k]))
        ? Object.assign({}, DEFAULTS[k], saved[k]) : saved[k];
    }
    return cfg;
  }
  function save(cfg) {
    try { localStorage.setItem(KEY, JSON.stringify(cfg)); return true; } catch (e) { return false; }
  }

  /* ------------------------------------------------------------ ESC/POS */
  const ESC = 0x1b, GS = 0x1d;
  const REPLACE = { "·": "-", "×": "x", "—": "-", "–": "-", "…": "...", "’": "'", "‘": "'", "“": '"', "”": '"', "₹": "Rs", "€": "EUR", "£": "GBP" };
  function ascii(text) {
    return String(text == null ? "" : text).replace(/[^\x20-\x7e\n]/g, ch => REPLACE[ch] !== undefined ? REPLACE[ch] : "?");
  }
  class Encoder {
    constructor(width) { this.width = width || 48; this.bytes = [ESC, 0x40]; }
    raw(arr) { this.bytes.push(...arr); return this; }
    text(t) { for (const c of ascii(t)) this.bytes.push(c.charCodeAt(0)); return this; }
    line(t = "") { return this.text(t).raw([0x0a]); }
    align(a) { return this.raw([ESC, 0x61, { left: 0, center: 1, right: 2 }[a] || 0]); }
    bold(on) { return this.raw([ESC, 0x45, on ? 1 : 0]); }
    size(w, h) { return this.raw([GS, 0x21, ((w - 1) << 4) | (h - 1)]); }
    rule(ch = "-") { return this.line(ch.repeat(this.width)); }
    pair(left, right, width) {
      width = width || this.width; left = ascii(left); right = ascii(right);
      const space = width - right.length - 1;
      const wrapped = wrap(left, Math.max(8, space));
      wrapped.forEach((part, i) => {
        if (i === wrapped.length - 1) this.line(part + " ".repeat(Math.max(1, width - part.length - right.length)) + right);
        else this.line(part);
      });
      return this;
    }
    feed(n = 3) { return this.raw([ESC, 0x64, n]); }
    cut() { return this.feed(4).raw([GS, 0x56, 0x42, 0x00]); }
    drawer(pin = 0) { return this.raw([ESC, 0x70, pin ? 1 : 0, 0x19, 0xfa]); }
    build() { return new Uint8Array(this.bytes); }
  }
  function wrap(text, width) {
    const words = ascii(text).split(/\s+/); const out = []; let cur = "";
    for (const w of words) {
      if ((cur + " " + w).trim().length > width) { if (cur) out.push(cur); cur = w.length > width ? w.slice(0, width) : w; }
      else cur = (cur + " " + w).trim();
    }
    if (cur || !out.length) out.push(cur);
    return out;
  }

  function buildReceipt(d, width, withDrawer, pin) {
    const e = new Encoder(width);
    e.align("center").bold(true).size(2, 2).line(d.company.name).size(1, 1).bold(false);
    if (d.company.address) wrap(d.company.address, width).forEach(l => e.line(l));
    if (d.company.phone) e.line(d.company.phone);
    e.rule().bold(true).line(d.title).bold(false);
    (d.meta || []).forEach(m => e.line(m));
    e.align("left").rule();
    (d.lines || []).forEach(l => { e.pair(`${l.qty} x ${l.name}`, l.amount); (l.extra || []).forEach(x => e.line("   " + x)); });
    e.rule();
    (d.totals || []).forEach(([k, v]) => e.pair(k, v));
    e.bold(true).size(1, 2).pair("TOTAL " + d.company.currency, d.grand_total).size(1, 1).bold(false);
    (d.payments || []).forEach(([k, v]) => e.pair(k, v));
    e.rule().align("center").line(d.footer || "Thank you!");
    e.cut();
    if (withDrawer) e.drawer(pin);
    return e.build();
  }
  function buildKot(d, width) {
    const e = new Encoder(width);
    e.align("center").bold(true).size(2, 2).line(d.title).size(1, 1).bold(false);
    (d.meta || []).forEach((m, i) => { if (i === 0) e.bold(true).size(2, 1).line(m).size(1, 1).bold(false); else e.line(m); });
    e.align("left").rule("=");
    (d.lines || []).forEach(l => {
      e.bold(true).size(1, 2).line(`${l.qty} x ${l.name}`).size(1, 1).bold(false);
      (l.extra || []).forEach(x => e.line("   " + x));
    });
    e.rule("=").cut();
    return e.build();
  }

  /* ---------------------------------------------------------- transports */
  const usbCache = {};
  async function findUsb(role, cfg) {
    if (!navigator.usb) throw new Error("This browser does not support USB printers. Use Chrome or Edge.");
    if (usbCache[role]) return usbCache[role];
    const want = cfg[role].usb;
    const devices = await navigator.usb.getDevices();
    const dev = devices.find(d => want && d.vendorId === want.vendorId && d.productId === want.productId && (!want.serialNumber || d.serialNumber === want.serialNumber));
    if (!dev) throw new Error("USB printer not connected. Open Devices settings and press Connect.");
    usbCache[role] = dev; return dev;
  }
  async function sendUsb(dev, data) {
    if (!dev.opened) await dev.open();
    if (dev.configuration === null) await dev.selectConfiguration(1);
    let iface = null, endpoint = null;
    for (const i of dev.configuration.interfaces) {
      for (const alt of i.alternates) {
        const ep = alt.endpoints.find(x => x.direction === "out" && x.type === "bulk");
        if (ep) { iface = i; endpoint = ep; break; }
      }
      if (endpoint) break;
    }
    if (!endpoint) throw new Error("This USB device has no printer output endpoint.");
    if (!iface.claimed) await dev.claimInterface(iface.interfaceNumber);
    for (let i = 0; i < data.length; i += 4096) await dev.transferOut(endpoint.endpointNumber, data.slice(i, i + 4096));
  }
  const serialCache = {};
  async function findSerial(role, cfg) {
    if (!navigator.serial) throw new Error("This browser does not support serial devices. Use Chrome or Edge on a computer.");
    if (serialCache[role]) return serialCache[role];
    const want = cfg[role].serial || {};
    const ports = await navigator.serial.getPorts();
    const port = ports.find(p => { const i = p.getInfo(); return i.usbVendorId === want.usbVendorId && i.usbProductId === want.usbProductId; }) || (ports.length === 1 ? ports[0] : null);
    if (!port) throw new Error("Serial printer not connected. Open Devices settings and press Connect.");
    serialCache[role] = port; return port;
  }
  async function sendSerial(port, data, baud) {
    if (!port.writable) await port.open({ baudRate: Number(baud) || 9600 });
    const writer = port.writable.getWriter();
    try { await writer.write(data); } finally { writer.releaseLock(); }
  }
  async function sendNetwork(cfg, target, data) {
    if (!target.host) throw new Error("Enter the printer's IP address in Devices settings.");
    let res;
    try {
      res = await fetch(cfg.agentUrl.replace(/\/$/, "") + "/print", {
        method: "POST", body: data,
        headers: { "Content-Type": "application/octet-stream", "X-Printer-Host": target.host, "X-Printer-Port": String(target.port || 9100) },
      });
    } catch (e) {
      throw new Error("Print agent is not running on this computer. Start scripts/print_agent.py (see Devices page).");
    }
    if (!res.ok) throw new Error("Printer error: " + (await res.text()));
  }
  /* In the BookPilot desktop app, "Any printer" can print silently to a
     chosen system printer instead of opening the print window. */
  function desktopPrinter(role) {
    const bridge = window.bookpilotDesktop;
    if (!bridge || !role) return null;
    const cfg = load();
    const r = role === "kitchen" && cfg.kitchen.mode === "same" ? cfg.receipt : cfg[role];
    return r && r.systemPrinter ? { bridge, printer: r.systemPrinter } : null;
  }
  function browserPrint(url, role) {
    const desk = desktopPrinter(role);
    if (desk && url) return desk.bridge.printUrl(new URL(url, location.href).href, { printer: desk.printer });
    if (window.bookpilotNative && url) return window.bookpilotNative.printUrl(url);
    return new Promise((resolve, reject) => {
      if (!url) return reject(new Error("Nothing to print."));
      const frame = document.createElement("iframe");
      frame.style.cssText = "position:fixed;right:0;bottom:0;width:0;height:0;border:0;visibility:hidden";
      frame.src = url;
      frame.onload = () => {
        try { frame.contentWindow.focus(); frame.contentWindow.print(); resolve(); }
        catch (e) { window.open(url, "_blank"); resolve(); }
        setTimeout(() => frame.remove(), 60000);
      };
      frame.onerror = () => reject(new Error("Could not load the print page."));
      document.body.appendChild(frame);
    });
  }
  function esc(t) { return String(t == null ? "" : t).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])); }
  function paperHtml(body, width) {
    const mm = Number(width) <= 32 ? 48 : 72;
    return `<!doctype html><html><head><meta charset="utf-8"><style>@page{size:${mm + 8}mm auto;margin:4mm}body{font:13px monospace;width:${mm}mm;margin:auto;color:#000}.c{text-align:center}.r{display:flex;justify-content:space-between;gap:8px}.l{border-top:1px dashed #000;margin:6px 0}h1{font-size:17px;margin:2px 0}.big{font-size:16px;font-weight:bold}</style></head><body>${body}</body></html>`;
  }
  function receiptHtml(d, width) {
    let b = `<div class="c"><h1>${esc(d.company.name)}</h1>${d.company.address ? esc(d.company.address) + "<br>" : ""}${d.company.phone ? esc(d.company.phone) + "<br>" : ""}${d.company.vat_number ? "VAT " + esc(d.company.vat_number) : ""}<div class="l"></div><b>${esc(d.title)}</b><br>${(d.meta || []).map(esc).join("<br>")}</div><div class="l"></div>`;
    (d.lines || []).forEach(l => { b += `<div class="r"><span>${esc(l.qty)} x ${esc(l.name)}</span><span>${esc(l.amount)}</span></div>` + (l.extra || []).map(x => `<div>&nbsp;&nbsp;${esc(x)}</div>`).join(""); });
    b += '<div class="l"></div>' + (d.totals || []).map(([k, v]) => `<div class="r"><span>${esc(k)}</span><span>${esc(v)}</span></div>`).join("");
    b += `<div class="r big"><span>TOTAL ${esc(d.company.currency)}</span><span>${esc(d.grand_total)}</span></div>` + (d.payments || []).map(([k, v]) => `<div class="r"><span>${esc(k)}</span><span>${esc(v)}</span></div>`).join("");
    return paperHtml(b + `<div class="l"></div><div class="c">${esc(d.footer || "Thank you!")}</div>`, width);
  }
  function kotHtml(d, width) {
    let b = `<div class="c"><h1>${esc(d.title)}</h1>${(d.meta || []).map(esc).join("<br>")}</div><div class="l"></div>`;
    (d.lines || []).forEach(l => { b += `<div class="big">${esc(l.qty)} x ${esc(l.name)}</div>` + (l.extra || []).map(x => `<div>&nbsp;&nbsp;${esc(x)}</div>`).join(""); });
    return paperHtml(b + '<div class="l"></div>', width);
  }
  function browserPrintHtml(html, role) {
    const desk = desktopPrinter(role);
    if (desk) return desk.bridge.printHtml(html, { printer: desk.printer });
    if (window.bookpilotNative) return window.bookpilotNative.printHtml(html);
    return new Promise(resolve => {
      const frame = document.createElement("iframe");
      frame.style.cssText = "position:fixed;right:0;bottom:0;width:0;height:0;border:0;visibility:hidden";
      frame.srcdoc = html;
      frame.onload = () => { try { frame.contentWindow.focus(); frame.contentWindow.print(); } catch (e) { /* ignore */ } resolve(); setTimeout(() => frame.remove(), 60000); };
      document.body.appendChild(frame);
    });
  }

  async function sendRaw(role, data) {
    const cfg = load();
    let target = cfg[role];
    if (role === "kitchen" && target.mode === "same") { role = "receipt"; target = cfg.receipt; }
    if (target.mode === "usb") return sendUsb(await findUsb(role, cfg), data);
    if (target.mode === "serial") return sendSerial(await findSerial(role, cfg), data, target.baud);
    if (target.mode === "network") return sendNetwork(cfg, target, data);
    throw new Error("raw-unavailable");
  }
  function modeOf(role) {
    const cfg = load(); const m = cfg[role].mode;
    return role === "kitchen" && m === "same" ? cfg.receipt.mode : m;
  }
  function widthOf(role) {
    const cfg = load(); const r = role === "kitchen" && cfg.kitchen.mode === "same" ? cfg.receipt : cfg[role];
    return Number(r.width) || 48;
  }
  async function getJson(url) {
    const res = await fetch(url, { credentials: "same-origin" });
    if (!res.ok) throw new Error("Could not load print data (" + res.status + ").");
    return res.json();
  }

  /* ---------------------------------------------------------- public API */
  const Devices = {
    load, save, DEFAULTS, Encoder, buildReceipt, buildKot,

    async connect(role, kind) {
      const cfg = load();
      if (kind === "usb") {
        if (!navigator.usb) throw new Error("USB printers need Chrome or Edge (desktop or Android).");
        const dev = await navigator.usb.requestDevice({ filters: [] });
        cfg[role].usb = { vendorId: dev.vendorId, productId: dev.productId, serialNumber: dev.serialNumber || "", name: dev.productName || "USB printer" };
        usbCache[role] = dev;
      } else if (kind === "serial") {
        if (!navigator.serial) throw new Error("Serial devices need Chrome or Edge on a computer.");
        const port = await navigator.serial.requestPort();
        const info = port.getInfo();
        cfg[role].serial = { usbVendorId: info.usbVendorId, usbProductId: info.usbProductId };
        serialCache[role] = port;
      }
      cfg[role].mode = kind;
      save(cfg);
      return cfg[role];
    },

    async printReceipt({ dataUrl, htmlUrl, drawer } = {}) {
      const cfg = load();
      if (modeOf("receipt") === "browser") return browserPrint(htmlUrl, "receipt");
      const data = await getJson(dataUrl);
      const kick = cfg.drawer.enabled && (drawer === undefined ? data.open_drawer : drawer);
      return sendRaw("receipt", buildReceipt(data, widthOf("receipt"), kick, cfg.drawer.pin));
    },

    async printKot({ dataUrl, htmlUrl } = {}) {
      const cfg = load();
      if (cfg.kitchen.mode === "none") return;
      if (modeOf("kitchen") === "browser") return browserPrint(htmlUrl, "kitchen");
      return sendRaw("kitchen", buildKot(await getJson(dataUrl), widthOf("kitchen")));
    },

    /* print from data held on this device (used by the offline POS) */
    async printReceiptData(data, { drawer } = {}) {
      const cfg = load();
      if (modeOf("receipt") === "browser") return browserPrintHtml(receiptHtml(data, widthOf("receipt")), "receipt");
      const kick = cfg.drawer.enabled && (drawer === undefined ? data.open_drawer : drawer);
      return sendRaw("receipt", buildReceipt(data, widthOf("receipt"), kick, cfg.drawer.pin));
    },

    async printKotData(data) {
      const cfg = load();
      if (cfg.kitchen.mode === "none") return;
      if (modeOf("kitchen") === "browser") return browserPrintHtml(kotHtml(data, widthOf("kitchen")), "kitchen");
      return sendRaw("kitchen", buildKot(data, widthOf("kitchen")));
    },

    async openDrawer() {
      const cfg = load();
      if (!cfg.drawer.enabled) throw new Error("Cash drawer is turned off in Devices settings.");
      if (modeOf("receipt") === "browser") throw new Error("The cash drawer needs a USB, serial or network receipt printer.");
      const e = new Encoder(); e.drawer(cfg.drawer.pin);
      return sendRaw("receipt", e.build());
    },

    async testPrint(role) {
      const w = widthOf(role);
      const e = new Encoder(w);
      e.align("center").bold(true).size(2, 2).line("TEST PRINT").size(1, 1).bold(false)
        .line("BookPilot device check").line(new Date().toLocaleString()).rule()
        .align("left").pair("Paper width", w + " chars").pair("Role", role)
        .rule().align("center").line("If you can read this, printing works!").cut();
      if (modeOf(role) === "browser" && desktopPrinter(role)) {
        return browserPrintHtml(paperHtml('<div class="c"><h1>TEST PRINT</h1>BookPilot desktop<br>' + esc(new Date().toLocaleString()) + '<div class="l"></div>If you can read this, printing works!</div>', w), role);
      }
      if (modeOf(role) === "browser") {
        const html = "data:text/html," + encodeURIComponent('<pre style="font:14px monospace">TEST PRINT\nBookPilot device check\n' + new Date().toLocaleString() + "</pre><script>print()<\/script>");
        window.open(html, "_blank"); return;
      }
      return sendRaw(role, e.build());
    },

    /* ---------------- alarm ---------------- */
    _audio: null,
    unlockAudio() {
      try {
        if (!this._audio) this._audio = new (window.AudioContext || window.webkitAudioContext)();
        if (this._audio.state === "suspended") this._audio.resume();
      } catch (e) { /* no audio */ }
      return this._audio && this._audio.state === "running";
    },
    audioReady() { return !!(this._audio && this._audio.state === "running"); },
    alarm(kind = "new", force = false) {
      const cfg = load();
      if (!cfg.alarm.enabled && !force) return;
      this.unlockAudio();
      const ctx = this._audio; if (!ctx) return;
      const vol = Math.max(0, Math.min(1, Number(cfg.alarm.volume) || 0.8));
      const patterns = {
        chime: [[880, 0, .18], [1318.5, .18, .35]],
        bell: [[1046.5, 0, .6], [1568, 0, .6], [2093, 0, .4]],
        beep: [[1000, 0, .12], [1000, .2, .12], [1000, .4, .12]],
      };
      const readyPattern = [[659.3, 0, .15], [784, .15, .15], [1046.5, .3, .3]];
      const pattern = kind === "ready" ? readyPattern : (patterns[cfg.alarm.sound] || patterns.chime);
      const repeat = kind === "ready" ? 1 : Math.max(1, Math.min(5, Number(cfg.alarm.repeat) || 1));
      const t0 = ctx.currentTime + 0.02;
      for (let r = 0; r < repeat; r++) {
        pattern.forEach(([freq, at, dur]) => {
          const osc = ctx.createOscillator(), gain = ctx.createGain();
          osc.type = cfg.alarm.sound === "beep" ? "square" : "sine";
          osc.frequency.value = freq;
          const start = t0 + r * 0.9 + at;
          gain.gain.setValueAtTime(0.0001, start);
          gain.gain.exponentialRampToValueAtTime(0.35 * vol + 0.0001, start + 0.02);
          gain.gain.exponentialRampToValueAtTime(0.0001, start + dur);
          osc.connect(gain).connect(ctx.destination);
          osc.start(start); osc.stop(start + dur + 0.05);
        });
      }
      if (navigator.vibrate) navigator.vibrate(kind === "ready" ? [120, 60, 120] : [300, 120, 300]);
    },

    /* ---------------- barcode scanner (keyboard wedge) ---------------- */
    attachScanner(onScan, opts = {}) {
      const cfg = load();
      if (!cfg.scanner.enabled) return () => {};
      let buf = "", last = 0;
      const maxGap = opts.maxGap || 40, minLen = opts.minLength || 4;
      const handler = (ev) => {
        const now = performance.now();
        const t = ev.target;
        const typingField = t && (t.tagName === "TEXTAREA" || (t.tagName === "INPUT" && !t.hasAttribute("data-scan-target") && t.type !== "search"));
        if (typingField) return;
        if (now - last > maxGap) buf = "";
        last = now;
        if (ev.key === "Enter") {
          if (buf.length >= minLen) { ev.preventDefault(); const code = buf; buf = ""; onScan(code); }
          buf = ""; return;
        }
        if (ev.key.length === 1) buf += ev.key;
      };
      document.addEventListener("keydown", handler, true);
      return () => document.removeEventListener("keydown", handler, true);
    },

    /* ---------------- customer display ---------------- */
    _channel: null,
    display(message) {
      const cfg = load();
      if (!cfg.display.enabled) return;
      try {
        if (!this._channel) this._channel = new BroadcastChannel("bookpilot-customer-display");
        this._channel.postMessage(message);
      } catch (e) { /* unsupported */ }
    },
  };

  // Browsers only allow sound after the user has interacted with the page.
  const unlock = () => { Devices.unlockAudio(); document.removeEventListener("pointerdown", unlock, true); document.removeEventListener("keydown", unlock, true); };
  document.addEventListener("pointerdown", unlock, true);
  document.addEventListener("keydown", unlock, true);

  window.Devices = Devices;
})();
