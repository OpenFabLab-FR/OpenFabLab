/* Shared-device privacy. The server is authoritative; pagehide is only extra
   protection. New GETs, leaving HTML pages, expiry and completion revoke there. */
(() => {
  'use strict';
  const form = document.querySelector('[data-public-enrollment]');
  if (!form) return;
  let submitting = false;
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
  form.addEventListener('submit', () => { submitting = true; });
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
    if (submitting) return; // Verify / correct within the same active form.
    const data = new FormData();
    data.set('evolution_csrf', form.querySelector('[name="evolution_csrf"]').value);
    clear();
    if (navigator.sendBeacon) navigator.sendBeacon(form.dataset.enrollmentCancel, data);
    else fetch(form.dataset.enrollmentCancel, {method:'POST',body:data,credentials:'same-origin',keepalive:true}).catch(() => {});
  });
})();
