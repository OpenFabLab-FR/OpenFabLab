/* Progressive enhancement only: one form, no duplicated/disabled inputs. */
document.addEventListener('DOMContentLoaded', () => {
  const catalogue = document.getElementById('catalogue-location');
  if (catalogue) {
    catalogue.classList.add('rental-enhanced');
    const money = new Intl.NumberFormat('fr-FR', {style: 'currency', currency: 'EUR'});
    catalogue.querySelectorAll('[data-rental-machine]').forEach(machine => {
      const button = machine.querySelector('.rental-toggle');
      const editor = machine.querySelector('.rental-edit-row');
      const open = value => {
        editor.classList.toggle('is-open', value);
        button.setAttribute('aria-expanded', String(value));
        button.querySelector('.rental-toggle-label').textContent = value ? 'Replier ⌃' : 'Modifier ⌄';
      };
      button.addEventListener('click', () => open(button.getAttribute('aria-expanded') !== 'true'));
      machine.addEventListener('invalid', () => open(true), true);
      const update = () => {
        machine.querySelector('[data-rental-name]').textContent = machine.querySelector('[name^=machine_name_]').value || 'Machine sans nom';
        machine.querySelector('[data-rental-state]').textContent = machine.querySelector('[type=checkbox]').checked ? 'Active' : 'Inactive';
        const monthly = machine.querySelector('[name^=machine_monthly_]').valueAsNumber;
        const deposit = machine.querySelector('[name^=machine_deposit_]').valueAsNumber;
        machine.querySelector('[data-rental-amounts]').textContent = `${Number.isFinite(monthly) ? money.format(monthly) : '—'}/mois · caution ${Number.isFinite(deposit) ? money.format(deposit) : '—'}`;
      };
      machine.addEventListener('input', update); machine.addEventListener('change', update);
      update();
    });
  }
  // Links into a collapsed panel (notably #smtp) must reveal their target.
  const reveal = () => {
    const target = document.getElementById(location.hash.slice(1));
    if (target) {
      for (let parent = target; parent; parent = parent.parentElement) {
        if (parent.tagName === 'DETAILS') parent.open = true;
      }
      target.scrollIntoView({block: 'start'});
    }
  };
  if (location.hash) reveal();
  window.addEventListener('hashchange', reveal);
});
