/* Administrative dashboard only: fit whole entries, then disclose history. */
(() => {
  'use strict';
  const columns = document.querySelector('[data-overview-columns]');
  if (columns) {
    const stack = columns.querySelector('[data-overview-stack]');
    const upcoming = columns.querySelector('[data-overview-upcoming]');
    const extra = Array.from(upcoming.querySelectorAll('[data-overview-extra]'));
    if (extra.length) {
      let frame = 0;
      const show = (count) => {
        extra.forEach((entry, index) => {
          if (index >= count && entry.contains(document.activeElement)) {
            upcoming.querySelector('.overview-calendar-link a').focus({preventScroll: true});
          }
          entry.hidden = index >= count;
        });
      };
      const balance = () => {
        frame = 0;
        const left = stack.getBoundingClientRect();
        const right = upcoming.getBoundingClientRect();
        // In the stacked layout, the right panel starts below the left one.
        if (Math.abs(left.top - right.top) > 1 || right.height === 0) {
          show(0);
          return;
        }
        // Batch measurements and restore the chosen visibility in this same
        // frame. Observing the left stack only avoids a feedback loop.
        extra.forEach((entry) => { entry.hidden = false; });
        const heights = extra.map((entry) => entry.getBoundingClientRect().height);
        let spare = left.height - upcoming.getBoundingClientRect().height
          + heights.reduce((sum, height) => sum + height, 0);
        let count = 0;
        while (count < heights.length && heights[count] <= spare + 1) {
          spare -= heights[count];
          count += 1;
        }
        show(count);
      };
      const schedule = () => {
        if (!frame) frame = requestAnimationFrame(balance);
      };
      if ('ResizeObserver' in window) new ResizeObserver(schedule).observe(stack);
      window.addEventListener('resize', schedule, {passive: true});
      document.fonts?.ready.then(schedule);
      balance();
    }
  }
  const toggle = document.querySelector('[data-overview-identifications-toggle]');
  const more = document.querySelector('[data-overview-identifications]');
  if (toggle && more) {
    toggle.hidden = false;
    toggle.addEventListener('click', () => {
      const expanded = more.hidden;
      more.hidden = !expanded;
      toggle.setAttribute('aria-expanded', String(expanded));
      toggle.textContent = expanded ? toggle.dataset.less : toggle.dataset.more;
    });
  }
})();
