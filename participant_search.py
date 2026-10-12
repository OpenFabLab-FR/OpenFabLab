"""Staff-only, bounded participant search. Never used by public booking routes."""
import re
import unicodedata


def normalized(value):
    return ''.join(c for c in unicodedata.normalize('NFKD',str(value or '')).casefold()
                   if not unicodedata.combining(c))


def search_users(db,query):
    query=str(query or '').strip()[:80]
    if not query:
        return dict(users=[],more=False)
    db.create_function('participant_search_key',1,normalized,deterministic=True)
    pattern='%'+normalized(query).replace('\\','\\\\').replace('%','\\%').replace('_','\\_')+'%'
    rows=db.execute("""SELECT id,public_id,first_name,last_name FROM users WHERE active=1
        AND (participant_search_key(first_name || ' ' || last_name) LIKE ? ESCAPE '\\'
             OR public_id LIKE ? ESCAPE '\\') ORDER BY participant_search_key(first_name),participant_search_key(last_name),id LIMIT 26""",(pattern,pattern)).fetchall()
    return dict(users=[dict(row) for row in rows[:25]],more=len(rows)>25)


def register(application,a):
    from flask import Blueprint,jsonify,request
    from evolution_routes import require_team
    bp=Blueprint('participant_search',__name__)
    @bp.get('/admin/api/participants')
    def search():
        require_team()
        response=jsonify(search_users(a.get_database(),request.args.get('q','')))
        response.headers['Cache-Control']='private, no-store'
        response.headers['X-Robots-Tag']='noindex, nofollow'
        return response
    application.register_blueprint(bp)
