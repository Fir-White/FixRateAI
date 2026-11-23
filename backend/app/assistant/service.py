"""Durable conversations and proposals. No model call owns a DB transaction."""
import asyncio,json,threading,logging,traceback,time,re
import os
from datetime import datetime,timedelta,timezone
from pathlib import Path
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import text
from app.schemas.assistant import AgentStep,ToolSelection,FinalReply
from ml_service.app.providers.aitunnel import AITunnelClient,AITunnelConfig,AITunnelFailure
from ml_service.app.providers.ollama import OllamaClient,OllamaConfig,OllamaFailure
from .tools import available,catalog,describe,validate_arguments,invoke,preflight,fingerprint,bounded,EXPECTED_PRINCIPAL
from .attachments import SCOPE,COOKIE_EFFECTS,HUMAN_SECRET,owned,public as public_file,image_inputs
from .read_transport import read as read_tool,safe_arguments,result_summary

PROMPT_VERSION='fixrate-orchestrator-v1'
GRAPH_PROMPT_VERSION='fixrate-langgraph-v3'
DYNAMIC_PROMPT_VERSION='fixrate-llm-dynamic-v1'
OPERATOR_PROMPT_VERSION='fixrate-erp-operator-v1'


def prompt_version(settings):
    if settings.assistant_agent_version != 'v3':
        return PROMPT_VERSION
    return {'llm_dynamic': DYNAMIC_PROMPT_VERSION, 'erp_operator': OPERATOR_PROMPT_VERSION}.get(
        settings.assistant_v3_pipeline, GRAPH_PROMPT_VERSION)
PROMPTS=Path(__file__).parent/'prompts'
SLOTS=threading.BoundedSemaphore(2)
logger=logging.getLogger(__name__)
MAX_STEPS=12
MAX_TOOL_CALLS=20
PROVIDER_FAILURES=(AITunnelFailure,OllamaFailure)

def now():return datetime.now(timezone.utc)
def dump(value):return json.dumps(value,ensure_ascii=False,default=str)

def progress_fact(tool,value):
    """Bounded, factual summary of a tool result; never expose arguments or reasoning."""
    if tool in ('tasks_find','staff_find','equipment_find','maintenance_catalog_read') and isinstance(value,dict):
        total=value.get('total');items=value.get('items')
        if isinstance(total,int) and not isinstance(total,bool) and total>=0 and isinstance(items,list):
            return {'total':total,'shown':len(items)}
    if tool in ('assignment_preview','assignment_prepare') and isinstance(value,dict):
        return {'ready':bool(value.get('command'))}
    return None

def selection_matches_title(choice,title):
    """Require the selected task's meaningful words to occur in the verified title."""
    ignored={'задание','работа','работу','задания','пожалуйста','выбираю','выберите','название'}
    words=[w for w in re.findall(r'[а-яa-z0-9]+',choice.casefold().replace('ё','е')) if len(w)>=4 and w not in ignored]
    title_words=re.findall(r'[а-яa-z0-9]+',title.casefold().replace('ё','е'))
    return bool(words) and all(any(t.startswith(w[:4]) for t in title_words) for w in words)

def person_mentioned(name,source):
    tokens=re.findall(r'[а-яa-z0-9]+',name.casefold().replace('ё','е'))
    wanted=[t for t in tokens if len(t)>=4 or t.isdigit()]
    actual=re.findall(r'[а-яa-z0-9]+',source.casefold().replace('ё','е'))
    return bool(wanted) and all(any(a==t if t.isdigit() else a.startswith(t[:4]) for a in actual) for t in wanted)

def matching_tasks(items,choice,request):
    tasks=[item for item in items if selection_matches_title(choice,item.get('summary',''))]
    if len(tasks)>1 and re.search(r'ближайш',request,re.I) and tasks[0].get('scheduledStart') and tasks[1].get('scheduledStart') and tasks[0]['scheduledStart']!=tasks[1]['scheduledStart']:
        return tasks[:1]
    return tasks

