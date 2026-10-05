'use strict';
document.querySelectorAll('[data-minor-toggle]').forEach(box => {
  const form = box.form, exact = form.querySelector('[name="birth_date"]'), year = form.querySelector('[name="birth_year"]');
  if (!exact || !year) return;
  const update = () => {
    const showDate = box.checked || exact.value !== '';
    exact.closest('[data-birth-date]').hidden = !showDate;
    exact.required = box.checked;
    year.closest('[data-birth-year]').hidden = box.checked;
    year.required = !box.checked && year.dataset.originalRequired === '1';
  };
  year.dataset.originalRequired = year.required ? '1' : '0';
  box.addEventListener('change', update); update();
});
document.querySelectorAll('[data-character-count]').forEach(input => {
  const status = input.parentElement.querySelector('[data-character-status]');
  const update = () => { if (status) status.textContent = Array.from(input.value).length + ' / ' + input.maxLength + ' caractères'; };
  input.addEventListener('input', update); update();
});
document.querySelectorAll('[data-welcome-email]').forEach(box => {
  const input = box.form?.querySelector('[name="email"]');
  if (!input) return;
  const update = () => {
    const valid = input.value.trim() !== '' && input.validity.valid;
    box.disabled = !valid || box.dataset.smtpReady !== '1';
    if (box.disabled) box.checked = false;
    else if (box.dataset.welcomeDefault === '1' && !box.dataset.userChosen) box.checked = true;
  };
  box.addEventListener('change', () => { box.dataset.userChosen = '1'; });
  input.addEventListener('input', update); update();
});
document.querySelectorAll('[data-enrollment-receipt]').forEach(element => {
  window.setTimeout(() => location.replace(element.dataset.home), 60000);
});

document.querySelectorAll('[data-session-toggle]').forEach(button => {
  const row = document.getElementById(button.getAttribute('aria-controls'));
  if (!row) return;
  const close = () => { row.hidden = true; button.setAttribute('aria-expanded', 'false'); button.focus(); };
  button.addEventListener('click', () => {
    if (!row.hidden) return close();
    row.hidden = false; button.setAttribute('aria-expanded', 'true');
    row.querySelector('input:not([type="hidden"])')?.focus();
  });
  row.querySelector('[data-session-close]')?.addEventListener('click', close);
  row.addEventListener('keydown', event => { if (event.key === 'Escape') { event.preventDefault(); close(); } });
});

// One ordering component for all registries. Pointer gestures are limited to
// the handle: normal form editing and scrolling remain native on touch screens.
document.querySelectorAll('[data-order-list]').forEach(list => {
  const items = () => Array.from(list.children).filter(el => el.dataset.orderKey);
  const status = list.parentElement.querySelector('[data-order-status]');
  let busy = false, drag = null;
  const announce = text => { if (status) status.textContent = text; };
  const update = () => items().forEach((el, i, all) => {
    el.querySelector('[data-order-move="-1"]').disabled = busy || i === 0;
    el.querySelector('[data-order-move="1"]').disabled = busy || i === all.length - 1;
  });
  const persist = async before => {
    busy = true; update(); list.setAttribute('aria-busy', 'true'); announce('Enregistrement…');
    try {
      const body = new URLSearchParams({evolution_csrf: list.dataset.csrf, keys: JSON.stringify(items().map(el => el.dataset.orderKey))});
      const response = await fetch(list.dataset.orderUrl, {method: 'POST', credentials: 'same-origin', body});
      const result = await response.json();
      if (!response.ok || !result.ok) throw new Error();
      announce('Ordre enregistré.');
    } catch (_) {
      before.forEach(el => list.append(el));
      announce('Ordre non enregistré. La liste précédente est rétablie ; rechargez la page et réessayez.');
    } finally { busy = false; list.removeAttribute('aria-busy'); update(); }
  };
  list.addEventListener('click', event => {
    const button = event.target.closest('[data-order-move]');
    if (!button || busy) return;
    const card = button.closest('[data-order-key]'), before = items();
    const target = before[before.indexOf(card) + Number(button.dataset.orderMove)];
    if (!target) return;
    if (Number(button.dataset.orderMove) < 0) list.insertBefore(card, target);
    else list.insertBefore(target, card);
    // Keep focus on a usable control even when the item reaches an end.
    const direction = button.dataset.orderMove;
    persist(before).then(() => {
      const next = card.querySelector('[data-order-move="' + direction + '"]');
      (next.disabled ? card.querySelector('[data-order-move="' + (direction === '1' ? '-1' : '1') + '"]') : next).focus();
    });
  });
  list.addEventListener('pointerdown', event => {
    const handle = event.target.closest('.drag-handle');
    if (!handle || busy || (event.pointerType === 'mouse' && event.button !== 0)) return;
    event.preventDefault();
    drag = {card: handle.closest('[data-order-key]'), before: items(), pointer: event.pointerId, handle};
    handle.setPointerCapture(event.pointerId); drag.card.classList.add('is-dragging');
  });
  list.addEventListener('pointermove', event => {
    if (!drag || drag.pointer !== event.pointerId) return;
    const target = document.elementFromPoint(event.clientX, event.clientY)?.closest('[data-order-key]');
    if (!target || target.parentElement !== list || target === drag.card) return;
    const bounds = target.getBoundingClientRect();
    list.insertBefore(drag.card, event.clientY < bounds.top + bounds.height / 2 ? target : target.nextSibling);
  });
  const finish = cancelled => {
    if (!drag) return;
    const {card, before, handle, pointer} = drag; drag = null;
    card.classList.remove('is-dragging');
    if (handle.hasPointerCapture(pointer)) handle.releasePointerCapture(pointer);
    if (cancelled) { before.forEach(el => list.append(el)); update(); return; }
    if (items().some((el, i) => el !== before[i])) persist(before);
  };
  list.addEventListener('pointerup', () => finish(false));
  list.addEventListener('pointercancel', () => finish(true));
  list.addEventListener('keydown', event => { if (event.key === 'Escape') finish(true); });
  update();
});

