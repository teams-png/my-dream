/* Overview charts: sales (12 months or 30 days), income vs expense, top expenses and payment methods.
   Colours follow light/dark mode; numbers come from the ovcData JSON next to the canvases. */
(function () {
  var el = document.getElementById("ovcData");
  if (!el || !window.Chart) return;
  var d = JSON.parse(el.textContent), L = document.getElementById("ovcLabels").dataset;
  var dark = document.documentElement.getAttribute("data-theme") === "dark";
  var ink = dark ? "#b3bccd" : "#4b5565", grid = dark ? "rgba(255,255,255,.08)" : "rgba(16,24,40,.07)";
  var BLUE = "#2f7bff", ORANGE = "#f59f00", PALETTE = ["#2f7bff", "#22b8cf", "#f59f00", "#7950f2", "#40c057", "#fa5252"];
  Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
  Chart.defaults.color = ink;
  var money = function (v) { return L.currency + " " + Number(v).toLocaleString(undefined, { maximumFractionDigits: 2 }); };
  var short = function (v) { return v >= 1e6 ? (v / 1e6).toFixed(1) + "M" : v >= 1e3 ? (v / 1e3).toFixed(v >= 1e4 ? 0 : 1) + "K" : v; };
  var axes = {
    x: { grid: { display: false }, ticks: { maxRotation: 0, autoSkipPadding: 12 } },
    y: { beginAtZero: true, grid: { color: grid }, border: { display: false }, ticks: { callback: short } }
  };
  var tip = { callbacks: { label: function (c) { return " " + c.dataset.label + ": " + money(c.parsed.y !== undefined ? c.parsed.y : c.parsed); } } };

  var salesCtx = document.getElementById("ovcSales");
  if (salesCtx) {
    var sales = new Chart(salesCtx, {
      type: "bar",
      data: { labels: d.months, datasets: [{ label: L.sales, data: d.sales12, backgroundColor: BLUE, borderRadius: 6, maxBarThickness: 34 }] },
      options: { maintainAspectRatio: false, plugins: { legend: { display: false }, tooltip: tip }, scales: axes }
    });
    document.querySelectorAll(".ovc-tabs button").forEach(function (b) {
      b.addEventListener("click", function () {
        document.querySelectorAll(".ovc-tabs button").forEach(function (x) { x.classList.toggle("on", x === b); });
        var days = b.dataset.range === "30";
        document.querySelectorAll("[data-range-sub]").forEach(function (s) { s.hidden = s.dataset.rangeSub !== b.dataset.range; });
        sales.config.type = days ? "line" : "bar";
        sales.data.labels = days ? d.days : d.months;
        sales.data.datasets[0] = days
          ? { label: L.sales, data: d.daily, borderColor: BLUE, backgroundColor: "rgba(47,123,255,.12)", fill: true, tension: .35, pointRadius: 0, pointHoverRadius: 5 }
          : { label: L.sales, data: d.sales12, backgroundColor: BLUE, borderRadius: 6, maxBarThickness: 34 };
        sales.update();
      });
    });
  }
  var inc = document.getElementById("ovcIncome");
  if (inc) new Chart(inc, {
    type: "bar",
    data: { labels: d.months, datasets: [
      { label: L.income, data: d.sales12, backgroundColor: BLUE, borderRadius: 5, maxBarThickness: 18 },
      { label: L.expense, data: d.spend12, backgroundColor: ORANGE, borderRadius: 5, maxBarThickness: 18 }] },
    options: { maintainAspectRatio: false, plugins: { legend: { display: false }, tooltip: tip }, scales: axes }
  });
  function donut(id, labels, values) {
    var c = document.getElementById(id);
    if (!c || !values.length) return;
    new Chart(c, {
      type: "doughnut",
      data: { labels: labels, datasets: [{ data: values, backgroundColor: PALETTE, borderWidth: 0, hoverOffset: 6 }] },
      options: { maintainAspectRatio: false, cutout: "64%",
        plugins: { legend: { position: "bottom", labels: { boxWidth: 10, boxHeight: 10, usePointStyle: true, padding: 14 } },
          tooltip: { callbacks: { label: function (x) { return " " + x.label + ": " + money(x.parsed); } } } } }
    });
  }
  donut("ovcSpend", d.spendLabels, d.spendValues);
  donut("ovcPay", d.payLabels, d.payValues);
})();
