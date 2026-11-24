"""Compare a model-driven dialogue with the saved v3 replay on the same demo site.

The models see identical prompts and projected, authenticated read tools. The
cloud variant is restricted to a SQL-verified synthetic fixture. Credentials,
arbitrary URLs, mutation calls and raw backend responses are never model input.
"""
import argparse
from functools import partial
import hashlib
import json
from pathlib import Path
from time import monotonic
from typing import Literal

from dotenv import dotenv_values
import httpx
import psycopg
from pydantic import BaseModel, ConfigDict, Field

from ml_service.app.providers.aitunnel import AITunnelClient, AITunnelConfig, AITunnelFailure
from ml_service.app.providers.ollama import OllamaClient, OllamaConfig, OllamaFailure


TOOLS = {
    'maintenance_catalog_read': ('/api/v1/assistant/workspace/maintenance-catalog',
        'Виды ТО, коды и названия конкретных операций по действующим регламентам текущего объекта. '
        'Отфильтруй нужный вид из результатов. Параметры limit, offset.'),
    'tasks_find': ('/api/v1/assistant/workspace/tasks',
        'Наряды с текущим состоянием, датами и точным total. period: all, upcoming, overdue, undated. '
        'maintenance_only=true выбирает наряды с регламентом. unfinished_only=true ограничивает незавершёнными. '
        'starts_on и ends_on ограничивают обе границы по местной дате планового начала или срока, YYYY-MM-DD. '
        'Параметры limit до 100, offset, state, q.'),
    'equipment_find': ('/api/v1/assistant/workspace/equipment',
        'Найти единицы оборудования по инвентарному коду или названию. Параметры q, asset_code, offset.'),
}
INSTRUCTIONS = (
    'Ты помощник FixRate. Ответь на текущий вопрос в рамках диалога. История включает все прежние запросы, '
    'ответы и результаты чтения. Инструменты выполняются сервером только на текущем объекте и с текущей ролью. '
    'Если для ответа нужны факты объекта, запроси подходящий инструмент или используй сохранённое чтение, которое '
    'подтверждает именно запрошенные факты в данном снимке. Не угадывай факты. После чтения сформулируй ответ '
    'по-русски и укажи источник человеческим названием. Отличай виды ТО, операции, единицы оборудования и наряды. '
    'Для дней перечисли каждый выбранный день и относящиеся к нему наряды, включая их коды. '
    'Если данные о сроке или состоянии отсутствуют, скажи об этом. Для вызова выбери tool и arguments_json, '
    'а answer оставь пустым. Для готового ответа tool=reply и arguments_json="{}".'
)


class Step(BaseModel):
    model_config = ConfigDict(extra='forbid')
    tool: Literal['maintenance_catalog_read', 'tasks_find', 'equipment_find', 'reply']
    arguments_json: str = Field(max_length=2000)
    answer: str = Field(max_length=12000)


