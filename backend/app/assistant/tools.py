"""Explicit capabilities over the real API; never accept a model-selected URL."""
from dataclasses import dataclass
from contextvars import ContextVar
import hashlib,json,re
from urllib.parse import quote,urlencode
from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.routing import APIRoute
import httpx
from pydantic import ValidationError
from app.schemas.assistant import ResultView
from .attachments import SCOPE,COOKIE_EFFECTS,HUMAN_SECRET,owned,content

ALL=('director','chief_engineer','engineer','dispatcher','admin','executor')
PLAN=('chief_engineer','engineer','dispatcher','admin')
EDIT=('chief_engineer','dispatcher','admin')
OPERATE=('chief_engineer','engineer','dispatcher')
P='/api/v1/maintenance'
EXPECTED_PRINCIPAL=ContextVar('assistant_expected_principal',default=None)

@dataclass(frozen=True)
class Tool:
    name:str
    title:str
    method:str
    path:str
    roles:tuple=ALL
    mode:str='read'
    agents:tuple=('assistant','planner')
    before:str|None=None
    secrets:tuple=()
    optional_secrets:tuple=()

# New capabilities must be reviewed here and tested through their existing endpoint.
# Even an apparently read-only POST may save forecasts or start work: default is proposal.
TOOLS=(
 Tool('chat_models','Доступные локальные и облачные модели чата','GET','/api/v1/assistant/models',ALL),
 Tool('chat_model_preference','Мой сохранённый выбор модели чата','GET','/api/v1/assistant/model-preference',ALL),
 Tool('chat_model_select','Выбрать мою модель чата для следующих сообщений','POST','/api/v1/assistant/model-preference',ALL,'write',before='chat_model_preference'),
 Tool('tasks_analyze','Полный серверный анализ незавершённых заданий: сроки, нагрузка, бизнес-дубли и единицы норм','GET','/api/v1/assistant/workspace/task-analysis',agents=('assistant','planner','photo')),
 Tool('draft_changes','Фактические отличия двух версий черновика','GET','/api/v1/assistant/workspace/draft-changes',(*PLAN,'director')),
 Tool('drafts_find','Все доступные черновики текущего объекта из регламентов и каталогов','GET','/api/v1/assistant/workspace/drafts',(*PLAN,'director')),
 Tool('planning_context','Проверенные обязанности, регламенты, исходные пробелы и политика выбранного периода','GET','/api/v1/assistant/workspace/planning-context',(*PLAN,'director')),
 Tool('inventory_read','Все доступные здания, оборудование, число операций ТО и пробелы подготовки','GET','/api/v1/assistant/workspace/inventory',agents=('assistant','planner','photo')),
 Tool('attachment_read','Прочитать лист и строки прикреплённого Excel без импорта','GET','/api/v1/assistant/conversations/{identity}/attachments/{attachment_id}/content',agents=('assistant','planner','photo')),
 Tool('equipment_list','Найти оборудование объекта','GET',P+'/equipment',agents=('assistant','planner','photo')),
 Tool('equipment_read','Карточка оборудования','GET',P+'/equipment/{equipment_id}',agents=('assistant','planner','photo')),
 Tool('catalog_read','Системы и типы оборудования','GET',P+'/management/catalog',(*PLAN,'director')),
 Tool('equipment_create','Добавить оборудование','POST',P+'/equipment',EDIT,'write'),
 Tool('equipment_edit','Изменить оборудование','PATCH',P+'/equipment/{equipment_id}',EDIT,'write',before='equipment_read'),
 Tool('equipment_retire','Вывести оборудование из эксплуатации','DELETE',P+'/equipment/{equipment_id}',EDIT,'write',before='equipment_read'),
 Tool('regulations_read','Регламенты и чек-листы оборудования','GET',P+'/equipment/{equipment_id}/service-configurations',agents=('assistant','planner','photo')),
 Tool('calendar_evidence','Рассчитать календарную периодичность по сохранённому регламенту','GET','/api/v1/assistant/workspace/equipment/{equipment_id}/calendar-evidence',agents=('assistant','planner','photo')),
 Tool('equipment_service_history','Фактическая история оборудования за период по отчётам и приёмке','GET','/api/v1/assistant/workspace/equipment/{equipment_id}/history',agents=('assistant','planner','photo')),
 Tool('workbook_readiness','Проверить исходный XLSX для расчёта трудозатрат и численности без выдуманных нормативов','GET','/api/v1/assistant/workspace/workbook-readiness',agents=('assistant','planner','photo')),
 Tool('regulation_create','Добавить конфигурацию обслуживания','POST',P+'/equipment/{equipment_id}/service-configurations',('chief_engineer','admin'),'write'),
 Tool('regulation_edit','Изменить конфигурацию обслуживания','PUT',P+'/equipment/{equipment_id}/service-configurations/{binding_id}',('chief_engineer','admin'),'write',before='regulations_read'),
 Tool('tasks_list','Задания текущего объекта и пользователя','GET',P+'/ui/tasks',agents=('assistant','planner','photo')),
 Tool('tasks_find','Поиск заданий по статусу, названию и ближайшей дате; история','GET','/api/v1/assistant/workspace/tasks',agents=('assistant','planner','photo')),
 Tool('equipment_find','Поиск оборудования по всему реестру','GET','/api/v1/assistant/workspace/equipment',agents=('assistant','planner','photo')),
 Tool('staff_find','Поиск сотрудников по имени и email','GET','/api/v1/assistant/workspace/staff',(*PLAN,'director')),
 Tool('staff_read','Подробные сведения о сотруднике','GET','/api/v1/assistant/workspace/staff/{user_id}',(*PLAN,'director')),
 Tool('task_read','Задание, инструкции и состояние отчёта','GET',P+'/ui/tasks/{task_id}',agents=('assistant','planner','photo')),
 Tool('calendar_read','Календарь работ','GET',P+'/ui/calendar',(*OPERATE,'director','executor')),
 Tool('assignment_context','Сотрудники и условия назначения','GET',P+'/ui/tasks/{task_id}/assignment-context',OPERATE),
 Tool('assignment_prepare','Проверить назначение конкретных сотрудников на задание','POST','/api/v1/assistant/workspace/tasks/{task_id}/prepare-assignment',OPERATE),
 Tool('assignment_preview','Проверить вариант назначения','POST',P+'/tasks/{task_id}/assignment-preview',OPERATE),
 Tool('task_assign','Назначить бригаду и время','POST',P+'/tasks/{task_id}/assign',OPERATE,'write',before='task_read'),
 Tool('task_cancel','Отменить задание с причиной','POST',P+'/tasks/{task_id}/cancel',OPERATE,'write',before='task_read'),
 Tool('task_start','Начать своё назначенное задание','POST',P+'/tasks/{task_id}/start',('executor',),'write',before='task_read'),
 Tool('report_save','Сохранить фактический отчёт','PUT',P+'/tasks/{task_id}/report',('executor',),'write',before='task_read'),
 Tool('consumption_record','Записать фактический расход материала в свою попытку','POST',P+'/tasks/{task_id}/consumptions',('executor',),'write',before='task_read'),
 Tool('consumptions_read','Прочитать фактический расход наряда и попытки','GET',P+'/tasks/{task_id}/consumptions',ALL,before='task_read'),
 Tool('consumption_correct','Исправить принятый факт расхода с причиной','POST',P+'/consumptions/{consumption_id}/correction',('chief_engineer',),'write',before='consumptions_read'),
 Tool('report_submit','Передать свой отчёт на проверку','POST',P+'/tasks/{task_id}/submit',('executor',),'write',before='task_read'),
 Tool('report_review','Принять отчёт или вернуть с причиной','POST',P+'/tasks/{task_id}/review',('chief_engineer',),'write',before='task_read'),
 Tool('photo_review','Проанализировать сохранённые фотографии отчёта','POST',P+'/tasks/{task_id}/photo-review',('engineer','chief_engineer'),'write',('assistant','photo'),'task_read',optional_secrets=('api_key',)),
 Tool('forecast_run','Рассчитать и сохранить прогноз задания','POST',P+'/tasks/{task_id}/forecast',OPERATE,'write',before='task_read',optional_secrets=('api_key',)),
 Tool('workforce_read','Команда, смены и квалификации','GET',P+'/management/workforce',(*PLAN,'director')),
 Tool('catalogs_list','Сохранённые Excel-каталоги','GET',P+'/catalog-imports',(*PLAN,'director')),
 Tool('portfolio_list','Сохранённые общие планы','GET',P+'/portfolio-plans',(*PLAN,'director')),
 Tool('portfolio_preview','Рассчитать общий состав без записи','POST',P+'/portfolio-plans/preview',PLAN),
 Tool('portfolio_save','Сохранить рассчитанный общий план','POST',P+'/portfolio-plans',EDIT,'write'),
 Tool('draft_list','Планы из каталога','GET',P+'/draft-plans',(*PLAN,'director')),
 Tool('draft_read','Выбранная версия и сводка плана','GET',P+'/draft-plans/{identity}',(*PLAN,'director')),
 Tool('draft_occurrences','Страница работ выбранной версии','GET',P+'/draft-plans/{identity}/occurrences',(*PLAN,'director')),
 Tool('draft_policy','Параметры версии плана','GET',P+'/draft-plans/{identity}/policy',(*PLAN,'director')),
 Tool('draft_load','Проверить нагрузку одной версии','POST',P+'/draft-plans/{identity}/load-preview',PLAN),
 Tool('draft_policy_edit','Изменить параметры новой версией','POST',P+'/draft-plans/{identity}/policy',EDIT,'write',before='draft_read'),
 Tool('draft_place','Разместить или закрепить сегмент','POST',P+'/draft-plans/{identity}/placements',EDIT,'write',before='draft_read'),
 Tool('draft_undo_preview','Возможность отмены собственного изменения','GET',P+'/draft-plans/{identity}/undo',EDIT),
 Tool('draft_undo','Отменить своё изменение новой версией','POST',P+'/draft-plans/{identity}/undo',EDIT,'write',before='draft_read'),
 Tool('catalog_read_saved','Сведения о сохранённом Excel','GET',P+'/catalog-imports/{identity}',(*PLAN,'director')),
 Tool('catalog_operations','Страница исходных операций Excel','GET',P+'/catalog-imports/{identity}/operations',(*PLAN,'director')),
 Tool('draft_preview','Рассчитать состав из подготовленных строк Excel','POST',P+'/draft-plans/preview',PLAN),
 Tool('draft_save','Сохранить рассчитанный план из Excel','POST',P+'/draft-plans',EDIT,'write'),
 Tool('draft_segments','Сегменты выбранной работы','GET',P+'/draft-plans/{identity}/occurrences/{occurrence_id}/segments',(*PLAN,'director')),
 Tool('draft_versions','История версий выбранного плана','GET',P+'/draft-plans/{identity}/versions',(*PLAN,'director')),
 Tool('draft_split','Изменить части работы новой версией','POST',P+'/draft-plans/{identity}/segments',EDIT,'write',before='draft_read'),
 Tool('draft_validate','Проверить допустимость версии без изменения','POST',P+'/draft-plans/{identity}/validate',PLAN),
 Tool('optimization_start','Запустить расчёт вариантов распределения','POST',P+'/draft-plans/{identity}/optimization-runs',EDIT,'write',before='draft_read'),
 Tool('optimization_list','Расчёты вариантов выбранного плана','GET',P+'/draft-plans/{identity}/optimization-runs',(*PLAN,'director')),
 Tool('optimization_read','Состояние и итоги расчёта','GET',P+'/optimization-runs/{run_id}',(*PLAN,'director')),
 Tool('optimization_placements','Размещения рассчитанного варианта','GET',P+'/optimization-runs/{run_id}/placements',(*PLAN,'director')),
 Tool('optimization_apply','Применить рассчитанный вариант новой версией','POST',P+'/optimization-runs/{run_id}/apply',EDIT,'write',before='optimization_read'),
 Tool('optimization_cancel','Остановить расчёт','POST',P+'/optimization-runs/{run_id}/cancel',EDIT,'write',before='optimization_read'),
 Tool('publication_regulations','Утверждённые инструкции для выпуска общего плана','GET',P+'/draft-plans/{identity}/publication-regulations',(*PLAN,'director')),
 Tool('publication_profiles','Шаблоны инструкций для выпуска каталога','GET',P+'/draft-plans/{identity}/publication-profiles',(*PLAN,'director')),
 Tool('publication_prepare','Подготовить предложение о выпуске','POST',P+'/draft-plans/{identity}/publication-proposals',EDIT,'write',before='draft_read'),
 Tool('publication_list','Согласования выбранного плана','GET',P+'/draft-plans/{identity}/publication-proposals',(*PLAN,'director')),
 Tool('publication_read','Точный состав предложения о выпуске','GET',P+'/publication-proposals/{identity}',(*PLAN,'director')),
 Tool('publication_changes','Страница изменений выпуска','GET',P+'/publication-proposals/{identity}/changes',(*PLAN,'director')),
 Tool('publication_approve','Утвердить точное предложение о выпуске','POST',P+'/publication-proposals/{identity}/approve',('chief_engineer',),'write',before='publication_read'),
 Tool('publication_reject','Отклонить предложение о выпуске','POST',P+'/publication-proposals/{identity}/reject',('chief_engineer',),'write',before='publication_read'),
 Tool('publication_publish','Выпустить утверждённый план в реальные задания','POST',P+'/publication-proposals/{identity}/publish',('chief_engineer',),'write',before='publication_read'),
)

