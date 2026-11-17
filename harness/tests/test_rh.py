import contextlib
import datetime as dt
import importlib.util
import io
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import rh
import pods
import intake_all
from policy_fixtures import prior_art as prior_fixture, config as config_fixture

ORIGINAL_POD_PROBE = pods.probe


class HarnessTests(unittest.TestCase):

    def test_taste_calls_refuse_sol_and_unknown(self):
        idea = self.add()
        promote = ['ideas', 'promote', 'test', idea, '--board', 'b', '--test', 't', '--bar', 'x']
        with patch.dict('os.environ', {'RH_DECIDED_BY': ''}), patch.object(rh, 'session_model', return_value=None):
            code, _, err = self.cli(*promote)
            self.assertEqual(code, 2)
            self.assertIn('who decided', err)
        code, _, err = self.cli(*(promote + ['--decided-by', 'gpt-6.1-sol']))
        self.assertEqual(code, 2)
        self.assertIn('not gpt-6.1-sol', err)
        code, _, err = self.cli(*(promote + ['--decided-by', 'claude-fable-5-1']))
        self.assertEqual(code, 0, err)
        self.assertEqual(rh.latest(self.history())[idea]['decided_by'], 'claude-fable-5-1')

    def test_promote_needs_prior_art(self):
        idea = self.add()
        code, _, err = self.cli('ideas', 'promote', 'test', idea, '--board', 'b', '--test', 't', '--bar', 'x', prior_art=False)
        self.assertEqual(code, 2)
        self.assertIn('prior-art', err)

    def test_depth_per_friend_tag(self):
        (self.lane / 'INTAKE.toml').write_text('keywords = []\ndepth_tags = ["friend:alpha", "friend:beta"]\ndepth_per_tag = 2\n')
        self.healthy()
        for _ in range(2):
            self.add(claim='alpha target', data_tag='friend:alpha')
        self.add(claim='beta target', data_tag='friend:beta')
        code, out = self.run_lint()
        self.assertEqual(code, 1)
        self.assertIn('friend:beta = 1 < 2', out)
        self.assertNotIn('friend:alpha', out)
        (self.lane / 'INTAKE.toml').write_text('keywords = []\ndepth_tags = ["friend:alpha"]\ndepth_per_tag = 1\ndepth_tag_status = ["testing"]\n')
        code, out = self.run_lint()
        self.assertIn('friend:alpha = 0 < 1 targets in testing', out)

    def test_mechanical_close_needs_result_not_taste(self):
        idea = self.add()
        result = self.root / 'fail.md'
        result.write_text('bar failed')
        self.assertEqual(self.cli('ideas', 'promote', 'test', idea, '--board', 'b', '--test', 't', '--bar', 'x')[0], 0)
        with patch.dict('os.environ', {'RH_DECIDED_BY': 'gpt-6.1-sol'}):
            self.assertEqual(self.cli('ideas', 'close', 'test', idea, '--closed-reason', 'not novel')[0], 2)
            self.assertEqual(self.cli('ideas', 'close', 'test', idea, '--mechanical')[0], 2)
            code, _, err = self.cli('ideas', 'close', 'test', idea, '--mechanical', '--result-path', str(result))
            self.assertEqual(code, 0, err)

    def test_lint_flags_taste_call_without_decider(self):
        self.healthy()
        row = dict(rh.latest(self.history()).popitem()[1])
        row.update(status='closed', closed_reason='known', event='close', revised=rh.now(), decided_by='gpt-6.1-sol')
        rh.append(self.lane / 'IDEAS.jsonl', row)
        code, out = self.run_lint()
        self.assertEqual(code, 1)
        self.assertIn('not gpt-6.1-sol', out)
    def setUp(self):
        # These tests exercise pre-cadence lint checks; bootstrap must not depend on wall time.
        cadence_check = patch.object(rh.cadence, 'lint', return_value=[])
        cadence_check.start()
        self.addCleanup(cadence_check.stop)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.lane = self.root / 'lanes/test'
        self.lane.mkdir(parents=True)
        (self.lane / 'INTAKE.toml').write_text('keywords = []\n')
        env = patch.dict('os.environ', {'RH_DECIDED_BY': 'claude-opus-5-5'})
        env.start()
        self.addCleanup(env.stop)

    def cli(self, *args, prior_art=True):
        args = list(args)
        if args[:2] == ['ideas', 'promote'] and prior_art and '--prior-art' not in args:
            survey = self.root / 'PRIOR_ART.md'
            prior_fixture(survey)
            args += ['--prior-art', str(survey)]
        if args[:2] == ['ideas', 'promote']:
            args += ['--sealed-holdout']
        if args[:2] == ['ideas', 'close'] and '--result-path' in args:
            args += ['--config-path', str(config_fixture(self.root / 'config.json'))]
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = rh.main(['--root', str(self.root)] + list(args))
        return code, out.getvalue(), err.getvalue()

    def add(self, **kw):
        args = ['ideas', 'add', 'test', '--claim', kw.pop('claim', 'A claim'),
                '--source-type', kw.pop('source_type', 'internal')]
        for key, value in kw.items():
            args.extend(['--' + key.replace('_', '-'), value])
        code, out, err = self.cli(*args)
        self.assertEqual(code, 0, err)
        return out.strip()

    def history(self):
        return rh.rows(self.lane / 'IDEAS.jsonl')

    def run_lint(self):
        code, out, _ = self.cli('lint', 'test')
        return code, out

    def healthy(self):
        for i in range(3):
            self.add(claim='idea ' + str(i))
        rh.append(self.lane / 'INTAKE_RUNS.jsonl', dict(created=rh.now(), sources_read=['arxiv'], added=0))

    def hit(self, title='A paper', url='https://example.org/paper'):
        return dict(title=title, source_url=url, source_type='paper')

    def ingest(self, hits, cfg=None, dry=False):
        with contextlib.redirect_stdout(io.StringIO()):
            return rh.ingest(self.lane, hits, cfg or {}, dry)

    def test_add_requires_source_type(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as cm:
            rh.main(['--root', str(self.root), 'ideas', 'add', 'test', '--claim', 'x'])
        self.assertEqual(cm.exception.code, 2)

    def test_every_external_source_requires_url(self):
        for source in rh.EXTERNAL:
            code, _, err = self.cli('ideas', 'add', 'test', '--source-type', source, '--claim', 'x', '--source-url', '  ')
            self.assertEqual(code, 2, source)
            self.assertIn('requires source_url', err)
        self.assertEqual(self.history(), [])

    def test_external_add_has_required_fields(self):
        self.add(source_type='paper', source_url='https://example.org')
        row = self.history()[0]
        self.assertTrue(set(('id created session source_type source_url claim question_it_answers board test bar status result_path closed_reason data_tags').split()) <= row.keys())

    def test_internal_and_owner_allow_empty_url(self):
        self.add(source_type='internal')
        self.add(source_type='owner')
        self.assertEqual(len(self.history()), 2)

    def test_promote_requires_each_field(self):
        idea = self.add()
        for missing in ('board', 'test', 'bar'):
            args = ['ideas', 'promote', 'test', idea]
            for field in ('board', 'test', 'bar'):
                if field != missing:
                    args += ['--' + field, 'value']
            code, _, err = self.cli(*args)
            self.assertEqual(code, 2)
            self.assertIn(missing, err)
        self.assertEqual(len(self.history()), 1)

    def test_promote_is_append_only_and_list_folds(self):
        idea = self.add()
        before = (self.lane / 'IDEAS.jsonl').read_bytes()
        code, _, err = self.cli('ideas', 'promote', 'test', idea, '--board', 'sealed-A', '--test', 'rank binders', '--bar', 'beat baseline')
        self.assertEqual(code, 0, err)
        self.assertTrue((self.lane / 'IDEAS.jsonl').read_bytes().startswith(before))
        code, out, _ = self.cli('ideas', 'list', 'test')
        self.assertEqual(len(out.splitlines()), 1)
        self.assertEqual(json.loads(out)['status'], 'testing')
        self.assertEqual(self.history()[0]['created'], self.history()[1]['created'])

    def test_none_requires_route_and_counts_depth(self):
        idea = self.add(board='none')
        self.assertEqual(self.cli('ideas', 'promote', 'test', idea)[0], 2)
        self.assertEqual(self.cli('ideas', 'promote', 'test', idea, '--route', 'ask organiser at forum')[0], 0)
        self.assertFalse(self.history()[-1]['runnable'])
        self.assertEqual(self.cli('ideas', 'depth', 'test')[1].strip(), '1')

    def test_only_new_can_promote(self):
        idea = self.add(board='none', route='expert')
        self.assertEqual(self.cli('ideas', 'promote', 'test', idea)[0], 0)
        self.assertEqual(self.cli('ideas', 'promote', 'test', idea)[0], 2)

    def test_close_requires_evidence_or_reason(self):
        idea = self.add()
        self.assertEqual(self.cli('ideas', 'close', 'test', idea)[0], 2)
        self.assertEqual(self.cli('ideas', 'close', 'test', idea, '--closed-reason', ' ')[0], 2)
        self.assertEqual(self.cli('ideas', 'close', 'test', idea, '--result-path', str(self.root / 'missing'))[0], 2)
        self.assertEqual(len(self.history()), 1)

    def test_close_accepts_file_and_retains_history(self):
        idea = self.add()
        result = self.root / 'result.txt'
        result.write_text('negative')
        self.assertEqual(self.cli('ideas', 'promote', 'test', idea, '--board', 'b', '--test', 't', '--bar', 'x')[0], 0)
        self.assertEqual(self.cli('ideas', 'close', 'test', idea, '--result-path', str(result))[0], 0)
        self.assertEqual(len(self.history()), 3)
        self.assertEqual(self.cli('ideas', 'depth', 'test')[1].strip(), '0')

    def test_close_accepts_reason(self):
        idea = self.add()
        self.assertEqual(self.cli('ideas', 'close', 'test', idea, '--closed-reason', 'ruled out by organiser', '--no-test-reason', 'organiser exclusion')[0], 0)
        self.assertEqual(self.history()[-1]['closed_reason'], 'ruled out by organiser')

    def test_dedupe_url_even_after_closed(self):
        self.ingest([self.hit()])
        idea = self.history()[0]['id']
        self.cli('ideas', 'close', 'test', idea, '--closed-reason', 'out of scope', '--no-test-reason', 'source triage fixture')
        self.assertEqual(self.ingest([self.hit('Changed title')]), 0)
        self.assertEqual(len(self.history()), 2)

    def test_dedupe_normalized_title_even_after_closed(self):
        self.ingest([self.hit('Binder: Design — RANKING!')])
        self.cli('ideas', 'close', 'test', self.history()[0]['id'], '--closed-reason', 'no')
        self.assertEqual(self.ingest([self.hit(' binder design ranking ', 'https://other.org')]), 0)

    def test_dedupe_within_batch(self):
        self.assertEqual(self.ingest([self.hit(), self.hit()]), 1)

    def test_banned_hit_recorded_closed_and_deduped(self):
        cfg = {'banned_patterns': [{'pattern': r'forbidden\s+stage', 'reason': 'lane rule: excluded stage'}]}
        hit = self.hit('A paper at forbidden stage')
        self.assertEqual(self.ingest([hit], cfg), 1)
        row = self.history()[0]
        self.assertEqual(row['status'], 'closed')
        self.assertEqual(row['closed_reason'], 'lane rule: excluded stage')
        self.assertEqual(row['data_tags'], ['BANNED:lane rule: excluded stage'])
        self.assertEqual(self.ingest([hit], cfg), 0)

    def test_banned_matches_summary_and_url(self):
        cfg = {'banned_patterns': [{'pattern': 'excluded', 'reason': 'rule'}]}
        hit = self.hit()
        hit['summary'] = 'An EXCLUDED dataset'
        self.ingest([hit], cfg)
        self.assertEqual(self.history()[0]['status'], 'closed')

    def test_dry_run_never_writes_or_fetches(self):
        (self.lane / 'INTAKE.toml').write_text('keywords = ["binder"]\n')
        with patch.object(rh, 'get_url', side_effect=AssertionError('network forbidden')):
            self.assertEqual(self.cli('intake', 'test')[0], 0)
            self.assertEqual(self.cli('intake', 'test', '--dry-run')[0], 0)
        self.assertEqual(self.history(), [])
        self.assertFalse((self.lane / 'INTAKE_RUNS.jsonl').exists())

    def test_dry_run_fixture_prints_would_add(self):
        fixture = self.root / 'hits.jsonl'
        rh.append(fixture, self.hit())
        code, out, err = self.cli('intake', 'test', '--hits-file', str(fixture))
        self.assertEqual(code, 0, err)
        self.assertIn('WOULD ADD', out)
        self.assertEqual(self.history(), [])

    def test_live_zero_hits_records_read(self):
        with patch.object(rh, 'fetch_sources', return_value=iter([('arxiv', [], '')])):
            self.assertEqual(self.cli('intake', 'test', '--live')[0], 0)
        self.assertEqual(rh.rows(self.lane / 'INTAKE_RUNS.jsonl')[0]['sources_read'], ['arxiv'])

    def test_failed_intake_does_not_certify_read(self):
        with patch.object(rh, 'fetch_sources', return_value=iter([('arxiv', [], 'timeout')])):
            self.assertEqual(self.cli('intake', 'test', '--live')[0], 1)
        self.assertEqual(rh.rows(self.lane / 'INTAKE_RUNS.jsonl')[0]['sources_read'], [])

    def test_lint_empty_has_all_missing_checks(self):
        code, out = self.run_lint()
        self.assertEqual(code, 1)
        for text in ('depth(new|testing)=0 < 3', 'no external source', 'no intake run'):
            self.assertIn(text, out)

    def test_lint_healthy_zero_novel_hits_passes(self):
        self.healthy()
        self.assertEqual(self.run_lint()[0], 0)

    def test_lint_recent_external_idea_without_intake_fails(self):
        for i in range(3):
            self.add(source_type='paper', source_url='https://example.org/' + str(i))
        code, out = self.run_lint()
        self.assertEqual(code, 1)
        self.assertIn('no intake run', out)
        self.assertNotIn('no external source added', out)

    def test_lint_run_without_read_fails_even_with_new_external_idea(self):
        self.add(source_type='paper', source_url='https://example.org')
        rh.append(self.lane / 'INTAKE_RUNS.jsonl', dict(created=rh.now(), sources_read=[]))
        self.assertIn('intake read no external sources', self.run_lint()[1])

    def test_lint_stale_and_future_read_fail(self):
        for hours in (-25, 1):
            stamp = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=hours)).isoformat()
            rh.append(self.lane / 'INTAKE_RUNS.jsonl', dict(created=stamp, sources_read=['arxiv']))
        self.assertIn('no intake run', self.run_lint()[1])

    def test_lint_each_stop_pattern(self):
        self.healthy()
        report = self.root / 'report.md'
        for text in ('NO IDEAS', 'out of ideas', 'recommend stopping', 'we could stop', 'nothing left to try'):
            report.write_text(text)
            code, out, _ = self.cli('lint', 'test', '--report', str(report))
            self.assertEqual(code, 1)
            self.assertIn('matches stop-pattern', out)

    def test_stop_pattern_requires_positive_depth(self):
        report = self.root / 'report.md'
        report.write_text('no ideas')
        self.assertNotIn('stop-pattern', self.cli('lint', 'test', '--report', str(report))[1])

    def test_lint_invalid_promoted_history_even_if_later_closed(self):
        row = rh.new_idea('internal', '', 'claim')
        row.update(status='testing')
        rh.append(self.lane / 'IDEAS.jsonl', row)
        row = dict(row, status='closed', closed_reason='negative')
        rh.append(self.lane / 'IDEAS.jsonl', row)
        self.assertIn('row 1 id=' + row['id'] + ': promotion requires board, test, bar', self.run_lint()[1])

    def test_lint_none_promoted_without_route(self):
        row = rh.new_idea('internal', '', 'claim', board='none', status='testing')
        rh.append(self.lane / 'IDEAS.jsonl', row)
        self.assertIn('board=none requires route', self.run_lint()[1])

    def test_lint_all_closed_does_not_fail_external_read(self):
        self.healthy()
        for row in list(rh.latest(self.history()).values()):
            self.cli('ideas', 'close', 'test', row['id'], '--closed-reason', 'negative', '--no-test-reason', 'source triage fixture')
        code, out = self.run_lint()
        self.assertEqual(code, 1)  # Explicit queue floor still applies.
        self.assertIn('depth(new|testing)=0 < 3', out)
        self.assertNotIn('no external', out)
        self.assertNotIn('no intake', out)

    def test_answers_actual_format_tag_routing_and_dedupe(self):
        (self.lane / 'INTAKE.toml').write_text('answers_tags = ["restricted"]\n')
        fixture = self.root / 'ANSWERS.md'
        fixture.write_text('# Answers\n\n- 2026-10-27 | https://x.com/a/status/1 | a | restricted\n  Answer: Try a different score.\n  More detail.\n  For us: verify.\n\n- 2026-10-27 | https://x.com/b/status/2 | b | other\n  Answer: unrelated\n')
        for _ in range(2):
            self.assertEqual(self.cli('answers-sync', 'test', '--answers-file', str(fixture))[0], 0)
        self.assertEqual(len(self.history()), 1)
        self.assertEqual(self.history()[0]['source_type'], 'answers')
        self.assertIn('More detail.', self.history()[0]['claim'])
        self.assertEqual(self.history()[0]['source_url'], 'https://x.com/a/status/1')

    def test_answers_absent_file_or_tag_quiet(self):
        fixture = self.root / 'ANSWERS.md'
        self.assertEqual(self.cli('answers-sync', 'test', '--answers-file', str(fixture)), (0, '', ''))
        fixture.write_text('# no matching entries')
        self.assertEqual(self.cli('answers-sync', 'test', '--answers-file', str(fixture)), (0, '', ''))

    def test_missing_lane_not_created(self):
        code, _, err = self.cli('intake', 'missing')
        self.assertEqual(code, 2)
        self.assertIn('lane directory missing', err)
        self.assertFalse((self.root / 'lanes/missing').exists())

    def test_path_traversal_rejected(self):
        self.assertEqual(self.cli('ideas', 'list', '../test')[0], 2)

    def test_malformed_history_fails_precisely(self):
        (self.lane / 'IDEAS.jsonl').write_text('not json\n')
        code, _, err = self.cli('ideas', 'list', 'test')
        self.assertEqual(code, 2)
        self.assertIn('IDEAS.jsonl:1:', err)

    def test_synthetic_config_parses(self):
        cfg = rh.config(ROOT.parent / 'examples/toy-lane/INTAKE.toml')
        rh.validate_config(cfg)
        self.assertIsInstance(cfg['keywords'], list)
        for rule in cfg.get('banned_patterns', []):
            self.assertTrue(rule['reason'].strip())

    def test_claude_science_required_lint_and_promote(self):
        # toy-evolution, 10-30: board-deciding ideas must go through Claude Science first.
        (self.lane / 'INTAKE.toml').write_text('keywords = []\nclaude_science_required = true\nclaude_science_max_age_days = 2\n')
        idea = self.add(source_type='paper', source_url='https://example.org/p')
        code, out, _ = self.cli('lint', 'test')
        self.assertIn('no claude-science idea added in last 2 day(s)', out)
        code, _, err = self.cli('ideas', 'promote', 'test', idea, '--board', 'b', '--test', 't', '--bar', 'x')
        self.assertEqual(code, 2)
        self.assertIn('--review-url', err)
        code, _, err = self.cli('ideas', 'promote', 'test', idea, '--board', 'b', '--test', 't', '--bar', 'x',
                                '--review-url', 'http://localhost:8765/projects/p1')
        self.assertEqual(code, 0, err)
        self.add(source_type='claude-science', source_url='http://localhost:8765/projects/p1', claim='CS review')
        code, out, _ = self.cli('lint', 'test')
        self.assertNotIn('claude-science', out)

    def test_claude_science_idea_needs_independent_check(self):
        idea = self.add(source_type='claude-science', source_url='http://localhost:8765/projects/p1', claim='CS says so')
        args = ('ideas', 'promote', 'test', idea, '--board', 'b', '--test', 't', '--bar', 'x')
        code, _, err = self.cli(*args)
        self.assertEqual(code, 2)
        self.assertIn('--independent-check', err)
        code, _, err = self.cli(*args, '--independent-check', 'reran the count from the primary table')
        self.assertEqual(code, 0, err)

    def test_claude_science_model_rule(self):
        rh.validate_config({'keywords': [], 'claude_science_model': 'claude-opus-4-6'})
        with self.assertRaises(ValueError) as caught:
            rh.validate_config({'keywords': [], 'claude_science_model': 'claude-opus-5'})
        self.assertIn('banned', str(caught.exception))
        cfg = {'keywords': [], 'claude_science_model': 'claude-opus-4-6'}
        rh.validate_config(cfg)
        self.assertEqual(cfg['claude_science_model'], rh.CS_ALTERNATE_MODEL)

    def test_session_model_follows_the_last_assistant_turn(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / '.claude/projects/x'
            folder.mkdir(parents=True)
            turns = [{'type': 'assistant', 'message': {'model': 'claude-opus-5-5'}},
                     {'type': 'assistant', 'message': {'model': 'claude-opus-4-6[1m]'}},
                     {'type': 'assistant', 'message': {'model': '<synthetic>'}}]
            (folder / 's1.jsonl').write_text('\n'.join(json.dumps(t) for t in turns))
            with patch.dict('os.environ', {'RH_TRANSCRIPTS_ROOT': str(folder.parent)}):
                with patch.dict('os.environ', {'CLAUDE_CODE_SESSION_ID': 's1'}):
                    self.assertEqual(rh.session_model(), 'claude-opus-4-6')
                with patch.dict('os.environ', {'CLAUDE_CODE_SESSION_ID': 'none'}):
                    self.assertIsNone(rh.session_model())

    def test_banned_cs_sessions_reads_the_daemon_database(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / 'orgs/synthetic/operon-cli.db'
            db.parent.mkdir(parents=True)
            con = sqlite3.connect(str(db))
            con.execute('create table frames (id, parent_frame_id, project_id, created_at, model)')
            late = rh.CS_MODEL_RULE_MS + 1
            con.executemany('insert into frames values (?,?,?,?,?)', [
                ('bad', None, 'proj_a', late, 'claude-opus-5'), ('old', None, 'proj_a', late - 2, 'claude-opus-5'),
                ('child', 'bad', 'proj_a', late, 'claude-opus-5'), ('ok', None, 'proj_a', late, 'claude-opus-5-5'),
                ('other', None, 'proj_b', late, 'claude-opus-5')])
            con.commit(); con.close()
            with patch.dict('os.environ', {'RH_CS_DB_ROOT': tmp}):
                self.assertEqual(rh.banned_cs_sessions('http://localhost:8765/projects/proj_a'), ['bad'])
                self.assertEqual(rh.banned_cs_sessions(''), [])

    def test_claude_science_flag_off_changes_nothing(self):
        idea = self.add(source_type='paper', source_url='https://example.org/p')
        code, _, err = self.cli('ideas', 'promote', 'test', idea, '--board', 'b', '--test', 't', '--bar', 'x')
        self.assertEqual(code, 0, err)
        for bad in ('claude_science_required = "yes"\n', 'claude_science_max_age_days = 0\n',
                    'claude_science_project = "https://example.org/x"\n'):
            with self.assertRaises(ValueError):
                rh.validate_config(rh.config(self._toml(bad)))

    def test_lane_key_after_banned_table_is_rejected(self):
        # 10-30: both restricted lanes appended claude_science_* after their [[banned_patterns]] tables.
        # TOML scoped the keys into the table, so the flag was inert and lint stayed green.
        body = ("keywords = []\n[[banned_patterns]]\npattern = 'x'\nreason = 'r'\n"
                "claude_science_required = true\n")
        with self.assertRaises(ValueError) as caught:
            rh.validate_config(rh.config(self._toml(body)))
        self.assertIn('claude_science_required', str(caught.exception))
        self.assertIn('above the first [[banned_patterns]]', str(caught.exception))

    def _toml(self, body):
        path = self.root / 'x.toml'
        path.write_text(body)
        return path

    def test_bare_arxiv_query_is_field_qualified(self):
        # arXiv treats an unfielded search_query loosely: the VE lane's first live intake
        # returned 160 of 162 hits off-topic (quantum, robotics, film) from plain phrases.
        self.assertEqual(rh.arxiv_search_query('optimal transport'),
                         'all:"optimal" AND all:"transport"')
        for already_fielded in ('all:"flow matching" AND all:"single-cell"', 'ti:"binder design"'):
            self.assertEqual(rh.arxiv_search_query(already_fielded), already_fielded)
        self.assertEqual(rh.arxiv_search_query(''), '')

    def test_atom_and_rss_parsing(self):
        atom = b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><id>https://arxiv.org/abs/1</id><title>Paper</title><summary>Summary</summary></entry></feed>'
        self.assertEqual(list(rh.feed_hits(atom))[0]['source_url'], 'https://arxiv.org/abs/1')
        rss = b'<rss><channel><item><title>Thread</title><link>https://community.org/1</link></item></channel></rss>'
        self.assertEqual(list(rh.feed_hits(rss, 'community'))[0]['source_type'], 'community')

    def test_fetchers_offline_fixtures(self):
        atom = b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><id>https://arxiv.org/abs/1</id><title>Binder paper</title></entry></feed>'
        bio = json.dumps({'messages': [{'status': 'ok'}], 'collection': [{'title': 'Binder paper', 'doi': '10.1101/123', 'abstract': 'binder'}]}).encode()
        with patch.object(rh, 'get_url', side_effect=[atom, bio, b'<html><title>Community thread</title></html>']) as get:
            results = list(rh.fetch_sources(dict(keywords=['binder'], community_urls=['https://community.org'])))
        self.assertEqual(get.call_count, 3)
        self.assertTrue(all(not error for _, _, error in results))
        self.assertEqual(results[1][1][0]['source_url'], 'https://www.biorxiv.org/content/10.1101/123')

    def test_github_pr_feed_filters_and_reports_errors(self):
        prs = json.dumps([dict(title='TOY42: improved upper bound', html_url='https://github.com/o/r/pull/2', body='x', created_at='2026-10-27T00:00:00Z'),
                          dict(title='Typo fix', html_url='https://github.com/o/r/pull/1', body=None, created_at='2026-10-26T00:00:00Z')]).encode()
        with patch.object(rh, 'get_url', return_value=prs):
            ((source, hits, error),) = list(rh.fetch_sources(dict(github_pr_repos=['o/r'], github_pr_include=r'TOY42')))
        self.assertEqual((source, error), ('github-prs:o/r', ''))
        self.assertEqual([h['source_url'] for h in hits], ['https://github.com/o/r/pull/2'])
        self.assertEqual(hits[0]['source_type'], 'community')
        with patch.object(rh, 'get_url', side_effect=OSError('down')):
            ((_, hits, error),) = list(rh.fetch_sources(dict(github_pr_repos=['o/r'])))
        self.assertEqual((hits, error), ([], 'down'))

    def test_scheduler_skips_missing_lanes_and_continues_failure(self):
        (self.root / 'lanes/restricted-b').mkdir()
        (self.root / 'lanes/restricted-a').mkdir()
        for name in ('restricted-b', 'restricted-a'):
            (self.root / 'lanes' / name / 'INTAKE.toml').write_text('')
        with patch.object(intake_all, 'ROOT', self.root), patch.object(intake_all.subprocess, 'run') as run:
            run.side_effect = [subprocess.CompletedProcess([], 1), subprocess.CompletedProcess([], 0), subprocess.CompletedProcess([], 0)]
            self.assertEqual(intake_all.main(), 1)
        self.assertEqual(run.call_count, 3)
        self.assertIn('--live', run.call_args[0][0])
        self.assertEqual(run.call_args[0][0][:3], ['/usr/bin/nice', '-n', '19'])

    def test_actual_cli_subprocess(self):
        result = subprocess.run([sys.executable, str(ROOT / 'rh.py'), '--root', str(self.root), 'ideas', 'depth', 'test'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, '0\n')

    def test_no_x_network_fetcher(self):
        with patch.object(rh, 'get_url', side_effect=AssertionError('must not fetch X')):
            self.assertEqual(list(rh.fetch_sources({'x_handles': ['organiser'], 'x_post_ids': ['123']})), [])

    def test_literal_toml_regex_preserves_backslashes(self):
        path = self.lane / 'INTAKE.toml'
        path.write_text("keywords = []\n[[banned_patterns]]\npattern = '\\bexcluded\\b'\nreason = 'data rule'\n")
        cfg = rh.config(path)
        self.assertEqual(cfg['banned_patterns'][0]['pattern'], r'\bexcluded\b')
        self.ingest([self.hit('An excluded stage')], cfg)
        self.assertEqual(self.history()[0]['status'], 'closed')

    def test_empty_x_capture_is_not_external_read(self):
        (self.lane / 'INTAKE.toml').write_text('x_local_file = "X_HITS.jsonl"\n')
        (self.lane / 'X_HITS.jsonl').touch()
        self.assertEqual(self.cli('intake', 'test', '--live')[0], 0)
        self.assertEqual(rh.rows(self.lane / 'INTAKE_RUNS.jsonl')[0]['sources_read'], [])

    def test_none_board_whitespace_cannot_become_runnable(self):
        idea = self.add(board=' none ', route='expert')
        self.assertEqual(self.cli('ideas', 'promote', 'test', idea)[0], 0)
        self.assertFalse(self.history()[-1]['runnable'])

    def test_biorxiv_budget_visits_newest_pages(self):
        first = {'messages': [{'status': 'ok', 'total': 250}], 'collection': [
            {'title': 'binder paper', 'doi': '10.1101/' + str(i)} for i in range(100)]}
        last = {'messages': [{'status': 'ok', 'total': 250}], 'collection': [
            {'title': 'recent binder paper', 'doi': '10.1101/new'}]}
        with patch.object(rh, 'get_url', side_effect=[json.dumps(first).encode(), json.dumps(last).encode()]) as get:
            result = list(rh.fetch_sources({'biorxiv_queries': ['binder'], 'biorxiv_pages': 2}))
        self.assertEqual(len(result), 2)
        self.assertTrue(get.call_args_list[0][0][0].endswith('/0'))
        self.assertTrue(get.call_args_list[1][0][0].endswith('/200'))
        self.assertEqual(result[-1][1][0]['title'], 'recent binder paper')


class PodTests(unittest.TestCase):
    def setUp(self):
        monitor = patch.object(rh, 'lint_monitor', return_value=0)
        monitor.start()
        self.addCleanup(monitor.stop)
        cadence_monitor = patch.object(rh.cadence, 'monitor', return_value=0)
        cadence_monitor.start()
        self.addCleanup(cadence_monitor.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for lane in pods.LANES | {'restricted-a', 'restricted-b', 'no-pods'}:
            path = self.root / 'lanes' / lane
            path.mkdir(parents=True)
            (path / 'INTAKE.toml').write_text('keywords = []\n')
            for _ in range(3):
                rh.append(path / 'IDEAS.jsonl', rh.new_idea('internal', '', 'fixture'))
            rh.append(path / 'INTAKE_RUNS.jsonl', dict(created=rh.now(), sources_read=['fixture']))
        self.clock = dt.datetime(2026, 11, 2, 16, tzinfo=dt.timezone.utc)
        self.pod = dict(name='p1', pod_id='abcdef', ssh_target=('abcdef-123' + chr(64) + 'ssh.runpod.io'),
                        lane='team', vcpus=32, gpus=0, dollars_per_hour=.96, owner_note='fixture owner')
        (self.root / 'pods.json').write_text(json.dumps([self.pod]))
        mock = patch.object(pods, 'probe', side_effect=AssertionError('live pod forbidden'))
        self.prober = mock.start()
        self.addCleanup(mock.stop)
        mock = patch.object(pods.harvest, 'run', return_value=0)
        mock.start()
        self.addCleanup(mock.stop)
        mock = patch.object(pods.pod_guard.lane_alerts, 'pod_alert', return_value=True)
        self.notifier = mock.start()
        self.addCleanup(mock.stop)
        mock = patch.object(rh, 'now', side_effect=lambda: self.clock.isoformat())
        mock.start()
        self.addCleanup(mock.stop)

    def cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = rh.main(['--root', str(self.root)] + list(args))
        return rc, out.getvalue(), err.getvalue()

    def sample(self, minute=0, cpu=.1, gpu=None, reachable=True, pod=None):
        p = pod or self.pod
        row = dict(utc=(self.clock + dt.timedelta(minutes=minute)).isoformat(), pod=p['name'],
                   pod_id=p['pod_id'], lane=p['lane'], cpu_frac=cpu, gpu_util=gpu, reachable=reachable)
        rh.append(self.root / 'PODS.jsonl', row)
        return row

    def history(self):
        return rh.rows(self.root / 'PODS.jsonl')

    def test_cpu_fraction_and_live_allowance(self):
        self.assertAlmostEqual(pods.cpu_fraction(1_000_000, 11_000_000, 5, 32), .0625)
        self.assertAlmostEqual(pods.cpu_fraction(0, 96_000_000, 5, 32), .60)
        self.assertEqual(pods.allowance('64', '3200000 100000'), 32)
        self.assertEqual(pods.allowance('16', 'max 100000'), 16)
        self.assertEqual(pods.allowance('8', '150000 100000'), 1.5)
        self.assertEqual(pods.allowance('128', '1600000\n100000'), 16)
        self.assertEqual(pods.allowance('32', '-1\n100000'), 32)
        with self.assertRaises(ValueError):
            pods.allowance('32', '100000 0')
        for args in [(10, 0, 5, 32), (0, 10, 0, 32), (0, 10, 5, 0)]:
            with self.assertRaises(ValueError):
                pods.cpu_fraction(*args)

    def test_probe_parses_cgroup_delta_and_all_gpu_devices(self):
        fields = dict(NPROC='64', MAX='3200000 100000', GPUS='GPU 0: A100\nGPU 1: A100',
                      CPU1='usage_usec 1000000\nuser_usec 0', CPU2='usage_usec 11000000',
                      TIME1='10.0 0.0', TIME2='15.0 0.0', GPUUTIL='2\n80')
        # Parse through the original function captured before setUp's patch.
        with patch.object(pods, 'remote_read', return_value=fields):
            result = ORIGINAL_POD_PROBE(self.pod)
            self.assertEqual(result['vcpus'], 32)
            self.assertEqual(result['gpus'], 2)
            self.assertEqual(result['gpu_util'], 80)
            self.assertAlmostEqual(result['cpu_frac'], .0625)
            fields['GPUUTIL'] = 'N/A\n80'
            with self.assertRaises(ValueError):
                ORIGINAL_POD_PROBE(self.pod)

    def test_cgroup_v1_uses_nanosecond_counter_and_cfs_quota(self):
        fields = dict(MODE='v1', NPROC='128', MAX='1600000\n100000', GPUS='NO_GPU',
                      CPU1='1000000000', CPU2='11000000000', TIME1='10 0', TIME2='15 0', GPUUTIL='')
        with patch.object(pods, 'remote_read', return_value=fields):
            result = ORIGINAL_POD_PROBE(self.pod)
        self.assertEqual(result['vcpus'], 16)
        self.assertAlmostEqual(result['cpu_frac'], .125)
        self.assertEqual(result['gpus'], 0)

    def test_underused_15_minute_cadence_and_busy_reset(self):
        self.sample(0)
        self.assertEqual(pods.state(self.history(), self.pod), (False, False))
        self.sample(15)
        self.assertEqual(pods.state(self.history(), self.pod), (False, False))
        self.sample(30)
        self.assertEqual(pods.state(self.history(), self.pod), (True, False))
        self.sample(45, cpu=.60)
        self.sample(60)
        self.assertEqual(pods.state(self.history(), self.pod), (False, False))
        self.sample(75)
        self.assertEqual(pods.state(self.history(), self.pod), (False, False))
        self.sample(90)
        self.assertEqual(pods.state(self.history(), self.pod), (True, False))

    def test_underused_exact_25_minute_boundary_and_gpu_threshold(self):
        self.pod['gpus'] = 1
        self.sample(0, gpu=59.9)
        self.sample(12, gpu=59.9)
        self.sample(24, gpu=59.9)
        self.assertFalse(pods.state(self.history(), self.pod)[0])
        self.sample(25, gpu=59.9)
        self.assertTrue(pods.state(self.history(), self.pod)[0])
        self.sample(40, gpu=60)
        self.assertFalse(pods.state(self.history(), self.pod)[0])
        self.sample(55, gpu=None)
        self.assertFalse(pods.state(self.history(), self.pod)[0])

    def test_idle_windows_follow_cpu_and_gpu_contracts(self):
        for minute in (0, 5, 10, 15):
            self.sample(minute, cpu=.049)
        self.assertEqual(pods.state(self.history(), self.pod), (False, False))
        self.sample(20, cpu=.049)
        self.assertEqual(pods.state(self.history(), self.pod), (False, True))
        self.sample(25, cpu=.05)
        self.assertFalse(pods.state(self.history(), self.pod)[1])
        burst = [dict(self.history()[0], utc=(self.clock + dt.timedelta(minutes=i)).isoformat()) for i in range(4)]
        self.assertEqual(pods.state(burst, self.pod), (False, False))
        self.pod['gpus'] = 1
        gpu_rows = [dict(r, cpu_frac=1, gpu_util=0) for r in self.history()[:3]]
        self.assertTrue(pods.state(gpu_rows, self.pod)[1])
        gpu_rows[-1]['gpu_util'] = 1
        self.assertFalse(pods.state(gpu_rows, self.pod)[1])

    def test_unreachable_resets_evidence_and_never_crashes_check(self):
        self.sample(-30, cpu=0)
        self.sample(-15, cpu=0)
        self.prober.side_effect = subprocess.TimeoutExpired('ssh SECRET', 60, output='SECRET')
        code, out, err = self.cli('pods', 'sample')
        self.assertEqual(code, 0, err)
        row = json.loads(out)
        self.assertFalse(row['reachable'])
        self.assertIsNone(row['cpu_frac'])
        self.assertIsNone(row['gpu_util'])
        self.assertNotIn('SECRET', out + err + (self.root / 'PODS.jsonl').read_text())
        self.assertEqual(pods.state(self.history(), self.pod), (False, False))
        self.prober.assert_called_once()
        self.notifier.assert_not_called()
        self.sample(15, cpu=0)
        self.assertFalse(pods.state(self.history(), self.pod)[0])

    def test_agent_alert_throttles_30_minutes_and_retries_failure(self):
        for minute in range(0, 21, 5):
            self.sample(minute, cpu=0)
        for _ in range(2):
            pods.alerts(self.root, self.history(), self.pod, rh)
        self.assertEqual(self.notifier.call_count, 1)
        for minute in range(25, 50, 5):
            self.sample(minute, cpu=0)
            pods.alerts(self.root, self.history(), self.pod, rh)
        self.assertEqual(self.notifier.call_count, 1)
        self.sample(50, cpu=0)
        self.notifier.return_value = False
        pods.alerts(self.root, self.history(), self.pod, rh)
        self.assertEqual(self.notifier.call_count, 2)
        self.notifier.return_value = True
        pods.alerts(self.root, self.history(), self.pod, rh)
        self.assertEqual(self.notifier.call_count, 3)
        events = [r for r in self.history() if r.get('event') == 'AGENT_ALERT']
        self.assertEqual(len(events), 2)
        self.assertEqual(events[-1]['minutes_idle'], 50)
        self.assertAlmostEqual(events[-1]['idle_cost'], .8)

    def test_idle_alert_only_wakes_agents_without_lifecycle(self):
        self.pod['gpus'] = 1
        for minute in (0, 5, 10):
            self.sample(minute, cpu=1, gpu=0)
        with patch.object(pods, 'reap', side_effect=AssertionError('no lifecycle')):
            pods.alerts(self.root, self.history(), self.pod, rh)
            pods.alerts(self.root, self.history(), self.pod, rh)
        self.assertEqual(self.notifier.call_count, 1)
        payload = self.notifier.call_args.args[-1]
        self.assertEqual(payload['kind'], 'pod-idle')
        self.assertEqual(payload['for'], 'agents')
        self.assertEqual(payload['pod_id'], self.pod['pod_id'])
        self.assertEqual(len(pods.samples(self.history(), self.pod)), 3)

    def test_lint_fails_every_pod_lane_and_leaves_other_lanes_unchanged(self):
        for lane in sorted(pods.LANES):
            p = dict(self.pod, lane=lane)
            (self.root / 'pods.json').write_text(json.dumps([p]))
            for minute in (-30, -15, 0):
                self.sample(minute, pod=p)
            code, out, err = self.cli('lint', lane)
            self.assertEqual(code, 1, err)
            self.assertIn('underused pod p1: CPU 10.0%', out)
        for lane in ('restricted-a', 'restricted-b', 'no-pods'):
            code, out, err = self.cli('lint', lane)
            self.assertEqual(code, 0, err)
            self.assertEqual(out, 'OK {}: outreach (0 messages)\nOK {}: depth=3; external reading and intake fresh\n'.format(lane, lane))
        self.prober.assert_not_called()

    def test_busy_uses_latest_fresh_sample_cpu_or_gpu_and_never_probes(self):
        self.assertEqual(self.cli('pods', 'busy', 'p1')[0], 1)
        self.sample(0, cpu=.599)
        self.assertEqual(self.cli('pods', 'busy', 'p1')[0], 1)
        self.sample(0, cpu=.60)
        self.assertEqual(self.cli('pods', 'busy', 'p1')[0], 0)
        self.sample(0, cpu=None, reachable=False)
        self.assertEqual(self.cli('pods', 'busy', 'p1')[0], 1)
        self.pod['gpus'] = 1
        (self.root / 'pods.json').write_text(json.dumps([self.pod]))
        self.sample(0, cpu=0, gpu=60)
        self.assertEqual(self.cli('pods', 'busy', 'p1')[0], 0)
        self.clock += dt.timedelta(minutes=31)
        self.assertEqual(self.cli('pods', 'busy', 'p1')[0], 1)
        self.assertEqual(self.cli('pods', 'busy', 'missing')[0], 1)
        self.prober.assert_not_called()

    def test_registry_add_measures_hardware_and_remove_retains_history(self):
        args = ['pods', 'add', 'p2', '--pod-id', 'ghijkl', '--ssh-target', ('ghijkl-124' + chr(64) + 'ssh.runpod.io'),
                '--lane', 'theory', '--dollars-per-hour', '1.28', '--owner-note', 'lane owner',
                '--results', '/workspace/result', '--harvest-dest', str(self.root / 'lanes/theory/results')]
        self.prober.side_effect = None
        self.prober.return_value = dict(vcpus=16, gpus=1, cpu_frac=.8, gpu_util=0)
        self.assertEqual(self.cli(*args)[0], 0)
        registered = pods.registry(self.root)[-1]
        self.assertEqual((registered['vcpus'], registered['gpus']), (16, 1))
        self.assertEqual(self.cli(*args)[0], 2)
        self.assertEqual(self.prober.call_count, 1)
        self.sample()
        before = (self.root / 'PODS.jsonl').read_bytes()
        self.assertEqual(self.cli('pods', 'remove', 'p1')[0], 0)
        self.assertEqual((self.root / 'PODS.jsonl').read_bytes(), before)
        self.assertTrue((self.root / 'pods.json.bak-registry').exists())
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            self.cli(*(args[:args.index('--lane') + 1] + ['restricted-a'] + args[args.index('--lane') + 2:]))

    def test_check_is_parallel_max_eight_and_one_probe_per_pod(self):
        import threading
        import time
        entries = [dict(self.pod, name='p' + str(i), pod_id='id' + str(i),
                        ssh_target=('id{}-123' + chr(64) + 'ssh.runpod.io').format(i)) for i in range(12)]
        (self.root / 'pods.json').write_text(json.dumps(entries))
        active, peak = 0, 0
        guard = threading.Lock()

        def measure(p):
            nonlocal active, peak
            with guard:
                active += 1
                peak = max(peak, active)
            time.sleep(.02)
            with guard:
                active -= 1
            return dict(vcpus=32, gpus=0, cpu_frac=.7, gpu_util=None)

        self.prober.side_effect = measure
        self.assertEqual(self.cli('pods', 'sample')[0], 0)
        self.assertEqual(self.prober.call_count, 12)
        self.assertEqual(len(self.history()), 12)
        self.assertGreater(peak, 1)
        self.assertLessEqual(peak, 8)

    def test_proxy_uses_one_session_and_local_wait_without_uploading(self):
        from unittest.mock import MagicMock
        process = MagicMock()
        process.poll.return_value = None
        prefix = 'RH_fixture'

        def output(items):
            return ''.join('\n{}_{}\n{}\n'.format(prefix, label, value) for label, value in items).encode()

        first = output([('MODE', 'v2'), ('NPROC', '32'), ('MAX', 'max 100000'), ('GPUS', 'NO_GPU'),
                        ('TIME1', '10 0'), ('CPU1', 'usage_usec 1000000'), ('WAIT', '')])
        second = output([('TIME2', '15 0'), ('CPU2', 'usage_usec 11000000'), ('GPUUTIL', ''), ('END', '')])
        with patch.object(pods.subprocess, 'Popen', return_value=process) as popen, \
                patch.object(pods.select, 'select', return_value=([process.stdout], [], [])), \
                patch.object(pods.os, 'read', side_effect=[b'# ', first, second]), \
                patch.object(pods.uuid, 'uuid4', return_value=type('Token', (), {'hex': 'fixture'})()), \
                patch.object(pods.time, 'sleep') as sleep:
            fields = pods.remote_read(self.pod)
        popen.assert_called_once()
        sleep.assert_called_once_with(5)
        self.assertEqual(fields['CPU2'], 'usage_usec 11000000')
        self.assertIn('StrictHostKeyChecking=yes', popen.call_args.args[0])
        commands = b''.join(c.args[0] for c in process.stdin.write.call_args_list).decode()
        for forbidden in ('stty', 'base64', 'curl', 'rm ', 'sleep ', '/proc/1/environ', 'kill '):
            self.assertNotIn(forbidden, commands)
        process.kill.assert_called_once()
        process.wait.assert_called_once()

    def test_proxy_deadline_reaps_local_ssh_without_retry(self):
        from unittest.mock import MagicMock
        process = MagicMock()
        process.poll.return_value = None
        with patch.object(pods.subprocess, 'Popen', return_value=process) as popen, \
                patch.object(pods.time, 'monotonic', side_effect=[0, 61]):
            with self.assertRaises(TimeoutError):
                pods.remote_read(self.pod, timeout=60)
        popen.assert_called_once()
        process.stdin.write.assert_not_called()
        process.kill.assert_called_once()
        process.wait.assert_called_once()


if __name__ == '__main__':
    unittest.main()


class IntakeExitTests(unittest.TestCase):
    """11-17: one transient source error failed the whole intake job twice a day."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.lane = Path(self.tmp.name) / 'lanes/test'
        self.lane.mkdir(parents=True)
        (self.lane / 'INTAKE.toml').write_text('keywords = []\n')

    def run_intake(self, sources):
        args = types.SimpleNamespace(live=True, hits_file=None)
        with patch.object(rh, 'fetch_sources', lambda cfg: iter(sources)), \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()) as err:
            return rh.intake(self.lane, args), err.getvalue()

    def test_one_transient_error_is_a_warning(self):
        rc, err = self.run_intake([('arxiv:a', [], ''), ('github-prs:o/r', [], 'HTTP Error 403: rate limit exceeded')])
        self.assertEqual(rc, 0)
        self.assertIn('intake warning: github-prs:o/r', err)

    def test_reading_nothing_fails(self):
        rc, _ = self.run_intake([('github-prs:o/r', [], 'HTTP Error 403')])
        self.assertEqual(rc, 1)

    def test_the_same_source_failing_three_runs_in_a_row_fails(self):
        bad = [('arxiv:a', [], ''), ('github-prs:o/r', [], 'HTTP Error 403')]
        self.assertEqual(self.run_intake(bad)[0], 0)
        self.assertEqual(self.run_intake(bad)[0], 0)
        rc, err = self.run_intake(bad)
        self.assertEqual(rc, 1)
        self.assertIn('intake error: github-prs:o/r', err)

    def test_github_requests_carry_the_token_in_a_header_only(self):
        seen = {}

        class Opener:
            def open(self, request, timeout=None):
                seen['url'], seen['auth'] = request.full_url, request.get_header('Authorization')
                return io.BytesIO(b'[]')
        with patch.dict('os.environ', {'GITHUB_TOKEN': 'tok123'}), \
                patch.object(rh.urllib.request, 'build_opener', lambda *a: Opener()):
            try:
                rh.get_url('https://api.github.com/repos/o/r/pulls')
            except Exception:
                pass
        self.assertEqual(seen.get('auth'), 'Bearer tok123')
        self.assertNotIn('tok123', seen.get('url', ''))
