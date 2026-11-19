"""The KB ranking is a generated block, and the rest of the page may not cite a bench as guidance."""
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
from pathlib import Path


def load(name):
    spec = spec_from_loader(name.replace('-', '_'), SourceFileLoader(name.replace('-', '_'), str(Path(__file__).with_name(name))))
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


render, lint = load('render-kb-block'), load('kb-rank-lint')
BOARD = """| Role | Model | Routing order | Everyday passed | Everyday n | Bench passed | Date |
|---|---|---:|---:|---:|---:|---|
| batch | gpt-6.2-sol | 1 | 1.0 | inherited from gpt-6.1-sol (n=25); own n=0 | - | 2026-11-19 |
| batch | claude-sonnet-5-5 | 2 | n<5 | 0 | - | 2026-11-19 |
| batch | gpt-6.1-sol | - | 1.0 | 25 | - | 2026-11-19 |
| batch | gpt-6.1-sol | 1 | 0.9 | 20 | - | 2026-11-18 |
| review | claude-opus-5-5 | 1 | n<5 | 0 | 1.0 | 2026-11-19 |
"""


def test_the_block_has_everyday_first_and_the_bench_apart_from_the_newest_day(tmp_path):
    out = render.block(BOARD)
    assert out.startswith(render.BEGIN) and out.rstrip().endswith(render.END)
    assert '| Role | # | Model | Everyday passed | Everyday n | Bench passed |' in out
    assert '| batch | 1 | gpt-6.2-sol | 1.0 | inherited from gpt-6.1-sol (n=25); own n=0 | - |' in out
    assert '| batch | - | gpt-6.1-sol | 1.0 | 25 | - |' in out and '0.9' not in out
    assert '| review | 1 | claude-opus-5-5 | n<5 | 0 | 1.0 |' in out
    board = tmp_path / 'LEADERBOARD.md'
    board.write_text(BOARD)
    page = tmp_path / 'page.md'
    page.write_text('# Page\n\nintro\n' + render.BEGIN + '\nhand edit\n' + render.END + '\n\nnotes\n')
    assert render.main([str(page), '--leaderboard', str(board)]) == 0
    text = page.read_text()
    assert 'hand edit' not in text and text.startswith('# Page\n\nintro\n') and text.endswith('\n\nnotes\n')
    (tmp_path / 'bare.md').write_text('# No markers\n')
    assert render.main([str(tmp_path / 'bare.md'), '--leaderboard', str(board)]) == 2
    assert lint.findings(text) == []


def test_the_lint_flags_bench_guidance_outside_the_block_only():
    page = '\n'.join([
        render.BEGIN, '| 1 | some model | bench 100% | rank by bench |', render.END,
        'Switch Gemini 4 to low effort: the bench showed it loops at high.',
        'Prefer Sol over Astra on planted claims.',
        'A bench is only a second check and never sets a rank.',
        'Terminal-Bench reports Sol leads; @arena ranks Opus first.',
        'Both 6.2 models answered a smoke test on Codex before the switch.',
    ])
    assert [n for n, _ in lint.findings(page)] == [4, 5, 8]
