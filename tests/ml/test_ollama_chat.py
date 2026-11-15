"""Actual loopback HTTP: schemas, prose, images, pinning, failures and no cloud fallback."""
from dataclasses import replace
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from threading import Thread
import json,time
import pytest
from app.schemas.assistant import ToolSelection
from ml_service.app.providers.ollama import OllamaClient,OllamaConfig,OllamaFailure

MODEL='qwen3.5:4b-q4_K_M';DIGEST='sha256:'+'a'*64

@pytest.fixture
def endpoint():
    state=dict(calls=[],digest=DIGEST,remote=False,status=200,reason='stop',model=MODEL,content='Подробный ответ по исходным данным.',done=True)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
            state['calls'].append((self.path,None));self.send_response(200);self.end_headers()
            self.wfile.write(json.dumps(dict(models=[dict(name=MODEL,digest=state['digest'],remote_host='cloud.example' if state['remote'] else None)])).encode())
        def do_POST(self):
            body=json.loads(self.rfile.read(int(self.headers['Content-Length'])));state['calls'].append((self.path,body))
            self.send_response(state['status'])
            if state['status']==307:self.send_header('Location','https://example.test/leak')
            self.end_headers()
            value=dict(model=state['model'],done=state['done'],done_reason=state['reason'],message=dict(content=state['content'],thinking='DO NOT EXPOSE'))
            self.wfile.write(json.dumps(value).encode())
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);worker=Thread(target=server.serve_forever,daemon=True);worker.start()
    yield state,OllamaConfig(f'http://127.0.0.1:{server.server_port}',MODEL,DIGEST)
    server.shutdown();server.server_close();worker.join()


def test_prose_is_native_local_text_and_images_and_has_no_schema(endpoint):
    state,config=endpoint;client=OllamaClient(config)
    assert client.text([dict(role='user',content='Анализ',images=['fixture'])])==state['content']
    assert [p for p,_ in state['calls']]==['/api/tags','/api/chat']
    body=state['calls'][-1][1]
    assert 'format' not in body and body['stream'] is False and body['messages'][0]['images']==['fixture']
    assert body['options']['num_ctx']==32768 and body['options']['num_predict']==8192
    assert client.response_model==config.model_ref
    assert 'DO NOT EXPOSE' not in client.text([dict(role='user',content='Next')])


def test_structured_decisions_use_schema_and_current_model_pin(endpoint):
    state,config=endpoint;state['content']='{"tools":[],"workbook_ids":[]}'
    result=OllamaClient(config).chat([dict(role='user',content='hello')],ToolSelection,1200)
    assert result.tools==[]
    assert state['calls'][-1][1]['format']==ToolSelection.model_json_schema()
    assert state['calls'][-1][1]['options']['temperature']==0

def test_invalid_structured_decision_retries_inference_once_without_executing_tools(endpoint,monkeypatch):
    _,config=endpoint;client=OllamaClient(config);calls=[]
    def request(path,payload=None):
        if path=='/api/tags':return {'models':[{'name':MODEL,'digest':DIGEST}]}
        calls.append(payload)
        content='{"tools": 123}' if len(calls)==1 else '{"tools":[],"workbook_ids":[]}'
        return {'model':MODEL,'done':True,'done_reason':'stop','message':{'content':content}}
    monkeypatch.setattr(client,'request',request)
    assert client.chat([{'role':'user','content':'тест'}],ToolSelection,1200).tools==[]
    assert len(calls)==2 and 'previous response' in calls[-1]['messages'][-1]['content']
    assert '{"tools": 123}' not in json.dumps(calls[-1])


