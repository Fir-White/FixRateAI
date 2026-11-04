"""The actual workers offered by demo assignment must be able to execute jobs."""
from contextlib import closing
import os
from fastapi.testclient import TestClient
import pytest
from tests.backend.test_runtime_integration import runtime,PREFIX


@pytest.mark.parametrize('number',[1,2,3])
def test_seeded_assignment_workers_have_real_executor_sessions(runtime,number):
    _,app=runtime
    with closing(TestClient(app)) as client:
        response=client.post('/api/v1/auth/login',json=dict(
            email=f'fixrate-assignment-{number}@example.test',password=os.environ['FIXRATE_TEST_PASSWORD']))
        assert response.status_code==200,response.text
        assert response.json()['profile']['role']=='executor'
        assert client.get(PREFIX+'/ui/tasks').status_code==200
        assert client.get(PREFIX+'/management/workforce').status_code==403
