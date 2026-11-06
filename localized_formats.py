"""Presentation only: no locale-dependent storage, calculations or identifiers."""
from datetime import date,datetime
from decimal import Decimal
from i18n import language

MONTHS={
 'en':'Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec'.split(),
 'es':'ene feb mar abr may jun jul ago sep oct nov dic'.split(),
}

def day(value,code=None):
    code=code or language()
    try:parsed=value if isinstance(value,date) else date.fromisoformat(value)
    except (ValueError,TypeError):return value
    if code=='fr':return parsed.strftime('%d/%m/%Y')
    if code in MONTHS:return str(parsed.day)+' '+MONTHS[code][parsed.month-1]+' '+str(parsed.year)
    return f'{parsed.day}.{parsed.month}.{parsed.year}'

def timestamp(value,code=None):
    code=code or language()
    join={'fr':' à ','en':' at ','de':' um ','es':' a las ','fi':' klo '}.get(code,' ')
    return day(value.date(),code)+join+value.strftime('%H:%M')

def calendar_moment(value, zone):
    """Local schedule values are wall time; aware booking instants are converted once."""
    if not value:return None
    try:parsed=datetime.fromisoformat(value)
    except (ValueError,TypeError):return None
    return parsed.replace(tzinfo=zone) if parsed.tzinfo is None else parsed.astimezone(zone)

def event_display(value, zone):
    """A calendar date is not an instant; do not turn it into a UTC midnight."""
    if not value:return ''
    if len(value)==10:return day(value)
    parsed=calendar_moment(value,zone)
    return timestamp(parsed) if parsed else value

def decimal(value,places=2,code=None):
    code=code or language()
    result=format(Decimal(value),'.'+str(places)+'f')
    return result if code=='en' else result.replace('.',',')
