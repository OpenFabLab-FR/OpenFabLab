"""Real PDF parsers/generators, fictional tutorials and access-control tests."""
import hashlib
import io
from pathlib import Path
import unittest
from pypdf import PdfReader,PdfWriter
from reportlab.pdfgen import canvas
from werkzeug.datastructures import FileStorage
from tests import test_v214_core as core
from app import write_setting
from family_model import setting
import machine_maintenance as machines
import resource_booking as bookings
import resource_documents as documents
from resource_portal import label_pdf,local_base,public_base,resource_url


def pdf(text='Tutoriel fictif - aucun contenu de production'):
    out=io.BytesIO();c=canvas.Canvas(out);c.drawString(50,780,text);c.showPage()
    c.setPageSize((842,595));c.drawString(50,540,'Page paysage fictive');c.showPage();c.save()
    return out.getvalue()


def upload(content):return FileStorage(stream=io.BytesIO(content),filename='tutoriel-fictif.pdf',content_type='application/pdf')


class Documents(unittest.TestCase):
    setUp=core.NewVersion.setUp
    login=core.NewVersion.login
    def publish(self):
        write_setting(self.db,'resource_public_base_url','https://fablab.example/stat')
        write_setting(self.db,'resource_public_pages_enabled','1')
        machines.set_condition(self.db,self.key,dict(status='operational',visibility_controls='1',public_visible='1'),'admin','admin')
        self.db.commit()
    def add(self,public='0',key=None,content=None):
        return documents.import_pdf(self.db,self.path,key or self.key,upload(content or pdf()),dict(title='Tutoriel fictif',language='fr',public=public),'moderator')

    def test_local_qr_explicit_private_address_keeps_remote_url_and_pdf_scope(self):
        self.publish()
        document=self.add('1')
        self.db.commit()
        token=self.login();route='/admin/reglages/ressources'
        response=self.client.post(route,data=dict(access='local',local_url='http://192.168.50.10:8080/stat',enabled='1',evolution_csrf=token))
        self.assertEqual(response.status_code,302)
        self.assertEqual(resource_url(self.db,self.key),'http://192.168.50.10:8080/stat/r/'+self.key)
        self.assertEqual(setting(self.db,'resource_public_base_url'),'https://fablab.example/stat')
        public=self.client.get('/r/'+self.key,environ_overrides={'SCRIPT_NAME':'/stat'})
        self.assertIn('/stat/r/'+self.key+'/documents/'+document+'.pdf',public.text)
        self.assertEqual(self.client.get('/admin/ressources/'+self.key+'/qr.svg').status_code,200)
        for value in ('http://example.org','http://127.0.0.1:8000','http://192.168.1.1/%2e%2e','http://user@192.168.1.1','http://192.168.1.1/?','http://192.168.1.1:99999'):
            with self.subTest(value=value),self.assertRaises(ValueError):local_base(value)
        self.assertEqual(local_base('http://[fd00::1234]:5080/stat/'),'http://[fd00::1234]:5080/stat')

    def test_original_bytes_pages_layout_preserved_and_deduplicated(self):
        content=pdf();document=self.add(content=content)
        key=bookings.save_resource(self.db,dict(name='Deuxième ressource fictive',type_key='machine',active='1'),'admin');self.db.commit()
        again=self.add(public='1',key=key,content=content)
        self.assertEqual(document,again)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM resource_documents').fetchone()[0],1)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM resource_document_links').fetchone()[0],2)
        row=documents.items(self.db,self.key)[0];self.assertFalse(row['public'])
        path=documents.blob_path(self.path,row);self.assertEqual(path.read_bytes(),content)
        reader=PdfReader(path);self.assertEqual(len(reader.pages),2)
        self.assertGreater(float(reader.pages[1].mediabox.width),float(reader.pages[1].mediabox.height))
        self.assertEqual(len(list(documents.directory(self.path).glob('*.pdf'))),1)

    def test_internal_document_not_public_even_when_url_known_and_public_resource_enabled(self):
        self.publish();document=self.add()
        route='/r/'+self.key+'/documents/'+document+'.pdf'
        self.assertEqual(self.client.get(route).status_code,404)
        private='/admin/ressources/'+self.key+'/documents/'+document+'.pdf'
        self.assertNotEqual(self.client.get(private).status_code,200)
        self.login('moderator')
        response=self.client.get(private);self.assertEqual(response.status_code,200)
        self.assertIn('no-store',response.headers['Cache-Control'])
        self.assertEqual(response.data,documents.blob_path(self.path,documents.items(self.db,self.key)[0]).read_bytes())
        self.assertEqual(self.client.get(route).status_code,404)

    def test_public_projection_no_internal_notes_and_visibility_revoked_immediately(self):
        self.publish();document=self.add('1')
        page=self.client.get('/r/'+self.key)
        self.assertEqual(page.status_code,200)
        self.assertNotIn('Intervention fictive privée',page.text)
        self.assertNotIn('person0@example',page.text)
        self.assertEqual(self.client.get('/r/'+self.key+'/documents/'+document+'.pdf').status_code,200)
        machines.set_condition(self.db,self.key,dict(status='operational',visibility_controls='1',public_visible='0'),'admin','admin');self.db.commit()
        self.assertEqual(self.client.get('/r/'+self.key).status_code,404)
        self.assertEqual(self.client.get('/r/'+self.key+'/documents/'+document+'.pdf').status_code,404)

    def test_replace_keeps_shared_links_requires_confirmation_and_optimistic_revision(self):
        document=self.add();key=bookings.save_resource(self.db,dict(name='Partage fictif',type_key='machine',active='1'),'admin');self.db.commit()
        with self.db:documents.attach(self.db,key,document,'moderator')
        values=dict(action='update',title='Titre corrigé',language='en',public='1',revision='1')
        with self.assertRaises(ValueError):documents.modify(self.db,self.path,self.key,document,values,'moderator',upload(pdf('Remplacement fictif')))
        documents.modify(self.db,self.path,self.key,document,values|dict(confirm_shared='1'),'moderator',upload(pdf('Remplacement fictif')))
        self.assertEqual(documents.items(self.db,key)[0]['title'],'Titre corrigé')
        self.assertEqual(documents.items(self.db,key)[0]['revision'],2)
        self.assertEqual(documents.items(self.db,key)[0]['document_uuid'],document)
        with self.assertRaises(ValueError):documents.modify(self.db,self.path,self.key,document,values,'moderator')
        documents.modify(self.db,self.path,self.key,document,dict(action='detach',revision='2'),'moderator')
        self.assertFalse(documents.items(self.db,self.key));self.assertEqual(documents.items(self.db,key)[0]['document_uuid'],document)

    def test_active_encrypted_attached_invalid_and_oversized_files_refused(self):
        examples=[b'not a PDF',b'%PDF-'+b'x'*(documents.MAX_BYTES+1)]
        for mode in ('javascript','attachment','encrypted'):
            w=PdfWriter();w.add_blank_page(100,100)
            if mode=='javascript':w.add_js('app.alert("FICTIONAL")')
            if mode=='attachment':w.add_attachment('fictional.txt',b'FAKE')
            if mode=='encrypted':w.encrypt('FICTIONAL_ONLY')
            out=io.BytesIO();w.write(out);examples.append(out.getvalue())
        for content in examples:
            with self.subTest(length=len(content)),self.assertRaises(ValueError):self.add(content=content)
        self.assertFalse(self.db.execute('SELECT 1 FROM resource_documents').fetchone())
        self.assertFalse(list(documents.directory(self.path).glob('.upload-*')))

    def test_forms_permissions_csrf_multiple_upload_and_module_off(self):
        token=self.login('moderator');route='/admin/ressources/'+self.key+'/fiche'
        self.assertEqual(self.client.get(route).status_code,200)
        self.assertEqual(self.client.post(route,data={'action':'attach'}).status_code,400)
        response=self.client.post(route,data={'action':'import','language':'fr','evolution_csrf':token,
            'pdf':[(io.BytesIO(pdf('Premier fictif')),'premier.pdf'),(io.BytesIO(pdf('Deuxième fictif')),'deuxieme.pdf')]},content_type='multipart/form-data')
        self.assertEqual(response.status_code,302)
        self.assertEqual(len(documents.items(self.db,self.key)),2)
        self.assertNotEqual(self.client.get('/admin/reglages/ressources').status_code,200)
        write_setting(self.db,'module_resources','0');write_setting(self.db,'module_maintenance','0');self.db.commit()
        self.assertEqual(self.client.get(route).status_code,404)

    def test_backup_restoration_includes_pdf_and_links(self):
        from private_backup import create_backup,validate_backup
        document=self.add('1')
        with __import__('tempfile').TemporaryDirectory() as folder:
            root=Path(folder);create_backup(self.path,root/'complete.zip')
            validate_backup(root/'complete.zip',root/'restored')
            restored=root/'restored/resource-documents'
            original=documents.blob_path(self.path,documents.items(self.db,self.key)[0])
            self.assertEqual((restored/original.name).read_bytes(),original.read_bytes())
            with __import__('sqlite3').connect(root/'restored/openfablab.db') as db:
                self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],__import__('family_model').SCHEMA)
                self.assertTrue(db.execute('SELECT 1 FROM resource_document_links WHERE document_uuid=?',(document,)).fetchone())

    def test_https_qr_stable_uuid_formats_and_no_secret(self):
        self.publish();self.login()
        original=resource_url(self.db,self.key)
        self.db.execute('UPDATE resources SET name=? WHERE resource_uuid=?',('Nouveau nom fictif',self.key));self.db.commit()
        self.assertEqual(resource_url(self.db,self.key),original)
        for kind,mime in [('png','image/png'),('svg','image/svg+xml'),('pdf','application/pdf')]:
            response=self.client.get('/admin/ressources/'+self.key+'/qr.'+kind)
            self.assertEqual(response.status_code,200);self.assertEqual(response.mimetype,mime)
            self.assertGreater(len(response.data),100)
            if kind=='pdf':self.assertEqual(len(PdfReader(io.BytesIO(response.data)).pages),1)
        for value in ('http://example.invalid','https://user:SECRET@example.invalid','https://example.invalid/?token=secret'):
            with self.assertRaises(ValueError):public_base(value)

if __name__=='__main__':unittest.main()
