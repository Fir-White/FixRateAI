"""Run prompts held apart from the first development cycle."""
import os

import pytest

from tests.agent_reliability_lab.evals.holdout import HOLDOUT
from tests.agent_reliability_lab.evals.test_agent_v3_e2e import lab, test_independent_v3 as execute_case
from tests.backend.test_assistant import assistant_case
from tests.backend.test_management import managed
from tests.backend.test_runtime_integration import runtime


@pytest.mark.skipif(os.environ.get('FIXRATE_AGENT_LIVE') != '1', reason='Requires pinned offline Ollama profile')
@pytest.mark.parametrize('case', HOLDOUT, ids=[case.id for case in HOLDOUT])
def test_holdout(lab, case, caplog):
    execute_case(lab, case, caplog)
