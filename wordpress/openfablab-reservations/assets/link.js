(async function () {
  'use strict';
  const root = document.querySelector('[data-openfablab-link]');
  if (!root) return;
  const status = root.querySelector('[role="status"]');
  const buttons = root.querySelector('.openfablab-link-buttons');
  const config = {api:root.dataset.api};
  const storage = 'ofl-email-link-v4';
  let link, environment, csrf;
  const key = () => Array.from(crypto.getRandomValues(new Uint8Array(24)), x => x.toString(16).padStart(2, '0')).join('');
  async function request(route, body) {
    const response = await fetch(config.api + route, body ? {
      method:'POST',credentials:'same-origin',cache:'no-store',
      headers:{'Content-Type':'application/json','X-OpenFabLab-CSRF':csrf},body:JSON.stringify(body)
    } : {credentials:'same-origin',cache:'no-store'});
    const result = await response.json();
    if (!response.ok) throw new Error(result.message || 'Cette action est indisponible.');
    return result;
  }
  async function follow(pending) {
    status.textContent = 'Action reçue. Vérification en cours…';
    const start = Date.now();
    while (Date.now() - start < 600000) {
      const result = await request('status',{environment,request_key:pending.key});
      if (result.state === 'expired') throw new Error(result.message);
      if (result.state === 'done') {
        sessionStorage.removeItem(storage + '-pending');
        if (!result.result.ok) throw new Error(result.result.message);
        return result.result.value;
      }
      await new Promise(resolve => setTimeout(resolve,2500));
    }
    throw new Error('Cette action est toujours en cours. Actualisez cette page pour reprendre son suivi.');
  }
  async function send(action) {
    const pending = {key:key(),environment,action,until:Date.now()+1200000};
    sessionStorage.setItem(storage+'-pending',JSON.stringify(pending));
    await request('link',{environment,action,link,consent:action!=='view',request_key:pending.key});
    return follow(pending);
  }
  function display(result, action) {
    buttons.replaceChildren();
    status.textContent = result.label || ({cancelled:'Réservation annulée.',confirmed:'Réservation confirmée.',declined:'Place refusée.',expired:'Cette proposition a expiré. Aucune place n’a été confirmée.',waitlisted:'Votre groupe est en liste d’attente.'}[result.status] || 'État confirmé par OpenFabLab.');
    if (action !== 'view') return;
    const choices = result.can_answer ? [['accept','Accepter la proposition'],['decline','Refuser la proposition']] : [];
    if (['confirmed','waitlisted','offer_pending'].includes(result.status)) choices.push(['cancel','Annuler ma réservation']);
    for (const [type,label] of choices) {
      const form = document.createElement('form');
      const consent = document.createElement('label');consent.className='openfablab-family-person';
      const checkbox=document.createElement('input');checkbox.type='checkbox';checkbox.required=true;
      consent.append(checkbox,document.createTextNode('Je confirme ce choix.'));
      const button=document.createElement('button');button.className='openfablab-button';button.textContent=label;
      form.append(consent,button);buttons.append(form);
      form.addEventListener('submit',async event=>{
        event.preventDefault();buttons.querySelectorAll('button').forEach(b=>{b.disabled=true;});
        try {display(await send(type),type);}
        catch(error){status.textContent=error.message;}
      });
    }
  }
  try {
    const fragment = new URLSearchParams(location.hash.slice(1)).get('ofl');
    if (fragment) {
      history.replaceState(null,'',location.pathname+location.search);
      const previous = JSON.parse(sessionStorage.getItem(storage)||'null');
      if (!previous || previous.link !== fragment) sessionStorage.removeItem(storage+'-pending');
      sessionStorage.setItem(storage,JSON.stringify({link:fragment,until:Date.now()+1200000}));
    }
    const saved=JSON.parse(sessionStorage.getItem(storage)||'null');
    if (!saved || saved.until<Date.now()) throw new Error('Ce lien a expiré. Ouvrez à nouveau le lien de votre e-mail.');
    link=saved.link;
    const token=JSON.parse(atob(link.split('.')[0].replace(/-/g,'+').replace(/_/g,'/')));
    environment=token.e;
    if (!['production','test'].includes(environment)) throw new Error('Ce lien est invalide.');
    const session=await request('session?environment='+environment);csrf=session.csrf;
    const pending=JSON.parse(sessionStorage.getItem(storage+'-pending')||'null');
    if (pending && pending.environment===environment && pending.until>Date.now()) display(await follow(pending),pending.action);
    else display(await send('view'),'view');
  } catch(error){status.textContent=error.message;}
}());
