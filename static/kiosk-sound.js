/* Synthesized locally, no microphone, media file, external transport or telemetry. */
(() => {
  'use strict';
  const configNode = document.getElementById('kiosk-audio');
  if (!configNode) return;
  const config = JSON.parse(configNode.textContent);
  const pathOf = url => {
    const parsed = new URL(url, location.href);
    if (parsed.origin !== location.origin || !parsed.pathname.startsWith(config.base || '')) return '';
    return parsed.pathname.slice((config.base || '').length) || '/';
  };
  let context = null;
  const Audio = window.AudioContext || window.webkitAudioContext;
  const notes = {
    navigation: [[430, 0, .035]], management: [[390, 0, .04], [510, .035, .04]],
    arrival: [[440, 0, .055], [660, .055, .075]],
    departure: [[560, 0, .06], [370, .055, .08]],
    visitor: [[520, 0, .045], [650, .045, .065]],
    error: [[280, 0, .085]], warning: [[330, 0, .055], [310, .07, .055]]
  };
  function unlock() {
    if (!Audio || !config.enabled) return;
    try {
      if (!context) context = new Audio();
      if (context.state === 'suspended') context.resume().catch(() => {});
    } catch (_) { /* The kiosk always remains usable. */ }
  }
  function play(action, test = false) {
    if (!notes[action] || (!config.enabled && !test) || !Audio) return false;
    let volume = config.volume / 100, ambience = config.ambience;
    if (test) {
      volume = Number(document.querySelector('[name="kiosk_sound_volume"]').value) / 100;
      const value = document.querySelector('[name="kiosk_sound_ambience"]').value;
      ambience = value === 'auto' ? config.ambience : value;
    }
    if (!volume) return false;
    try {
      if (!context && test) context = new Audio(); // Test click is a real gesture.
      if (!context) return false;
      if (context.state === 'suspended') { context.resume().then(() => tone()).catch(() => {}); }
      else tone();
      function tone() {
        if (context.state !== 'running') return;
        const shift = ambience === 'halloween' ? .78 : ambience === 'christmas' ? 1.15 : 1;
        for (const [frequency, offset, duration] of notes[action]) {
          const oscillator = context.createOscillator(), gain = context.createGain();
          const start = context.currentTime + offset;
          oscillator.type = 'sine'; oscillator.frequency.setValueAtTime(frequency * shift, start);
          if (ambience === 'halloween') oscillator.frequency.exponentialRampToValueAtTime(frequency * shift * .94, start + duration);
          gain.gain.setValueAtTime(0, start); gain.gain.linearRampToValueAtTime(volume * .13, start + .008);
          gain.gain.exponentialRampToValueAtTime(.0001, start + duration);
          oscillator.connect(gain); gain.connect(context.destination);
          oscillator.start(start); oscillator.stop(start + duration + .01);
          oscillator.onended = () => { oscillator.disconnect(); gain.disconnect(); };
        }
      }
      return true;
    } catch (_) { return false; }
  }
  document.querySelectorAll('[data-sound-test]').forEach(button => button.addEventListener('click', () => {
    const okay = play(button.dataset.soundTest, true);
    const status = document.getElementById('sound-test-status');
    if (status) status.textContent = okay ? 'Test demandé. Si aucun son n’est audible, vérifiez le volume de l’appareil.' : 'Son indisponible ou volume nul. La borne reste utilisable.';
  }));
  if (!config.enabled) return; // No context, listeners, fetch or sound engine when off.
  document.addEventListener('pointerdown', unlock, {capture: true});
  document.addEventListener('keydown', unlock, {capture: true});
  document.addEventListener('click', event => {
    const link = event.target.closest('a');
    if (!link) return;
    const path = pathOf(link.href);
    if (path === '/identification') play('navigation');
    else if (path === '/admin' || path === '/admin/connexion' || path === '/gestion') play('management');
  });
  const pending = new WeakSet();
  const matches = form => form.method.toLowerCase() === 'post' && /^\/(identification|visiteurs|usagers\/\d+\/(presence|depart-rapide))$/.test(pathOf(form.action));
  async function submit(form) {
    if (!matches(form) || !Audio) { HTMLFormElement.prototype.submit.call(form); return; }
    if (pending.has(form)) return;
    pending.add(form); unlock();
    const data = new FormData(form); data.set('kiosk_action', config.token);
    if (pathOf(form.action) === '/visiteurs') play('navigation');
    try {
      const response = await fetch(form.action, {method: 'POST', body: data, headers: {'X-OFL-Kiosk': '1'}, credentials: 'same-origin'});
      if (!response.ok) throw new Error('Action non confirmée');
      const result = await response.json();
      const target = new URL(result.location, location.origin);
      if (target.origin !== location.origin) throw new Error('Destination incorrecte');
      if (result.event) play(result.event);
      // No timer and no audio wait: navigation and attendance never wait on sound.
      location.assign(target.href);
    } catch (_) {
      play('error');
      let status = document.getElementById('kiosk-action-status');
      if (!status) { status = document.createElement('p'); status.id = 'kiosk-action-status'; status.setAttribute('role', 'alert'); form.after(status); }
      status.textContent = 'Confirmation indisponible. Réessayez cette action ou actualisez la page. Aucun son de réussite n’a été joué.';
      pending.delete(form); delete form.dataset.submitting;
      form.querySelectorAll('button').forEach(button => { button.disabled = false; });
    }
  }
  window.OFLKiosk = {submit};
  document.addEventListener('submit', event => {
    if (matches(event.target) && Audio) { event.preventDefault(); submit(event.target); }
  }, {capture: true});
  window.addEventListener('pagehide', () => { if (context) context.close().catch(() => {}); });
})();
