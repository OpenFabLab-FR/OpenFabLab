'use strict';
const uiLanguage=JSON.parse(document.querySelector('#ui-language-data')?.textContent||'{}');
const uiPatterns=Object.entries(uiLanguage.catalog||{}).filter(([key])=>/\{\d+\}/.test(key)).map(([key,value])=>{
 const fields=[...key.matchAll(/\{(\d+)\}/g)].map(match=>match[1]);
 const source=key.split(/\{\d+\}/).map(piece=>piece.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')).join('([\\s\\S]*?)');
 return [new RegExp('^'+source+'$'),fields,value];
});
window.OFLTranslate=text=>{
 if(uiLanguage.catalog?.[text])return uiLanguage.catalog[text];
 if(typeof text!=='string')return text;
 for(const [pattern,fields,value]of uiPatterns){const found=pattern.exec(text);if(found){const values=Object.fromEntries(fields.map((key,index)=>[key,found[index+1]]));return value.replace(/\{(\d+)\}/g,(match,key)=>values[key]??match);}}
 return text;
};
document.querySelectorAll('.ui-language-form').forEach(form=>form.addEventListener('submit',event=>{
 if(document.querySelector('form[data-ui-dirty="1"]')&&!window.confirm(window.OFLTranslate('Changer de langue effacera les informations non enregistrées. Continuer ?'))){event.preventDefault();}
}));
document.addEventListener('input',event=>{const form=event.target.closest('form');if(form&&!form.classList.contains('ui-language-form'))form.dataset.uiDirty='1';});
if(uiLanguage.idleEnabled){
 let lastActivity=Date.now();
 for(const event of ['pointerdown','keydown','input','change','touchstart'])document.addEventListener(event,()=>{lastActivity=Date.now();},{passive:true,capture:true});
 window.setInterval(()=>{if(Date.now()-lastActivity>=Number(uiLanguage.idle||10)*60000)document.querySelector('#ui-idle-form')?.requestSubmit();},1000);
}
document.querySelectorAll('[data-machine-dialog]').forEach(button=>button.addEventListener('click',()=>{
 const dialog=document.querySelector('#machine-information');if(dialog?.showModal)dialog.showModal();
}));
document.querySelectorAll('[data-close-dialog]').forEach(button=>button.addEventListener('click',()=>button.closest('dialog')?.close()));
document.querySelectorAll('[data-resource-color]').forEach(box=>{
 const input=box.querySelector('[name=color]'),fallback=box.querySelector('[name=color_default]');
 fallback.addEventListener('change',()=>{input.disabled=fallback.checked;});
});

document.querySelectorAll('[data-machine-condition]').forEach(form=>{
 const state=form.elements.status,fields=form.querySelector('.machine-unavailable-fields');
 const refresh=()=>{fields.hidden=state.value==='operational';};
 state.addEventListener('change',()=>{if(state.value==='operational'){form.elements.public_reason.value='';form.elements.return_estimate.value='';}refresh();});refresh();
});
document.querySelectorAll('[data-opening-form]').forEach(form=>{
 const refresh=()=>{const closed=form.elements.kind.value==='closed';
  form.querySelectorAll('[data-opening-hours]').forEach(box=>{box.hidden=closed;box.querySelectorAll('input').forEach(input=>{input.disabled=closed;if(input.type==='time')input.required=!closed;});});
  form.querySelector('[data-opening-closed]').hidden=!closed;
 };form.elements.kind.addEventListener('change',refresh);refresh();
});
document.querySelectorAll('[data-calendar-maintenance]').forEach(input=>input.addEventListener('change',()=>input.form.requestSubmit()));
function revealIntervention(){if(!location.hash.startsWith('#intervention-'))return;const item=document.getElementById(location.hash.slice(1));if(item instanceof HTMLDetailsElement){item.open=true;item.scrollIntoView({block:'nearest'});}}
window.addEventListener('hashchange',revealIntervention);revealIntervention();
document.addEventListener('keydown',event=>{if(event.key==='Escape')document.querySelectorAll('.ui-language-menu[open]').forEach(menu=>{menu.open=false;menu.querySelector('summary').focus();});});
document.addEventListener('pointerdown',event=>document.querySelectorAll('.ui-language-menu[open]').forEach(menu=>{if(!menu.contains(event.target))menu.open=false;}));
