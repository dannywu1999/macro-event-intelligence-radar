"""TEMP-only SQLite integrity, durability and current real projection preservation."""
import copy,csv,hashlib,json,os,sqlite3,tempfile,threading,time,unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from unittest.mock import Mock,patch
from tools.stage1b_historical_campaign.radar_intelligence_store import IntelligenceStore,StoreError,IntelligenceRecorder,configured_db,time_value
from tools.stage1b_historical_campaign import global_event_radar_read_adapter as radar
from tools.stage1b_historical_campaign.radar_reality_replay import replay_event_as_of
from radar_replay_fixture import projection,at,ROOT
class StoreTests(unittest.TestCase):
 def setUp(self):self.temp=tempfile.TemporaryDirectory(prefix="radar-a6-test-");self.db=Path(self.temp.name)/'intelligence.sqlite3';self.store=IntelligenceStore(self.db,create=True);self.v,self.eid=projection()
 def tearDown(self):self.temp.cleanup()
 def rows(self):
  with self.store.connection() as db:return [tuple(r) for r in db.execute('SELECT * FROM observations ORDER BY observation_id')]
 def test_schema(self):
  with self.store.connection() as db:self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],1);self.assertEqual(db.execute('SELECT value FROM schema_metadata').fetchone()[0],'RADAR_INTELLIGENCE_DB_V1');self.assertEqual(db.execute('PRAGMA journal_mode').fetchone()[0],'wal')
 def test_default_disabled(self):
  with patch.dict(os.environ,{},clear=True):self.assertIsNone(configured_db())
 def test_explicit_paths(self):
  with patch.dict(os.environ,{'RADAR_INTELLIGENCE_DB':str(self.db)}):self.assertEqual(configured_db(),self.db)
  with patch.dict(os.environ,{'RADAR_INTELLIGENCE_DB':'','RADAR_RUNTIME_ROOT':self.temp.name}):self.assertEqual(configured_db(),Path(self.temp.name)/'intelligence/radar_intelligence.sqlite3')
 def test_inside_source_tree_rejected(self):self.assertRaises(StoreError,IntelligenceStore,ROOT/'forbidden.sqlite3',create=True)
 def test_read_open_never_creates(self):p=Path(self.temp.name)/'absent/new.sqlite3';self.assertRaises(StoreError,IntelligenceStore,p);self.assertFalse(p.parent.exists())
 def test_new_schema_rejected(self):
  with closing(sqlite3.connect(self.db)) as d, d:d.execute("UPDATE schema_metadata SET value='NEWER' WHERE key='contract_version'")
  self.assertRaises(StoreError,IntelligenceStore,self.db);self.assertRaises(StoreError,IntelligenceStore,self.db,create=True)
 def test_corrupt_database(self):p=Path(self.temp.name)/'bad.db';p.write_bytes(b'broken');self.assertRaises(StoreError,IntelligenceStore,p)
 def test_append_idempotency(self):ids=self.store.ingest_projection(self.v,observed_at=at('09:00'));before=self.rows();self.assertTrue(ids);self.assertEqual(self.store.ingest_projection(self.v,observed_at=at('09:00')),[]);self.assertEqual(before,self.rows())
 def test_repeated_poll_no_duplicates(self):self.store.ingest_projection(self.v,observed_at=at('09:00'));before=self.rows();self.assertEqual(self.store.ingest_projection(self.v,observed_at=at('09:05')),[]);self.assertEqual(before,self.rows())
 def test_semantic_key_order(self):a=self.store.ingest_projection(self.v,observed_at=at('09:00'));reordered=json.loads(json.dumps(self.v,sort_keys=True));self.assertEqual(self.store.ingest_projection(reordered,observed_at=at('09:00')),[])
 def test_changed_only_one_append(self):self.store.ingest_projection(self.v,observed_at=at('09:00'));before=self.rows();v=copy.deepcopy(self.v);v['items'][0]['title']='Changed synthetic title';ids=self.store.ingest_projection(v,observed_at=at('09:05'));self.assertEqual(len(ids),1);self.assertTrue(set(before)<=set(self.rows()))
 def test_old_duplicate_after_new_version(self):self.store.ingest_projection(self.v,observed_at=at('09:00'));v=copy.deepcopy(self.v);v['items'][0]['title']='changed';self.store.ingest_projection(v,observed_at=at('09:05'));self.assertEqual(self.store.ingest_projection(self.v,observed_at=at('09:00')),[])
 def test_backdate_rejected(self):self.store.ingest_projection(self.v,observed_at=at('09:05'));v=copy.deepcopy(self.v);v['items'][0]['title']='changed';self.assertRaises(StoreError,self.store.ingest_projection,v,observed_at=at('09:00'))
 def test_conflicting_same_time_rollback(self):self.store.ingest_projection(self.v,observed_at=at('09:00'));before=self.rows();v=copy.deepcopy(self.v);v['items'][0]['title']='changed';self.assertRaises(StoreError,self.store.ingest_projection,v,observed_at=at('09:00'));self.assertEqual(before,self.rows())
 def test_trigger_update_delete(self):
  self.store.ingest_projection(self.v,observed_at=at('09:00'))
  for sql in ["UPDATE observations SET payload='{}'","DELETE FROM observations"]:
   with self.assertRaises(sqlite3.IntegrityError),closing(sqlite3.connect(self.db)) as db, db:db.execute(sql)
 def test_read_connection_cannot_write(self):
  with self.store.connection() as db,self.assertRaises(sqlite3.OperationalError):db.execute('DELETE FROM observations')
 def test_restart(self):self.store.ingest_projection(self.v,observed_at=at('09:00'));old=self.rows();new=IntelligenceStore(self.db);self.assertEqual(new.read_as_of(self.eid,at('09:05')),self.store.read_as_of(self.eid,at('09:05')));self.assertEqual(old,self.rows())
 def test_import_old_timestamp_not_backfilled(self):self.store.ingest_projection(self.v,observed_at=at('11:00'));r=replay_event_as_of(self.store,self.eid,at('10:59'));self.assertEqual(r['replay_status'],'NO_OBSERVATIONS');r=replay_event_as_of(self.store,self.eid,at('11:00'));self.assertEqual(r['news_observations'][0]['payload']['observed_at'],at('09:00'));self.assertEqual(r['news_observations'][0]['observed_at'],'2026-10-07T11:00:00.000000Z')
 def test_exact_microseconds(self):a=time_value('2026-10-07T09:00:00.000001Z')[1];b=time_value('2026-10-07T09:00:00.000002Z')[1];self.assertEqual(b-a,1)
 def test_freeze_persist_restart(self):self.store.ingest_projection(self.v,observed_at=at('09:00'));f=self.store.freeze_event(self.eid,freeze_key='SYNTHETIC_FREEZE',as_of=at('09:00'),created_at=at('09:01'));self.assertEqual(IntelligenceStore(self.db).freezes(self.eid),[f])
 def test_freeze_idempotency(self):self.store.ingest_projection(self.v,observed_at=at('09:00'));f=self.store.freeze_event(self.eid,freeze_key='key',as_of=at('09:00'),created_at=at('09:01'));again=self.store.freeze_event(self.eid,freeze_key='key',as_of=at('09:00'),created_at=at('09:02'));self.assertEqual(f,again);self.assertEqual(len(self.store.freezes(self.eid)),1)
 def test_old_freeze_bytes_unchanged(self):self.store.ingest_projection(self.v,observed_at=at('09:00'));f=self.store.freeze_event(self.eid,freeze_key='key1',as_of=at('09:00'),created_at=at('09:00'));before=self.store.freezes(self.eid);v,_=projection('09:45');self.store.ingest_projection(v,observed_at=at('09:45'));new=self.store.freeze_event(self.eid,freeze_key='key2',as_of=at('09:45'),created_at=at('09:45'));self.assertNotEqual(f['macroview_id'],new['macroview_id']);self.assertIn(f,self.store.freezes(self.eid));self.assertEqual(before[0],f)
 def test_freeze_trigger(self):
  self.store.ingest_projection(self.v,observed_at=at('09:00'));self.store.freeze_event(self.eid,freeze_key='key',as_of=at('09:00'),created_at=at('09:00'))
  for sql in ["UPDATE macroview_freezes SET payload='{}'","DELETE FROM macroview_freezes"]:
   with self.assertRaises(sqlite3.IntegrityError),closing(sqlite3.connect(self.db)) as db, db:db.execute(sql)
 def test_freeze_cannot_use_future_created_time(self):self.store.ingest_projection(self.v,observed_at=at('09:00'));self.assertRaises(StoreError,self.store.freeze_event,self.eid,freeze_key='key',as_of=at('09:05'),created_at=at('09:00'))
 def test_freeze_before_observation_rejected(self):self.store.ingest_projection(self.v,observed_at=at('09:00'));self.assertRaises(StoreError,self.store.freeze_event,self.eid,freeze_key='key',as_of=at('08:59'),created_at=at('09:00'))
 def test_recorder_dedup_owned_thread(self):f=Mock(return_value=self.v);rec=IntelligenceRecorder(self.db,f,clock=lambda:at('09:00'));self.assertTrue(rec.record_once());self.assertTrue(rec.record_once());self.assertEqual(len(self.store.freezes(self.eid)),1);rec.start();thread=rec.thread;rec.start();self.assertIs(rec.thread,thread);rec.close();self.assertFalse(thread.is_alive())
 def test_recorder_failure_is_bounded(self):rec=IntelligenceRecorder(self.db,Mock(side_effect=StoreError('unavailable')));self.assertFalse(rec.record_once());self.assertEqual(rec.status,'UNAVAILABLE');rec.close()
 def test_real_eia_ecb_bundle_preserved(self):
  bundle=ROOT/'demo/radar_public';before={n:(bundle/n).read_bytes() for n in ['official-packet.json','ecb-official-packet.json','news/rss_headlines_eia_snapshot.csv']};packet=json.loads(before['ecb-official-packet.json']);rows=list(csv.DictReader(before['news/rss_headlines_eia_snapshot.csv'].decode().splitlines()));rows.append(dict(observed_time=packet['official_project_first_seen_at'],event_time='',headline_or_text=packet['document_title'],source_name='ECB Press',source_url=packet['article_reference']));p=Path(self.temp.name)/'real-news.json';p.write_text(json.dumps(rows),'utf-8');v=radar.build_radar_view(radar.EvidencePaths(news=p,official=bundle/'official-packet.json'));self.assertEqual(len(v['official_evidence']),2);self.store.ingest_projection(v,observed_at='2099-01-01T00:00:00Z')
  for event in v['events']:
   r=replay_event_as_of(self.store,event['event_id'],'2099-01-01T00:00:00Z');self.assertEqual(r['reconstructed_macroview']['snapshot']['event']['geography'],event['geography']);self.assertEqual(r['reconstructed_macroview']['expectation_state'],'NONE')
  self.assertEqual(before,{n:(bundle/n).read_bytes() for n in before})
 def test_writer_readers(self):
  self.store.ingest_projection(self.v,observed_at=at('09:00'))
  def read(_):return replay_event_as_of(IntelligenceStore(self.db),self.eid,at('09:30'))['replay_status']
  with ThreadPoolExecutor(max_workers=5) as pool:
   results=[pool.submit(read,i) for i in range(20)];v=copy.deepcopy(self.v);v['items'][0]['title']='Concurrent synthetic update';self.store.ingest_projection(v,observed_at=at('09:20'));self.assertTrue(all(r.result()=='AVAILABLE' for r in results))
  with self.store.connection() as db:self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0],'ok')
 def test_same_key_same_contents_later_time_reuses_original_freeze(self):
  self.store.ingest_projection(self.v,observed_at=at('09:00'));first=self.store.freeze_event(self.eid,freeze_key='same-key',as_of=at('09:00'),created_at=at('09:01'));later=self.store.freeze_event(self.eid,freeze_key='same-key',as_of=at('09:05'),created_at=at('09:06'));self.assertEqual(first,later);self.assertEqual(len(self.store.freezes(self.eid)),1)
 def test_persisted_freeze_raw_bytes_unchanged(self):
  self.store.ingest_projection(self.v,observed_at=at('09:00'));f=self.store.freeze_event(self.eid,freeze_key='key',as_of=at('09:00'),created_at=at('09:01'))
  with self.store.connection() as db:before=tuple(db.execute('SELECT payload,payload_sha256,created_at,provenance FROM macroview_freezes WHERE macroview_id=?',(f['macroview_id'],)).fetchone())
  v,_=projection('09:30');self.store.ingest_projection(v,observed_at=at('09:30'));self.store.freeze_event(self.eid,freeze_key='key',as_of=at('09:30'),created_at=at('09:30'))
  with self.store.connection() as db:after=tuple(db.execute('SELECT payload,payload_sha256,created_at,provenance FROM macroview_freezes WHERE macroview_id=?',(f['macroview_id'],)).fetchone())
  self.assertEqual(before,after)
if __name__=='__main__':unittest.main()
