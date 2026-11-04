(() => {
  const thread = document.querySelector('[data-conversation]');
  if (!thread) return;
  const list = document.querySelector('#messages'), status = document.querySelector('#poll-status');
  const base = thread.dataset.conversation, visible = new Set();
  let after = 0, delay = 5000, reading = false;
  const observer = new IntersectionObserver(entries => entries.forEach(entry => {
    if (entry.isIntersecting) visible.add(entry.target.dataset.messageId);
    else visible.delete(entry.target.dataset.messageId);
  }), {root: list, threshold: 0.5});
  async function markVisible() {
    if (reading || document.hidden || !visible.size) return;
    const token = document.querySelector('[name=csrfmiddlewaretoken]')?.value;
    if (!token) return;
    reading = true;
    try {
      await fetch(base + 'read/', {method: 'POST', headers: {'X-CSRFToken': token, 'Content-Type': 'application/x-www-form-urlencoded'}, body: 'message_ids=' + [...visible].slice(0,50).join(',')});
    } finally {reading = false;}
  }
  async function poll() {
    if (document.hidden) {setTimeout(poll,5000);return;}
    try {
      const response = await fetch(base + 'messages/?after_id=' + after, {headers: {Accept: 'application/json'}});
      if (!response.ok) throw Error('request');
      const data = await response.json(), nearBottom = list.scrollHeight - list.scrollTop - list.clientHeight < 80;
      data.messages.forEach(message => {
        if (message.message_id <= after) return;
        const item = document.createElement('li'), text = document.createElement('p'), time = document.createElement('small');
        item.dataset.messageId = message.message_id;
        text.textContent = message.message_text;
        time.textContent = new Date(message.sent_at).toLocaleString() + ' · Sender #' + message.sender_id + (message.read_at ? ' · Read' : '');
        item.append(text,time); list.append(item); observer.observe(item); after = message.message_id;
      });
      data.receipts.forEach(receipt => {
        const time = list.querySelector('[data-message-id="' + receipt.message_id + '"] small');
        if (time && !time.dataset.read) {time.textContent = time.textContent.replace(/ · Read$/, '') + ' · Read'; time.dataset.read = 'true';}
      });
      if (nearBottom) list.scrollTop = list.scrollHeight;
      status.textContent = list.children.length ? 'Messages up to date' : 'No messages yet';
      delay = data.has_more ? 100 : 5000;
    } catch {
      status.textContent = 'Messages could not refresh. Your draft is preserved; retrying.';
      delay = Math.min(delay * 2, 60000);
    }
    setTimeout(poll,delay);
  }
  setInterval(() => markVisible().catch(() => {}), 1500);
  poll();
})();
