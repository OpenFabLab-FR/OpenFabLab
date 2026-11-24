"""Targeted tests and browser fixtures; only fictional, isolated SQLite data."""
import json
import time
import unittest

from tests.test_families import FamilyTests


QUEUE = '/admin/usagers/demandes'
TASKS = '/admin/elements-a-traiter.json'
DIRECTORY = '/admin/usagers'


class OnlineAdmin218(unittest.TestCase):
    def setUp(self):
        self.f = FamilyTests(); self.f.setUp(); self.addCleanup(self.f.doCleanups)
        self.client, self.db = self.f.client, self.f.db
        self.db.execute("UPDATE app_settings SET value='1' WHERE key='setup_completed'")
        self.db.execute("UPDATE users SET first_name='Élodie' WHERE id=?", (self.f.a,))
        self.db.execute('INSERT INTO online_identities VALUES(?,?,?)', (self.f.a, 'person0@example.invalid', int(time.time())))
        self.db.commit()
        self.f.f.login_admin()

    def post(self, decision, **data):
        with self.client.session_transaction() as session:
            token = session['evolution_csrf']
        return self.client.post(QUEUE, data=dict(evolution_csrf=token, decision=decision, **data), follow_redirects=True)

    def pending(self):
        now = int(time.time())
        for i, kind in enumerate(('signup', 'child', 'claim')):
            data = json.dumps(dict(first_name='Camille', last_name=f'Exemple {i}', birth_date='1990-01-01'))
            self.db.execute("""INSERT INTO online_requests(id,kind,owner,email,data,state,created,expires)
                VALUES(?,?,?,?,?,'review',?,?)""", (str(i)*32, kind, self.f.a,
                    f'demande{i}@example.invalid', data, now, now+3000))
        self.db.commit()

    def test_private_search_by_name_and_public_id(self):
        for q in ('elodie', 'EXEMPLE Élodie', '2001'):
            r = self.post('find_access',q=q)
            self.assertIn('no-store', r.headers['Cache-Control'])
            self.assertIn('Élodie EXEMPLE', r.text)
            self.assertNotIn('Fictif1 EXEMPLE', r.text)
        for q in ('2002', '%_', 'n o n'):
            self.assertIn('Aucun accès en ligne ne correspond', self.post('find_access',q=q).text)
        self.assertEqual(self.client.post(QUEUE,data=dict(decision='find_access',q='2001')).status_code,400)

    def test_revocation_keeps_users_relationships_and_bookings(self):
        self.f.book([self.f.a,self.f.c])
        self.db.execute('INSERT INTO online_sessions VALUES(?,?,?,?)', ('a'*64,self.f.a,int(time.time())+3600,int(time.time())))
        self.db.commit()
        tables = ('users','user_family_links','animation_bookings')
        before = [[tuple(row) for row in self.db.execute('SELECT * FROM '+table)] for table in tables]
        followup = f'/admin/usagers/{self.f.a}/suivi'
        self.assertIn('Révoquer l’accès en ligne', self.client.get(followup).text)
        self.assertIn('Élodie EXEMPLE',self.client.get(QUEUE+f'?revoke={self.f.a}').text)
        self.assertIn('Confirmation requise', self.post('revoke',user_id=self.f.a).text)
        self.assertIsNotNone(self.db.execute('SELECT 1 FROM online_sessions').fetchone())
        self.assertIn('Accès en ligne révoqué', self.post('revoke',user_id=self.f.a,checked='1').text)
        self.assertIsNone(self.db.execute('SELECT 1 FROM online_sessions').fetchone())
        self.assertIsNone(self.db.execute('SELECT 1 FROM online_identities').fetchone())
        self.assertEqual(before,[[tuple(row) for row in self.db.execute('SELECT * FROM '+table)] for table in tables])
        self.assertNotIn('Révoquer l’accès en ligne',self.client.get(followup).text)

    def test_header_and_queue_keep_existing_permissions(self):
        self.pending()
        self.assertEqual(self.client.get(QUEUE).text.count('class="online-request-card"'),3)
        self.assertIn('class="admin-button secondary compact directory-requests"',self.client.get(DIRECTORY).text)
        groups=self.client.get(TASKS).json['groups']
        self.assertIn(dict(kind='people',label='Demandes de comptes',count=3,url=QUEUE),groups)
        with self.client.session_transaction() as session:
            session.update(access_role='moderator',admin_authenticated=False)
        self.assertNotIn('demande0@example.invalid',self.client.get(QUEUE,follow_redirects=True).text)
        self.assertNotIn('directory-requests',self.client.get(DIRECTORY).text)
        self.assertFalse(any(row['kind']=='people' for row in self.client.get(TASKS).json['groups']))
        self.db.execute("UPDATE app_settings SET value='0' WHERE key='online_header_tasks'")
        self.db.commit()
        self.assertEqual(self.client.get(TASKS).status_code,404)
        self.assertNotIn('data-online-tasks',self.client.get(DIRECTORY).text)


def snapshots():
    case = OnlineAdmin218()
    case.setUp()
    try:
        c = case.client
        pages = dict(empty=c.get(QUEUE).text)
        case.pending()
        pages.update(directory=c.get(DIRECTORY).text, queue=c.get(QUEUE).text,
                     selected=c.get(QUEUE+f'?revoke={case.f.a}').text, counts=c.get(TASKS).json)
        print(json.dumps(pages))
    finally:
        case.doCleanups()


if __name__=='__main__':
    import sys
    snapshots() if '--snapshots' in sys.argv else unittest.main()
