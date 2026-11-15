"""Private chat workspace, explicit confirmations, and stateless MCP tools transport."""
from datetime import timedelta
import json
from uuid import UUID,uuid4
from typing import Literal
from fastapi import BackgroundTasks,Depends,HTTPException,Query,Request,Response,UploadFile,File
from fastapi.responses import JSONResponse,FileResponse
from sqlalchemy import text
from app.schemas.assistant import ConversationCreate,MessageCreate,ConfirmAction
from app.assistant import service as svc
from app.assistant.tools import available,catalog,describe,validate_arguments,invoke,bounded,EXPECTED_PRINCIPAL
from app.assistant.attachments import SCOPE,COOKIE_EFFECTS,MAX_FILE,public as public_file,content as file_content

BASE='/api/v1/assistant'
AGENTS=[dict(id='assistant',title='Ассистент',description='Оборудование, задания и повседневная работа'),
        dict(id='planner',title='Планирование',description='Версии плана, распределение и нагрузка'),
        dict(id='photo',title='Фотоанализ',description='Проверка сохранённых фотоотчётов')]

def forwarded(request):
    # Secrets remain only in memory and never enter prompts, DB records or tool results.
    return {key:request.headers[key] for key in ('cookie','x-csrf-token') if key in request.headers}

def register_routes(app,views):
    from .assistant_workspace import register_routes as register_workspace
    register_workspace(app,views)
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
        v.session.execute(text("UPDATE assistant_turns SET status='failed',error_code='ASSISTANT_INTERRUPTED',answer='Ответ прерван. Сообщение сохранено; отправьте новый запрос.',finished_at=now() WHERE conversation_id=:id AND status='running' AND created_at<:cutoff"),dict(id=identity,cutoff=svc.now()-timedelta(seconds=svc.turn_timeout_seconds())))
        turns=v.session.execute(text('SELECT * FROM assistant_turns WHERE conversation_id=:id ORDER BY created_at DESC,turn_id DESC LIMIT 25 OFFSET :offset'),dict(id=identity,offset=offset)).mappings().all()
        count=v.session.scalar(text('SELECT count(*) FROM assistant_turns WHERE conversation_id=:id'),dict(id=identity))
        rows=v.session.execute(text('''SELECT * FROM assistant_actions WHERE conversation_id=:id AND
            (turn_id=ANY(CAST(:turns AS uuid[])) OR turn_id IS NULL) ORDER BY created_at LIMIT 100'''),dict(id=identity,turns=[r['turn_id'] for r in turns])).mappings().all()
        files=v.session.execute(text('''SELECT a.*,EXISTS(SELECT 1 FROM assistant_turn_attachments f WHERE f.attachment_id=a.attachment_id) AS sent
            FROM assistant_attachments a WHERE a.conversation_id=:id ORDER BY a.created_at DESC,a.attachment_id LIMIT 20'''),dict(id=identity)).mappings().all()
        linked=v.session.execute(text('''SELECT a.*,f.turn_id FROM assistant_turn_attachments f
            JOIN assistant_attachments a ON a.attachment_id=f.attachment_id AND a.conversation_id=f.conversation_id
            WHERE f.conversation_id=:id AND f.turn_id=ANY(CAST(:turns AS uuid[])) ORDER BY f.position'''),
            dict(id=identity,turns=[r['turn_id'] for r in turns])).mappings().all()
        by_turn={}
        for row in linked:by_turn.setdefault(row['turn_id'],[]).append(public_file(row))
        return dict(conversation=thread,turns=list(reversed([dict(r,attachments=by_turn.get(r['turn_id'],[])) for r in turns])),total=count,
            actions=[svc.public_action(r) for r in rows],attachments=[public_file(r) for r in files],pending_attachments=[public_file(r) for r in files if not r['sent']])

    @app.post(BASE+'/conversations/{identity}/turns/{turn_id}/stop')
    def stop_turn(identity:UUID,turn_id:UUID,v=Depends(views)):
        svc.conversation(v.session,v.principal,identity)
        row=v.session.execute(text("UPDATE assistant_turns SET status='failed',error_code='ASSISTANT_STOPPED',answer='Ответ остановлен по вашей просьбе.',finished_at=now() WHERE conversation_id=:id AND turn_id=:turn AND status='running' RETURNING turn_id"),dict(id=identity,turn=turn_id)).first()
        if row:
            v.session.execute(text("UPDATE assistant_actions SET status='rejected',finished_at=now() WHERE conversation_id=:id AND turn_id=:turn AND status='proposed'"),dict(id=identity,turn=turn_id))
            v.session.commit()
        elif not v.session.scalar(text('SELECT EXISTS(SELECT 1 FROM assistant_turns WHERE conversation_id=:id AND turn_id=:turn)'),dict(id=identity,turn=turn_id)):
            raise HTTPException(404,'Сообщение не найдено')
        return dict(stopped=bool(row))

    @app.delete(BASE+'/conversations/{identity}')
    def delete_conversation(identity:UUID,v=Depends(views)):
        from app.storage import safe_storage_path
        svc.conversation(v.session,v.principal,identity)
        # Lock turns before the conversation, matching the proposal lock order.
        v.session.execute(text('SELECT turn_id FROM assistant_turns WHERE conversation_id=:id FOR UPDATE'),dict(id=identity)).all()
        svc.conversation(v.session,v.principal,identity,lock=True)
        actions=v.session.execute(text('SELECT status FROM assistant_actions WHERE conversation_id=:id FOR UPDATE'),dict(id=identity)).scalars().all()
        if 'executing' in actions:raise HTTPException(409,'Дождитесь завершения подтверждённого действия перед удалением чата')
        keys=list(v.session.scalars(text('SELECT storage_key FROM assistant_attachments WHERE conversation_id=:id'),dict(id=identity)))
        paths=[safe_storage_path(app.state.settings.photo_storage_root,key) for key in keys]
        for table in ('assistant_actions','assistant_turn_attachments','assistant_attachments','assistant_turns'):
            v.session.execute(text('DELETE FROM '+table+' WHERE conversation_id=:id'),dict(id=identity))
        v.session.execute(text('DELETE FROM assistant_conversations WHERE conversation_id=:id'),dict(id=identity))
        v.session.commit()
        for path in paths:
            try:path.unlink(missing_ok=True)
            except OSError:svc.logger.warning('assistant_attachment_cleanup_failed conversation=%s',identity)
        return dict(deleted=True)

    @app.post(BASE+'/conversations/{identity}/attachments',status_code=201)
    def upload(identity:UUID,file:UploadFile=File(...),v=Depends(views)):
        from pathlib import PureWindowsPath
        import hashlib
        from app.files import validate_upload
        from app.storage import safe_storage_path
        svc.conversation(v.session,v.principal,identity,lock=True)
        filename=PureWindowsPath(file.filename or 'file').name[:160]
        blob=file.file.read(MAX_FILE+1)
        if not blob or len(blob)>MAX_FILE:raise HTTPException(413,'Вложение должно быть от 1 байта до 10 МиБ')
        suffix=PureWindowsPath(filename).suffix.lower()
        if suffix=='.xlsx':
            if not blob.startswith(b'PK'):raise HTTPException(422,'Нужен настоящий файл Excel XLSX')
            mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        else:
            try:mime=validate_upload(blob,filename,file.content_type)
            except Exception:raise HTTPException(422,'Прикрепите XLSX или фотографию JPEG/PNG/WebP') from None
        sha=hashlib.sha256(blob).hexdigest()
        old=v.session.execute(text('SELECT * FROM assistant_attachments WHERE conversation_id=:id AND sha256=:sha AND original_name=:name'),dict(id=identity,sha=sha,name=filename)).mappings().first()
        if old:return public_file(old)
        count,total=v.session.execute(text('SELECT count(*),coalesce(sum(size_bytes),0) FROM assistant_attachments WHERE conversation_id=:id'),dict(id=identity)).one()
        if count>=20 or total+len(blob)>104857600:raise HTTPException(413,'В одном диалоге — до 20 вложений и 100 МиБ')
        file_id=uuid4();key=f'{v.principal.site_id}/assistant/{identity}/{file_id}'
        path=safe_storage_path(app.state.settings.photo_storage_root,key)
        try:
            path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(blob)
            v.session.execute(text('INSERT INTO assistant_attachments(attachment_id,conversation_id,original_name,mime_type,size_bytes,sha256,storage_key) VALUES (:id,:conversation,:name,:mime,:size,:sha,:key)'),dict(id=file_id,conversation=identity,name=filename,mime=mime,size=len(blob),sha=sha,key=key))
            v.session.commit()
        except BaseException:
            path.unlink(missing_ok=True);raise
        return public_file(v.session.execute(text('SELECT * FROM assistant_attachments WHERE attachment_id=:id'),dict(id=file_id)).mappings().one())

    @app.get(BASE+'/attachments/{identity}')
    def download(identity:UUID,v=Depends(views)):
        from app.storage import safe_storage_path
        row=v.session.execute(text('''SELECT a.* FROM assistant_attachments a JOIN assistant_conversations c USING(conversation_id)
            WHERE a.attachment_id=:id AND c.user_id=:user AND c.site_id=:site AND c.role=:role'''),dict(id=identity,user=v.principal.user_id,site=v.principal.site_id,role=v.principal.role)).mappings().first()
        if row is None:raise HTTPException(404,'Вложение не найдено')
        SCOPE.set((row['conversation_id'],v.principal.user_id,v.principal.site_id,v.principal.role))
        file_content(app,identity)
        return FileResponse(safe_storage_path(app.state.settings.photo_storage_root,row['storage_key']),filename=row['original_name'],media_type=row['mime_type'],headers={'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff'})

    @app.get(BASE+'/conversations/{identity}/attachments/{attachment_id}/content')
    def attachment_read(identity:UUID,attachment_id:UUID,response:Response,sheet:str|None=Query(None,max_length=255),
                        offset:int=Query(0,ge=0),limit:int=Query(25,ge=1,le=25),q:str=Query('',max_length=200),v=Depends(views)):
        from app.assistant.workbooks import page
        svc.conversation(v.session,v.principal,identity)
        SCOPE.set((identity,v.principal.user_id,v.principal.site_id,v.principal.role))
        response.headers['Cache-Control']='private, no-store'
        return page(app,attachment_id,sheet,offset,limit,q)

    @app.post(BASE+'/conversations/{identity}/messages',status_code=202)
    def message(identity:UUID,command:MessageCreate,background:BackgroundTasks,request:Request,v=Depends(views)):
        thread=svc.conversation(v.session,v.principal,identity,lock=True)
        message_content=command.content or 'Проанализируй прикреплённые файлы.'
        previous=v.session.execute(text('SELECT * FROM assistant_turns WHERE conversation_id=:id AND request_key=:key'),dict(id=identity,key=command.idempotency_key)).mappings().first()
        if previous:
            previous_files=list(v.session.scalars(text('SELECT attachment_id FROM assistant_turn_attachments WHERE turn_id=:id ORDER BY position'),dict(id=previous['turn_id'])))
            if previous['content']!=message_content or (command.attachment_ids is not None and previous_files!=command.attachment_ids):
                raise HTTPException(409,'Ключ повтора принадлежит другому сообщению или набору файлов')
            return dict(previous)
        selected=command.attachment_ids
        if selected is None:
            selected=list(v.session.scalars(text('''SELECT a.attachment_id FROM assistant_attachments a WHERE a.conversation_id=:id
                AND NOT EXISTS(SELECT 1 FROM assistant_turn_attachments f WHERE f.attachment_id=a.attachment_id)
                ORDER BY a.created_at,a.attachment_id LIMIT 20'''),dict(id=identity)))
        files=v.session.execute(text('SELECT * FROM assistant_attachments WHERE conversation_id=:id AND attachment_id=ANY(CAST(:files AS uuid[]))'),
            dict(id=identity,files=selected)).mappings().all()
        if len(files)!=len(selected):raise HTTPException(404,'Вложение не найдено в этом диалоге')
        if sum(row['mime_type'].startswith('image/') for row in files)>4:raise HTTPException(422,'К одному сообщению можно отправить не больше четырёх изображений')
        if v.session.scalar(text("SELECT EXISTS(SELECT 1 FROM assistant_turns WHERE conversation_id=:id AND status='running' AND created_at>:cutoff)"),dict(id=identity,cutoff=svc.now()-timedelta(seconds=svc.turn_timeout_seconds()))):
            raise HTTPException(409,'Дождитесь ответа на предыдущее сообщение')
        if not svc.configured()['available'] and not hasattr(app.state,'assistant_provider_factory'):raise HTTPException(503,'ИИ не настроен. Проверьте провайдер и модель чата на сервере.')
        if not svc.SLOTS.acquire(blocking=False):raise HTTPException(429,'ИИ сейчас занят. Попробуйте через несколько секунд.')
        turn=uuid4()
        try:
            v.session.execute(text("INSERT INTO assistant_turns(turn_id,conversation_id,request_key,content,status,prompt_version) VALUES (:id,:conversation,:key,:content,'running',:prompt)"),
                dict(id=turn,conversation=identity,key=command.idempotency_key,content=message_content,prompt=svc.PROMPT_VERSION))
            if selected:
                v.session.execute(text('INSERT INTO assistant_turn_attachments(turn_id,attachment_id,conversation_id,position) VALUES (:turn,:file,:conversation,:position)'),
                    [dict(turn=turn,file=file_id,conversation=identity,position=position) for position,file_id in enumerate(selected)])
            title=command.content or ('Файл: '+files[0]['original_name'])
            v.session.execute(text("UPDATE assistant_conversations SET updated_at=now(),title=CASE WHEN title='Новый диалог' THEN :title ELSE title END WHERE conversation_id=:id"),dict(id=identity,title=title[:100]))
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
    async def confirm(identity:UUID,command:ConfirmAction,request:Request,response:Response,v=Depends(views)):
        row=svc.action(v.session,v.principal,identity,lock=True)
        if command.payload_sha256!=row['payload_sha256']:raise HTTPException(409,'Состав предложения изменился')
        if row['status']!='proposed':return svc.public_action(row)
        if row['expires_at']<svc.now():raise HTTPException(409,'Предложение истекло. Подготовьте новое по свежим данным.')
        cookies=[];token=COOKIE_EFFECTS.set(cookies)
        try:result=await svc.confirm(app,v.session,v.principal,row,forwarded(request),command.secret_values)
        finally:COOKIE_EFFECTS.reset(token)
        for cookie in cookies:response.raw_headers.append((b'set-cookie',cookie.encode('latin-1')))
        return result

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
                from app.assistant.tools import file_fields
                if tool.mode=='write' or file_fields(app,tool):
                    description['inputSchema']['properties']['conversation_id']=dict(type='string',format='uuid',description='Existing private chat in /assistant')
                    description['inputSchema']['required'].append('conversation_id')
                tools.append(description)
            result=dict(tools=tools)
        elif method=='prompts/list':result=dict(prompts=[dict(name=a['id'],description=a['description'],arguments=[]) for a in AGENTS])
        elif method=='prompts/get':
            if not isinstance(params.get('name'),str) or params['name'] not in {a['id'] for a in AGENTS}:return error(-32602,'Unknown prompt')
            result=dict(messages=[dict(role='user',content=dict(type='text',text=svc.prompt(params['name'])))])
        elif method=='tools/call':
            if not isinstance(params.get('name'),str):return error(-32602,'Tool name must be a string')
            tool=available(app,v.principal.role).get(params.get('name'))
            if tool is None:return error(-32602,'Unknown or unavailable tool')
            try:
                arguments=params.get('arguments',{})
                if not isinstance(arguments,dict):raise HTTPException(422,'Аргументы должны быть объектом')
                arguments=dict(arguments);thread_id=arguments.pop('conversation_id',None)
                EXPECTED_PRINCIPAL.set((v.principal.user_id,v.principal.site_id,v.principal.role))
                from app.assistant.tools import file_fields
                if tool.mode=='write' or file_fields(app,tool):
                    try:thread_id=UUID(thread_id)
                    except (ValueError,TypeError,AttributeError):raise HTTPException(422,'Укажите conversation_id своего диалога')
                    thread=svc.conversation(v.session,v.principal,thread_id)
                    SCOPE.set((thread_id,v.principal.user_id,v.principal.site_id,v.principal.role))
                    if tool.name not in available(app,v.principal.role,'assistant'):raise HTTPException(403,'Инструмент недоступен агенту диалога')
                    if tool.mode=='write':value=await svc.propose(app,v.session,v.principal,thread,tool,arguments,'Предложение MCP: '+tool.title,forwarded(request))
                    else:value=bounded(await invoke(app,tool,validate_arguments(app,tool,arguments),forwarded(request)))
                else:value=bounded(await invoke(app,tool,validate_arguments(app,tool,arguments),forwarded(request)))
                result=dict(content=[dict(type='text',text=svc.dump(value))],isError=False)
            except HTTPException as exc:result=dict(content=[dict(type='text',text=str(exc.detail))],isError=True)
        else:return error(-32601,'Method not found')
        return dict(jsonrpc='2.0',id=identity,result=result)

    @app.get(BASE+'/mcp',include_in_schema=False)
    def mcp_no_stream(v=Depends(views)):
        raise HTTPException(405,'This MCP endpoint uses JSON responses without a standalone SSE stream',headers={'Allow':'POST'})
