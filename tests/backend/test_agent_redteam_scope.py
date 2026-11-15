"""Independent expected cohorts for natural-language analysis filters; real agent API and DB."""
from datetime import timedelta
from uuid import uuid4
import pytest
from sqlalchemy import text
from tests.backend.test_runtime_integration import runtime
from tests.backend.test_management import managed
from tests.backend.test_assistant import assistant_case,B,thread
from tests.backend.test_assistant_task_analytics import add_orders,TODAY,clock

CASES=(
    ('tomorrow','Проанализируй все незавершённые задания на завтра.',1),
    ('january','Проанализируй все незавершённые задания за январь 2027 года.',1),
    ('february','Проанализируй все незавершённые задания за февраль 2027 года.',1),
    ('exact','Проанализируй все незавершённые задания на 2027-02-10.',1),
    ('review','Проанализируй незавершённые задания, только на приёмке.',1),
    ('pending','Проанализируй незавершённые задания, только ожидающие исполнения.',3),
    ('manual','Проанализируй все незавершённые задания, только созданные вручную.',4),
    ('scheduled','Проанализируй все незавершённые задания, только из календаря.',0),
)

@pytest.mark.parametrize('identity,question,expected',CASES,ids=[c[0] for c in CASES])
def test_analysis_does_not_silently_drop_user_scope(assistant_case,clock,identity,question,expected):
    engine,app,client,_,ids=assistant_case
    from datetime import datetime,timezone
    add_orders(assistant_case,[dict(deadline=TODAY+timedelta(days=1)),
        dict(deadline=datetime(2027,1,10,10,tzinfo=timezone.utc)),
        dict(deadline=datetime(2027,2,10,10,tzinfo=timezone.utc)),
        dict(status='in_review',deadline=TODAY-timedelta(days=1))])
    class NoInference:
        def chat(self,*args):raise AssertionError('A typed cohort must be selected before response rendering')
    app.state.assistant_provider_factory=NoInference
    try:
        chat=thread(client)
        response=client.post(B+f'/conversations/{chat}/messages',json=dict(content=question,idempotency_key=str(uuid4())))
        assert response.status_code==202,response.text
        view=client.get(B+'/conversations/'+chat).json();turn=view['turns'][-1]
        assert turn['status']=='completed',turn
        reads=[row for row in turn['trace'] if row['tool']=='tasks_analyze' and row['status']=='completed']
        assert reads and reads[0]['result']['selected_tasks']==expected,turn
        assert not view['actions']
        with engine.connect() as db:assert db.scalar(text('SELECT count(*) FROM work_orders WHERE site_id=:site'),dict(site=ids['site']))==4
    finally:del app.state.assistant_provider_factory


@pytest.mark.parametrize('question',[
    'Проанализируй все завершённые задания.',
    'Проанализируй все отменённые задания.',
    'Проверь все принятые наряды.',
    'Покажи все задания в статусе completed.',
    'Покажи все задания в статусе cancelled.',
])
def test_unfinished_handler_does_not_capture_terminal_state_requests(question):
    from app.assistant.task_report import requested
    assert not requested(question)

@pytest.mark.parametrize('question',[
    'Проанализируй все незавершённые задания за январь.',
    'Проанализируй все незавершённые задания за 2027 год.',
    'Проанализируй все незавершённые задания на следующую неделю.',
    'Проанализируй все незавершённые задания на 2027-02-31.',
    'Проанализируй все незавершённые задания с 2027-02-20 по 2027-01-01.',
    'Проанализируй все незавершённые задания только для оборудования RT-PUMP.',
])
def test_unsupported_or_invalid_scope_never_expands_to_everything(question):
    from app.assistant.analysis_scope import selectors
    with pytest.raises(ValueError):selectors(question,dict(local_date='2026-11-15'))

def test_classification_request_does_not_filter_everything_to_today():
    from app.assistant.analysis_scope import selectors
    assert selectors('Проанализируй все незавершённые задания. Раздели на просроченные, на сегодня и будущие.',dict(local_date='2026-11-15'))=={}
