"""Complete WordPress component, run from the full candidate source tree."""
import hashlib,re,tempfile,unittest
from pathlib import Path
from zipfile import ZipFile
import build_wordpress_plugin as builder

class PluginDistribution(unittest.TestCase):
    def test_reproducible_complete_plugin_has_all_local_catalogs_and_includes(self):
        with tempfile.TemporaryDirectory() as folder:
            first=builder.build(Path(folder)/'one.zip');second=builder.build(Path(folder)/'two.zip')
            self.assertEqual(hashlib.sha256(first.read_bytes()).digest(),hashlib.sha256(second.read_bytes()).digest())
            with ZipFile(first) as archive:
                self.assertIsNone(archive.testzip())
                expected={'openfablab-reservations/'+p.relative_to(builder.PLUGIN).as_posix() for p in builder.PLUGIN.rglob('*') if p.is_file()}
                self.assertEqual(set(archive.namelist()),expected)
                self.assertTrue(all(archive.read(n)==(builder.PLUGIN/Path(n).relative_to('openfablab-reservations')).read_bytes() for n in expected))
                for code in ('en','de','es','fi'):self.assertIn('openfablab-reservations/languages/'+code+'.json',expected)
                self.assertIn('openfablab-reservations/includes/class-openfablab-i18n.php',expected)
        source=(builder.PLUGIN/'openfablab-reservations.php').read_text()
        self.assertEqual(builder.VERSION,'2.15.0');self.assertIn("OPENFABLAB_RES_VERSION','2.15.0'",source)
        self.assertIn("OPENFABLAB_RES_SCHEMA_VERSION','2.8.2-relay3'",source)
        self.assertFalse(any(p.suffix in ('.db','.zip','.log') for p in builder.PLUGIN.rglob('*')))