from .capabilities import extra_tools
TOOLS=(*TOOLS,*extra_tools(Tool,P,ALL,PLAN,EDIT,OPERATE))

def available(app,role,agent='assistant'):
    routes={(r.path,m):r for r in app.routes if isinstance(r,APIRoute) for m in r.methods}
    return {t.name:t for t in TOOLS if role in t.roles and agent in t.agents and (t.path,t.method) in routes}

def route_for(app,tool):
    return next(r for r in app.routes if isinstance(r,APIRoute) and r.path==tool.path and tool.method in r.methods)

def multipart(app,tool):
    body=app.openapi()['paths'][tool.path][tool.method.lower()].get('requestBody',{})
    return 'multipart/form-data' in body.get('content',{}) or 'application/x-www-form-urlencoded' in body.get('content',{})

def file_fields(app,tool):
    if not multipart(app,tool):return set()
    return {f.name for f in route_for(app,tool).dependant.body_params if f.field_info.__class__.__name__=='File'}

def catalog(app,role,agent):
    result=[]
    for tool in available(app,role,agent).values():
        entry=dict(name=tool.name,title=tool.title,requires_confirmation=tool.mode=='write')
        if tool.mode=='write':
            body=describe(app,tool)['inputSchema'].get('properties',{}).get('body',{})
            entry['body_fields']=list(body.get('properties',{}))
        result.append(entry)
    return result

