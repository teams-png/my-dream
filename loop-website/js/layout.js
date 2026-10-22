/* The menu, footer and floating buttons shared by every page. Each page has <div id="siteNav"></div> right after <body>
   and <div id="siteFooter"></div> at the end; this script fills them, so a menu change is made here once. */
(function () {
  var page = document.body.dataset.page || "";
  var links = [
    ["index.html", "home", "Home"],
    ["bookpilot.html", "bookpilot", "BookPilot"],
    ["services.html", "services", "Services"],
    ["ai.html", "ai", "AI Solutions"],
    ["work.html", "work", "Our Work"],
    ["about.html", "about", "About"],
    ["contact.html", "contact", "Contact"]
  ];
  function nav() {
    return links.map(function (l) {
      var on = l[1] === page;
      return '<li class="nav-item"><a class="nav-link' + (on ? " active" : "") + '"' + (on ? ' aria-current="page"' : "") +
        ' href="' + l[0] + '">' + l[2] + (l[1] === "bookpilot" ? ' <span class="nav-star">★</span>' : "") + "</a></li>";
    }).join("");
  }

  var head = document.getElementById("siteNav");
  if (head) head.outerHTML =
    '<div id="preloader" aria-hidden="true"><img src="assets/loop-mark-white.png" alt=""><div class="bar"></div></div>' +
    '<div id="scrollBar" aria-hidden="true"></div>' +
    '<nav id="mainNav" class="navbar navbar-expand-xl fixed-top" aria-label="Main">' +
    '<div class="container">' +
    '<a class="navbar-brand d-flex align-items-center gap-2" href="index.html" aria-label="Loop Technologies home">' +
    '<img src="assets/loop-mark-white.png" alt="" class="brand-mark">' +
    '<span class="brand-text">Loop <b>Technologies</b></span></a>' +
    '<button class="navbar-toggler border-0" type="button" data-bs-toggle="collapse" data-bs-target="#navLinks" aria-controls="navLinks" aria-expanded="false" aria-label="Open menu">' +
    '<i class="bi bi-list fs-2"></i></button>' +
    '<div class="collapse navbar-collapse" id="navLinks"><ul class="navbar-nav ms-auto align-items-xl-center gap-xl-1">' + nav() +
    '<li class="nav-item ms-xl-3 mt-2 mt-xl-0"><a class="btn btn-signal rounded-pill px-4" href="contact.html?need=BookPilot%20free%20demo"><i class="bi bi-calendar-check me-1"></i> Free demo</a></li>' +
    "</ul></div></div></nav>";

  var foot = document.getElementById("siteFooter");
  if (foot) foot.outerHTML =
    '<footer class="footer"><div class="container"><div class="row g-4">' +
    '<div class="col-lg-4"><img src="assets/loop-logo-white.png" alt="Loop Technologies" width="96" height="106" class="mb-3 foot-logo">' +
    '<p class="mb-1 fw-semibold text-white">Loop Technologies</p>' +
    '<p class="small">Makers of BookPilot business software. Websites, custom software, apps, design and AI for growing businesses.</p>' +
    '<div class="social mt-3"><a data-needs="whatsapp" data-site-href="wa" href="#" target="_blank" rel="noopener" aria-label="WhatsApp"><i class="bi bi-whatsapp"></i></a>' +
    '<a data-needs="phone" data-site-href="tel" href="#" aria-label="Call"><i class="bi bi-telephone"></i></a>' +
    '<a data-needs="email" data-site-href="mailto" href="#" aria-label="Email"><i class="bi bi-envelope"></i></a>' +
    '<a data-needs="instagram" data-site-href="instagram" href="#" target="_blank" rel="noopener" aria-label="Instagram"><i class="bi bi-instagram"></i></a>' +
    '<a data-needs="facebook" data-site-href="facebook" href="#" target="_blank" rel="noopener" aria-label="Facebook"><i class="bi bi-facebook"></i></a>' +
    '<a data-needs="linkedin" data-site-href="linkedin" href="#" target="_blank" rel="noopener" aria-label="LinkedIn"><i class="bi bi-linkedin"></i></a></div></div>' +
    '<div class="col-6 col-lg-2"><h4>Company</h4><ul class="list-unstyled small">' +
    '<li><a href="about.html">About us</a></li><li><a href="work.html">Our work</a></li><li><a href="contact.html">Contact</a></li><li><a href="contact.html?need=BookPilot%20free%20demo">Book a demo</a></li></ul></div>' +
    '<div class="col-6 col-lg-2"><h4>BookPilot</h4><ul class="list-unstyled small">' +
    '<li><a href="bookpilot.html">Features</a></li><li><a href="bookpilot.html#industries">Industries</a></li>' +
    '<li><a href="bookpilot.html#pricing">Pricing</a></li><li><a data-bp-link="/login/" href="bookpilot.html">Sign in</a></li></ul></div>' +
    '<div class="col-6 col-lg-2"><h4>Services</h4><ul class="list-unstyled small">' +
    '<li><a href="services.html#web">Web development</a></li><li><a href="services.html#software">Software development</a></li>' +
    '<li><a href="services.html#apps">Mobile apps</a></li><li><a href="services.html#design">UI/UX &amp; design</a></li>' +
    '<li><a href="ai.html">AI solutions</a></li><li><a href="services.html#marketing">Digital marketing</a></li></ul></div>' +
    '<div class="col-6 col-lg-2"><h4>Contact</h4><ul class="list-unstyled small">' +
    '<li data-needs="phone"><a data-site="phone" data-site-href="tel" href="#" dir="ltr"></a></li>' +
    '<li data-needs="email"><a data-site="email" data-site-href="mailto" href="#"></a></li>' +
    '<li data-needs="address"><span data-site="address"></span></li><li data-needs="hours"><span data-site="hours"></span></li></ul></div>' +
    '</div><hr><div class="d-flex flex-wrap justify-content-between gap-2 small">' +
    '<span>© <span class="js-year"></span> Loop Technologies. All rights reserved.</span>' +
    '<span data-needs="domain"><i class="bi bi-globe2 me-1"></i><span data-site="domain"></span></span></div></div></footer>' +
    '<a class="wa-float" data-needs="whatsapp" data-site-href="wa" href="#" target="_blank" rel="noopener" aria-label="Chat on WhatsApp"><i class="bi bi-whatsapp"></i></a>' +
    '<button class="to-top" type="button" aria-label="Back to top"><i class="bi bi-arrow-up"></i></button>';
})();
