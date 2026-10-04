/* Adds "e.g. …" examples to text and number boxes that have none (hand-written forms and rows added later).
   Data comes from the bp-form-samples JSON the page renders for the business type. */
(function () {
  var node = document.getElementById("bp-form-samples");
  if (!node) return;
  var data;
  try { data = JSON.parse(node.textContent); } catch (e) { return; }
  var TYPES = { text: 1, email: 1, tel: 1, url: 1, search: 0, number: 1 };

  function key(name) {
    return (name || "").replace(/^form-\d+-/, "").replace(/^[a-z]{1,3}-(?=[a-z])/, "").replace(/(_|-)\d+$/, "").replace(/\[\]$/, "");
  }

  function hint(el) {
    if (el.placeholder || el.readOnly || el.disabled || el.value) return;
    var type = (el.getAttribute("type") || "text").toLowerCase();
    if (el.tagName === "INPUT" && !TYPES[type]) return;
    var k = key(el.name);
    if (!k) return;
    if (type === "number") {
      if (data.numbers[k]) el.placeholder = data.numbers[k];
      return;
    }
    var sample = data.fields[k];
    if (!sample) return;
    el.placeholder = sample.indexOf("\n") >= 0 ? sample : data.prefix.replace("%(sample)s", sample);
  }

  function run(root) {
    var els = (root || document).querySelectorAll(".main input, .main textarea");
    for (var i = 0; i < els.length; i++) hint(els[i]);
  }

  run();
  var main = document.querySelector(".main");
  if (main && window.MutationObserver) {
    var pending = false;
    new MutationObserver(function () {
      if (pending) return;
      pending = true;
      setTimeout(function () { pending = false; run(main); }, 60);
    }).observe(main, { childList: true, subtree: true });
  }
})();
