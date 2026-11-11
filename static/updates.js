/* No HTML injection: release notes and agent codes are rendered as text only. */
(() => {
 'use strict';
 const root=document.querySelector('[data-updates]');if(!root)return;
 const t=text=>window.OFLTranslate?.(text)||text,message=root.querySelector('[data-update-message]');
 const agent=root.querySelector('[data-update-agent]'),upload=root.querySelector('[data-update-upload]');
 let job=null,confirmation=null,timer=null,busy=false,following=false,retries=0,discovered=false,awaiting=null;
 const labels={checking_source:'Vérification de l’installation',downloading:'Téléchargement officiel',validating_zip:'Vérification de l’archive ZIP',
  checking_space_and_access:'Espace et accès',building_image:'Construction de l’image',
  isolated_migration_and_health:'Essai isolé de migration et de démarrage',verifying_source_unchanged:'Contrôle final de la source',
  ready:'Prêt à installer',checking_before_install:'Vérification avant installation',coherent_hot_backup:'Sauvegarde avant interruption',
  last_source_check_before_stop:'Contrôle final de la source',
  stopping_source:'Arrêt contrôlé',complete_cold_pre_backup:'Sauvegarde complète PRE',migration:'Migration SQLite',
  verifying_migration:'Intégrité et conservation des données',installing_runtime:'Installation du runtime',starting_target:'Démarrage',
  http_health_and_identity:'Santé HTTP et identité',data_and_private_state:'Données et fichiers privés',
  wordpress_normal_test:'Échanges WordPress Normal/Test',post_relay_integrity:'Contrôle après synchronisation',complete_post_backup:'Sauvegarde complète POST',
  success:'Mise à jour réussie',failed_preserved:'Échec : état préservé, décision humaine nécessaire',
  refused:'Opération refusée',cancelled:'Préparation annulée',resuming_verified_target:'Reprise de la cible vérifiée'};
 const installTail=['coherent_hot_backup','last_source_check_before_stop','stopping_source','complete_cold_pre_backup',
  'migration','verifying_migration','installing_runtime','starting_target','http_health_and_identity','data_and_private_state',
  'wordpress_normal_test','post_relay_integrity','complete_post_backup'];
 const activeResults=['preparing','installing','recovering'];
 const stateLabels={done:'Réussie',active:'En cours',waiting:'En attente',refused:'Refusée',failed:'Échouée',interrupted:'Interrompue'};
 const symbols={done:'✓',active:'',waiting:'○',refused:'⊘',failed:'✕',interrupted:'■'};
 const fill=(text,...args)=>t(text).replace(/\{(\d+)\}/g,(_,n)=>String(args[Number(n)]??''));
 const safeCode=value=>/^[A-Z][A-Z0-9_]{1,100}$/.test(value||'')?value:'';
 function explain(code){
  const text={
   SOURCE_SCHEMA_NOT_SUPPORTED:'Le schéma de départ n’est pas pris en charge par ce paquet.',
   UPDATE_MANIFEST_INCOMPATIBLE:'Le manifeste du ZIP n’est pas compatible avec cet agent.',
   UPDATE_MANIFEST_FILE_LIST_MISMATCH:'Le contenu du ZIP ne correspond pas à son manifeste.',
   MIGRATION_SOURCE_SCHEMA_REFUSED:'La migration ne peut pas partir de ce schéma SQLite.',
   ISOLATED_GUNICORN_START_FAILED:'La version candidate n’a pas démarré dans l’essai isolé.',
  }[code]||(/_SPACE_INSUFFICIENT$/.test(code)?'L’espace disponible ne permet pas de poursuivre en sécurité.':
       'Consultez le code de contrôle et le rapport avant de réessayer.');
  return t(text)+(code?' · '+code:'');
 }
 function renderSteps(value){
  const list=root.querySelector('[data-update-events]'),counter=root.querySelector('[data-update-count]');
  const events=(value.events||[]).filter(event=>event.phase in labels &&
      !['success','refused','failed_preserved','cancelled'].includes(event.phase));
  const running=activeResults.includes(value.result),last=events.at(-1);
  const failure=value.phase==='refused'?'refused':value.phase==='failed_preserved'?'failed':null;
  const state=events.map((event,index)=>({phase:event.phase,state:index===events.length-1?
      failure|| (value.phase==='cancelled'||value.result==='interrupted'?'interrupted':running?'active':'done'):'done'}));
  if(failure&&!last)state.push({phase:value.phase,state:failure});
  // Append only phases known from the established agent plan. Preparation
  // before a manifest is read has no reliable denominator.
  if(value.result==='ready'||value.result==='installing'){
   const planned=['checking_before_install',...(value.isolated_probe_pending?['building_image','isolated_migration_and_health']:[]),
       ...installTail.filter(phase=>phase!=='migration'||value.migration_required===true)];
   const completedPlan=new Set(events.slice(events.findIndex(e=>e.phase==='checking_before_install')<0?
       events.length:events.findIndex(e=>e.phase==='checking_before_install')).map(e=>e.phase));
   for(const phase of planned)if(!completedPlan.has(phase))state.push({phase,state:'waiting'});
  }
  const index=state.findIndex(step=>step.state==='active');
  counter.textContent=index>=0?
    (value.result==='installing'&&Number.isInteger(value.target_schema)?fill('Étape {0} sur {1}',index+1,state.length):fill('Étape {0}',index+1)):
    state.length&&value.result==='success'?fill('{0} étapes terminées',state.length):'';
  list.replaceChildren();
  for(const step of state){
   const li=document.createElement('li'),mark=document.createElement('span'),label=document.createElement('strong'),note=document.createElement('small');
   li.dataset.stepState=step.state;mark.className='update-step-mark';mark.textContent=symbols[step.state];mark.setAttribute('aria-hidden','true');
   label.textContent=t(labels[step.phase]||'Contrôle');note.textContent=t(stateLabels[step.state]);
   if(step.state==='failed'||step.state==='refused')note.textContent+=' · '+explain(safeCode(value.code));
   if(step.state==='active')li.setAttribute('aria-current','step');
   li.append(mark,label,note);list.append(li);
  }
 }
 function showSuccess(value,confirmed){
  const panel=root.querySelector('[data-update-success]'),backups=root.querySelector('[data-update-backups]');
  panel.hidden=!confirmed;
  if(!confirmed)return;
  const version=value.version?'V'+value.version:'';
  const actual=root.querySelector('[data-update-installed]').textContent.trim();
  root.querySelector('[data-update-success-version]').textContent=
      actual===version?fill('Version installée : {0}',actual):fill('Version confirmée par l’agent : {0}',version);
  backups.replaceChildren();
  for(const [key,label] of [['pre_backup','Sauvegarde complète PRE'],['post_backup','Sauvegarde complète POST']]){
   if(value[key]){const li=document.createElement('li');li.textContent='✓ '+t(label);backups.append(li);}
  }
 }
 function show(value,operation){
  if(operation==='status'){
   agent.textContent=t('Agent local connecté');
   if(/^\d+\.\d+\.\d+$/.test(value.agent_version||'') && Number.isInteger(value.agent_protocol))
    agent.textContent+=' · v'+value.agent_version+' · '+fill('Protocole {0}',value.agent_protocol);
   if(/^V\d+\.\d+\.\d+$/.test(value.web_version||''))root.querySelector('[data-update-installed]').textContent=value.web_version;
   if(following||retries)message.textContent='';
   upload.querySelector('fieldset').disabled=value.local_zip!==1;
   if(value.local_zip!==1)message.textContent=t('Cet agent ne prend pas encore en charge l’import ZIP.');
   const history=root.querySelector('[data-update-history]'),list=root.querySelector('[data-update-history-list]');
   list.replaceChildren();
   for(const item of value.history||[]){
    const li=document.createElement('li');li.textContent=[item.version,item.source_schema!=null?'SQLite '+item.source_schema+' → '+item.target_schema:'',t(labels[item.result]||'État de l’opération')].filter(Boolean).join(' · ');list.append(li);
   }
   history.hidden=!list.children.length;
  }
  if(operation==='status'&&awaiting){
   const stale=awaiting.operation==='install'?(value.id!==awaiting.job||value.result==='ready'):(!value.id||value.id===awaiting.job);
   if(stale&&!value.last_error){
    message.textContent=t('Opération lancée. Le suivi se met à jour automatiquement.');
    if(++awaiting.polls<40)schedule();else awaiting=null;
    return;
   }
   if(stale&&value.last_error){
    awaiting=null;following=false;message.textContent=t('L’agent a refusé la demande.')+' '+explain(safeCode(value.last_error));return;
   }
   awaiting=null;
  }
  const confirmed=value.result==='success'&&value.code==='UPDATE_SUCCESS';
  if(value.last_error&&!confirmed){message.textContent=t('L’agent a refusé la demande.')+' '+explain(safeCode(value.last_error));}
  if(value.latest){
   root.querySelector('[data-update-release]').hidden=false;
   root.querySelector('[data-update-version]').textContent=value.latest;
   root.querySelector('[data-update-notes]').textContent=value.notes||'';
   const link=root.querySelector('[data-update-release-link]');
   if(/^https:\/\/github\.com\/OpenFabLab-FR\/OpenFabLab\/releases\/tag\/v\d+\.\d+\.\d+$/.test(value.page||''))link.href=value.page;
   message.textContent=t(value.newer?'Une nouvelle version stable est disponible.':'Aucune version stable plus récente.');
  }
  if(value.accepted){awaiting={operation,job,polls:0};showSuccess(value,false);message.textContent=t('Opération lancée. Le suivi se met à jour automatiquement.');following=true;schedule();return;}
  if(!value.phase)return;
  const compatibility=root.querySelector('[data-update-compatibility]');
  if(value.version&&Number.isInteger(value.source_schema)&&Number.isInteger(value.target_schema)){
   compatibility.hidden=false;compatibility.textContent=t('Version préparée')+' : '+value.version+' · '+(value.source_schema===value.target_schema?'SQLite '+value.target_schema+' · '+t('Aucune migration de schéma'):'SQLite '+value.source_schema+' → '+value.target_schema);
  }
  job=value.id||null;confirmation=value.confirmation||null;
  root.querySelector('[data-update-confirmation]').hidden=!(value.result==='ready'&&confirmation);
  root.querySelector('[data-update-cancel-stale]').hidden=!(value.result==='ready'&&!confirmation);
  root.querySelector('[data-update-progress]').hidden=!value.events;
  const code=safeCode(value.code);
  root.querySelector('[data-update-phase]').textContent=t(value.phase==='success'&&!confirmed?'Confirmation finale en attente':labels[value.phase]||'État de l’opération')+(code?' · '+code:'');
  root.querySelector('[data-update-candidate-notes]').textContent=value.notes||'';
  root.querySelector('[data-update-probe]').hidden=!value.isolated_probe_pending;
  renderSteps(value);
  showSuccess(value,confirmed);
  if(confirmed)message.textContent='';
  if(value.recovery_required)message.textContent=t('L’état actuel est conservé. N’installez pas une ancienne version et ne restaurez pas automatiquement une sauvegarde.');
  else if(value.phase==='refused')message.textContent=t('Un contrôle a échoué. Consultez l’étape et le code indiqués avant de réessayer.');
  following=activeResults.includes(value.result);
  if(following)schedule();else clearTimeout(timer);
 }
 function schedule(){clearTimeout(timer);timer=setTimeout(()=>send('status'),1800);}
 async function send(operation,file){
  if(busy)return;scheduleClear();busy=true;
  const data=new FormData();data.set('operation',operation);data.set('evolution_csrf',root.dataset.csrf);
  if(file)data.set('candidate',file);
  if(['install','cancel'].includes(operation)){data.set('id',job||'');}
  if(operation==='install'){data.set('confirmation',confirmation||'');data.set('consent','INSTALLER');}
  try{
   const response=await fetch(root.dataset.url,{method:'POST',body:data,credentials:'same-origin',headers:{Accept:'application/json'}});
   const body=await response.json();
   if(!body.ok){
    const code=safeCode(body.code);
    if((operation==='status'||operation==='install')&&(!code||code==='AGENT_UNAVAILABLE_MANUAL_UPDATE_AVAILABLE'))throw new Error('agent unavailable');
    awaiting=null;following=false;
    message.textContent=body.message?t(body.message)+(code?' · '+code:''):explain(code);
    return;
   }
   show(body.value,operation);retries=0;
  }catch{
   if(operation==='status'||operation==='install'){
    if(operation==='install')awaiting={operation,job,polls:0};
    agent.textContent=t('Agent local indisponible');if(operation==='install'||following&&++retries<40){following=true;schedule();}
   }
   if(operation==='discover')discovered=false;
   message.textContent=operation==='status'||operation==='install'?
    t('Le suivi est momentanément indisponible. Cela ne prouve pas l’échec de l’installation. Actualisez le suivi sans relancer l’installation.'):
    t('La demande n’a pas pu être vérifiée. Réessayez après avoir rétabli la connexion.');
  }
  finally{busy=false;}
 }
 function scheduleClear(){clearTimeout(timer);}
 root.querySelectorAll('[data-update-operation]').forEach(button=>button.addEventListener('click',()=>send(button.dataset.updateOperation)));
 root.querySelectorAll('[data-update-mode]').forEach(button=>button.addEventListener('click',()=>{
  const mode=button.dataset.updateMode;
  for(const item of root.querySelectorAll('[data-update-mode]')){const active=item===button;item.setAttribute('aria-pressed',String(active));item.classList.toggle('primary',active);item.classList.toggle('secondary',!active);}
  for(const panel of root.querySelectorAll('[data-update-panel]'))panel.hidden=panel.dataset.updatePanel!==mode;
  if(mode==='official'&&!busy&&!discovered&&!root.querySelector('[data-update-operation="discover"]').disabled){discovered=true;send('discover');}
 }));
 upload.addEventListener('submit',event=>{
  event.preventDefault();const file=upload.elements.candidate.files[0];
  if(!file||file.size>64*1024*1024){message.textContent=t('Choisissez un ZIP de 64 Mio maximum.');return;}
  send('prepare_zip',file);
 });
 root.querySelector('[data-update-confirmation]').addEventListener('submit',event=>{event.preventDefault();if(event.currentTarget.reportValidity())send('install');});
 if(root.querySelector('[data-update-operation="status"]')&&!root.querySelector('[data-update-operation="status"]').disabled)send('status');
})();
