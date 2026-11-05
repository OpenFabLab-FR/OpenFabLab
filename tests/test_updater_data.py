"""Actual SQLite evidence: no secret values, protected history, new writes kept."""
import json
import unittest
from tests import test_v214_core as core
from updater_agent import data_checks as checks
from updater_agent.security import Refused
from app import write_setting


class Data(unittest.TestCase):
    setUp=core.NewVersion.setUp

    def test_snapshot_readonly_hashes_not_secret_values(self):
        write_setting(self.db,'fictional_secret','NEVER_LOG_FICTIONAL_SECRET');self.db.commit()
        before=list(self.db.iterdump());result=checks.snapshot(self.path,26)
        self.assertEqual(result['integrity'],'ok')
        self.assertNotIn('NEVER_LOG_FICTIONAL_SECRET',json.dumps(result))
        self.assertEqual(before,list(self.db.iterdump()))

    def test_migration_compare_retains_all_values_and_refuses_extra_setting(self):
        before=checks.snapshot(self.path,26)
        checks.compare_before_open(self.path,before,dict(schema=26))
        write_setting(self.db,'unknown_new_key','FICTITIOUS');self.db.commit()
        with self.assertRaisesRegex(Refused,'UNEXPECTED_ADDED_SETTING'):
            checks.compare_before_open(self.path,before,dict(schema=26))
        checks.compare_before_open(self.path,before,dict(schema=26,new_settings={'unknown_new_key':'FICTITIOUS'}))

    def test_unknown_secret_change_never_accepted(self):
        write_setting(self.db,'fictional_secret','BEFORE');self.db.commit()
        before=checks.snapshot(self.path,26)
        write_setting(self.db,'fictional_secret','AFTER');self.db.commit()
        with self.assertRaisesRegex(Refused,'HISTORICAL_SETTING_CHANGED'):
            checks.compare_live(self.path,before)

    def test_expected_lazily_created_flags_are_typed_not_a_prefix_wildcard(self):
        self.db.execute("DELETE FROM app_settings WHERE key LIKE 'reservation_participant_calendar_%'");self.db.commit()
        before=checks.snapshot(self.path,26)
        for key in ('reservation_participant_calendar_production','reservation_participant_calendar_test'):
            write_setting(self.db,key,'1')
        self.db.commit();checks.compare_live(self.path,before)
        write_setting(self.db,'reservation_participant_calendar_test','anything_else');self.db.commit()
        with self.assertRaisesRegex(Refused,'UNEXPECTED_ADDED_SETTING'):checks.compare_live(self.path,before)
        write_setting(self.db,'reservation_participant_calendar_test','1')
        write_setting(self.db,'reservation_participant_calendar_unknown','1');self.db.commit()
        with self.assertRaisesRegex(Refused,'UNEXPECTED_ADDED_SETTING'):checks.compare_live(self.path,before)

    def test_legitimate_new_accounts_and_departures_not_lost_or_auto_restored(self):
        before=checks.snapshot(self.path,26)
        self.db.execute("UPDATE users SET first_name='Correction fictive' WHERE id=?",(self.f.a,))
        self.db.execute("INSERT INTO users(public_id,first_name,last_name,active,category,created_at) VALUES('9898','Nouveau','EXEMPLE',1,'user','2026-11-04T12:00:00+00:00')")
        self.db.commit()
        checks.compare_live(self.path,before)
        self.assertTrue(self.db.execute("SELECT 1 FROM users WHERE public_id='9898'").fetchone())
        with self.assertRaisesRegex(Refused,'HISTORICAL_DATA_CHANGED'):
            checks.compare_before_open(self.path,before,dict(schema=26))

    def test_missing_historical_identity_stops_check_never_restores_it(self):
        self.db.execute('CREATE TABLE fictional_history(id TEXT PRIMARY KEY,value TEXT)')
        self.db.execute("INSERT INTO fictional_history VALUES('fixed','private')");self.db.commit()
        before=checks.snapshot(self.path,26)
        self.db.execute('DELETE FROM fictional_history');self.db.commit()
        with self.assertRaisesRegex(Refused,'HISTORICAL_IDENTITIES_MISSING'):checks.compare_live(self.path,before)
        self.assertFalse(self.db.execute('SELECT 1 FROM fictional_history').fetchone())

if __name__=='__main__':unittest.main()
