"""Hermetic collection and offline tests, including child interpreters.

HOME is replaced before module collection. The original home is never read by the
suite. Socket guards forbid Internet connections while permitting local Unix IPC.
"""
import os
from pathlib import Path
import shlex
import socket
import sys
import tempfile

import pytest

_TEST_HOME = tempfile.TemporaryDirectory(prefix='ai-research-tests-')
os.environ['HOME'] = _TEST_HOME.name
os.environ['XDG_CONFIG_HOME'] = str(Path(_TEST_HOME.name) / '.config')
os.environ['XDG_STATE_HOME'] = str(Path(_TEST_HOME.name) / '.local/state')
os.environ['RH_POD_LANES'] = 'team,theory,orbits,toy-evolution'
os.environ['RH_POLICY_EXCLUDED'] = 'restricted-a,restricted-b'
os.environ['RH_REAP_EXCLUDED'] = 'restricted-a,restricted-b'
for key in ('RH_ROLES_FILE', 'RH_CONTACTS', 'RH_DECIDED_BY', 'CLAUDE_CODE_SESSION_ID', 'RH_EVIDENCE_ROOT',
            'RH_SELECTION_GATE', 'MODEL_OVERRIDES', 'MODEL_REVIEW_ROOT', 'MODEL_DRAFTS_LOG', 'MODEL_STATE', 'MODEL_LEDGER', 'RH_ROOT', 'LAUNCH_SELECTOR', 'LAUNCH_ARTIFACT_DIR', 'LAUNCH_IDEA', 'LAUNCH_IDEA_ROOT',
            'RH_TRANSCRIPTS_ROOT', 'RH_CS_DB_ROOT', 'RH_HARVEST_STATE', 'RH_POD_GATE_CONFIG', 'RH_POD_GATE_AUDIT', 'LAUNCH_MODEL', 'LAUNCH_MODEL_OVERRIDE',
            'RH_OWNER_ALIASES', 'RH_DISK_FLOOR_BYTES', 'RH_ENV_FILE', 'RH_INTAKE_LANES', 'RH_RUNPOD_KEY_FILE', 'RUNPOD_API_KEY',
            'RH_X_ACCOUNT', 'RH_X_GATE', 'RH_X_GATE_LOG', 'RH_X_REPLIED', 'RH_OUTREACH_ROOT',
            'RH_XLINT', 'RH_SIGNATURE_NAMES', 'RH_X_ORIGINALS_PER_DAY', 'RH_X_MIN_GAP_MINUTES',
            'RH_CONTACT_UPDATES'):
    os.environ.pop(key, None)
_RUNTIME = Path(_TEST_HOME.name) / 'runtime'
_RUNTIME.mkdir()
os.environ['RH_ROOT'] = str(_RUNTIME)
os.environ['AGENT_BACKEND'] = 'codex'
# Test drafts live under the system temp dir, which outreach refuses for real drafts.
os.environ['RH_DRAFT_TEMP_OK'] = '1'
FIXTURE = Path(__file__).parent / 'tests/fixtures/check.py'
os.environ['RH_VOICE_COMMAND'] = shlex.join([sys.executable, str(FIXTURE), 'voice'])
os.environ['RH_SCIENCE_CHECK_COMMAND'] = shlex.join([sys.executable, str(FIXTURE), 'science'])


@pytest.fixture(autouse=True)
def no_internet(monkeypatch):
    connect, connect_ex = socket.socket.connect, socket.socket.connect_ex
    def guarded(self, address):
        if self.family in (socket.AF_INET, socket.AF_INET6):
            raise AssertionError('network is disabled in tests')
        return connect(self, address)
    def guarded_ex(self, address):
        if self.family in (socket.AF_INET, socket.AF_INET6):
            raise AssertionError('network is disabled in tests')
        return connect_ex(self, address)
    monkeypatch.setattr(socket.socket, 'connect', guarded)
    monkeypatch.setattr(socket.socket, 'connect_ex', guarded_ex)
