(() => {
  const el=document.querySelector('[data-online-tasks]');if(!el)return;
  fetch(el.dataset.url,{credentials:'same-origin',cache:'no-store'}).then(r=>r.ok?r.json():null).then(v=>{
    if(!v||!Number.isSafeInteger(v.total)||v.total<0)return;
    el.querySelector('[data-task-total]').textContent=String(v.total);
    const groups=el.querySelector('[data-task-groups]');
    const icons=new Map([...el.querySelectorAll('template[data-task-icon]')].map(icon=>[icon.dataset.taskIcon,icon]));
    for(const row of Array.isArray(v.groups)?v.groups:[]){
      if(!row||typeof row.label!=='string'||typeof row.url!=='string'||!Number.isSafeInteger(row.count)||row.count<1)continue;
      const u=new URL(row.url,location.href);
      if(u.origin!==location.origin||u.protocol!==location.protocol)continue;
      const li=document.createElement('li'), a=document.createElement('a');
      const icon=document.createElement('span'), label=document.createElement('span'), count=document.createElement('span');
      a.href=u.href; a.className='v218-task-row';
      icon.className='v218-task-icon'; icon.append((icons.get(row.kind)||icons.get('tasks')).content.cloneNode(true));
      label.textContent=row.label;
      count.className='v218-task-badge'; count.textContent=String(row.count);
      a.append(icon,label,count); li.append(a); groups.append(li);
    }
    groups.hidden=!groups.children.length;
    el.querySelector('[data-task-empty]').hidden=!!groups.children.length;
    el.hidden=false;
  }).catch(()=>{});
})();