def task_choice_prompt(observations,force=False):
    """List only server-returned work; never ask the user to discover an internal ID."""
    failed=any(o.get('tool') in ('task_read','assignment_context','assignment_preview','task_assign') and o.get('status_code') in (404,422) for o in observations)
    result=next((o.get('result') for o in reversed(observations) if o.get('tool')=='tasks_find' and isinstance(o.get('result'),dict) and o['result'].get('items')),None)
    if not (failed or force) or not result:return None
    lines=[]
    for item in result['items'][:5]:
        if not isinstance(item,dict) or not re.fullmatch(r'[0-9a-fA-F-]{36}',str(item.get('id',''))):continue
        label=str(item.get('summary') or item.get('title') or 'Задание').replace('\n',' ')[:180]
        equipment=str(item.get('equipmentName') or 'оборудование не указано').replace('\n',' ')[:120]
        date=str(item.get('mandatoryDueDate') or item.get('scheduledStart') or 'дата не указана')[:10]
        overdue='; просрочено' if item.get('isOverdue') else ''
        states={'draft':'черновик','assigned':'назначено','in_progress':'в работе','submitted':'на проверке','rework_required':'на доработке','accepted':'завершено'}
        state=item.get('state');status=states.get(state,'статус не указан')
        lines.append(f"{len(lines)+1}. {label} — {equipment}, срок: {date}, статус: {status}{overdue} (ID: {item['id']})")
    if not lines:return None
    return 'Не удалось определить задание для назначения. Вот найденные работы:\n\n'+'\n'.join(lines)+'\n\nВыберите задание по номеру или ID. Если нужно другое, уточните название или дату.'

def chosen_task_id(choice,previous_answer):
    listed=re.findall(r'^\s*(\d+)\.\s.*\(ID: ([0-9a-fA-F-]{36})\)\s*$',previous_answer,re.M)
    value=choice.strip().casefold().rstrip('.! ')
    return next((identity for number,identity in listed if value in (number,identity.casefold())),None)

def needs_history(question,previous_answer=''):
    """Keep prior turns for explicit references and elliptical follow-up commands."""
    value=question.casefold().strip().replace('ё','е')
    selection=bool(previous_answer and len(value)<=200 and '?' not in value and re.search(r'(?:укажите|выберите|како[ей]|какую|уточните).{0,100}(?:задани|работ|сотрудник|исполнител)',previous_answer.casefold(),re.S))
    return bool(selection or re.search(r'\b(?:он|она|они|их|его|ее|ему|им|это|этот|эта|эту|эти|этого|этой|этом|этим|этому|ними|него|нее|них|там|тогда|тот|та|те|той|тех|также|еще|подробнее|продолжи\w*|предыдущ\w*|выше|указанн\w*|названн\w*|упомянут\w*)\b',value)
        or re.match(r'^а\s+',value)
        or re.fullmatch(r'(?:почему|зачем|как так|что дальше|и что)[\s?.!]*',value)
        or re.fullmatch(r'(?:да|нет|ага|угу|конечно|согласен|согласна|готов|готова|готовы|подтверждаю|верно|именно|хорошо|ладно|давай|делай)[\s?.!]*',value)
        or re.match(r'^(?:назначь|распредели|перенеси|отмени|выполни|подтверди|сравни|измени|удали|продолжай)(?:\s|$)',value))

def progress(app,turn_id,trace,tool=None):
    """Publish only server-controlled operation metadata, never model reasoning."""
    entries=[*trace,*([dict(tool=tool,status='running',at=now().isoformat())] if tool else [])]
    with app.state.factory() as session:
        session.execute(text("UPDATE assistant_turns SET trace=CAST(:trace AS jsonb) WHERE turn_id=:id AND status='running'"),dict(id=turn_id,trace=dump(entries)))
        session.commit()

def conversation(session,principal,identity,lock=False):
    row=session.execute(text('SELECT * FROM assistant_conversations WHERE conversation_id=:id AND site_id=:site AND user_id=:user AND role=:role'+(' FOR UPDATE' if lock else '')),
        dict(id=identity,site=principal.site_id,user=principal.user_id,role=principal.role)).mappings().first()
    if row is None:raise HTTPException(404,'Диалог не найден')
    return dict(row)

