/* No HTML injection: release notes and agent codes are rendered as text only. */
(() => {
 'use strict';
 const root=document.querySelector('[data-updates]');if(!root)return;
 const t=text=>window.OFLTranslate?.(text)||text,message=root.querySelector('[data-update-message]');
 const agent=root.querySelector('[data-update-agent]'),upload=root.querySelector('[data-update-upload]');
 let job=null,confirmation=null,timer=null,busy=false,following=false,retries=0,discovered=false;
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
  refused:'Opération refusée',cancelled:'Préparation annulée'};
 function show(value,operation){
  if(operation==='status'){
   agent.textContent=t('Agent local connecté');
   upload.querySelector('fieldset').disabled=value.local_zip!==1;
   if(value.local_zip!==1)message.textContent=t('Cet agent ne prend pas encore en charge l’import ZIP.');
   const history=root.querySelector('[data-update-history]'),list=root.querySelector('[data-update-history-list]');
   list.replaceChildren();
   for(const item of value.history||[]){
    const li=document.createElement('li');li.textContent=[item.version,item.source_schema!=null?'SQLite '+item.source_schema+' → '+item.target_schema:'',t(labels[item.result]||'État de l’opération')].filter(Boolean).join(' · ');list.append(li);
   }
   history.hidden=!list.children.length;
  }
  if(value.last_error){message.textContent=t('L’agent a refusé la demande.')+' '+value.last_error;}
  if(value.latest){
   root.querySelector('[data-update-release]').hidden=false;
   root.querySelector('[data-update-version]').textContent=value.latest;
   root.querySelector('[data-update-notes]').textContent=value.notes||'';
   const link=root.querySelector('[data-update-release-link]');
   if(/^https:\/\/github\.com\/OpenFabLab-FR\/OpenFabLab\/releases\/tag\/v\d+\.\d+\.\d+$/.test(value.page||''))link.href=value.page;
   message.textContent=t(value.newer?'Une nouvelle version stable est disponible.':'Aucune version stable plus récente.');
  }
  if(value.accepted){message.textContent=t('Opération lancée. Le suivi se met à jour automatiquement.');following=true;schedule();return;}
  if(!value.phase)return;
  const compatibility=root.querySelector('[data-update-compatibility]');
  if(value.version&&Number.isInteger(value.source_schema)&&Number.isInteger(value.target_schema)){
   compatibility.hidden=false;compatibility.textContent=t('Version préparée')+' : '+value.version+' · '+(value.source_schema===value.target_schema?'SQLite '+value.target_schema+' · '+t('Aucune migration de schéma'):'SQLite '+value.source_schema+' → '+value.target_schema);
  }
  job=value.id||null;confirmation=value.confirmation||null;
  root.querySelector('[data-update-confirmation]').hidden=!(value.result==='ready'&&confirmation);
  root.querySelector('[data-update-cancel-stale]').hidden=!(value.result==='ready'&&!confirmation);
  root.querySelector('[data-update-progress]').hidden=!value.events;
  root.querySelector('[data-update-phase]').textContent=t(labels[value.phase]||'État de l’opération')+(value.code?' · '+value.code:'');
  root.querySelector('[data-update-candidate-notes]').textContent=value.notes||'';
  root.querySelector('[data-update-probe]').hidden=!value.isolated_probe_pending;
  const list=root.querySelector('[data-update-events]');list.replaceChildren();
  for(const event of value.events||[]){const item=document.createElement('li');item.textContent=t(labels[event.phase]||'Contrôle')+(event.code!=='OK'?' · '+event.code:'');list.append(item);}
  if(value.recovery_required)message.textContent=t('L’état actuel est conservé. N’installez pas une ancienne version et ne restaurez pas automatiquement une sauvegarde.');
  following=['preparing','installing','recovering'].includes(value.result);
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
   const body=await response.json();if(!body.ok)throw new Error(t(body.message||'Opération refusée.')+(body.code?' · '+body.code:''));retries=0;show(body.value,operation);
  }catch(error){
   if(operation==='status'){agent.textContent=t('Agent local indisponible');if(following&&++retries<40)schedule();}
   if(operation==='discover')discovered=false;
   message.textContent=(operation==='status'||operation==='install'?t('Le suivi est momentanément indisponible. Cela ne prouve pas l’échec de l’installation. Actualisez le suivi sans relancer l’installation.')+' ':'')+error.message;
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
