"""Explicit capabilities over the real API; never accept a model-selected URL."""
from dataclasses import dataclass
from contextvars import ContextVar
import hashlib,json,re
from urllib.parse import quote
from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.routing import APIRoute
import httpx

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

# New capabilities must be reviewed here and tested through their existing endpoint.
# Even an apparently read-only POST may save forecasts or start work: default is proposal.
TOOLS=(
 Tool('equipment_list','Найти оборудование объекта','GET',P+'/equipment',agents=('assistant','planner','photo')),
 Tool('equipment_read','Карточка оборудования','GET',P+'/equipment/{equipment_id}',agents=('assistant','planner','photo')),
 Tool('catalog_read','Системы и типы оборудования','GET',P+'/management/catalog',(*PLAN,'director')),
 Tool('equipment_create','Добавить оборудование','POST',P+'/equipment',EDIT,'write'),
 Tool('equipment_edit','Изменить оборудование','PATCH',P+'/equipment/{equipment_id}',EDIT,'write',before='equipment_read'),
 Tool('equipment_retire','Вывести оборудование из эксплуатации','DELETE',P+'/equipment/{equipment_id}',EDIT,'write',before='equipment_read'),
 Tool('regulations_read','Регламенты и чек-листы оборудования','GET',P+'/equipment/{equipment_id}/service-configurations',agents=('assistant','planner','photo')),
 Tool('regulation_create','Добавить конфигурацию обслуживания','POST',P+'/equipment/{equipment_id}/service-configurations',('chief_engineer','admin'),'write'),
 Tool('regulation_edit','Изменить конфигурацию обслуживания','PUT',P+'/equipment/{equipment_id}/service-configurations/{binding_id}',('chief_engineer','admin'),'write',before='regulations_read'),
 Tool('tasks_list','Задания текущего объекта и пользователя','GET',P+'/ui/tasks',agents=('assistant','planner','photo')),
 Tool('task_read','Задание, инструкции и состояние отчёта','GET',P+'/ui/tasks/{task_id}',agents=('assistant','planner','photo')),
 Tool('calendar_read','Календарь работ','GET',P+'/ui/calendar'),
 Tool('assignment_context','Сотрудники и условия назначения','GET',P+'/ui/tasks/{task_id}/assignment-context',OPERATE),
 Tool('assignment_preview','Проверить вариант назначения','POST',P+'/tasks/{task_id}/assignment-preview',OPERATE),
 Tool('task_assign','Назначить бригаду и время','POST',P+'/tasks/{task_id}/assign',OPERATE,'write',before='task_read'),
 Tool('task_cancel','Отменить задание с причиной','POST',P+'/tasks/{task_id}/cancel',OPERATE,'write',before='task_read'),
 Tool('task_start','Начать своё назначенное задание','POST',P+'/tasks/{task_id}/start',('executor',),'write',before='task_read'),
 Tool('report_save','Сохранить фактический отчёт','PUT',P+'/tasks/{task_id}/report',('executor',),'write',before='task_read'),
 Tool('report_submit','Передать свой отчёт на проверку','POST',P+'/tasks/{task_id}/submit',('executor',),'write',before='task_read'),
 Tool('report_review','Принять отчёт или вернуть с причиной','POST',P+'/tasks/{task_id}/review',('engineer','chief_engineer'),'write',before='task_read'),
 Tool('photo_review','Проанализировать сохранённые фотографии отчёта','POST',P+'/tasks/{task_id}/photo-review',('engineer','chief_engineer'),'write',('assistant','photo'),'task_read'),
 Tool('forecast_run','Рассчитать и сохранить прогноз задания','POST',P+'/tasks/{task_id}/forecast',OPERATE,'write',before='task_read'),
 Tool('workforce_read','Команда, смены и квалификации','GET',P+'/management/workforce',PLAN),
 Tool('catalogs_list','Сохранённые Excel-каталоги','GET',P+'/catalog-imports',PLAN),
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
 Tool('catalog_read_saved','Сведения о сохранённом Excel','GET',P+'/catalog-imports/{identity}',PLAN),
 Tool('catalog_operations','Страница исходных операций Excel','GET',P+'/catalog-imports/{identity}/operations',PLAN),
 Tool('draft_preview','Рассчитать состав из подготовленных строк Excel','POST',P+'/draft-plans/preview',PLAN),
 Tool('draft_save','Сохранить рассчитанный план из Excel','POST',P+'/draft-plans',EDIT,'write'),
 Tool('draft_segments','Сегменты выбранной работы','GET',P+'/draft-plans/{identity}/occurrences/{occurrence_id}/segments',PLAN),
 Tool('draft_versions','История версий выбранного плана','GET',P+'/draft-plans/{identity}/versions',PLAN),
 Tool('draft_split','Изменить части работы новой версией','POST',P+'/draft-plans/{identity}/segments',EDIT,'write',before='draft_read'),
 Tool('draft_validate','Проверить допустимость версии без изменения','POST',P+'/draft-plans/{identity}/validate',PLAN),
 Tool('optimization_start','Запустить расчёт вариантов распределения','POST',P+'/draft-plans/{identity}/optimization-runs',EDIT,'write',before='draft_read'),
 Tool('optimization_list','Расчёты вариантов выбранного плана','GET',P+'/draft-plans/{identity}/optimization-runs',PLAN),
 Tool('optimization_read','Состояние и итоги расчёта','GET',P+'/optimization-runs/{run_id}',PLAN),
 Tool('optimization_placements','Размещения рассчитанного варианта','GET',P+'/optimization-runs/{run_id}/placements',PLAN),
 Tool('optimization_apply','Применить рассчитанный вариант новой версией','POST',P+'/optimization-runs/{run_id}/apply',EDIT,'write',before='optimization_read'),
 Tool('optimization_cancel','Остановить расчёт','POST',P+'/optimization-runs/{run_id}/cancel',EDIT,'write',before='optimization_read'),
 Tool('publication_regulations','Утверждённые инструкции для выпуска общего плана','GET',P+'/draft-plans/{identity}/publication-regulations',PLAN),
 Tool('publication_profiles','Шаблоны инструкций для выпуска каталога','GET',P+'/draft-plans/{identity}/publication-profiles',PLAN),
 Tool('publication_prepare','Подготовить предложение о выпуске','POST',P+'/draft-plans/{identity}/publication-proposals',EDIT,'write',before='draft_read'),
 Tool('publication_list','Согласования выбранного плана','GET',P+'/draft-plans/{identity}/publication-proposals',PLAN),
 Tool('publication_read','Точный состав предложения о выпуске','GET',P+'/publication-proposals/{identity}',PLAN),
 Tool('publication_changes','Страница изменений выпуска','GET',P+'/publication-proposals/{identity}/changes',PLAN),
 Tool('publication_approve','Утвердить точное предложение о выпуске','POST',P+'/publication-proposals/{identity}/approve',('chief_engineer',),'write',before='publication_read'),
 Tool('publication_reject','Отклонить предложение о выпуске','POST',P+'/publication-proposals/{identity}/reject',('chief_engineer',),'write',before='publication_read'),
 Tool('publication_publish','Выпустить утверждённый план в реальные задания','POST',P+'/publication-proposals/{identity}/publish',('chief_engineer',),'write',before='publication_read'),
)

