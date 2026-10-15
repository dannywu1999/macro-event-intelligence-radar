"""Deterministic failure fixtures; no real provider network requests."""
import copy, json, os, tempfile, unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
from unittest.mock import patch
from tools.stage1b_historical_campaign import radar_news_capture_service as s,radar_news_prospective as p

def rss(title='SYNTHETIC ONLY ECB cuts interest rates',date='Mon, 12 Oct 2026 09:00:00 GMT'):
 return ('<rss><channel><item><title>'+title+'</title><link>https://www.ecb.europa.eu/SYNTHETIC-V49</link><pubDate>'+date+'</pubDate></item></channel></rss>').encode()
class Clock:
 def __init__(self):self.value=datetime(2026,10,12,10,tzinfo=timezone.utc)
 def __call__(self):self.value+=timedelta(microseconds=1);return self.value.isoformat().replace('+00:00','Z')
 def advance(self,seconds=1801):self.value+=timedelta(seconds=seconds)
class Capture(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(dir=os.environ['V49_TEST_ROOT']);self.volume=Path(self.tmp.name)
  p.atomic_json(self.volume/'RADAR_DURABLE_VOLUME_V1.json',dict(contract='RADAR_DURABLE_VOLUME_V1',volume_id='test-volume-v49',role='ISOLATED_TEST_VOLUME'))
  self.value=dict(contract=s.CONTRACT,scope=s.LOCAL,root=str(self.volume/'ledger'),durable_root=str(self.volume),volume_id='test-volume-v49',ledger_id='test-ledger-v49',providers=['ECB Press'],daily_quota=6,per_source_quota=6,interval=1800,max_backoff=21600,max_storage_bytes=32*1024*1024,warning_bytes=24*1024*1024,min_free_bytes=4*1024*1024,initialize=True,activation_approved=False,fixture_path=None)
  self.clock=Clock();self.data=rss();self.failure=None;self.calls=[]
  def fetch(provider):
   self.calls.append(provider)
   if self.failure:raise self.failure
   return self.data
  self.fetch=fetch
 def tearDown(self):self.tmp.cleanup()
 def runner(self,value=None):return s.ContinuousRunner(s.Config(value or self.value),clock=self.clock,fetcher=self.fetch)
 def rows(self,runner):return list(runner.store.stream())
 def once(self,runner):
  with p.owner_lock(runner.root):runner.recover();return runner.provider_once('ECB Press')
 def news(self,runner):return [r for r in self.rows(runner) if r['observation_kind']=='NEWS_ARTICLE']
 def test_off_import_and_start_no_process(self):
  with patch.object(s.subprocess,'Popen',side_effect=AssertionError('NO_PROCESS')):
   life=s.Lifecycle();life.start();self.assertEqual(life.status()['status'],'OFF')
 def test_missing_required_config_fails_closed(self):
  value=copy.deepcopy(self.value);value.pop('daily_quota')
  with self.assertRaises(p.StoreError):s.Config(value)
 def test_missing_volume_marker_fails_closed(self):
  (self.volume/'RADAR_DURABLE_VOLUME_V1.json').unlink()
  with self.assertRaises(p.StoreError):self.runner()
 def test_ephemeral_source_tree_and_relative_rejected(self):
  value=copy.deepcopy(self.value);value['root']='relative'
  with self.assertRaises(p.StoreError):s.Config(value)
 def test_production_requires_distinct_approved_role(self):
  value=copy.deepcopy(self.value);value['scope']=s.PRODUCTION
  with self.assertRaises(p.StoreError):s.Config(value)
 def test_production_mount_gate_validation_only_no_capture(self):
  value=copy.deepcopy(self.value);value.update(scope=s.PRODUCTION,activation_approved=True)
  p.atomic_json(self.volume/'RADAR_DURABLE_VOLUME_V1.json',dict(contract='RADAR_DURABLE_VOLUME_V1',volume_id='test-volume-v49',role='AUTHORIZED_DURABLE_VOLUME'))
  with patch.object(s.os.path,'ismount',return_value=False):
   with self.assertRaises(p.StoreError):s.Config(value)
  with patch.object(s.os.path,'ismount',return_value=True):self.assertEqual(s.Config(value).scope,s.PRODUCTION)
  self.assertFalse(Path(value['root']).exists());self.assertEqual(self.calls,[])
 def test_legacy_pilot_cannot_be_adopted(self):
  root=Path(self.value['root']);root.mkdir();(root/'V47_PILOT.json').write_text('{}')
  with self.assertRaises(p.StoreError):self.runner()
 def test_policy_change_cannot_reset_quota(self):
  runner=self.runner();self.once(runner);value=copy.deepcopy(self.value);value['daily_quota']=12
  with self.assertRaises(p.StoreError):self.runner(value)
 def test_daily_quota_persisted_before_fetch(self):
  self.value['daily_quota']=1;runner=self.runner();self.once(runner);self.clock.advance()
  other=self.runner();self.assertEqual(self.once(other)['status'],'REQUEST_BUDGET_EXHAUSTED');self.assertEqual(len(self.calls),1)
  self.assertEqual(other.store.quota('2026-10-12')['total'],1)
 def test_per_source_quota(self):
  self.value['per_source_quota']=1;runner=self.runner();self.once(runner);self.clock.advance()
  self.assertEqual(self.once(runner)['status'],'REQUEST_BUDGET_EXHAUSTED');self.assertEqual(len(self.calls),1)
 def test_midnight_new_day_does_not_erase_previous_quota(self):
  self.value['daily_quota']=1;runner=self.runner();self.once(runner);self.clock.advance(86400);self.once(runner)
  self.assertEqual(runner.store.quota('2026-10-12')['total'],1);self.assertEqual(runner.store.quota('2026-10-13')['total'],1)
 def test_clock_rollback_cannot_reset_day(self):
  runner=self.runner();self.once(runner);self.clock.advance(-86400)
  with self.assertRaises(p.StoreError):self.once(runner)
  self.assertEqual(len(self.calls),1)
 def test_minimum_cadence_survives_restart(self):
  runner=self.runner();self.once(runner);other=self.runner()
  self.assertEqual(self.once(other)['requests'],0);self.assertEqual(len(self.calls),1)
 def test_unchanged_repeat_preserves_first(self):
  runner=self.runner();self.once(runner);first=self.news(runner)[0];self.clock.advance();result=self.once(self.runner())
  self.assertEqual(result['duplicates'],1);self.assertEqual(self.news(runner)[0],first)
 def test_updated_content_is_new_version_not_new_first(self):
  runner=self.runner();self.once(runner);first=self.news(runner)[0];self.clock.advance();self.data=rss('SYNTHETIC ONLY ECB raises interest rates');self.once(runner)
  versions=self.news(runner);self.assertEqual(len(versions),2);self.assertEqual(versions[0]['payload']['observed_at'],versions[1]['payload']['observed_at'])
  earlier=p.research_as_of(runner.store,first['canonical_event_id'],first['observed_at'])
  self.assertEqual(earlier['news'][0]['title'],first['payload']['title'])
 def test_timeout_retains_last_good_and_backoff(self):
  runner=self.runner();self.once(runner);first=self.news(runner);self.clock.advance();self.failure=TimeoutError();self.once(runner)
  source=p.state_from_rows(runner.state_rows())['providers']['ECB Press']['payload']
  self.assertEqual(source['status'],'LAST_VALID_FALLBACK');self.assertEqual(source['consecutive_failures'],1)
  self.clock.advance();self.assertEqual(self.once(runner)['status'],'BACKOFF_OR_NOT_DUE');self.assertEqual(len(self.calls),2);self.assertEqual(self.news(runner),first)
 def test_http406_no_bypass_no_immediate_retry(self):
  runner=self.runner();self.failure=p.FetchError('HTTP_406',True);self.once(runner);self.clock.advance(7200)
  self.assertEqual(self.once(runner)['status'],'SOURCE_PAUSED');self.assertEqual(len(self.calls),1)
 def test_repeated_failure_opens_persisted_circuit(self):
  runner=self.runner();self.failure=TimeoutError()
  for _ in range(5):self.clock.advance(86401);self.once(runner)
  self.clock.advance(86401);other=self.runner()
  self.assertEqual(self.once(other)['status'],'SOURCE_PAUSED');self.assertEqual(len(self.calls),5)
 def test_offline_circuit_ack_preserves_quota_and_history(self):
  runner=self.runner();self.failure=p.FetchError('HTTP_406',True);self.once(runner);before=self.rows(runner)
  s.acknowledge_source_recovery(runner.capture_config,'ECB Press')
  after=self.rows(runner);self.assertEqual(after[:len(before)],before)
  self.assertFalse(p.state_from_rows(runner.store.news_capture_rows())['providers']['ECB Press']['payload']['circuit_open'])
  self.assertTrue(p.state_from_rows(runner.state_rows())['providers']['ECB Press']['payload']['circuit_open'])
  self.assertEqual(runner.store.quota('2026-10-12')['total'],1);self.assertEqual(len(self.calls),1)
 def test_empty_and_invalid_response_fail_once(self):
  runner=self.runner()
  for body in [b'',b'<rss>',b'{}']:
   self.data=body;self.clock.advance(86401);self.assertEqual(self.once(runner)['status'],'FAILED')
  self.assertEqual(self.news(runner),[]);self.assertEqual(len(self.calls),3)
 def test_one_source_timeout_next_source_proceeds_sequentially(self):
  self.value['providers']=['ECB Press','Global Voices'];runner=self.runner();calls=[]
  def fetch(name):
   calls.append(name)
   if name=='ECB Press':raise TimeoutError()
   return b'<rss><channel></channel></rss>'
  runner.fetcher=fetch;runner.serve(max_cycles=1)
  self.assertEqual(calls,['ECB Press','Global Voices']);self.assertEqual(runner.store.quota('2026-10-12')['total'],2)
 def test_private_shutdown_stops_before_next_provider(self):
  self.value['providers']=['ECB Press','Global Voices'];runner=self.runner();calls=[]
  def fetch(provider):
   calls.append(provider);p.atomic_json(runner.root/'capture-stop.json',dict(contract=s.CONTRACT,target_pid=os.getpid(),stop=True));return rss()
  runner.fetcher=fetch;runner.serve(max_cycles=1)
  self.assertEqual(calls,['ECB Press']);self.assertEqual(runner.store.quota('2026-10-12')['total'],1)
 def test_source_recovers_without_resetting_first(self):
  runner=self.runner();self.once(runner);first=self.news(runner);self.clock.advance();self.failure=TimeoutError();self.once(runner)
  self.failure=None;self.clock.advance(3601);self.once(runner)
  self.assertEqual(self.news(runner),first);self.assertEqual(p.state_from_rows(runner.state_rows())['providers']['ECB Press']['payload']['consecutive_failures'],0)
 def test_storage_probe_failure_prevents_request(self):
  runner=self.runner()
  with patch.object(runner,'probe',side_effect=PermissionError()):
   with self.assertRaises(PermissionError):runner.provider_once('ECB Press')
  self.assertEqual(self.calls,[])
 def test_capacity_stops_before_quota_or_request(self):
  runner=self.runner()
  with patch.object(s.shutil,'disk_usage',return_value=type('Disk',(),{'free':0})()):
   with self.assertRaises(p.StoreError):runner.provider_once('ECB Press')
  self.assertEqual(self.calls,[]);self.assertEqual(runner.store.quota('2026-10-12')['total'],0)
 def test_warning_and_no_retention_deletion(self):
  self.value['warning_bytes']=1;runner=self.runner();self.once(runner)
  self.assertTrue(runner.capacity()['warning']);self.assertTrue(runner.root.joinpath('receipts').is_dir())
 def test_corrupt_checkpoint_rebuilt_preserving_evidence(self):
  runner=self.runner();self.once(runner);before=self.rows(runner);(runner.root/'checkpoint.json').write_bytes(b'{broken')
  runner.recover();self.assertEqual(self.rows(runner),before);self.assertTrue(list(runner.root.glob('checkpoint.corrupt-*')))
 def test_torn_receipt_recovered_from_committed_ledger(self):
  runner=self.runner();self.once(runner);path=next((runner.root/'receipts').glob('*.json'));original=path.read_bytes();path.write_bytes(original[:15]);runner.recover()
  self.assertEqual(path.read_bytes(),original);self.assertTrue(list(path.parent.glob('*.partial-*')))
 def test_modified_receipt_fails_closed(self):
  runner=self.runner();self.once(runner);path=next((runner.root/'receipts').glob('*.json'));path.write_bytes(b'corrupt-not-prefix')
  with self.assertRaises(p.StoreError):runner.recover()
 def test_reserved_crash_spends_quota_and_retains_cadence(self):
  runner=self.runner();original=runner.publish_checkpoint;runner.publish_checkpoint=lambda:(_ for _ in ()).throw(p.StoreError('STORE_CHECKPOINT_INTERRUPTED'))
  with self.assertRaises(p.StoreError):runner.provider_once('ECB Press')
  self.assertEqual(self.calls,[]);other=self.runner();other.recover()
  self.assertEqual(other.store.quota('2026-10-12')['total'],1);self.assertEqual(self.once(other)['requests'],0)
 def test_sqlite_backup_and_actual_restore_asof(self):
  runner=self.runner();self.once(runner);original=self.rows(runner);destination=self.volume/'restored'
  manifest=s.backup_capture(runner.capture_config,destination);target=self.volume/'verified_restore'
  s.restore_capture(runner.capture_config,destination,target);self.clock.value=datetime.now(timezone.utc)
  value=copy.deepcopy(self.value);value.update(root=str(target),initialize=False)
  restored=self.runner(value);restored.recover();self.assertEqual(self.rows(restored)[:len(original)],original)
  first=self.news(runner)[0]
  self.assertEqual(p.research_as_of(restored.store,first['canonical_event_id'],first['observed_at']),p.research_as_of(runner.store,first['canonical_event_id'],first['observed_at']))
  self.assertEqual(len(manifest['receipt_hashes']),1)
 def test_backup_manifest_verified_before_restore(self):
  runner=self.runner();self.once(runner);backup=self.volume/'backup';s.backup_capture(runner.capture_config,backup)
  restored=self.volume/'restore_target';result=s.restore_capture(runner.capture_config,backup,restored)
  self.assertEqual(result['status'],'RESTORED_NOT_STARTED')
  self.clock.value=datetime.now(timezone.utc);value=copy.deepcopy(self.value);value.update(root=str(restored),initialize=False)
  reader=self.runner(value);reader.recover();self.assertEqual(self.rows(reader)[:-1],self.rows(runner))
  self.assertEqual(self.once(reader)['status'],'REQUEST_BUDGET_EXHAUSTED');self.assertEqual(len(self.calls),1)
 def test_corrupt_backup_never_restores(self):
  runner=self.runner();self.once(runner);backup=self.volume/'backup';s.backup_capture(runner.capture_config,backup)
  with (backup/'evidence.sqlite3').open('ab') as f:f.write(b'corrupt')
  target=self.volume/'must_not_create'
  with self.assertRaises(p.StoreError):s.restore_capture(runner.capture_config,backup,target)
  self.assertFalse(target.exists())
 def test_foreign_local_scope_cannot_be_promoted(self):
  runner=self.runner();self.once(runner);value=copy.deepcopy(self.value);value.update(scope=s.PRODUCTION,activation_approved=True)
  p.atomic_json(self.volume/'RADAR_DURABLE_VOLUME_V1.json',dict(contract='RADAR_DURABLE_VOLUME_V1',volume_id='test-volume-v49',role='AUTHORIZED_DURABLE_VOLUME'))
  with self.assertRaises(p.StoreError):self.runner(value)
 def test_paged_history_over_20000_without_weakening_legacy_limit(self):
  runner=self.runner();records=[runner.record('SOURCE_STATE','v49:audit:'+str(i),dict(record_type='AUDIT',index=i)) for i in range(20001)]
  runner.store.append(records,observed_at=self.clock());runner.recover()
  self.assertEqual(len(list(runner.store.stream())),20001);self.assertEqual(runner.state_rows(),[])
  with self.assertRaises(p.StoreError):p.ledger_rows(p.IntelligenceStore(runner.store.path))
 def test_news_cache_integrity_fail_closed(self):
  runner=self.runner();self.once(runner);(runner.root/'CURRENT_NEWS.json').write_text('[]')
  from tools.stage1b_historical_campaign import global_event_radar_read_adapter as adapter
  with self.assertRaises(p.StoreError):s.CaptureIngestion(runner.store).read_view(adapter,adapter.EvidencePaths.from_environment())
 def test_capture_event_reader_preserves_related_identity_versions(self):
  runner=self.runner();self.once(runner);first=self.news(runner)[0];event=first['canonical_event_id']
  payload=dict(official_evidence_id='SYNTHETIC-FACT',canonical_event_id=event,authority_role='FACT_AUTHORITY',fact_proposition='SYNTHETIC ONLY one proposition',evidence_status='OFFICIAL_PARTIAL')
  self.clock.advance();runner.store.append([runner.record('OFFICIAL_EVIDENCE','SYNTHETIC-FACT',payload,event)],observed_at=self.clock())
  prior=self.clock();self.clock.advance();moved={**payload,'canonical_event_id':'SYNTHETIC-other-event'}
  runner.store.append([runner.record('OFFICIAL_EVIDENCE','SYNTHETIC-FACT',moved,'SYNTHETIC-other-event')],observed_at=self.clock())
  self.assertEqual(sum(r['observation_kind']=='OFFICIAL_EVIDENCE' for r in runner.store.read_as_of(event,prior)),1)
  self.assertEqual(sum(r['observation_kind']=='OFFICIAL_EVIDENCE' for r in runner.store.read_as_of(event,self.clock())),2)

if __name__=='__main__':unittest.main()
