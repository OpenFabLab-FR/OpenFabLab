"""Shared persistent PDF blobs; routes must enforce per-resource visibility."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from uuid import uuid4
from evolution_schema import audit,now
from memberships import atomic

LANGUAGES={'fr','en','de','es','fi','other'}
MAX_BYTES=16*1024*1024


def directory(database_path):
    root=Path(database_path).resolve().parent/'resource-documents'
    if root.is_symlink():raise ValueError('Stockage des documents non sûr.')
    root.mkdir(mode=0o700,exist_ok=True)
    return root


def validate(path):
    process=None
    try:
        process=subprocess.Popen([sys.executable,str(Path(__file__).with_name('pdf_guard.py')),str(path)],
            stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
            env=os.environ|{'PYTHONDONTWRITEBYTECODE':'1','OPENFABLAB_EXTERNAL_ACTIONS':'0'})
        deadline=time.monotonic()+15
        while True:
            if sys.platform=='darwin' and process.poll() is None:
                usage=subprocess.run(['/bin/ps','-o','rss=','-p',str(process.pid)],stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,timeout=1)
                if usage.returncode==0 and usage.stdout.strip().isdigit() and int(usage.stdout)>768*1024:
                    raise ValueError('PDF_MEMORY_LIMIT')
                if usage.returncode!=0 and process.poll() is None:
                    raise ValueError('PDF_MEMORY_MEASUREMENT_UNAVAILABLE')
            remaining=deadline-time.monotonic()
            if remaining<=0:raise subprocess.TimeoutExpired('PDF validation',15)
            try:
                output,_=process.communicate(timeout=min(.1,remaining));break
            except subprocess.TimeoutExpired:continue
        metadata=json.loads(output[:1000])
        if process.returncode or metadata.get('valid') is not True:raise ValueError()
        return metadata
    except (ValueError,OSError,subprocess.TimeoutExpired):
        raise ValueError('PDF non accepté : utilisez un document non chiffré, sans formulaire ni contenu actif, de 16 Mo et 200 pages maximum.') from None
    finally:
        if process and process.poll() is None:
            process.kill();process.communicate(timeout=2)


def uploaded_blob(database_path,upload):
    if not str(upload.filename or '').lower().endswith('.pdf'):
        raise ValueError('Choisissez un fichier PDF.')
    if upload.mimetype not in ('application/pdf','application/octet-stream'):
        raise ValueError('Le fichier transmis n’est pas un PDF.')
    root=directory(database_path)
    with tempfile.NamedTemporaryFile(prefix='.upload-',suffix='.tmp',dir=root,delete=False) as temporary:
        path=Path(temporary.name);path.chmod(0o600)
        try:
            digest=hashlib.sha256();total=0
            while block:=upload.stream.read(1024*1024):
                total+=len(block)
                if total>MAX_BYTES:raise ValueError('Le PDF dépasse la limite de 16 Mo.')
                temporary.write(block);digest.update(block)
            temporary.flush();os.fsync(temporary.fileno())
            metadata=validate(path)
            identifier=digest.hexdigest();target=root/(identifier+'.pdf')
            if target.is_symlink():raise ValueError('Stockage des documents non sûr.')
            if target.exists():
                if hashlib.sha256(target.read_bytes()).hexdigest()!=identifier:
                    raise ValueError('Le document stocké ne correspond plus à son empreinte.')
            else:
                # Atomic publication of one immutable private blob, never a
                # client-supplied filename and never an overwrite of user files.
                os.link(path,target);target.chmod(0o600)
            return identifier,total,metadata['pages']
        finally:
            temporary.close();path.unlink(missing_ok=True)


def require_resource(db,key,role,write=False):
    if role not in ('admin','moderator'):raise PermissionError('Action réservée à l’équipe.')
    row=db.execute('SELECT * FROM resources WHERE resource_uuid=?',(key,)).fetchone()
    if not row:raise ValueError('Ressource inconnue.')
    if write and row['archived_at']:raise ValueError('Restaurez cette ressource avant de modifier ses documents.')
    return row


def items(db,key,public_only=False):
    return [dict(r) for r in db.execute('''SELECT d.*,(SELECT COUNT(*) FROM resource_document_links x
        WHERE x.document_uuid=d.document_uuid) AS uses FROM resource_documents d
        JOIN resource_document_links l USING(document_uuid) WHERE l.resource_uuid=? AND d.archived_at IS NULL
        AND (?=0 OR d.public=1) ORDER BY d.title,d.language''',(key,int(public_only)))]


def attach(db,key,document,role):
    require_resource(db,key,role,True)
    if not db.execute('SELECT 1 FROM resource_documents WHERE document_uuid=? AND archived_at IS NULL',(document,)).fetchone():
        raise ValueError('Document inconnu.')
    db.execute('INSERT OR IGNORE INTO resource_document_links VALUES(?,?,?)',(key,document,now()))
    audit(db,'resource_document',document,'attached',role,{'resource_uuid':key})


def import_pdf(db,database_path,key,upload,values,role):
    require_resource(db,key,role,True)
    title=str(values.get('title','')).strip();language=values.get('language','fr')
    if not title or len(title)>180 or language not in LANGUAGES:raise ValueError('Titre et langue du document requis.')
    digest,size,pages=uploaded_blob(database_path,upload)
    with atomic(db):
        previous=db.execute('SELECT * FROM resource_documents WHERE sha256=?',(digest,)).fetchone()
        if previous:
            if previous['archived_at']:raise ValueError('Ce document a été retiré de la bibliothèque. Demandez sa réactivation à l’administrateur.')
            document=previous['document_uuid']
            # Importing the same bytes never changes existing public/team
            # visibility, title or language on other resources unexpectedly.
        else:
            document=str(uuid4());stamp=now()
            db.execute('''INSERT INTO resource_documents(document_uuid,title,language,sha256,size_bytes,public,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?)''',(document,title,language,digest,size,int(values.get('public')=='1'),stamp,stamp))
            audit(db,'resource_document',document,'imported',role,{'sha256':digest,'pages':pages})
        attach(db,key,document,role)
    return document


def modify(db,database_path,key,document,values,role,upload=None):
    require_resource(db,key,role,True)
    with atomic(db):
        previous=db.execute('SELECT d.* FROM resource_documents d JOIN resource_document_links l USING(document_uuid) WHERE l.resource_uuid=? AND d.document_uuid=?',(key,document)).fetchone()
        if not previous:raise ValueError('Document non associé à cette ressource.')
        if str(previous['revision'])!=str(values.get('revision')):raise ValueError('Ce document a changé. Rechargez la fiche.')
        if values.get('action')=='detach':
            db.execute('DELETE FROM resource_document_links WHERE resource_uuid=? AND document_uuid=?',(key,document))
            audit(db,'resource_document',document,'detached',role,{'resource_uuid':key});return
        title=str(values.get('title','')).strip();language=values.get('language','fr')
        if not title or len(title)>180 or language not in LANGUAGES:raise ValueError('Titre et langue du document requis.')
        uses=db.execute('SELECT COUNT(*) FROM resource_document_links WHERE document_uuid=?',(document,)).fetchone()[0]
        if uses>1 and values.get('confirm_shared')!='1':
            raise ValueError('Ce document est partagé : confirmez la modification pour toutes les ressources associées.')
        digest,size=previous['sha256'],previous['size_bytes']
        if upload and upload.filename:
            digest,size,_=uploaded_blob(database_path,upload)
            if db.execute('SELECT 1 FROM resource_documents WHERE sha256=? AND document_uuid!=?',(digest,document)).fetchone():
                raise ValueError('Ce PDF existe déjà. Associez le document existant plutôt que le remplacer par un doublon.')
        db.execute('UPDATE resource_documents SET title=?,language=?,sha256=?,size_bytes=?,public=?,revision=revision+1,updated_at=? WHERE document_uuid=?',
            (title,language,digest,size,int(values.get('public')=='1'),now(),document))
        audit(db,'resource_document',document,'updated',role,{'previous_sha256':previous['sha256'],'sha256':digest,'resource_uuid':key})


def blob_path(database_path,row):
    digest=row['sha256']
    import re
    if not re.fullmatch('[0-9a-f]{64}',digest):raise ValueError('Empreinte de document invalide.')
    path=directory(database_path)/(digest+'.pdf')
    if path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=digest:
        raise ValueError('Le PDF est indisponible ou son intégrité doit être vérifiée.')
    return path
