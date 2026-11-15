"""Pinned local chat/vision transport. Never pulls models or falls back to a cloud API."""
from dataclasses import dataclass
import json,math,os,re,time,logging
from urllib.parse import urlsplit
from urllib.request import Request,build_opener,ProxyHandler,HTTPRedirectHandler
from urllib.error import HTTPError,URLError
from pydantic import ValidationError


logger=logging.getLogger(__name__)


def agent_wire_schema(schema):
    """Native grammar encodes arguments as an object, not JSON inside JSON.

    Public AgentStep and cloud wire compatibility remain unchanged. This local
    adapter only removes a redundant serialization layer; tool schemas and all
    backend validations still apply after decoding.
    """
    value=schema.model_json_schema()
    if schema.__name__=='AgentStep' and 'AgentCall' in value.get('$defs',{}):
        call=value['$defs']['AgentCall']
        call['properties']['arguments_json']=dict(type='object',description='Tool arguments as a JSON OBJECT, never a string. Only use fields supported by the selected tool.',
            properties={**{key:dict(type='object',additionalProperties=True) for key in ('path','query','body','view')},'name':dict(type='string')},additionalProperties=False)
    return value


def decode_agent_wire(schema,value):
    if schema.__name__!='AgentStep':return schema.model_validate_json(value)
    decoded=json.loads(value)
    if isinstance(decoded,dict) and isinstance(decoded.get('calls'),list):
        for call in decoded['calls']:
            if isinstance(call,dict) and isinstance(call.get('arguments_json'),dict):
                call['arguments_json']=json.dumps(call['arguments_json'],ensure_ascii=False,separators=(',',':'))
    return schema.model_validate(decoded)

class OllamaFailure(Exception):
    def __init__(self,code,*,reason='unspecified',attempt=0,validation=None):
        super().__init__(code)
        self.diagnostic=dict(code=code,reason=reason,attempt=attempt,validation=validation or [])


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        raise OllamaFailure('OLLAMA_REDIRECT_REJECTED')


@dataclass(frozen=True)
class OllamaConfig:
    base_url:str
    model:str
    digest:str
    timeout:float=240
    num_ctx:int=32768

    @classmethod
    def from_environment(cls,environment=None):
        env=os.environ if environment is None else environment
        base=env.get('OLLAMA_CHAT_BASE_URL',env.get('OLLAMA_BASE_URL','http://127.0.0.1:11434')).rstrip('/')
        parsed=urlsplit(base)
        if (parsed.scheme!='http' or parsed.hostname not in ('127.0.0.1','localhost','::1','host.docker.internal','ollama','vision')
                or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment):
            raise ValueError('OLLAMA_CHAT_BASE_URL must point to a local Ollama service')
        # Accessing port also validates malformed/out-of-range port strings.
        if parsed.port is not None and not 1<=parsed.port<=65535:raise ValueError('Invalid Ollama port')
        model=env.get('OLLAMA_CHAT_MODEL','qwen3.5:4b-q4_K_M').strip()
        digest=env.get('OLLAMA_CHAT_DIGEST','').strip()
        if not re.fullmatch(r'[A-Za-z0-9._/-]+:[A-Za-z0-9._-]+',model) or 'cloud' in model.casefold():
            raise ValueError('Select an explicit local Ollama model tag')
        if not re.fullmatch(r'sha256:[0-9a-f]{64}',digest):raise ValueError('Pin OLLAMA_CHAT_DIGEST from /api/tags')
        try:timeout=float(env.get('OLLAMA_CHAT_TIMEOUT_SECONDS','240'));num_ctx=int(env.get('OLLAMA_CHAT_NUM_CTX','32768'))
        except ValueError:raise ValueError('Invalid local chat limits') from None
        if not math.isfinite(timeout) or not 0<timeout<=600 or not 4096<=num_ctx<=65536:raise ValueError('Local chat limits are outside supported bounds')
        return cls(base,model,digest,timeout,num_ctx)

    @property
    def model_ref(self):return 'ollama:'+self.model+'@'+self.digest


