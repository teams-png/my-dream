/* Kanban board: drag a card to another column to change its status.
   Boards with data-kb-url-pattern post {status} to that url (the id goes where the pattern has /0/);
   a card holding its own <form> with a select (e.g. the candidate pipeline) gets that select set and sent. */
(function () {
  var tokenEl = document.querySelector("[name=csrfmiddlewaretoken]"), token = tokenEl ? tokenEl.value : "";
  document.querySelectorAll(".kb-board, .rc-board").forEach(function (board) {
    var dragging = null;
    function counts() {
      board.querySelectorAll(".kb-col, .rc-col").forEach(function (col) {
        var n = col.querySelector(".kb-n"); if (n) n.textContent = col.querySelectorAll(".kb-card, .rc-card").length;
      });
    }
    board.addEventListener("dragstart", function (e) {
      var card = e.target.closest(".kb-card, .rc-card[draggable=true]");
      if (!card) return;
      dragging = card; card.classList.add("kb-drag");
      e.dataTransfer.effectAllowed = "move";
      e.dataTransfer.setData("text/plain", card.dataset.id || "");
    });
    board.addEventListener("dragend", function () {
      if (dragging) dragging.classList.remove("kb-drag");
      dragging = null;
      board.querySelectorAll(".kb-over").forEach(function (c) { c.classList.remove("kb-over"); });
    });
    board.addEventListener("dragover", function (e) {
      var col = e.target.closest(".kb-col, .rc-col");
      if (!col || !dragging) return;
      e.preventDefault();
      board.querySelectorAll(".kb-over").forEach(function (c) { if (c !== col) c.classList.remove("kb-over"); });
      col.classList.add("kb-over");
    });
    board.addEventListener("drop", function (e) {
      var col = e.target.closest(".kb-col, .rc-col");
      if (!col || !dragging) return;
      e.preventDefault();
      col.classList.remove("kb-over");
      var card = dragging, status = col.dataset.status, from = card.parentNode;
      if (!status || from === col) return;
      var form = card.querySelector("form");
      if (form) {
        var sel = form.querySelector("select[name=stage], select[name=status]");
        if (sel) { sel.value = status; form.submit(); }
        return;
      }
      var url = board.dataset.kbUrlPattern.replace("/0/", "/" + card.dataset.id + "/");
      col.appendChild(card); counts(); card.classList.add("saving");
      var body = new FormData(); body.append("status", status);
      fetch(url, { method: "POST", body: body, credentials: "same-origin", headers: { "X-CSRFToken": token, "X-Requested-With": "fetch" } })
        .then(function (r) { if (!r.ok) throw r; card.classList.remove("saving"); })
        .catch(function () { from.appendChild(card); counts(); card.classList.remove("saving"); card.classList.add("bad"); });
    });
  });
})();
