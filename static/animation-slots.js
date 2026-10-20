(function () {
  'use strict';
  const mode = document.getElementById('booking-mode');
  if (!mode) return;
  const inputs = ['start-time','end-time','slot-duration','slot-gap','slot-capacity'].map(id => document.getElementById(id));
  const preview = document.getElementById('slot-preview');
  const capacity = document.getElementById('expected-participants');
  const existing = JSON.parse(document.getElementById('existing-slot-capacities')?.textContent || '[]');
  const initialDefault = Number(document.getElementById('slot-capacity').value);
  const date = document.getElementById('service-date'), initialDate = date.value;
  const overrides = new Map(existing.filter(s => s.capacity !== initialDefault).map(s => [s.label,s.capacity]));
  function update() {
    const enabled = mode.value === 'slots';
    document.querySelectorAll('[data-slot-field]').forEach(node => { node.hidden = !enabled; });
    capacity.readOnly = enabled;
    if (!enabled) return;
    const minute = value => /^\d{2}:\d{2}$/.test(value) ? Number(value.slice(0,2))*60+Number(value.slice(3)) : NaN;
    const [a,b,d,g,c] = inputs.map(node => node.value);
    const start=minute(a), end=minute(b), duration=Number(d), gap=Number(g), count=Number(c);
    preview.replaceChildren();
    if (![duration,gap,count].every(Number.isInteger) || duration<=0 || gap<0 || count<=0 || !(end-start>=duration)) {
      preview.textContent = 'Renseignez des horaires valides, une durée et capacité positives et un battement positif ou nul.'; return;
    }
    const list = document.createElement('ul'); list.className='animation-slot-preview';
    const format = m => String(Math.floor(m/60)).padStart(2,'0')+':'+String(m%60).padStart(2,'0');
    let total=0, places=0;
    for (let time=start;time+duration<=end;time+=duration+gap) {
      const label=format(time)+'–'+format(time+duration), seats=(date.value===initialDate ? overrides.get(label) : undefined) ?? count;
      const item=document.createElement('li');item.textContent=label+' · '+seats+' place(s)'; list.appendChild(item);total++;places+=seats;
    }
    preview.appendChild(list);
    const summary=document.createElement('p');summary.textContent=total+' créneaux · total : '+places+' places'+(overrides.size ? ' · capacités particulières conservées' : '');
    preview.appendChild(summary); capacity.value=places;
  }
  [...inputs,mode,date].forEach(node => node.addEventListener('input',update)); update();
})();