def available(app,role,agent='assistant'):
    routes={(r.path,m):r for r in app.routes if isinstance(r,APIRoute) for m in r.methods}
    return {t.name:t for t in TOOLS if role in t.roles and agent in t.agents and (t.path,t.method) in routes}

def route_for(app,tool):
    return next(r for r in app.routes if isinstance(r,APIRoute) and r.path==tool.path and tool.method in r.methods)

def catalog(app,role,agent):
    return [dict(name=t.name,title=t.title,requires_confirmation=t.mode=='write') for t in available(app,role,agent).values()]

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
    for kind in ('path','query'):
        fields={p['name']:expand(p['schema']) for p in operation.get('parameters',[]) if p['in']==kind}
        needed=[p['name'] for p in operation.get('parameters',[]) if p['in']==kind and p.get('required')]
        props[kind]=dict(type='object',properties=fields,additionalProperties=False,required=needed)
        if needed:required.append(kind)
    body=operation.get('requestBody')
    if body:
        props['body']=expand(body['content']['application/json']['schema'])
        if body.get('required'):required.append('body')
    return dict(name=tool.name,title=tool.title,description=tool.title+(' — создаёт предложение; подтверждает только пользователь' if tool.mode=='write' else ''),
        inputSchema=dict(type='object',properties=props,additionalProperties=False,required=required),
        annotations=dict(readOnlyHint=tool.mode=='read',destructiveHint=tool.mode=='write',idempotentHint=tool.mode=='read',openWorldHint=False))