def describe(app,tool):
    operation=app.openapi()['paths'][tool.path][tool.method.lower()]
    components=app.openapi().get('components',{}).get('schemas',{})
    def expand(value,seen=()):
        if isinstance(value,list):return [expand(v,seen) for v in value]
        if not isinstance(value,dict):return value
        if '$ref' in value:
            name=value['$ref'].split('/')[-1]
            return {} if name in seen else expand(components[name],(*seen,name))
        return {k:expand(v,seen) for k,v in value.items()}
    props={};required=[]
    if tool.mode=='read':props['view']=ResultView.model_json_schema()
    for kind in ('path','query'):
        fields={p['name']:expand(p['schema']) for p in operation.get('parameters',[]) if p['in']==kind}
        if kind=='query' and 'limit' in fields:fields['limit'].update(default=25,maximum=25)
        needed=[p['name'] for p in operation.get('parameters',[]) if p['in']==kind and p.get('required')]
        props[kind]=dict(type='object',properties=fields,additionalProperties=False,required=needed)
        if needed:required.append(kind)
    body=operation.get('requestBody')
    if body:
        media=next(iter(body['content']))
        props['body']=expand(body['content'][media]['schema'])
        if tool.name=='component_reading':
            from app.schemas.registry import UsageReading
            props['body']['properties']['payload']=UsageReading.model_json_schema()
        for name in file_fields(app,tool):
            props['body']['properties'][name]=dict(type='string',format='uuid',description='ID уже прикреплённого файла из контекста диалога; не путь и не URL')
        for name in (*tool.secrets,*tool.optional_secrets):
            props['body']['properties'][name]=dict(type='string',const=HUMAN_SECRET,description='Пользователь введёт секрет только в карточке подтверждения. Никогда не запрашивать его в тексте чата.')
            props['body']['required']=[k for k in props['body'].get('required',[]) if k!=name]
        if body.get('required'):required.append('body')
    return dict(name=tool.name,title=tool.title,description=tool.title+(' — создаёт предложение; подтверждает только пользователь' if tool.mode=='write' else ''),
        inputSchema=dict(type='object',properties=props,additionalProperties=False,required=required),
        annotations=dict(readOnlyHint=tool.mode=='read',destructiveHint=tool.mode=='write',idempotentHint=tool.mode=='read',openWorldHint=False))

