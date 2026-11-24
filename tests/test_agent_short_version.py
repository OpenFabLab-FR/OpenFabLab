import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
from unittest import mock
from zipfile import ZipFile
from updater_agent.engine import Engine
from updater_agent.local_candidate import LocalCandidate
from updater_agent.releases import unpack
from updater_agent.security import version, Refused

class ShortVersion(unittest.TestCase):
    def test_order(self):
        self.assertGreater(version('2.17'),version('2.16.1'))
        self.assertEqual(version('2.17.0'),version('2.17'))
        self.assertLess(version('2.17'),version('2.18'))
        for value in ('2','2.17.','2.17.0.4','2.17-beta','v2.17','2.17\n',[],None,'2.١٧'):
            with self.assertRaises(Refused):version(value)
    def test_real_reader_manifest_and_file_hash(self):
        for data in (b'fixture',b'altered'):
            stream=io.BytesIO()
            with ZipFile(stream,'w') as z:
                z.writestr('sample.txt',data)
                z.writestr('UPDATE-MANIFEST.json',json.dumps(dict(format=1,version='2.17',agent_protocol=1,
                   schema=29,source_schemas=[28],migration='family_model.migrate',files={'sample.txt':hashlib.sha256(b'fixture').hexdigest()})))
            raw=stream.getvalue()
            c=LocalCandidate(stream,len(raw),hashlib.sha256(raw).hexdigest())
            with tempfile.TemporaryDirectory() as d:
                dest=Path(d)/'app.zip'
                self.assertEqual(c.latest()['version'],'2.17');c.download(c.latest(),dest)
                if data==b'fixture':self.assertEqual(unpack(dest,Path(d)/'runtime','2.17')['schema'],29)
                else:
                    with self.assertRaisesRegex(Refused,'INTEGRITY'):unpack(dest,Path(d)/'runtime','2.17')
    def test_no_identical_or_older(self):
        for current,is_new in [('2.16.1',True),('2.17',False),('2.17.0',False),('2.18',False)]:
            with tempfile.TemporaryDirectory() as d:
                ex=mock.Mock();ex.inspect.return_value=dict(version=current,schema=28)
                provider=mock.Mock();provider.latest.return_value=dict(version='2.17',page='test',notes='test')
                engine=Engine({'state':d,'enabled':True},provider,ex)
                self.assertEqual(engine.discover()['newer'],is_new)
                if not is_new:
                    with self.assertRaisesRegex(Refused,'NOT_NEWER'):engine.prepare(local=provider)
                    provider.download.assert_not_called()
    def test_image_prepare_only(self):
        filename=Path(__file__).resolve().parents[1]/'tools/agent-transition/prepare.py'
        if not filename.is_file():self.skipTest('Outil de transition séparé du ZIP applicatif')
        spec=importlib.util.spec_from_file_location('agent_transition_prepare',filename)
        import sys
        m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)
        old='sha256:'+'a'*64; new='sha256:'+'b'*64; commands=[]
        def run(args,input,**opts):
            commands.append(args)
            if args[1]=='build':
                with tarfile.open(fileobj=io.BytesIO(input)) as t:
                    self.assertEqual(set(t.getnames()),{'Dockerfile','security.py','__init__.py'})
                output=new
            elif args[1]=='container':output=old
            else:
                self.assertNotIn('--mount',args);self.assertIn('--read-only',args);self.assertIn('none',args)
                output=''
            return subprocess.CompletedProcess(args,0,output.encode())
        values=m.prepare('docker',filename.parents[2]/'updater_agent',run)
        self.assertFalse(values['activated']);self.assertEqual(values['prepared_image'],new)
        self.assertEqual([a[1] for a in commands],['container','run','build','run','container'])
        with tempfile.TemporaryDirectory() as d:
            root=Path(d).resolve()
            for name in m.OLD:(root/name).write_bytes(b'unknown')
            with self.assertRaises(ValueError):m.verify_old(root)
