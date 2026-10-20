/* Fills in the contact details from config.js and runs the page effects: preloader, scroll bar, reveal on scroll,
   counters, typing text, terminal, network background, 3D tilt, spotlight cards, timeline and the enquiry form.
   Everything calms down for visitors who ask their device for reduced motion. */
(function () {
  var S = window.SITE || {};
  var calm = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var wa = (S.whatsapp || "").replace(/\D/g, "");
  S.whatsapp_display = S.phone && S.phone.replace(/\D/g, "") === wa ? S.phone : (wa ? "+" + wa : "");
  var bp = (S.bookpilot_url || "").replace(/\/+$/, "");
  function $all(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }

  // ---- contact details ------------------------------------------------------
  $all("[data-site]").forEach(function (el) { el.textContent = S[el.dataset.site] || ""; });
  $all("[data-site-href]").forEach(function (el) {
    var kind = el.dataset.siteHref;
    if (kind === "tel" && S.phone) el.href = "tel:" + S.phone.replace(/[^\d+]/g, "");
    if (kind === "mailto" && S.email) el.href = "mailto:" + S.email;
    if (kind === "wa" && wa) el.href = "https://wa.me/" + wa + (el.dataset.waText ? "?text=" + encodeURIComponent(el.dataset.waText) : "");
  });
  $all("[data-needs]").forEach(function (el) {
    var key = el.dataset.needs === "whatsapp" ? wa : S[el.dataset.needs];
    el.classList.toggle("is-empty", !key);
  });
  if (bp) $all("[data-bp-link]").forEach(function (a) {
    a.href = bp + a.dataset.bpLink;
    a.target = "_blank";
    a.rel = "noopener";
  });
  $all(".js-year").forEach(function (el) { el.textContent = new Date().getFullYear(); });

  // ---- preloader --------------------------------------------------------------
  var pre = document.getElementById("preloader");
  function hidePre() { if (pre) pre.classList.add("done"); }
  window.addEventListener("load", function () { setTimeout(hidePre, 250); });
  setTimeout(hidePre, 1800);

  // ---- navbar, scroll bar, back to top -----------------------------------------
  var nav = document.getElementById("mainNav"), bar = document.getElementById("scrollBar"), top = document.querySelector(".to-top");
  function onScroll() {
    var y = window.scrollY, h = document.documentElement.scrollHeight - window.innerHeight;
    if (nav) nav.classList.toggle("scrolled", y > 30);
    if (bar) bar.style.width = (h > 0 ? (y / h) * 100 : 0) + "%";
    if (top) top.classList.toggle("show", y > 700);
  }
  onScroll();
  window.addEventListener("scroll", onScroll, { passive: true });
  if (top) top.addEventListener("click", function () { window.scrollTo({ top: 0, behavior: calm ? "auto" : "smooth" }); });
  var menu = document.getElementById("navLinks");
  if (menu) {
    menu.addEventListener("show.bs.collapse", function () { nav.classList.add("menu-open"); });
    menu.addEventListener("hidden.bs.collapse", function () { nav.classList.remove("menu-open"); });
  }

  // ---- reveal on scroll + counters + steps line ------------------------------------
  function count(el) {
    var end = parseFloat(el.dataset.count), suffix = el.dataset.suffix || "", t0 = null, dur = 1600;
    if (calm) { el.textContent = end + suffix; return; }
    function step(t) {
      if (!t0) t0 = t;
      var p = Math.min((t - t0) / dur, 1), e = 1 - Math.pow(1 - p, 3);
      el.textContent = Math.round(end * e) + suffix;
      if (p < 1) requestAnimationFrame(step);
    }
    requestAnimationFrame(step);
  }
  var watched = $all(".reveal, [data-count], .steps, .stat");
  if ("IntersectionObserver" in window) {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (!e.isIntersecting) return;
        e.target.classList.add("in");
        if (e.target.dataset.count) count(e.target);
        io.unobserve(e.target);
      });
    }, { threshold: 0.15, rootMargin: "0px 0px -40px 0px" });
    watched.forEach(function (el) { io.observe(el); });
  } else {
    watched.forEach(function (el) { el.classList.add("in"); if (el.dataset.count) el.textContent = el.dataset.count + (el.dataset.suffix || ""); });
  }

  // ---- typing rotator: data-rotate='["one","two"]' ------------------------------
  $all("[data-rotate]").forEach(function (el) {
    var words = JSON.parse(el.dataset.rotate), i = 0, j = 0, del = false;
    if (calm) { el.textContent = words[0]; return; }
    (function tick() {
      var w = words[i];
      j += del ? -1 : 1;
      el.textContent = w.slice(0, j);
      var wait = del ? 35 : 70;
      if (!del && j === w.length) { del = true; wait = 1700; }
      else if (del && j === 0) { del = false; i = (i + 1) % words.length; wait = 300; }
      setTimeout(tick, wait);
    })();
  });

  // ---- terminal: lines typed one after another, then again --------------------------
  $all("[data-terminal]").forEach(function (pre) {
    var lines = JSON.parse(pre.querySelector("script").textContent);
    function esc(s) { return s.replace(/&/g, "&amp;").replace(/</g, "&lt;"); }
    function paint(done, partial) {
      pre.innerHTML = done.map(function (l) { return '<span class="' + (l.c || "") + '">' + esc(l.t) + "</span>"; }).join("\n") +
        (partial !== undefined ? (done.length ? "\n" : "") + partial : "") + '<span class="caret"></span>';
    }
    if (calm) { paint(lines.filter(function (l) { return !l.pause; })); return; }
    function run() {
      var done = [], n = 0;
      (function nextLine() {
        if (n >= lines.length) { setTimeout(run, 3800); return; }
        var l = lines[n++];
        if (l.pause) { setTimeout(nextLine, l.pause); return; }
        if (!l.type) { done.push(l); paint(done); setTimeout(nextLine, l.wait || 260); return; }
        var k = 0;
        (function typeChar() {
          k++;
          paint(done, '<span class="' + (l.c || "") + '">' + esc(l.t.slice(0, k)) + "</span>");
          if (k < l.t.length) setTimeout(typeChar, 38 + Math.random() * 40);
          else { done.push(l); setTimeout(nextLine, 380); }
        })();
      })();
    }
    var started = false;
    var tio = new IntersectionObserver(function (es) { if (es[0].isIntersecting && !started) { started = true; run(); } });
    tio.observe(pre);
  });

  // ---- network background: points that link up and lean towards the mouse -------------
  $all("canvas.net-canvas").forEach(function (cv) {
    var ctx = cv.getContext("2d"), pts = [], W = 0, H = 0, dpr = Math.min(window.devicePixelRatio || 1, 2), mouse = { x: -999, y: -999 }, running = false, raf;
    function size() {
      var r = cv.getBoundingClientRect();
      W = r.width; H = r.height;
      cv.width = W * dpr; cv.height = H * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      var n = Math.round(Math.min(90, (W * H) / 14000));
      pts = [];
      for (var i = 0; i < n; i++) pts.push({ x: Math.random() * W, y: Math.random() * H, vx: (Math.random() - .5) * .35, vy: (Math.random() - .5) * .35, r: Math.random() * 1.6 + .8 });
    }
    function frame() {
      ctx.clearRect(0, 0, W, H);
      for (var i = 0; i < pts.length; i++) {
        var p = pts[i];
        if (!calm) { p.x += p.vx; p.y += p.vy; }
        if (p.x < 0 || p.x > W) p.vx *= -1;
        if (p.y < 0 || p.y > H) p.vy *= -1;
        var dxm = p.x - mouse.x, dym = p.y - mouse.y, dm = Math.sqrt(dxm * dxm + dym * dym);
        if (dm < 160) { p.x -= dxm * .006; p.y -= dym * .006; }
        for (var j = i + 1; j < pts.length; j++) {
          var q = pts[j], dx = p.x - q.x, dy = p.y - q.y, d = dx * dx + dy * dy;
          if (d < 16900) {
            ctx.strokeStyle = "rgba(34,211,230," + (0.22 * (1 - d / 16900)).toFixed(3) + ")";
            ctx.lineWidth = 1;
            ctx.beginPath(); ctx.moveTo(p.x, p.y); ctx.lineTo(q.x, q.y); ctx.stroke();
          }
        }
        if (dm < 160) {
          ctx.strokeStyle = "rgba(94,230,242," + (0.5 * (1 - dm / 160)).toFixed(3) + ")";
          ctx.beginPath(); ctx.moveTo(p.x, p.y); ctx.lineTo(mouse.x, mouse.y); ctx.stroke();
        }
        ctx.fillStyle = "rgba(140,240,248,.85)";
        ctx.beginPath(); ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2); ctx.fill();
      }
      if (running && !calm) raf = requestAnimationFrame(frame);
    }
    size(); frame();
    var host = cv.parentElement;
    host.addEventListener("mousemove", function (e) { var r = cv.getBoundingClientRect(); mouse.x = e.clientX - r.left; mouse.y = e.clientY - r.top; });
    host.addEventListener("mouseleave", function () { mouse.x = mouse.y = -999; });
    var rt; window.addEventListener("resize", function () { clearTimeout(rt); rt = setTimeout(function () { size(); frame(); }, 200); });
    new IntersectionObserver(function (es) {
      running = es[0].isIntersecting;
      cancelAnimationFrame(raf);
      if (running) frame();
    }).observe(cv);
  });

  // ---- 3D tilt and spotlight -------------------------------------------------------
  if (!calm && window.matchMedia("(hover: hover)").matches) {
    $all("[data-tilt]").forEach(function (el) {
      var max = parseFloat(el.dataset.tilt) || 8;
      el.addEventListener("mousemove", function (e) {
        var r = el.getBoundingClientRect(), x = (e.clientX - r.left) / r.width - .5, y = (e.clientY - r.top) / r.height - .5;
        el.style.transform = "perspective(900px) rotateX(" + (-y * max) + "deg) rotateY(" + (x * max) + "deg)";
      });
      el.addEventListener("mouseleave", function () { el.style.transform = ""; });
    });
  }
  $all(".glass").forEach(function (el) {
    el.addEventListener("mousemove", function (e) {
      var r = el.getBoundingClientRect();
      el.style.setProperty("--mx", (e.clientX - r.left) + "px");
      el.style.setProperty("--my", (e.clientY - r.top) + "px");
    });
  });

  // ---- timeline line that fills as you scroll ---------------------------------------
  $all(".timeline").forEach(function (tl) {
    var fill = tl.querySelector(".fill");
    function upd() {
      var r = tl.getBoundingClientRect(), vh = window.innerHeight;
      var p = Math.max(0, Math.min(1, (vh * .7 - r.top) / r.height));
      fill.style.height = (p * (r.height - 12)) + "px";
    }
    upd();
    window.addEventListener("scroll", upd, { passive: true });
  });

  // ---- enquiry form: opens WhatsApp (or email) with the message already written ---------
  var form = document.getElementById("enquiry");
  if (form) {
    var note = document.getElementById("formNote");
    var want = new URLSearchParams(location.search).get("need");
    if (want) $all("option", form.elements.need).forEach(function (o) { if (o.value === want) o.selected = true; });
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      if (!form.checkValidity()) { form.classList.add("was-validated"); return; }
      var f = form.elements;
      var text = "Hello MMM Technologie,\n\nName: " + f.name.value + "\nPhone: " + f.phone.value +
        (f.company.value ? "\nBusiness: " + f.company.value : "") + "\nInterested in: " + f.need.value +
        (f.message.value ? "\n\n" + f.message.value : "");
      if (wa) window.open("https://wa.me/" + wa + "?text=" + encodeURIComponent(text), "_blank", "noopener");
      else if (S.email) window.location.href = "mailto:" + S.email + "?subject=" + encodeURIComponent("Enquiry: " + f.need.value) + "&body=" + encodeURIComponent(text);
      else { note.textContent = "Contact details are coming soon. Please check back shortly."; return; }
      note.textContent = "Thank you! Your message is ready to send on WhatsApp.";
    });
  }
})();
