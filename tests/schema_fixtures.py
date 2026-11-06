"""Remove schema 27 from a synthetic fixture before emulating older versions."""
from v2153_schema import SETTINGS,TABLES


def remove_27(db):
    db.execute('DROP TABLE IF EXISTS machine_maintenance_slots')
    for name in ('resource_problem_decisions','resource_problem_reports','user_profile_activity'):
        db.execute('DROP TABLE '+name)
    for name, in db.execute("SELECT name FROM sqlite_schema WHERE type='index' AND name LIKE 'dashboard_%'").fetchall():
        db.execute('DROP INDEX '+name)
    db.executemany('DELETE FROM app_settings WHERE key=?', [(key,) for key in SETTINGS])
    old,=db.execute("SELECT sql FROM sqlite_schema WHERE name='machine_condition'").fetchone()
    db.execute(old.replace('"machine_condition"', 'machine_condition_v26', 1).replace(",'unavailable'", ""))
    db.execute('INSERT INTO machine_condition_v26 SELECT * FROM machine_condition')
    db.execute('DROP TABLE machine_condition')
    db.execute('ALTER TABLE machine_condition_v26 RENAME TO machine_condition')
    db.execute('PRAGMA user_version=26')