def validate_arguments(app,tool,arguments):
    if not isinstance(arguments,dict):raise HTTPException(422,'Аргументы должны быть объектом с разделами path, query и body')
    unknown=set(arguments)-{'path','query','body','view'}
    if unknown:raise HTTPException(422,'Неизвестные разделы аргументов: '+', '.join(sorted(str(x)[:80] for x in unknown)[:10])+'. Используйте только path, query, body и view.')
    route=route_for(app,tool);result={}
    if 'view' in arguments:
        if tool.mode!='read':raise HTTPException(422,'Просмотр результата доступен только инструментам чтения')
        try:result['view']=ResultView.model_validate(arguments['view']).model_dump(mode='json')
        except ValidationError as exc:
            issues=[dict(field='view.'+'.'.join(map(str,e['loc'])),type=e['type']) for e in exc.errors(include_input=False,include_url=False)]
            raise HTTPException(422,dict(code='INVALID_VIEW',issues=issues)) from None
    for kind,fields in (('path',route.dependant.path_params),('query',route.dependant.query_params)):
        values=arguments.get(kind,{})
        if not isinstance(values,dict):raise HTTPException(422,'Раздел '+kind+' должен быть объектом')
        unknown=set(values)-{f.name for f in fields}
        if unknown:raise HTTPException(422,'Неизвестные параметры '+kind+': '+', '.join(sorted(str(x)[:80] for x in unknown)[:10])+'. Допустимые: '+(', '.join(f.name for f in fields) or 'нет'))
        result[kind]={}
        for field in fields:
            if field.name not in values:
                if field.field_info.is_required():raise HTTPException(422,'Нужен параметр '+field.name)
                if kind=='query' and field.name=='limit':result[kind][field.name]=25
                continue
            validated,errors=field.validate(values[field.name],{},loc=(kind,field.name))
            if errors:raise HTTPException(422,'Проверьте параметр '+field.name)
            result[kind][field.name]=jsonable_encoder(validated)
            if kind=='query' and field.name=='limit':result[kind][field.name]=min(result[kind][field.name],25)
    if route.body_field:
        raw=arguments.get('body')
        if isinstance(raw,dict):raw={**raw,**{key:HUMAN_SECRET for key in (*tool.secrets,*tool.optional_secrets) if key in tool.secrets or raw.get(key) is not None}}
        if tool.name=='component_reading' and isinstance(raw,dict) and isinstance(raw.get('payload'),dict):
            from app.schemas.registry import UsageReading
            try:raw={**raw,'payload':UsageReading.model_validate_json(json.dumps(raw['payload'])).model_dump_json()}
            except ValidationError:raise HTTPException(422,'Проверьте дату, ревизию, наработку и примечание показания') from None
        if multipart(app,tool):
            fields=route.dependant.body_params;files=file_fields(app,tool)
            if not isinstance(raw,dict) or set(raw)-{f.name for f in fields}:raise HTTPException(422,'Проверьте поля формы инструмента')
            body={}
            for field in fields:
                if field.name not in raw:
                    if field.field_info.is_required():raise HTTPException(422,'Нужно поле '+field.name)
                    continue
                if field.name in files:
                    if raw[field.name] is None and field.field_info.is_required():raise HTTPException(422,'Нужно вложение '+field.name)
                    try:body[field.name]=str(__import__('uuid').UUID(str(raw[field.name]))) if raw[field.name] is not None else None
                    except ValueError:raise HTTPException(422,'Для файла нужен ID прикреплённого вложения') from None
                else:
                    val,errors=field.validate(raw[field.name],{},loc=('body',field.name))
                    if errors:raise HTTPException(422,'Проверьте поле '+field.name)
                    body[field.name]=jsonable_encoder(val)
            result['body']=body
        else:
            body,errors=route.body_field.validate(raw,{},loc=('body',))
            if errors:
                # Pydantic's full errors include raw input/ctx. Return only
                # bounded field locations and error types, never body values.
                issues=[dict(field='.'.join(str(p)[:80] for p in e.get('loc',())[:6]),type=e.get('type','invalid')) for e in errors[:16]]
                raise HTTPException(422,dict(code='INVALID_COMMAND',issues=issues))
            # Preserve PATCH field presence through validation -> proposal ->
            # transport. Materializing defaults would turn omitted fields into
            # explicit null resets and fail the second strict model validation.
            result['body']=jsonable_encoder(body,exclude_unset=True)
    elif 'body' in arguments and arguments['body'] is not None:raise HTTPException(422,'Этот инструмент не принимает body')
    if len(json.dumps(result,ensure_ascii=False))>40000:raise HTTPException(413,'Слишком большая команда')
    return result

