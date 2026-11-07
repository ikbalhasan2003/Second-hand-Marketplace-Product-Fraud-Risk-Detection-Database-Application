// Progressive enhancements: the server remains authoritative for every mutation.
(() => {
  const announce = (form, text) => {
    let status = form.querySelector('[data-submit-status]');
    if (!status) { status = document.createElement('p'); status.dataset.submitStatus = ''; status.setAttribute('role', 'status'); form.append(status); }
    status.textContent = text;
  };
  document.querySelectorAll('[data-order-review]').forEach(form => {
    const dialog = form.querySelector('dialog'), trigger = form.querySelector('[data-review-trigger]'), cancel = form.querySelector('[data-review-cancel]');
    dialog.close(); trigger.hidden = false; cancel.hidden = false;
    trigger.addEventListener('click', () => {dialog.showModal(); dialog.querySelector('h2').focus();});
    cancel.addEventListener('click', () => dialog.close());
    dialog.addEventListener('close', () => trigger.focus());
  });
  document.querySelectorAll('form').forEach(form => {
    // Associate server field errors even when custom widgets are used.
    form.querySelectorAll('.errorlist').forEach((errors, index) => {
      const field = errors.parentElement.querySelector('input:not([type=hidden]),textarea,select');
      if (field) {errors.id ||= `field-errors-${index}-${field.id}`; field.setAttribute('aria-invalid', 'true'); field.setAttribute('aria-describedby', [field.getAttribute('aria-describedby'), errors.id].filter(Boolean).join(' '));}
    });
    form.addEventListener('submit', event => {
      if (form.method.toLowerCase() !== 'post') return;
      if (form.dataset.submitting) {event.preventDefault(); return;}
      const selectedAction = form.querySelector('select[name=status],select[name=action]')?.selectedOptions[0]?.textContent;
      if (form.dataset.confirmAction && !window.confirm(form.dataset.confirmAction + (selectedAction ? '\nAction: ' + selectedAction : ''))) {event.preventDefault(); return;}
      form.dataset.submitting = 'true';
      if (event.submitter) event.submitter.setAttribute('aria-busy', 'true');
      announce(form, 'Submitting. Please wait for confirmation.');
    });
  });
  window.addEventListener('pageshow', () => document.querySelectorAll('form').forEach(form => {
    delete form.dataset.submitting;
    form.querySelectorAll('[aria-busy]').forEach(button => button.removeAttribute('aria-busy'));
    form.querySelector('[data-submit-status]')?.remove();
  }));
  const summary = document.querySelector('[data-error-summary], [role=alert]');
  if (summary) {summary.tabIndex = -1; summary.focus();}
  document.querySelectorAll('textarea[maxlength]').forEach(field => {
    const counter = document.createElement('small'); counter.className = 'helptext'; counter.id = `${field.id}-counter`; field.after(counter);
    field.setAttribute('aria-describedby', [field.getAttribute('aria-describedby'), counter.id].filter(Boolean).join(' '));
    const update = () => {counter.textContent = `${field.value.length}/${field.maxLength} characters`;};
    field.addEventListener('input', update); update();
  });
  document.querySelectorAll('input[type=file]').forEach(input => {
    const limit = Number(input.dataset.maxFiles || (input.name === 'evidence' ? 3 : 6));
    const preview = document.createElement('div'); preview.className = 'upload-preview'; preview.setAttribute('aria-live', 'polite'); input.after(preview);
    const render = () => {
      preview.querySelectorAll('img').forEach(img => URL.revokeObjectURL(img.src)); preview.replaceChildren();
      const files = [...input.files], count = document.createElement('p'); count.textContent = `${files.length} of ${limit} images selected`; preview.append(count);
      input.setCustomValidity(files.length > limit ? `Maximum ${limit} images` : '');
      files.forEach((file, index) => {
        const row = document.createElement('div'), label = document.createElement('span'), remove = document.createElement('button');
        const error = !['image/jpeg','image/png','image/webp'].includes(file.type) ? 'Unsupported image format' : file.size > 5242880 ? 'File exceeds 5 MB' : '';
        label.textContent = `${file.name} (${Math.ceil(file.size / 1024)} KB) - ${error || 'Selected; server validation required'}`;
        if (error) input.setCustomValidity(error);
        row.append(label); remove.type = 'button'; remove.className = 'btn btn-outline-secondary btn-sm'; remove.textContent = `Remove ${file.name}`;
        remove.onclick = () => { const data = new DataTransfer(); files.forEach((item, i) => {if (i !== index) data.items.add(item);}); input.files = data.files; render(); input.focus(); };
        row.append(remove);
        for (const [offset, title] of [[-1, 'Move earlier'], [1, 'Move later']]) {
          const reorder = document.createElement('button'); reorder.type = 'button'; reorder.className = 'btn btn-outline-secondary btn-sm'; reorder.textContent = `${title}: ${file.name}`;
          reorder.disabled = index + offset < 0 || index + offset >= files.length;
          reorder.onclick = () => {const data = new DataTransfer(), sorted = [...files]; [sorted[index], sorted[index + offset]] = [sorted[index + offset], sorted[index]]; sorted.forEach(item => data.items.add(item)); input.files = data.files; render(); input.focus();};
          row.append(reorder);
        }
        preview.append(row);
      });
    };
    input.addEventListener('change', render);
  });
  // Only explicitly marked non-secret text is recoverable, scoped to this tab and identity.
  try {
    const owner = document.body.dataset.userId;
    const pendingKey = `market-pending-draft:${owner}`;
    if (document.querySelector('[data-committed]')) {const pending = sessionStorage.getItem(pendingKey); if (pending) sessionStorage.removeItem(pending); sessionStorage.removeItem(pendingKey);}
    document.querySelectorAll('form[data-preserve-draft]').forEach(form => {
      const key = `market-draft:${owner}:${location.pathname}`;
      const fields = [...form.querySelectorAll('textarea,input[type=text],input[type=number]')].filter(field => field.name && !field.readOnly && !field.disabled);
      const stored = JSON.parse(sessionStorage.getItem(key) || '{}'); let recovered = false;
      fields.forEach(field => {if (!field.value && stored[field.name]) {field.value = stored[field.name]; recovered = true;}});
      if (recovered) announce(form, 'Recovered unsent text from this tab. Review before submitting. Files must be selected again.');
      form.addEventListener('input', () => sessionStorage.setItem(key, JSON.stringify(Object.fromEntries(fields.map(field => [field.name, field.value])))));
      form.addEventListener('submit', () => {if (form.checkValidity()) sessionStorage.setItem(pendingKey, key);});
    });
  } catch { /* Storage can be disabled; normal server forms continue working. */ }
  document.querySelectorAll('select[data-selected]').forEach(select => {select.value = select.dataset.selected;});
  document.querySelectorAll('nav a').forEach(link => {if (!link.closest('.category-nav') && link.pathname === location.pathname && link.search === location.search) link.setAttribute('aria-current', 'page');});
  document.querySelectorAll('.table-responsive').forEach(region => {region.tabIndex = 0; region.setAttribute('role', 'region'); region.setAttribute('aria-label', region.querySelector('caption')?.textContent || 'Scrollable records');});
})();
// Preserve an honest photo state when a stored listing image cannot be loaded.
document.querySelectorAll('img.listing-image').forEach(image => {
  const unavailable = () => {
    const state = document.createElement('div');
    state.className = 'image-placeholder';
    state.textContent = 'Photo unavailable';
    image.replaceWith(state);
  };
  image.addEventListener('error', unavailable, {once: true});
  if (image.complete && image.naturalWidth === 0) unavailable();
});
