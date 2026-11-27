"""Shared model registry and canonicalizer, extracted from model-roles.py.

Canonical keys retain provider and explicit effort; native CLI spellings are aliases.
"""
import re

MODELS = {'anthropic/claude-opus-5.5': ('claude', 'claude-opus-5-5'),
 'anthropic/claude-fable-5.1': ('claude', 'claude-fable-5-1'),
 'anthropic/claude-fable-5.2': ('claude', 'claude-fable-5-2'),
 'anthropic/claude-sonnet-5.5': ('claude', 'claude-sonnet-5-5'),
 'anthropic/claude-haiku-5.5': ('claude', 'claude-haiku-5-5'),
 'anthropic/claude-opus-4.6': ('claude', 'claude-opus-4-6'),
 'openai/gpt-6.2-sol': ('codex', 'gpt-6.2-sol'),
 'openai/gpt-6.2-astra': ('codex', 'gpt-6.2-astra'),
 'openai/gpt-6.1-sol': ('codex', 'gpt-6.1-sol'),
 'openai/gpt-6-astra': ('codex', 'gpt-6-astra'),
 'openai/gpt-6.1-terra': ('codex', 'gpt-6.1-terra'),
 'openai/gpt-6-luna': ('codex', 'gpt-6-luna'),
 'openai/gpt-5.6-sol': ('codex', 'gpt-5.6-sol'),
 'deepseek/deepseek-v4.1-flash-1017': ('openrouter', 'deepseek/deepseek-v4.1-flash-1017'),
 'z-ai/glm-5.3-flash': ('openrouter', 'z-ai/glm-5.3-flash'),
 'moonshotai/kimi-k3.1-pro': ('openrouter', 'moonshotai/kimi-k3.1-pro'),
 'x-ai/grok-4.6': ('openrouter', 'x-ai/grok-4.6'),
 'google/gemini-4-argon': ('gemini', 'google/gemini-4-argon'),
 'google/gemini-4-carbon': ('gemini', 'google/gemini-4-carbon'),
 'google/gemini-4-hydrogen': ('gemini', 'google/gemini-4-hydrogen'),
 # 11-19: Gemini on the Antigravity subscription (agy). `agy models` on the m5 lists these three tiers.
 'google/gemini-3.8-flash-high': ('agy', 'gemini-3.8-flash-high'),
 'google/gemini-3.8-flash-medium': ('agy', 'gemini-3.8-flash-medium'),
 'google/gemini-3.8-flash-low': ('agy', 'gemini-3.8-flash-low'),
 # 11-19 later: Google AI Pro adds Gemini 4 to agy (Carbon is Ultra-only). Distinct canonical IDs from the
 # Gemini API routes above, whose history stays as it is. Low and medium are both candidates: effort is chosen
 # like everything else, from graded real lane work at each effort (Ricardo 11-19: "Those are synthetic tests.
 # I wouldn't use synthetic tests as the guidance... It's everyday work.").
 'google/gemini-4-carbon-high': ('agy', 'gemini-4-carbon-high'),
 'google/gemini-4-carbon-medium': ('agy', 'gemini-4-carbon-medium'),
 'google/gemini-4-carbon-low': ('agy', 'gemini-4-carbon-low'),
 'google/gemini-4-neon-high': ('agy', 'gemini-4-neon-high'),
 'google/gemini-4-hydrogen-high': ('agy', 'gemini-4-hydrogen-high'),
 'google/gemini-4-neon-medium': ('agy', 'gemini-4-neon-medium'),
 'google/gemini-4-argon-medium': ('agy', 'gemini-4-argon-medium'),
 'google/gemini-4-hydrogen-medium': ('agy', 'gemini-4-hydrogen-medium'),
 'google/gemini-4-neon-low': ('agy', 'gemini-4-neon-low'),
 'google/gemini-4-argon-low': ('agy', 'gemini-4-argon-low'),
 'google/gemini-4-hydrogen-low': ('agy', 'gemini-4-hydrogen-low')}

