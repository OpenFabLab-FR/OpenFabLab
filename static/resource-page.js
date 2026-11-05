/* Local section navigation only; never changes a resource or saves a form. */
(()=>{'use strict';
 const sections={general:'general',booking_settings:'bookings',legacy_prices:'bookings',condition:'availability',
  intervention:'interventions',reminder:'reminders',reminder_reschedule:'reminders',reminder_cancel:'reminders',reminder_close:'reminders',
  import:'documents',attach:'documents',update:'documents',detach:'documents',archive:'advanced',restore:'advanced',delete:'advanced',handover:'loans',return:'loans'};
 function reveal(){let id='';try{id=decodeURIComponent(location.hash.slice(1));}catch(_){return;}
  const error=document.querySelector('[data-resource-error]');if(error)id=sections[error.dataset.resourceError]||id;
  const target=document.getElementById(id);if(!target)return;
  for(let current=target;current;current=current.parentElement)if(current.tagName==='DETAILS')current.open=true;
  requestAnimationFrame(()=>target.scrollIntoView({block:'start'}));
 }
 window.addEventListener('hashchange',reveal);reveal();
})();