def fingerprint(value):return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()

def bounded(value,depth=0):
    if depth>8:return '[Ограничено по глубине]'
    if isinstance(value,list):
        items=[bounded(v,depth+1) for v in value[:25]]
        return items if len(value)<=25 else dict(items=items,total=len(value),truncated=True)
    if isinstance(value,dict):return {k:bounded(v,depth+1) for k,v in value.items()}
    if isinstance(value,str):return value if len(value)<=3000 else value[:3000]+' [текст сокращён; используйте view]'
    return value

def enrollment_values(tool_name,value):
    """Only known enrollment output shapes identify credential strings."""
    if tool_name not in ('enrollment_read','enrollment_create'):return frozenset()
    found=set()
    def visit(node):
        if not isinstance(node,dict):return
        code=node.get('code')
        if isinstance(code,str) and re.fullmatch(r'[A-Za-z0-9_-]{16,256}',code):found.add(code)
        if node.get('source_path')==['code'] and isinstance(node.get('text_parts'),list):
            joined=''.join(part for part in node['text_parts'] if isinstance(part,str))
            if re.fullmatch(r'[A-Za-z0-9_-]{16,256}',joined):found.add(joined)
        for key in ('data','preview','result'):
            if isinstance(node.get(key),dict):visit(node[key])
    visit(value)
    return frozenset(found)


