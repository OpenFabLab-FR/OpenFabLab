"""Stable natural ordering of displayed resource names, not category order."""
import re
import unicodedata

def name_key(value):
    text=''.join(c for c in unicodedata.normalize('NFKD',str(value or '').casefold()) if not unicodedata.combining(c))
    return tuple(int(part) if index%2 else part for index,part in enumerate(re.split(r'(\d+)',text)))

def ordered(rows,name='name',identity='resource_uuid'):
    field=lambda row,key:key(row) if callable(key) else row[key]
    return sorted(rows,key=lambda row:(name_key(field(row,name)),str(field(row,identity))))