def action(session,principal,identity,lock=False):
    row=session.execute(text('''SELECT a.* FROM assistant_actions a JOIN assistant_conversations c USING(conversation_id)
        WHERE a.action_id=:id AND c.site_id=:site AND c.user_id=:user AND c.role=:role'''+(' FOR UPDATE OF a' if lock else '')),
        dict(id=identity,site=principal.site_id,user=principal.user_id,role=principal.role)).mappings().first()
    if row is None:raise HTTPException(404,'Предложение не найдено')
    return dict(row)

def public_action(row):
    from .tools import enrollment_values,mask_known_outputs
    known=enrollment_values(row['tool_name'],row.get('result'))|enrollment_values(row['tool_name'],row.get('before_snapshot'))
    result=dict(row)
    from .tools import TOOLS
    tool=next((t for t in TOOLS if t.name==row['tool_name']),None)
    result['secret_fields']=list(tool.secrets)+[k for k in tool.optional_secrets if row['arguments'].get('body',{}).get(k)==HUMAN_SECRET] if tool else []
    if row['tool_name'] in ('enrollment_read','enrollment_create'):
        from .tools import protected_result
        legacy=result.get('result')
        if legacy is not None:
            data=legacy.get('data') if isinstance(legacy,dict) and 'data' in legacy else legacy
            result['result']=dict(data=protected_result(row['tool_name'],data),verification=dict(
                status='unverified',reason='protected_output_requires_current_api_view',
                summary='Откройте защищённый просмотр с текущей проверкой прав.',evidence={}))
        if result.get('before_snapshot') is not None:
            safe=protected_result(row['tool_name'],result['before_snapshot'].get('preview'))
            result['before_snapshot']=dict(preview=safe,sha256=fingerprint(safe))

    # Crash after dispatch is deliberately not retried: the downstream API may have committed.
    if result['status']=='executing' and result['started_at'] and result['started_at']<now()-timedelta(minutes=3):
        result['status']='uncertain'
    return mask_known_outputs(result,known)

def audit(session,principal,identity,event,details):
    session.execute(text('''INSERT INTO audit_events(site_id,actor_type,actor_user_id,entity_type,entity_id,action,after_snapshot)
        VALUES (:site,'user',:user,'assistant_action',:id,:event,CAST(:details AS jsonb))'''),
        dict(site=principal.site_id,user=principal.user_id,id=identity,event=event,details=dump(details)))

