'use strict';
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
