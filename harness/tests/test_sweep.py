"""Offline sweep/compiler tests. Never invoke launch.sh, a notifier, or a socket."""
import contextlib
import datetime as dt
import fcntl
import hashlib
import io
import json
import re
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import rh
import sweep
import idea_policy
from policy_fixtures import prior_art as prior_fixture, config as config_fixture


class SweepTests(unittest.TestCase):
    def setUp(self):
        # Cadence has its own frozen-clock acceptance tests.
        cadence_check = patch.object(rh.cadence, 'lint', return_value=[])
        cadence_check.start()
        self.addCleanup(cadence_check.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()  # macOS: /var -> /private/var
        self.lane = self.root / 'lanes/test'
        self.lane.mkdir(parents=True)
        (self.lane / 'INTAKE.toml').write_text("keywords = ['fixture']\n")
        self.policy = 'SEALED: never open sealed.csv. BANNED WINDOW: strictly between X and Y.\n'
        (self.lane / 'RULES.md').write_text(self.policy)
        self.cfg = dict(enabled=True, start_date=(dt.date.today() - dt.timedelta(days=10)).isoformat(),
                        working_directory='.', rules_files=['RULES.md'],
                        search_targets=['fixture target'], sources=['https://example.org/feed'],
                        banned_sources=['sealed data'], allowed_tests=['small arithmetic only'],
                        allowed_writes=['work/'], run_directory='work/runs',
                        search_report='work/{date}-search.md', read_report='work/{date}-read.md',
                        kill_report='work/{date}-kill.md', launcher='/not/a/live/launcher.sh',
                        testing_max_age_days=2, stagger_seconds=0)
        self.save_cfg()
        self.worker = patch.object(sweep, 'run_worker', side_effect=AssertionError('live worker forbidden')).start()
        self.notifier = patch.object(sweep, 'notify', side_effect=AssertionError('live notification forbidden')).start()
        self.addCleanup(patch.stopall)
        self.network = patch.object(rh, 'get_url', side_effect=AssertionError('network forbidden')).start()

    def save_cfg(self):
        (self.lane / 'SWEEP.toml').write_text('\n'.join(k + ' = ' + (str(v).lower() if type(v) is bool else json.dumps(v))
                                                        for k, v in self.cfg.items()) + '\n')

    def cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = rh.main(['--root', str(self.root)] + list(args))
        return rc, out.getvalue(), err.getvalue()

    def add(self, days=4, **values):
        row = rh.new_idea('internal', '', 'fixture')
        row.update(created=(dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)).isoformat())
        row.update(values)
        rh.append(self.lane / 'IDEAS.jsonl', row)
        return row

    def loaded(self):
        return sweep.load(self.lane, rh)

    def paths(self):
        paths = {s: self.lane / (s + '.md') for s in ('search', 'read', 'kill')}
        return paths

    def evidence(self, key):
        p = self.lane / 'evidence.md'
        p.write_text('READ {}: rejected after source and rules screen\nDONE\n'.format(key))
        return p

    def healthy_existing_lint(self):
        for _ in range(3):
            self.add(days=0)
        rh.append(self.lane / 'INTAKE_RUNS.jsonl', dict(created=rh.now(), sources_read=['fixture']))

    def fake_worker(self, spec, cfg):
        """Models worker outputs, without running any subprocess."""
        stage = spec.stem.split('-', 1)[1]
        report = spec.parent / (stage + '.report.md')
        if stage == 'search':
            report.write_text('IDEA TEST-1: https://example.org new signal; metric; kill test; no rules risk\nDONE\n')
            prior_fixture(spec.parent / 'prior-art-TEST-1.json')
        elif stage == 'read':
            rows = rh.latest(rh.rows(self.lane / 'IDEAS.jsonl'))
            report.write_text(''.join('READ {}: checked method and exclusions\n'.format(k) for k in rows) + 'DONE\n')
        else:
            report.write_text('RESULT TEST-1: KILLED value=0; pass line > 1\nDONE\n')
        return 0

    def test_dry_run_is_read_only_and_carries_verbatim_rules(self):
        self.add(days=0)
        before = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        rc, out, err = self.cli('sweep', 'test', '--dry-run')
        self.assertEqual(rc, 0, err)
        self.assertIn(self.policy, out)
        self.assertIn((self.lane / 'INTAKE.toml').read_text(), out)
        self.assertIn('search -> read -> kill -> check', out)
        self.assertEqual(before, {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob('*') if p.is_file()})
        self.worker.assert_not_called()
        self.notifier.assert_not_called()
        self.network.assert_not_called()

    def test_missing_and_empty_rules_refuse_even_dry_run(self):
        for value in ('MISSING.md', 'RULES.md'):
            self.cfg['rules_files'] = [value]
            self.save_cfg()
            (self.lane / 'RULES.md').write_text('')
            rc, _, err = self.cli('sweep', 'test', '--dry-run')
            self.assertEqual(rc, 1)
            self.assertIn('required rules file missing or empty', err)
        self.worker.assert_not_called()

    def test_the_harness_text_in_a_stage_prompt_has_a_budget_and_is_not_the_ask(self):
        """planets, 11-08: about 900 of the 1,011 words launch.sh counted in its search spec were the
        sweep's own fixed instructions, so no trim of the lane's config could get under the cap. They
        are now marked and excluded from the cap; their size is held here instead, so harness text
        that keeps growing still fails, in the repo rather than at launch."""
        import importlib.util
        spec = importlib.util.spec_from_file_location('sw', Path(sweep.__file__).parent / 'tools/spec_words.py')
        sw = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(sw)
        (self.lane / 'INTAKE.toml').write_text('keywords = []\narxiv_queries = []\nbiorxiv_pages = 0\n'
                                               'x_local_file = "X_HITS.jsonl"\n')
        self.cfg.update(evidence_policy=True, github_repo_queries=['"fixture library"'],
                        github_watch_repos=['example/watched'])
        self.save_cfg()
        cfg = self.loaded()
        budget = 1200   # harness-written words per stage prompt; raise it only on purpose
        for stage in ('search', 'read', 'kill'):
            text = sweep.generate(stage, self.lane, cfg, self.paths(), '2026-11-01', ['B-1', 'B-2'],
                                  ['ideas without a result: B-1'] * 30)
            blocks = re.findall(re.escape(sweep.H.BEGIN) + r'\n(.*?)\n' + re.escape(sweep.H.END), text, re.S)
            harness_words = sum(len(b.split()) for b in blocks)
            self.assertLess(harness_words, budget, stage)
            self.assertLess(len(sw.job_specific(text).split()), 400, stage + ': the lane-controlled part is what counts')
            self.assertIn('X POLICY', text, 'marked, not removed')

    def test_github_sources_generate_read_only_commands_in_every_stage(self):
        self.cfg.update(github_repo_queries=['"fixture library"'],
                        github_code_queries=['fixture language:Python'],
                        github_watch_repos=['example/watched'],
                        github_fork_repos=['example/library'],
                        github_import_queries=['"from fixture" language:Python'])
        self.save_cfg()
        cfg = self.loaded()
        commands = [shlex.split(line.split(': ', 1)[1]) for line in sweep.github_commands(cfg)]
        gh = 'gh'
        self.assertTrue(all(argv[0] == gh for argv in commands))
        repo_search = commands[0]
        self.assertEqual(repo_search[1:3], ['search', 'repos'])
        self.assertEqual(repo_search[-2:], ['--', '"fixture library"'])
        self.assertEqual(repo_search[repo_search.index('--sort') + 1], 'updated')
        self.assertIn([gh, 'search', 'code', '--limit', '30', '--', '"from fixture" language:Python'], commands)
        self.assertIn([gh, 'repo', 'view', 'example/watched'], commands)
        endpoints = [argv[-1] for argv in commands if argv[1] == 'api']
        for suffix in ('commits?per_page=30',
                       'pulls?state=open&sort=updated&direction=desc&per_page=30',
                       'issues?state=open&sort=updated&direction=desc&per_page=30'):
            self.assertIn('repos/example/watched/' + suffix, endpoints)
        self.assertIn('repos/example/library/forks?sort=newest&per_page=100', endpoints)
        self.assertTrue(all(argv[2:4] == ['--method', 'GET'] for argv in commands if argv[1] == 'api'))
        with patch.object(sweep.subprocess, 'run', side_effect=AssertionError('no command execution')):
            rc, out, err = self.cli('sweep', 'test', '--dry-run')
        self.assertEqual(rc, 0, err)
        for stage in ('search', 'read', 'kill'):
            text = sweep.generate(stage, self.lane, cfg, self.paths(), '2026-11-01', [])
            self.assertIn('Library forks', text)
            self.assertIn('Library importers', text)
            self.assertIn('search stage only', text)
        self.worker.assert_not_called()
        self.network.assert_not_called()

    def test_github_query_is_one_shell_quoted_argument(self):
        query = '-topic:fixture "a b" $(touch should-not-exist) `false`; echo nope'
        commands = sweep.github_commands(dict(github_repo_queries=[query], github_code_queries=[query]))
        for line in commands:
            argv = shlex.split(line.split(': ', 1)[1])
            self.assertEqual(argv[-2:], ['--', query])
        self.assertFalse((self.root / 'should-not-exist').exists())

    def test_bad_discovery_config_refuses_before_workers_or_handoff(self):
        for key in sweep.GITHUB_FIELDS + ('x_queries',):
            for invalid in ('not-an-array', [1], [''], ['two\nlines'], ['a\rb'], ['a\0b']):
                with self.subTest(key=key, invalid=invalid):
                    self.cfg[key] = invalid
                    self.save_cfg()
                    rc, _, err = self.cli('sweep', 'test')
                    self.assertEqual(rc, 1, err)
                    self.assertIn(key, err)
            self.cfg.pop(key)
        for key in ('github_watch_repos', 'github_fork_repos'):
            for invalid in ('https://github.com/a/b', '../escape', 'owner/repo/commits', '-owner/repo', 'owner/..', 'repo'):
                with self.subTest(key=key, invalid=invalid):
                    self.cfg[key] = [invalid]
                    self.save_cfg()
                    self.assertIn('owner/repo', self.cli('sweep', 'test')[2])
            self.cfg.pop(key)
        self.assertFalse((self.lane / 'X_QUERIES.txt').exists())
        self.worker.assert_not_called()

    def test_x_handoff_dry_run_previews_without_writing_or_changing_file(self):
        self.cfg['x_queries'] = ['"generic topic" code', 'from:Example']
        self.save_cfg()
        handoff = self.lane / 'X_QUERIES.txt'
        for existing in (False, True):
            if existing:
                handoff.write_text('preserve existing handoff\n')
            rc, out, err = self.cli('sweep', 'test', '--dry-run')
            self.assertEqual(rc, 0, err)
            self.assertIn('Would write browser handoff: ' + str(handoff), out)
            self.assertIn('"generic topic" code\nfrom:Example', out)
            self.assertEqual(handoff.exists(), existing)
            if existing:
                self.assertEqual(handoff.read_text(), 'preserve existing handoff\n')
        self.worker.assert_not_called()
        self.network.assert_not_called()

    def test_x_handoff_written_before_workers_and_clears_removed_queries(self):
        self.cfg['x_queries'] = ['"generic topic" code', 'from:Example']
        self.save_cfg()
        handoff = self.lane / 'X_QUERIES.txt'
        def worker(spec, cfg):
            queries = [line for line in handoff.read_text().splitlines() if line and not line.startswith('#')]
            self.assertEqual(queries, cfg['x_queries'])
            return self.fake_worker(spec, cfg)
        self.worker.side_effect = worker
        with patch.object(sweep, 'guard'):
            rc, out, err = self.cli('sweep', 'test')
            self.assertEqual(rc, 0, out + err)
            self.cfg['x_queries'] = []
            self.save_cfg()
            rc, out, err = self.cli('sweep', 'test')
            self.assertEqual(rc, 0, out + err)
        self.assertNotIn('from:Example', handoff.read_text())
        self.network.assert_not_called()
        self.notifier.assert_not_called()

    def test_x_only_intake_policy_applies_to_all_stages_and_repair(self):
        # Legacy source text is preserved, but the operational override is explicit.
        self.cfg['x_queries'] = ['"generic topic"']
        self.save_cfg()
        cfg = self.loaded()
        cfg['rules'].append(('legacy.md', 'X via web search only.'))
        for stage in ('search', 'read', 'kill'):
            for failures in ((), ('repair fixture',)):
                text = sweep.generate(stage, self.lane, cfg, self.paths(), '2026-11-01', [], failures)
                for phrase in ('overrides all legacy source-spec X instructions',
                               'X results arrive ONLY through intake in IDEAS.jsonl',
                               'Workers have no other route to X', 'use any X API',
                               'web search, mirrors or proxies', 'without opening its X source URL'):
                    self.assertIn(phrase, text)

    def test_browser_capture_reaches_queue_through_existing_intake(self):
        (self.lane / 'INTAKE.toml').write_text('keywords = []\narxiv_queries = []\nbiorxiv_pages = 0\nx_local_file = "X_HITS.jsonl"\n')
        rh.append(self.lane / 'X_HITS.jsonl', dict(title='Captured generic method',
                  source_url='https://x.com/Example/status/123', summary='Public method metadata'))
        rc, out, err = self.cli('intake', 'test', '--live')
        self.assertEqual(rc, 0, out + err)
        queued = list(rh.latest(rh.rows(self.lane / 'IDEAS.jsonl')).values())
        self.assertEqual(len(queued), 1)
        self.assertEqual(queued[0]['source_type'], 'x')
        self.assertEqual(queued[0]['source_url'], 'https://x.com/Example/status/123')
        self.assertIn('x-local', rh.rows(self.lane / 'INTAKE_RUNS.jsonl')[0]['sources_read'])
        self.network.assert_not_called()
        self.worker.assert_not_called()

    def test_browser_handoff_uses_configured_intake_capture_path(self):
        self.cfg['x_queries'] = ['"generic method"']
        self.save_cfg()
        for capture in ('captures/browser.jsonl', str(self.lane / 'absolute.jsonl')):
            with self.subTest(capture=capture):
                (self.lane / 'INTAKE.toml').write_text(
                    'keywords = []\narxiv_queries = []\nbiorxiv_pages = 0\nx_local_file = '
                    + json.dumps(capture) + '\n')
                rc, out, err = self.cli('sweep', 'test', '--dry-run')
                self.assertEqual(rc, 0, err)
                path = self.lane / capture
                self.assertIn('# Capture metadata in ' + str(path), out)
                self.assertIn('# Then run rh intake test --live.', out)
                path.parent.mkdir(parents=True, exist_ok=True)
                rh.append(path, dict(title='Captured method ' + capture,
                                    source_url='https://x.com/Example/status/' + str(len(capture))))
                self.assertEqual(self.cli('intake', 'test', '--live')[0], 0)
        self.assertEqual(len(rh.latest(rh.rows(self.lane / 'IDEAS.jsonl'))), 2)
        self.network.assert_not_called()
        self.worker.assert_not_called()

    def test_browser_handoff_without_capture_configuration_requests_it(self):
        text = sweep.x_query_text(self.lane, self.loaded())
        self.assertIn('General must configure x_local_file in INTAKE.toml', text)
        self.assertNotIn('Capture metadata in ', text)

    def test_invalid_intake_capture_path_refuses_before_handoff(self):
        for capture in (17, ['capture.jsonl'], 'two\nlines', 'a\0b'):
            with self.subTest(capture=capture):
                (self.lane / 'INTAKE.toml').write_text('x_local_file = ' + json.dumps(capture) + '\n')
                rc, _, err = self.cli('sweep', 'test')
                self.assertEqual(rc, 1)
                self.assertIn('INTAKE x_local_file', err)
        self.assertFalse((self.lane / 'X_QUERIES.txt').exists())
        self.worker.assert_not_called()



    def test_missing_rules_lint_is_refusal(self):
        self.cfg['rules_files'] = ['absent.md']
        self.save_cfg()
        code, out, err = self.cli('lint', 'test')
        self.assertEqual(code, 1)
        self.assertIn('lint input unreadable or invalid', out)
        self.assertEqual(err, '')

    def test_disabled_lane_does_not_need_rules_or_launch(self):
        (self.lane / 'SWEEP.toml').write_text('enabled = false\nstart_date = \"2026-11-01\"\n')
        for extra in ((), ('--dry-run',)):
            rc, out, err = self.cli('sweep', 'test', *extra)
            self.assertEqual(rc, 0, err)
            self.assertIn('SKIP', out)
        self.assertFalse((self.root / '.sweep.lock').exists())
        self.assertEqual(sweep.lint(self.lane, rh), ([], []))
        self.worker.assert_not_called()

    def test_all_bad_preflight_does_not_block_valid_lane(self):
        other = self.root / 'lanes/broken'
        other.mkdir()
        with patch.object(sweep, 'guard'), patch.object(sweep, 'run_lane', return_value=0) as run:
            rc, _, err = self.cli('sweep', '--all')
        self.assertEqual(run.call_count, 1)
        self.assertEqual(rc, 1)
        self.assertIn('REFUSED broken', err)
        self.worker.assert_not_called()

    def test_execution_host_is_a_validated_lane_setting(self):
        """A host becomes an ssh argv, so a bad one is a config error at load time, not a string
        handed to ssh. Same shape launch.sh validates, so the two cannot disagree about what an
        ssh alias is."""
        self.cfg['host'] = 'm5'
        self.save_cfg()
        self.assertEqual(sweep.execution_host(self.loaded()), 'm5')
        for bad in ('-oProxyCommand=x', 'host name', 'a' * 64, 'two;cmds', ''.join(['x', '\n'])):
            self.cfg['host'] = bad
            self.save_cfg()
            with self.assertRaises(ValueError) as caught:
                self.loaded()
            self.assertIn('SWEEP host', str(caught.exception))

    def test_a_lane_without_a_host_runs_here_as_before(self):
        self.assertEqual(self.loaded()['host'], '')
        self.assertEqual(sweep.execution_host(self.loaded()), '')

    def test_invalid_sweep_cli_and_traversal(self):
        for args in [(), ('test', '--all'), ('../test',), ('absent',)]:
            self.assertNotEqual(self.cli('sweep', *args)[0], 0)

    def test_unread_new_and_closed_rows_fail_after_three_days(self):
        for state in ('new', 'closed'):
            self.add(status=state, closed_reason='screened out')
        _, errors, _ = sweep.obligations(self.lane, self.loaded(), rh)
        self.assertEqual(sum('unread after 3 days' in e for e in errors), 2)
        self.assertIn('unread after 3 days', self.cli('lint', 'test')[1])

    def test_grandfathering_lists_old_rows_without_failure(self):
        self.cfg['start_date'] = '2026-11-01'
        self.save_cfg()
        old = self.add(created='2026-10-31T12:00:00+00:00', status='testing', board='none', route='organiser')
        due, errors, legacy = sweep.obligations(self.lane, self.loaded(), rh, clock=dt.datetime(2026, 11, 2, tzinfo=dt.timezone.utc))
        self.assertEqual((due, errors, legacy), ([], [], [old['id']]))
        out = self.cli('lint', 'test')[1]
        self.assertIn('GRANDFATHERED test: ' + old['id'], out)
        self.assertNotIn('unread after', out)

    def test_legacy_ts_schema_is_grandfathered(self):
        self.cfg['start_date'] = '2026-11-01'
        self.save_cfg()
        row = dict(id='legacy-ts', ts='2026-10-31T12:00:00+00:00', status='lead')
        rh.append(self.lane / 'IDEAS.jsonl', row)
        self.assertEqual(sweep.obligations(self.lane, self.loaded(), rh, clock=dt.datetime(2026, 11, 2, tzinfo=dt.timezone.utc)), ([], [], ['legacy-ts']))

    def test_exact_three_day_boundary_and_date_only(self):
        clock = dt.datetime(2026, 11, 10, tzinfo=dt.timezone.utc)
        self.add(created='2026-11-07')
        cfg = self.loaded()
        cfg['start_date'] = '2026-11-01'
        self.assertFalse(sweep.obligations(self.lane, cfg, rh, clock)[1])
        self.assertIn('unread after', sweep.obligations(self.lane, cfg, rh, clock + dt.timedelta(seconds=1))[1][0])

    def test_explicit_read_mark_preserves_history_and_needs_evidence(self):
        row = self.add()
        report = self.evidence(row['id'])
        rc, _, err = self.cli('ideas', 'read', 'test', row['id'], '--report', str(report))
        self.assertEqual(rc, 0, err)
        history = rh.rows(self.lane / 'IDEAS.jsonl')
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0], row)
        self.assertEqual(history[1]['event'], 'read')
        self.assertFalse(sweep.obligations(self.lane, self.loaded(), rh)[1])
        report.write_text('changed\nDONE\n')
        self.assertIn('unread after', sweep.obligations(self.lane, self.loaded(), rh)[1][0])

    def test_seen_file_or_promotion_does_not_count_as_read(self):
        row = self.add(status='testing', revised=rh.now(), board='B', test='t', bar='b')
        (self.lane / 'SEEN_IDEAS.txt').write_text(row['id'])
        self.assertIn('unread after', sweep.obligations(self.lane, self.loaded(), rh)[1][0])

    def test_read_report_requires_id_judgment_and_done(self):
        row = self.add()
        p = self.lane / 'bad.md'
        for value in ['DONE\n', 'READ {}:\nDONE\n'.format(row['id']), 'READ {}: judged\nBLOCKED\n'.format(row['id'])]:
            p.write_text(value)
            self.assertNotEqual(self.cli('ideas', 'read', 'test', row['id'], '--report', str(p))[0], 0)

    def test_testing_clock_does_not_restart_on_read(self):
        row = self.add(status='testing', board='B', test='t', bar='b', revised=(dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=3)).isoformat())
        self.cli('ideas', 'read', 'test', row['id'], '--report', str(self.evidence(row['id'])))
        errors = sweep.obligations(self.lane, self.loaded(), rh)[1]
        self.assertIn('testing without a result after 2 days', ' '.join(errors))
        result = self.lane / 'result.md'
        result.write_text('Measured 0; bar > 1; killed\n')
        # Freeze the pre-existing testing row before attaching a new run.
        current = dict(rh.latest(rh.rows(self.lane / 'IDEAS.jsonl'))[row['id']])
        idea_policy.freeze(current, sealed=True)
        rh.append(self.lane / 'IDEAS.jsonl', dict(current, event='freeze', revised=rh.now()))
        self.assertEqual(self.cli('ideas', 'result', 'test', row['id'], '--result-path', str(result),
                                  '--config-path', str(config_fixture(self.lane / 'config.json')))[0], 0)
        self.assertFalse(sweep.obligations(self.lane, self.loaded(), rh)[1])

    def test_new_promotion_records_its_own_start(self):
        row = self.add()
        survey = self.lane / 'PRIOR_ART.md'
        prior_fixture(survey)
        rc, _, err = self.cli('ideas', 'promote', 'test', row['id'], '--board', 'none', '--route', 'ask organiser',
                              '--prior-art', str(survey), '--decided-by', 'claude-opus-5-5')
        self.assertEqual(rc, 0, err)
        current = rh.latest(rh.rows(self.lane / 'IDEAS.jsonl'))[row['id']]
        self.assertIn('testing_started', current)
        self.assertNotIn('testing without', ' '.join(sweep.obligations(self.lane, self.loaded(), rh)[1]))

    def test_revision_cannot_change_original_created_clock(self):
        row = self.add()
        rh.append(self.lane / 'IDEAS.jsonl', dict(row, created=rh.now(), event='revision'))
        self.assertIn('unread after', ' '.join(sweep.obligations(self.lane, self.loaded(), rh)[1]))

    def test_compiler_matches_every_idea_and_read(self):
        paths = self.paths()
        paths['search'].write_text('IDEA B-1: https://example.org signal; metric; kill; risk\nDONE\n')
        paths['read'].write_text('DONE\n')
        paths['kill'].write_text('RESULT NONE\nDONE\n')
        errors = sweep.check(paths, ['B-2'])
        self.assertIn('ideas without a result: B-1', errors)
        self.assertIn('queue ids without a read judgment: B-2', errors)
        paths['read'].write_text('READ B-2: judged rejected\nDONE\n')
        paths['kill'].write_text('RESULT B-1: SURVIVED value=2; pass line > 1\nDONE\n')
        self.assertEqual(sweep.check(paths, ['B-2']), [])

    def test_compiler_rejects_blocked_unfinished_and_malformed_reports(self):
        p = self.paths()
        p['search'].write_text('IDEA no-id: ignored\nDONE\n')
        p['read'].write_text('unfinished')
        p['kill'].write_text('RESULT NONE\nBLOCKED\n')
        errors = ' '.join(sweep.check(p, []))
        for value in ('malformed', 'unfinished', 'BLOCKED'):
            self.assertIn(value, errors)

    def test_per_idea_blocks_are_outcomes_not_a_blocked_stage(self):
        """planets, 11-08: ideas waiting on a future data release are BLOCKED per idea, and failing the
        whole sweep for them kept the lane STALLED every day."""
        p = self.paths()
        p['search'].write_text('IDEA B-1: https://example.org signal; metric; kill; risk\n'
                               'IDEA B-2: https://example.org signal; metric; kill; risk\nDONE\n')
        p['read'].write_text('DONE\n')
        p['kill'].write_text('RESULT B-1: KILLED value=0.1; pass line > 1\n'
                             'RESULT B-2: BLOCKED need the next public data release\nBLOCKED\n')
        self.assertEqual(sweep.check(p, []), [])
        p['kill'].write_text('RESULT B-1: KILLED value=0.1; pass line > 1\nBLOCKED\n')
        self.assertIn('kill report BLOCKED', ' '.join(sweep.check(p, [])))

    def test_settled_rows_are_named_so_the_kill_stage_skips_them(self):
        result = self.lane / 'result.md'
        result.write_text('measured\n')
        queue = {'A': dict(status='closed'), 'B': dict(status='testing', result_path=str(result)),
                 'C': dict(status='testing'), 'D': dict(status='new'), 'E': dict(status='shipped')}
        self.assertEqual(sweep.settled(queue), ['A', 'B', 'E'])

    def test_empty_day_is_valid(self):
        p = self.paths()
        p['search'].write_text('Searched fixture repo and paper feed; NOTHING NEW\nDONE\n')
        p['read'].write_text('No unread rows\nDONE\n')
        p['kill'].write_text('RESULT NONE\nDONE\n')
        self.assertEqual(sweep.check(p, []), [])

    def test_board_and_uuid_ids_share_search_read_kill_contract(self):
        for key in ('B-1', '00acbfca05cb4c858783504af83fc5d2',
                    '00acbfca-05cb-4c85-8783-504af83fc5d2'):
            with self.subTest(key=key):
                p = self.paths()
                p['search'].write_text('IDEA {}: https://example.org method; metric; kill; risk\nDONE\n'.format(key))
                p['read'].write_text('READ {}: judged source and exclusions\nDONE\n'.format(key))
                p['kill'].write_text('RESULT {}: KILLED value=0; pass > 1\nDONE\n'.format(key))
                self.assertEqual(sweep.check(p, [key], known_ids=[key]), [])
                self.assertTrue(sweep.read_evidence(p['read'], key))
                self.assertEqual(sweep.carry_over(self.lane, p, rh, rh.now()), [])
                p['kill'].write_text('RESULT {}: BLOCKED needs fixture\nDONE\n'.format(key))
                self.assertEqual(sweep.carry_over(self.lane, p, rh, rh.now()), [key])

    def test_queue_kill_results_are_valid_but_unknown_ids_still_fail(self):
        key = self.add(days=0)['id']
        p = self.paths()
        p['search'].write_text('Searched actual sources; NOTHING NEW\nDONE\n')
        p['read'].write_text('READ {}: judged metadata and exclusions\nDONE\n'.format(key))
        p['kill'].write_text('RESULT {}: BLOCKED needs public fixture\nDONE\n'.format(key))
        self.assertEqual(sweep.check(p, [key], known_ids=[key]), [])
        errors = sweep.check(p, [], known_ids=[])
        self.assertIn('unexpected or duplicate RESULT lines', errors)
        self.assertTrue(any('unknown queue ids' in e for e in errors))
        # Existing queue results cannot stand in for a newly proposed search idea.
        p['search'].write_text('IDEA B-1: https://example.org new method\nDONE\n')
        self.assertIn('ideas without a result: B-1', sweep.check(p, [], known_ids=[key]))

    def test_malformed_ids_fail_in_all_report_parsers(self):
        for key in ('not-an-id', 'a' * 31, 'g' * 32, 'B-1suffix'):
            with self.subTest(key=key):
                p = self.paths()
                p['search'].write_text('IDEA {}: https://example.org method\nDONE\n'.format(key))
                p['read'].write_text('READ {}: judged metadata\nDONE\n'.format(key))
                p['kill'].write_text('RESULT {}: KILLED value=0; pass > 1\nDONE\n'.format(key))
                errors = sweep.check(p, [])
                self.assertIn('malformed or duplicate IDEA lines', errors)
                self.assertIn('malformed READ lines', errors)
                self.assertIn('malformed RESULT lines', errors)
                with self.assertRaisesRegex(ValueError, 'invalid idea id'):
                    sweep.read_evidence(p['read'], key)

    def test_mid_run_intake_is_refreshed_and_late_unread_rows_can_wait(self):
        for arrival_stage, judged in (('search', True), ('read', True),
                                      ('read', False), ('kill', False)):
            with self.subTest(arrival_stage=arrival_stage, judged=judged):
                arrived, calls = [], []
                def worker(spec, cfg):
                    stage = spec.stem.split('-', 1)[1]
                    calls.append(stage)
                    if stage == 'read' and arrival_stage == 'search':
                        required = next(line for line in spec.read_text().splitlines()
                                        if line.startswith('Required queue ids'))
                        self.assertIn(arrived[0]['id'], required)
                    if stage == arrival_stage and judged and stage == 'read':
                        arrived.append(self.add(days=0))
                    rc = self.fake_worker(spec, cfg)
                    if stage == arrival_stage and not arrived:
                        arrived.append(self.add(days=0))
                    return rc
                self.worker.side_effect = worker
                with patch.object(sweep, 'guard'):
                    rc, out, err = self.cli('sweep', 'test')
                self.assertEqual(rc, 0, out + err)
                self.assertEqual(calls, ['search', 'read', 'kill'])
                current = rh.latest(rh.rows(self.lane / 'IDEAS.jsonl'))[arrived[0]['id']]
                self.assertEqual(sweep.valid_read(current), judged)
                self.notifier.assert_not_called()

    def test_uuid_search_receipts_are_recorded_and_checked_by_lint(self):
        key = '00acbfca05cb4c858783504af83fc5d2'
        def worker(spec, cfg):
            rc = self.fake_worker(spec, cfg)
            stage = spec.stem.split('-', 1)[1]
            report = spec.parent / (stage + '.report.md')
            report.write_text(report.read_text().replace('TEST-1', key))
            if stage == 'search':
                prior_fixture(spec.parent / ('prior-art-' + key + '.json'))
            return rc
        self.worker.side_effect = worker
        with patch.object(sweep, 'guard'):
            rc, out, err = self.cli('sweep', 'test')
        self.assertEqual(rc, 0, out + err)
        run = rh.rows(self.lane / 'SWEEP_RUNS.jsonl')[-1]
        self.assertEqual(set(run['prior_art_receipts']), {key})
        self.assertNotIn('no successful sweep report in 26 hours', sweep.lint(self.lane, rh)[0])
        # Removing the UUID receipt must invalidate success just as for BOARD-n.
        run['prior_art_receipts'] = {}
        rh.append(self.lane / 'SWEEP_RUNS.jsonl', run)
        # The sweep linter scans successful records rather than reducing by id.
        (self.lane / 'SWEEP_RUNS.jsonl').write_text(json.dumps(run) + '\n')
        self.assertIn('no successful sweep report in 26 hours', sweep.lint(self.lane, rh)[0])

    def test_ve_board_and_line_bounds_are_lane_owned(self):
        p = self.paths()
        p['search'].write_text('T1 NOTHING NEW\nDONE\n')
        p['read'].write_text('DONE\n')
        p['kill'].write_text('RESULT NONE\nDONE\n')
        self.assertIn('board unaccounted for: EMB', sweep.check(p, [], dict(boards=['T1', 'EMB'])))
        self.assertIn('search report exceeds lane line limit', sweep.check(p, [], dict(search_max_lines=1)))

    def test_repair_once_then_success_and_explicit_read_revision(self):
        row = self.add()
        seen = []
        def worker(spec, cfg):
            seen.append(spec.stem)
            if spec.stem == '0-search':
                return 1
            return self.fake_worker(spec, cfg)
        self.worker.side_effect = worker
        with patch.object(sweep, 'guard'):
            rc, out, err = self.cli('sweep', 'test')
        self.assertEqual(rc, 0, out + err)
        self.assertEqual(seen, ['0-search', '0-read', '0-kill', '1-search', '1-read', '1-kill'])
        self.notifier.assert_not_called()
        run = rh.rows(self.lane / 'SWEEP_RUNS.jsonl')[-1]
        self.assertTrue(run['ok'])
        read_row = rh.latest(rh.rows(self.lane / 'IDEAS.jsonl'))[row['id']]
        self.assertTrue(sweep.valid_read(read_row))
        self.assertFalse(sweep.lint(self.lane, rh)[0])
        # A new date-based report cannot corrupt immutable row evidence.
        sweep.reports(self.loaded(), dt.date.today().isoformat())['read'].write_text('new report\nDONE\n')
        self.assertTrue(sweep.valid_read(read_row))

    def test_exhausted_repair_notifies_exactly_once(self):
        self.worker.side_effect = lambda *_: 0  # launcher lies: no artifacts
        self.notifier.side_effect = None
        with patch.object(sweep, 'guard'):
            rc, _, _ = self.cli('sweep', 'test')
        self.assertEqual(rc, 1)
        self.assertEqual(self.worker.call_count, 6)
        self.notifier.assert_called_once()
        self.assertFalse(rh.rows(self.lane / 'SWEEP_RUNS.jsonl')[-1]['ok'])

    def test_stale_canonical_reports_cannot_pass_failed_new_run(self):
        for p in sweep.reports(self.loaded(), dt.date.today().isoformat()).values():
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text('NOTHING NEW\nRESULT NONE\nDONE\n')
        self.worker.side_effect = lambda *_: 0
        self.notifier.side_effect = None
        with patch.object(sweep, 'guard'):
            self.assertEqual(self.cli('sweep', 'test')[0], 1)

    def test_stale_report_fails_after_grace_and_bootstrap_is_clean(self):
        self.assertIn('no successful sweep report in 26 hours', sweep.lint(self.lane, rh)[0])
        self.cfg['start_date'] = rh.now()
        self.save_cfg()
        self.assertEqual(sweep.lint(self.lane, rh)[0], [])

    def test_tampered_and_expired_success_reports_fail_lint(self):
        self.worker.side_effect = self.fake_worker
        with patch.object(sweep, 'guard'):
            self.assertEqual(self.cli('sweep', 'test')[0], 0)
        runs = rh.rows(self.lane / 'SWEEP_RUNS.jsonl')
        Path(runs[-1]['reports']['search']).write_text('tampered')
        self.assertIn('no successful sweep report', ' '.join(sweep.lint(self.lane, rh)[0]))
        runs[-1]['finished'] = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=27)).isoformat()
        rh.append(self.lane / 'SWEEP_RUNS.jsonl', runs[-1])
        self.assertIn('no successful sweep report', ' '.join(sweep.lint(self.lane, rh)[0]))

    def test_prior_art_receipt_tampering_invalidates_success(self):
        self.worker.side_effect = self.fake_worker
        with patch.object(sweep, 'guard'):
            self.assertEqual(self.cli('sweep', 'test')[0], 0)
        run = rh.rows(self.lane / 'SWEEP_RUNS.jsonl')[-1]
        receipt = run['prior_art_receipts']['TEST-1']
        path = Path(receipt['path'])
        data = json.loads(path.read_text())
        data['baseline'] = 'changed after the sweep'
        path.write_text(json.dumps(data))
        self.assertIn('no successful sweep report', ' '.join(sweep.lint(self.lane, rh)[0]))

    def test_independent_all_skips_disabled_and_staggers(self):
        other = self.root / 'lanes/zz'
        other.mkdir()
        (other / 'SWEEP.toml').write_text((self.lane / 'SWEEP.toml').read_text())
        (other / 'INTAKE.toml').write_text('keywords = []\n')
        (other / 'RULES.md').write_text(self.policy)
        disabled = self.root / 'lanes/disabled'
        disabled.mkdir()
        (disabled / 'SWEEP.toml').write_text('enabled = false\n')
        visits = []
        with patch.object(sweep, 'run_lane', side_effect=lambda lane, *_: visits.append(lane.name) or 0), patch.object(sweep, 'guard'), patch.object(sweep.time, 'sleep') as sleep:
            self.assertEqual(self.cli('sweep', '--all')[0], 0)
        self.assertCountEqual(visits, ['test', 'zz'])
        sleep.assert_called_once_with(0)

    def test_lane_lock_prevents_overlap_with_individual_sweep(self):
        with (self.lane / '.sweep-run.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            rc, _, err = self.cli('sweep', 'test')
        self.assertEqual(rc, 1)
        self.assertIn('another sweep is running', err)
        self.worker.assert_not_called()

    def test_unsettled_ideas_are_requeued_once(self):
        scratch = {k: self.root / (k + '.md') for k in ('search', 'kill', 'read')}
        scratch['search'].write_text('IDEA T1-1: try method A on board T1\nIDEA T1-2: try method B\nDONE\n')
        scratch['kill'].write_text('RESULT T1-1: KILLED 0.3 < 0.5\nRESULT T1-2: BLOCKED needs GPU\nDONE\n')
        scratch['read'].write_text('DONE\n')
        self.assertEqual(sweep.carry_over(self.lane, scratch, rh, rh.now()), ['T1-2'])
        self.assertEqual(sweep.carry_over(self.lane, scratch, rh, rh.now()), [])
        rows = rh.rows(self.lane / 'IDEAS.jsonl')
        self.assertEqual([r['sweep_idea_id'] for r in rows if r.get('sweep_idea_id')], ['T1-2'])

    def test_high_load_and_low_disk_refuse(self):
        cfg = self.loaded()
        cfg['load_wait_minutes'] = 0
        with patch.object(sweep, 'disk_guard'), patch.object(sweep, 'cpu_busy', return_value=None), patch.object(sweep, 'free_memory_gib', return_value=100),\
                patch.object(sweep.os, 'getloadavg', return_value=(0, 99, 0)), self.assertRaisesRegex(ValueError, 'load'):
            sweep.guard(cfg)
        # a 1-min spike alone no longer refuses; a high 5-min average waits, then proceeds once it drops
        cfg['load_wait_minutes'] = 30
        with patch.object(sweep, 'cpu_busy', return_value=None), patch.object(sweep, 'free_memory_gib', return_value=100),\
                patch.object(sweep.os, 'getloadavg', side_effect=[(99, 99, 0), (99, 1, 0)]),\
                patch.object(sweep.time, 'sleep') as sleep,\
                patch.object(sweep.shutil, 'disk_usage', return_value=type('Disk', (), {'free': 100 * 1024**3})()):
            sweep.guard(cfg)
        sleep.assert_called_once_with(30)
        with patch.object(sweep.os, 'getloadavg', return_value=(0, 0, 0)), patch.object(sweep.shutil, 'disk_usage', return_value=type('Disk', (), {'free': 0})()), self.assertRaisesRegex(ValueError, 'free'):
            sweep.guard(cfg)

    def test_run_directory_cannot_escape_working_directory(self):
        self.cfg['run_directory'] = '../escape'
        self.save_cfg()
        with self.assertRaisesRegex(ValueError, 'run_directory'):
            self.loaded()

    def test_config_resource_limits_reject_unsafe_memory(self):
        self.cfg['memory_gib'] = 12
        self.save_cfg()
        self.assertNotEqual(self.cli('sweep', 'test', '--dry-run')[0], 0)

    def test_worker_launcher_adapter_env_and_cleanup_without_launch(self):
        cfg = self.loaded()
        cfg['launcher_path'] = self.lane / 'launcher.sh'
        cfg['launcher_path'].write_text('# fixture only; never executed\n')
        spec = self.lane / 'work/runs/0-search.md'
        spec.parent.mkdir(parents=True)
        spec.write_text('fixture')
        process = MagicMock(pid=123456, returncode=0)
        process.poll.return_value = 0
        with patch.object(sweep, 'guard'), patch.object(sweep.subprocess, 'Popen', return_value=process) as popen, patch.object(sweep.os, 'killpg') as kill:
            # Call the actual function underneath the setUp safety patch.
            with patch.object(sweep, 'run_worker', self.original_run_worker):
                self.assertEqual(sweep.run_worker(spec, cfg), 0)
        args, kw = popen.call_args
        self.assertEqual(args[0][0], str(cfg['launcher_path']))  # no stacked nice (11-02)
        self.assertEqual((cfg['launcher_path'].parent / (args[0][1] + '.md')).resolve(), spec)
        self.assertEqual(kw['env']['OMP_NUM_THREADS'], '1')
        self.assertNotIn('FORCE_LAUNCH', kw['env'])
        self.assertTrue(kw['start_new_session'])
        self.assertEqual(kill.call_count, 2)

    original_run_worker = staticmethod(sweep.run_worker)

    def test_worker_memory_limit_kills_process_group(self):
        cfg = self.loaded()
        cfg['launcher_path'] = self.lane / 'launcher.sh'
        cfg['launcher_path'].touch()
        spec = self.lane / 'spec.md'
        spec.write_text('fixture')
        process = MagicMock(pid=123456)
        process.poll.side_effect = [None, 0]
        with patch.object(sweep, 'guard'), patch.object(sweep.subprocess, 'Popen', return_value=process), patch.object(sweep.os, 'killpg') as kill, patch.object(sweep, 'process_rss', return_value=7 * 1024**3), self.assertRaisesRegex(ValueError, 'memory limit'):
            self.original_run_worker(spec, cfg)
        self.assertEqual(kill.call_count, 2)

    def test_rss_sums_entire_process_group(self):
        with patch.object(sweep.subprocess, 'check_output', return_value='10 100\n10 200\n20 400\n'):
            self.assertEqual(sweep.process_rss(10), 300 * 1024)



    def test_disabled_worker_lane_still_enforces_row_deadlines(self):
        self.cfg['enabled'] = False
        self.save_cfg()
        self.add()
        errors, _ = sweep.lint(self.lane, rh)
        self.assertIn('unread after 3 days', ' '.join(errors))
        self.assertNotIn('sweep report', ' '.join(errors))

    def test_compiler_rejects_unknown_read_ids_and_duplicate_results(self):
        p = self.paths()
        p['search'].write_text('IDEA B-1: https://example.org signal; metric; kill; risk\nDONE\n')
        p['read'].write_text('READ INVENTED-1: never in queue\nDONE\n')
        p['kill'].write_text('RESULT B-1: KILLED value=0; bar > 1\nRESULT B-1: SURVIVED value=2; bar > 1\nDONE\n')
        errors = ' '.join(sweep.check(p, [], known_ids=[]))
        self.assertIn('unknown queue ids', errors)
        self.assertIn('duplicate RESULT', errors)

    def test_result_without_detail_cannot_consume_done(self):
        p = self.paths()
        p['search'].write_text('IDEA B-1: https://example.org method\nDONE\n')
        p['read'].write_text('DONE\n')
        p['kill'].write_text('RESULT B-1: KILLED\nDONE\n')
        self.assertIn('result missing', ' '.join(sweep.check(p, [])))

    def test_worker_timeout_and_interrupt_clean_process_group(self):
        cfg = self.loaded()
        cfg['launcher_path'] = self.lane / 'launcher.sh'
        cfg['launcher_path'].touch()
        spec = self.lane / 'spec.md'
        spec.write_text('fixture')
        for interrupted in (False, True):
            process = MagicMock(pid=123456)
            process.poll.side_effect = [None, 0]
            with patch.object(sweep, 'guard'), patch.object(sweep.subprocess, 'Popen', return_value=process), patch.object(sweep.os, 'killpg') as kill, patch.object(sweep.time, 'monotonic', side_effect=[0, 999999]), patch.object(sweep, 'process_rss', side_effect=KeyboardInterrupt() if interrupted else None):
                # Timeout happens before the memory read; separately exercise interruption.
                if interrupted:
                    with patch.object(sweep.time, 'monotonic', return_value=0), self.assertRaises(KeyboardInterrupt):
                        self.original_run_worker(spec, cfg)
                else:
                    with self.assertRaisesRegex(ValueError, 'timeout'):
                        self.original_run_worker(spec, cfg)
                self.assertEqual(kill.call_count, 2)

    def test_signal_handler_is_restored_after_live_refusal(self):
        import signal
        before = signal.getsignal(signal.SIGTERM)
        with patch.object(sweep, 'guard', side_effect=ValueError('high load')):
            self.assertNotEqual(self.cli('sweep', 'test')[0], 0)
        self.assertIs(signal.getsignal(signal.SIGTERM), before)

    def test_expired_success_report_fails_without_tampering(self):
        self.worker.side_effect = self.fake_worker
        with patch.object(sweep, 'guard'):
            self.assertEqual(self.cli('sweep', 'test')[0], 0)
        run = rh.rows(self.lane / 'SWEEP_RUNS.jsonl')[-1]
        run['finished'] = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=27)).isoformat()
        # Rewrite our own fixture, not a real audit, to isolate the freshness check.
        (self.lane / 'SWEEP_RUNS.jsonl').write_text(json.dumps(run) + '\n')
        self.assertIn('no successful sweep report', ' '.join(sweep.lint(self.lane, rh)[0]))