async def propose(app,session,principal,thread,tool,args,explanation,headers,turn_id=None,workflow_goal_id=None,workflow_root_turn_id=None):
    question=''
    if turn_id:
        if workflow_goal_id:
            workflow_root_turn_id=workflow_root_turn_id or turn_id
            root=session.scalar(text('SELECT turn_id FROM assistant_turns WHERE turn_id=:root AND conversation_id=:chat FOR UPDATE'),dict(root=workflow_root_turn_id,chat=thread['conversation_id']))
            if root is None:raise HTTPException(404,'Поручение не найдено')
        turn_source=session.execute(text('SELECT status,content,execution_engine FROM assistant_turns WHERE turn_id=:id FOR UPDATE'),dict(id=turn_id)).mappings().first()
        if turn_source is None or turn_source['status']!='running':raise HTTPException(409,'Ответ уже прерван. Отправьте новый запрос.')
        question=turn_source['content']
        if workflow_root_turn_id:
            question=session.scalar(text('SELECT content FROM assistant_turns WHERE turn_id=:root AND conversation_id=:chat'),dict(root=workflow_root_turn_id,chat=thread['conversation_id'])) or question
        if workflow_goal_id:
            existing=session.scalar(text('SELECT action_id FROM assistant_actions WHERE workflow_root_turn_id=:root AND workflow_goal_id=:goal'),dict(root=workflow_root_turn_id,goal=workflow_goal_id))
            if existing:return public_action(action(session,principal,existing))
    args=validate_arguments(app,tool,args)
    from .explicit_draft import specification,arguments as explicit_arguments
    explicit=specification(question) if turn_id else None
    if explicit and (tool.name!=explicit['tool'] or any(str(args.get('path',{}).get(key,'')).casefold()!=value.casefold() for key,value in explicit['path'].items())):
        raise HTTPException(422,'Операция или карточка не соответствует явной команде пользователя. Используйте указанные действие и идентификатор.')
    from .tools import file_fields
    for name in file_fields(app,tool):
        if args.get('body',{}).get(name):owned(app,args['body'][name])
    before=await preflight(app,tool,args,headers)
    if turn_id and tool.name == 'equipment_edit':
        from .semantic_plan import QUOTED, UUID, asset_references, equipment_changes
        changes, incomplete = equipment_changes(question)
        business_fields = {key: value for key, value in args.get('body', {}).items() if key != 'expected_revision'}
        if incomplete or len(changes) > 1 and business_fields != changes:
            raise HTTPException(422, 'Карточка должна содержать все явно запрошенные изменения оборудования.')
        if len(changes) > 1 and isinstance(before, dict):
            if args.get('body', {}).get('expected_revision') != before.get('revision'):
                raise HTTPException(409, 'Ревизия оборудования изменилась. Откройте свежую карточку.')
            source = QUOTED.sub(' ', question)
            codes = {code.casefold() for code in asset_references(source)}
            ids = {value.lower() for value in re.findall(r'\b' + UUID + r'\b', source, re.I)}
            if ids:
                matches = ids == {str(before.get('equipment_id'))}
            elif codes:
                matches = codes == {str(before.get('asset_code')).casefold()}
            else:
                name = str(before.get('name') or '')
                matches = bool(name and re.search(r'(?<!\w)' + re.escape(name) + r'(?!\w)', source, re.I))
            if not matches:
                raise HTTPException(422, 'Не удалось однозначно связать изменения с указанной карточкой оборудования.')
    if explicit:
        exact=explicit_arguments(explicit,before)
        if exact is None:raise HTTPException(422,'Явная команда не подтверждена текущим состоянием карточки')
        if set(args.get('body',{}))-set(exact['body']):raise HTTPException(422,'Для этой явной команды переданы непрошенные поля. Подготовьте только указанное изменение.')
        args=validate_arguments(app,tool,{**args,'body':exact['body']})
    from .intents import mutation_requested
    if turn_id and mutation_requested(question) and tool.name in ('equipment_edit','staff_edit') and isinstance(before,dict):
        from .intents import literal_rename,explicit_revision
        parts=re.split(r'\b(?:затем|после этого|then)\b',question,maxsplit=1,flags=re.I)
        source_action=parts[-1] if len(parts)==2 and not mutation_requested(parts[0]) else question
        body=dict(args.get('body',{}));revision=before.get('revision')
        # Supply the technical token while preparing the reviewable draft, not
        # during confirmation. Explicit user/MCP conditions remain authoritative.
        if type(revision) is int and revision>0 and not explicit_revision(source_action):body['expected_revision']=revision
        if tool.name=='equipment_edit' and 'name' in body:
            requested_name=literal_rename(source_action)
            if requested_name is not None:body['name']=requested_name
        args=validate_arguments(app,tool,{**args,'body':body})
    snapshot=None if before is None else dict(sha256=fingerprint(before),preview=bounded(before))
    identity=uuid4();expires=now()+timedelta(minutes=15)
    sha=fingerprint(dict(tool=tool.name,arguments=args,before=snapshot,actor=str(principal.user_id),site=str(principal.site_id)))
    session.execute(text('''INSERT INTO assistant_actions(action_id,conversation_id,turn_id,tool_name,arguments,payload_sha256,before_snapshot,explanation,status,expires_at,workflow_goal_id,workflow_root_turn_id)
        VALUES (:id,:conversation,:turn,:tool,CAST(:args AS jsonb),:sha,CAST(:before AS jsonb),:explanation,'proposed',:expires,:goal,:root)'''),
        dict(id=identity,conversation=thread['conversation_id'],turn=turn_id,tool=tool.name,args=dump(args),sha=sha,before=dump(snapshot),explanation=explanation[:3000],expires=expires,goal=workflow_goal_id,root=workflow_root_turn_id))
    audit(session,principal,identity,'proposed',dict(tool=tool.name,payload_sha256=sha))
    if turn_id and turn_source['execution_engine'] == 'v3':
        from .graph_persistence import register_thread, thread_config
        config = thread_config(principal, thread['conversation_id'], 'action', identity)
        register_thread(session, config, thread['conversation_id'])
    session.commit()
    return public_action(action(session,principal,identity))

