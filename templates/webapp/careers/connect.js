/* BookPilot careers connector.
   Add to the career page:  <script src="…/careers/<name>/connect.js" defer></script>
   Optional attributes on that <script> tag:
     data-form=".my-form"            which form(s) to watch (default: forms with a phone, email or file field)
     data-map='{"mobile_no":"phone"}' extra field mapping (your field name -> name, phone, email, nationality,
                                      passport_no, trade, experience_years, current_location, message, cv)
   The page's own form keeps working exactly as before; a copy of each application is sent to BookPilot. */
(function () {
  "use strict";
  var ENDPOINT = {{ endpoint|safe }};
  var me = document.currentScript || document.querySelector('script[src*="/connect.js"]');
  var selector = me && me.getAttribute("data-form");
  var extraMap = {};
  try { extraMap = JSON.parse((me && me.getAttribute("data-map")) || "{}"); } catch (e) { extraMap = {}; }

  var RULES = [
    ["passport_no", /passport/],
    ["email", /e-?mail/],
    ["phone", /phone|mobile|whats ?app|contact ?(no|number)|\btel\b|cell/],
    ["nationality", /nationality|citizenship/],
    ["experience_years", /experience|years? of|exp\b/],
    ["trade", /position|vacanc|job|post\b|role|designation|apply(ing)? for|trade|skill|profession|category/],
    ["current_location", /location|city|current country|residing|address|place/],
    ["message", /message|comment|cover|note|about|remarks|details/],
    ["first_name", /first ?name|given ?name|fname/],
    ["last_name", /last ?name|surname|family ?name|lname/],
    ["name", /name/]
  ];

  function labelText(el) {
    var t = [el.name, el.id, el.placeholder, el.getAttribute("aria-label"), el.title];
    if (el.id) {
      var l = document.querySelector('label[for="' + el.id.replace(/"/g, '\\"') + '"]');
      if (l) t.push(l.textContent);
    }
    var wrap = el.closest("label");
    if (wrap) t.push(wrap.textContent);
    return t.filter(Boolean).join(" ").toLowerCase();
  }

  function keyFor(el, text) {
    if (extraMap[el.name]) return extraMap[el.name];
    if (el.type === "file") return "cv";
    if (el.type === "email") return "email";
    if (el.type === "tel") return "phone";
    for (var i = 0; i < RULES.length; i++) {
      if (RULES[i][1].test(text)) {
        if (RULES[i][0] === "name" && /company|user ?name|file|job|position/.test(text)) continue;
        return RULES[i][0];
      }
    }
    return null;
  }

  function collect(form) {
    var out = new FormData(), seen = {}, extras = [], first = "", last = "", hasCv = false;
    var fields = form.querySelectorAll("input, select, textarea");
    for (var i = 0; i < fields.length; i++) {
      var el = fields[i];
      if (!el.name || el.disabled || /^(submit|button|reset|hidden|password)$/.test(el.type)) continue;
      if ((el.type === "checkbox" || el.type === "radio") && !el.checked) continue;
      var text = labelText(el), key = keyFor(el, text);
      if (key === "cv") {
        if (!hasCv && el.files && el.files[0]) { out.append("cv", el.files[0]); hasCv = true; }
        continue;
      }
      var value = (el.value || "").trim();
      if (!value) continue;
      if (key === "first_name") { first = value; continue; }
      if (key === "last_name") { last = value; continue; }
      if (key && !seen[key]) { seen[key] = value; continue; }
      extras.push((el.labels && el.labels[0] ? el.labels[0].textContent.trim() : el.name) + ": " + value);
    }
    if (!seen.name && (first || last)) seen.name = (first + " " + last).trim();
    if (extras.length) seen.message = ((seen.message ? seen.message + "\n" : "") + extras.join("\n")).slice(0, 2000);
    for (var k in seen) out.append(k, seen[k]);
    return seen.name && seen.phone ? out : null;
  }

  function send(data) {
    return fetch(ENDPOINT, { method: "POST", body: data, mode: "cors", credentials: "omit",
                             headers: { "Accept": "application/json" } }).catch(function () {});
  }

  function watched(form) {
    if (selector) return form.matches(selector);
    return !!form.querySelector('input[type=file], input[type=tel], input[type=email], input[name*=phone i], input[name*=mobile i]');
  }

  var resubmitting = false;
  window.addEventListener("submit", function (e) {
    var form = e.target;
    if (resubmitting || !(form instanceof HTMLFormElement) || !watched(form)) return;
    var data = collect(form);
    if (!data) return;
    if (e.defaultPrevented) { send(data); return; }  // the page sends its form with JavaScript and stays open
    e.preventDefault();                               // a normal form post: send our copy first, then continue
    var done = false;
    var go = function () { if (done) return; done = true; resubmitting = true; HTMLFormElement.prototype.submit.call(form); };
    send(data).then(go);
    setTimeout(go, 8000);
  }, false);
})();
