"""ALG07/08 reproducible synthetic scenarios; no database or real accuracy claims."""
from copy import deepcopy
from datetime import date, datetime
import json
import logging
from pathlib import Path
import sys
import time
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'backend'),str(ROOT)]

from app.schemas.maintenance import ForecastSnapshot, Uncertainty
from app.scheduling.schemas import SchedulingBinding
from app.orchestrator.forecast import compare_forecasts, forecast_result
from ml_service.app.forecast.synthetic import compute_snapshot_hash
from scripts.verification_paths import prepare_run


def inputs(origin="synthetic_demo"):
    example=deepcopy(json.loads((ROOT/'tests/fixtures/scheduling/examples.json').read_text(encoding='utf-8'))['request'])
    row=example['bindings'][0]
    for name in ('binding','equipment','operation','rule'): row[name]['data_origin']=origin
    row['rule'].update(calendar_unit='month',interval=1,anchor_date='2026-11-10',allowed_lead_days=9,source_text='DEMO: ежемесячно от 10 ноября')
    example['site']['data_origin']=origin
    item=SchedulingBinding.model_validate_json(json.dumps(row))
    payload=dict(schema_version='maintenance-0.1',data_origin=origin,snapshot_id=str(uuid4()),content_sha256='0'*64,
        binding_id=str(item.binding.binding_id),binding_revision=1,site=example['site'],equipment=row['equipment'],
        operation=row['operation'],rule=row['rule'],as_of='2026-11-01T08:00:00+05:00',horizon_end='2027-11-01',
        earliest_date='2026-11-01',mandatory_due_date='2026-11-10',runtime_due_at_hours=None,accepted_events=[],
        runtime_reading=None,feature_schema_version='rf-features-v1')
    snapshot=ForecastSnapshot.model_validate_json(json.dumps(payload))
    return snapshot.model_copy(update={'content_sha256':compute_snapshot_hash(json.loads(snapshot.model_dump_json()))}),item


def ai_value(snapshot, day='2026-11-10', *, calibrated=False):
    value=forecast_result(snapshot,uuid4(),'ai',status='ok',day=date.fromisoformat(day),explanation='Синтетический ответ провайдера',model_ref='synthetic_demo:fixture-v1')
    uncertainty=Uncertainty(kind='deterministic' if calibrated else 'tree_dispersion',lower_date=value.recommended_date,
        upper_date=value.recommended_date,calibrated=calibrated,note='Эталонный сценарий; качество реальной модели не измеряется')
    return value.model_copy(update={'model_ref':'synthetic_demo:fixture-v1','uncertainty':uncertainty})


def scenarios():
    return [
        ('same_date',lambda s: ai_value(s),'selected','2026-11-10'),
        ('demo_ai_earlier',lambda s: ai_value(s,'2026-11-05'),'selected','2026-11-05'),
        ('ai_after_deadline',lambda s: ai_value(s,'2026-11-12'),'fallback','2026-11-10'),
        ('ai_before_window',lambda s: ai_value(s,'2026-10-30'),'fallback','2026-11-10'),
        ('model_missing',lambda s: forecast_result(s,uuid4(),'ai',status='unavailable',error='MODEL_NOT_READY',explanation='Модель отсутствует'),'fallback','2026-11-10'),
        ('invalid_json',lambda s: '{broken','fallback','2026-11-10'),
        ('provider_exception',lambda s: (_ for _ in ()).throw(RuntimeError('fixture')),'fallback','2026-11-10'),
        ('foreign_snapshot',lambda s: ai_value(s).model_copy(update={'snapshot_id':uuid4()}),'fallback','2026-11-10'),
        ('timeout',lambda s: (time.sleep(0.04),ai_value(s))[1],'fallback','2026-11-10'),
    ]


