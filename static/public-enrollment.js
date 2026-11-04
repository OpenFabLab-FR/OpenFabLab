/* OFL native UI marked */
/* Shared-device privacy. The server is authoritative; pagehide is only extra
   protection. New GETs, leaving HTML pages, expiry and completion revoke there. */
(() => {
  'use strict';
  const __oflT_52e4fa64=text=>window.OFLTranslate?.(text)||text;
  const form = document.querySelector('[data-public-enrollment]');
  if (!form) return;
  let submitting = false;
  let nativeSubmission = false;
  let finished = false;
  const deadline = Date.now() + Number(form.dataset.enrollmentSeconds || 0) * 1000;
  const edited = new WeakSet();
  // Browser history restoration does not emit beforeinput. Genuine new input
  // must survive the delayed cleanup, even when an animation frame is late.
  form.addEventListener('beforeinput', event => {
    if (event.isTrusted) edited.add(event.target);
  });
  form.addEventListener('change', event => {
    if (event.isTrusted) edited.add(event.target);
  });
  const clear = (preserveEdits = false) => {
    form.querySelectorAll('input:not([type="hidden"]), textarea').forEach(field => {
      if (preserveEdits && edited.has(field)) return;
      if (['checkbox', 'radio'].includes(field.type)) field.checked = field.name === 'send_welcome' && field.defaultChecked;
      else field.value = ['public_id', 'phone_country_code'].includes(field.name) ? field.defaultValue : '';
    });
    form.querySelectorAll('select').forEach(field => {
      if (!preserveEdits || !edited.has(field)) field.selectedIndex = 0;
    });
    form.querySelectorAll('[data-selected-responsible]').forEach(field => field.remove());
  };
  const token = () => form.querySelector('[name="evolution_csrf"]').value;
  const renew = value => {
    document.querySelectorAll('input[name="evolution_csrf"]').forEach(field => {
      field.value = value; field.defaultValue = value;
    });
  };
  const expire = () => {
    if (finished) return;
    finished = true; clear();
    window.location.replace(form.dataset.enrollmentHome);
  };
  const focusError = () => window.requestAnimationFrame(() => {
    const field = form.querySelector('[aria-invalid="true"]');
    if (field) { field.focus(); if (!field.readOnly && typeof field.select === 'function') field.select(); }
    else {
      const region = document.querySelector('[data-enrollment-errors]:not([hidden])');
      if (region) { region.tabIndex = -1; region.focus(); }
    }
  });
  const showErrors = (messages, fields = {}) => {
    const region = document.querySelector('[data-enrollment-errors]');
    if (region) {
      const heading = document.createElement('strong'), list = document.createElement('ul');
      heading.textContent = __oflT_52e4fa64('Vérifiez ces informations :');
      messages.forEach(message => { const item = document.createElement('li'); item.textContent = message; list.append(item); });
      region.replaceChildren(heading, list); region.hidden = false;
    }
    form.querySelectorAll('[data-enrollment-error-for]').forEach(error => { error.hidden = true; error.textContent = ''; });
    form.querySelectorAll('[aria-invalid]').forEach(field => field.removeAttribute('aria-invalid'));
    for (const [name, message] of Object.entries(fields)) {
      const field = form.elements.namedItem(name);
      if (!(field instanceof HTMLElement)) continue;
      let error = [...form.querySelectorAll('[data-enrollment-error-for]')].find(n => n.dataset.enrollmentErrorFor === name);
      if (!error) {
        error = document.createElement('small'); error.className = 'enrollment-field-error';
        error.dataset.enrollmentErrorFor = name; error.id = 'enrollment-error-' + name;
        field.closest('.form-field')?.append(error);
      }
      error.textContent = message; error.hidden = false; field.setAttribute('aria-invalid', 'true');
      const described = new Set((field.getAttribute('aria-describedby') || '').split(' ').filter(Boolean));
      described.add(error.id); field.setAttribute('aria-describedby', [...described].join(' '));
    }
    focusError();
  };
  const state = async () => {
    const documentToken = token();
    try {
      const response = await fetch(form.dataset.enrollmentState, {credentials:'same-origin',cache:'no-store',headers:{'X-OpenFabLab-Enrollment':documentToken}});
      if (!response.ok) return null;
      const value = await response.json();
      return documentToken === token() ? value.active === true : null;
    } catch (_) { return null; }
  };
  form.addEventListener('submit', async event => {
    if (submitting || finished) { event.preventDefault(); return; }
    // Keep the existing guardian verification and no-JS HTML fallback.
    if (event.submitter?.name === 'family_step' || typeof fetch !== 'function') {
      nativeSubmission = true; submitting = true; return;
    }
    event.preventDefault();
    if (Date.now() >= deadline) { expire(); return; }
    const body = new FormData(form);
    submitting = true; form.setAttribute('aria-busy','true');
    const controls = [...form.querySelectorAll('input:not([type=hidden]),textarea,select,button')].map(field => [field,field.disabled]);
    controls.forEach(([field]) => { field.disabled = true; });
    try {
      const active = await state();
      if (finished) return;
      if (active === false) { expire(); return; }
      if (active === null) throw new Error('NetworkUnavailable');
      const response = await fetch(form.action, {method:'POST',body,credentials:'same-origin',cache:'no-store',
        headers:{'Accept':'application/json','X-OpenFabLab-Enrollment-Form':'1'}});
      if (finished) return;
      if (response.headers.get('content-type')?.includes('application/json')) {
        const value = await response.json();
        if (finished) return;
        if (value.enrollment === true && value.ok === true && response.ok) {
          const next = new URL(value.redirect, location.href);
          if (next.origin !== location.origin) throw new Error('InvalidResponse');
          finished = true; nativeSubmission = true; clear(); window.location.replace(next.href); return;
        }
        if (value.enrollment === true && Array.isArray(value.errors) && typeof value.csrf_token === 'string') {
          renew(value.csrf_token);
          if (typeof value.proposed_id === 'string') {
            const identifier = form.elements.namedItem('public_id');
            if (identifier) identifier.value = value.proposed_id;
          }
          showErrors(value.errors, value.field_errors || {}); return;
        }
      }
      if (await state() === false) { expire(); return; }
      showErrors([__oflT_52e4fa64('Le service ne répond pas correctement. Vos informations sont conservées dans ce formulaire. Réessayez dans un instant ou demandez à l’équipe.')]);
    } catch (_) {
      if (!finished) showErrors([__oflT_52e4fa64('Connexion interrompue. Vos informations sont encore dans ce formulaire. Vérifiez la connexion puis réessayez. En cas de doute, demandez à l’équipe avant de recommencer.')]);
    } finally {
      submitting = false; form.removeAttribute('aria-busy');
      controls.forEach(([field,disabled]) => { field.disabled = disabled; });
    }
  });
  // No browser persistence or extra lifetime: clear even when the tab has stayed
  // open, and recheck on return from a suspended/backgrounded device.
  window.setTimeout(expire, Math.max(0,deadline-Date.now()));
  window.setInterval(async () => {
    if (finished || submitting) return;
    if (Date.now() >= deadline) { expire(); return; }
    const active = await state();
    if (!submitting && active === false) expire();
  }, 30000);
  document.addEventListener('visibilitychange', () => { if (!document.hidden && Date.now() >= deadline) expire(); });
  focusError();
  window.addEventListener('pageshow', async event => {
    submitting = false;
    const navigation = window.performance?.getEntriesByType('navigation')[0];
    // Some browsers restore input values after pageshow even without BFCache.
    // A fresh GET must stay empty; only its non-personal proposed code remains.
    if (form.dataset.enrollmentFresh === '1') {
      clear(true);
      window.requestAnimationFrame(() => window.requestAnimationFrame(() => {
        if (!submitting) clear(true);
      }));
      const welcome = form.querySelector('[name="send_welcome"]');
      if (welcome) welcome.checked = welcome.defaultChecked;
    }
    // A refreshed POST verification page must not repeat someone's identity.
    if (navigation?.type === 'reload') {
      clear(); window.location.replace(form.dataset.enrollmentStart); return;
    }
    if (!event.persisted && navigation?.type !== 'back_forward') return;
    try {
      const response = await fetch(form.dataset.enrollmentState, {
        credentials:'same-origin', cache:'no-store',
        headers:{'X-OpenFabLab-Enrollment':form.querySelector('[name="evolution_csrf"]').value}
      });
      if (response.ok && (await response.json()).active) return;
    } catch (_) { /* Never keep personal content when state cannot be verified. */ }
    clear(); window.location.replace(form.dataset.enrollmentStart);
  });
  window.addEventListener('pagehide', () => {
    if (nativeSubmission) return; // Verify / correct within the same active form.
    const data = new FormData();
    data.set('evolution_csrf', form.querySelector('[name="evolution_csrf"]').value);
    clear();
    if (navigator.sendBeacon) navigator.sendBeacon(form.dataset.enrollmentCancel, data);
    else fetch(form.dataset.enrollmentCancel, {method:'POST',body:data,credentials:'same-origin',keepalive:true}).catch(() => {});
  });
})();