def test_schema_failure_reports_reason_and_safe_validation_not_output(endpoint,caplog):
    state,config=endpoint;state['content']='{"tools":"PRIVATE_SECRET_NOT_A_LIST"}'
    with pytest.raises(OllamaFailure) as error:OllamaClient(config).chat([],ToolSelection,1200)
    detail=error.value.diagnostic
    assert detail['reason']=='schema_validation' and detail['attempt']==2
    assert detail['validation'][0]['path']=='tools'
    assert 'PRIVATE_SECRET' not in caplog.text and 'DO NOT EXPOSE' not in caplog.text
    assert len([path for path,_ in state['calls'] if path=='/api/chat'])==2


def test_token_limit_retries_schema_once_with_bounded_budget(endpoint,monkeypatch):
    _,config=endpoint;client=OllamaClient(config);budgets=[]
    def request(path,payload=None):
        if path=='/api/tags':return dict(models=[dict(name=MODEL,digest=DIGEST)])
        budgets.append(payload['options']['num_predict'])
        return dict(model=MODEL,done=True,done_reason='length' if len(budgets)==1 else 'stop',message=dict(content='{"tools":[],"workbook_ids":[]}'))
    monkeypatch.setattr(client,'request',request)
    assert client.chat([],ToolSelection,1200).tools==[] and budgets==[1200,2400]


def test_plain_text_failure_is_not_hidden_or_retried(endpoint):
    state,config=endpoint;state['content']=''
    with pytest.raises(OllamaFailure) as error:OllamaClient(config).text([])
    assert error.value.diagnostic['reason']=='empty_content'
    assert len([path for path,_ in state['calls'] if path=='/api/chat'])==1


@pytest.mark.parametrize('change,code',[('digest','OLLAMA_MODEL_CHANGED'),('remote','OLLAMA_CLOUD_MODEL_REJECTED')])
def test_wrong_or_remote_model_is_rejected_before_inference(endpoint,change,code):
    state,config=endpoint;state[change]='b'*64 if change=='digest' else True
    with pytest.raises(OllamaFailure,match=code):OllamaClient(config).text([])
    assert len(state['calls'])==1


@pytest.mark.parametrize('field,value',[('done',False),('reason','length'),('model','other:4b'),('content','  ')])
def test_incomplete_wrong_model_or_empty_output_is_never_success(endpoint,field,value):
    state,config=endpoint;state[field]=value
    with pytest.raises(OllamaFailure,match='OLLAMA_INVALID_RESPONSE'):OllamaClient(config).text([])


def test_redirect_and_expired_deadline_never_dispatch_to_external_servers(endpoint):
    state,config=endpoint;state['status']=307
    with pytest.raises(OllamaFailure,match='OLLAMA_REDIRECT_REJECTED'):OllamaClient(config).text([])
    client=OllamaClient(config);client.deadline=time.monotonic()-1;state['calls'].clear()
    with pytest.raises(OllamaFailure,match='OLLAMA_TIMEOUT'):client.text([])
    assert not state['calls']


@pytest.mark.parametrize('key,value',[('OLLAMA_CHAT_BASE_URL','https://evil.example'),('OLLAMA_CHAT_BASE_URL','http://user:secret@localhost:11434'),
    ('OLLAMA_CHAT_BASE_URL','http://127.0.0.1:11434/api'),('OLLAMA_CHAT_BASE_URL','http://localhost:11434/?secret=x'),
    ('OLLAMA_CHAT_MODEL','model:cloud'),('OLLAMA_CHAT_DIGEST',''),('OLLAMA_CHAT_TIMEOUT_SECONDS','nan'),('OLLAMA_CHAT_NUM_CTX','1000000')])
def test_invalid_endpoints_cloud_tags_and_unbounded_settings_are_rejected(key,value):
    env=dict(OLLAMA_CHAT_MODEL=MODEL,OLLAMA_CHAT_DIGEST=DIGEST);env[key]=value
    with pytest.raises(ValueError):OllamaConfig.from_environment(env)