def verify():
    rows=[]
    for name,provider,status,selected in scenarios():
        snapshot,item=inputs()
        started=time.perf_counter()
        algorithmic,ai,decision=compare_forecasts(snapshot,item,provider,timeout_seconds=0.005 if name=='timeout' else 1)
        assert decision.status==status and str(decision.selected_date)==selected,(name,decision)
        assert decision.selected_date<=snapshot.mandatory_due_date
        rows.append(dict(case=name,algorithmic=str(algorithmic.recommended_date),ai=str(ai.recommended_date) if ai.recommended_date else None,
            ai_status=ai.status,error=ai.error_code,status=decision.status,selected=str(decision.selected_date),reason=decision.reasons[0],
            milliseconds=round((time.perf_counter()-started)*1000,2)))
    # Real-origin input does not acquire permission for an uncalibrated early move.
    snapshot,item=inputs('customer')
    algorithmic,ai,decision=compare_forecasts(snapshot,item,lambda s: ai_value(s,'2026-11-05'))
    assert decision.status=='fallback' and decision.selected_date==date(2026,11,10)
    rows.append(dict(case='customer_no_early_evidence',algorithmic=str(algorithmic.recommended_date),ai=str(ai.recommended_date),
        ai_status=ai.status,error=ai.error_code,status=decision.status,selected=str(decision.selected_date),reason=decision.reasons[0],milliseconds=0))
    for name in ('missing_rule','overdue'):
        snapshot,item=inputs()
        if name=='missing_rule':
            rule=item.rule.model_copy(update={'confirmed':False})
            item=item.model_copy(update={'rule':rule})
            snapshot=snapshot.model_copy(update={'rule':rule})
        else:
            snapshot=snapshot.model_copy(update={'as_of':datetime.fromisoformat('2026-11-11T08:00:00+05:00')})
        snapshot=snapshot.model_copy(update={'content_sha256':compute_snapshot_hash(json.loads(snapshot.model_dump_json()))})
        algorithmic,ai,decision=compare_forecasts(snapshot,item,lambda s:ai_value(s))
        assert decision.selected_date is None and decision.status==('needs_input' if name=='missing_rule' else 'manual_review')
        rows.append(dict(case=name,algorithmic=str(algorithmic.recommended_date) if algorithmic.recommended_date else None,
            ai=str(ai.recommended_date),ai_status=ai.status,error=ai.error_code,status=decision.status,selected=None,
            reason=decision.reasons[0],milliseconds=0))
    return rows


def write_reports(output):
    rows=verify()
    output.mkdir(parents=True,exist_ok=True)
    header='# ALG07: сравнение методов\n\nВсе случаи — исполняемые синтетические fixtures, а не метрики модели на данных заказчика.\n'
    header+='Источник нормативной даты — настоящий ALG02. Провайдеры AI здесь задают граничные ответы для проверки политики.\n\n'
    lines=['| Сценарий | Регламент | AI | Итог | Статус |','|---|---|---|---|---|']
    for row in rows: lines.append(f"| {row['case']} | {row['algorithmic'] or 'нет данных'} | {row['ai'] or row['error']} | {row['selected'] or 'ручная проверка / нужны данные'} | {row['status']} |")
    comparable=[r for r in rows if r['ai'] is not None and r['algorithmic'] is not None]
    disagreements=sum(r['ai']!=r['algorithmic'] for r in comparable)
    header+='\n'.join(lines)+f'\n\nНесогласие дат среди сравнимых предложений в этом специально подобранном наборе: {disagreements}/{len(comparable)}. Случаи без даты не входят в знаменатель. Нарушений обязательного срока: 0. Это не частота ошибок в эксплуатации и не точность прогнозирования.\n'
    header+='\nПри неподтверждённом правиле оркестратор возвращает needs_input; прошедший срок требует manual_review. Два результата и итог не подменяют друг друга.\n'
    (output/'prediction_comparison.md').write_text(header,encoding='utf-8')
    failures=[r for r in rows if r['error']]
    (output/'orchestration_resilience.md').write_text('# ALG08: устойчивость\n\nКоманда: `.venv/Scripts/python.exe -B scripts/verify_orchestration.py`.\n\n'
        +'Проверены некорректный JSON, исключение провайдера, чужой snapshot, отсутствие модели и таймаут. Во всех случаях пригодный регламент остаётся доступен.\n\n'
        +'\n'.join(f"- {r['case']}: {r['error']}, {r['status']}, {r['milliseconds']} мс." for r in failures)
        +'\n\nВыполнение AI ограничено двумя daemon workers; истёкший запрос не сохраняет поздний ответ. Session БД в поток не передаётся. Повторы и транзакционные ошибки проверяются отдельно реальными HTTP/PostgreSQL-тестами и браузерным прогоном scripts/verify.py --browser.\n',encoding='utf-8')
    (output/'orchestration_cases.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
    return rows


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,help='New reports directory; defaults to reports/verification/<run-id>')
    args=parser.parse_args()
    output,logs=prepare_run(args.output,prefix='orchestration')
    logging.basicConfig(filename=logs/'orchestration.log',encoding='utf-8',level=logging.INFO,
                        format='%(levelname)s %(name)s %(message)s',force=True)
    result=write_reports(output)
    message=f'{len(result)} orchestration scenarios passed; reports: {output}'
    logging.info(message)
    print(message)
