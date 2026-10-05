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
  async function call(route, body) {
    const response = await fetch(config.api + route, body ? {
      method: 'POST', credentials: 'omit', cache: 'no-store',
      headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)
    } : {credentials: 'omit', cache: 'no-store'});
    const value = await response.json();
    if (!response.ok) throw new Error(value.message || 'La demande n’a pas abouti.');
    return value;
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
    async function refresh() {
      try {
        const result = await call('animations?environment=' + encodeURIComponent(environment));
        list.replaceChildren();
        status.textContent = result.animations.length ? '' : 'Aucune animation ouverte à la réservation.';
        result.animations.forEach(animation => {
          const card = node('article', 'openfablab-card');
          card.appendChild(node('h3', '', animation.title));
          card.appendChild(node('p', 'openfablab-date', animation.date + ' · ' + animation.hours));
          card.appendChild(node('p', '', animation.description || ''));
          card.appendChild(node('p', '', animation.available + ' place(s) disponible(s)' + (animation.waitlist_enabled ? ' · liste d’attente possible' : '')));
          const button = node('button', 'openfablab-button', 'Réserver'); button.type = 'button';
          button.addEventListener('click', () => identify(animation));
          card.appendChild(button); list.appendChild(card);
        });
      } catch (error) {status.textContent = error.message;}
    }
    function form(title) {
      host.replaceChildren();
      const value = node('form', 'openfablab-booking-form');
      const heading = node('h3', '', title); heading.tabIndex = -1;
      value.appendChild(heading);
      const feedback = node('p', 'openfablab-verification'); feedback.setAttribute('role', 'status');
      value.appendChild(feedback);host.appendChild(value);heading.focus();
      return [value, feedback];
    }
    function identify(animation) {
      const [value, feedback] = form('Identifier mon compte');
      value.appendChild(node('p', '', 'Saisissez votre identifiant et une coordonnée déjà renseignée dans votre fiche. Les membres rattachés ne sont affichés qu’après cette vérification.'));
      value.appendChild(field('public_id', 'Identifiant OpenFabLab'));
      value.appendChild(field('contact', 'E-mail ou téléphone de votre fiche'));
      const button = node('button', 'openfablab-button', 'Continuer');value.appendChild(button);
      value.addEventListener('submit', async event => {
        event.preventDefault();button.disabled = true;
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
        try {
          const result = await call('reserve', {environment, service_id: animation.service_id, token: identity.token,
            participants: selected, slot_uuid: slot, request_key: requestKey, consent: true});
          const [receipt] = form(result.status === 'confirmed' ? 'Réservation confirmée' : 'Groupe en liste d’attente');
          receipt.appendChild(node('p', '', result.count + ' participant(s). ' + (result.status === 'confirmed' ? 'Tous sont inscrits ensemble.' : 'Aucune place n’est encore confirmée. Une proposition sera envoyée par e-mail si tout le groupe peut être accueilli.')));
          await refresh();
        } catch (error) {feedback.textContent = error.message;submit.disabled = false;back.disabled = false;}
      });
    }
    refresh();
  }
  document.querySelectorAll('.openfablab-reservations').forEach(init);
}());
