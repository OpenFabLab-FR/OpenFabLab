(function(){'use strict';
 const standalone=document.querySelector('[data-openfablab-link]');
 const cfg=window.OpenFabLabPublic||(standalone?{api:standalone.dataset.api,multilingual:standalone.dataset.multilingual==='1',language:standalone.dataset.language}:null);if(!cfg)return;
 const translations={
  'Calendrier public':'Public calendar','Ressources':'Resources','Réservations des animations':'Activity reservations','Chargement…':'Loading…','Aujourd’hui':'Today',
  'Semaine précédente':'Previous week','Semaine suivante':'Next week','Aucun événement.':'No events.','Fermer':'Close','Réserver':'Book',
  'Plus d’informations':'More information','OpenLab':'OpenLab','Animation':'Activity','Disponible':'Available','En maintenance':'Under maintenance','Hors service':'Out of service',
  'Retour estimé':'Estimated return','Inscriptions ouvertes':'Registration open','Liste d’attente ouverte':'Waiting list open',
  'Inscriptions à venir':'Registration opens soon','Inscriptions closes':'Registration closed','Animation terminée':'Activity ended',
  'Capacité maximale':'Maximum capacity','Créneau d’ouverture au public du FabLab.':'Public opening session at the FabLab.',
  'Moyenne des séances avec passages enregistrés, au même horaire, sur les 26 dernières semaines.':'Average of sessions with recorded arrivals, at the same hours, over the last 26 weeks.',
  'Les informations ne sont pas récentes. Vérifiez auprès de votre FabLab.':'This information is out of date. Please check with your FabLab.',
  'Les informations ne sont pas disponibles pour le moment.':'Information is currently unavailable.',
  'Cette période n’est pas couverte par le dernier échange.':'This period is not covered by the latest update.',
  'Les informations saisies seront effacées. Changer de langue ?':'Entered information will be cleared. Change language?',
 };
 let language=cfg.language==='en'?'en':'fr';
 const languageKey='ofl.public.language:'+location.pathname+location.search;
 if(cfg.multilingual){try{const saved=sessionStorage.getItem(languageKey)||localStorage.getItem('ofl.public.language');if(['fr','en'].includes(saved))language=saved;}catch(_){}}
 Object.assign(translations,window.OpenFabLabEnglish||{});
 const patterns=Object.entries(translations).filter(([key])=>/\{\d+\}/.test(key)).map(([key,value])=>{
  const fields=[...key.matchAll(/\{(\d+)\}/g)].map(match=>match[1]);
  const source=key.split(/\{\d+\}/).map(piece=>piece.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')).join('([\\s\\S]*?)');
  return [new RegExp('^'+source+'$'),fields,value];
 });
 const t=text=>{
  if(language!=='en'||typeof text!=='string')return text;
  if(translations[text])return translations[text];
  for(const [pattern,fields,value]of patterns){const found=pattern.exec(text);if(found){const values=Object.fromEntries(fields.map((key,index)=>[key,found[index+1]]));return value.replace(/\{(\d+)\}/g,(match,key)=>values[key]??match);}}
  return text;
 };
 function node(tag,text,cls){const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;}
 function button(label,action){const b=node('button',t(label));b.type='button';b.addEventListener('click',action);return b;}
 const modules=new Map();let menu=null,scheduled=false;
 function closeMenu(focus=false){if(!menu)return;const trigger=menu.querySelector('.ofl-language-trigger');trigger.setAttribute('aria-expanded','false');const options=menu.querySelector('.ofl-language-options');if(!options.hidden)options.hidden=true;if(focus)trigger.focus();}
 function languageMenu(){
  const group=node('div',undefined,'ofl-lang');group.setAttribute('aria-label','Language / Langue');
  const summary=node('button',undefined,'ofl-language-trigger');summary.type='button';summary.setAttribute('aria-haspopup','menu');summary.setAttribute('aria-expanded','false');summary.setAttribute('aria-label','Language / Langue');summary.append(node('span',language==='en'?'🇬🇧':'🇫🇷'),node('span',language.toUpperCase()),node('span','⌄'));group.append(summary);
  const options=node('div',undefined,'ofl-language-options');options.setAttribute('role','menu');options.hidden=true;group.append(options);
  function open(){options.hidden=false;summary.setAttribute('aria-expanded','true');}
  summary.addEventListener('click',event=>{event.preventDefault();event.stopPropagation();if(options.hidden)open();else closeMenu();});
  summary.addEventListener('keydown',event=>{if(['ArrowDown','ArrowUp'].includes(event.key)){event.preventDefault();open();const list=options.querySelectorAll('button');list[event.key==='ArrowDown'?0:list.length-1].focus();}});
  for(const [lang,label] of [['fr','Français'],['en','English']]){
   const b=button(label,()=>{
    closeMenu();if(language===lang)return;
    const forms=[...document.querySelectorAll('.openfablab-booking-form')];
    if(forms.some(form=>[...form.querySelectorAll('input')].some(input=>input.value))&&!window.confirm(t('Les informations saisies seront effacées. Changer de langue ?')))return;
    try{sessionStorage.setItem(languageKey,lang);}catch(_){}
    // One reload aligns all modules and preserves existing pending-request
    // recovery. Changing language never submits a booking or changes the NAS.
    location.reload();
   });
   b.setAttribute('role','menuitemradio');b.setAttribute('aria-checked',String(language===lang));b.setAttribute('aria-pressed',String(language===lang));b.lang=lang;options.append(b);
  }
  group.addEventListener('keydown',event=>{
   if(event.key==='Escape'){event.preventDefault();event.stopPropagation();closeMenu(true);}
   if(['ArrowDown','ArrowUp','Home','End'].includes(event.key)&&event.target!==summary){event.preventDefault();const list=[...options.querySelectorAll('button')],i=list.indexOf(document.activeElement);list[event.key==='Home'?0:event.key==='End'?list.length-1:(i+(event.key==='ArrowDown'?1:-1)+list.length)%list.length].focus();}
  });
  group.addEventListener('focusout',event=>{if(event.relatedTarget&&!group.contains(event.relatedTarget))closeMenu();});
  return group;
 }
 function reconcile(){
  scheduled=false;
  for(const root of modules.keys())if(!root.isConnected)modules.delete(root);
  const ordered=document.querySelectorAll('.openfablab-reservations[data-environment],[data-ofl-public],[data-openfablab-link]');
  const first=[...ordered].find(root=>modules.has(root)&&!root.hidden&&root.getClientRects().length&&modules.get(root).isConnected);
  if(!cfg.multilingual||!first){menu?.remove();return;}
  menu=menu||languageMenu();const host=modules.get(first);if(menu.parentElement!==host){closeMenu();host.append(menu);}
  const blocked=[...document.querySelectorAll('dialog[open],[aria-modal="true"]:not([hidden])')].some(n=>n.getClientRects().length&&getComputedStyle(n).visibility!=='hidden');menu.inert=blocked;if(blocked)closeMenu();
 }
 function schedule(){if(!scheduled){scheduled=true;queueMicrotask(reconcile);}}
 function ready(root,header,visible=true){if(visible&&header)modules.set(root,header);else modules.delete(root);schedule();}
 const localDate=(value,zone)=>new Intl.DateTimeFormat('sv-SE',{timeZone:zone,year:'numeric',month:'2-digit',day:'2-digit'}).format(value);
 const advance=(day,count)=>{const d=new Date(day+'T12:00:00Z');d.setUTCDate(d.getUTCDate()+count);return d.toISOString().slice(0,10);};
 const monthBefore=day=>{const [year,month,date]=day.split('-').map(Number),last=new Date(Date.UTC(year,month-1,0)).getUTCDate();return new Date(Date.UTC(year,month-2,Math.min(date,last),12)).toISOString().slice(0,10);};
 const monday=day=>{const d=new Date(day+'T12:00:00Z');return advance(day,-((d.getUTCDay()+6)%7));};
 const locale=()=>language==='en'?'en-GB':'fr-FR';
 const dayLabel=day=>new Intl.DateTimeFormat(locale(),{timeZone:'UTC',year:'numeric',month:language==='fr'?'2-digit':'short',day:'2-digit'}).format(new Date(day+'T12:00:00Z'));
 const time=(value,zone)=>new Intl.DateTimeFormat(locale(),{timeZone:zone,hour:'2-digit',minute:'2-digit',hour12:false}).format(new Date(value));
 const dateTime=(value,zone)=>new Intl.DateTimeFormat(locale(),{timeZone:zone,year:'numeric',month:'long',day:'numeric'}).format(new Date(value));
 function eventDialog(item,zone,stale){
  closeMenu();
  const dialog=node('dialog',undefined,'ofl-public-modal');dialog.append(node('h2',item.title),node('p',dateTime(item.start,zone)+' · '+time(item.start,zone)+'–'+time(item.end,zone)));
  const state=Date.now()>=Date.parse(item.end)?'ended':item.signup_open_at&&Date.now()<Date.parse(item.signup_open_at)?'not_open':Date.now()>=Date.parse(item.close_at)?'closed':item.availability_state;
  const labels={available:'Inscriptions ouvertes',waiting:'Liste d’attente ouverte',not_open:'Inscriptions à venir',ended:'Animation terminée'};
  if(item.kind==='animation'){
   if(item.description)dialog.append(node('p',item.description,'ofl-public-description'));
   if(Number.isInteger(item.capacity))dialog.append(node('p',t('Capacité maximale')+' : '+item.capacity));
   dialog.append(node('p',t(labels[state]||'Inscriptions closes')));
  }else{
   dialog.append(node('p',t('Créneau d’ouverture au public du FabLab.')));
   const average=item.attendance_average;
   if(average){
    const weekday=new Intl.DateTimeFormat(locale(),{timeZone:zone,weekday:'long'}).format(new Date(item.start));
    const day=weekday.charAt(0).toLocaleUpperCase(locale())+weekday.slice(1);
    dialog.append(node('p',language==='en'?`${day}: ${average.users} ${average.users===1?'user':'users'} · ${average.visitors} ${average.visitors===1?'visitor':'visitors'} on average`:`${day} : ${average.users} ${average.users===1?'usager':'usagers'} · ${average.visitors} ${average.visitors===1?'visiteur':'visiteurs'} en moyenne`,'ofl-public-average'));
    const period=average.method==='observed_same_weekday_hours_12m_v1'?(language==='en'?'Average calculated over the last 12 months.':'Moyenne calculée sur les 12 derniers mois.'):(language==='en'?'Average calculated over the last 26 weeks.':'Moyenne calculée sur les 26 dernières semaines.');
    dialog.append(node('small',period));
   }
  }
  const href=item.information_url||(['available','waiting'].includes(state)&&!stale?cfg.bookingPage:'');
  if(href){try{const url=new URL(href,location.href);if(['http:','https:'].includes(url.protocol)){
   const a=node('a',t(item.information_url?'Plus d’informations':'Réserver'));if(!item.information_url)url.searchParams.set('ofl_animation',item.service_id);a.href=url.href;dialog.append(a);
  }}catch(_){}}
  dialog.append(button('Fermer',()=>dialog.close()));document.body.append(dialog);dialog.addEventListener('close',()=>dialog.remove());dialog.showModal();
 }
 const mounted=new WeakSet();
 async function mount(root){
  if(mounted.has(root))return;mounted.add(root);
  const kind=root.dataset.oflPublic,env=root.dataset.environment;let data;
  try{const response=await fetch(cfg.api+kind+'?environment='+encodeURIComponent(env),{credentials:'same-origin',cache:'no-store'});if(!response.ok)throw Error();data=await response.json();}
  catch(_){root.replaceChildren(node('p',t('Les informations ne sont pas disponibles pour le moment.')));ready(root,null,false);return;}
  let week=monday(localDate(new Date(),data.timezone));
  function render(){root.replaceChildren();root.lang=language;root.hidden=false;
   if(kind==='machines'){
    const items=data.items.filter(item=>!root.dataset.category||item.category_key===root.dataset.category);
    if(!items.length&&!data.stale){root.hidden=true;ready(root,null,false);return;}
    const titles={resources:['Ressources','Resources'],machines:['Machines','Machines'],equipment:['Équipements','Equipment'],rooms:['Salles','Rooms']};
    const title=(titles[data.resource_label]||titles.resources)[language==='en'?1:0];
    const header=node('div',undefined,'ofl-module-toolbar ofl-resource-toolbar');let host=null;
    if(cfg.showMachinesTitle!==false){header.append(node('h2',title));root.append(header);host=header;}
    if(data.stale)root.append(node('p',t('Les informations ne sont pas récentes. Vérifiez auprès de votre FabLab.'),'ofl-public-warning'));
    for(const item of items){
     const card=node('article',undefined,'ofl-public-machine'),heading=node('div',undefined,'ofl-public-machine-heading');
     if(item.category)heading.append(node('span',item.category,'ofl-public-category'));
     heading.append(node('strong',item.name),node('span',t({operational:'Disponible',maintenance:'En maintenance',out_of_service:'Hors service'}[item.status]),'ofl-public-badge'));
     const line=node('div',undefined,'ofl-public-machine-line');line.append(heading);card.append(line);if(!host)host=line;
     if(item.reason)card.append(node('p',item.reason));if(item.return_estimate)card.append(node('p',t('Retour estimé')+' : '+dayLabel(item.return_estimate)));root.append(card);
    }
    if(!host){const warning=root.querySelector('.ofl-public-warning');if(warning)host=warning;}
    ready(root,host,!!host);
    return;
   }
   const toolbar=node('nav',undefined,'ofl-calendar-toolbar ofl-module-toolbar');toolbar.setAttribute('aria-label',t('Calendrier public'));
   const firstDay=[monthBefore(localDate(new Date(),data.timezone)),data.history_start||data.coverage_start].sort().at(-1),firstWeek=monday(firstDay);
   const previous=button('Semaine précédente',()=>{week=advance(week,-7)<firstWeek?firstWeek:advance(week,-7);render();});previous.disabled=advance(week,-7)<firstWeek;
   const next=button('Semaine suivante',()=>{week=advance(week,7);render();});next.disabled=advance(week,7)>=data.coverage_end;
   toolbar.append(previous,button('Aujourd’hui',()=>{week=monday(localDate(new Date(),data.timezone));render();}),node('strong',language==='fr'?'Du '+dayLabel(week)+' au '+dayLabel(advance(week,6)):dayLabel(week)+' – '+dayLabel(advance(week,6))),next);root.append(toolbar);ready(root,toolbar);
   if(data.stale)root.append(node('p',t('Les informations ne sont pas récentes. Vérifiez auprès de votre FabLab.'),'ofl-public-warning'));
   if(week<data.coverage_start||advance(week,6)>=data.coverage_end)root.append(node('p',t('Cette période n’est pas couverte par le dernier échange.'),'ofl-public-warning'));
   const grid=node('div',undefined,'ofl-week');
   const entries=data.items.flatMap(item=>item.slots?.length?item.slots.map(slot=>({...item,...slot,slots:undefined})):item);
   for(let i=0;i<7;i++){const day=advance(week,i),column=node('section',undefined,'ofl-week-day');column.append(node('h3',new Intl.DateTimeFormat(locale(),{weekday:'short',day:'numeric',month:'short',timeZone:'UTC'}).format(new Date(day+'T12:00:00Z'))));
    const items=entries.filter(e=>day>=firstDay&&localDate(new Date(e.start),data.timezone)===day).sort((a,b)=>a.start.localeCompare(b.start));
    for(const item of items){const b=button('',()=>eventDialog(item,data.timezone,data.stale));b.className='ofl-public-event '+item.kind+(Date.now()>=Date.parse(item.end)?' ended':'');b.append(node('strong',item.title),node('small',time(item.start,data.timezone)+'–'+time(item.end,data.timezone)),node('small',t(item.kind==='openlab'?'OpenLab':'Animation')));column.append(b);}
    if(!items.length)column.append(node('p',t('Aucun événement.')));grid.append(column);
   }root.append(grid);
  }
  render();
 }
 window.OpenFabLabPublicI18n={t,get language(){return language;},extend:map=>Object.assign(translations,map),ready,
  selector:(root)=>{const header=node('div',undefined,'ofl-module-toolbar');header.append(node('h2',t('Réservations des animations')));root.prepend(header);ready(root,header);return header;}};
 window.OpenFabLabPublicI18n.calendar=(root,value)=>{
  if(!value?.ics||typeof value.ics!=='string'||value.ics.length>100000||!value.ics.startsWith('BEGIN:VCALENDAR'))return;
  const group=node('div',undefined,'openfablab-link-buttons');
  const download=node('a',language==='en'?'Add to Apple, Outlook or another calendar (.ics)':'Ajouter à Apple, Outlook ou autre calendrier (.ics)');
  const url=URL.createObjectURL(new Blob([value.ics],{type:'text/calendar;charset=utf-8'}));download.href=url;download.download='animation.ics';group.append(download);
  try{const target=new URL(value.google);if(target.protocol==='https:'&&target.hostname==='calendar.google.com'){
   const google=node('a',t('Google Agenda'));google.href=target.href;google.target='_blank';google.rel='noopener noreferrer';group.append(google);
  }}catch(_){}root.append(group);window.addEventListener('pagehide',()=>URL.revokeObjectURL(url),{once:true});
 };
 if(standalone){standalone.lang=language;standalone.querySelector('h1').textContent=t('Gérer ma réservation');document.title=t('Gérer ma réservation')+' — OpenFabLab';window.OpenFabLabPublicI18n.selector(standalone);}
 function scan(){document.querySelectorAll('[data-ofl-public]').forEach(mount);schedule();}
 window.addEventListener('resize',schedule);
 window.addEventListener('blur',()=>closeMenu());
 document.addEventListener('pointerdown',event=>{if(menu&&!menu.contains(event.target))closeMenu();},true);
 new MutationObserver(scan).observe(document.body,{childList:true,subtree:true,attributes:true,attributeFilter:['hidden','open','aria-modal','aria-hidden','class','style']});scan();
})();