def provider_config(selection=None):
    from .model_preferences import config
    return config(selection)

def provider(selection=None):
    config=provider_config(selection)
    return OllamaClient(config) if isinstance(config,OllamaConfig) else AITunnelClient(config)

def turn_timeout_seconds(selection=None):
    try:
        config=provider_config(selection)
        return max(180,config.timeout+30)
    except ValueError:return 180

def configured(selection=None):
    try:
        config=provider_config(selection)
        return dict(available=True if isinstance(config,OllamaConfig) else bool(config.api_key),model_ref=config.model_ref)
    except ValueError:return dict(available=False,model_ref=None)

def prompt(agent):
    base=(PROMPTS/'assistant.md').read_text(encoding='utf-8')
    return base if agent=='assistant' else base+'\n\n'+(PROMPTS/(agent+'.md')).read_text(encoding='utf-8')

def compact(value,budget=18000):
    """Keep complete JSON; never slice a serialized tool response mid-value."""
    result=bounded(value)
    def shrink(item,limit,width):
        if isinstance(item,list):return [shrink(v,limit,width) for v in item[:limit]]
        if isinstance(item,dict):return {k:shrink(v,limit,width) for k,v in item.items()}
        if isinstance(item,str) and len(item)>width:return item[:width]+' [текст сокращён]'
        return item
    for limit,width in ((10,1500),(5,700),(2,300),(1,100)):
        if len(dump(result))<=budget:return result
        result=dict(data=shrink(bounded(value),limit,width),truncated=True,note='Ответ сокращён. Для точной операции прочитайте выбранную карточку или следующую страницу.')
    return result if len(dump(result))<=budget else dict(truncated=True,note='Слишком большой ответ. Уточните объект, фильтры или страницу.')

def readable_evidence(value, titles=None):
    """Project tool evidence for ordinary prose; tool execution keeps the original data."""
    names={'tool':'источник','source_arguments':'условия поиска','result':'результат','query':'параметры',
           'active_only':'только активные','period':'период','state':'состояние','dataOrigin':'происхождение данных',
           'status':'статус','assignees':'исполнители','start_at':'начало','end_at':'окончание'}
    labels={'synthetic_demo':'демонстрационные данные','draft':'черновик','assigned':'назначено',
            'accepted':'принято','completed':'выполнено','overdue':'просрочено','upcoming':'предстоящие',
            'unconfirmed':'не подтверждено','all':'все'}
    if titles is None:
        from .tools import TOOLS
        titles={tool.name:tool.title for tool in TOOLS}
    if isinstance(value,list):return [readable_evidence(item,titles) for item in value]
    if isinstance(value,dict):
        result={}
        for key,item in value.items():
            if isinstance(item,str) and re.fullmatch(r'[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}',item):continue
            if key=='tool' and isinstance(item,str):item=titles.get(item,item)
            elif key in ('status','state','period','dataOrigin') and isinstance(item,str):item=labels.get(item,item)
            result[names.get(key,key)]=readable_evidence(item,titles)
        return result
    return value

def incomplete_answer(question,trace,reason):
    if any(s['status']=='proposed' for s in trace):
        return 'Предложение подготовлено и доступно в карточке. Проверьте параметры и подтвердите изменение; оно пока не выполнено.'
    question=question.casefold()
    ranking=any(word in question for word in ('результатив','эффективн','лучш','рейтинг')) and any(word in question for word in ('работник','сотрудник','исполнител'))
    if ranking:
        return 'Пока не могу достоверно назвать самого результативного работника: сопоставимую статистику по сотрудникам подтвердить не удалось. Это не означает, что данных в системе нет. За какой период сравниваем и по какому критерию — принятым работам, трудозатратам или соблюдению сроков?'
    if reason in ('AITUNNEL_TIMEOUT','OLLAMA_TIMEOUT'):
        return 'Не удалось завершить проверку за отведённое время. По полученным сведениям надёжный ответ пока не подтверждён. Уточните объект или период, чтобы я проверил более узкий запрос.'
    if any(s.get('code')==403 for s in trace) and not any(s['status']=='completed' and s['tool']!='describe_tool' for s in trace):
        return 'Не удалось получить необходимые сведения: часть данных недоступна для вашей роли. Это не означает, что записей нет. Уточните доступный объект или обратитесь к пользователю с нужными правами.'
    return 'Мне пока не хватает проверенных сведений, чтобы уверенно ответить на этот вопрос. Проверку не удалось завершить, поэтому я не буду делать вывод по неполной выборке. Уточните нужный объект, период или критерий — продолжим с конкретными условиями.'