def workflow_enrollment_values(state):
    values=set()
    for proof in (state or {}).get('evidence',[]):
        values.update(enrollment_values(proof.get('tool'),proof.get('result')))
    return frozenset(values)


def mask_known_outputs(value,known):
    """Exact known bearer strings only; ordinary business codes stay intact."""
    if not known:return value
    if isinstance(value,str):
        for secret in sorted(known,key=len,reverse=True):value=value.replace(secret,'[защищённый код]')
        return value
    if isinstance(value,dict):return {key:mask_known_outputs(item,known) for key,item in value.items()}
    if isinstance(value,list):return [mask_known_outputs(item,known) for item in value]
    return value


def conversation_enrollment_values(session,principal,conversation_id):
    """One bounded owner/site/role scoped query; never reads or rotates live code."""
    from sqlalchemy import text
    rows=session.execute(text("""/* assistant_enrollment_private_values */
        SELECT left(a.result->'data'->>'code',257) AS result_code,
               left(a.result->>'code',257) AS root_code,
               left(a.before_snapshot->'preview'->>'code',257) AS preview_code
        FROM assistant_actions a JOIN assistant_conversations c USING(conversation_id)
        WHERE c.conversation_id=:chat AND c.user_id=:user AND c.site_id=:site AND c.role=:role
          AND a.tool_name IN ('enrollment_read','enrollment_create')
          AND (a.result->'data'->>'code' IS NOT NULL OR a.result->>'code' IS NOT NULL
               OR a.before_snapshot->'preview'->>'code' IS NOT NULL)
        ORDER BY a.created_at DESC,a.action_id DESC LIMIT 64"""),
        dict(chat=conversation_id,user=principal.user_id,site=principal.site_id,role=principal.role)).mappings()
    values=set()
    for row in rows:
        for code in row.values():values.update(enrollment_values('enrollment_read',dict(code=code)))
    return frozenset(values)


