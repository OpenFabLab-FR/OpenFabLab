/* Personal data stays in memory and in text nodes, never HTML or web storage. */
(() => {
  'use strict';
  const i18n=window.OpenFabLabPublicI18n, words=window.OpenFabLabAccountLanguages?.[i18n?.language]||{};
  const tr = text => Object.hasOwn(words,text)?words[text]:i18n?.t(text)||text;
  const node = (tag,text) => { const e=document.createElement(tag); if(text!=null)e.textContent=tr(text);return e; };
  const literal = (tag,text) => {const e=document.createElement(tag);e.textContent=text||'';return e;};
  const randomKey = () => Array.from(crypto.getRandomValues(new Uint8Array(24)),b=>b.toString(16).padStart(2,'0')).join('');
  const pause = ms => new Promise(resolve=>setTimeout(resolve,ms));
  // Only a CSRF proof in memory; never store a profile or a ticket in browser storage.
  const sessions = new Map();
  const icons={info:'M5 20v-2a4 4 0 0 1 4-4h6a4 4 0 0 1 4 4v2M12 10a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z',
    family:'M2 20v-2a4 4 0 0 1 4-4h4a4 4 0 0 1 4 4v2M8 10a3 3 0 1 0 0-6 3 3 0 0 0 0 6ZM22 20v-2a4 4 0 0 0-4-4h-1m-1-10a3 3 0 0 1 0 6',
    bookings:'M7 3v4m10-4v4M4 10h16M4 5h16v15H4Z'};
  function icon(key){
    const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');
    const path=document.createElementNS(svg.namespaceURI,'path');
    svg.setAttribute('viewBox','0 0 24 24');svg.setAttribute('aria-hidden','true');
    path.setAttribute('d',icons[key]);svg.append(path);return svg;
  }
  document.querySelectorAll('.ofl-account').forEach(root => {
    const env=root.dataset.env,api=root.dataset.api,status=root.querySelector('[role=status]'),body=root.querySelector('.ofl-account-body');
    root.lang=i18n?.language||'fr';root.querySelector('h2').textContent=tr('Mon compte');root.setAttribute('aria-label',tr('Mon compte'));
    i18n?.ready(root,root.querySelector('header'));
    let csrf,me,options={},busy=false,animations=[],expiration,section=body,publicAction='',catalogue;
    const intentKey='ofl-account-intent-'+env;
    function intent(value) { try {
      if(value!==undefined)sessionStorage.setItem(intentKey,JSON.stringify({value,until:Date.now()+1800000}));
      const v=JSON.parse(sessionStorage.getItem(intentKey)||'null');return v&&v.until>Date.now()?v.value:0;
    } catch(_) {return value||0;} }
    const initial=Number(new URLSearchParams(location.search).get('ofl_animation'));
    if(Number.isSafeInteger(initial)&&initial>0)intent(initial);
    function fromHash(){
      const value=location.hash.match(/^#ofl-account=([A-Za-z0-9_-]{43})$/)?.[1];
      if(value)history.replaceState(null,'',location.pathname+location.search);
      return value;
    }
    let ticket=fromHash();
    const signal=(text='',kind='info',personal=false)=>{
      status.textContent=personal?text:tr(text);status.dataset.kind=kind;status.hidden=!text;
    };
    const loading='Chargement de votre espace personnel…';
    const locale={fr:'fr-FR',en:'en-GB',de:'de-DE',es:'es-ES',fi:'fi-FI'}[root.lang]||'fr-FR';
    const formats=new Intl.DateTimeFormat(locale,{dateStyle:'short',timeZone:'UTC'});
    const dateText=value=>/^\d{4}-\d{2}-\d{2}$/.test(value||'')?formats.format(new Date(value+'T12:00:00Z')):value;
    async function req(route,data,retry=true) {
      const r=await fetch(api+route,{credentials:'same-origin',cache:'no-store',referrerPolicy:'no-referrer',
        ...(data?{method:'POST',headers:{'Content-Type':'application/json','X-OpenFabLab-CSRF':csrf},body:JSON.stringify(data)}:{})});
      const v=await r.json();
      // A 429 from our same-origin permission check means no action was admitted.
      // Keep the SAME request key; never blindly retry an ambiguous network failure.
      if(r.status===429 && retry && Number.isInteger(v.data?.retry_after) && v.data.retry_after>=1 && v.data.retry_after<=61){
        signal('Veuillez patienter quelques instants.','loading');await pause(1000*v.data.retry_after);
        return req(route,data,false);
      }
      if(!r.ok)throw Error(v.message||tr('Connexion indisponible.'));return v;
    }
    async function session(){
      if(!sessions.has(env)){
        const pending=req('session?account=1&environment='+env).catch(error=>{sessions.delete(env);throw error;});
        sessions.set(env,pending);
      }
      const value=await sessions.get(env);
      if(!value.csrf)throw Error(tr('Connexion indisponible.'));
      if(Number(value.csrf.split('.')[0])*1000<Date.now()+30000){sessions.delete(env);return session();}
      csrf=value.csrf;
      return value;
    }
    async function call(op,fields={}) {
      await session();
      const key=randomKey(),base={environment:env,request_key:key,lang:window.OpenFabLabPublicI18n?.language||'fr'};
      await req('account',{...fields,...base,op});
      for(let i=0;i<60;i++) {
        await pause([550,700,750,950,1200,1600][i]||2500);
        const r=await req('status',{...base,account:true});
        if(r.state==='done'){if(!r.result.ok){if(r.result.auth_required&&me)landing();throw Error(r.result.message);}return r.result.value;}
        if(r.state==='expired')throw Error(r.message);
      }
      throw Error(tr('Le service met plus de temps que prévu. Vérifiez votre espace avant de réessayer.'));
    }
    async function run(fn) {
      if(busy)return;busy=true;body.setAttribute('aria-busy','true');signal(loading,'loading');
      const slow=setTimeout(()=>signal('Veuillez patienter quelques instants.','loading'),4500);
      try{await fn();if(status.dataset.kind==='loading')signal();}
      catch(e){signal(e instanceof TypeError?'Connexion interrompue. Réessayez lorsque le service revient.':e.message,'error');}
      finally{clearTimeout(slow);busy=false;body.removeAttribute('aria-busy');}
    }
    function button(parent,title,action,variant='secondary') {const b=node('button',title);b.type='button';b.className='ofl-account-btn is-'+variant;b.addEventListener('click',action);parent.append(b);return b;}
    function card(parent,title,name='section') {
      const el=node(name);el.className='ofl-account-card';if(title)el.append(node('h3',title));parent.append(el);return el;
    }
    function grid(parent,name='ofl-account-grid') {const el=node('div');el.className=name;parent.append(el);return el;}
    function field(form,name,label,type='text',required=true,personal=false) {
      const l=node('label'),i=node('input');l.className=type==='checkbox'?'ofl-account-check':'ofl-account-field';i.type=type;i.name=name;i.required=required;i.maxLength={first_name:80,last_name:80,city:100,postal_code:12,nationality:80,phone:30,phone_country_code:7}[name]||254;
      if(type==='checkbox')l.append(i,personal?literal('span',label):node('span',label));
      else if(type==='date'){
        const wrap=node('span');wrap.className='ofl-account-date';
        const hint=literal('small',new Intl.DateTimeFormat(locale,{year:'numeric',month:'2-digit',day:'2-digit',timeZone:'UTC'})
          .formatToParts(new Date('2004-10-23T12:00:00Z')).map(part=>({day:tr('JJ'),month:tr('MM'),year:tr('AAAA')}[part.type]||part.value)).join(''));
        hint.setAttribute('aria-hidden','true');wrap.append(i,hint);l.append(node('span',label),wrap);
        const update=()=>{wrap.dataset.empty=i.value?'0':'1';};
        i.addEventListener('input',update);i.addEventListener('change',update);update();
      } else l.append(node('span',label),i);
      form.append(l);return i;
    }
    function form(title,submit,onSubmit,parent=section){
      const f=card(parent,title,'form');const b=node('button',submit);b.className='ofl-account-btn is-primary';b.type='submit';
      f.addEventListener('submit',e=>{e.preventDefault();if(!busy){b.disabled=true;run(()=>onSubmit(f)).finally(()=>{b.disabled=false;});}});
      return {f,finish:()=>grid(f,'ofl-account-actions').append(b)};
    }
    const values=f=>Object.fromEntries(new FormData(f));
    function phoneFields(parent){
      const group=grid(parent,'ofl-account-phone');
      const code=field(group,'phone_country_code','Indicatif','tel',false);
      code.autocomplete='tel-country-code';code.value='+33';
      const phone=field(group,'phone','Téléphone','tel',false);phone.autocomplete='tel-national';
      return {code,phone};
    }
    function coordinates(parent){
      const row=grid(parent);field(row,'postal_code','Code postal','text',false).autocomplete='postal-code';
      field(row,'city','Commune de domicile','text',false).autocomplete='address-level2';
    }
    function personFields(parent,child=false){
      const names=grid(parent);field(names,'first_name','Prénom').autocomplete='given-name';field(names,'last_name','Nom').autocomplete='family-name';
      const row=grid(parent);
      if(child)field(row,'birth_date','Date de naissance','date').autocomplete='bday';
      else {
        const now=new Date().getFullYear(),year=field(row,'birth_year','Année de naissance','number');
        year.autocomplete='bday-year';year.min=1900;year.max=now;year.inputMode='numeric';
        const exact=field(row,'birth_date','Date de naissance complète','date',false);
        exact.autocomplete='bday';
        const help=node('small','Indiquez votre année, ou votre date complète : elle remplit l’année automatiquement. La date complète est requise pour les mineurs et près d’un seuil d’âge.');
        help.className='ofl-account-field-help';
        parent.append(help);
        const helpId='ofl-birth-help-'+randomKey();
        help.id=helpId;year.setAttribute('aria-describedby',helpId);exact.setAttribute('aria-describedby',helpId);
        const syncBirth=()=>{
          year.readOnly=!!exact.value;
          if(exact.value)year.value=exact.value.slice(0,4);
        };
        exact.addEventListener('input',syncBirth);
        exact.addEventListener('change',syncBirth);
      }
      const more=grid(parent),label=node('label'),gender=node('select');label.className='ofl-account-field';gender.name='gender';
      for(const [v,t] of [['','Non renseigné'],['female','Femme'],['male','Homme'],['non_binary','Non-binaire']]){
        const option=node('option',t);option.value=v;gender.append(option);
      }
      label.append(node('span','Genre'),gender);more.append(label);
      field(more,'nationality','Nationalité','text',false);
    }
    function landing() {
      clearTimeout(expiration);me=null;publicAction='';body.replaceChildren();section=body;
      const hero=card(body,'Bienvenue dans votre espace personnel');
      hero.append(node('p','Retrouvez vos informations, votre famille et vos réservations au même endroit.'));
      const nav=grid(hero,'ofl-account-actions');
      button(nav,'J’ai déjà un compte',()=>entry('login'),'primary');
      if(options.signup)button(nav,'Créer mon compte',()=>entry('signup'));
      button(nav,'Identifiant oublié ?',()=>entry('recover'),'quiet');
      hero.append(node('small','Sans adresse e-mail vérifiable ou en cas de coordonnées partagées, contactez votre FabLab.'));
    }
    function entry(op){
      signal();publicAction=op;body.replaceChildren();section=body;
      const title={login:'Connexion',signup:'Créer mon compte',recover:'Retrouver mon identifiant'}[op];
      const {f,finish}=form(title,{login:'Recevoir un lien de connexion',signup:'Créer mon compte',recover:'Recevoir mon identifiant'}[op],async f=>{
        const r=await call(op,{...values(f),consent:!!f.elements.consent?.checked});
        landing();signal(r.message,'success');});
      if(op==='signup'){personFields(f);coordinates(f);}
      field(f,'email','Adresse e-mail','email').autocomplete='email';
      if(op==='signup')phoneFields(f);
      if(op==='signup'){if(root.dataset.privacy){const a=node('a','Informations de confidentialité');a.href=root.dataset.privacy;
        a.target='_blank';a.rel='noopener noreferrer';f.append(a);}
        field(f,'consent','J’ai pris connaissance des informations de confidentialité du FabLab.','checkbox');}
      f.append(node('p','Ouvrez le lien reçu dans ce même navigateur.'));finish();
      button(f,'Retour à Mon compte',()=>{signal();landing();},'quiet');
    }
    function privateNav(active){
      body.replaceChildren();const nav=node('nav');nav.className='ofl-account-tabs';nav.setAttribute('aria-label',tr('Mon espace'));body.append(nav);
      for(const [id,title,view] of [['info','Mes informations',info],['family','Ma famille',family],['bookings','Mes réservations',reservations]]){
        const tab=button(nav,title,()=>{
          signal();view();body.querySelector('[aria-current=page]')?.focus();
          if(id==='bookings'&&!animations.length)loadCatalogue().then(()=>{
            if(animations.length && tab.textContent===body.querySelector('[aria-current=page]')?.textContent)reservations();
          });
        },'tab');
        tab.prepend(icon(id));
        if(active===id)tab.setAttribute('aria-current','page');
      }
      button(nav,'Déconnexion',()=>run(async()=>{await call('logout');sessions.delete(env);landing();signal('Vous êtes déconnecté.');}),'quiet');
      section=grid(body,'ofl-account-section');
    }
    function qr(parent,person){
      if(!person?.public_id)return;
      parent.append(literal('p',tr('Identifiant à la borne')+' · '+person.public_id));
      const region=grid(parent,'ofl-account-qr');
      button(region,'Afficher le QR Code',()=>run(async()=>{
        const result=await call('qr',{person:person.id});
        if(!/^[A-Za-z0-9+/]{20,4096}={0,2}$/.test(result.png||''))throw Error('QR Code indisponible.');
        region.replaceChildren();
        const img=node('img');img.src='data:image/png;base64,'+result.png;img.alt=tr('QR Code pour la borne');img.width=144;img.height=144;
        const download=node('a','Télécharger le QR Code');download.href=img.src;download.download='OpenFabLab-QR.png';
        region.append(img,download);
      }));
    }
    function info(){
      privateNav('info');
      const details=card(section,'Mes informations'), profile=me.me;
      details.append(literal('p',profile.first_name+' '+profile.last_name));
      const dl=node('dl');dl.className='ofl-account-data';details.append(dl);
      const phone=[profile.phone_country_code,profile.phone].filter(Boolean).join(' ');
      for(const [label,value] of [['Adresse e-mail',profile.email],['Téléphone',profile.phone&&phone],['Commune de domicile',[profile.postal_code,profile.city].filter(Boolean).join(' ')]])
        dl.append(node('dt',label),literal('dd',value||tr('Non renseigné')));
      const controls=grid(details,'ofl-account-actions'),editor=grid(section,'ofl-account-section');
      for(const [op,label,submit] of [['phone','Modifier mon téléphone','Enregistrer mon téléphone'],['email','Modifier mon adresse e-mail','Modifier mon adresse e-mail']]){
        button(controls,label,()=>{
          editor.replaceChildren();signal();
          const {f,finish}=form(label,submit,async f=>{
            const result=await call(op,values(f));
            // The email change only sends a link; the displayed address is
            // not changed until the link is verified.
            if(op==='phone')await refresh();
            info();signal(result.message,'success');},editor);
          if(op==='phone'){const {code,phone}=phoneFields(f);code.value=profile.phone_country_code||'+33';phone.value=profile.phone||'';phone.focus();}
          else field(f,'email','Nouvelle adresse e-mail','email').focus();
          finish();button(f,'Annuler',()=>editor.replaceChildren(),'quiet');
        });
      }
      qr(card(section,'Mon identifiant et mon QR Code'),me.people[0]);
    }
    function family(){
      privateNav('family');const panel=card(section,'Ma famille'),kids=me.people.slice(1);
      if(!kids.length)panel.append(node('p','Aucun enfant rattaché pour le moment.'));
      for(const person of kids){const item=card(panel);item.append(literal('h4',person.first_name+' '+person.last_name));qr(item,person);}
      const actions=grid(panel,'ofl-account-actions');
      if(intent())button(actions,'Reprendre ma réservation',reservations);
      if(me.can_manage_family===false)return;
      const editor=grid(section,'ofl-account-section');
      button(actions,'Ajouter un enfant',()=>{
        editor.replaceChildren();signal();
        const {f,finish}=form('Ajouter un enfant','Ajouter mon enfant',async f=>{
          const result=await call('child',{...values(f),consent:f.elements.consent.checked,
            same_address:f.elements.same_address.checked,same_contact:f.elements.same_contact.checked});
          await refresh();family();signal(result.message,'success');},editor);
        personFields(f,true);
        const sameAddress=field(f,'same_address','Mon enfant réside à la même adresse que moi.','checkbox',false);
        const address=grid(f,'ofl-account-section');coordinates(address);
        const sameContact=field(f,'same_contact','Utiliser mes coordonnées pour mon enfant.','checkbox',false);
        const contact=grid(f,'ofl-account-section');field(contact,'email','Adresse e-mail','email',false);phoneFields(contact);
        const present=value=>typeof value==='string'&&value.trim().length>0;
        const parent=me.me;
        for(const [box,container,available] of [[sameAddress,address,present(parent.postal_code)&&present(parent.city)],
                                                [sameContact,contact,present(parent.email)&&present(parent.phone)]]){
          box.checked=available;
          const update=()=>{container.hidden=box.checked;container.querySelectorAll('input').forEach(i=>{i.disabled=box.checked;});};
          box.addEventListener('change',update);update();
        }
        field(f,'consent','Je suis autorisé à gérer les inscriptions de cet enfant.','checkbox');finish();
        button(f,'Annuler',()=>editor.replaceChildren(),'quiet');
        f.elements.first_name.focus();
      });
    }
    function reservations(){
      privateNav('bookings');
      const panel=card(section,'Mes réservations');
      const labels={confirmed:'Confirmée',waitlisted:'Liste d’attente',offer_pending:'Place proposée : consultez votre e-mail.',
        cancelled:'Annulée',declined:'Refusée',expired:'Expirée',present:'Présent',absent:'Absent'};
      const byTime=[me.reservations.filter(b=>b.date>=me.today).sort((a,b)=>a.date.localeCompare(b.date)),me.reservations.filter(b=>b.date<me.today)];
      const controls=new Set();
      for(const [n,bookings] of byTime.entries()){if(!bookings.length)continue;
      panel.append(node('h4',n?'Historique':'À venir'));const list=node('ul');list.className='ofl-account-bookings';panel.append(list);
      for(const b of bookings){const li=node('li'),badge=node('span',labels[b.status]||b.status);
        badge.className='ofl-account-badge';li.append(literal('strong',b.title),literal('p',[dateText(b.date),b.hours,b.person].filter(Boolean).join(' · ')),badge);list.append(li);
        if(!b.cancel||controls.has(b.cancel))continue;controls.add(b.cancel);
        if(b.cancel && b.status==='offer_pending')for(const [op,label] of [['accept_offer','Accepter les places'],['decline_offer','Décliner les places']])
          button(li,label,()=>{if(window.confirm(tr('Confirmer cette décision pour tout le groupe ?')))run(async()=>{
            await call(op,{group:b.cancel,consent:true});await refresh();reservations();signal(op==='accept_offer'?'Votre place a été confirmée.':'Vous avez décliné les places proposées.','success');});});
        if(b.cancel)button(li,'Annuler la réservation du groupe',()=>{if(window.confirm(tr('Confirmer l’annulation du groupe ?')))run(async()=>{
          await call('cancel',{group:b.cancel,consent:true});await refresh();reservations();signal('Votre réservation a été annulée.','success');});});}}
      if(!me.reservations.length)panel.append(node('p','Aucune réservation pour le moment.'));
      if(!animations.length)return;
      const reserve=card(section,'Réserver une animation');
      const picker=node('select'),label=node('label','Choisir une animation');label.className='ofl-account-field';reserve.append(label);label.append(picker);
      const prompt=node('option','Sélectionner une animation');prompt.value='';picker.append(prompt);
      for(const a of animations){const option=literal('option',dateText(a.date)+' · '+a.title);option.value=a.service_id;picker.append(option);}
      if(animations.some(a=>a.service_id===intent()))picker.value=intent();
      const redraw=()=>{const old=reserve.querySelector('form');if(old)old.remove();
        const a=animations.find(i=>i.service_id===Number(picker.value));if(!a)return;
        const {f,finish}=form('Participants','Réserver l’animation',async f=>{const ids=[...f.querySelectorAll('[name=person]:checked')].map(e=>Number(e.value));
          const r=await call('reserve',{service_id:a.service_id,participants:ids,slot_uuid:f.elements.slot?.value||null,consent:f.elements.consent.checked});
          await refresh();reservations();signal(r.status==='confirmed'?'Votre réservation a bien été enregistrée.':'Votre demande est inscrite sur la liste d’attente.','success');},reserve);
        f.append(node('p','Chaque participant et chaque accompagnateur occupe une place. Les places sont revérifiées à la confirmation.'));
        if(a.minimum_age!=null)f.append(node('p',tr('Âge minimum')+' : '+a.minimum_age));
        if(me.autonomy!=null)f.append(node('p',tr('Accompagnement requis avant')+' : '+me.autonomy));
        if(a.slots?.length){const l=node('label','Créneau'),s=node('select');s.name='slot';s.required=true;l.append(s);f.append(l);
          for(const slot of a.slots){const o=node('option',slot.label||slot.starts_at);o.value=slot.slot_uuid;s.append(o);}}
        const count=node('output');count.setAttribute('aria-live','polite');
        for(const p of me.people){const box=field(f,'person',p.first_name+' '+p.last_name,'checkbox',false,true);
          box.value=p.id;box.addEventListener('change',()=>{count.textContent=tr('Places demandées')+' : '+f.querySelectorAll('[name=person]:checked').length;});}
        count.textContent=tr('Places demandées')+' : 0';f.append(count);
        button(f,'Ajouter un enfant',family);field(f,'consent','Je confirme la sélection des participants.','checkbox');finish();};
      picker.addEventListener('change',()=>{intent(Number(picker.value));signal();redraw();});redraw();
    }
    async function refresh(profile){me=profile||await call('overview');clearTimeout(expiration);
      expiration=setTimeout(()=>{landing();signal('Session expirée ou indisponible. Identifiez-vous à nouveau.');},Math.max(0,me.session_seconds)*1000);}
    function confirmView(){
      publicAction='confirm';body.replaceChildren();section=body;
      const panel=card(body,'Poursuivre ma demande');
      panel.append(node('p','Validez la demande commencée dans ce navigateur. Cette étape empêche les robots de messagerie d’utiliser votre lien.'));
      const actions=grid(panel,'ofl-account-actions');
      const confirm=button(actions,'Valider et continuer',()=>run(async()=>{
        const result=await call('confirm',{ticket,include_profile:true});ticket=null;
        if(result.profile||result.signed_in){await present(result.profile);return;}
        // Previous application versions return only a message after confirming.
        if(!options.bootstrap){await startAfterLegacyConfirmation(result.message);return;}
        landing();signal(result.message,'success');
      }),'primary');
      button(actions,'Retour à Mon compte',()=>{ticket=null;signal();landing();},'quiet');
      panel.append(node('small','Vous êtes sur un autre appareil ? Revenez au navigateur de départ ou demandez un nouveau lien depuis cet appareil.'));
      confirm.focus();
    }
    function loadCatalogue(){
      if(!catalogue)catalogue=req('animations?environment='+env)
        .then(data=>{animations=(data.animations||[]).filter(a=>a.availability_state!=='ended');})
        .catch(()=>{catalogue=null;});
      return catalogue;
    }
    async function startAfterLegacyConfirmation(message){
      const value=await call('options');options=value;
      if(value.signed_in)await present();else {landing();signal(message,'success');}
    }
    async function present(profile){
      await refresh(profile);
      if(intent()){
        await loadCatalogue();
        reservations();
      }else{
        info();
        void loadCatalogue();
      }
        signal(tr('Bienvenue, {prénom} !').replace('{prénom}',me.me.first_name),'success',true);
    }
    async function start() {
      const state=await session();
      const capability=state.portal?.bootstrap===true;
      options={signup:state.portal?.signup===true,bootstrap:capability};
      if(ticket){if(!publicAction)confirmView();return;}
      if(capability && state.known_browser===false){if(!publicAction)landing();return;}
      if(!publicAction)signal(loading,'loading');
      const value=await call(capability?'bootstrap':'options');
      options={...value,bootstrap:capability};
      if(publicAction)return;
      if(!value.signed_in){landing();if(status.dataset.kind==='loading')signal();return;}
      await present(value.profile);
    }
    if(ticket)confirmView();else landing();
    start().catch(e=>{if(!busy)signal(e.message,'error');});
    window.addEventListener('hashchange',()=>{
      const value=fromHash();
      if(value){ticket=value;signal();confirmView();}
    });
    window.addEventListener('pagehide',()=>{body.replaceChildren();me=null;ticket=null;});
    window.addEventListener('pageshow',e=>{if(e.persisted)location.reload();});
  });
})();
