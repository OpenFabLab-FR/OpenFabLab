(function () {
  'use strict';
  const config = window.OpenFabLabReservations;
  if (!config || !config.api) return;
  function node(tag, className, text) {
    const value = document.createElement(tag);
    if (className) value.className = className;
    if (text !== undefined) value.textContent = text;
    return value;
  }
  const csrf = new Map();
  const active = new Map();
  function randomKey() {return Array.from(crypto.getRandomValues(new Uint8Array(24)), byte => byte.toString(16).padStart(2, '0')).join('');}
  async function request(route, body) {
    if (body && !csrf.has(body.environment)) {
      const session = await request('session?environment=' + encodeURIComponent(body.environment));
      csrf.set(body.environment, session.csrf);
    }
    const response = await fetch(config.api + route, body ? {
      method: 'POST', credentials: 'same-origin', cache: 'no-store',
      headers: {'Content-Type': 'application/json', 'X-OpenFabLab-CSRF': csrf.get(body.environment)}, body: JSON.stringify(body)
    } : {credentials: 'same-origin', cache: 'no-store'});
    const value = await response.json();
    if (!response.ok) throw new Error(response.status === 404 && route === 'status' ? 'Cette demande n’a pas été transmise ou son suivi a expiré. Identifiez-vous à nouveau.' : (value.message || 'La demande n’a pas abouti.'));
    return value;
  }
  const storageKey = env => 'ofl-pending-v4-' + env;
  function remember(value) {try {sessionStorage.setItem(storageKey(value.environment), JSON.stringify(value));} catch (_) {}}
  function forget(env) {try {sessionStorage.removeItem(storageKey(env));} catch (_) {}}
  async function awaitResult(pending) {
    const started = Date.now();
    while (Date.now() - started < 600000) {
      const status = await request('status', {environment: pending.environment, request_key: pending.key});
      if (status.state === 'expired') {forget(pending.environment);throw new Error(status.message);}
      if (status.state === 'done') {
        forget(pending.environment);
        if (!status.result.ok) throw new Error(status.result.message || 'La demande n’a pas pu être confirmée.');
        return status.result.value;
      }
      await new Promise(resolve => setTimeout(resolve, 2500));
    }
    throw new Error('Votre demande est toujours en cours. Vous pouvez actualiser cette page pour reprendre son suivi.');
  }
  async function call(route, body) {
    if (!body) return request(route);
    const key = body.request_key || randomKey();
    const pending = {environment: body.environment, route, key, animation: active.get(body.environment), until: Date.now() + 1200000};
    // No contacts, participant names or link tokens in the reload record.
    remember(pending);
    try {await request(route, {...body, request_key: key});}
    catch (error) {if (!(error instanceof TypeError)) {forget(body.environment);throw error;}}
    return awaitResult(pending);
  }
  function field(name, label, type) {
    const wrapper = node('label', 'openfablab-field');
    wrapper.appendChild(node('span', '', label));
    const input = node('input'); input.name = name; input.type = type || 'text';
    input.required = true; input.maxLength = name === 'public_id' ? 4 : 254;
    if (name === 'public_id') {input.pattern = '[0-9]{4}'; input.inputMode = 'numeric';}
    wrapper.appendChild(input); return wrapper;
  }
  function init(root) {
    const environment = root.dataset.environment;
    const list = root.querySelector('.openfablab-animation-list');
    const host = root.querySelector('.openfablab-form-host');
    const status = root.querySelector('.openfablab-status');
    let scanner;
    async function refresh() {
      try {
        const result = await call('animations?environment=' + encodeURIComponent(environment));
        list.replaceChildren();
        status.textContent = result.animations.length ? '' : 'Aucune animation ouverte à la réservation.';
        result.animations.forEach(animation => {
          const card = node('article', 'openfablab-card');
          card.dataset.serviceId = String(animation.service_id);
          card.appendChild(node('h3', '', animation.title));
          card.appendChild(node('p', 'openfablab-date', animation.date + ' · ' + animation.hours));
          card.appendChild(node('p', '', animation.description || ''));
          card.appendChild(node('p', 'openfablab-availability', animation.available + ' place(s) disponible(s)' + (animation.waitlist_enabled ? ' · liste d’attente autorisée' : '')));
          const button = node('button', 'openfablab-button openfablab-reserve-button', 'Réserver'); button.type = 'button';
          button.addEventListener('click', () => choose(animation));
          card.appendChild(button); list.appendChild(card);
        });
        markSelection();
      } catch (error) {status.textContent = error.message;}
    }
    function form(title) {
      if (scanner) {scanner.destroy();scanner = null;}
      host.replaceChildren();
      const value = node('form', 'openfablab-booking-form');
      const animation = active.get(environment);
      if (animation) value.appendChild(node('p', 'openfablab-selected-summary', 'Réservation pour : ' + animation.title + ' · ' + animation.date + ' · ' + animation.hours));
      const heading = node('h3', '', title); heading.tabIndex = -1;
      value.appendChild(heading);
      const feedback = node('p', 'openfablab-verification'); feedback.setAttribute('role', 'status');
      value.appendChild(feedback);host.appendChild(value);heading.focus();
      return [value, feedback];
    }
    function choose(animation) {
      active.set(environment, animation);
      markSelection();
      if (animation.account_required !== false) {identify(animation);return;}
      const [value] = form('Comment souhaitez-vous réserver ?');
      const choices = node('div', 'openfablab-entry-choices');
      for (const [title, help, action] of [
        ['J’ai un compte OpenFabLab', 'Retrouvez votre fiche et vos éventuels liens familiaux.', () => identify(animation)],
        ['Réserver sans compte', 'Réservez simplement pour vous avec vos coordonnées.', () => guest(animation)]
      ]) {
        const card = node('div', 'openfablab-entry-card');
        const button = node('button', 'openfablab-button', title);button.type = 'button';button.addEventListener('click', action);
        card.appendChild(button);card.appendChild(node('p', '', help));choices.appendChild(card);
      }
      value.appendChild(choices);
    }
    function markSelection() {
      const selected = active.get(environment);
      list.querySelectorAll('.openfablab-card').forEach(card => {
        const chosen = !!selected && card.dataset.serviceId === String(selected.service_id);
        card.classList.toggle('is-selected', chosen);
        card.querySelector('button').setAttribute('aria-pressed', String(chosen));
      });
    }
    function guest(animation, previous = {}) {
      const [value, feedback] = form('Réserver sans compte');
      value.appendChild(node('p', '', 'Une place pour vous, sans création de compte. Une personne non autonome réserve avec son responsable depuis le parcours avec compte.'));
      const fields = node('div', 'openfablab-guest-fields');
      for (const [name, label, type] of [['first_name','Prénom','text'],['last_name','Nom','text'],['birth_date','Date de naissance','date'],['email','E-mail','email'],['phone',animation.phone_required ? 'Téléphone (obligatoire)' : 'Téléphone (facultatif)','tel']]) {
        const wrapper = field(name,label,type), input = wrapper.querySelector('input');input.value = previous[name] || '';
        input.maxLength = ['first_name','last_name'].includes(name) ? 120 : name === 'phone' ? 40 : 254;
        if (name === 'phone') input.required = animation.phone_required === true;
        input.autocomplete = {first_name:'given-name',last_name:'family-name',birth_date:'bday',email:'email',phone:'tel'}[name];
        fields.appendChild(wrapper);
      }
      value.appendChild(fields);
      value.appendChild(node('small', '', 'La date de naissance sert uniquement à vérifier l’âge minimum et l’autonomie à la date de l’animation. Aucune fiche usager n’est créée.'));
      let slots;
      if (animation.booking_mode === 'slots') {
        const label = node('label','openfablab-field');label.appendChild(node('span','','Créneau'));
        slots = node('select');slots.required = true;slots.name = 'slot_uuid';
        const empty = node('option','','Choisir un créneau');empty.value = '';slots.appendChild(empty);
        animation.slots.forEach(slot => {const option = node('option','',slot.label);option.value = slot.slot_uuid;slots.appendChild(option);});
        slots.value = previous.slot_uuid || '';label.appendChild(slots);value.appendChild(label);
      }
      const back = node('button','openfablab-secondary','Changer de parcours');back.type = 'button';back.addEventListener('click',() => choose(animation));value.appendChild(back);
      value.appendChild(node('button','openfablab-button','Voir le récapitulatif'));
      value.addEventListener('submit', event => {
        event.preventDefault();if (!value.reportValidity()) return;
        const data = Object.fromEntries(new FormData(value));data.slot_uuid = slots ? slots.value : null;
        guestRecap(animation, data);
      });
    }
    function guestRecap(animation, data) {
      const [value, feedback] = form('Récapitulatif');
      value.appendChild(node('p','',data.first_name + ' ' + data.last_name + ' · 1 place demandée'));
      value.appendChild(node('p','','Vous recevrez la décision d’OpenFabLab par e-mail. Aucune place n’est confirmée avant cette décision.'));
      const consent = node('label','openfablab-family-person');const box = node('input');box.type = 'checkbox';box.required = true;
      consent.appendChild(box);consent.appendChild(node('span','','J’accepte l’utilisation de ces informations pour gérer la réservation.'));value.appendChild(consent);
      const back = node('button','openfablab-secondary','Modifier');back.type = 'button';back.addEventListener('click',() => guest(animation,data));value.appendChild(back);
      const submit = node('button','openfablab-button','Valider la réservation');value.appendChild(submit);
      const key = randomKey();
      value.addEventListener('submit',async event => {
        event.preventDefault();if (!value.reportValidity()) return;submit.disabled = true;back.disabled = true;feedback.textContent = 'Votre demande est transmise. Vérification en cours…';
        try {receipt(await call('guest',{...data,environment,service_id:animation.service_id,request_key:key,consent:true}));await refresh();}
        catch (error) {feedback.textContent = error.message;submit.disabled = false;back.disabled = false;}
      });
    }
    function identify(animation) {
      active.set(environment, animation);
      const [value, feedback] = form('Identifier mon compte');
      value.appendChild(node('p', '', 'Saisissez votre identifiant et une coordonnée déjà renseignée dans votre fiche. Les membres rattachés ne sont affichés qu’après cette vérification.'));
      value.appendChild(field('public_id', 'Identifiant OpenFabLab'));
      value.appendChild(field('contact', 'E-mail ou téléphone de votre fiche'));
      const id = value.querySelector('[name=public_id]'), contactInput = value.querySelector('[name=contact]');
      const methods = node('div','openfablab-identification-methods');
      const scan = node('button','openfablab-button','Scanner mon QR Code');scan.type = 'button';
      const manual = node('button','openfablab-secondary','Saisir mon identifiant');manual.type = 'button';
      const camera = node('div','openfablab-scanner');camera.hidden = true;
      if (window.OpenFabLabQR) scanner = window.OpenFabLabQR(camera,id,() => {feedback.textContent = 'QR Code reconnu. Vérifiez votre compte avec votre e-mail ou téléphone.';contactInput.focus();});
      scan.addEventListener('click',() => {if (scanner) scanner.start();else feedback.textContent = 'Scanner indisponible. Saisissez votre identifiant.';});
      manual.addEventListener('click',() => {if (scanner) scanner.stop();id.focus();});
      id.addEventListener('focus',() => {if (scanner) scanner.stop();});
      methods.appendChild(scan);methods.appendChild(manual);value.insertBefore(methods,value.querySelector('label'));value.insertBefore(camera,value.querySelector('label'));
      const button = node('button', 'openfablab-button', 'Continuer');value.appendChild(button);
      value.addEventListener('submit', async event => {
        event.preventDefault();button.disabled = true;
        if (scanner) scanner.stop();
        feedback.textContent = 'Vérification en cours…';
        try {
          const data = new FormData(value);
          const result = await call('verify', {environment, service_id: animation.service_id,
            public_id: data.get('public_id'), contact: data.get('contact')});
          if (result.contact_required) contact(animation, result);
          else select(animation, result);
        } catch (error) {feedback.textContent = error.message;button.disabled = false;}
      });
    }
    function contact(animation, identity) {
      const [value, feedback] = form('Compléter mes coordonnées');
      value.appendChild(node('p', '', 'Un e-mail valide est nécessaire pour recevoir la confirmation et les éventuelles propositions de places.'));
      value.appendChild(field('email', 'E-mail', 'email'));
      const phone = field('phone', identity.phone_required ? 'Téléphone (obligatoire)' : 'Téléphone (facultatif)', 'tel');
      phone.querySelector('input').required = identity.phone_required;
      phone.querySelector('input').maxLength = 40;value.appendChild(phone);
      const button = node('button', 'openfablab-button', 'Enregistrer et continuer');value.appendChild(button);
      value.addEventListener('submit', async event => {
        event.preventDefault();button.disabled = true;
        feedback.textContent = 'Vérification en cours…';
        try {
          const data = new FormData(value);
          const result = await call('contact', {environment, service_id: animation.service_id, token: identity.token,
            email: data.get('email'), phone: data.get('phone')});
          select(animation, result);
        } catch (error) {feedback.textContent = error.message;button.disabled = false;}
      });
    }
    function select(animation, identity, previous, previousSlot) {
      const [value, feedback] = form('Pour qui réservez-vous ?');
      value.appendChild(node('p', '', 'Une place par personne. Une personne non autonome doit participer avec un responsable rattaché à son compte.'));
      identity.participants.forEach(person => {
        const label = node('label', 'openfablab-family-person');
        const box = node('input');box.type = 'checkbox';box.name = 'participants';box.value = person.key;
        box.checked = (previous || []).includes(person.key);
        label.appendChild(box);label.appendChild(node('span', '', person.name + ' · ' + person.label));value.appendChild(label);
      });
      let slots;
      if (animation.booking_mode === 'slots') {
        const label = node('label', 'openfablab-field');label.appendChild(node('span', '', 'Créneau'));
        slots = node('select');slots.required = true;
        const empty = node('option', '', 'Choisir un créneau');empty.value = '';slots.appendChild(empty);
        animation.slots.forEach(slot => {const option = node('option', '', slot.label);option.value = slot.slot_uuid;slots.appendChild(option);});
        if (previousSlot) slots.value = previousSlot;
        label.appendChild(slots);value.appendChild(label);
      }
      const button = node('button', 'openfablab-button', 'Voir le récapitulatif');value.appendChild(button);
      value.addEventListener('submit', event => {
        event.preventDefault();
        const selected = Array.from(value.querySelectorAll('input[name="participants"]:checked')).map(box => box.value);
        if (!selected.length) {feedback.textContent = 'Sélectionnez au moins une personne.';return;}
        recap(animation, identity, selected, slots ? slots.value : null);
      });
    }
    function recap(animation, identity, selected, slot) {
      const [value, feedback] = form('Récapitulatif');
      const names = node('ul');
      identity.participants.filter(person => selected.includes(person.key)).forEach(person => names.appendChild(node('li', '', person.name)));
      value.appendChild(names);
      value.appendChild(node('p', '', selected.length + ' place(s) demandée(s). Tout le groupe sera confirmé ou mis en attente ensemble.'));
      const consent = node('label', 'openfablab-family-person');
      const checkbox = node('input');checkbox.type = 'checkbox';checkbox.required = true;
      consent.appendChild(checkbox);consent.appendChild(node('span', '', 'J’accepte l’utilisation de ces informations pour gérer la réservation.'));value.appendChild(consent);
      const back = node('button', 'openfablab-secondary', 'Modifier');back.type = 'button';back.addEventListener('click', () => select(animation, identity, selected, slot));value.appendChild(back);
      const submit = node('button', 'openfablab-button', 'Valider la réservation');value.appendChild(submit);
      // Reuse this key after timeout. A lost response must never duplicate seats.
      const requestKey = Array.from(crypto.getRandomValues(new Uint8Array(24)), byte => byte.toString(16).padStart(2, '0')).join('');
      value.addEventListener('submit', async event => {
        event.preventDefault();submit.disabled = true;back.disabled = true;
        feedback.textContent = 'Vérification en cours…';
        try {
          const result = await call('reserve', {environment, service_id: animation.service_id, token: identity.token,
            participants: selected, slot_uuid: slot, request_key: requestKey, consent: true});
          receipt(result);
          await refresh();
        } catch (error) {feedback.textContent = error.message;submit.disabled = false;back.disabled = false;}
      });
    }
    function receipt(result) {
      const single = result.count === 1;
      const [value] = form(result.status === 'confirmed' ? 'Réservation confirmée' : single ? 'Inscription en liste d’attente' : 'Groupe en liste d’attente');
      value.appendChild(node('p', '', result.count + (single ? ' place demandée. ' : ' participants. ') + (result.status === 'confirmed' ? single ? 'Votre inscription est confirmée.' : 'Tous sont inscrits ensemble.' : single ? 'Vous recevrez une proposition par e-mail lorsqu’une place sera disponible.' : 'Aucune place n’est encore confirmée. Une proposition sera envoyée par e-mail si tout le groupe peut être accueilli.')));
    }
    async function resume() {
      await refresh();
      let pending;
      try {pending = JSON.parse(sessionStorage.getItem(storageKey(environment)) || 'null');} catch (_) {}
      if (!pending || pending.until < Date.now() || pending.environment !== environment) {forget(environment);return;}
      active.set(environment, pending.animation);
      markSelection();
      const [, feedback] = form('Vérification en cours…');
      feedback.textContent = 'Votre demande est reçue. Cette page se mettra à jour automatiquement.';
      try {
        const result = await awaitResult(pending);
        if (pending.route === 'reserve' || pending.route === 'guest') {receipt(result);await refresh();}
        else if (pending.animation) {
          if (result.contact_required) contact(pending.animation, result);
          else select(pending.animation, result);
        }
      } catch (error) {feedback.textContent = error.message;}
    }
    resume();
  }
  document.querySelectorAll('.openfablab-reservations').forEach(init);
}());