class IntakeRegressionTests(unittest.TestCase):
    def test_308_redirect_on_python39_without_network(self):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b'fixture'
        with patch.object(rh.urllib.request, 'build_opener') as build:
            build.return_value.open.return_value = response
            self.assertEqual(rh.get_url('https://example.org/old'), b'fixture')
            handler = build.call_args[0][0]
        req = urllib.request.Request('https://example.org/old')
        req.timeout = 30
        handler.parent = MagicMock()
        handler.parent.open.return_value = b'new response'
        self.assertEqual(handler.http_error_308(req, io.BytesIO(b''), 308, 'redirect', {'location': '/new'}), b'new response')
        redirected = handler.parent.open.call_args[0][0]
        self.assertEqual(redirected.full_url, 'https://example.org/new')

    def test_429_bounded_retry_and_exhaustion(self):
        for succeeds in (True, False):
            errors = [urllib.error.HTTPError('https://example.org', 429, 'rate limit', {'Retry-After': '3'}, io.BytesIO()) for _ in range(3)]
            response = MagicMock()
            response.__enter__.return_value.read.return_value = b'ok'
            with patch.object(rh.urllib.request, 'build_opener') as build, patch.object(rh.time, 'sleep') as sleep:
                build.return_value.open.side_effect = [errors[0], errors[1], response if succeeds else errors[2]]
                if succeeds:
                    self.assertEqual(rh.get_url('https://example.org'), b'ok')
                else:
                    with self.assertRaises(urllib.error.HTTPError):
                        rh.get_url('https://example.org')
                self.assertEqual(build.return_value.open.call_count, 3)
                self.assertEqual(sleep.call_count, 2)

    def test_long_retry_after_remains_a_failure_without_early_retry(self):
        error = urllib.error.HTTPError('https://example.org', 429, 'rate limit', {'Retry-After': '3600'}, None)
        with patch.object(rh.urllib.request, 'build_opener') as build, patch.object(rh.time, 'sleep') as sleep:
            build.return_value.open.side_effect = error
            with self.assertRaises(urllib.error.HTTPError):
                rh.get_url('https://example.org')
            sleep.assert_not_called()
            self.assertEqual(build.return_value.open.call_count, 1)

    def test_arxiv_requests_are_spaced(self):
        atom = b'<feed xmlns="http://www.w3.org/2005/Atom"/>'
        with patch.object(rh, 'get_url', return_value=atom), patch.object(rh.time, 'sleep') as sleep:
            results = list(rh.fetch_sources(dict(arxiv_queries=['all:a', 'all:b', 'all:c'])))
        self.assertEqual(len(results), 3)
        self.assertEqual(sleep.call_count, 2)


if __name__ == '__main__':
    unittest.main()