async def finish_answer(app,client,turn_id,question,history,observations,trace,reason,workbooks=None,images=None,server_context=None):
    progress(app,turn_id,trace,'__responding')
    if reason=='task_choice_needed' or re.search(r'назнач|распредел',question,re.I):
        choices=task_choice_prompt(observations,force=bool(re.search(r'ближайш',question,re.I)))
        if choices:return choices
    context=dict(question=question,history=[dict(user=t['content'][:3000],answer=t['answer'][:3000]) for t in reversed(history[1:4])] if needs_history(question,history[1]['answer'] if len(history)>1 else '') else [],
        verified_results=compact(observations,22000),completion_reason=reason,workbooks=workbooks or [],server_context=server_context or {})
    try:
        from .photo_reading import requested as reading_requested,VisiblePhotoReading,SYSTEM as reading_system,render as render_reading
        if len(images or [])==1 and reading_requested(question):
            value=await asyncio.to_thread(client.chat,[dict(role='system',content=reading_system),dict(role='user',content=question,images=images)],VisiblePhotoReading,1200)
            trace.append(dict(tool='__photo_observation',status='completed',result=dict(label_read=value.asset_label is not None,value_read=value.value is not None,unit_read=value.unit is not None)))
            return render_reading(value)
        simple=callable(getattr(client,'text',None)) and not observations and not workbooks and not images
        content=dict(question=question,history=context['history'],server_context=context['server_context']) if simple else context
        if not simple and callable(getattr(client,'text',None)) and not re.search(r'\b(?:uuid|json|api|идентификатор\w*|техническ\w*|поля|инструмент\w*)\b',question.casefold()):
            content={**context,'verified_results':readable_evidence(context['verified_results'])}
        messages=[dict(role='system',content=(PROMPTS/('conversation.md' if simple else 'final.md')).read_text(encoding='utf-8')),dict(role='user',content=dump(content))]
        if images:messages[-1]['images']=images
        if callable(getattr(client,'text',None)):
            return await asyncio.to_thread(client.text,messages,8192)
        result=await asyncio.to_thread(client.chat,messages,FinalReply,6000)
        return result.answer
    except Exception as exc:
        logger.warning('assistant_final_reply_unavailable turn=%s exception_type=%s',turn_id,type(exc).__name__)
        if isinstance(exc,PROVIDER_FAILURES):raise
        return incomplete_answer(question,trace,reason)

async def agent_turn(app,principal,thread_id,turn_id,headers):
    with app.state.factory() as session:
        engine = session.scalar(text('SELECT execution_engine FROM assistant_turns WHERE turn_id=:id'), dict(id=turn_id))
    if engine == 'v3':
        from .graph_agent import run
    else:
        from .orchestrator import run
    return await run(app,principal,thread_id,turn_id,headers)


def run_turn(app,principal,thread_id,turn_id,headers):
    try:
        with app.state.factory() as session:
            claimed = session.execute(text("""UPDATE assistant_turns SET worker_claimed_at=now()
                WHERE turn_id=:turn AND conversation_id=:chat AND status='running'
                  AND worker_claimed_at IS NULL AND (deadline_at IS NULL OR deadline_at>now())
                RETURNING turn_id"""), dict(turn=turn_id, chat=thread_id)).scalar()
            session.commit()
        if claimed:
            asyncio.run(agent_turn(app,principal,thread_id,turn_id,headers))
    finally:
        SLOTS.release()


