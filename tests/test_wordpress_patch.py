"""Plugin packaging and compatibility; no network or real data."""
import hashlib
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from zipfile import ZipFile

import build_wordpress_plugin as builder


class WordPressPatchTests(unittest.TestCase):
    def test_application_public_version_is_canonical(self):
        from openfablab import __version__
        import build_openfablab
        self.assertEqual(__version__,'2.8.3')
        self.assertEqual(build_openfablab.OUTPUT.name,'OpenFabLab-2.8.3.zip')

    def test_protocol_advertises_slots_and_keeps_both_environments(self):
        api=(builder.PLUGIN/'includes/class-openfablab-api.php').read_text()
        self.assertIn('animation_slots_v1',api)
        self.assertIn('production',api)
        self.assertIn('test',api)

    def test_uninstall_includes_private_email_option(self):
        source=(builder.PLUGIN/'uninstall.php').read_text()
        self.assertIn("'email_settings'",source)
        self.assertIn('WP_UNINSTALL_PLUGIN',source)

    def test_additive_version_and_schema(self):
        source = (builder.PLUGIN / 'openfablab-reservations.php').read_text()
        self.assertIn('Version: 2.8.2', source)
        self.assertIn("define('OPENFABLAB_RES_VERSION','2.8.2')", source)
        self.assertIn("define('OPENFABLAB_RES_SCHEMA_VERSION','2.8.2-relay3')", source)
        self.assertEqual(builder.OUTPUT.name, 'openfablab-reservations-2.8.2.zip')

    def test_build_is_reproducible_and_allowlisted(self):
        with tempfile.TemporaryDirectory(prefix='openfablab-plugin-patch-') as directory:
            first = builder.build(Path(directory) / 'one.zip')
            second = builder.build(Path(directory) / 'two.zip')
            self.assertEqual(hashlib.sha256(first.read_bytes()).digest(), hashlib.sha256(second.read_bytes()).digest())
            with ZipFile(first) as archive:
                self.assertIsNone(archive.testzip())
                self.assertEqual(archive.namelist(), ['openfablab-reservations/' + name for name in builder.INCLUDED])
                for name in builder.INCLUDED:
                    self.assertEqual(archive.read('openfablab-reservations/' + name), (builder.PLUGIN / name).read_bytes())

    def test_private_files_and_fixtures_are_never_distributed(self):
        with tempfile.TemporaryDirectory(prefix='openfablab-plugin-private-') as directory:
            root = Path(directory)
            for name in builder.INCLUDED:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes((builder.PLUGIN / name).read_bytes())
            for name in ('.secret_key', 'openfablab.db', 'private.openfablab-profile.zip', 'dump.sql', 'capture.png', 'test_fixture.php'):
                (root / name).write_bytes(b'fictional excluded private content')
            with mock.patch.object(builder, 'PLUGIN', root):
                output = builder.build(root / 'plugin.zip')
            with ZipFile(output) as archive:
                self.assertEqual(len(archive.namelist()), len(builder.INCLUDED))
                self.assertFalse(any('fictional excluded' in archive.read(name).decode(errors='ignore') for name in archive.namelist()))

    def test_symlink_source_is_refused_without_replacing_output(self):
        with tempfile.TemporaryDirectory(prefix='openfablab-plugin-symlink-') as directory:
            root = Path(directory)
            for name in builder.INCLUDED:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'fixture')
            (root / builder.INCLUDED[0]).unlink()
            (root / builder.INCLUDED[0]).symlink_to(root / builder.INCLUDED[1])
            output = root / 'plugin.zip'
            output.write_bytes(b'existing distribution must survive')
            with mock.patch.object(builder, 'PLUGIN', root), self.assertRaises(ValueError):
                builder.build(output)
            self.assertEqual(output.read_bytes(), b'existing distribution must survive')

    def test_standalone_distribution_has_full_licenses(self):
        self.assertIn('Copyright (c) 2026 William Aumand',(builder.PLUGIN/'LICENSE').read_text())
        self.assertIn('Permission is hereby granted',(builder.PLUGIN/'LICENSE').read_text())
        self.assertIn('Apache',(builder.PLUGIN/'THIRD_PARTY_NOTICES.md').read_text())
        self.assertIn('Apache License',(builder.PLUGIN/'assets/jsQR-LICENSE.txt').read_text())

    def test_runtime_has_no_historical_wordpress_engine_or_network_client(self):
        files=list(builder.PLUGIN.rglob('*.php'))
        source='\n'.join(path.read_text() for path in files)
        for name in ('OpenFabLab_Bookings','OpenFabLab_Slots','OpenFabLab_Emails','OpenFabLab_Legacy_Reset',
                     'OpenFabLab_Test_Maintenance','OpenFabLab_Reconciliation','OpenFabLab_Family_Gateway'):
            self.assertNotIn(name,source)
        self.assertNotRegex(source,r'\b(?:wp_remote_get|wp_remote_post|wp_mail|promote_waitlist)\s*\(')
        self.assertNotIn('/sync/snapshot',source)
        self.assertNotIn('/sync/commands',source)

    def test_only_empty_historical_storage_can_be_removed(self):
        source=(builder.PLUGIN/'includes/class-openfablab-database.php').read_text()
        self.assertIn('LOCK TABLES',source)
        self.assertIn('UNLOCK TABLES',source)
        self.assertIn("if ((int)$count!==0)",source)
        self.assertIn("$state='retained'",source)
        self.assertNotIn('DELETE FROM',source)
        self.assertNotIn('TRUNCATE',source)
        self.assertNotIn('sync_secret',source)

    def test_admin_secret_rotation_is_secondary_and_guarded(self):
        source=(builder.PLUGIN/'includes/class-openfablab-admin.php').read_text()
        self.assertIn('Diagnostic avancé',source)
        self.assertIn('Environnement Test',source)
        self.assertIn("current_user_can('manage_options')",source)
        self.assertIn("$_SERVER['REQUEST_METHOD']!=='POST'",source)
        self.assertIn("check_admin_referer('openfablab_connection_secret')",source)
        self.assertIn('connection_lock()',source)
        self.assertIn('expires_at>',source)
        self.assertIn('Content-Disposition: attachment',source)

    def test_packaged_core_does_not_contain_previous_wordpress_routes(self):
        root=Path(__file__).resolve().parents[1]
        source=(root/'reservations_sync.py').read_text()
        tablet=(root/'tablet_reservations.py').read_text()
        self.assertNotIn('def _sync_environment',source)
        self.assertNotIn('def receive_events',source)
        self.assertNotIn('def process_requests',tablet)
        self.assertNotIn('/sync/directory',source)
        self.assertNotIn('/public/reserve',tablet)

    def test_historical_test_fixtures_are_excluded_from_both_archives(self):
        import build_openfablab
        paths=[path.relative_to(build_openfablab.ROOT).as_posix() for path in build_openfablab.included_paths()]
        self.assertFalse(any(name.startswith('tests/') for name in paths))
        self.assertFalse(any('historical' in name for name in builder.INCLUDED))

    def test_maintenance_has_no_destructive_or_sync_side_effect_calls(self):
        source = (Path(__file__).parent / 'historical-wordpress/includes/class-openfablab-test-maintenance.php').read_text()
        self.assertNotRegex(source, r'\b(?:DELETE\s+FROM|TRUNCATE|DROP\s+TABLE)\b')
        self.assertNotRegex(source, r'\b(?:wp_mail|promote_waitlist|run_due_tasks|OpenFabLab_Database::event)\s*\(')
        self.assertNotIn('openfablab_res_sync_secret', source)
        self.assertNotIn('token_hash', source)
        self.assertIn("'environment' => 'test'", source)
        self.assertIn("'status' => 'cancelled'", source)


if __name__ == '__main__':
    unittest.main()
