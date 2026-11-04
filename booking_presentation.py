"""Pure grouping of existing booking rows; never changes business state."""
from i18n import native as __ui_native__
from collections import OrderedDict
from datetime import datetime, timezone


def sections(bookings, reservation_status, now=None):
    groups = {key:OrderedDict() for key in ('confirmed','offer_pending','waitlisted','closed')}
    offers = OrderedDict()
    current=now or datetime.now(timezone.utc)
    for booking in bookings:
        status=reservation_status(booking)
        key=status if status in groups else 'closed'
        request=booking.get('group_uuid') or booking['external_uuid']
        groups[key].setdefault(request,[]).append(booking)
        expiry=booking.get('offer_expires_at')
        if status=='offer_pending' and expiry and datetime.fromisoformat(expiry.replace('Z','+00:00'))>current:
            offer=offers.setdefault((request,expiry),dict(count=0,expires=expiry))
            offer['count']+=1
    labels=(__ui_native__('Participants confirmés'),__ui_native__('Places proposées, en attente de réponse'),__ui_native__('Liste d’attente'),__ui_native__('Inscriptions annulées, refusées et expirées'))
    result=[dict(key=key,label=label,closed=key=='closed',groups=list(value.values()),
                 count=sum(map(len,value.values()))) for (key,value),label in zip(groups.items(),labels)]
    return result,list(offers.values())
