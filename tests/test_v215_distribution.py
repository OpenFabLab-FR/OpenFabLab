"""Actual deterministic ZIP bytes and executor manifest, no Docker or network."""
import hashlib,json,tempfile,unittest
from pathlib import Path
from zipfile import ZipFile
import build_openfablab as builder
from updater_agent.docker_executor import DockerExecutor

class Distribution(unittest.TestCase):
    def test_complete_reproducible_archive_and_safe_manifested_extraction(self):
        with tempfile.TemporaryDirectory() as root:
            root=Path(root);first=builder.build(root/'one.zip');second=builder.build(root/'two.zip')
            self.assertEqual(hashlib.sha256(first.read_bytes()).digest(),hashlib.sha256(second.read_bytes()).digest())
            with ZipFile(first) as archive:
                self.assertIsNone(archive.testzip());names=set(archive.namelist())
                self.assertTrue({'app.py','updater_agent/installation.py','update_wire.py','tests/test_v215_core.py','docs/update-agent.md'}<=names)
                self.assertFalse(any(n.endswith(('.db','.zip','.log')) or n.startswith(('data/','NAS-','Technique/','wordpress/')) for n in names))
                self.assertNotIn('dsm_initial.py',names);self.assertNotIn('bootstrap_seed.py',names)
                manifest=json.loads(archive.read('UPDATE-MANIFEST.json'))
                self.assertEqual(set(manifest['files']),names-{'UPDATE-MANIFEST.json'})
                self.assertTrue(all(hashlib.sha256(archive.read(n)).hexdigest()==v for n,v in manifest['files'].items()))
            policy={key:str(root) for key in ('state','project','data','backups','database')}
            executor=DockerExecutor(policy,'sha256:'+'1'*64)
            extracted=executor.unpack(first,root/'unpacked','2.15.2')
            self.assertEqual(extracted['schema'],26);self.assertEqual(extracted['source_schemas'],[26])
            self.assertFalse(any(n.startswith('updater_agent/') for n in extracted['runtime_files']))
            self.assertTrue((root/'unpacked/.env.example').is_file())
    def test_protocol_and_plugin_metadata_are_independent_of_public_version(self):
        # This suite must also run from the application-only ZIP. The separate
        # plugin distribution suite validates its own archive and metadata.
        from openfablab import __version__
        self.assertEqual(__version__,'2.15.2')
        from outbound_sync import negotiate
        class Client:
            def post(self,route,payload):return dict(protocol_version=4,relay_revision=3,outbound_actions_v1=True)
        self.assertEqual(negotiate(Client(),'production')['relay_revision'],3)

if __name__=='__main__':unittest.main()
