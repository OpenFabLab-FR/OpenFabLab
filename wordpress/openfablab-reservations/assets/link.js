/* OFL native UI marked */
(async function () {
  'use strict';
  const __oflT_69d636b7=text=>window.OpenFabLabPublicI18n?.t(text)||text;
  const root = document.querySelector('[data-openfablab-link]');
  if (!root) return;
  const status = root.querySelector('[role="status"]');
  const buttons = root.querySelector('.openfablab-link-buttons');
  const config = {api:root.dataset.api};
  const storage = 'ofl-email-link-v4';
  // Opening a different e-mail link in this same document must not keep the
  // previous booking on screen. Re-enter the existing guarded initialization.
  window.addEventListener('hashchange',()=>{if(new URLSearchParams(location.hash.slice(1)).has('ofl'))location.reload();});
  let link, environment, csrf;
  let lastDetails;
  const details=root.querySelector('.openfablab-link-details') || root.insertBefore(document.createElement('div'),status);
  const key = () => Array.from(crypto.getRandomValues(new Uint8Array(24)), x => x.toString(16).padStart(2, '0')).join('');
  async function request(route, body) {
    const response = await fetch(config.api + route, body ? {
      method:'POST',credentials:'same-origin',cache:'no-store',
      headers:{'Content-Type':'application/json','X-OpenFabLab-CSRF':csrf},body:JSON.stringify(body)
    } : {credentials:'same-origin',cache:'no-store'});
    const result = await response.json();
    if (!response.ok) throw new Error(__oflT_69d636b7(result.message) || __oflT_69d636b7("Cette action est indisponible."));
    return result;
  }
  async function follow(pending) {
    status.textContent = pending.action==='cancel' ? __oflT_69d636b7("Votre demande d’annulation est transmise. Elle attend la confirmation d’OpenFabLab.") : __oflT_69d636b7("Votre demande a bien été reçue. Elle attend la confirmation d’OpenFabLab.");
    const start = Date.now();
    while (Date.now() - start < 600000) {
      const result = await request('status',{environment,request_key:pending.key});
      if (result.state === 'expired') throw new Error(__oflT_69d636b7(result.message));
      if (result.state === 'done') {
        sessionStorage.removeItem(storage + '-pending');
        if (!result.result.ok) throw new Error(__oflT_69d636b7(result.result.message));
        return result.result.value;
      }
      await new Promise(resolve => setTimeout(resolve,2500));
    }
    throw new Error(__oflT_69d636b7("Cette action est toujours en cours. Actualisez cette page pour reprendre son suivi."));
  }
  async function send(action) {
    const pending = {key:key(),environment,action,until:Date.now()+1200000};
    sessionStorage.setItem(storage+'-pending',JSON.stringify(pending));
    await request('link',{environment,action,link,consent:action!=='view',request_key:pending.key});
    return follow(pending);
  }
  function display(result, action) {
    buttons.replaceChildren();
    if(result.title)lastDetails=result;
    details.replaceChildren();
    if(lastDetails){
      const title=document.createElement('h2');title.textContent=lastDetails.title;
      const date=document.createElement('p');date.textContent=(lastDetails.date||'').split('-').reverse().join('/')+' · '+(lastDetails.hours||'');
      const count=document.createElement('p');count.textContent=lastDetails.count+__oflT_69d636b7(" participant")+(lastDetails.count===1?'':'s');
      const people=document.createElement('ul');for(const name of lastDetails.participants||[]){const li=document.createElement('li');li.textContent=name;people.append(li);}
      details.append(title,date,count,people);
      if(lastDetails.information_url){try{const url=new URL(lastDetails.information_url);if(['http:','https:'].includes(url.protocol)){const info=document.createElement('a');info.href=url.href;info.rel='noopener noreferrer';info.textContent=__oflT_69d636b7("En savoir plus sur cette animation");details.append(info);}}catch(_error){}}
    }
    const badge=document.createElement('span');badge.className='openfablab-state-badge';badge.textContent=__oflT_69d636b7(result.label)||({cancelled:__oflT_69d636b7("Annulée"),confirmed:__oflT_69d636b7("Confirmée"),waitlisted:__oflT_69d636b7("En attente"),offer_pending:__oflT_69d636b7("Place proposée"),declined:__oflT_69d636b7("Refusée"),expired:__oflT_69d636b7("Expirée")}[result.status]||__oflT_69d636b7("État confirmé"));details.append(badge);
    if(result.status==='confirmed'&&result.calendar)window.OpenFabLabPublicI18n?.calendar(details,result.calendar);
    status.textContent = ({cancelled:__oflT_69d636b7("Votre réservation est annulée."),confirmed:__oflT_69d636b7("Votre réservation est confirmée."),declined:__oflT_69d636b7("Votre proposition a été refusée."),expired:__oflT_69d636b7("Cette proposition a expiré. Aucune place n’a été confirmée."),waitlisted:__oflT_69d636b7("Votre demande est en liste d’attente. Aucune place n’est encore confirmée."),offer_pending:__oflT_69d636b7("Des places sont proposées pour tout votre groupe.")}[result.status] || __oflT_69d636b7("État confirmé par OpenFabLab."));
    if (action !== 'view') return;
    const choices = result.can_answer ? [['accept',__oflT_69d636b7("Accepter la proposition")],['decline',__oflT_69d636b7("Refuser la proposition")]] : [];
    if (['confirmed','waitlisted','offer_pending'].includes(result.status)) choices.push(['cancel',__oflT_69d636b7("Annuler ma réservation")]);
    for (const [type,label] of choices) {
      const button=document.createElement('button');button.type='button';button.className='openfablab-button';button.textContent=label;
      buttons.append(button);button.addEventListener('click',()=>confirmAction(type,label,result));
    }
  }
  function confirmAction(type,label,result){
    buttons.replaceChildren();
    const text=document.createElement('p');const count=lastDetails?lastDetails.count:result.count;
    text.textContent=type==='cancel'?__oflT_69d636b7("Vous souhaitez annuler cette réservation")+(count?__oflT_69d636b7(" pour ")+count+__oflT_69d636b7(" personne")+(count===1?'':'s'):'')+__oflT_69d636b7(". Les places retenues seront libérées."):__oflT_69d636b7(type==='accept'?"Accepter la proposition pour tout votre groupe ?":"Refuser la proposition pour tout votre groupe ?");
    const form=document.createElement('form');
    const consent=document.createElement('label');consent.className='openfablab-family-person';
    const checkbox=document.createElement('input');checkbox.type='checkbox';checkbox.required=true;
    consent.append(checkbox,document.createTextNode(type==='cancel'?__oflT_69d636b7("Je confirme vouloir annuler cette réservation."):__oflT_69d636b7("Je confirme cette réponse pour tout le groupe.")));
    const back=document.createElement('button');back.type='button';back.className='openfablab-button is-secondary';back.textContent=__oflT_69d636b7("Retour");back.addEventListener('click',()=>display(result,'view'));
    const confirm=document.createElement('button');confirm.className='openfablab-button';confirm.textContent=type==='cancel'?__oflT_69d636b7("Confirmer l’annulation"):label;
    form.append(consent,back,confirm);buttons.append(text,form);checkbox.focus();
    form.addEventListener('submit',async event=>{
      event.preventDefault();if(!checkbox.checked)return;
      buttons.querySelectorAll('button').forEach(b=>{b.disabled=true;});
      try{const result=await send(type);display(result.status==='confirmed'?await send('view'):result,type);}catch(error){status.textContent=__oflT_69d636b7(error.message);}
    });
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
    if (!saved || saved.until<Date.now()) throw new Error(__oflT_69d636b7("Ce lien a expiré. Ouvrez à nouveau le lien de votre e-mail."));
    link=saved.link;
    const token=JSON.parse(atob(link.split('.')[0].replace(/-/g,'+').replace(/_/g,'/')));
    environment=token.e;
    if (!['production','test'].includes(environment)) throw new Error(__oflT_69d636b7("Ce lien est invalide."));
    const session=await request('session?environment='+environment);csrf=session.csrf;
    const pending=JSON.parse(sessionStorage.getItem(storage+'-pending')||'null');
    if (pending && pending.environment===environment && pending.until>Date.now()) display(await follow(pending),pending.action);
    else display(await send('view'),'view');
  } catch(error){status.textContent=__oflT_69d636b7(error.message);}
}());
