"""Exercise the watcher's CLI with synthetic source responses and fake side effects."""
from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import time

import pytest

TOOL = Path(__file__).resolve().parents[1] / 'tools/x-hot-watch'
NOW = '2026-11-28T15:00:00Z'
FRESH = '2026-11-28T14:53:00Z'
OLD = '2026-11-28T14:44:59Z'
FUTURE = '2026-11-28T15:00:01Z'


def pid(index):
    return str(2125000000000000000 + index)


def post(index, author='GuillaumeAIinSF', created=FRESH, text='A proof in Lean.', kind='post'):
    return dict(post_id=pid(index), author=author, created_at=created,
                url=f'https://x.com/{author}/status/{pid(index)}', text=text, kind=kind)


def pr(number, login='outside-dev'):
    return dict(number=number, author={'login': login}, createdAt=FRESH, title='Adds sample',
                url=f'https://github.com/rpinho/lean-golf/pull/{number}')


def read_rows(path):
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def write_rows(path, *rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(''.join(json.dumps(row) + '\n' for row in rows))


class FakeWatch:
    def __init__(self, root):
        self.root = root
        self.engage = root / 'engage'
        self.engage.mkdir()
        self.state = root / 'state'
        self.drafts = self.engage / 'REPLY_DRAFTS.md'
        self.trace = root / 'calls.jsonl'
        fake = root / 'fake'
        fake.write_text(f'#!{sys.executable}\n' + '''
import json, os, sys
from pathlib import Path
root = Path(os.environ["X_TEST_ROOT"])
if Path(sys.argv[0]).name == "pgrep":
    mode, args = "pgrep", sys.argv[1:]
else:
    mode, args = sys.argv[1], sys.argv[2:]
with (root / "calls.jsonl").open("a") as stream:
    stream.write(json.dumps([mode, *args]) + "\\n")
if mode == "pgrep":
    sys.exit(0 if (root / "busy").exists() else 1)
if mode in ("grok", "gh"):
    response = root / mode
    if not response.exists():
        sys.exit(7)
    print(response.read_text())
''')
        fake.chmod(0o755)
        (root / 'pgrep').symlink_to(fake)
        self.env = dict(os.environ, X_HOT_PRIORITY='nobody', X_TEST_ROOT=str(root), X_ENGAGE_DIR=str(self.engage),
                        X_HOT_STATE=str(self.state), PATH=str(root) + os.pathsep + os.environ['PATH'])
        for mode in ('grok', 'gh', 'tell', 'notify', 'review'):
            self.env['X_HOT_' + mode.upper()] = shlex.quote(str(fake)) + ' ' + mode
        self.grok([])
        self.gh([])

    def grok(self, rows, deco='plain'):
        output = json.dumps(rows)
        if deco == 'fenced':
            output = 'Found posts:\n\x60\x60\x60json\n' + output + '\n\x60\x60\x60\n'
        if deco == 'prose':
            output = 'Results follow [not JSON]. ' + output + ' End of results.'
        (self.root / 'grok').write_text(output)

    def gh(self, rows):
        (self.root / 'gh').write_text(json.dumps(rows))

    def run(self, *args, now=NOW):
        done = subprocess.run([sys.executable, str(TOOL), '--now', now, *args],
                              env=self.env, capture_output=True, text=True, timeout=10)
        assert done.returncode == 0, done.stderr
        return done

    def calls(self, mode):
        return [row[1:] for row in read_rows(self.trace) if row[0] == mode]

    def review_call(self, index):
        for _ in range(100):
            if self.calls('review'):
                break
            time.sleep(0.01)
        assert self.calls('review') == [['--hot', pid(index)]]

    def run_log(self):
        return read_rows(self.state / 'run.jsonl')[-1]


@pytest.fixture
def watch(tmp_path):
    return FakeWatch(tmp_path)


@pytest.mark.parametrize('deco', ['fenced', 'prose'])
def test_single_grok_query_and_fresh_post_queues_once(watch, deco):
    targets = ['Alpha', 'beta', 'ALPHA', 'Rob1Ham', *[f'target{i}' for i in range(1, 32)]]
    (watch.engage / 'TARGETS.md').write_text(
        '# REPLY-EARLY 30\n- Math (adds: listedFirst): ' + ', '.join(targets)
        + '\nSearch URLs (latest):\n- A: https://x.com/search?q=%28from%3AlistedFirst%29\n'
        + '# Another section\n- Outside: otherHandle\n')
    text = 'New proof in Lean\n## Heading inside the post\nStatus: ready'
    watch.grok([post(1, 'ListedFirst', text=text)], deco)
    watch.run()
    watch.review_call(1)
    [[*opts, query]] = watch.calls('grok')
    assert opts == ['--host', 'm5', '--timeout', '120']
    assert '2026-11-28T14:45:00Z through ' + NOW in query
    assert query.count('@Rob1Ham') == 1 and '@Alpha' in query and '@ALPHA' not in query
    assert '@target26' in query and '@target27' not in query and '@otherHandle' not in query
    assert 'mentions of @rpinho_sci' in query and '@exitcode0dev' in query
    assert watch.calls('pgrep') == [['-f', 'x-reply-review']]
    assert watch.drafts.read_text() == (
        f'\n\n## HOT {NOW} @ListedFirst https://x.com/ListedFirst/status/{pid(1)}\n'
        'Status: hot\n\n> New proof in Lean\n> ## Heading inside the post\n> Status: ready\n')
    assert read_rows(watch.state / 'hot.jsonl') == [
        dict(post_id=pid(1), author='ListedFirst', url=post(1, 'ListedFirst')['url'], queued_utc=NOW)]
    watch.run(now='2026-11-28T15:05:00Z')   # still inside the 15-min window
    assert watch.run_log()['decisions'][0]['reason'] == 'duplicate'
    assert watch.drafts.read_text().count('## HOT ') == 1
    watch.review_call(1)
    assert watch.calls('notify') == []


def test_invalid_irrelevant_seen_and_recent_author_rows_are_skipped(watch):
    (watch.engage / 'replied.json').write_text(json.dumps([pid(4)]))
    write_rows(watch.engage / 'log.jsonl',
               dict(action='like', target_url=post(5)['url']),
               dict(action='reply', utc='2026-11-27T16:00:00Z', in_reply_to=post(90, 'mAjDiFlOw')['url'],
                    target_url=post(91, 'rpinho_sci')['url']),
               dict(action='reply', utc='2026-11-27T16:00:00Z', target_url=post(92, 'rob1ham')['url'],
                    reply_url=post(93, 'rpinho_sci')['url']))
    watch.drafts.write_text(f'### Ready {post(6)["url"]}\nStatus: ready\n')
    write_rows(watch.state / 'hot.jsonl', dict(post_id=pid(7), author='EXITCODE0DEV', queued_utc=FRESH))
    invalid_time = post(10)
    del invalid_time['created_at']
    watch.grok([post(1, created=OLD), post(2, created=FUTURE), post(3, text='A nice walk.'),
                post(4), post(5), post(6), post(7), post(8, author='Majdiflow'),
                post(9, author='exitcode0dev'), invalid_time, dict(post(11), post_id='123'),
                post(12, author='Rob1Ham'), post(13, created='yesterday'), post(14, created='2026-11-28T14:53:00'),
                post(15, author='unlisted'), dict(post(16), url=post(17)['url']), None])
    watch.run()
    assert [row['reason'] for row in watch.run_log()['decisions']] == [
        'stale', 'future', 'irrelevant', 'duplicate', 'duplicate', 'duplicate', 'duplicate',
        'author cap', 'author cap', 'invalid created_at', 'invalid post_id', 'author cap',
        'invalid created_at', 'invalid created_at', 'outside watchlist', 'invalid permalink', 'invalid row']
    assert '## HOT' not in watch.drafts.read_text()
    assert not watch.calls('pgrep') and not watch.calls('review') and not watch.calls('notify')


def test_24_hours_and_freshness_window_are_inclusive(watch):
    started = datetime.fromisoformat(NOW.replace('Z', '+00:00'))
    at_cap = (started - timedelta(hours=24)).isoformat()
    beyond_cap = (started - timedelta(hours=24, seconds=1)).isoformat()
    write_rows(watch.engage / 'log.jsonl',
               dict(action='reply', utc=at_cap, target_url=post(90, 'Rob1Ham')['url']),
               dict(action='reply', utc=beyond_cap, target_url=post(91, 'Majdiflow')['url']))
    watch.grok([post(1, 'Rob1Ham', NOW), post(2, 'Majdiflow', '2026-11-28T14:40:00Z'),
                post(3, 'exitcode0dev', '2026-11-28T14:39:59Z')])
    watch.run('--window-min', '20')
    assert [(row['decision'], row.get('reason')) for row in watch.run_log()['decisions']] == [
        ('skip', 'author cap'), ('queue', None), ('skip', 'stale')]
    watch.review_call(2)


def test_twentieth_trigger_is_last_for_the_eastern_day(watch):
    # 01:30Z on Nov 29 is still Nov 28 ET.
    now = '2026-11-29T01:30:00Z'
    write_rows(watch.state / 'hot.jsonl', *[
        dict(post_id=pid(100 + n), author=f'other{n}', queued_utc=NOW) for n in range(19)])
    write_rows(watch.state / 'review.jsonl', *[
        dict(post_id=pid(100 + n), utc=NOW) for n in range(19)])
    watch.grok([post(1, created=now), post(2, 'Rob1Ham', now)])
    watch.run(now=now)
    watch.review_call(1)
    assert [row['decision'] for row in watch.run_log()['decisions']] == ['queue', 'skip']
    assert watch.run_log()['decisions'][1]['reason'] == 'ET day cap'
    assert len(read_rows(watch.state / 'review.jsonl')) == 20

    next_day = '2026-11-29T13:00:00Z'
    watch.grok([post(3, created=next_day), post(2, 'Rob1Ham', next_day)])
    watch.run(now=next_day)
    assert [row.get('reason') for row in watch.run_log()['decisions']] == ['author cap', None]
    assert len(read_rows(watch.state / 'review.jsonl')) == 21


def test_busy_reviewer_leaves_block_then_next_tick_can_resume(watch):
    busy = watch.root / 'busy'
    busy.touch()
    watch.grok([post(1)])
    watch.run()
    assert 'Status: hot' in watch.drafts.read_text()
    assert watch.run_log()['review'] == 'busy'
    assert not watch.calls('review')
    busy.unlink()
    watch.grok([])
    watch.run(now='2026-11-28T15:15:00Z')
    watch.review_call(1)
    assert watch.drafts.read_text().count('## HOT ') == 1


def test_replies_push_once_unless_already_in_mentions(watch):
    mention = post(1, author='stranger', kind='reply_to_us')
    seen = post(2, author='someoneelse', kind='reply_to_us')
    own = post(3, author='rpinho_sci', kind='reply_to_us')
    write_rows(watch.engage / 'mentions.jsonl', dict(id=seen['post_id'], at=FRESH))
    watch.grok([mention, seen, own, mention])
    watch.run()
    assert [row.get('reason') for row in watch.run_log()['decisions']] == [
        None, 'mention already seen', 'own post', 'mention already seen']
    watch.run(now='2026-11-28T15:15:00Z')
    [[message, title, priority]] = watch.calls('notify')
    assert mention['url'] in message and title == 'X reply or mention' and priority == '3'
    assert not watch.drafts.exists() and not watch.calls('review')


def test_lean_golf_prs_seed_and_only_new_outside_pr_pushes(watch):
    watch.gh([pr(1), pr(2, 'rpinho')])
    watch.run()
    assert watch.calls('notify') == []
    assert watch.calls('gh') == [['pr', 'list', '-R', 'rpinho/lean-golf', '--state', 'all', '--limit', '30',
                                 '--json', 'number,author,createdAt,url,title']]
    watch.gh([pr(3), pr(1), pr(4, 'RPinho'), pr(3), dict(pr(5), author=None)])
    watch.run()
    assert [row.get('reason') for row in watch.run_log()['decisions']] == [
        None, 'PR already seen', 'own PR', 'PR already seen', 'unknown PR author']
    watch.run()
    [[message, title, priority]] = watch.calls('notify')
    assert pr(3)['url'] in message and title == 'New Lean Golf PR' and priority == '3'
    assert not watch.calls('review')


def test_empty_first_pr_poll_seeds_and_gh_failure_does_not_stop_x(watch):
    (watch.root / 'gh').unlink()
    watch.grok([post(1)])
    watch.run()
    watch.review_call(1)
    assert watch.run_log()['X_HOT_GH'] == 'exit 7'
    assert not (watch.state / 'prs.jsonl').exists()
    watch.grok([])
    watch.gh([])
    watch.run()
    watch.gh([pr(1)])
    watch.run()
    assert len(watch.calls('notify')) == 1


def test_grok_failure_alerts_general_once_per_streak_and_prs_continue(watch):
    watch.run()
    (watch.root / 'grok').unlink()
    watch.gh([pr(1)])
    for streak in range(1, 6):
        watch.run()
        assert watch.run_log()['grok_streak'] == streak
        assert watch.run_log()['X_HOT_GROK'] == 'exit 7'
        assert len(watch.calls('tell')) == int(streak >= 4)
    assert watch.calls('tell')[0][0] == 'fyi'
    assert len(watch.calls('notify')) == 1  # the PR is independent
    watch.grok([])
    watch.run()
    assert watch.run_log()['grok_streak'] == 0
    (watch.root / 'grok').write_text('malformed response')
    for _ in range(4):
        watch.run()
    assert len(watch.calls('tell')) == 2


@pytest.mark.parametrize('outside', ['2026-11-28T12:59:59Z', '2026-11-29T04:00:00Z', '2026-07-01T11:59:59Z'])
def test_outside_hours_is_silent(watch, outside):
    done = watch.run(now=outside)
    assert not done.stdout and not done.stderr and not watch.trace.exists() and not watch.state.exists()


@pytest.mark.parametrize('start', ['2026-11-28T13:00:00Z', '2026-07-01T12:00:00Z'])
def test_start_includes_eight_am_with_eastern_dst(watch, start):
    watch.run(now=start)
    assert len(watch.calls('grok')) == 1


def test_dry_run_writes_only_the_run_log_and_prints_decisions(watch):
    watch.run()  # seed PRs before testing dry-run output
    watch.grok([post(1), post(2, author='exitcode0dev', text='hello'),
                post(3, author='someone', kind='reply_to_us')])
    watch.gh([pr(9)])
    before = {p: p.read_bytes() for p in [*watch.state.iterdir(), *watch.engage.iterdir()]}
    done = watch.run('--dry-run')
    assert done.stdout.splitlines() == [
        f'x {pid(1)} queue', f'x {pid(2)} skip irrelevant', f'x {pid(3)} push', 'pr 9 push']
    assert set(watch.state.iterdir()) | set(watch.engage.iterdir()) == set(before)
    assert all(p.read_bytes() == old for p, old in before.items() if p.name != 'run.jsonl')
    assert watch.run_log()['dry_run']
    assert not watch.calls('notify') and not watch.calls('pgrep') and not watch.calls('review') and not watch.calls('tell')
    watch.run()
    watch.review_call(1)
    assert len(watch.calls('notify')) == 2


def test_dry_run_does_not_advance_the_live_grok_failure_streak(watch):
    (watch.root / 'grok').unlink()
    for _ in range(3):
        watch.run()
    watch.run('--dry-run')
    assert watch.run_log()['grok_streak'] == 4 and not watch.calls('tell')
    watch.run()
    assert watch.run_log()['grok_streak'] == 4 and len(watch.calls('tell')) == 1


def test_priority_account_new_post_skips_the_author_cap_but_not_the_post_dedupe(watch):
    """11-28 (general 1128k): a new post by a priority account gets a fast reply even if we replied to them today."""
    watch.env.pop('X_HOT_PRIORITY')
    write_rows(watch.engage / 'log.jsonl',
               dict(action='reply', utc=NOW, target_url=post(90, 'GuillaumeAIinSF')['url']),
               dict(action='reply', utc=NOW, target_url=post(91, 'conjectures_io')['url']))
    (watch.engage / 'replied.json').write_text(json.dumps([pid(2)]))
    watch.grok([post(1), post(2), post(3, 'conjectures_io')])
    watch.run()
    assert [(row['decision'], row.get('reason')) for row in watch.run_log()['decisions']][:2] == [
        ('queue', None), ('skip', 'duplicate')]
    assert '## HOT' in watch.drafts.read_text()