def protected_result(tool_name,value):
    """Credentials stay behind the current authenticated API, never in tools.

    Context is deliberately tool-specific: operation and inventory codes are
    ordinary business identifiers and must remain usable.
    """
    if tool_name not in ('enrollment_read','enrollment_create'):return value
    present=None
    if isinstance(value,dict):
        if 'code' in value:present=isinstance(value['code'],str) and bool(value['code'])
        elif type(value.get('code_present')) is bool:present=value['code_present']
    return dict(code_present=present,protected_output=True,resource=dict(
        url='/api/v1/maintenance/management/enrollment',title='Открыть код компании в защищённом просмотре',
        mime='application/json',protected=True),
        note='Код доступен только в защищённом просмотре с текущей проверкой прав; значение не передаётся модели и не сохраняется в диалоге.')

async def invoke(app,tool,args,headers):
    # ASGI transport never opens a socket or forwards cookies to the model/provider.
    if tool.name in ('site_switch','session_logout') and COOKIE_EFFECTS.get() is None:raise HTTPException(403,'Изменение сессии требует подтверждения пользователя')
    path=tool.path
    for key,value in args.get('path',{}).items():
        encoded=quote(str(value),safe='')
        if '/' in str(value) or str(value) in ('.','..'):raise HTTPException(422,'Некорректный идентификатор')
        path=path.replace('{'+key+'}',encoded)
    if re.search(r'[{}]',path):raise HTTPException(422,'Не указан идентификатор')
    options=dict(params=args.get('query',{}),headers=headers)
    if multipart(app,tool):
        files={};data={}
        for key,value in args.get('body',{}).items():
            if value is None:continue
            if key in file_fields(app,tool):
                row,blob=content(app,value);files[key]=(row['original_name'],blob,row['mime_type'])
            else:data[key]=str(value)
        options.update(data=data,files=files or None)
    else:options['json']=args.get('body')
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app,raise_app_exceptions=False),base_url='http://assistant.internal',follow_redirects=False) as client:
        try:response=await client.request(tool.method,path,**options)
        except httpx.TransportError:raise HTTPException(502,'Backend инструмента недоступен') from None
    if response.status_code<300 and response.content and 'json' not in response.headers.get('content-type',''):
        if args.get('view'):raise HTTPException(422,'У файла нет JSON-полей просмотра. Получите ссылку без view.')
        if len(response.content)>20_971_520:raise HTTPException(413,'Слишком большой файл результата')
        return dict(resource=dict(url=path+('?' +urlencode(args.get('query',{}),doseq=True) if args.get('query') else ''),title=tool.title,mime=response.headers.get('content-type','application/octet-stream'),size_bytes=len(response.content)))
    if len(response.content)>1_048_576:raise HTTPException(413,'Результат слишком большой. Уточните фильтр или страницу.')
    try:payload=response.json() if response.content else None
    except ValueError:raise HTTPException(502,'Инструмент вернул неподдерживаемый ответ') from None
    if response.status_code>=300:
        detail=payload.get('detail','Действие отклонено API') if isinstance(payload,dict) else 'Действие отклонено API'
        raise HTTPException(response.status_code,detail if isinstance(detail,str) else 'Проверьте поля команды')
    # Filter secret output BEFORE any projection/text slicing or persistence.
    payload=protected_result(tool.name,payload)
    if args.get('view'):
        view=args['view'];selected=payload
        for key in view['path']:
            if not isinstance(selected,dict) or key not in selected:raise HTTPException(422,'Неизвестное поле результата. Используйте имена из прочитанного ответа.')
            selected=selected[key]
        if isinstance(selected,list):
            if view['q']:selected=[item for item in selected if view['q'].casefold() in json.dumps(item,ensure_ascii=False).casefold()]
            payload=dict(items=selected[view['offset']:view['offset']+view['limit']],total=len(selected),offset=view['offset'],limit=view['limit'],source_path=view['path'])
        elif isinstance(selected,str):
            segment=selected[view['text_offset']:view['text_offset']+view['text_limit']]
            payload=dict(text_parts=[segment[i:i+2000] for i in range(0,len(segment),2000)],total_characters=len(selected),returned_characters=len(segment),text_offset=view['text_offset'],source_path=view['path'])
        else:payload=selected
    if tool.name in ('site_switch','session_logout'):
        effects=COOKIE_EFFECTS.get()
        if effects is None:raise HTTPException(500,'Изменение сессии доступно только при подтверждении')
        effects.extend(response.headers.get_list('set-cookie'))
        if isinstance(payload,dict):payload.pop('csrfToken',None)
        payload=dict(profile=payload.get('profile') if isinstance(payload,dict) else None,navigate_to='/login' if tool.name=='session_logout' else '/assistant')
    return payload

