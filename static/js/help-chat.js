// Help chat: sends messages without reloading and checks for new ones every 15 seconds.
// Markup: <div data-chat data-poll="messages.json url" data-post="form url"> with .chat-log (data-last="id")
// and a <form data-chat-form> holding a textarea[name=body] and the csrf token.
(function () {
  const box = document.querySelector('[data-chat]');
  if (!box) return;
  const log = box.querySelector('.chat-log');
  const form = box.querySelector('[data-chat-form]');
  const input = form.querySelector('textarea[name=body]');
  const err = box.querySelector('.chat-error');
  let last = parseInt(log.dataset.last || '0', 10);
  let busy = false;

  function bottom() { log.scrollTop = log.scrollHeight; }

  function add(m) {
    if (m.id <= last) return;
    last = m.id;
    const empty = log.querySelector('.chat-empty');
    if (empty) empty.remove();
    const row = document.createElement('div');
    row.className = 'chat-msg ' + (m.mine ? 'mine' : 'theirs');
    const bubble = document.createElement('div');
    bubble.className = 'chat-bubble';
    bubble.textContent = m.body;
    const meta = document.createElement('div');
    meta.className = 'chat-meta';
    meta.textContent = (m.who ? m.who + ' · ' : '') + m.at;
    row.append(bubble, meta);
    log.appendChild(row);
  }

  async function poll() {
    if (busy || document.hidden) return;
    try {
      const r = await fetch(box.dataset.poll + '?after=' + last, { headers: { 'x-requested-with': 'fetch' } });
      if (!r.ok) return;
      const data = await r.json();
      if (data.messages.length) { data.messages.forEach(add); bottom(); }
    } catch (e) { /* offline: try again next round */ }
  }

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const text = input.value.trim();
    if (!text || busy) return;
    busy = true;
    form.querySelector('button[type=submit]').disabled = true;
    if (err) err.textContent = '';
    try {
      const body = new FormData(form);
      body.set('action', 'reply');
      const r = await fetch(box.dataset.post + '?after=' + last, {
        method: 'POST', body, headers: { 'x-requested-with': 'fetch' },
      });
      const data = await r.json();
      if (!r.ok) { if (err) err.textContent = data.error || 'Could not send.'; return; }
      input.value = '';
      data.messages.forEach(add);
      bottom();
    } catch (e2) {
      form.submit();  // no JSON (e.g. offline page): fall back to a normal post
    } finally {
      busy = false;
      form.querySelector('button[type=submit]').disabled = false;
      input.focus();
    }
  });

  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) form.requestSubmit();
  });
  bottom();
  setInterval(poll, 15000);
  document.addEventListener('visibilitychange', poll);
})();
