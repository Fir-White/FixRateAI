"""A provider's exhaustion or missing timeout cannot leave a turn awaiting forever."""
import asyncio
import time
from types import SimpleNamespace
import pytest
from app.assistant.orchestrator import InferenceFailure,infer_client
from app.assistant.read_transport import result_summary
from tests.backend.test_runtime_integration import runtime
from tests.backend.test_management import managed
from tests.backend.test_assistant import assistant_case,thread


def test_exhausted_provider_is_a_normal_failure_without_unhandled_future_error():
    async def run():
        errors=[]
        asyncio.get_running_loop().set_exception_handler(lambda loop,context:errors.append(context))
        def exhausted(*args):raise StopIteration('TEST ONLY no more model steps')
        with pytest.raises(InferenceFailure,match='ASSISTANT_PROVIDER_EXHAUSTED'):
            await asyncio.wait_for(infer_client(SimpleNamespace(chat=exhausted),[],object,1,time.monotonic()+1),timeout=2)
        assert not errors
    asyncio.run(run())


def test_provider_without_timeout_is_bounded_by_persisted_turn_deadline():
    async def run():
        def slow(*args):time.sleep(.05);return 'too late'
        with pytest.raises(InferenceFailure,match='ASSISTANT_TIMEOUT'):
            await infer_client(SimpleNamespace(chat=slow),[],object,1,time.monotonic()+.005)
    asyncio.run(run())


def test_expired_deadline_never_starts_another_model_call():
    def unexpected(*args):raise AssertionError('No new inference after expiry')
    with pytest.raises(InferenceFailure,match='ASSISTANT_TIMEOUT'):
        asyncio.run(infer_client(SimpleNamespace(chat=unexpected),[],object,1,time.monotonic()-1))


def test_aggregate_trace_retains_the_actual_cohort_counts():
    summary=result_summary(dict(complete=True,summary=dict(selected_tasks=0,scanned_tasks=4),sections={}))
    assert summary['selected_tasks']==0 and summary['scanned_tasks']==4


def test_exhausted_provider_persists_an_unfinished_goal_instead_of_hanging(assistant_case):
    from tests.backend.test_assistant_orchestrator import Planner,goal,send
    _,app,client,_,_=assistant_case
    app.state.assistant_provider_factory=lambda:Planner([goal('unread','regulations_read')],[])
    try:
        view=send(client,thread(client),'Read the requested regulation; do not change data.')
        turn=view['turns'][-1]
        assert turn['status']=='failed' and turn['error_code']=='ASSISTANT_PROVIDER_EXHAUSTED'
        assert turn['workflow']['outcome']!='completed'
        assert turn['workflow']['goals'][0]['status']=='blocked'
        assert 'Незавершённые пункты' in turn['answer'] and not view['actions']
    finally:del app.state.assistant_provider_factory
