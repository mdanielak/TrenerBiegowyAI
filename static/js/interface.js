const toggle = document.querySelector('.nav-toggle');
if (toggle) {
  document.documentElement.classList.add('has-js');
  toggle.addEventListener('click', () => {
    const open = toggle.getAttribute('aria-expanded') !== 'true';
    toggle.setAttribute('aria-expanded', String(open));
    document.getElementById('primary-nav').classList.toggle('is-open', open);
  });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && toggle.getAttribute('aria-expanded') === 'true') {
      toggle.click(); toggle.focus();
    }
  });
}
document.querySelectorAll('[data-password-toggle]').forEach(button => {
  button.addEventListener('click', () => {
    const field = document.getElementById(button.dataset.passwordToggle);
    const show = field.type === 'password';
    field.type = show ? 'text' : 'password';
    button.setAttribute('aria-pressed', String(show));
    button.textContent = show ? 'Ukryj hasło' : 'Pokaż hasło';
  });
});
document.querySelector('[role="alert"][autofocus]')?.focus();
async function pollJob() {
  const current = document.getElementById('job-status');
  if (!current || current.dataset.poll !== 'true') return;
  try {
    const response = await fetch(location.href, {cache: 'no-store'});
    if (!response.ok) throw new Error('status');
    const page = new DOMParser().parseFromString(await response.text(), 'text/html');
    const next = page.getElementById('job-status');
    if (!next) throw new Error('content');
    if (!current.contains(document.activeElement) && current.innerHTML !== next.innerHTML) current.replaceWith(next);
    document.getElementById('poll-error')?.remove();
  } catch {
    if (!document.getElementById('poll-error')) {
      const message = document.createElement('p');
      message.id = 'poll-error'; message.setAttribute('role', 'status');
      message.textContent = 'Nie można odświeżyć postępu. Spróbuję ponownie za kilka sekund. Możesz też odświeżyć stronę ręcznie.';
      current.after(message);
    }
  }
  setTimeout(pollJob, 5000);
}
setTimeout(pollJob, 5000);

// Po ułożeniu lub wysłaniu planu strona ma się odświeżyć sama, ale nie kosztem niezapisanego tekstu.
async function reloadWhenDone() {
  if (!document.querySelector('[data-reload-when-done]')) return;
  try {
    const response = await fetch(location.href, {cache: 'no-store'});
    const page = new DOMParser().parseFromString(await response.text(), 'text/html');
    if (response.ok && !page.querySelector('[data-reload-when-done]')) {
      const dirty = Array.from(document.querySelectorAll('textarea, input[type="text"]'))
        .some(field => field.value !== field.defaultValue);
      if (!dirty) { location.reload(); return; }
      const banner = document.querySelector('[data-reload-when-done]');
      banner.removeAttribute('data-reload-when-done');
      const link = document.createElement('p');
      link.innerHTML = '<a href="">Gotowe — odśwież stronę</a> (najpierw zapisz wpisany tekst).';
      (banner.querySelector('.banner-body') || banner).append(link);
      return;
    }
    // Wciąż trwa: podmień sam postęp (etap, procent, czas), reszta strony zostaje nietknięta.
    const fresh = page.querySelector('.sync-status .sync-progress');
    const shown = document.querySelector('.sync-status .sync-progress');
    // Bez response.ok: przy pierwszym pobieraniu strona bez danych odpowiada 404, a pasek ma iść dalej.
    if (fresh && shown) shown.replaceWith(document.importNode(fresh, true));
  } catch {
    // Brak połączenia: spróbujemy ponownie za chwilę.
  }
  setTimeout(reloadWhenDone, 5000);
}
setTimeout(reloadWhenDone, 5000);

// Czas etapu tyka co sekundę w przeglądarce; serwer poprawia go przy każdym sprawdzeniu postępu.
setInterval(() => {
  document.querySelectorAll('[data-elapsed]').forEach(span => {
    const seconds = Number(span.dataset.elapsed) + 1;
    span.dataset.elapsed = seconds;
    const minutes = Math.floor(seconds / 60);
    span.textContent = minutes ? `${minutes} min ${seconds % 60} s` : `${seconds % 60} s`;
  });
}, 1000);

// Keep submitter names intact for multi-action forms while preventing duplicate requests.
document.querySelectorAll('form[method="post"]').forEach(form => {
  let submitting = false;
  window.addEventListener('pageshow', () => {
    submitting = false; form.removeAttribute('aria-busy');
    form.querySelector('[data-submit-feedback]')?.remove();
  });
  form.addEventListener('submit', event => {
    if (submitting) { event.preventDefault(); return; }
    submitting = true;
    form.setAttribute('aria-busy', 'true');
    const feedback = document.createElement('p');
    feedback.dataset.submitFeedback = 'true';
    feedback.setAttribute('role', 'status');
    feedback.textContent = 'Przetwarzanie…';
    form.append(feedback);
  });
});

const painNote = document.getElementById('pain-note-field');
if (painNote) {
  const painChecks = document.querySelectorAll('#journal-form input[name="pain"]');
  const note = painNote.querySelector('input');
  const updatePainNote = () => { painNote.hidden = !note.value.trim() && !Array.from(painChecks).some(input => input.checked); };
  painChecks.forEach(input => input.addEventListener('change', updatePainNote));
  note.addEventListener('input', updatePainNote);
  updatePainNote();
}