def validate_arguments(app,tool,arguments):
    if not isinstance(arguments,dict) or set(arguments)-{'path','query','body'}:raise HTTPException(422,'Неизвестные аргументы инструмента')
    route=route_for(app,tool);result={}
    for kind,fields in (('path',route.dependant.path_params),('query',route.dependant.query_params)):
        values=arguments.get(kind,{})
        if not isinstance(values,dict) or set(values)-{f.name for f in fields}:raise HTTPException(422,'Неизвестные параметры '+kind)
        result[kind]={}
        for field in fields:
            if field.name not in values:
                if field.required:raise HTTPException(422,'Нужен параметр '+field.name)
                continue
            validated,errors=field.validate(values[field.name],{},loc=(kind,field.name))
            if errors:raise HTTPException(422,'Проверьте параметр '+field.name)
            result[kind][field.name]=jsonable_encoder(validated)
    if route.body_field:
        body,errors=route.body_field.validate(arguments.get('body'),{},loc=('body',))
        if errors:raise HTTPException(422,'Аргументы не соответствуют схеме команды. Уточните обязательные поля.')
        result['body']=jsonable_encoder(body)
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
    if isinstance(value,str):return value[:3000]
    return value

async def invoke(app,tool,args,headers):
    # ASGI transport never opens a socket or forwards cookies to the model/provider.
    path=tool.path
    for key,value in args.get('path',{}).items():
        encoded=quote(str(value),safe='')
        if '/' in str(value) or str(value) in ('.','..'):raise HTTPException(422,'Некорректный идентификатор')
        path=path.replace('{'+key+'}',encoded)
    if re.search(r'[{}]',path):raise HTTPException(422,'Не указан идентификатор')
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app,raise_app_exceptions=False),base_url='http://assistant.internal',follow_redirects=False) as client:
        response=await client.request(tool.method,path,params=args.get('query',{}),json=args.get('body'),headers=headers)
    if len(response.content)>1_048_576:raise HTTPException(413,'Результат слишком большой. Уточните фильтр или страницу.')
    try:payload=response.json() if response.content else None
    except ValueError:raise HTTPException(502,'Инструмент вернул неподдерживаемый ответ') from None
    if response.status_code>=300:
        detail=payload.get('detail','Действие отклонено API') if isinstance(payload,dict) else 'Действие отклонено API'
        raise HTTPException(response.status_code,detail if isinstance(detail,str) else 'Проверьте поля команды')
    return payload

async def preflight(app,tool,args,headers):
    if not tool.before:return None
    before=next(t for t in TOOLS if t.name==tool.before)
    fields={f.name for f in route_for(app,before).dependant.path_params}
    params=dict(path={k:v for k,v in args.get('path',{}).items() if k in fields},query={})
    return await invoke(app,before,validate_arguments(app,before,params),headers)
