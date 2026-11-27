"""Seeded operation-preserving changes in wording, role and ordering."""
import os

import pytest

from tests.agent_reliability_lab.evals.generated import generate
from tests.agent_reliability_lab.evals.test_agent_v3_e2e import lab, test_independent_v3 as execute_case
from tests.backend.test_assistant import assistant_case
from tests.backend.test_management import managed
from tests.backend.test_runtime_integration import runtime


SEED = int(os.environ.get('FIXRATE_RELIABILITY_SEED', '20261123'))
CASES = tuple(generate(SEED))


@pytest.mark.skipif(os.environ.get('FIXRATE_AGENT_LIVE') != '1', reason='Requires pinned offline Ollama profile')
@pytest.mark.parametrize('case', CASES, ids=[case.id for case in CASES])
def test_generated(lab, case, caplog):
    execute_case(lab, case, caplog)
