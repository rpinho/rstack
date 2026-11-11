"""Lane liveness acceptance tests: frozen clock, fake pushes, no live workers/pods."""
import contextlib
import datetime as dt
import fcntl
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cadence
import lane_alerts
import pods
import rh
import sweep

UTC = dt.timezone.utc
NOW = dt.datetime(2026, 11, 3, 14, 0, tzinfo=UTC)
ORIGINAL_PUSH = lane_alerts.push
SECRET = 'PRIVATE IDEA TITLE AND RESEARCH FILE CONTENTS'


class FrozenDateTime(dt.datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW.astimezone(tz) if tz else NOW.replace(tzinfo=None)


class LaneHealthTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.lane = self.make_lane('restricted-a')
        self.start_patch(patch('datetime.datetime', FrozenDateTime))
        self.start_patch(patch.object(rh, 'now', return_value=NOW.isoformat()))
        self.start_patch(patch.object(rh, 'banned_cs_sessions', return_value=[]))
        self.start_patch(patch.object(rh, 'taste_models', return_value=('claude-science',)))
        self.push = self.start_patch(patch.object(lane_alerts, 'push', return_value=True))
        # Mimic reversible Trash within the fixture, without Finder on test files.
        self.trashed = []
        self.start_patch(patch.object(lane_alerts, 'trash', side_effect=self.trash))
        self.start_patch(patch.object(sweep, 'run_worker', side_effect=AssertionError('worker forbidden')))
        self.start_patch(patch.object(pods, 'probe', side_effect=AssertionError('SSH forbidden')))

    def start_patch(self, p):
        result = p.start()
        self.addCleanup(p.stop)
        return result

    def trash(self, path):
        if path.exists():
            dest = self.root / 'test-trash' / (str(len(self.trashed)) + '-' + path.name)
            dest.parent.mkdir(exist_ok=True)
            shutil.move(str(path), str(dest))
            self.trashed.append(dest)

    def make_lane(self, name, healthy=False):
        lane = self.root / 'lanes' / name
        lane.mkdir(parents=True)
        (lane / 'INTAKE.toml').write_text('keywords = []\n')
        (lane / 'SWEEP.toml').write_text('enabled = false\nstart_date = "2026-11-01"\n')
        if healthy:
            self.healthy(lane)
        return lane

    def healthy(self, lane=None):
        lane = lane or self.lane
        (lane / 'IDEAS.jsonl').write_text(''.join(json.dumps(dict(id='ID-'+str(i),
            created=NOW.isoformat(), status='new', source_type='internal', claim=SECRET))+'\n' for i in range(3)))
        (lane / 'INTAKE_RUNS.jsonl').write_text(json.dumps(dict(created=NOW.isoformat(), sources_read=[SECRET]))+'\n')

    def config(self, lane=None, **values):
        lane = lane or self.lane
        cfg = dict(deliverable=SECRET, every_hours=26, owner_session=lane.name,
                   evidence_globs=['evidence/*.receipt'])
        cfg.update(values)
        (lane / 'CADENCE.toml').write_text(''.join(k+' = '+json.dumps(v)+'\n' for k,v in cfg.items()))
        return cfg

    def receipt(self, age=0, lane=None, name='delivery.receipt'):
        lane = lane or self.lane
        path = lane / 'evidence' / name
        path.parent.mkdir(exist_ok=True)
        path.write_text(SECRET)
        clock = (NOW-dt.timedelta(hours=age)).timestamp()
        os.utime(str(path), (clock, clock))
        return path

    def cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = rh.main(['--root', str(self.root)] + list(args))
        self.assertEqual(err.getvalue(), '')
        return rc, out.getvalue()

    def snapshot(self, path=None):
        path = path or self.root
        return {str(p.relative_to(path)): (p.read_bytes(), p.stat().st_mtime_ns)
                for p in path.rglob('*') if p.is_file()}

    def assert_private(self):
        for path in (self.root/'alerts').glob('*'):
            text = path.read_text()
            self.assertNotIn(SECRET, text)
            self.assertNotIn('delivery.receipt', text)
            self.assertNotIn('evidence/', text)
            for line in text.splitlines():
                self.assertIn(line.split('=')[0], ('lane', 'failure_count', 'checks', 'owner_session'))
        for args in self.push.call_args_list:
            self.assertNotIn(SECRET, args.args[0])
            self.assertNotIn('evidence/', args.args[0])

    def test_lint_all_continues_past_failing_disabled_lane_json_exit(self):
        self.healthy()
        (self.lane/'INTAKE.toml').write_text('invalid '+SECRET)
        self.make_lane('zdisabled', healthy=True)
        rc, text = self.cli('lint', '--all', '--json')
        rows = json.loads(text)
        self.assertEqual(rc, 1)
        self.assertEqual([(r['lane'],r['status']) for r in rows], [('restricted-a','FAIL'),('zdisabled','OK')])
        self.assertEqual(rows[0]['failures'][0]['check'], 'lint-input-invalid')
        self.assertNotIn(SECRET, text)
        rc, text = self.cli('lint', '--all')
        self.assertEqual(rc, 1)
        self.assertIn('FAIL restricted-a', text)
        self.assertIn('OK zdisabled', text)

    def test_lint_all_clean_exit_and_read_only(self):
        self.healthy()
        self.make_lane('zdisabled', healthy=True)
        before = self.snapshot()
        rc, text = self.cli('lint', '--all', '--json')
        self.assertEqual(rc, 0)
        self.assertEqual(len(json.loads(text)), 2)
        self.assertEqual(before,self.snapshot())
        self.push.assert_not_called()

    def test_lint_push_dedupe_change_same_count_and_recovery_once(self):
        # Real lint, disabled lane, no research rows required to trigger health checks.
        self.assertEqual(rh.lint_monitor(self.root), 1)
        active = self.root/'alerts/lint-failed-restricted-a'
        self.assertTrue(active.exists())
        self.assertEqual(self.push.call_count,1)
        rh.lint_monitor(self.root)
        self.assertEqual(self.push.call_count,1)
        # Exchange one failure for another while preserving the number of failures.
        self.healthy()
        (self.lane/'INTAKE.toml').write_text('keywords = []\nclaude_science_required = true\n')
        rh.lint_monitor(self.root)
        self.assertEqual(self.push.call_count,2)
        (self.lane/'INTAKE.toml').write_text('keywords = []\n')
        self.assertEqual(rh.lint_monitor(self.root),0)
        self.assertFalse(active.exists())
        recovered = self.root/'alerts/lint-recovered-restricted-a'
        self.assertTrue(recovered.exists())
        self.assertIn('failure_count=0',recovered.read_text())
        before = recovered.stat().st_mtime_ns
        rh.lint_monitor(self.root)
        self.assertEqual(self.push.call_count,3)
        self.assertEqual(recovered.stat().st_mtime_ns,before)
        self.assert_private()

    def test_fingerprint_sorted_and_changed_messages_repush_without_leaking(self):
        failures = [dict(check='queue-depth',message=SECRET+' A'),dict(check='idea-policy',message=SECRET+' B')]
        row = dict(lane='restricted-a',failures=failures)
        lane_alerts.monitor(self.root,'lint',[row])
        lane_alerts.monitor(self.root,'lint',[dict(row,failures=list(reversed(failures)))])
        self.assertEqual(self.push.call_count,1)
        # Same count/check name, different failed obligation => new failure set.
        failures[0] = dict(check='queue-depth',message=SECRET+' C')
        lane_alerts.monitor(self.root,'lint',[row])
        self.assertEqual(self.push.call_count,2)
        self.assert_private()
        self.assertNotIn(SECRET,(self.root/'.lane-health-state/lint-restricted-a.json').read_text())

    def test_failure_and_recovery_push_retry_survive_monitor_restart(self):
        self.push.side_effect=[False,True,False,True]
        rh.lint_monitor(self.root)
        rh.lint_monitor(self.root)
        rh.lint_monitor(self.root)
        self.assertEqual(self.push.call_count,2)
        self.healthy()
        rh.lint_monitor(self.root)
        recovered=self.root/'alerts/lint-recovered-restricted-a'
        before=recovered.stat().st_mtime_ns
        state=json.loads((self.root/'.lane-health-state/lint-restricted-a.json').read_text())
        self.assertIn('pending',state)
        rh.lint_monitor(self.root)
        rh.lint_monitor(self.root)
        self.assertEqual(self.push.call_count,4)
        self.assertEqual(before,recovered.stat().st_mtime_ns)
        self.assertNotIn('pending',json.loads((self.root/'.lane-health-state/lint-restricted-a.json').read_text()))
        self.assert_private()

    def test_recurrent_failure_after_recovery_pushes_again(self):
        rh.lint_monitor(self.root)
        self.healthy()
        rh.lint_monitor(self.root)
        (self.lane/'INTAKE_RUNS.jsonl').write_text('')
        rh.lint_monitor(self.root)
        self.assertEqual(self.push.call_count,3)

    def test_scheduler_runs_both_monitors_before_pod_registry_failure(self):
        self.config()
        before=self.snapshot(self.root/'lanes')
        with patch.object(pods,'registry',side_effect=ValueError('broken pod registry')):
            with self.assertRaisesRegex(ValueError,'broken pod registry'):
                pods.main(self.root,rh.parser().parse_args(['pods','check']),rh)
        self.assertTrue((self.root/'alerts/lint-failed-restricted-a').exists())
        self.assertTrue((self.root/'alerts/lane-stalled-restricted-a').exists())
        self.assertEqual(self.push.call_count,2)
        self.assertEqual(before,self.snapshot(self.root/'lanes'))
        self.assert_private()

    def test_scheduler_checks_disabled_lane_and_dispatches_independent_maintenance(self):
        self.config()
        args=rh.parser().parse_args(['pods','check'])
        with patch.object(pods,'registry',return_value=[]), patch.object(pods,'check',return_value=0) as check,\
             patch.object(pods.harvest,'run',return_value=0) as harvest, patch.object(pods,'reap',return_value=0) as reap,\
             patch.object(pods.pod_maintenance,'schedule',return_value=0) as schedule:
            self.assertEqual(pods.main(self.root,args,rh),1)
        schedule.assert_called_once_with(self.root.resolve(), [])
        check.assert_not_called()
        harvest.assert_not_called()
        reap.assert_not_called()
        self.assertEqual(self.push.call_count,2)

    def test_monitor_does_not_take_lane_lock_and_alert_lock_is_nonblocking(self):
        lock=self.lane/'.lock'
        with lock.open('w') as stream:
            fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
            rh.lint_monitor(self.root)
        self.assertEqual(self.push.call_count,1)
        with (self.root/'.lane-health-state/lint.lock').open('a') as stream:
            fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
            self.assertEqual(rh.lint_monitor(self.root),0)
        self.assertEqual(self.push.call_count,1)

    def test_cadence_status_boundaries_and_default_warn(self):
        self.config()
        for age,status in [(0,'OK'),(18.19,'OK'),(18.2,'WARN'),(26,'WARN'),(26.001,'STALLED')]:
            with self.subTest(age=age):
                self.receipt(age)
                row=cadence.evaluate(self.lane,rh)
                self.assertEqual(row['status'],status)
                self.assertAlmostEqual(row['warn_hours'],18.2)

    def test_cadence_missing_evidence_is_stalled(self):
        self.config()
        row=cadence.evaluate(self.lane,rh)
        self.assertEqual(row['status'],'STALLED')
        self.assertIsNone(row['last_delivery'])
        self.assertIn('STALLED',cadence.lint(self.lane,rh)[0])

    def test_a_refused_sweep_is_named_on_a_stalled_lane(self):
        """virtual-embryo, 11-07: a disk-floor refusal read as 57 h of STALLED, like an idle session."""
        self.config()
        runs = self.lane / 'SWEEP_RUNS.jsonl'
        rh.append(runs, dict(id='r1', status='started', ok=None))
        rh.append(runs, dict(id='r1', status='finished', ok=False,
                             errors=['sweep refused on the disk floor: less than 30 GiB free']))
        row = cadence.evaluate(self.lane, rh)
        self.assertEqual(row['status'], 'STALLED')
        self.assertIn('disk floor', row['last_sweep_refused'])
        rh.append(runs, dict(id='r2', status='finished', ok=False, errors=['lane failed']))
        self.assertNotIn('last_sweep_refused', cadence.evaluate(self.lane, rh))

    def test_cadence_window_exempt_before_open_and_at_close(self):
        for cfg in [dict(window_opens=(NOW+dt.timedelta(seconds=1)).isoformat()),
                    dict(window_closes=NOW.isoformat())]:
            self.config(**cfg)
            self.assertEqual(cadence.evaluate(self.lane,rh)['status'],'EXEMPT')
            self.assertEqual(cadence.lint(self.lane,rh),[])
        self.config(window_opens=NOW.isoformat())
        self.assertEqual(cadence.evaluate(self.lane,rh)['status'],'STALLED')

    def test_a_held_lane_is_held_not_stalled(self):
        """friends, 11-11: paused by its owner, then reported STALLED and nudged to start rounds."""
        self.config()
        (self.lane / 'HOLD').write_text('PAUSED 11-11 by the owner\n')
        row = cadence.evaluate(self.lane, rh)
        self.assertEqual((row['status'], row['held']), ('HELD', 'PAUSED 11-11 by the owner'))
        self.assertEqual(cadence.lint(self.lane, rh), [])

    def test_cadence_unconfigured_and_lint_bootstrap_grace_fixed_epoch(self):
        self.assertEqual(cadence.evaluate(self.lane,rh)['status'],'UNCONFIGURED')
        ship=cadence.stamp(cadence.SHIPPED_UTC)
        self.assertEqual(cadence.lint(self.lane,rh,(ship+dt.timedelta(hours=26)-dt.timedelta(seconds=1)).isoformat()),[])
        self.assertIn('bootstrap',cadence.lint(self.lane,rh,(ship+dt.timedelta(hours=26)).isoformat())[0])
        self.healthy()
        with patch.object(rh,'now',return_value=(ship+dt.timedelta(hours=26)).isoformat()):
            row=rh.checked_lint(self.lane)
        self.assertTrue(any(f['check']=='cadence-unconfigured' for f in row['failures']))

    def test_cadence_cli_all_disabled_and_readonly(self):
        self.config()
        self.make_lane('disabled')
        before=self.snapshot()
        rc,text=self.cli('lanes','cadence','--json')
        self.assertEqual(rc,1)
        self.assertEqual([(r['lane'],r['status']) for r in json.loads(text)],[('disabled','UNCONFIGURED'),('restricted-a','STALLED')])
        rc,text=self.cli('lanes','cadence','--lane','disabled','--json')
        self.assertEqual(rc,0)
        self.assertEqual(len(json.loads(text)),1)
        self.assertEqual(before,self.snapshot())
        self.push.assert_not_called()

    def test_cadence_jsonl_beats_fresh_mtime_and_failed_or_future_receipts(self):
        self.config(evidence_jsonl='receipts.jsonl',timestamp_field='delivered',success_field='ok')
        self.receipt(0)
        log=self.lane/'receipts.jsonl'
        log.write_text('\n'.join(json.dumps(r) for r in [
            dict(delivered=(NOW-dt.timedelta(hours=28)).isoformat(),ok=True,private=SECRET),
            dict(delivered=NOW.isoformat(),ok=False),
            dict(delivered=(NOW+dt.timedelta(hours=1)).isoformat(),ok=True)])+'\n')
        self.assertEqual(cadence.evaluate(self.lane,rh)['status'],'STALLED')
        with log.open('a') as f:f.write(json.dumps(dict(delivered=NOW.isoformat(),ok=True))+'\n')
        self.assertEqual(cadence.evaluate(self.lane,rh)['status'],'OK')

    def test_jsonl_missing_empty_or_invalid_never_falls_back_to_glob(self):
        self.config(evidence_jsonl='receipts.jsonl',timestamp_field='delivered')
        self.receipt(0)
        self.assertEqual(cadence.evaluate(self.lane,rh)['status'],'STALLED')
        for text in ['', SECRET, json.dumps(dict(delivered=SECRET)), '[]\nnull\n']:
            (self.lane/'receipts.jsonl').write_text(text)
            self.assertEqual(cadence.evaluate(self.lane,rh)['status'],'STALLED')

    def test_jsonl_alone_and_unsorted_timestamps(self):
        self.config(evidence_globs=[],evidence_jsonl='receipts.jsonl',timestamp_field='delivered')
        (self.lane/'receipts.jsonl').write_text(''.join(json.dumps(dict(delivered=(NOW-dt.timedelta(hours=h)).isoformat()))+'\n' for h in [10,2,30]))
        row=cadence.evaluate(self.lane,rh)
        self.assertEqual(row['status'],'OK')
        self.assertEqual(row['hours_since_last_delivery'],2)

    def test_evidence_root_relative_to_lane_and_absolute_paths(self):
        self.config(evidence_root='evidence',evidence_globs=['*.receipt'])
        self.receipt(5)
        self.assertEqual(cadence.evaluate(self.lane,rh)['hours_since_last_delivery'],5)
        self.config(evidence_root=str(self.lane/'evidence'),evidence_globs=['*.receipt'])
        self.assertEqual(cadence.evaluate(self.lane,rh)['status'],'OK')
        self.config(evidence_globs=[str(self.lane/'evidence'/'*.receipt')])
        self.assertEqual(cadence.evaluate(self.lane,rh)['status'],'OK')

    def test_newest_glob_mtime_counts_only_files_and_ignores_future(self):
        self.config()
        self.receipt(30,name='old.receipt')
        self.receipt(2,name='fresh.receipt')
        self.receipt(-1,name='future.receipt')
        (self.lane/'evidence/directory.receipt').mkdir()
        self.assertEqual(cadence.evaluate(self.lane,rh)['hours_since_last_delivery'],2)

    def test_malformed_cadence_alerts_and_lint_failure_without_content(self):
        self.healthy()
        (self.lane/'CADENCE.toml').write_text('broken '+SECRET)
        row=cadence.evaluate(self.lane,rh)
        self.assertTrue(row['broken'])
        self.assertEqual(row['status'],'STALLED')
        self.assertIn('broken',cadence.lint(self.lane,rh)[0])
        self.assertEqual(rh.checked_lint(self.lane)['status'],'FAIL')
        cadence.monitor(self.root,rh)
        cadence.monitor(self.root,rh)
        self.assertEqual(self.push.call_count,1)
        self.assertTrue((self.root/'alerts/lane-cadence-broken-restricted-a').exists())
        self.assert_private()

    def test_unreadable_cadence_config_is_broken(self):
        self.config()
        original=rh.config
        def read(path):
            if path.name=='CADENCE.toml':raise PermissionError(SECRET)
            return original(path)
        with patch.object(rh,'config',side_effect=read):
            row=cadence.evaluate(self.lane,rh)
            self.assertTrue(row['broken'])
            cadence.monitor(self.root,rh)
        self.assertTrue((self.root/'alerts/lane-cadence-broken-restricted-a').exists())
        self.assert_private()

    def test_malformed_fields_never_silently_skip(self):
        for values in [dict(every_hours=0),dict(every_hours=True),dict(warn_hours=30),
                       dict(owner_session=SECRET),dict(evidence_globs='receipt'),
                       dict(window_closes='bad'),dict(window_closes='2026-11-01T00:00:00'),
                       dict(window_closes='2026-11-01T00:00:00+01:00'),dict(unknown='field'),
                       dict(timestamp_field='delivered'),dict(evidence_jsonl='x')]:
            with self.subTest(values=values):
                self.config(**values)
                self.assertTrue(cadence.evaluate(self.lane,rh)['broken'])
                self.assertTrue(cadence.lint(self.lane,rh))

    def test_duplicate_toml_key_is_broken(self):
        self.config()
        with (self.lane/'CADENCE.toml').open('a') as f:f.write('every_hours = 24\n')
        self.assertTrue(cadence.evaluate(self.lane,rh)['broken'])

    def test_cadence_push_warn_stalled_changed_set_and_recovery_retry(self):
        self.config()
        self.receipt(20)
        cadence.monitor(self.root,rh)
        cadence.monitor(self.root,rh)
        self.assertEqual(self.push.call_count,1)
        self.assertTrue((self.root/'alerts/lane-warn-restricted-a').exists())
        self.receipt(28)
        cadence.monitor(self.root,rh)
        cadence.monitor(self.root,rh)
        self.assertEqual(self.push.call_count,2)
        self.assertFalse((self.root/'alerts/lane-warn-restricted-a').exists())
        self.assertTrue((self.root/'alerts/lane-stalled-restricted-a').exists())
        self.push.return_value=False
        self.receipt(1)
        cadence.monitor(self.root,rh)
        self.push.return_value=True
        cadence.monitor(self.root,rh)
        cadence.monitor(self.root,rh)
        self.assertEqual(self.push.call_count,4)
        self.assertFalse((self.root/'alerts/lane-stalled-restricted-a').exists())
        self.assertTrue((self.root/'alerts/lane-recovered-restricted-a').exists())
        self.assert_private()

    def test_cadence_failure_push_retries_without_rewriting_alert(self):
        self.config()
        self.push.return_value=False
        cadence.monitor(self.root,rh)
        active=self.root/'alerts/lane-stalled-restricted-a'
        before=active.stat().st_mtime_ns
        self.push.return_value=True
        cadence.monitor(self.root,rh)
        cadence.monitor(self.root,rh)
        self.assertEqual(self.push.call_count,2)
        self.assertEqual(before,active.stat().st_mtime_ns)

    def test_cadence_broken_recovery_and_window_closure_clear_once(self):
        (self.lane/'CADENCE.toml').write_text(SECRET)
        cadence.monitor(self.root,rh)
        self.config()
        self.receipt(1)
        cadence.monitor(self.root,rh)
        self.assertFalse((self.root/'alerts/lane-cadence-broken-restricted-a').exists())
        self.receipt(30)
        cadence.monitor(self.root,rh)
        self.config(window_closes=NOW.isoformat())
        cadence.monitor(self.root,rh)
        cadence.monitor(self.root,rh)
        self.assertEqual(self.push.call_count,4)
        self.assertFalse((self.root/'alerts/lane-stalled-restricted-a').exists())
        self.assert_private()

    def grandfather_row(self, **values):
        row=dict(id='OLD-1',created='2026-09-01T00:00:00Z',status='new',claim=SECRET)
        row.update(values)
        rh.append(self.lane/'IDEAS.jsonl',row)
        return row

    def test_grandfather_default_expires_from_lane_start_not_creation(self):
        self.grandfather_row()
        cfg=dict(enabled=False,start_date='2026-10-20',testing_max_age_days=3)
        start=cadence.stamp('2026-10-20T00:00:00Z')
        boundary=start+dt.timedelta(days=14)
        due,errors,legacy=sweep.obligations(self.lane,cfg,rh,boundary-dt.timedelta(seconds=1))
        self.assertEqual((due,errors,legacy),([],[],['OLD-1']))
        before=self.snapshot(self.lane)
        due,errors,legacy=sweep.obligations(self.lane,cfg,rh,boundary)
        self.assertEqual((due,legacy),(['OLD-1'],[]))
        self.assertIn('entire idea set is grandfathered and its exemption expired',' '.join(errors))
        self.assertIn('unread after 3 days',' '.join(errors))
        self.assertEqual(before,self.snapshot(self.lane))

    def test_grandfather_expiry_configuration_and_disabled_lane_lint(self):
        self.grandfather_row()
        path=self.lane/'SWEEP.toml'
        path.write_text('enabled = false\nstart_date = "2026-11-01"\ngrandfather_max_age_days = 1\n')
        errors,legacy=sweep.lint(self.lane,rh)
        self.assertEqual(legacy,[])
        self.assertIn('unread after',' '.join(errors))
        path.write_text('enabled = false\nstart_date = "2026-11-01"\ngrandfather_max_age_days = 30\n')
        self.assertEqual(sweep.lint(self.lane,rh),([],['OLD-1']))

    def test_grandfather_mixed_set_has_row_failure_without_entire_set_message(self):
        self.grandfather_row()
        self.grandfather_row(id='NEW-1',created=NOW.isoformat())
        cfg=dict(start_date='2026-10-01',testing_max_age_days=3)
        due,errors,legacy=sweep.obligations(self.lane,cfg,rh,NOW)
        self.assertIn('OLD-1',due)
        self.assertFalse(legacy)
        self.assertFalse(any('entire idea set' in e for e in errors))
        self.assertIn('idea OLD-1 unread',' '.join(errors))

    def test_grandfather_expired_testing_obligation_also_rearms(self):
        self.grandfather_row(status='testing',testing_started='2026-09-01T00:00:00Z')
        cfg=dict(start_date='2026-10-01',testing_max_age_days=3)
        errors=sweep.obligations(self.lane,cfg,rh,NOW)[1]
        self.assertIn('testing without a result',' '.join(errors))

    def test_invalid_grandfather_config_fails_for_disabled_workers(self):
        for value in ['true','-1','1.5','"fourteen"']:
            (self.lane/'SWEEP.toml').write_text('enabled = false\nstart_date = "2026-11-01"\ngrandfather_max_age_days = '+value+'\n')
            self.assertEqual(rh.checked_lint(self.lane)['status'],'FAIL')

    def test_alert_failure_on_one_lane_does_not_stop_another(self):
        self.make_lane('zdisabled')
        original=lane_alerts.update
        def update(root,channel,lane,*args,**kwargs):
            if lane=='restricted-a':raise OSError(SECRET)
            return original(root,channel,lane,*args,**kwargs)
        with patch.object(lane_alerts,'update',side_effect=update), contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(rh.lint_monitor(self.root),1)
        self.assertNotIn(SECRET,out.getvalue())
        self.assertTrue((self.root/'alerts/lint-failed-zdisabled').exists())

    def test_push_goes_to_the_agent_queue_and_never_to_owner(self):
        # 11-03: lane health is an agent's job, not a phone notification for Operator.
        # The real wrapper must not shell out to notify-agent at all.
        import lane_alerts
        with tempfile.TemporaryDirectory() as home:
            queue = Path(home) / 'agent-alerts.jsonl'
            with patch.dict(os.environ, {'RH_AGENT_ALERTS': str(queue)}),\
                 patch.object(subprocess, 'run', side_effect=AssertionError('must not shell out')):
                self.assertTrue(ORIGINAL_PUSH('lane=restricted-a\nfailure_count=1\nchecks=queue-depth\n'))
            rows = [json.loads(line) for line in queue.read_text().splitlines() if line.strip()]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['for'], 'agents')
        self.assertEqual(rows[0]['kind'], 'lane-health')
        self.assertIn('lane=restricted-a', rows[0]['message'])
        self.assertNotIn(SECRET, json.dumps(rows[0]))

    def test_push_failure_is_bounded_and_returns_false(self):
        import lane_alerts
        unwritable = Path('/proc/nonexistent-rh/agent-alerts.jsonl')
        with patch.dict(os.environ, {'RH_AGENT_ALERTS': str(unwritable)}):
            self.assertFalse(ORIGINAL_PUSH('lane=restricted-a\nfailure_count=1\nchecks=queue-depth\n'))

    def test_pod_measurement_changes_do_not_change_failure_fingerprint(self):
        self.healthy()
        with patch.object(pods, 'lint', return_value=['underused pod example: cpu=3% gpu=0%']):
            rh.lint_monitor(self.root)
        with patch.object(pods, 'lint', return_value=['underused pod example: cpu=4% gpu=1%']):
            rh.lint_monitor(self.root)
        self.assertEqual(self.push.call_count, 1)
        with patch.object(pods, 'lint', return_value=['underused pod different: cpu=4% gpu=1%']):
            rh.lint_monitor(self.root)
        self.assertEqual(self.push.call_count, 2)
        self.assert_private()
