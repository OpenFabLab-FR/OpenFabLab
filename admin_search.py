"""Bounded local search. Role/module filtering happens before SQL, not in JS."""
import sqlite3
import unicodedata
from time import monotonic
from urllib.parse import quote


def folded(value):
    return ''.join(c for c in unicodedata.normalize('NFKD',str(value or '').casefold())
                   if not unicodedata.combining(c))


def search(db,query,role,modules):
    if role not in ('admin','moderator'):
        raise PermissionError('Recherche réservée à l’équipe.')
    query=str(query or '').strip()
    if not 2<=len(query)<=80 or any(ord(c)<32 for c in query):
        return []
    escaped='%'+folded(query).replace('\\','\\\\').replace('%','\\%').replace('_','\\_')+'%'
    groups=[]
    deadline=monotonic()+.15
    db.set_progress_handler(lambda:int(monotonic()>deadline),10000)
    # SQLite's built-in NOCASE only handles ASCII; local names in all five
    # interface languages remain searchable without adding an index or table.
    db.create_function('ofl_search_fold',1,folded,deterministic=True)
    def add(label,sql,make):
        rows=db.execute(sql,(escaped,)).fetchall()
        if rows:
            groups.append(dict(label=label,items=[make(dict(row)) for row in rows]))
    try:
        if modules.get('users'):
            add('Usagers',"SELECT id,first_name,last_name,public_id FROM users WHERE ofl_search_fold(first_name||' '||last_name||' '||public_id) LIKE ? ESCAPE '\\' ORDER BY active DESC,last_name,first_name LIMIT 8",
                lambda r:dict(title=r['first_name']+' '+r['last_name'],detail=r['public_id'],url='/admin/usagers/'+str(r['id'])+'/suivi'))
        if modules.get('resources') or modules.get('maintenance'):
            add('Ressources',"SELECT resource_uuid,name,archived_at FROM resources WHERE ofl_search_fold(name) LIKE ? ESCAPE '\\' ORDER BY (archived_at IS NOT NULL),name LIMIT 8",
                lambda r:dict(title=r['name'],detail='Archivée' if r['archived_at'] else 'Ressource',url='/admin/ressources?archived=1#resource-'+quote(r['resource_uuid'],safe='')))
        if modules.get('activities'):
            add('Animations',"SELECT id,title,service_date FROM fablab_services WHERE service_type='animation' AND ofl_search_fold(title) LIKE ? ESCAPE '\\' ORDER BY service_date DESC LIMIT 8",
                lambda r:dict(title=r['title'],detail=r['service_date'],url='/admin/animations/'+str(r['id'])+'/inscriptions'))
        if modules.get('resources'):
            add('Réservations',"SELECT b.booking_uuid,r.name,b.starts_at FROM resource_bookings b JOIN resources r USING(resource_uuid) WHERE ofl_search_fold(r.name) LIKE ? ESCAPE '\\' ORDER BY b.starts_at DESC LIMIT 8",
                lambda r:dict(title=r['name'],detail=r['starts_at'],url='/admin/ressources/reservations#reservation-'+quote(r['booking_uuid'],safe='')))
        if modules.get('maintenance'):
            add('Interventions',"SELECT i.resource_uuid,i.description,i.performed_on,r.name FROM machine_interventions i JOIN resources r USING(resource_uuid) WHERE ofl_search_fold(r.name||' '||i.description) LIKE ? ESCAPE '\\' ORDER BY i.performed_on DESC LIMIT 8",
                lambda r:dict(title=r['name'],detail=r['description'][:140],url='/admin/ressources/'+quote(r['resource_uuid'],safe='')+'/fiche#interventions'))
        if role=='admin' and modules.get('billing'):
            add('Clients et structures',"SELECT id,contact_name,structure_name,city FROM billing_clients WHERE ofl_search_fold(structure_name||' '||contact_name) LIKE ? ESCAPE '\\' ORDER BY structure_name,contact_name,id LIMIT 8",
                lambda r:dict(title=r['structure_name'] or r['contact_name'],detail=r['contact_name'] if r['structure_name'] else r['city'],url='/admin/facturation/clients/'+str(r['id'])+'/modifier'))
            add('Devis, factures et locations',"""SELECT b.id,b.title,b.quote_number,b.invoice_number FROM billing_records b
                LEFT JOIN billing_clients c ON c.id=b.client_id
                WHERE ofl_search_fold(b.title||' '||b.quote_number||' '||COALESCE(b.invoice_number,'')||' '||
                COALESCE(c.structure_name,'')||' '||COALESCE(c.contact_name,'')) LIKE ? ESCAPE '\\' ORDER BY b.id DESC LIMIT 8""",
                lambda r:dict(title=r['title'],detail=r['invoice_number'] or r['quote_number'],url='/admin/facturation/'+str(r['id'])))
            if modules.get('resources'):
                add('Réservations liées aux clients',"""SELECT b.booking_uuid,r.name,b.starts_at FROM resource_bookings b
                    JOIN resources r USING(resource_uuid) JOIN billing_records f ON f.id=b.billing_record_id
                    JOIN billing_clients c ON c.id=f.client_id
                    WHERE ofl_search_fold(c.structure_name||' '||c.contact_name) LIKE ? ESCAPE '\\'
                    ORDER BY b.starts_at DESC,b.booking_uuid LIMIT 8""",
                    lambda r:dict(title=r['name'],detail=r['starts_at'],url='/admin/ressources/reservations#reservation-'+quote(r['booking_uuid'],safe='')))
    except sqlite3.OperationalError as error:
        if str(error)!='interrupted':
            raise
        # Keep only fully computed groups; no malformed/partial business result.
    finally:
        db.set_progress_handler(None,0)
        db.create_function('ofl_search_fold',1,None)
    return groups
