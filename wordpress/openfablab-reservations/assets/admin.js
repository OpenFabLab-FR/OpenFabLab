(() => {
  'use strict';
  document.querySelectorAll('.ofl-admin [data-openfablab-copy]').forEach(button => {
    button.addEventListener('click', async () => {
      const input = document.getElementById(button.dataset.openfablabCopy);
      const status = document.getElementById('openfablab-copy-status');
      if (!input || !status) return;
      try {
        if (!navigator.clipboard) throw new Error('clipboard unavailable');
        await navigator.clipboard.writeText(input.value);
        status.textContent = status.dataset.copied;
      } catch (_) {
        input.focus(); input.select();
        status.textContent = status.dataset.selected;
      }
    });
  });
})();
