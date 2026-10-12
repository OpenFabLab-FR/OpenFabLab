/* Same-origin authorized staff search; keep selected people across searches. */
document.querySelectorAll('[data-participant-picker]').forEach(root=>{
  'use strict';
  const input=root.querySelector('[data-participant-query]'),results=root.querySelector('[data-participant-results]');
  const selectedHost=root.querySelector('[data-participant-selected]'),status=root.querySelector('[data-participant-status]');
  const summary=root.querySelector('[data-participant-selection-summary]');
  const prompt='Saisissez un prénom, un nom ou un identifiant pour rechercher un usager.';
  const selected=new Map();let sequence=0,timer,controller;
  const multiple=root.dataset.multiple==='1';
  function choice(person){
    const label=document.createElement('label');label.className='family-person';
    const control=document.createElement('input');control.type=multiple?'checkbox':'radio';
    control.name=root.dataset.name;control.value=person.id;control.checked=selected.has(String(person.id));
    if(!multiple)control.required=true;
    const span=document.createElement('span');span.append(document.createTextNode(person.name));
    const small=document.createElement('small');small.textContent=person.code;span.append(small);label.append(control,span);
    control.addEventListener('change',()=>{
      if(!multiple)selected.clear();
      if(control.checked)selected.set(String(person.id),person);else selected.delete(String(person.id));
      draw(lastResults,lastMore,!input.value.trim());
      const replacement=[...root.querySelectorAll('input[name]')].find(item=>item.value===String(person.id));
      if(replacement)replacement.focus({preventScroll:true});
    });return label;
  }
  let lastResults=[],lastMore=false;
  function draw(people,more,idle=false){
    lastResults=people;lastMore=more;selectedHost.replaceChildren();results.replaceChildren();
    for(const person of selected.values())selectedHost.append(choice(person));
    for(const person of people)if(!selected.has(String(person.id)))results.append(choice(person));
    status.textContent=idle?prompt:(people.length?people.length+' résultat(s)'+(more?' — affinez votre recherche.':'.'):'Aucun résultat.');
    if(summary){summary.hidden=!selected.size;summary.textContent=selected.size+' personne(s) sélectionnée(s).';}
  }
  draw([],false,true);
  input.addEventListener('input',()=>{
    clearTimeout(timer);const requestSequence=++sequence,query=input.value.trim();
    if(controller)controller.abort();
    if(!query){draw([],false,true);return;}
    draw([],false);status.textContent='Recherche en cours…';
    timer=setTimeout(async()=>{
      controller=new AbortController();
      try{
        const response=await fetch(root.dataset.api+'?q='+encodeURIComponent(query),{signal:controller.signal,credentials:'same-origin',cache:'no-store',headers:{Accept:'application/json'}});
        if(!response.ok)throw Error('Recherche indisponible.');const data=await response.json();
        if(requestSequence!==sequence)return;
        draw(data.users.map(p=>({id:String(p.id),name:p.first_name+' '+p.last_name,code:'#'+p.public_id})),data.more);
      }catch(error){if(requestSequence===sequence&&error.name!=='AbortError')status.textContent='Recherche momentanément indisponible. Les personnes sélectionnées sont conservées.';}
    },250);
  });
});
