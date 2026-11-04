document.querySelectorAll('form[method="post"]').forEach(form => form.addEventListener('submit', event => {
  if (form.dataset.highRisk && !form.dataset.confirmed) {
    event.preventDefault();
    const dialog = form.querySelector('dialog'), submitter = event.submitter;
    dialog.showModal();
    dialog.querySelector('[data-risk-cancel]').onclick = () => dialog.close();
    dialog.querySelector('[data-risk-continue]').onclick = () => {
      const confirm = dialog.querySelector('[data-risk-confirm]');
      if (!confirm.checked) {confirm.focus();return;}
      form.querySelector('[name=acknowledge]').value='yes';
      form.dataset.confirmed='true';dialog.close();form.requestSubmit(submitter);
    };
    return;
  }
  if (form.dataset.submitting) {event.preventDefault();return;}
  form.dataset.submitting = 'true';
  const button = event.submitter;
  if (button) button.setAttribute('aria-busy','true');
}));
window.addEventListener('pageshow', () => document.querySelectorAll('form').forEach(form => {
  delete form.dataset.submitting;
  form.querySelectorAll('[aria-busy]').forEach(button => button.removeAttribute('aria-busy'));
}));
document.querySelectorAll('.errorlist').length && document.querySelector('.errorlist')?.scrollIntoView({block:'nearest'});
document.querySelectorAll('input[type=file]').forEach(input => input.addEventListener('change', () => {
  let preview = input.parentElement.querySelector('[data-preview]');
  if (!preview) {preview = document.createElement('div');preview.dataset.preview='';preview.className='d-flex gap-2 flex-wrap mt-2';input.after(preview);}
  preview.querySelectorAll('img').forEach(img=>URL.revokeObjectURL(img.src));preview.replaceChildren();
  [...input.files].slice(0,6).forEach(file=>{if(!['image/jpeg','image/png','image/webp'].includes(file.type)||file.size>5242880)return;const img=document.createElement('img');img.src=URL.createObjectURL(file);img.alt='Selected image preview';img.width=90;img.height=90;img.style.objectFit='cover';preview.append(img);});
}));
