(() => {
 'use strict';
 const dialog=document.querySelector('[data-admin-search]');if(!dialog)return;
 const input=dialog.querySelector('input'),results=dialog.querySelector('[data-admin-search-results]'),message=dialog.querySelector('[data-admin-search-message]');
 const t=text=>window.OFLTranslate?.(text)||text;
 const adminRoot=new URL(dialog.dataset.url,location.href).pathname.replace(/recherche$/,'');
 let controller=null,timer=null,revision=0;
 function open(){document.querySelectorAll('.ui-language-menu[open]').forEach(menu=>menu.open=false);if(!dialog.open)dialog.showModal();input.focus();}
 function close(){dialog.close();}
 document.querySelector('[data-admin-search-open]').addEventListener('click',open);
 dialog.querySelector('[data-admin-search-close]').addEventListener('click',close);
 dialog.addEventListener('close',()=>{revision++;controller?.abort();clearTimeout(timer);input.value='';results.replaceChildren();message.textContent=t('Saisissez au moins deux caractères.');});
 document.addEventListener('keydown',event=>{if((event.metaKey||event.ctrlKey)&&event.key.toLowerCase()==='k'&&!document.querySelector('dialog[open]:not([data-admin-search])')){event.preventDefault();open();}});
 dialog.addEventListener('click',event=>{if(event.target===dialog){const r=dialog.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)close();}});
 dialog.addEventListener('keydown',event=>{
  const links=[...results.querySelectorAll('a')],index=links.indexOf(document.activeElement);
  if(event.key==='ArrowDown'&&links.length){event.preventDefault();links[Math.min(index+1,links.length-1)].focus();}
  if(event.key==='ArrowUp'&&links.length){event.preventDefault();if(index<=0)input.focus();else links[index-1].focus();}
  if(event.key==='Enter'&&document.activeElement===input&&links.length){event.preventDefault();links[0].click();}
 });
 input.addEventListener('input',()=>{revision++;controller?.abort();clearTimeout(timer);const q=input.value.trim(),mine=revision;results.replaceChildren();if(q.length<2){message.textContent=t('Saisissez au moins deux caractères.');return;}
  timer=setTimeout(async()=>{
   controller=new AbortController();const form=new FormData();form.set('q',q);form.set('evolution_csrf',dialog.dataset.csrf);
   try{const response=await fetch(dialog.dataset.url,{method:'POST',body:form,credentials:'same-origin',signal:controller.signal});if(!response.ok)throw Error();const body=await response.json();if(mine!==revision||!dialog.open)return;
    results.replaceChildren();let total=0;
    for(const group of body.groups||[]){const section=document.createElement('section'),title=document.createElement('h3'),list=document.createElement('ul');title.textContent=t(group.label);section.append(title,list);
     for(const item of group.items){const target=new URL(item.url,location.href);if(target.origin!==location.origin||!target.pathname.startsWith(adminRoot))continue;const li=document.createElement('li'),a=document.createElement('a'),strong=document.createElement('strong'),detail=document.createElement('span');a.href=target.href;strong.textContent=item.title;detail.textContent=item.detail;a.append(strong,detail);li.append(a);list.append(li);total++;}results.append(section);}
    message.textContent=total?'':t('Aucun résultat.');
   }catch(error){if(error.name!=='AbortError'&&mine===revision)message.textContent=t('La recherche est momentanément indisponible.');}
  },180);
 });
})();