# Explicit successor -> predecessor pairs for routing evidence and retired launch requests.
INHERITS = {'openai/gpt-6.2-sol': 'openai/gpt-6.1-sol', 'openai/gpt-6.2-astra': 'openai/gpt-6-astra'}
SUPERSEDED = {old: new for new, old in INHERITS.items()}

# bare 'opus': family-alert-watch rows, 11-10..16; 'claude-opus-5': one laptop grades-feed row, 10-28
ALIASES = [('opus[- ]?5[.-]5|^opus$|^claude-opus-5$', 'anthropic/claude-opus-5.5'),
 ('fable[- ]?5[.-]1|fable-5-1', 'anthropic/claude-fable-5.1'),
 ('sonnet[- ]?5[.-]5', 'anthropic/claude-sonnet-5.5'),
 ('haiku[- ]?5[.-]5', 'anthropic/claude-haiku-5.5'),
 ('opus[- ]?4[.-]6', 'anthropic/claude-opus-4.6'),
 ('5\\.6-sol', 'openai/gpt-5.6-sol'),
 ('6\\.1-sol', 'openai/gpt-6.1-sol'),
 ('6[- ]astra', 'openai/gpt-6-astra'),
 ('^sol\\b', 'openai/gpt-6.2-sol'),
 ('astra', 'openai/gpt-6.2-astra'),
 ('terra', 'openai/gpt-6.1-terra'),
 ('luna', 'openai/gpt-6-luna'),
 ('deepseek', 'deepseek/deepseek-v4.1-flash-1017'),
 ('glm', 'z-ai/glm-5.3-flash'),
 ('kimi', 'moonshotai/kimi-k3.1-pro'),
 ('grok[- ]?4\\.6', 'x-ai/grok-4.6'),
 ('argon', 'google/gemini-4-argon'),
 ('carbon', 'google/gemini-4-carbon'),
 ('hydrogen', 'google/gemini-4-hydrogen')]

# Ids that name a surface, not a model, so no row under them can be ranked: void, and not reported as unknown.
# codex-chrome: one laptop grades-feed row (10-28) from Codex driving Chrome; which Codex model ran is not recorded.
VOID_IDS = frozenset(('codex-chrome',))


def canon(s):
    s = (s or "").lower().strip()
    s = re.sub(r"\[(?:1m|context[^]]*)\]$", "", s).strip()
    if s.startswith('anthropic/'):
        s = s.split('/', 1)[1]
    if s.startswith('claude-'):
        s = re.sub(r'-(?:low|medium|high|max|xhigh)$', '', s)
        s = re.sub(r'-(\d+)-(\d+)$', r'-\1.\2', s)
    # Bare Gemini 4 names in driver sessions mean the high subscription tier.
    if s in ('gemini-4-neon', 'gemini-4-hydrogen', 'google/gemini-4-neon'):
        s = s.rsplit('/', 1)[-1] + '-high'
    if s in MODELS:
        return s
    for canonical, (_, native) in MODELS.items():
        if s == native:
            return canonical
    # Versioned native names and canonical provider IDs register their own routes.
    # A bare family name is deliberately insufficient to identify a model version.
    if re.fullmatch(r'claude-[a-z]+-\d+(?:[.-]\d+)+', s):
        canonical = 'anthropic/' + re.sub(r'-(\d+)-(\d+)$', r'-\1.\2', s)
    elif re.fullmatch(r'gpt-\d+(?:\.\d+)?-[a-z0-9.-]+', s):
        canonical = 'openai/' + s
    elif re.fullmatch(r'[a-z][a-z0-9-]*/[a-z][a-z0-9_.-]*', s):
        canonical = s
    else:
        for pat, c in ALIASES:
            if re.search(pat, s):
                return c
        return None
    provider, name = canonical.split('/', 1)
    cli = {'anthropic': 'claude', 'openai': 'codex'}.get(provider, 'openrouter')
    native = re.sub(r'(\d+)\.(\d+)', r'\1-\2', name) if provider == 'anthropic' else name if provider == 'openai' else canonical
    MODELS[canonical] = (cli, native)
    return canonical

