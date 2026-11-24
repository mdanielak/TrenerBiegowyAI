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

document.querySelector('[autofocus][tabindex="-1"]')?.focus();

const otherDistance = document.getElementById('other-distance');
if (otherDistance) {
  const updateOtherDistance = () => {
    const selected = document.querySelector('input[name="distance"]:checked');
    otherDistance.hidden = !selected || selected.value !== 'other';
  };
  document.querySelectorAll('input[name="distance"]').forEach(input => input.addEventListener('change', updateOtherDistance));
  updateOtherDistance();
}

function openHashDetails(hashValue = location.hash) {
  const targetId = (hashValue || '').replace(/^#/, '');
  if (!targetId) return;
  const target = document.getElementById(targetId);
  if (!target) return;
  const details = target.tagName === 'DETAILS' ? target : target.closest('details');
  if (details) details.open = true;
}
openHashDetails();
window.addEventListener('hashchange', () => openHashDetails());
document.querySelectorAll('a[href^="#"]').forEach(anchor => {
  anchor.addEventListener('click', () => openHashDetails(anchor.getAttribute('href')));
});

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
if (document.getElementById('job-status')?.dataset.poll === 'true') {
  setTimeout(pollJob, 5000);
}

// Po ułożeniu lub wysłaniu planu strona ma się odświeżyć sama, ale nie kosztem niezapisanego tekstu.
async function reloadWhenDone() {
  if (!document.querySelector('[data-reload-when-done]')) return;
  try {
    const response = await fetch(location.href, {cache: 'no-store'});
    const page = new DOMParser().parseFromString(await response.text(), 'text/html');
    if (response.ok && !page.querySelector('[data-reload-when-done]')) {
      // Każde zmienione pole się liczy: data, liczba, zaznaczenie, hasło, nie tylko tekst.
      const dirty = Array.from(document.querySelectorAll('textarea, input:not([type="hidden"]):not([type="submit"])'))
        .some(field => field.value !== field.defaultValue || field.checked !== field.defaultChecked);
      if (!dirty) { location.reload(); return; }
      const banner = document.querySelector('[data-reload-when-done]');
      banner.removeAttribute('data-reload-when-done');
      const link = document.createElement('p');
      const reloadAnchor = document.createElement('a');
      reloadAnchor.href = '';
      reloadAnchor.textContent = 'Gotowe — odśwież stronę';
      link.append(reloadAnchor, document.createTextNode(' (najpierw zapisz wpisany tekst).'));
      (banner.querySelector('.banner-body') || banner).append(link);
      return;
    }
    // Wciąż trwa: podmień same paski postępu (synchronizacja, plan), reszta strony zostaje nietknięta.
    const fresh = page.querySelectorAll('.sync-progress');
    // Bez response.ok: przy pierwszym pobieraniu strona bez danych odpowiada 404, a pasek ma iść dalej.
    document.querySelectorAll('.sync-progress').forEach((shown, index) => {
      if (fresh[index]) shown.replaceWith(document.importNode(fresh[index], true));
    });
  } catch {
    // Brak połączenia: spróbujemy ponownie za chwilę.
  }
  setTimeout(reloadWhenDone, 5000);
}
if (document.querySelector('[data-reload-when-done]')) {
  setTimeout(reloadWhenDone, 5000);
}

// Czas etapu tyka co sekundę w przeglądarce; serwer poprawia go przy każdym sprawdzeniu postępu.
if (document.querySelector('[data-elapsed]')) {
  setInterval(() => {
    document.querySelectorAll('[data-elapsed]').forEach(span => {
      const seconds = Number(span.dataset.elapsed) + 1;
      span.dataset.elapsed = seconds;
      const minutes = Math.floor(seconds / 60);
      span.textContent = minutes ? `${minutes} min ${seconds % 60} s` : `${seconds % 60} s`;
    });
  }, 1000);
}

// Odliczanie przerwy (np. po ułożeniu planu): co sekundę mniej, przy zerze komunikat znika.
function secondsWord(count) {
  const last = count % 10, lastTwo = count % 100;
  if (count === 1) return 'sekundę';
  return last >= 2 && last <= 4 && (lastTwo < 12 || lastTwo > 14) ? 'sekundy' : 'sekund';
}
document.querySelectorAll('[data-countdown]').forEach(span => {
  const timer = setInterval(() => {
    const seconds = Number(span.dataset.countdown) - 1;
    if (seconds <= 0) {
      clearInterval(timer);
      (span.closest('[data-countdown-banner]') || span).remove();
      return;
    }
    span.dataset.countdown = seconds;
    span.textContent = `${seconds} ${secondsWord(seconds)}`;
  }, 1000);
});

// Keep submitter names intact for multi-action forms while preventing duplicate requests.
document.querySelectorAll('form[method="post"]:not([data-review-form])').forEach(form => {
  let submitting = false;
  window.addEventListener('pageshow', () => {
    submitting = false; form.removeAttribute('aria-busy');
    form.querySelector('[data-submit-feedback]')?.remove();
  });
  form.addEventListener('submit', event => {
    if (submitting) { event.preventDefault(); return; }
    submitting = true;
    form.setAttribute('aria-busy', 'true');
    const customProgressId = form.dataset.testProgress;
    if (customProgressId && event.submitter?.getAttribute('formaction') === '/settings/ai/test') {
      const progress = document.getElementById(customProgressId);
      if (progress) {
        progress.hidden = false;
        return;
      }
    }
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

// Szczegóły treningu: natywne okienko (Esc zamyka samo); kliknięcie w tło też zamyka.
let lastDialogTrigger = null;
document.querySelectorAll('[data-dialog]').forEach(button => {
  button.addEventListener('click', () => {
    const dialog = document.getElementById(button.dataset.dialog);
    if (!dialog) return;
    lastDialogTrigger = button;
    dialog.showModal();
  });
});
document.querySelectorAll('dialog').forEach(dialog => {
  dialog.addEventListener('click', event => {
    if (event.target === dialog) dialog.close();
  });
  dialog.addEventListener('close', () => {
    lastDialogTrigger?.focus();
  });
});

// Wiadomość do trenera nie ginie po przejściu na inną stronę: szkic w pamięci karty do czasu wysłania.
document.querySelectorAll('form[data-draft-key]').forEach(form => {
  const field = form.querySelector('textarea, input[type="text"]');
  const key = form.dataset.draftKey;
  if (!field) return;
  try { const draft = sessionStorage.getItem(key); if (draft !== null && draft !== field.value) field.value = draft; } catch {}
  field.addEventListener('input', () => { try { sessionStorage.setItem(key, field.value); } catch {} });
  const isCoachChat = form.classList.contains('coach-form');
  form.addEventListener('submit', () => {
    try {
      sessionStorage.removeItem(key);
      if (isCoachChat) sessionStorage.setItem(key + '-sent', field.value.trim());
    } catch {}
  });
  // Ctrl+Enter (Cmd+Enter) wysyła; zwykły Enter zostaje nową linią.
  field.addEventListener('keydown', event => {
    if (event.key === 'Enter' && (event.ctrlKey || event.metaKey) && !form.querySelector('button[type="submit"]')?.disabled) {
      event.preventDefault();
      form.requestSubmit();
    }
  });
  if (!isCoachChat) return;
  // Pytanie zapisuje się razem z odpowiedzią; do tego czasu pokaż je nad „Trener odpowiada…”.
  const pending = document.querySelector('.coach-msg.is-pending');
  let sent = '';
  try { sent = sessionStorage.getItem(key + '-sent') || ''; if (!pending) sessionStorage.removeItem(key + '-sent'); } catch {}
  // Nieudana odpowiedź: pytanie wraca do pola, żeby wystarczyło wysłać je jeszcze raz.
  if (document.querySelector('.coach-failed') && sent && !field.value) {
    field.value = sent;
    try { sessionStorage.setItem(key, sent); sessionStorage.removeItem(key + '-sent'); } catch {}
  }
  if (pending && sent) {
    const bubble = document.createElement('div');
    bubble.className = 'coach-msg is-you coach-sent';
    const who = document.createElement('span'); who.className = 'coach-who'; who.textContent = 'Ty';
    const text = document.createElement('p'); text.textContent = sent;
    bubble.append(who, text);
    pending.before(bubble);
  }
});

// Przełącznik „Dotyczy”: podpis, przykład i przycisk mówią, co się stanie z wiadomością (dziś albo cały tydzień).
document.querySelectorAll('form.coach-form').forEach(form => {
  const parts = [form.querySelector('.coach-label'), form.querySelector('.coach-submit-text')].filter(Boolean);
  parts.forEach(el => { el.dataset.today = el.textContent; });
  const field = form.querySelector('textarea');
  if (field) field.dataset.todayPlaceholder = field.placeholder;
  const hint = form.querySelector('.coach-scope-hint');
  const apply = () => {
    const week = form.querySelector('input[name="scope"]:checked')?.value === 'week';
    parts.forEach(el => { el.textContent = week ? el.dataset.week : el.dataset.today; });
    if (field) field.placeholder = week ? field.dataset.weekPlaceholder : field.dataset.todayPlaceholder;
    if (hint) hint.hidden = !week;
  };
  form.querySelectorAll('input[name="scope"]').forEach(input => input.addEventListener('change', apply));
  apply();
});


// „Oceń mój ostatni trening” i „Oceń mój tydzień biegowy”: pasek ładowania i komentarz trenera pojawia się w tym samym miejscu, bez odświeżania strony.
document.querySelectorAll('[data-review-box]').forEach(box => {
  const form = box.querySelector('[data-review-form]');
  const row = form.closest('.spread');
  const loading = box.querySelector('[data-review-loading]');
  const error = box.querySelector('[data-review-error]');
  const statusUrl = box.dataset.statusUrl;
  const result = box.querySelector('[data-review-result]');
  const label = box.querySelector('[data-review-label]');
  const pause = ms => new Promise(resolve => setTimeout(resolve, ms));

  function showError(message) {
    loading.hidden = true;
    row.hidden = false;
    form.querySelector('button').disabled = false;
    error.textContent = message;
    error.hidden = false;
  }

  function showComment(text) {
    if (result) {  // ocena tygodnia: komentarz zostaje nad przyciskiem, który można użyć ponownie
      result.querySelector('.suggestion-text').textContent = text;
      result.hidden = false;
      loading.hidden = true;
      row.hidden = false;
      form.querySelector('button').disabled = false;
      if (label?.dataset.againLabel) label.textContent = label.dataset.againLabel;
      return;
    }
    const wrapper = document.createElement('div');
    wrapper.className = 'suggestion';
    const inner = document.createElement('div');
    const title = document.createElement('p');
    title.className = 'suggestion-title';
    title.textContent = 'Komentarz trenera';
    const body = document.createElement('p');
    body.className = 'suggestion-text';
    body.textContent = text;
    inner.append(title, body);
    wrapper.append(inner);
    box.replaceWith(wrapper);
  }

  form.addEventListener('submit', async event => {
    event.preventDefault();
    error.hidden = true;
    form.querySelector('button').disabled = true;
    row.hidden = true;
    loading.hidden = false;
    try {
      const sent = await fetch(form.action, {method: 'POST', body: new FormData(form), headers: {'X-Requested-With': 'fetch'}});
      const first = await sent.json();
      if (first.state === 'failed') return showError(first.message || 'Nie udało się ocenić treningu.');
      // Zadanie w tle trwa zwykle kilkanaście sekund; pytamy o wynik co 2 s, najdłużej przez 4 minuty.
      for (let attempt = 0; attempt < 120; attempt++) {
        await pause(2000);
        const status = await (await fetch(statusUrl, {cache: 'no-store'})).json();
        if (status.state === 'done') return showComment(status.comment);
        if (status.state === 'failed') return showError(status.message || 'Nie udało się ocenić treningu.');
        if (status.state === 'idle' && first.state === 'busy') return showError('Poczekaj chwilę i spróbuj ponownie.');
      }
      showError('Ocena trwa dłużej niż zwykle. Odśwież stronę za chwilę, komentarz może już tam być.');
    } catch {
      showError('Nie udało się połączyć z aplikacją. Spróbuj ponownie.');
    }
  });
});
