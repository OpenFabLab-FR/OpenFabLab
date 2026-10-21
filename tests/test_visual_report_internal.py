"""Small internal aggregates, no disclosure thresholds, fictional data only."""
import io,json,sqlite3,unittest
from unittest import mock
from tests.test_consolidation_212 import ConsolidationTests,pdf_text
import app
from visual_report import public_summary,generate_visual_report


class InternalPDFTests(ConsolidationTests):
    def records(self,n=3,missing=False):
        ids=list(self.f.people)
        with self.db:
            category_keys=[r[0] for r in self.db.execute('SELECT category_key FROM user_categories ORDER BY sort_order,category_key')]
            for index in range(len(ids),n):
                key=self.db.execute("INSERT INTO users(public_id,first_name,last_name,active,category,created_at) VALUES(?,?,?,1,'user','2025-01-01')",
                    (str(93000+index),'PrénomFictif'+str(index),'NOMFICTIF')).lastrowid
                ids.append(key)
            for index,user in enumerate(ids[:n]):
                gender=None if missing else [None,'female','male','non_binary'][index%4]
                city=None if missing or index==0 else f'Commune fictive {index:03d} - Quartier de la rivière et des ateliers'
                nation=None if missing or index==0 else f'Nationalité fictive {index:03d}'
                self.db.execute('UPDATE users SET gender=?,birth_year=?,city=?,city_normalized=?,nationality=?,nationality_normalized=? WHERE id=?',
                    (gender,None if missing or index==0 else 1980+index%40,city,city,nation,nation,user))
                self.db.execute('UPDATE users SET category=? WHERE id=?',(category_keys[index%len(category_keys)],user))
                self.db.execute("INSERT INTO sessions(user_id,check_in,check_out,entry_method) VALUES(?,'2025-08-14T12:00:00+00:00','2025-08-14T13:00:00+00:00','id')",(user,))
        return ids[:n]

    def test_one_user_and_every_small_dimension_are_visible(self):
        self.records(1);projection=public_summary(self.stats(),{})
        self.assertTrue(all(d['available'] and d['total']==1 for d in projection['distributions']))
        self.assertTrue(all(d['rows'][0]['count']==1 and d['rows'][0]['percentage']==100 for d in projection['distributions']))

    def test_threshold_boundaries_no_longer_change_visibility(self):
        self.records(1);statistics=self.stats()
        for total in (1,2,4,5,14,15,20):
            statistics['selected_summary']['unique_users']=total
            statistics['gender_rows']=[dict(key='female',label='Femme',count=total-1,percentage=round((total-1)/total*100,1)),
                                       dict(key='male',label='Homme',count=1,percentage=round(1/total*100,1))]
            dimension=public_summary(statistics,{})['distributions'][1]
            self.assertTrue(dimension['available']);self.assertEqual(dimension['total'],total)
            self.assertEqual(sum(r['count'] for r in dimension['rows']),total)

    def test_missing_data_label_and_denominator_include_all_users(self):
        self.records(3);projection=public_summary(self.stats(),{})
        for dimension in projection['distributions']:
            self.assertEqual(dimension['total'],3)
            self.assertEqual(sum(r['count'] for r in dimension['rows']),3)
        for dimension in projection['distributions'][1:]:
            unknown=next(r for r in dimension['rows'] if r['label']=='Non renseigné')
            self.assertEqual(unknown['count'],1);self.assertEqual(unknown['percentage'],33.3)

    def test_all_missing_is_real_unknown_not_invented_profiles(self):
        self.records(1,missing=True)
        for dimension in public_summary(self.stats(),{})['distributions'][1:]:
            self.assertEqual(dimension['rows'],[dict(label='Non renseigné',count=1,percentage=100.0)])

    def test_all_supported_genders_kept_with_exact_counts(self):
        self.records(4);rows=public_summary(self.stats(),{})['distributions'][1]['rows']
        self.assertEqual({r['label'] for r in rows},{'Femme','Homme','Non-binaire','Non renseigné'})
        self.assertTrue(all(r['count']==1 and r['percentage']==25 for r in rows))

    def test_percentages_reuse_existing_rounding_without_forced_total(self):
        self.records(3);statistics=self.stats();rows=public_summary(statistics,{})['distributions'][1]['rows']
        self.assertAlmostEqual(sum(r['percentage'] for r in rows),99.9)
        self.assertEqual([r['percentage'] for r in rows],[r['percentage'] for r in statistics['gender_rows'] if r['count']])
        self.assertEqual(sum(r['count'] for r in rows),3)

    def test_large_city_and_nationality_lists_use_twenty_not_screen_ten(self):
        self.records(47);statistics=self.stats();projection=public_summary(statistics,{})
        self.assertTrue(any(r['key']=='__other__' for r in statistics['city_rows']))
        for dimension,key in [(projection['distributions'][3],'city_export_rows'),(projection['distributions'][4],'nationality_export_rows')]:
            self.assertEqual(len(dimension['rows']),22)
            self.assertEqual([r['count'] for r in dimension['rows'][:20]],[1]*20)
            other=next(r for r in dimension['rows'] if r['label']=='Autres')
            self.assertEqual(other,dict(label='Autres',count=26,percentage=55.3))
            self.assertEqual(dimension['rows'][-1]['label'],'Non renseigné')
            self.assertEqual(sum(r['count'] for r in dimension['rows']),47)

    def test_top_twenty_boundary_ranking_and_combined_percentage(self):
        self.records(1);statistics=self.stats()
        for size in (0,1,19,20,21,42):
            source=[dict(key=f'city-{i}',label=f'Ville {i:02d}',count=i+1,percentage=0) for i in range(size)]
            total=sum(r['count'] for r in source)+2
            source.append(dict(key='unknown',label='Inconnue',count=2,percentage=round(200/total,1)))
            for row in source:row['percentage']=round(row['count']/total*100,1)
            for key,index in [('city_export_rows',3),('nationality_export_rows',4)]:
                statistics[key]=source
                rows=public_summary(statistics,{})['distributions'][index]['rows']
                self.assertEqual(len(rows),min(size,20)+1+(size>20))
                self.assertEqual(sum(r['count'] for r in rows),total)
                self.assertEqual(rows[-1],dict(label='Non renseigné',count=2,percentage=round(200/total,1)))
                self.assertEqual([r['label'] for r in rows[:min(size,20)]],[f'Ville {i:02d}' for i in range(size-1,max(-1,size-21),-1)])
                if size>20:
                    count=sum(range(1,size-19))
                    self.assertEqual(rows[-2],dict(label='Autres',count=count,percentage=round(count/total*100,1)))

    def test_top_twenty_ties_are_stable_and_other_dimensions_are_not_limited(self):
        self.records(1);statistics=self.stats()
        source=[dict(key=str(i),label=f'Valeur {i:02d}',count=1,percentage=4) for i in reversed(range(25))]
        for key in ('city_export_rows','nationality_export_rows','gender_rows','age_rows'):statistics[key]=source
        before=repr(statistics);data=public_summary(statistics,{})
        for dimension in data['distributions'][3:]:
            self.assertEqual([r['label'] for r in dimension['rows'][:20]],[f'Valeur {i:02d}' for i in range(20)])
            self.assertEqual(dimension['rows'][-1],dict(label='Autres',count=5,percentage=20.0))
        self.assertEqual(len(data['distributions'][1]['rows']),25)
        self.assertEqual(len(data['distributions'][2]['rows']),25)
        self.assertEqual(repr(statistics),before)

    def test_category_history_keeps_sessions_even_with_zero_unique_users(self):
        user=self.f.a
        with self.db:
            self.db.execute("UPDATE users SET category='volunteer' WHERE id=?",(user,))
            self.db.execute("INSERT INTO sessions(user_id,check_in,check_out,entry_method) VALUES(?,'2025-08-14T12:00:00+00:00','2025-08-14T13:00:00+00:00','id')",(user,))
            self.db.execute("UPDATE users SET category='user' WHERE id=?",(user,))
            self.db.execute("INSERT INTO sessions(user_id,check_in,check_out,entry_method) VALUES(?,'2025-08-15T12:00:00+00:00','2025-08-15T13:00:00+00:00','id')",(user,))
        rows=public_summary(self.stats(),{})['distributions'][0]['rows']
        self.assertEqual(sum(r['sessions'] for r in rows),2)
        self.assertEqual(sum(r['hours'] for r in rows),2)
        self.assertTrue(any(r['count']==0 and r['sessions']==1 for r in rows))

    def test_repeated_visits_do_not_inflate_unique_user_denominators(self):
        users=self.records(3)
        with self.db:self.db.execute("INSERT INTO sessions(user_id,check_in,check_out,entry_method) VALUES(?,'2025-08-15T12:00:00+00:00','2025-08-15T13:00:00+00:00','id')",(users[0],))
        data=public_summary(self.stats(),{})
        self.assertEqual(data['summary']['sessions'],4);self.assertEqual(data['summary']['unique_users'],3)
        self.assertTrue(all(d['total']==3 for d in data['distributions']))

    def test_projection_never_carries_individual_fields(self):
        self.records(3);statistics=self.stats();statistics['private_extra']='PRIVATE_SENTINEL'
        projection=public_summary(statistics,{})
        text=json.dumps(projection)
        for value in ('PRIVATE_SENTINEL','first_name','last_name','public_id','user_id','email','phone','Fictif0','EXEMPLE','@example.invalid'):
            self.assertNotIn(value,text)

    def test_full_pdf_contains_small_counts_percentages_and_no_suppression(self):
        self.records(4);content=generate_visual_report(self.stats(),{'name':'Atelier fictif'})
        text=pdf_text(content)
        for value in ('Genres','Homme','Femme','Non-binaire','Non renseigné','25,0 %','Effectif','Total'):
            self.assertIn(value,text)
        for value in ('effectifs insuffisants','non publiée','15 usagers','moins de 5','Fictif0','EXEMPLE','@example.invalid','0600000000'):
            self.assertNotIn(value,text)

    def test_long_pdf_contains_twenty_complete_labels_other_and_unknown(self):
        self.records(47);statistics=self.stats();text=' '.join(pdf_text(generate_visual_report(statistics,{})).split())
        projection=public_summary(statistics,{})
        for dimension in projection['distributions'][3:]:
            for row in dimension['rows']:self.assertIn(row['label'],text)
        for value in ('Autres','Non renseigné','55,3 %','20 valeurs'):self.assertIn(value,text)
        for value in ('Commune fictive 046','Nationalité fictive 046'):self.assertNotIn(value,text)

    def test_zero_period_has_no_invented_unknown_user(self):
        statistics=self.stats(2020);data=public_summary(statistics,{})
        self.assertTrue(all(not d['rows'] and d['total']==0 for d in data['distributions']))
        text=pdf_text(generate_visual_report(statistics,{}))
        self.assertIn('Aucune donnée de fréquentation',text);self.assertNotIn('100,0 %',text)

    def test_generating_pdf_does_not_write_database_or_mutate_statistics(self):
        self.records(3);statistics=self.stats();before=repr(statistics);writes=self.db.total_changes
        schema=self.db.execute('PRAGMA user_version').fetchone()[0]
        for _ in range(2):generate_visual_report(statistics,{'name':'Atelier fictif'})
        self.assertEqual(repr(statistics),before);self.assertEqual(self.db.total_changes,writes)
        self.assertEqual(schema,22);self.assertEqual(self.db.execute('PRAGMA user_version').fetchone()[0],22)

def load_tests(loader,suite,pattern):
    return unittest.TestSuite(InternalPDFTests(n) for n in InternalPDFTests.__dict__ if n.startswith('test_'))
