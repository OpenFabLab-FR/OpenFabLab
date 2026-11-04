"""Schema25: distinguish archival from reservation enablement, no row rewrite."""
def ensure(db):
    columns={r[1] for r in db.execute('PRAGMA table_info(resources)')}
    if not columns:raise RuntimeError('Table des ressources manquante ; migration refusée.')
    if 'archived_at' not in columns:db.execute('ALTER TABLE resources ADD COLUMN archived_at TEXT')