def test_docker_host_endpoint_and_configured_provider_are_explicit(monkeypatch):
    from app.assistant.service import configured,provider,turn_timeout_seconds
    monkeypatch.setenv('ASSISTANT_PROVIDER','ollama');monkeypatch.setenv('OLLAMA_CHAT_MODEL',MODEL);monkeypatch.setenv('OLLAMA_CHAT_DIGEST',DIGEST)
    monkeypatch.setenv('OLLAMA_CHAT_BASE_URL','http://host.docker.internal:11434')
    assert configured()==dict(available=True,model_ref='ollama:'+MODEL+'@'+DIGEST)
    assert isinstance(provider(),OllamaClient) and turn_timeout_seconds()==270
    monkeypatch.setenv('ASSISTANT_PROVIDER','typo');assert not configured()['available']


def test_existing_photo_pipeline_accepts_the_same_pinned_native_host(monkeypatch):
    from ml_service.app.cv.local_vision import LocalVisionConfig
    monkeypatch.setenv('OLLAMA_BASE_URL','http://host.docker.internal:11434');monkeypatch.setenv('OLLAMA_VISION_MODEL',MODEL);monkeypatch.setenv('OLLAMA_VISION_DIGEST',DIGEST)
    assert LocalVisionConfig.from_environment().base_url=='http://host.docker.internal:11434'


@pytest.mark.parametrize('broken',['{query: {q: "PRIVATE_SECRET"}}','null','[]','','{"query":{"q":"PRIVATE_SECRET"'])
def test_nested_argument_json_feedback_is_specific_bounded_and_does_not_echo_bad_output(endpoint,monkeypatch,broken):
    from app.schemas.assistant import AgentStep
    _,config=endpoint;client=OllamaClient(config);calls=[]
    def request(path,payload=None):
        if path=='/api/tags':return dict(models=[dict(name=MODEL,digest=DIGEST)])
        calls.append(payload)
        reply=dict(answer='',calls=[dict(tool='equipment_find',arguments_json=broken if len(calls)==1 else '{}',explanation='Read authorized equipment')])
        return dict(model=MODEL,done=True,done_reason='stop',message=dict(content=json.dumps(reply)))
    monkeypatch.setattr(client,'request',request)
    answer=client.chat([dict(role='user',content='Read equipment')],AgentStep,3500)
    assert answer.calls[0].arguments=={} and len(calls)==2
    feedback=calls[-1]['messages'][-1]['content']
    assert 'arguments_json' in feedback and 'valid JSON OBJECT' in feedback
    assert 'PRIVATE_SECRET' not in json.dumps(calls[-1])


@pytest.mark.parametrize('arguments',[
    {},
    {'query':{'q':'TEST ONLY "quoted" value'}},
    {'path':{'user_id':'12345678-1234-1234-1234-123456789abc'}},
    {'path':{'equipment_id':'12345678-1234-1234-1234-123456789abc'},'body':{'expected_revision':2,'name':'TEST ONLY rename'}},
    {'view':{'path':['items'],'limit':5}},
])
def test_local_native_object_arguments_roundtrip_without_nested_quoting(endpoint,arguments):
    from app.schemas.assistant import AgentStep
    state,config=endpoint
    state['content']=json.dumps(dict(answer='',calls=[dict(tool='TEST_ONLY',arguments_json=arguments,explanation='Transport fixture, no domain invocation')]))
    value=OllamaClient(config).chat([dict(role='user',content='Transport fixture')],AgentStep,3500)
    assert value.calls[0].arguments==arguments
    assert len([p for p,_ in state['calls'] if p=='/api/chat'])==1
    wire=state['calls'][-1][1]['format']['$defs']['AgentCall']['properties']['arguments_json']
    assert wire['type']=='object' and wire['additionalProperties'] is False
    # Public/cloud DTO still requires a JSON string; native decoding is an
    # explicit local adapter, not a relaxation of the canonical contract.
    assert AgentStep.model_json_schema()['$defs']['AgentCall']['properties']['arguments_json']['type']=='string'
