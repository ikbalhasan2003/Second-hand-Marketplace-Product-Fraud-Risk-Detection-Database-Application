(() => {
  const thread = document.querySelector('[data-conversation]');
  if (!thread) return;
  const list = document.querySelector('#messages'), status = document.querySelector('#poll-status');
  const base = thread.dataset.conversation, visible = new Set();
  let after = Math.max(0, ...[...list.children].map(item => Number(item.dataset.messageId))), delay = 5000, reading = false;
  const seen = new Set([...list.children].map(item => Number(item.dataset.messageId)));
  if (list.children.length) list.scrollTop = list.scrollHeight;
  const observer = new IntersectionObserver(entries => entries.forEach(entry => {
    if (entry.isIntersecting) visible.add(entry.target.dataset.messageId);
    else visible.delete(entry.target.dataset.messageId);
  }), {root: list, threshold: 0.5});
  list.querySelectorAll('[data-message-id]').forEach(item => observer.observe(item));
  async function markVisible() {
    if (reading || document.hidden || !visible.size) return;
    const token = document.querySelector('[name=csrfmiddlewaretoken]')?.value;
    if (!token) return;
    reading = true;
    try {
      await fetch(base + 'read/', {method: 'POST', signal: AbortSignal.timeout(15000), headers: {'X-CSRFToken': token, 'Content-Type': 'application/x-www-form-urlencoded'}, body: 'message_ids=' + [...visible].slice(0,50).join(',')});
    } finally {reading = false;}
  }
  async function poll() {
    if (document.hidden) {setTimeout(poll,5000);return;}
    try {
      const response = await fetch(base + 'messages/?after_id=' + after, {headers: {Accept: 'application/json'}, signal: AbortSignal.timeout(15000)});
      if (!response.ok || response.redirected) throw Error('request');
      const data = await response.json(), nearBottom = list.scrollHeight - list.scrollTop - list.clientHeight < 80;
      data.messages.forEach(message => {
        if (seen.has(message.message_id)) return;
        seen.add(message.message_id);
        const item = document.createElement('li'), text = document.createElement('p'), time = document.createElement('small');
        item.dataset.messageId = message.message_id;
        text.textContent = message.message_text;
        time.textContent = new Date(message.sent_at).toLocaleString(undefined, {timeZoneName:'short'}) + ' · Sender #' + message.sender_id + (message.read_at ? ' · Read' : '');
        item.append(text,time); list.append(item); observer.observe(item); after = message.message_id;
      });
      data.receipts.forEach(receipt => {
        const time = list.querySelector('[data-message-id="' + receipt.message_id + '"] small');
        if (time && !time.dataset.read) {time.textContent = time.textContent.replace(/ · Read$/, '') + ' · Read'; time.dataset.read = 'true';}
      });
      if (nearBottom) list.scrollTop = list.scrollHeight;
      status.textContent = (list.children.length ? 'Messages up to date' : 'No messages yet') + ' - Last refreshed ' + new Date().toLocaleString(undefined, {timeZoneName:'short'});
      delay = data.has_more ? 100 : 5000;
    } catch {
      status.textContent = 'Unable to refresh. Data may be out of date. Your draft is preserved; retrying.';
      delay = Math.min(delay * 2, 60000);
    }
    setTimeout(poll,delay);
  }
  setInterval(() => markVisible().catch(() => {}), 1500);
  const older = document.querySelector('[data-load-older]');
  older?.addEventListener('click', async () => {
    older.disabled = true;
    try {
      const before = Math.min(...[...list.children].map(item => Number(item.dataset.messageId)));
      const response = await fetch(base + 'messages/?before_id=' + before, {signal: AbortSignal.timeout(15000)});
      if (!response.ok || response.redirected) throw Error('history');
      const data = await response.json(), height = list.scrollHeight, top = list.scrollTop, fragment = document.createDocumentFragment();
      data.messages.forEach(message => {
        if (seen.has(message.message_id)) return;
        seen.add(message.message_id);
        const item = document.createElement('li'), text = document.createElement('p'), time = document.createElement('small');
        item.dataset.messageId = message.message_id; text.textContent = message.message_text;
        time.textContent = new Date(message.sent_at).toLocaleString(undefined, {timeZoneName:'short'}) + ' - Sender #' + message.sender_id + (message.read_at ? ' - Read' : '');
        item.append(text, time); fragment.append(item); observer.observe(item);
      });
      list.prepend(fragment); list.scrollTop = top + list.scrollHeight - height;
      if (!data.has_more) {older.hidden = true; list.focus({preventScroll:true});}
    } catch {status.textContent = 'Earlier messages could not load. Try again.';}
    finally {older.disabled = false;}
  });
  poll();
})();
