/* Browser-local voices only. Attendance never waits for speech. */
(() => {
  'use strict';
  const node = document.getElementById('kiosk-audio');
  if (!node) return;
  const options = JSON.parse(node.textContent).voice || {};
  const engine = window.speechSynthesis;
  const available = !!(engine && typeof engine.getVoices === 'function' && window.SpeechSynthesisUtterance);
  const key = 'ofl:kiosk-voice';
  const lang = () => document.documentElement.lang.toLowerCase().split('-')[0];
  const translate = text => window.OFLTranslate?.(text) || text;
  const phrases = {
    fr: ['Bienvenue', 'Au revoir'], en: ['Welcome', 'Goodbye'], de: ['Willkommen', 'Auf Wiedersehen'],
    es: ['¡Bienvenido', '¡Hasta pronto'], fi: ['Tervetuloa', 'Näkemiin'],
  };
  const voices = () => available ? engine.getVoices().filter(v => v.localService === true) : [];

  function speak(event, first, choice, volume) {
    if (!available || !(Number(volume) > 0) || !['arrival','departure','visitor'].includes(event)) return false;
    const code = lang();
    const matches = voices().filter(v => v.lang.toLowerCase().split('-')[0] === code);
    const voice = matches.find(v => v.voiceURI === choice) || matches.find(v => v.default) || matches[0];
    if (!voice) return false;
    try {
      const text = (phrases[code] || phrases.fr)[event === 'departure' ? 1 : 0];
      const suffix = event !== 'visitor' && typeof first === 'string' && first ? ', ' + first.slice(0,80) : '';
      const message = new SpeechSynthesisUtterance(text + suffix + (code === 'es' ? '!' : ' !'));
      message.voice = voice;
      message.lang = voice.lang;
      message.volume = Math.min(1, Number(volume) / 100);
      engine.cancel();
      engine.speak(message);
      return true;
    } catch (_) { return false; }
  }

  window.OFLVoice = {available, handoff(receipt, target) {
    if (!options.enabled || !available || !['arrival','departure','visitor'].includes(receipt.event)) return;
    try {
      sessionStorage.setItem(key, JSON.stringify({
        event: receipt.event, first: receipt.event === 'visitor' ? '' : receipt.first,
        target: target.pathname, time: Date.now(),
      }));
    } catch (_) { speak(receipt.event, receipt.first, options.name, options.volume); }
  }};
  try {
    const item = sessionStorage.getItem(key);
    sessionStorage.removeItem(key);
    const pending = item && JSON.parse(item);
    if (options.enabled && pending && pending.target === location.pathname && Date.now() - pending.time < 6500) {
      if (!speak(pending.event, pending.first, options.name, options.volume) && available) {
        let waiting = true;
        engine.addEventListener('voiceschanged', () => {
          if (waiting && Date.now() - pending.time < 6500) speak(pending.event, pending.first, options.name, options.volume);
        }, {once: true});
        setTimeout(() => {waiting = false; pending.first = '';}, 6500);
      }
    }
  } catch (_) { /* Unavailable storage must not affect the kiosk. */ }

  const select = document.querySelector('[name="kiosk_voice_name"]');
  if (!select) return;
  const status = document.querySelector('[data-voice-status]');
  const refresh = () => {
    const chosen = select.dataset.voiceLoaded ? select.value : select.dataset.savedVoice;
    select.dataset.voiceLoaded = '1';
    select.replaceChildren(new Option(translate('Automatique'), ''));
    for (const voice of voices()) select.add(new Option(voice.name + ' (' + voice.lang + ')', voice.voiceURI));
    if (chosen && !Array.from(select.options).some(o => o.value === chosen)) {
      select.add(new Option(translate('Voix enregistrée indisponible'), chosen));
    }
    select.value = chosen || '';
  };
  refresh();
  if (available) engine.addEventListener('voiceschanged', refresh);
  document.querySelector('[data-voice-test]')?.addEventListener('click', () => {
    const volume = document.querySelector('[name="kiosk_voice_volume"]').value;
    status.textContent = translate(speak('visitor', '', select.value, volume)
      ? 'Test vocal demandé. Vérifiez le volume de l’appareil.'
      : 'Aucune voix locale compatible ou volume nul.');
  });
})();
