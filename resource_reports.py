"""Private issue intake. Anonymous submissions cannot change resource state."""
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import unicodedata
from uuid import uuid4

import machine_maintenance as machines
from family_model import local_day, setting


STATES = {'new': 'Nouveau signalement', 'assigned': 'Pris en charge',
          'dismissed': 'Classé sans suite', 'resolved': 'Résolu'}
ACTIONS = {'assign': 'Prendre en charge', 'dismiss': 'Classer sans suite',
           'resolve': 'Marquer comme résolu', 'intervention': 'Créer une intervention'}


class Throttled(ValueError):
    pass


def enabled(db):
    return setting(db, 'resource_reports_enabled', '0') == '1'


def submit(db, key, text, address, secret, now=None):
    if not db.in_transaction:
        raise RuntimeError('Report transaction required')
    text = unicodedata.normalize('NFC', str(text or '').replace('\r\n', '\n')).strip()
    if not 1 <= len(text) <= 500 or any(unicodedata.category(c).startswith('C') and c not in '\n\t' for c in text):
        raise ValueError('Décrivez le problème en 1 à 500 caractères.')
    now = now or datetime.now(timezone.utc)
    since = (now - timedelta(hours=1)).isoformat()
    recent = db.execute('SELECT description FROM resource_problem_reports WHERE resource_uuid=? AND received_at>=?',
                        (key, since)).fetchall()
    normalized = ' '.join(text.casefold().split())
    if any(' '.join(row[0].casefold().split()) == normalized for row in recent):
        return None  # idempotent, no second notification
    secret = secret.encode() if isinstance(secret, str) else secret
    rate_key = hmac.new(secret, ('report-rate:' + str(address or '')).encode(), hashlib.sha256).hexdigest()
    # Bound the total rate even when a client rotates IPs or discards cookies.
    if (len(recent) >= 10 or
            db.execute('SELECT COUNT(*) FROM resource_problem_reports WHERE received_at>=?', (since,)).fetchone()[0] >= 40 or
            db.execute('SELECT COUNT(*) FROM resource_problem_reports WHERE rate_key=? AND received_at>=?',
                       (rate_key, (now - timedelta(minutes=15)).isoformat())).fetchone()[0] >= 4):
        raise Throttled('Trop de signalements. Réessayez dans quelques minutes.')
    db.execute('UPDATE resource_problem_reports SET rate_key=NULL WHERE rate_key IS NOT NULL AND received_at<?', (since,))
    report_id = str(uuid4())
    db.execute('INSERT INTO resource_problem_reports(report_id,resource_uuid,description,received_at,rate_key) VALUES(?,?,?,?,?)',
               (report_id, key, text, now.isoformat(), rate_key))
    return report_id, text, now


def decide(db, key, report_id, action, role, reason=''):
    machines.require(role)
    if not db.in_transaction:
        raise RuntimeError('Report transaction required')
    row = db.execute('SELECT * FROM resource_problem_reports WHERE report_id=? AND resource_uuid=?',
                     (report_id, key)).fetchone()
    if not row or row['state'] not in ('new', 'assigned') or action not in ACTIONS:
        raise ValueError('Ce signalement n’est plus modifiable.')
    reason = str(reason or '').strip()
    if len(reason) > 500:
        raise ValueError('Le motif ne doit pas dépasser 500 caractères.')
    target = {'assign': 'assigned', 'intervention': 'assigned', 'dismiss': 'dismissed', 'resolve': 'resolved'}[action]
    intervention = row['intervention_uuid']
    if action == 'intervention':
        if not machines.enabled(db) or intervention:
            raise ValueError('Une intervention ne peut pas être créée pour ce signalement.')
        intervention = machines.intervention(db, key, {
            'performed_on': str(local_day(db)), 'kind': 'inspection', 'description': reason or row['description'],
        }, role, role)
    if action == 'assign' and target == row['state']:
        raise ValueError('Ce signalement est déjà pris en charge.')
    db.execute('UPDATE resource_problem_reports SET state=?,intervention_uuid=? WHERE report_id=?',
               (target, intervention, report_id))
    db.execute('INSERT INTO resource_problem_decisions(report_id,action,role,reason,created_at) VALUES(?,?,?,?,?)',
               (report_id, action, role, reason, machines.stamp()))
    return intervention


def list_reports(db, key, page=1, focus=None):
    if focus:
        row = db.execute('SELECT received_at FROM resource_problem_reports WHERE resource_uuid=? AND report_id=?',
                         (key, focus)).fetchone()
        if row:
            newer = db.execute('''SELECT COUNT(*) FROM resource_problem_reports WHERE resource_uuid=?
                AND (received_at,report_id)>(?,?)''', (key, row[0], focus)).fetchone()[0]
            page = 1 + newer // 25
    rows = [dict(r) for r in db.execute('''SELECT report_id,description,received_at,state,intervention_uuid
        FROM resource_problem_reports WHERE resource_uuid=? ORDER BY received_at DESC, report_id DESC LIMIT 26 OFFSET ?''',
        (key, (page-1)*25))]
    for row in rows[:25]:
        row['decisions'] = db.execute('''SELECT action,role,reason,created_at FROM resource_problem_decisions
            WHERE report_id=? ORDER BY id''', (row['report_id'],)).fetchall()
    return rows[:25], page, len(rows) > 25
