"""Private chat workspace, explicit confirmations, and stateless MCP tools transport."""
from datetime import timedelta
import json
from uuid import UUID,uuid4
from fastapi import BackgroundTasks,Depends,HTTPException,Query,Request,Response
from fastapi.responses import JSONResponse
from sqlalchemy import text
from app.schemas.assistant import ConversationCreate,MessageCreate,ConfirmAction
from app.assistant import service as svc
from app.assistant.tools import available,catalog,describe,validate_arguments,invoke,bounded,EXPECTED_PRINCIPAL

BASE='/api/v1/assistant'
AGENTS=[dict(id='assistant',title='Ассистент',description='Оборудование, задания и повседневная работа'),
        dict(id='planner',title='Планирование',description='Версии плана, распределение и нагрузка'),
        dict(id='photo',title='Фотоанализ',description='Проверка сохранённых фотоотчётов')]

def forwarded(request):
    # Secrets remain only in memory and never enter prompts, DB records or tool results.
    return {key:request.headers[key] for key in ('cookie','x-csrf-token') if key in request.headers}

def register_routes(app,views):
    @app.get(BASE+'/capabilities')
    def capabilities(response:Response,v=Depends(views)):
        response.headers['Cache-Control']='private, no-store'
        return dict(**svc.configured(),prompt_version=svc.PROMPT_VERSION,agents=AGENTS,
            tools={a['id']:catalog(app,v.principal.role,a['id']) for a in AGENTS})

    @app.get(BASE+'/conversations')
    def conversations(response:Response,offset:int=Query(0,ge=0),v=Depends(views)):
        response.headers['Cache-Control']='private, no-store'
        params=dict(site=v.principal.site_id,user=v.principal.user_id,role=v.principal.role,offset=offset)
        rows=v.session.execute(text('''SELECT * FROM assistant_conversations WHERE site_id=:site AND user_id=:user AND role=:role
            ORDER BY updated_at DESC,conversation_id LIMIT 25 OFFSET :offset'''),params).mappings().all()
        count=v.session.scalar(text('SELECT count(*) FROM assistant_conversations WHERE site_id=:site AND user_id=:user AND role=:role'),params)
        return dict(items=[dict(r) for r in rows],total=count)

    @app.post(BASE+'/conversations',status_code=201)
    def create(command:ConversationCreate,v=Depends(views)):
        identity=uuid4()
        v.session.execute(text('INSERT INTO assistant_conversations(conversation_id,site_id,user_id,role,title,agent) VALUES (:id,:site,:user,:role,:title,:agent)'),
            dict(id=identity,site=v.principal.site_id,user=v.principal.user_id,role=v.principal.role,title=command.title,agent=command.agent))
        v.session.commit()
        return svc.conversation(v.session,v.principal,identity)

    @app.get(BASE+'/conversations/{identity}')
    def read(identity:UUID,response:Response,offset:int=Query(0,ge=0),v=Depends(views)):
        response.headers['Cache-Control']='private, no-store'
        thread=svc.conversation(v.session,v.principal,identity)
        # A lost process cannot leave the UI polling forever; read never retries model or action.
        v.session.execute(text("UPDATE assistant_turns SET status='failed',error_code='ASSISTANT_INTERRUPTED',answer='Ответ прерван. Сообщение сохранено; отправьте новый запрос.',finished_at=now() WHERE conversation_id=:id AND status='running' AND created_at<:cutoff"),dict(id=identity,cutoff=svc.now()-timedelta(minutes=3)))
        turns=v.session.execute(text('SELECT * FROM assistant_turns WHERE conversation_id=:id ORDER BY created_at DESC,turn_id DESC LIMIT 25 OFFSET :offset'),dict(id=identity,offset=offset)).mappings().all()
        count=v.session.scalar(text('SELECT count(*) FROM assistant_turns WHERE conversation_id=:id'),dict(id=identity))
        rows=v.session.execute(text('''SELECT * FROM assistant_actions WHERE conversation_id=:id AND
            (turn_id=ANY(CAST(:turns AS uuid[])) OR turn_id IS NULL) ORDER BY created_at LIMIT 100'''),dict(id=identity,turns=[r['turn_id'] for r in turns])).mappings().all()
        return dict(conversation=thread,turns=list(reversed([dict(r) for r in turns])),total=count,actions=[svc.public_action(r) for r in rows])

    @app.post(BASE+'/conversations/{identity}/messages',status_code=202)
    def message(identity:UUID,command:MessageCreate,background:BackgroundTasks,request:Request,v=Depends(views)):
        thread=svc.conversation(v.session,v.principal,identity,lock=True)
        previous=v.session.execute(text('SELECT * FROM assistant_turns WHERE conversation_id=:id AND request_key=:key'),dict(id=identity,key=command.idempotency_key)).mappings().first()
        if previous:
            if previous['content']!=command.content:raise HTTPException(409,'Ключ повтора принадлежит другому сообщению')
            return dict(previous)
        if v.session.scalar(text("SELECT EXISTS(SELECT 1 FROM assistant_turns WHERE conversation_id=:id AND status='running' AND created_at>:cutoff)"),dict(id=identity,cutoff=svc.now()-timedelta(minutes=3))):
            raise HTTPException(409,'Дождитесь ответа на предыдущее сообщение')
        if not svc.configured()['available'] and not hasattr(app.state,'assistant_provider_factory'):raise HTTPException(503,'ИИ не настроен. Укажите серверный ключ AI Tunnel и модель чата.')
        if not svc.SLOTS.acquire(blocking=False):raise HTTPException(429,'ИИ сейчас занят. Попробуйте через несколько секунд.')
        turn=uuid4()
        try:
            v.session.execute(text("INSERT INTO assistant_turns(turn_id,conversation_id,request_key,content,status,prompt_version) VALUES (:id,:conversation,:key,:content,'running',:prompt)"),
                dict(id=turn,conversation=identity,key=command.idempotency_key,content=command.content,prompt=svc.PROMPT_VERSION))
            v.session.execute(text("UPDATE assistant_conversations SET updated_at=now(),title=CASE WHEN title='Новый диалог' THEN :title ELSE title END WHERE conversation_id=:id"),dict(id=identity,title=command.content[:100]))
            v.session.commit()
        except BaseException:svc.SLOTS.release();raise
        background.add_task(svc.run_turn,app,v.principal,identity,turn,forwarded(request))
        return dict(turn_id=turn,status='running')

    @app.post(BASE+'/actions/{identity}/reject')
    def reject(identity:UUID,v=Depends(views)):
        row=svc.action(v.session,v.principal,identity,lock=True)
        if row['status']=='proposed':
            v.session.execute(text("UPDATE assistant_actions SET status='rejected',finished_at=now() WHERE action_id=:id"),dict(id=identity))
            svc.audit(v.session,v.principal,identity,'rejected',dict(tool=row['tool_name']));v.session.commit()
        return svc.public_action(svc.action(v.session,v.principal,identity))

    @app.post(BASE+'/actions/{identity}/confirm')
    async def confirm(identity:UUID,command:ConfirmAction,request:Request,v=Depends(views)):
        row=svc.action(v.session,v.principal,identity,lock=True)
        if command.payload_sha256!=row['payload_sha256']:raise HTTPException(409,'Состав предложения изменился')
        if row['status']!='proposed':return svc.public_action(row)
        if row['expires_at']<svc.now():raise HTTPException(409,'Предложение истекло. Подготовьте новое по свежим данным.')
        return await svc.confirm(app,v.session,v.principal,row,forwarded(request))

    @app.post(BASE+'/mcp')
    async def mcp(request:Request,v=Depends(views)):
        """Pinned MCP 2025-06-18, stateless Streamable HTTP JSON responses, session auth."""
        accept=request.headers.get('accept','')
        if 'application/json' not in accept or 'text/event-stream' not in accept:raise HTTPException(406,'MCP Accept must include application/json and text/event-stream')
        if request.headers.get('content-length','0').isdigit() and int(request.headers.get('content-length','0'))>65536:raise HTTPException(413,'Слишком большой запрос MCP')
        raw=await request.body()
        if len(raw)>65536:raise HTTPException(413,'Слишком большой запрос MCP')
        try:message=json.loads(raw)
        except ValueError:return JSONResponse(dict(jsonrpc='2.0',id=None,error=dict(code=-32700,message='Parse error')))
        identity=message.get('id') if isinstance(message,dict) else None
        def error(code,message):return dict(jsonrpc='2.0',id=identity,error=dict(code=code,message=message))
        if not isinstance(message,dict) or message.get('jsonrpc')!='2.0' or not isinstance(message.get('method'),str):return error(-32600,'Invalid request')
        method=message['method'];params=message.get('params',{})
        if not isinstance(params,dict):return error(-32602,'Invalid params')
        if method=='notifications/initialized':return Response(status_code=202)
        if identity is None:return Response(status_code=202)
        if not isinstance(identity,(str,int)) or isinstance(identity,bool):return error(-32600,'Invalid id')
        version='2025-06-18'
        if method!='initialize' and request.headers.get('mcp-protocol-version','2025-03-26')!=version:raise HTTPException(400,'Unsupported MCP protocol version')
        result={}
        if method=='initialize':result=dict(protocolVersion=version,capabilities=dict(tools=dict(listChanged=False),prompts=dict(listChanged=False)),serverInfo=dict(name='FixRateAI',version='1.0.0'),instructions='Write tools only prepare proposals. The signed-in owner confirms them in /assistant; model tools cannot confirm.')
        elif method=='ping':pass
        elif method=='tools/list':
            tools=[]
            for tool in available(app,v.principal.role).values():
                description=describe(app,tool)
                if tool.mode=='write':
                    description['inputSchema']['properties']['conversation_id']=dict(type='string',format='uuid',description='Existing private chat in /assistant')
                    description['inputSchema']['required'].append('conversation_id')
                tools.append(description)
            result=dict(tools=tools)
        elif method=='prompts/list':result=dict(prompts=[dict(name=a['id'],description=a['description'],arguments=[]) for a in AGENTS])
        elif method=='prompts/get':
            if params.get('name') not in {a['id'] for a in AGENTS}:return error(-32602,'Unknown prompt')
            result=dict(messages=[dict(role='user',content=dict(type='text',text=svc.prompt(params['name'])))])
        elif method=='tools/call':
            tool=available(app,v.principal.role).get(params.get('name'))
            if tool is None:return error(-32602,'Unknown or unavailable tool')
            try:
                arguments=params.get('arguments',{})
                if not isinstance(arguments,dict):raise HTTPException(422,'Аргументы должны быть объектом')
                arguments=dict(arguments);thread_id=arguments.pop('conversation_id',None)
                EXPECTED_PRINCIPAL.set((v.principal.user_id,v.principal.site_id,v.principal.role))
                if tool.mode=='write':
                    try:thread_id=UUID(thread_id)
                    except (ValueError,TypeError,AttributeError):raise HTTPException(422,'Укажите conversation_id своего диалога')
                    thread=svc.conversation(v.session,v.principal,thread_id)
                    if tool.name not in available(app,v.principal.role,thread['agent']):raise HTTPException(403,'Инструмент недоступен агенту диалога')
                    value=await svc.propose(app,v.session,v.principal,thread,tool,arguments,'Предложение MCP: '+tool.title,forwarded(request))
                else:value=bounded(await invoke(app,tool,validate_arguments(app,tool,arguments),forwarded(request)))
                result=dict(content=[dict(type='text',text=svc.dump(value))],isError=False)
            except HTTPException as exc:result=dict(content=[dict(type='text',text=str(exc.detail))],isError=True)
        else:return error(-32601,'Method not found')
        return dict(jsonrpc='2.0',id=identity,result=result)

    @app.get(BASE+'/mcp',include_in_schema=False)
    def mcp_no_stream(v=Depends(views)):
        raise HTTPException(405,'This MCP endpoint uses JSON responses without a standalone SSE stream',headers={'Allow':'POST'})