class OllamaClient:
    def __init__(self,config):
        self.config=config;self.deadline=time.monotonic()+config.timeout;self.response_model=None
        self.opener=build_opener(ProxyHandler({}),NoRedirect())

    def request(self,path,payload=None):
        remaining=self.deadline-time.monotonic()
        if remaining<=0:raise OllamaFailure('OLLAMA_TIMEOUT')
        request=Request(self.config.base_url+path,data=json.dumps(payload,ensure_ascii=False).encode() if payload is not None else None,
                        headers={'Content-Type':'application/json'})
        try:
            with self.opener.open(request,timeout=remaining) as response:raw=response.read(1_048_577)
            if len(raw)>1_048_576:raise OllamaFailure('OLLAMA_INVALID_RESPONSE',reason='response_too_large')
            return json.loads(raw)
        except OllamaFailure:raise
        except HTTPError as exc:raise OllamaFailure('OLLAMA_MODEL_NOT_READY' if exc.code==404 else 'OLLAMA_UNAVAILABLE') from None
        except TimeoutError:raise OllamaFailure('OLLAMA_TIMEOUT') from None
        except (URLError,OSError) as exc:
            raise OllamaFailure('OLLAMA_TIMEOUT' if isinstance(getattr(exc,'reason',None),TimeoutError) else 'OLLAMA_UNAVAILABLE') from None
        except (ValueError,TypeError):raise OllamaFailure('OLLAMA_INVALID_RESPONSE',reason='invalid_transport_json') from None

    def check_model(self):
        tags=self.request('/api/tags')
        if not isinstance(tags,dict) or not isinstance(tags.get('models'),list):raise OllamaFailure('OLLAMA_INVALID_RESPONSE')
        found=next((m for m in tags['models'] if isinstance(m,dict) and m.get('name')==self.config.model),None)
        if not found:raise OllamaFailure('OLLAMA_MODEL_NOT_READY')
        if str(found.get('digest','')).removeprefix('sha256:')!=self.config.digest.removeprefix('sha256:'):
            raise OllamaFailure('OLLAMA_MODEL_CHANGED')
        if found.get('remote_model') or found.get('remote_host'):raise OllamaFailure('OLLAMA_CLOUD_MODEL_REJECTED')

    def chat(self,messages,schema,tokens):
        self.check_model()
        converted=[{key:message[key] for key in ('role','content','images') if key in message} for message in messages]
        payload=dict(model=self.config.model,messages=converted,stream=False,think=False,keep_alive='10m',
                     options=dict(temperature=0 if schema else .2,num_ctx=self.config.num_ctx,num_predict=tokens,repeat_penalty=1.05))
        if schema:
            payload['format']=agent_wire_schema(schema)
            converted=[*converted,dict(role='system',content='Return exactly one JSON object matching this schema. Use exact property names, include required fields. '+json.dumps(payload['format'],ensure_ascii=False))]
            payload['messages']=converted
        for attempt in range(2 if schema else 1):
            raw=self.request('/api/chat',payload)
            try:
                if not isinstance(raw,dict):raise OllamaFailure('OLLAMA_INVALID_RESPONSE',reason='invalid_envelope')
                if raw.get('model')!=self.config.model:raise OllamaFailure('OLLAMA_INVALID_RESPONSE',reason='unexpected_model')
                if raw.get('done') is not True:raise OllamaFailure('OLLAMA_INVALID_RESPONSE',reason='incomplete_response')
                if raw.get('done_reason')=='length':raise OllamaFailure('OLLAMA_INVALID_RESPONSE',reason='token_limit')
                value=raw['message']['content']
                if not isinstance(value,str) or not value.strip():raise OllamaFailure('OLLAMA_INVALID_RESPONSE',reason='empty_content')
                if len(value)>200000:raise OllamaFailure('OLLAMA_INVALID_RESPONSE',reason='content_too_large')
                if schema:result=decode_agent_wire(schema,value)
                else:
                    result=value.strip()
                    if len(result)>32000:raise OllamaFailure('OLLAMA_INVALID_RESPONSE',reason='content_too_large')
                self.response_model=self.config.model_ref
                return result
            except (OllamaFailure,KeyError,TypeError,ValidationError,ValueError) as exc:
                issues=[]
                if isinstance(exc,ValidationError):
                    issues=[dict(path='.'.join(str(p) if isinstance(p,int) or re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]{0,60}',str(p)) else '[field]' for p in error['loc'])[:120],type=error['type']) for error in exc.errors(include_input=False,include_context=False,include_url=False)[:10]]
                reason=exc.diagnostic['reason'] if isinstance(exc,OllamaFailure) else 'schema_validation' if isinstance(exc,ValidationError) else 'invalid_message_structure'
                failure=OllamaFailure('OLLAMA_INVALID_RESPONSE',reason=reason,attempt=attempt+1,validation=issues)
                logger.warning('ollama_response_rejected diagnostic=%s',json.dumps(failure.diagnostic))
                if not schema or attempt or reason in ('unexpected_model','content_too_large','invalid_envelope','incomplete_response'):
                    raise failure from None
                # Retry inference only; never repeat a tool or action. Do not retain malformed output.
                feedback='The previous response did not match the required schema. Return a valid JSON object with all required fields and correct types. Validation fields/types: '+json.dumps(issues)
                if any(e['path'].endswith('arguments_json') for e in issues):
                    feedback+=' arguments_json must be a valid JSON OBJECT with double-quoted keys, never Python syntax, a quoted string, null or an array. For empty arguments use {}. Example call: '+json.dumps(dict(tool='equipment_find',arguments_json=dict(query=dict(q='pump')),explanation='Find equipment'))
                payload['messages']=[*converted,dict(role='system',content=feedback)]
                if reason=='token_limit':payload['options']['num_predict']=min(tokens*2,7000)

    def text(self,messages,tokens=8192):return self.chat(messages,None,tokens)
