"""Real published-source migration, coherent backups and target runtime probe.

Docker is not invoked: the identical fixed worker is executed as a subprocess.
All fixture data is generated locally, all worker network calls are prohibited.
"""
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from updater_agent.filesystem import coherent_copy, inventory, sha, write_probe
from updater_agent.data_checks import snapshot
from updater_agent.security import Refused
from openfablab import __version__

SOURCE=Path(__file__).resolve().parents[1]


class Files(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        environment=os.environ|{'PYTHONDONTWRITEBYTECODE':'1'}
        result=subprocess.run([sys.executable,str(SOURCE/'tests/source25_fixture.py'),str(self.root/'source25')],
             env=environment,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=45)
        self.assertEqual(result.returncode,0,result.stderr.decode()[-1000:])
        self.data=self.root/'source25/data'
        self.database=self.data/'openfablab.db'
        self.manifest=dict(version=__version__,schema=26,source_schemas=[25],
            new_tables=['user_booking_restrictions','resource_documents','resource_document_links'],
            new_settings={'resource_public_base_url':'','resource_public_pages_enabled':'0','setup_completed':'1','setup_progress':'{}'})
        self.manifest_path=self.root/'manifest.json';self.manifest_path.write_text(json.dumps(self.manifest))

    def worker(self,operation,**arguments):
        output=self.root/(operation+'-result.json')
        command=[sys.executable,'-m','updater_agent.worker',operation,'--database',str(self.database),'--output',str(output)]
        for key,value in arguments.items():
            command+=['--'+key.replace('_','-')]
            if value is not True:command+=[str(value)]
        environment=os.environ|dict(PYTHONPATH=str(SOURCE)+os.pathsep+os.environ.get('PYTHONPATH',''),PYTHONDONTWRITEBYTECODE='1',OPENFABLAB_EXTERNAL_ACTIONS='0',OPENFABLAB_ENABLE_SCHEDULER='0')
        result=subprocess.run(command,env=environment,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=45)
        value=json.loads(output.read_bytes())
        self.assertEqual(result.returncode,0,value)
        return value

    def test_actual_target_probe_25_to26_from_published_runtime_keeps_source_unchanged(self):
        before=inventory(self.data)
        result=self.worker('probe',destination=self.root/'probe',runtime=SOURCE,manifest=self.manifest_path)
        self.assertTrue(result['success']);self.assertEqual(result['schema'],26)
        self.assertEqual(result['http']['transport'],'real_loopback_http')
        self.assertEqual(before,inventory(self.data))
        self.assertEqual(snapshot(self.database)['schema'],25)
        self.assertEqual(snapshot(self.root/'probe/openfablab.db')['schema'],26)

    def test_complete_private_backup_is_really_restored_and_opened(self):
        project=self.root/'project';project.mkdir()
        (project/'.env').write_text('FICTIONAL_CONFIG=preserved\n')
        result=self.worker('backup',destination=self.root/'backup',project=project,version='2.14.4',schema=25)
        self.assertTrue(result['restoration_test'])
        restored=self.root/'backup/restoration-test/openfablab.db'
        self.assertEqual(snapshot(restored)['schema'],25)
        self.assertEqual(snapshot(self.database)['tables']['users']['sha256'],snapshot(restored)['tables']['users']['sha256'])
        self.assertEqual((self.root/'backup/configuration/private.env').read_text(),'FICTIONAL_CONFIG=preserved\n')

    def test_same_schema_copy_runs_real_http_and_preserves_source_and_history(self):
        destination=self.root/'source26'
        self.worker('probe',destination=destination,runtime=SOURCE,manifest=self.manifest_path)
        self.data=destination;self.database=destination/'openfablab.db'
        source=inventory(self.data);before=snapshot(self.database,26)
        staged=self.root/'probe-data'
        result=self.worker('probe-copy',destination=staged,schema=26)
        self.assertTrue(result['success']);self.assertEqual(source,inventory(self.data))
        original=self.database;self.database=staged/'openfablab.db'
        self.manifest_path.write_text(json.dumps(dict(version=__version__,schema=26,source_schemas=[26],new_tables=[],new_settings={})))
        result=self.worker('probe',destination=staged,runtime=SOURCE,manifest=self.manifest_path,prepared_copy=True)
        self.assertEqual(result['http']['transport'],'real_loopback_http')
        self.assertEqual(source,inventory(original.parent))
        after=snapshot(self.database,26)
        self.assertEqual(before['tables']['users'],after['tables']['users'])
        self.assertEqual(before['settings'],after['settings'])

    def test_custom_compose_and_active_override_are_saved_not_assumed(self):
        project=self.root/'project';project.mkdir()
        compose=project/'installation.yml';compose.write_text('services: {fictional: {image: example}}\n')
        override=self.root/'override.json';override.write_text('{"services":{}}')
        self.worker('backup',destination=self.root/'custom-backup',project=project,version='2.14.4',schema=25,compose=compose,override=override)
        configuration=self.root/'custom-backup/configuration'
        self.assertEqual((configuration/'compose-source.yml').read_bytes(),compose.read_bytes())
        self.assertEqual((configuration/'compose-active-override.json').read_bytes(),override.read_bytes())

    def test_live_wal_copy_keeps_committed_rows_without_touching_source_sidecars(self):
        with sqlite3.connect(self.database) as writer:
            writer.execute('PRAGMA journal_mode=WAL')
            writer.execute("INSERT INTO app_settings VALUES('fictional_wal','committed')");writer.commit()
            wal=Path(str(self.database)+'-wal');self.assertTrue(wal.is_file())
            before=sha(wal)
            coherent_copy(self.data,self.root/'copy')
            self.assertTrue(wal.is_file());self.assertEqual(before,sha(wal))
            with sqlite3.connect(self.root/'copy/openfablab.db') as copied:
                self.assertEqual(copied.execute("SELECT value FROM app_settings WHERE key='fictional_wal'").fetchone()[0],'committed')

    def test_symlink_refusal_no_probe_residue(self):
        (self.data/'unsafe').symlink_to(self.root/'manifest.json')
        with self.assertRaises(Refused):coherent_copy(self.data,self.root/'refused')
        self.assertFalse((self.root/'refused').exists())
        target=self.root/'probe-target';target.mkdir();write_probe(target)
        self.assertEqual(list(target.iterdir()),[])

if __name__=='__main__':unittest.main()
