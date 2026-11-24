"""The monthly-demand placeholder is private and must not invent plan data."""
from contextlib import closing

from fastapi.testclient import TestClient

from app.assistant.tools import TOOLS
from tests.backend.test_runtime_integration import login, runtime


URL = '/api/v1/demand/monthly'


def test_monthly_demand_requires_session(runtime):
    _, app = runtime
    assert TestClient(app, raise_server_exceptions=False).get(URL).status_code == 401


def test_monthly_demand_distinguishes_no_source_from_denied_access(runtime):
    _, app = runtime
    with closing(login(app, 'executor')) as worker, closing(login(app, 'chief_engineer')) as chief:
        assert worker.get(URL).status_code == 403
        assert chief.get(URL).status_code == 404


def test_material_tools_have_one_registration_each():
    names = ['consumption_record', 'consumptions_read', 'consumption_correct', 'demand_monthly']
    assert {name: sum(tool.name == name for tool in TOOLS) for name in names} == dict.fromkeys(names, 1)
