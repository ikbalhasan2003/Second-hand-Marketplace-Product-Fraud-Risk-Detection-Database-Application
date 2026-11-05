(() => {
  document.querySelectorAll('[data-risk-refresh]').forEach(region => {
  const status = region.parentElement.querySelector('[data-risk-status]');
  let delay = 10000, lastSuccess = null, reviewChanged = false;
  async function poll() {
    if (document.hidden || document.querySelector('dialog[open]') || region.contains(document.activeElement)) {setTimeout(poll, delay); return;}
    try {
      const response = await fetch(region.dataset.riskRefresh, {headers: {Accept: 'text/html'}, signal: AbortSignal.timeout(15000)});
      if (!response.ok || response.redirected) throw Error('refresh');
      const html = await response.text();
      // The user can move focus or open the review while the request is in flight.
      // Defer applying the response until the next poll can safely update the panel.
      if (document.hidden || document.querySelector('dialog[open]') || region.contains(document.activeElement)) {
        setTimeout(poll, delay); return;
      }
      const parsed = new DOMParser().parseFromString(html, 'text/html').querySelector('section.risk');
      if (!parsed) throw Error('response');
      const changed = region.textContent.replace(/\s+/g, ' ').trim() !== parsed.textContent.replace(/\s+/g, ' ').trim();
      if (changed && document.querySelector('[data-order-review]')) {
        reviewChanged = true;
        const trigger = document.querySelector('[data-review-trigger]'); if (trigger) trigger.disabled = true;
      }
      if (region.innerHTML.trim() !== parsed.outerHTML.trim()) {
        const x = window.scrollX, y = window.scrollY;
        const expanded = region.querySelector('details')?.open;
        region.replaceChildren(parsed); if (expanded && parsed.querySelector('details')) parsed.querySelector('details').open = true;
        window.scrollTo(x, y);
      }
      lastSuccess = new Date().toLocaleString(undefined, {timeZoneName:'short'}); status.textContent = `Last refreshed ${lastSuccess}`; delay = 10000;
    } catch {status.textContent = `Unable to refresh. Data may be out of date.${lastSuccess ? ' Last successful refresh: '+lastSuccess : ''} Retrying automatically.`; delay = Math.min(delay * 2, 60000);}
    if (reviewChanged) {
      const reviewLink = document.createElement('a'); reviewLink.href = location.pathname; reviewLink.textContent = 'Assessment changed. Review the updated listing before ordering.'; status.append(' ', reviewLink);
    }
    setTimeout(poll, delay);
  }
  setTimeout(poll, delay);
  });
})();