async def preflight(app,tool,args,headers):
    if not tool.before:return None
    before=next(t for t in TOOLS if t.name==tool.before)
    fields={f.name for f in route_for(app,before).dependant.path_params}
    params=dict(path={k:v for k,v in args.get('path',{}).items() if k in fields},query={})
    snapshot=await invoke(app,before,validate_arguments(app,before,params),headers)
    if tool.name=='task_assign':
        from datetime import datetime
        from zoneinfo import ZoneInfo
        context_tool=next(t for t in TOOLS if t.name=='assignment_context')
        context=await invoke(app,context_tool,validate_arguments(app,context_tool,dict(path=args['path'])),headers)
        if context.get('status')!='ready':raise HTTPException(422,context.get('explanation') or 'Уточните условия назначения')
        body=args['body'];tz=ZoneInfo(context['timezone'])
        start=datetime.fromisoformat(body['start_at']);end=datetime.fromisoformat(body['end_at'])
        request=dict(path=args['path'],body=dict(expected_revision=body['expected_revision'],start_local=start.astimezone(tz).replace(tzinfo=None).isoformat(),end_local=end.astimezone(tz).replace(tzinfo=None).isoformat(),executor_ids=body['executor_ids'],crew_id=body.get('crew_id')))
        preview_tool=next(t for t in TOOLS if t.name=='assignment_preview')
        preview=await invoke(app,preview_tool,validate_arguments(app,preview_tool,request),headers)
        command=preview.get('command')
        if not command:raise HTTPException(422,preview.get('explanation') or 'Нет допустимого состава и времени назначения')
        if set(command['executor_ids'])!=set(body['executor_ids']) or datetime.fromisoformat(command['start_at'])!=start or datetime.fromisoformat(command['end_at'])!=end:
            raise HTTPException(422,'Используйте точные состав и время из успешного assignment_preview')
    return snapshot