def expire_turns(session, conversation_id):
    """Expire a lost execution lease; recovery uses a fresh authorized message."""
    cutoff = now()
    return session.execute(text("""UPDATE assistant_turns
        SET status='failed', error_code='ASSISTANT_INTERRUPTED', finished_at=now(),
            answer=CASE WHEN workflow IS NOT NULL
                THEN 'Ответ прерван. Поручение сохранено, его можно продолжить.'
                ELSE 'Ответ прерван. Сообщение сохранено, его можно отправить повторно.' END
        WHERE conversation_id=:chat AND status='running'
          AND ((deadline_at IS NOT NULL AND deadline_at<=:now) OR
               (deadline_at IS NULL AND created_at<=:legacy_cutoff))"""),
        dict(chat=conversation_id, now=cutoff,
             legacy_cutoff=cutoff-timedelta(seconds=turn_timeout_seconds()))).rowcount

async def confirm(app,session,principal,row,headers,secret_values=None):
    EXPECTED_PRINCIPAL.set((principal.user_id,principal.site_id,principal.role))
    SCOPE.set((row['conversation_id'],principal.user_id,principal.site_id,principal.role))
    thread=conversation(session,principal,row['conversation_id'])
    tools=available(app,principal.role,'assistant');tool=tools.get(row['tool_name'])
    if tool is None or tool.mode!='write':raise HTTPException(403,'Право на действие изменилось')
    secret_values=secret_values or {}
    secret_fields=public_action(row)['secret_fields']
    if set(secret_values)!=set(secret_fields) or any(not isinstance(v,str) or not 1<=len(v)<=4096 for v in secret_values.values()):
        raise HTTPException(422,'Заполните защищённые поля подтверждения. Не отправляйте пароль сообщением.')
    arguments=row['arguments']
    if secret_fields:arguments={**arguments,'body':{**arguments.get('body',{}),**secret_values}}
    try:
        before=await preflight(app,tool,row['arguments'],headers)
        if row['before_snapshot'] is not None and fingerprint(before)!=row['before_snapshot']['sha256']:
            session.execute(text("UPDATE assistant_actions SET status='stale',finished_at=now() WHERE action_id=:id"),dict(id=row['action_id']))
            audit(session,principal,row['action_id'],'stale',dict(tool=tool.name));session.commit()
            raise HTTPException(409,'Данные изменились после подготовки. Попросите ИИ подготовить новое предложение.')
    except BaseException:
        session.rollback();raise
    session.execute(text("UPDATE assistant_actions SET status='executing',started_at=now() WHERE action_id=:id"),dict(id=row['action_id']))
    audit(session,principal,row['action_id'],'confirmed',dict(tool=tool.name,payload_sha256=row['payload_sha256']))
    # Claim before dispatch. Repeated confirmation will never dispatch this action twice.
    session.commit()
    try:
        value=await invoke(app,tool,arguments,headers)
        from .action_outcomes import verify_action
        verification=await verify_action(app,tool,arguments,value,headers,before=before)
        if tool.name=='profile_email' or (tool.name=='staff_edit' and str(arguments.get('path',{}).get('user_id'))==str(principal.user_id)):
            value=dict(data=value,navigate_to='/assistant')
        status='succeeded';result=dict(data=bounded(value),verification=verification)
    except HTTPException as exc:
        status='uncertain' if exc.status_code>=500 or exc.status_code==413 else 'failed'
        result=dict(message=str(exc.detail)[:2000],status_code=exc.status_code)
    except BaseException:
        status='uncertain';result=dict(message='Результат выполнения не подтверждён. Проверьте карточку объекта перед новой командой.')
    session.execute(text('UPDATE assistant_actions SET status=:status,result=CAST(:result AS jsonb),finished_at=now() WHERE action_id=:id'),dict(id=row['action_id'],status=status,result=dump(result)))
    audit(session,principal,row['action_id'],status,dict(tool=tool.name,payload_sha256=row['payload_sha256']))
    session.commit()
    return public_action(action(session,principal,row['action_id']))


def reject(session, principal, row):
    identity = row['action_id']
    if row['status'] == 'proposed':
        session.execute(text("UPDATE assistant_actions SET status='rejected',finished_at=now() WHERE action_id=:id"),
                        dict(id=identity))
        audit(session, principal, identity, 'rejected', dict(tool=row['tool_name']))
        session.commit()
    return public_action(action(session, principal, identity))


def action_uses_graph(session, row):
    return row['turn_id'] is not None and session.scalar(text(
        'SELECT execution_engine FROM assistant_turns WHERE turn_id=:id'
    ), dict(id=row['turn_id'])) == 'v3'
