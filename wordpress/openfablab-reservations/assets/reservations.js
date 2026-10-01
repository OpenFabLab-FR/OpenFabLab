(function () {
  'use strict';
  const endpoint = window.OpenFabLabReservations && window.OpenFabLabReservations.api;
  if (!endpoint) return;

  function element(tag, className, content) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (content !== undefined) node.textContent = content;
    return node;
  }

  function request(route, options) {
    return fetch(endpoint + route, Object.assign({ credentials: 'omit', cache: 'no-store' }, options || {}))
      .then(async response => {
        const body = await response.json();
        if (!response.ok) throw new Error(body.message || 'La demande n’a pas abouti.');
        return body;
      });
  }

  function field(name, title, type, required) {
    const label = element('label', 'openfablab-field');
    label.appendChild(element('span', '', title + (required ? ' *' : '')));
    const input = element('input');
    input.name = name;
    input.type = type || 'text';
    input.required = !!required;
    if (name === 'birth_year') {
      input.min = '1900';
      input.max = String(new Date().getFullYear());
      input.inputMode = 'numeric';
    }
    if (name === 'public_id') {
      input.pattern = '[0-9]{4}';
      input.maxLength = 4;
      input.inputMode = 'numeric';
    }
    if (name === 'phone') input.autocomplete = 'tel';
    if (name === 'email') input.autocomplete = 'email';
    if (name === 'first_name') input.autocomplete = 'given-name';
    if (name === 'last_name') input.autocomplete = 'family-name';
    label.appendChild(input);
    return label;
  }

  function formatDate(value, timezone) {
    return new Intl.DateTimeFormat('fr-FR', {
      dateStyle: 'full', timeStyle: 'short', timeZone: timezone || 'Europe/Paris'
    }).format(new Date(value));
  }

  function animationYear(animation) {
    return Number(new Intl.DateTimeFormat('en-GB', {
      year: 'numeric', timeZone: animation.timezone || 'Europe/Paris'
    }).format(new Date(animation.starts_at)));
  }

  function init(root) {
    const environment = root.dataset.environment;
    const list = root.querySelector('.openfablab-animation-list');
    const status = root.querySelector('.openfablab-status');
    const formHost = root.querySelector('.openfablab-form-host');
    let animations = [];

    async function refresh() {
      status.textContent = 'Chargement des animations…';
      try {
        const result = await request('animations?environment=' + encodeURIComponent(environment));
        animations = result.animations || [];
        list.replaceChildren();
        status.textContent = animations.length ? '' : 'Aucune animation ouverte à la réservation pour le moment.';
        animations.forEach(animation => {
          const card = element('article', 'openfablab-card');
          card.appendChild(element('h3', '', animation.title));
          card.appendChild(element('p', 'openfablab-date', formatDate(animation.starts_at, animation.timezone)));
          if (animation.description) card.appendChild(element('p', '', animation.description.replace(/<[^>]*>/g, '')));
          const duration = Math.round((new Date(animation.ends_at) - new Date(animation.starts_at)) / 60000);
          const audience = animation.audience === 'registered' ? 'Usagers enregistrés uniquement' : 'Ouverte à tous';
          card.appendChild(element('p', 'openfablab-facts',
            duration + ' min · dès ' + animation.minimum_age + ' ans · ' + audience));
          const availability = animation.available > 0
            ? animation.available + ' place' + (animation.available > 1 ? 's' : '') + ' disponible' + (animation.available > 1 ? 's' : '')
            : (animation.waitlist_enabled ? 'Complet · liste d’attente ouverte' : 'Complet');
          card.appendChild(element('p', 'openfablab-availability', availability));
          const button = element('button', 'openfablab-button', 'Réserver');
          button.type = 'button';
          button.disabled = !animation.registration_open || (!animation.available && !animation.waitlist_enabled);
          button.addEventListener('click', () => showForm(animation));
          card.appendChild(button);
          list.appendChild(card);
        });
      } catch (error) { status.textContent = error.message; }
    }

    function showForm(animation) {
      formHost.replaceChildren();
      const form = element('form', 'openfablab-booking-form');
      form.noValidate = false;
      form.appendChild(element('h3', '', 'Réserver : ' + animation.title));
      const info = element('p', 'openfablab-form-info',
        animation.audience === 'registered'
          ? 'Cette animation est réservée aux usagers enregistrés du FabLab.'
          : 'Réservation conseillée avec votre identifiant usager, mais possibilité de réserver sans cela');
      form.appendChild(info);
      let slotSelect = null;
      if (animation.booking_mode === 'slots') {
        const label = element('label', 'openfablab-field openfablab-slot-choice');
        label.appendChild(element('span', '', 'Choisissez votre créneau *'));
        slotSelect = element('select'); slotSelect.name = 'slot_uuid'; slotSelect.required = true;
        const placeholder = element('option', '', 'Choisir un créneau'); placeholder.value = '';
        slotSelect.appendChild(placeholder);
        const clock = value => new Intl.DateTimeFormat('fr-FR', {hour:'2-digit', minute:'2-digit', timeZone:animation.timezone}).format(new Date(value));
        (animation.slots || []).forEach(slot => {
          const state = !slot.registration_open ? 'Inscriptions closes' : slot.available > 0
            ? slot.available + ' place' + (slot.available > 1 ? 's' : '') + ' restante' + (slot.available > 1 ? 's' : '')
            : animation.waitlist_enabled ? 'Complet · liste d’attente' : 'Complet';
          const option = element('option', '', clock(slot.starts_at) + '–' + clock(slot.ends_at) + ' · ' + state);
          option.value = slot.slot_uuid;
          option.disabled = !slot.registration_open || (!slot.available && !animation.waitlist_enabled);
          slotSelect.appendChild(option);
        });
        label.appendChild(slotSelect); form.appendChild(label);
      }
      const choice = element('fieldset', 'openfablab-choice');
      choice.appendChild(element('legend', '', 'Votre situation'));
      for (const [value, labelText] of [['registered', 'Je suis déjà usager du FabLab'], ['visitor', 'Je n’ai pas encore de compte usager']]) {
        if (animation.audience === 'registered' && value === 'visitor') continue;
        const label = element('label');
        const radio = element('input'); radio.type = 'radio'; radio.name = 'user_kind'; radio.value = value;
        radio.checked = value === 'registered' || animation.audience !== 'registered' && value === 'visitor';
        label.appendChild(radio); label.appendChild(document.createTextNode(' ' + labelText)); choice.appendChild(label);
      }
      form.appendChild(choice);
      const fields = element('div', 'openfablab-fields');
      const idLabel = field('public_id', 'Identifiant à quatre chiffres', 'text', false);
      const scan = element('button', 'openfablab-secondary', 'Scanner mon QR code');
      scan.type = 'button';
      const scanner = element('div', 'openfablab-scanner');
      scanner.hidden = true;
      scan.addEventListener('click', () => scanQR(idLabel.querySelector('input'), scanner, scan));
      const idBlock = element('div', 'openfablab-id-block');
      idBlock.appendChild(idLabel); idBlock.appendChild(scan); idBlock.appendChild(scanner);
      fields.appendChild(idBlock);
      const emailField = field('email', 'E-mail de contact', 'email', true);
      const phoneField = field('phone', 'Téléphone de contact', 'tel', true);
      fields.appendChild(emailField);
      fields.appendChild(phoneField);
      const verify = element('button', 'openfablab-secondary', 'Vérifier mon compte');
      verify.type = 'button';
      const verification = element('p', 'openfablab-verification');
      verification.setAttribute('role', 'status');
      const prefillNotice = element('p', 'openfablab-hint');
      let verificationToken = '';
      let verifiedId = '';
      let verificationRevision = 0;
      const injected = new Map();
      fields.appendChild(verify); fields.appendChild(verification); fields.appendChild(prefillNotice);
      fields.appendChild(field('first_name', 'Prénom', 'text', true));
      fields.appendChild(field('last_name', 'Nom', 'text', true));
      const birth = field('birth_year', 'Année de naissance', 'number', true);
      fields.appendChild(birth);
      const birthHint = element('p', 'openfablab-hint',
        'Si l’année de votre fiche usager est erronée, vous pouvez la corriger pour cette réservation ; votre fiche ne sera pas modifiée.');
      fields.appendChild(birthHint);
      const companionBlock = element('fieldset', 'openfablab-companion');
      companionBlock.appendChild(element('legend', '', 'Accompagnateur (une deuxième place)'));
      companionBlock.appendChild(field('companion_first_name', 'Prénom de l’accompagnateur', 'text', true));
      companionBlock.appendChild(field('companion_last_name', 'Nom de l’accompagnateur', 'text', true));
      companionBlock.appendChild(field('companion_birth_year', 'Année de naissance de l’accompagnateur', 'number', true));
      companionBlock.appendChild(field('companion_email', 'E-mail de l’accompagnateur', 'email', true));
      companionBlock.appendChild(field('companion_phone', 'Téléphone de l’accompagnateur', 'tel', true));
      companionBlock.appendChild(field('companion_public_id', 'Identifiant usager de l’accompagnateur, si connu', 'text', false));
      fields.appendChild(companionBlock);
      const honeypot = field('website', 'Laisser vide', 'text', false);
      honeypot.classList.add('openfablab-honeypot'); honeypot.setAttribute('aria-hidden', 'true');
      honeypot.querySelector('input').tabIndex = -1;
      fields.appendChild(honeypot);
      const privacyNotice = element('p', 'openfablab-privacy',
        'Les informations demandées sont utilisées pour gérer votre réservation ou vous contacter à ce sujet.');
      if (window.OpenFabLabReservations.privacy) {
        const privacyLink = element('a', '', 'En savoir plus sur la gestion de vos données');
        privacyLink.href = window.OpenFabLabReservations.privacy;
        privacyLink.target = '_blank'; privacyLink.rel = 'noopener';
        privacyNotice.appendChild(document.createTextNode(' '));
        privacyNotice.appendChild(privacyLink);
      }
      fields.appendChild(privacyNotice);
      form.appendChild(fields);
      const actions = element('div', 'openfablab-actions');
      const submit = element('button', 'openfablab-button', 'Confirmer la réservation'); submit.type = 'submit';
      const close = element('button', 'openfablab-secondary', 'Fermer'); close.type = 'button';
      close.addEventListener('click', () => formHost.replaceChildren());
      actions.appendChild(submit); actions.appendChild(close); form.appendChild(actions);
      const feedback = element('p', 'openfablab-feedback'); feedback.setAttribute('role', 'alert');
      form.appendChild(feedback);
      formHost.appendChild(form);
      form.scrollIntoView({ behavior: 'smooth', block: 'start' });

      function updateChoice() {
        const registered = form.querySelector('[name="user_kind"]:checked').value === 'registered';
        idBlock.hidden = !registered;
        idLabel.querySelector('input').required = registered;
        verify.hidden = !registered;
        verification.hidden = !registered;
        birthHint.hidden = !registered;
        // The server fills this from a verified account, otherwise a declaration is necessary.
        birth.querySelector('input').required = true;
        verification.textContent = '';
        prefillNotice.textContent = '';
        verificationToken = ''; verifiedId = ''; verificationRevision++;
        // Returning to Visitor removes only untouched automatically injected values.
        if (!registered) {
          injected.forEach((value, name) => {
            const input = form.querySelector('[name="' + name + '"]');
            if (input.value === value) input.value = '';
          });
          injected.clear();
        }
        if (!registered) idLabel.querySelector('input').value = '';
      }
      choice.addEventListener('change', updateChoice);
      updateChoice();
      for (const input of [idLabel, emailField, phoneField].map(label => label.querySelector('input'))) {
        input.addEventListener('input', () => {
          verificationRevision++;
          if (input.name === 'public_id') {
            verificationToken = ''; verifiedId = '';
            verification.textContent = ''; prefillNotice.textContent = '';
          }
        });
      }

      function updateCompanion() {
        const year = Number(birth.querySelector('input').value);
        const age = animationYear(animation) - year;
        const required = year > 1900 && age < animation.accompaniment_under_age;
        const minor = year > 1900 && age < 18;
        emailField.querySelector('span').textContent = (minor ? 'E-mail de contact / responsable légal' : 'E-mail de contact') + ' *';
        phoneField.querySelector('span').textContent = (minor ? 'Téléphone de contact / responsable légal' : 'Téléphone de contact') + ' *';
        companionBlock.hidden = !required;
        companionBlock.querySelectorAll('input').forEach(input => {
          if (input.name !== 'companion_public_id') input.required = required;
        });
      }
      birth.querySelector('input').addEventListener('input', updateCompanion);
      updateCompanion();
      verify.addEventListener('click', async () => {
        const get = key => form.querySelector('[name="' + key + '"]').value.trim();
        const idInput = idLabel.querySelector('input');
        if (!idInput.reportValidity()) return;
        if (!get('email') && !get('phone')) {
          verification.textContent = 'Renseignez votre e-mail ou votre téléphone pour vérifier votre compte.';
          emailField.querySelector('input').focus();
          return;
        }
        if (get('email') && !emailField.querySelector('input').checkValidity()) {
          emailField.querySelector('input').reportValidity();
          return;
        }
        verification.textContent = 'Vérification…';
        prefillNotice.textContent = '';
        verificationToken = ''; verifiedId = '';
        const revision = ++verificationRevision;
        const checkedId = get('public_id');
        try {
          const result = await request('verify', { method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ environment, public_id: get('public_id'), email: get('email'), phone: get('phone') }) });
          if (revision !== verificationRevision || !form.isConnected) return;
          if (result.status === 'matched') {
            verification.textContent = 'Compte reconnu : ' + result.masked_identity;
            prefillNotice.textContent = 'Vos informations peuvent maintenant être préremplies. Elles restent modifiables pour cette réservation.';
            verificationToken = result.verification_token || ''; verifiedId = checkedId;
            for (const name of ['first_name', 'last_name', 'birth_year', 'email', 'phone']) {
              const input = form.querySelector('[name="' + name + '"]');
              input.value = result[name] == null ? '' : String(result[name]);
              injected.set(name, input.value);
            }
            updateCompanion();
          } else {
            verification.textContent = 'Compte non reconnu. Vérifiez votre identifiant et vos coordonnées.';
          }
        } catch (error) {
          if (revision === verificationRevision) verification.textContent = error.message;
        }
      });

      form.addEventListener('submit', async event => {
        event.preventDefault();
        if (!form.reportValidity()) return;
        submit.disabled = true;
        feedback.textContent = 'Enregistrement en cours…';
        const get = key => form.querySelector('[name="' + key + '"]').value.trim();
        const payload = {
          environment, service_id: animation.service_id,
          first_name: get('first_name'), last_name: get('last_name'), birth_year: get('birth_year'),
          email: get('email'), phone: get('phone'), public_id: get('public_id'),
          verification_token: verifiedId === get('public_id') ? verificationToken : '',
          website: get('website')
        };
        if (slotSelect) payload.slot_uuid = slotSelect.value;
        if (!companionBlock.hidden) payload.companion = {
          first_name: get('companion_first_name'), last_name: get('companion_last_name'),
          birth_year: get('companion_birth_year'), email: get('companion_email'),
          phone: get('companion_phone'), public_id: get('companion_public_id')
        };
        try {
          const result = await request('reserve', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload) });
          feedback.textContent = result.message;
          verificationToken = ''; verifiedId = ''; verificationRevision++;
          verification.textContent = ''; prefillNotice.textContent = ''; injected.clear();
          form.querySelectorAll('input').forEach(input => { if (input.type !== 'radio') input.value = ''; });
          await refresh();
        } catch (error) { feedback.textContent = error.message; }
        submit.disabled = false;
      });
    }

    async function scanQR(input, host, button) {
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia || !window.jsQR) {
        host.textContent = 'Caméra indisponible. Saisissez les quatre chiffres manuellement.';
        host.hidden = false;
        return;
      }
      button.disabled = true;
      host.hidden = false;
      host.replaceChildren();
      const video = element('video'); video.setAttribute('playsinline', ''); video.muted = true;
      host.appendChild(video);
      const stop = element('button', 'openfablab-secondary', 'Fermer la caméra'); stop.type = 'button';
      host.appendChild(stop);
      let stream;
      let active = true;
      const close = () => {
        active = false;
        if (stream) stream.getTracks().forEach(track => track.stop());
        host.hidden = true;
        button.disabled = false;
      };
      stop.addEventListener('click', close);
      try {
        stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' }, audio: false });
        video.srcObject = stream;
        await video.play();
        const canvas = document.createElement('canvas');
        const context = canvas.getContext('2d', { willReadFrequently: true });
        const frame = () => {
          if (!active) return;
          if (video.readyState >= 2) {
            canvas.width = video.videoWidth; canvas.height = video.videoHeight;
            context.drawImage(video, 0, 0);
            const pixels = context.getImageData(0, 0, canvas.width, canvas.height);
            const result = window.jsQR(pixels.data, canvas.width, canvas.height);
            if (result && /^[0-9]{4}$/.test(result.data.trim())) {
              input.value = result.data.trim();
              close();
              return;
            }
          }
          requestAnimationFrame(frame);
        };
        requestAnimationFrame(frame);
      } catch (error) {
        close();
        host.hidden = false;
        host.textContent = 'Caméra indisponible. Saisissez les quatre chiffres manuellement.';
      }
    }
    refresh();
  }

  document.querySelectorAll('.openfablab-reservations').forEach(init);
}());
