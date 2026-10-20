/* Fills in the contact details from config.js, links BookPilot buttons, and runs the small page effects. */
(function () {
  var S = window.SITE || {};
  var wa = (S.whatsapp || "").replace(/\D/g, "");
  S.whatsapp_display = wa ? "+" + wa : "";
  var bp = (S.bookpilot_url || "").replace(/\/+$/, "");

  // contact details: text, links, and hide anything still empty
  document.querySelectorAll("[data-site]").forEach(function (el) { el.textContent = S[el.dataset.site] || ""; });
  document.querySelectorAll("[data-site-href]").forEach(function (el) {
    var kind = el.dataset.siteHref;
    if (kind === "tel" && S.phone) el.href = "tel:" + S.phone.replace(/[^\d+]/g, "");
    if (kind === "mailto" && S.email) el.href = "mailto:" + S.email;
    if (kind === "wa" && wa) el.href = "https://wa.me/" + wa;
  });
  document.querySelectorAll("[data-needs]").forEach(function (el) {
    var key = el.dataset.needs === "whatsapp" ? wa : S[el.dataset.needs];
    el.classList.toggle("is-empty", !key);
  });

  // BookPilot buttons open the live app when its address is set
  if (bp) document.querySelectorAll("[data-bp-link]").forEach(function (a) {
    a.href = bp + a.dataset.bpLink;
    a.target = "_blank";
    a.rel = "noopener";
  });

  document.getElementById("year").textContent = new Date().getFullYear();

  // navbar turns white after the hero; mobile menu closes after a tap
  var nav = document.getElementById("mainNav");
  function onScroll() { nav.classList.toggle("scrolled", window.scrollY > 40); }
  onScroll();
  window.addEventListener("scroll", onScroll, { passive: true });
  var menu = document.getElementById("navLinks");
  menu.querySelectorAll("a").forEach(function (a) {
    a.addEventListener("click", function () {
      if (menu.classList.contains("show")) bootstrap.Collapse.getOrCreateInstance(menu).hide();
    });
  });
  // a white bar behind the open mobile menu reads better than the dark hero
  menu.addEventListener("show.bs.collapse", function () { nav.classList.add("scrolled"); });
  menu.addEventListener("hidden.bs.collapse", onScroll);

  // fade sections in as they scroll into view
  var items = document.querySelectorAll(".reveal");
  if ("IntersectionObserver" in window) {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) { if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); } });
    }, { threshold: 0.12 });
    items.forEach(function (el) { io.observe(el); });
  } else {
    items.forEach(function (el) { el.classList.add("in"); });
  }

  // enquiry form: opens WhatsApp (or email) with the message already written
  var form = document.getElementById("enquiry"), note = document.getElementById("formNote");
  form.addEventListener("submit", function (e) {
    e.preventDefault();
    if (!form.checkValidity()) { form.classList.add("was-validated"); return; }
    var f = form.elements;
    var text = "Hello MMM Technologie,\n\nName: " + f.name.value + "\nPhone: " + f.phone.value +
      (f.company.value ? "\nBusiness: " + f.company.value : "") + "\nInterested in: " + f.need.value +
      (f.message.value ? "\n\n" + f.message.value : "");
    if (wa) {
      window.open("https://wa.me/" + wa + "?text=" + encodeURIComponent(text), "_blank", "noopener");
    } else if (S.email) {
      window.location.href = "mailto:" + S.email + "?subject=" + encodeURIComponent("Enquiry: " + f.need.value) +
        "&body=" + encodeURIComponent(text);
    } else {
      note.textContent = "Contact details are coming soon. Please check back shortly.";
      return;
    }
    note.textContent = "Thank you! Your message is ready to send.";
  });
})();
