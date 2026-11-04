"""Schema24: extend the existing work-kind constraint, inside family_model's transaction.

No new business storage. Existing IDs, rowids, reminders, history and values remain
identical. An exception rolls back DDL and data together; foreign keys stay enabled.
"""
def ensure(db):
    row=db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='machine_interventions'").fetchone()
    if not row:raise RuntimeError('Table des interventions manquante ; migration refusée.')
    ddl=row[0]
    old="CHECK(kind IN('care','preventive','repair','other'))"
    new="CHECK(kind IN('care','preventive','repair','inspection','other'))"
    if new in ddl:return
    if old not in ddl:raise RuntimeError('Structure des interventions inconnue ; migration refusée.')
    # Rebuild the one dependent table first, never disable foreign-key checks.
    for name, in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall():
        for foreign in db.execute('PRAGMA foreign_key_list("'+name.replace('"','""')+'")'):
            if foreign[2] in ('machine_interventions','machine_reminders') and not (name=='machine_reminders' and foreign[2]=='machine_interventions'):
                raise RuntimeError('Référence aux interventions inconnue ; migration refusée.')
    child_sql=db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='machine_reminders'").fetchone()[0]
    children=db.execute('SELECT rowid,* FROM machine_reminders').fetchall()
    extras=[r[0] for r in db.execute("SELECT sql FROM sqlite_master WHERE tbl_name IN('machine_interventions','machine_reminders') AND type IN('index','trigger') AND sql IS NOT NULL ORDER BY type,name")]
    db.execute(ddl.replace('machine_interventions','_v2141_interventions',1).replace(old,new))
    columns=[r[1] for r in db.execute('PRAGMA table_info(machine_interventions)')]
    names=','.join('"'+name+'"' for name in ['rowid']+columns)
    db.execute('INSERT INTO _v2141_interventions('+names+') SELECT '+names+' FROM machine_interventions')
    db.execute('DROP TABLE machine_reminders')
    db.execute('DROP TABLE machine_interventions')
    db.execute('ALTER TABLE _v2141_interventions RENAME TO machine_interventions')
    db.execute(child_sql)
    columns=[r[1] for r in db.execute('PRAGMA table_info(machine_reminders)')]
    names=','.join('"'+name+'"' for name in ['rowid']+columns)
    db.executemany('INSERT INTO machine_reminders('+names+') VALUES('+','.join('?' for _ in range(len(columns)+1))+')',children)
    for sql in extras:db.execute(sql)
    if db.execute('PRAGMA foreign_key_check').fetchall():raise RuntimeError('Références invalides après migration ; annulation.')