def read_fixture(credentials, database, conversation_id):
    """Bind the replay to the actual site's SQL facts and verify demo provenance."""
    with psycopg.connect(host='127.0.0.1', port=52426, user='postgres', password=credentials['postgres'],
                         dbname=database, row_factory=psycopg.rows.dict_row) as connection:
        connection.execute('SET TRANSACTION READ ONLY')
        scope = connection.execute('''SELECT c.site_id,s.timezone,c.role FROM assistant_conversations c
            JOIN sites s USING(site_id) WHERE c.conversation_id=%s''', (conversation_id,)).fetchone()
        if not scope or scope['role'] != 'chief_engineer':
            raise ValueError('Expected the chief engineer demo conversation')
        site, zone = scope['site_id'], scope['timezone']
        origins = connection.execute('''SELECT bool_and(is_demo) AS synthetic FROM (
            SELECT r.data_origin IS NOT DISTINCT FROM 'synthetic_demo' AS is_demo
            FROM maintenance_rules r WHERE r.site_id=%s AND r.publication_status='published'
            UNION ALL SELECT (e.properties->>'data_origin') IS NOT DISTINCT FROM 'synthetic_demo'
            FROM equipment e WHERE e.site_id=%s
            UNION ALL SELECT COALESCE(o.operation_snapshot->>'data_origin',r.data_origin) IS NOT DISTINCT FROM 'synthetic_demo'
            FROM work_orders o LEFT JOIN maintenance_rules r USING (site_id,maintenance_rule_id)
            WHERE o.site_id=%s) AS provenance''', (site, site, site)).fetchone()
        ongoing = connection.execute('''SELECT o.work_order_id::text AS id, LEFT(o.work_order_id::text,8) AS code,
            COALESCE(o.operation_snapshot->>'title',op.title) AS title,
            (COALESCE(o.planned_start_at,o.regulatory_deadline_at) AT TIME ZONE %s)::date AS day, o.status
            FROM work_orders o JOIN maintenance_rules r USING (site_id,maintenance_rule_id)
            JOIN operation_templates op USING(site_id,operation_template_id)
            WHERE o.site_id=%s AND o.status IN ('draft','assigned','clarification','rework','in_progress','in_review')
            ORDER BY o.work_order_id''', (zone, site)).fetchall()
        operations = connection.execute('''SELECT DISTINCT m.name AS kind,
            COALESCE(NULLIF(r.schedule_parameters->'operation_metadata'->>'code',''),o.code) AS code,
            COALESCE(NULLIF(r.schedule_parameters->'operation_metadata'->>'title',''),o.title) AS title
            FROM rule_equipment b JOIN equipment e USING(site_id,equipment_id)
            JOIN maintenance_rules r USING(site_id,maintenance_rule_id)
            JOIN regulation_editions ed USING(site_id,regulation_edition_id)
            JOIN operation_templates o USING(site_id,operation_template_id)
            JOIN maintenance_types m USING(maintenance_type_id)
            WHERE b.site_id=%s AND e.status<>'retired' AND o.is_active AND r.publication_status='published'
              AND ed.is_approved AND COALESCE(r.schedule_parameters->>'superseded_binding','') IN ('','false')
              AND CURRENT_DATE BETWEEN b.valid_from AND COALESCE(b.valid_to,'infinity')
              AND CURRENT_DATE BETWEEN r.active_from AND COALESCE(r.active_until,'infinity')
              AND CURRENT_DATE BETWEEN ed.effective_from AND COALESCE(ed.effective_to,'infinity')
            ORDER BY m.name,code,title''', (site,)).fetchall()
    return dict(timezone=zone, synthetic=origins['synthetic'] is True, ongoing=ongoing, operations=operations)


def project(name, result):
    if name == 'maintenance_catalog_read':
        items = [{k: row[k] for k in ('type_name', 'code', 'title')} for row in result['items']]
        return dict(types=result['types'], items=items, date=result['date'], total=result['total'], offset=result['offset'])
    if name == 'equipment_find':
        return dict(total=result['total'], offset=result['offset'])
    keys = ('code', 'title', 'scheduledStart', 'mandatoryDueDate', 'regulatoryDeadlineAt')
    items = [{k: row.get(k) for k in keys} for row in result['items']]
    return {**{k: result[k] for k in ('total', 'filters', 'timezone', 'checked_at', 'period', 'offset')}, 'items': items}


def tool_call(client, name, arguments, authorized):
    if name not in authorized:
        return {'status': 'unauthorized'}
    if not isinstance(arguments, dict) or any(isinstance(value, (dict, list)) for value in arguments.values()):
        return {'status': 'invalid_arguments'}
    if name in ('tasks_find', 'maintenance_catalog_read'):
        limit = arguments.get('limit', 50)
        if type(limit) is not int or not 1 <= limit <= 100:
            return {'status': 'invalid_limit'}
        arguments = {'limit': limit, **arguments}
    response = client.get(TOOLS[name][0], params=arguments)
    return project(name, response.json()) if response.is_success else {'status': 'http_error', 'http_status': response.status_code}


def inference_factory(options):
    if options.variant == 'b' or options.ollama_model:
        cfg = OllamaConfig.from_environment(dict(OLLAMA_CHAT_BASE_URL='http://127.0.0.1:11434',
            OLLAMA_CHAT_MODEL=options.ollama_model or 'qwen3.5:4b-q4_K_M',
            OLLAMA_CHAT_DIGEST=options.ollama_digest or 'sha256:d8b0f5e9760cd1682034f292d7ef72ec46f432149be0df7574bf2d6e92e38c04',
            OLLAMA_CHAT_NUM_CTX=str(options.num_ctx)))
        return partial(OllamaClient, cfg)
    values = dotenv_values(options.provider_config, interpolate=False)
    settings = {key: values[key] for key in ('AI_TUNNEL_API_KEY', 'AITUNNEL_API_KEY', 'AITUNNEL_BASE_URL') if values.get(key)}
    settings.update(AITUNNEL_CHAT_MODEL=options.model, AITUNNEL_TIMEOUT_SECONDS='100')
    return partial(AITunnelClient, AITunnelConfig.from_environment('chat', settings))


