"""AN06 real cloud evaluation. Never writes fictitious execution into the live DB."""
from pathlib import Path
import argparse,json,sys,hashlib,copy
from datetime import datetime,timezone
from uuid import uuid4
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'backend'),str(ROOT)]

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--cloud',action='store_true',help='Call configured paid AI Tunnel model');parser.add_argument('--output',type=Path);parser.add_argument('--cases',nargs='+',help='Explicit subset of AN06 case IDs');args=parser.parse_args()
    from app.schemas.maintenance import PhotoReviewRequest
    from app.integration.photo_evidence import classify_evidence
    from ml_service.app.cv.quality import ImageQualityGuard
    from dotenv import load_dotenv
    load_dotenv(ROOT/'.env',override=False)
    source=ROOT/'docs/analysis/nastya-2026-11-04/source'
    manifest=json.loads((source/'tests/fixtures/evidence_manifest.json').read_text(encoding='utf-8'))
    policy=json.loads((ROOT/'docs/analysis/photo_review_policy.json').read_text(encoding='utf-8'))
    catalog=json.loads((ROOT/'docs/analysis/checklists/catalog.json').read_text(encoding='utf-8'))
    example=next(e['payload'] for e in json.loads((ROOT/'contracts/examples/maintenance.json').read_text(encoding='utf-8'))['examples'] if e['name']=='photo_review_request')
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    output=args.output or ROOT/f'reports/analyst-photos/{stamp}';output.mkdir(parents=True,exist_ok=False)
    results=[];guard=ImageQualityGuard()
    selected=manifest['evidence_cases']
    if args.cases:
        known={case['case_id'] for case in selected}
        if set(args.cases)-known:parser.error('Unknown AN06 case ID')
        selected=[case for case in selected if case['case_id'] in args.cases]
    for case in selected:
        data=copy.deepcopy(example)
        from ml_service.app.cv.aitunnel import PROMPT_VERSION
        data['prompt_set_version']=PROMPT_VERSION if args.cloud else 'analyst-technical-precheck-v1'
        profile=next(p for p in catalog['profiles'] if p['operation_code']==case['operation_id'])
        # This is explicitly a photo evaluation fixture, never an approved real regulation.
        op=data['operation'];op.update(code=profile['operation_code'],title=profile['title'],maintenance_type=profile['maintenance_type'],status='draft',
            instructions='Проверка видимых признаков по профилю аналитика. Нормативы и методика не утверждены. Не подтверждай нормальность показаний, скрытые работы и безопасность.',
            crew_size=profile['required_workers_from_source'],raw_norm_value=None,norm_unit='unconfirmed',planning_duration_minutes=None,duration_basis=None,qualification_ids=[],source_ref='analyst-photo-evaluation:unexecuted-fixture')
        visible=next(i for i in profile['items'] if i['setting']['photo_required'])['setting']
        op['checklist'][0].update(text=visible['text'],visual_verifiability=visible['visual_verifiability'])
        data['report']['narrative']='Искусственный тест входных фотографий AN06. Реальное выполнение ТО не подтверждается.'
        store={};quality=[]
        for photo,phase in zip(data['photos'],('before','after')):
            photo['phase']=phase;photo['photo_id']=str(uuid4());photo['captured_at']=None
            blob=(source/case['photo_'+phase+'_path']).read_bytes();store[__import__('uuid').UUID(photo['photo_id'])]=blob
            with Image.open(__import__('io').BytesIO(blob)) as image:photo['width'],photo['height']=image.size
            photo['file_size_bytes']=len(blob);photo['original_sha256']=hashlib.sha256(blob).hexdigest();photo['uploaded_at']=datetime.now(timezone.utc).isoformat()
            q=guard.assess_bytes(blob);quality.append(dict(phase=phase,acceptable=q.is_acceptable,issue=q.issue,laplacian=q.laplacian_var,brightness=q.mean_brightness))
        data['report']['photo_ids']=[p['photo_id'] for p in data['photos']]
        request=PhotoReviewRequest.model_validate_json(json.dumps(data))
        item=dict(case=case['case_id'],operation=case['operation_id'],expected=case['expected_ai_verdict'],quality=quality,source_execution_status=False)
        if args.cloud:
            from ml_service.app.cv.aitunnel import review_cloud_photos,AITunnelVisionClient
            from ml_service.app.providers.aitunnel import AITunnelConfig
            client=AITunnelVisionClient(AITunnelConfig.from_environment("vision"))
            result=review_cloud_photos(request,store.__getitem__,client=client,comparability_confirmed=lambda b,a:False)
            item["provider_diagnostics"]=client.response_diagnostics
            actual=classify_evidence(result,manual_evidence_required=True)
            item.update(actual=actual,result_status=result.status,error_code=result.error_code,model=result.model_ref,
                        verdict='SKIP' if result.status in ('unavailable','failed') else 'PASS' if actual in policy['cases'][case['case_id']]['allowed_classifications'] else 'FAIL',
                        source_expectation='MATCH' if actual==item['expected'] else 'DIFF',reviewed_expectations=policy['cases'][case['case_id']]['allowed_classifications'])
            (output/(case['case_id']+'.json')).write_text(result.model_dump_json(indent=2),encoding='utf-8')
        else:item.update(verdict='SKIP',reason='Only technical precheck; no model invocation')
        results.append(item);print(case['case_id'],item['verdict'],item.get('actual','no model'),flush=True)
        (output/'results.json').write_text(json.dumps(dict(scope='AN06 photo-provider evaluation; not end-to-end maintenance acceptance',cases=results),ensure_ascii=False,indent=2),encoding='utf-8')
    lines=['# AN06: фактическая проверка фотографий','',f'Запуск: {stamp}. Облачный вызов: {args.cloud}.','',
        'Это проверка фотоинструмента на исходных учебных изображениях. Реальное ТО, нормативы, числовая точность OCR и лицензии фотографий не подтверждаются. CASE-05 синтетически изменён, идентичность узла CASE-06 не доказана. Итоговая приёмка не выполняется.','',
        '| Кейс | Операция | Ожидание источника | Фактически | Сверка с источником | Проверенная политика |','|---|---|---|---|---|---|']
    lines += [f"| {i['case']} | {i['operation']} | {i['expected']} | {i.get('actual','—')} | {i.get('source_expectation','—')} | {i['verdict']} |" for i in results]
    lines+=['','PASS относится к проверенной политике photo_review_policy.json: неподтверждённые или разные объекты не принимаются. Расхождения с исходным manifest не скрыты; MATCH/DIFF показаны отдельно. SKIP при отказе модели не является PASS.','','Полный сквозной прогон шести реальных операций: BLOCKED — методики и нормативы не утверждены заказчиком.']
    (output/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8');print(output)
    if any(i['verdict']=='FAIL' for i in results):return 1
    return 2 if args.cloud and any(i['verdict']=='SKIP' for i in results) else 0
if __name__=='__main__':raise SystemExit(main())