// Existing category forms also remain explicitly submit-able without JS.
document.querySelectorAll('[data-order-key] .category-form, [data-order-key] .resource-category-form').forEach(form => {
  let queue = Promise.resolve(), sequence = 0;
  const status = form.closest('[data-order-list]').parentElement.querySelector('[data-order-status]');
  const save = () => {
    if (!form.reportValidity()) return;
    const body = new FormData(form), version = ++sequence;
    queue = queue.then(async () => {
      if (status) status.textContent = 'Enregistrement…';
      try {
        // A hidden input named "action" masks HTMLFormElement.action.
        const response = await fetch(form.getAttribute('action') || location.href, {method:'POST', body, credentials:'same-origin', headers:{'X-OpenFabLab-Autosave':'1'}});
        if (!response.headers.get('content-type')?.includes('application/json')) throw new Error('Réglages non enregistrés. La session ou le serveur doit être vérifié.');
        const result = await response.json();
        if (!response.ok || !result.ok) throw new Error(result.message || 'Réglages non enregistrés.');
        if (version === sequence && status) status.textContent = 'Réglages enregistrés.';
      } catch (error) {
        if (status) status.textContent = error.message + ' Rechargez pour retrouver les réglages enregistrés.';
      }
    });
  };
  form.addEventListener('change', save);
  form.addEventListener('submit', event => { event.preventDefault(); save(); });
});

// No auto-play or automatic navigation. A small dialog provides a keyboard/
// touch equivalent to hover details, with an explicit link to the source page.
document.querySelectorAll('[data-calendar-detail]').forEach(link => {
  link.addEventListener('click', event => {
    if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    const dialog = document.createElement('dialog'); dialog.className = 'calendar-dialog';
    const title = document.createElement('h2'); title.id = 'calendar-dialog-title'; title.textContent = link.dataset.title;
    dialog.setAttribute('aria-labelledby', title.id);
    const details = document.createElement('p'); details.className = 'multiline'; details.textContent = link.dataset.details;
    const people = document.createElement('ul'); people.className = 'calendar-people';
    let rows = [];
    try { rows = JSON.parse(link.dataset.people || '[]'); } catch (_) { /* Keep the source page accessible. */ }
    if (Array.isArray(rows)) rows.forEach(person => {
      const row = document.createElement('li');
      const name = document.createElement('strong'); name.textContent = person.name;
      row.append(name);
      if (person.category && /^[a-zA-Z0-9_-]+$/.test(person.category)) {
        const badge = document.createElement('span'); badge.className = 'category-badge category-' + person.category;
        badge.textContent = person.category_label || person.category;
        row.append(badge);
      }
      if (person.state) { const state = document.createElement('span'); state.className = 'calendar-person-state'; state.textContent = person.state; row.append(state); }
      people.append(row);
    });
    const open = document.createElement('a'); open.href = link.href; open.className = 'admin-button primary compact'; open.textContent = link.dataset.actionLabel || 'Ouvrir la page';
    const close = document.createElement('button'); close.type = 'button'; close.className = 'admin-button secondary compact'; close.textContent = 'Fermer';
    close.addEventListener('click', () => dialog.close());
    dialog.addEventListener('close', () => { dialog.remove(); link.focus(); });
    dialog.append(title, details); if (people.childElementCount) dialog.append(people);
    dialog.append(open, close); document.body.append(dialog); dialog.showModal(); close.focus();
    const visibility = document.getElementById('calendar-visibility');
    if (visibility) {
      const button = document.createElement('button');button.type = 'button';button.className = 'admin-button secondary compact';
      button.textContent = link.dataset.hidden === '1' ? 'Réafficher cet événement' : 'Masquer cet événement';
      button.addEventListener('click', () => {
        for (const key of ['kind', 'key', 'day']) visibility.elements.namedItem(key).value = link.dataset[key];
        visibility.elements.namedItem('hidden').value = link.dataset.hidden === '1' ? '0' : '1';
        visibility.submit();
      });dialog.append(button);
    }
  });
});