def execute(questions, client, available, factory, output, fixture_digest):
    history = []
    output.write_text(json.dumps(dict(fixture=fixture_digest, turns=[])), encoding='utf-8')
    for question in questions:
        provider = factory()
        evidence = []
        started = monotonic()
        answer, status = '', 'step_budget'
        for _ in range(5):
            previous = [{key: row[key] for key in ('question', 'answer', 'evidence')} for row in history]
            payload = dict(question=question, previous=previous, evidence=evidence,
                           tools={tool: TOOLS[tool][1] for tool in available}, local_date='2026-11-23')
            try:
                step = provider.chat([dict(role='system', content=INSTRUCTIONS),
                    dict(role='user', content=json.dumps(payload, ensure_ascii=False))], Step, 3500)
            except (AITunnelFailure, OllamaFailure) as exc:
                status = str(exc)
                break
            if step.tool == 'reply':
                answer, status = step.answer.strip(), 'completed' if step.answer.strip() else 'empty_reply'
                break
            try:
                arguments = json.loads(step.arguments_json)
            except ValueError:
                arguments = None
            value = tool_call(client, step.tool, arguments, available)
            evidence.append(dict(tool=step.tool, arguments=arguments, value=value))
        result = dict(question=question, answer=answer, status=status, evidence=evidence,
                      model=provider.response_model or provider.config.model_ref, seconds=round(monotonic()-started, 3),
                      usage=getattr(provider, 'metrics', getattr(provider, 'response_diagnostics', [])))
        history.append(result)
        output.write_text(json.dumps(dict(fixture=fixture_digest, turns=history), ensure_ascii=False, indent=2), encoding='utf-8')
        print(len(history), status, [item['tool'] for item in evidence], flush=True)
        if not evidence and status.startswith('AITUNNEL_'):
            return


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('variant', choices=('b', 'c'))
    parser.add_argument('--baseline', required=True, type=Path)
    parser.add_argument('--accounts', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--provider-config', type=Path)
    parser.add_argument('--model', default='deepseek-v4-flash')
    parser.add_argument('--ollama-model')
    parser.add_argument('--ollama-digest')
    parser.add_argument('--num-ctx', type=int, default=32768)
    options = parser.parse_args()
    if options.variant == 'c' and not (options.provider_config or options.ollama_model):
        parser.error('variant c requires --provider-config or --ollama-model')
    if options.ollama_model and not options.ollama_digest:
        parser.error('--ollama-model requires a pinned --ollama-digest')
    credentials = json.loads(options.accounts.read_text(encoding='utf-8-sig'))
    baseline = json.loads(options.baseline.read_text(encoding='utf-8'))
    questions = [row['content'] for row in baseline[:8]]
    with psycopg.connect(host='127.0.0.1', port=52426, user='postgres', password=credentials['postgres'],
                         dbname='fixrate_manual_v3_20261123') as connection:
        identity = connection.execute('SELECT conversation_id FROM assistant_turns WHERE turn_id=%s',
                                      (baseline[0]['turn_id'],)).fetchone()[0]
    fixture = read_fixture(credentials, 'fixrate_manual_v3_20261123', identity)
    fixture_json = json.dumps(fixture, default=str, ensure_ascii=False, sort_keys=True)
    digest = hashlib.sha256(fixture_json.encode()).hexdigest()
    options.out.with_suffix('.oracle.json').write_text(fixture_json, encoding='utf-8')
    if options.variant == 'c' and not options.ollama_model and not fixture['synthetic']:
        raise SystemExit('Cloud experiment requires all selected site data to be tagged synthetic')
    with httpx.Client(base_url='http://127.0.0.1:4251', timeout=12, trust_env=False) as client:
        client.post('/api/v1/auth/login', json=dict(email='chief@fixrate.local', password=credentials['password'])).raise_for_status()
        response = client.get('/api/v1/assistant/capabilities')
        response.raise_for_status()
        reads = {item['name'] for item in response.json()['tools']['assistant'] if not item['requires_confirmation']}
        if reads.intersection(TOOLS) != TOOLS.keys():
            raise SystemExit('Not all experiment reads are enabled for this role')
        execute(questions, client, list(TOOLS), inference_factory(options), options.out, digest)


if __name__ == '__main__':
    main()
