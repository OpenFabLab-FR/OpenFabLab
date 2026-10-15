/* Private analysis: bounded search, cancellable requests, scoped pagination. */
(() => {
  'use strict';
  const root = document.querySelector('[data-attendance-analysis]');
  if (!root) return;
  const $ = s => root.querySelector(s), form = $('[data-analysis-form]');
  const make = (tag, text, className) => { const node = document.createElement(tag); if (text !== undefined) node.textContent = text; if (className) node.className = className; return node; };
  const duration = n => `${Math.floor(n / 3600)} h ${Math.floor(n % 3600 / 60)} min`;
  const counted = (value, singular, plural) => `${value} ${value === 1 ? singular : plural}`;
  const date = value => value ? new Date(value).toLocaleDateString('fr-FR', {timeZone: timezone}) : 'Aucune';
  const time = value => new Date(value).toLocaleTimeString('fr-FR', {hour:'2-digit',minute:'2-digit',timeZone: timezone});
  let timer, searchController, dataController, generation = 0, parameters, cursor, timezone = 'Europe/Paris';
  function status(text) { $('[data-analysis-status]').textContent = text; }
  function metric(parent, label, value, detail = '') { const box = make('article', undefined, 'analysis-metric'+(label==='Dernière visite'?' is-date':'')); const number=make('strong',value);number.title=String(value);box.append(make('span',label),number);if(detail)box.append(make('small',detail));parent.append(box); }
  function reset() { generation++; if (dataController) dataController.abort(); cursor = null; $('[data-more]').hidden = true; $('[data-analysis-report]').hidden = true; }
  function updateModes() {
    $('[data-analysis-user]').hidden = form.elements.mode.value !== 'user';
    $('[data-analysis-category]').hidden = form.elements.mode.value !== 'category';
    $('[data-custom-period]').hidden = form.elements.period.value !== 'custom';
    $('[data-analysis-results]').replaceChildren();
  }
  form.addEventListener('change', event => { if (event.target.matches('select,input[type=date]')) { reset(); updateModes(); status('Filtres modifiés : affichez l’analyse pour actualiser les résultats.'); } });
  $('[data-analysis-search]').addEventListener('input', () => {
    clearTimeout(timer); if (searchController) searchController.abort();
    const query = $('[data-analysis-search]').value.trim();
    $('[data-analysis-results]').replaceChildren();
    form.elements.user_id.value = ''; $('[data-selected-user]').textContent = ''; reset();
    $('[data-search-note]').textContent = query ? 'Recherche…' : 'Saisissez un prénom, un nom ou un identifiant.';
    if (!query) return;
    timer = setTimeout(async () => {
      searchController = new AbortController();
      try {
        const response = await fetch(root.dataset.searchUrl + '?q=' + encodeURIComponent(query), {signal:searchController.signal,cache:'no-store'});
        if (!response.ok) throw new Error('Recherche indisponible.');
        const data = await response.json();
        if ($('[data-analysis-search]').value.trim() !== query || form.elements.mode.value !== 'user') return;
        data.users.forEach(user => { const button = make('button',`${user.first_name} ${user.last_name} · #${user.public_id}`,'admin-button secondary compact'); button.type = 'button'; button.addEventListener('click',() => { form.elements.user_id.value = user.id; $('[data-selected-user]').textContent = `${user.first_name} ${user.last_name}`; $('[data-analysis-results]').replaceChildren(); status('Usager sélectionné : affichez l’analyse.'); }); $('[data-analysis-results]').append(button); });
        $('[data-search-note]').textContent = data.more ? 'Précisez la recherche : 25 résultats affichés.' : (data.users.length ? 'Choisissez le compte souhaité.' : 'Aucun compte correspondant.');
      } catch (error) { if (error.name !== 'AbortError') $('[data-search-note]').textContent = 'Recherche indisponible. Réessayez.'; }
    }, 250);
  });
  function bars(container, values, labels, hours = false) {
    container.replaceChildren(); const graph = make('div',undefined,'analysis-bars'+(hours?' hour-bars':''));
    const maximum = Math.max(1,...values);
    values.forEach((value,index) => { const column = make('div',undefined,'analysis-bar'), button = make('button'); button.type='button'; const label = `${labels[index]} : ${hours?duration(value):counted(value,'visite','visites')}`; button.title = label; button.setAttribute('aria-label',label); const bar = make('span'); bar.style.height = `${100*value/maximum}%`; button.append(bar); button.addEventListener('click',() => { $('[data-heat-detail]').textContent=label; }); column.append(button,make('small',labels[index])); graph.append(column); }); container.append(graph);
  }
  function renderHistory(data, append = false) {
    const parent = $('[data-history]'); if (!append) parent.replaceChildren();
    data.passages.forEach(row => { const entry=make('tr',undefined,'analysis-history-row');entry.setAttribute('role','row');
      [date(row.arrival),time(row.arrival),row.departure?time(row.departure):'Présence ouverte',row.seconds===null?'En cours':duration(row.seconds)].forEach((value,index)=>{const cell=make('td',undefined,index===3?'analysis-history-duration':'');cell.dataset.label=['Date','Arrivée','Départ','Durée'][index];cell.setAttribute('role','cell');cell.append(make('span',value,!row.departure&&index===2?'analysis-open-note':''));entry.append(cell);});parent.append(entry); });
    if (!parent.children.length) {const row=make('tr'),cell=make('td','Aucun passage enregistré sur cette période.','analysis-empty');cell.colSpan=4;row.append(cell);parent.append(row);}
    cursor = data.cursor; $('[data-more]').hidden = !cursor;
  }
  function render(data) {
    timezone = data.timezone || 'Europe/Paris';
    $('[data-analysis-title]').textContent = data.scope.label;
    $('[data-analysis-period]').textContent = `${date(data.start)} – ${date(data.end)} à ${time(data.end)} · fuseau ${timezone}`;
    const metrics = $('[data-analysis-metrics]'); metrics.replaceChildren(); const m = data.metrics;
    metric(metrics,'Visites',m.visits); metric(metrics,'Temps cumulé',duration(m.seconds)); metric(metrics,'Durée moyenne',duration(m.mean_seconds)); if(data.scope.mode==='user')metric(metrics,'Dernière visite',date(m.last));
    if (data.scope.mode !== 'user') { metric(metrics,'Usagers distincts',m.distinct); metric(metrics,'Revenus au moins deux fois',m.regular,m.regular_percent === null?'Aucune donnée':`${m.regular_percent} %`); }
    metrics.dataset.count=metrics.children.length;
    $('[data-open-sessions]').hidden=!m.open;$('[data-open-sessions]').textContent=counted(m.open,'présence en cours','présences en cours');
    $('[data-animations-count]').textContent=counted(data.animations.present,'présence renseignée','présences renseignées');
    $('[data-analysis-small]').hidden = !data.small_collective;
    bars($('[data-weekdays]'),m.weekdays,['Lun','Mar','Mer','Jeu','Ven','Sam','Dim']); bars($('[data-hours]'),m.hourly,Array.from({length:24},(_,i)=>`${i}h`),true);
    const heat = $('[data-heat]'); heat.replaceChildren();
    if (m.heat.length) { const grid = make('div',undefined,'analysis-heat'); grid.append(make('small','Jour / heure')); for(let hour=0;hour<24;hour++) grid.append(make('small',`${hour}h`)); const maximum=Math.max(1,...m.heat.flat()); m.heat.forEach((row,day) => { grid.append(make('span',['Lundi','Mardi','Mercredi','Jeudi','Vendredi','Samedi','Dimanche'][day])); row.forEach((value,hour) => { const cell=make('button'); cell.type='button'; const text=`${['Lundi','Mardi','Mercredi','Jeudi','Vendredi','Samedi','Dimanche'][day]}, ${hour}h–${hour+1}h : ${duration(value)}`; cell.title=text;cell.setAttribute('aria-label',text);cell.style.backgroundColor=`hsl(198 38% ${96-38*value/maximum}%)`;cell.addEventListener('click',()=>{$('[data-heat-detail]').textContent=text;});grid.append(cell); }); }); heat.append(grid); }
    const evolution=$('[data-evolution]');evolution.replaceChildren();
    const metricLabel=make('label','Mesure du graphique d’évolution'),metricChoice=make('select');
    [['visits','Visites'],['seconds','Temps cumulé'],['distinct','Usagers distincts']].forEach(([value,label])=>{const option=make('option',label);option.value=value;metricChoice.append(option);});
    metricLabel.append(metricChoice);const series=make('div',undefined,'analysis-evolution');
    function drawEvolution(){series.replaceChildren();const field=metricChoice.value,maximum=Math.max(1,...m.evolution.map(row=>row[field]));
      m.evolution.forEach(row=>{const item=make('article'),values=make('div'),description=`${counted(row.visits,'visite','visites')} · ${duration(row.seconds)} · ${counted(row.distinct,'usager distinct','usagers distincts')}`;
        const track=make('span',undefined,'analysis-evolution-track'),bar=make('span');bar.style.width=`${100*row[field]/maximum}%`;track.append(bar);track.setAttribute('aria-hidden','true');
        values.append(make('span',description),track);item.append(make('strong',row.period),values);series.append(item);});}
    metricChoice.addEventListener('change',drawEvolution);drawEvolution();evolution.append(metricLabel,series);
    const comparison=$('[data-comparison]');comparison.replaceChildren();$('[data-comparison-period]').textContent=`Du ${date(data.previous_start)} au ${date(data.start)}`;
    Object.entries(data.comparison).forEach(([key,row])=>{metric(comparison,{visits:'Visites',seconds:'Temps cumulé',distinct:'Usagers distincts'}[key],key==='seconds'?`${row.delta<0?'−':'+'}${duration(Math.abs(row.delta))}`:`${row.delta>0?'+':''}${row.delta}`,row.percent===null?'Pourcentage non calculable':`${row.percent>0?'+':''}${row.percent} %`);});
    $('[data-cohorts-section]').hidden=data.scope.mode==='user';const cohort=$('[data-cohorts]');cohort.replaceChildren();data.cohorts.forEach(row=>{const block=make('article',undefined,'analysis-cohort');block.append(make('h3',`À ${row.days} jours`),make('p',`${counted(row.eligible,'usager avec recul complet','usagers avec recul complet')} · ${counted(row.immature,'encore en observation','encore en observation')}`),make('p',row.returned===null?'Retours non détaillés pour cet effectif.':`${counted(row.returned,'usager revenu','usagers revenus')} au moins une fois · ${row.repeated} au moins trois fois`));cohort.append(block);});
    $('[data-history-section]').hidden=!data.history;if(data.history)renderHistory(data.history);
    const animations=$('[data-animations]');animations.replaceChildren();
    if(data.scope.mode==='user'){ [['À venir (jusqu’à un an)','upcoming'],['Sur la période (50 dernières maximum)','past']].forEach(([label,key])=>{const group=make('section',undefined,'analysis-animation-group');group.append(make('h3',label));if(!data.animations[key].length)group.append(make('p',key==='upcoming'?'Aucune animation à venir.':'Aucune animation sur cette période.','analysis-empty'));data.animations[key].forEach(row=>{const item=make('article',undefined,'analysis-passage');item.append(make('strong',row.title),make('span',`${row.date} · ${row.hours}`),make('span',row.status));if(key==='past')item.append(make('span',row.presence));group.append(item);});animations.append(group);});}
    else{if(data.scope.mode==='category'){const help=make('details',undefined,'analysis-help');help.append(make('summary','Catégorie des participants'),make('p',data.animations.category_basis));animations.append(help);}if(!data.animations.aggregate.length)animations.append(make('p','Aucune présence renseignée pour cette sélection.','analysis-empty'));data.animations.aggregate.forEach(row=>{const item=make('article',undefined,'analysis-passage');item.append(make('strong',row.title),make('span',counted(row.count,'présence renseignée','présences renseignées')));animations.append(item);});}
    $('[data-analysis-report]').hidden=false;status('Analyse mise à jour.');
  }
  form.addEventListener('submit',async event=>{
    event.preventDefault();reset();const current=generation;parameters=new URLSearchParams(new FormData(form));dataController=new AbortController();status('Calcul de l’analyse…');
    try{const response=await fetch(root.dataset.url+'?'+parameters,{signal:dataController.signal,cache:'no-store'});const data=await response.json();if(!response.ok)throw new Error(data.message||'Analyse indisponible.');if(current===generation)render(data);}
    catch(error){if(error.name!=='AbortError')status(error.message);}
  });
  $('[data-more]').addEventListener('click',async()=>{if(!cursor)return;const current=generation;const values=new URLSearchParams(parameters);values.set('cursor',cursor);const button=$('[data-more]');button.disabled=true;try{const response=await fetch(root.dataset.url+'?'+values,{cache:'no-store'});if(!response.ok)throw new Error();const data=await response.json();if(current===generation)renderHistory(data,true);}catch{status('Les passages supplémentaires n’ont pas pu être chargés.');}finally{button.disabled=false;}});
  updateModes();
})();
