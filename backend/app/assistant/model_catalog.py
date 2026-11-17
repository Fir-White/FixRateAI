"""Bounded real provider catalogs. No model pulls, prompts, redirects or secret output."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass,field
import hashlib,json,os,re,threading,time
from urllib.request import Request,build_opener,ProxyHandler
from urllib.error import HTTPError,URLError
from urllib.parse import urlsplit
from fastapi import HTTPException
from ml_service.app.providers.aitunnel import AITunnelConfig,NoRedirect

MODEL=re.compile(r'^[A-Za-z0-9._][A-Za-z0-9._:/-]{0,127}$')
DIGEST=re.compile(r'^(?:sha256:)?[0-9a-f]{64}$')
MAX_BYTES=8_388_608

class CatalogFailure(Exception):pass

def local_base():
    base=os.environ.get('OLLAMA_CHAT_BASE_URL',os.environ.get('OLLAMA_BASE_URL','http://127.0.0.1:11434')).rstrip('/')
    p=urlsplit(base)
    if (p.scheme!='http' or p.hostname not in ('127.0.0.1','localhost','::1','host.docker.internal','ollama','vision')
            or p.username or p.password or p.path or p.query or p.fragment or (p.port is not None and not 1<=p.port<=65535)):
        raise ValueError('Invalid local model service')
    return base

def request_json(url,*,key='',body=None):
    headers={'Accept':'application/json'}
    if key:headers['Authorization']='Bearer '+key
    if body is not None:headers['Content-Type']='application/json'
    request=Request(url,data=json.dumps(body).encode('utf-8') if body is not None else None,headers=headers)
    try:
        with build_opener(ProxyHandler({}),NoRedirect()).open(request,timeout=8) as response:raw=response.read(MAX_BYTES+1)
        if len(raw)>MAX_BYTES:raise CatalogFailure('MODEL_CATALOG_TOO_LARGE')
        return json.loads(raw)
    except CatalogFailure:raise
    except json.JSONDecodeError:raise CatalogFailure('MODEL_CATALOG_INVALID_RESPONSE') from None
    except HTTPError as e:raise CatalogFailure('MODEL_CATALOG_AUTH_FAILED' if e.code in (401,403) else 'MODEL_CATALOG_UNAVAILABLE') from None
    except (URLError,OSError,ValueError):raise CatalogFailure('MODEL_CATALOG_UNAVAILABLE') from None
    except Exception:raise CatalogFailure('MODEL_CATALOG_INVALID_RESPONSE') from None

def local_catalog():
    value=request_json(local_base()+'/api/tags')
    if not isinstance(value,dict) or not isinstance(value.get('models'),list):raise CatalogFailure('MODEL_CATALOG_INVALID_RESPONSE')
    rows=[];seen=set()
    if len(value['models'])>2000:raise CatalogFailure('MODEL_CATALOG_TOO_LARGE')
    for item in value['models']:
        if not isinstance(item,dict):raise CatalogFailure('MODEL_CATALOG_INVALID_RESPONSE')
        name=item.get('name');digest=item.get('digest')
        if item.get('remote_host') or item.get('remote_model'):continue
        if not isinstance(name,str) or not MODEL.fullmatch(name) or not isinstance(digest,str) or not DIGEST.fullmatch(digest):
            raise CatalogFailure('MODEL_CATALOG_INVALID_RESPONSE')
        if name in seen:continue
        seen.add(name)
        rows.append(dict(id=name,name=name,digest='sha256:'+digest.removeprefix('sha256:'),selectable='cloud' not in name.casefold(),description='Установлена на этом компьютере'))
    return sorted(rows,key=lambda row:row['id'].casefold())

def cloud_catalog():
    config=AITunnelConfig.from_environment('chat')
    if not config.api_key:raise CatalogFailure('AITUNNEL_NOT_CONFIGURED')
    allowed=request_json(config.base_url+'/models',key=config.api_key)
    public=request_json('https://api.aitunnel.ru/public/aitunnel/models')
    if (not isinstance(allowed,dict) or not isinstance(allowed.get('data'),list)
            or not isinstance(public,dict) or not isinstance(public.get('chat'),dict)):
        raise CatalogFailure('MODEL_CATALOG_INVALID_RESPONSE')
    if len(allowed['data'])>3000:raise CatalogFailure('MODEL_CATALOG_TOO_LARGE')
    chat=public['chat'];other={name for group,items in public.items() if group!='chat' and isinstance(items,dict) for name in items}
    rows=[];seen=set()
    for item in allowed['data']:
        name=item.get('id') if isinstance(item,dict) else None
        if not isinstance(name,str) or not MODEL.fullmatch(name):raise CatalogFailure('MODEL_CATALOG_INVALID_RESPONSE')
        if name in seen or (name not in chat and name in other):continue
        seen.add(name);metadata=chat.get(name,{})
        if not isinstance(metadata,dict):metadata={}
        description=metadata.get('short_description') or metadata.get('description') or ''
        rows.append(dict(id=name,name=name,selectable=True,is_alias=name=='auto' or item.get('owned_by')=='preset',description=str(description)[:250]))
    return sorted(rows,key=lambda row:row['id'].casefold())

@dataclass
class CatalogCache:
    entries:dict=field(default_factory=dict)
    lock:threading.Lock=field(default_factory=threading.Lock)
    provider_locks:dict=field(default_factory=lambda:{p:threading.Lock() for p in ('ollama','aitunnel')})

def cache_for(app):
    # Construct once in route registration, before concurrent requests.
    return app.state.assistant_model_catalog

def provider_catalog(app,provider,refresh=False):
    cache=cache_for(app)
    key=(provider,hashlib.sha256((os.environ.get('AITUNNEL_API_KEY') or os.environ.get('AI_TUNNEL_API_KEY') or '').encode()).hexdigest()) if provider=='aitunnel' else (provider,os.environ.get('OLLAMA_CHAT_BASE_URL',os.environ.get('OLLAMA_BASE_URL','http://127.0.0.1:11434')))
    with cache.provider_locks[provider]:
        with cache.lock:hit=cache.entries.get(key)
        if not refresh and hit and time.monotonic()-hit[0]<hit[1]:return hit[2]
        try:
            rows=local_catalog() if provider=='ollama' else cloud_catalog()
            result=dict(id=provider,name='Локальные модели' if provider=='ollama' else 'AI Tunnel',status='ready',models=rows,error_code=None)
        except (CatalogFailure,ValueError) as e:
            code=str(e) if isinstance(e,CatalogFailure) else 'MODEL_CATALOG_CONFIGURATION_ERROR'
            result=dict(id=provider,name='Локальные модели' if provider=='ollama' else 'AI Tunnel',status='not_configured' if code=='AITUNNEL_NOT_CONFIGURED' else 'unavailable',models=[],error_code=code)
        # Only provider metadata, never the user's selected preference, is shared.
        with cache.lock:
            cache.entries={k:v for k,v in cache.entries.items() if k[0]!=provider}
            cache.entries[key]=(time.monotonic(),60 if result['status']=='ready' else 5,result)
        return result

def catalog(app,refresh=False,q=''):
    # Provider discovery has fixed request/response bounds and no per-model calls.
    with ThreadPoolExecutor(max_workers=2) as pool:
        providers=list(pool.map(lambda name:provider_catalog(app,name,refresh),('ollama','aitunnel')))
    if q:
        providers=[{**p,'models':[m for m in p['models'] if q.casefold() in m['name'].casefold()]} for p in providers]
    return dict(providers=providers)

def validate_choice(app,provider,model):
    group=provider_catalog(app,provider)
    if group['status']!='ready':raise HTTPException(503,'Не удалось проверить список моделей этого провайдера. Повторите обновление списка.')
    item=next((m for m in group['models'] if m['id']==model and m['selectable']),None)
    if item is None:raise HTTPException(422,'Модель отсутствует в доступном каталоге. Обновите список и выберите её заново.')
    if provider=='ollama':
        details=request_json(local_base()+'/api/show',body=dict(model=model))
        capabilities=details.get('capabilities') if isinstance(details,dict) else None
        if not isinstance(capabilities,list) or 'completion' not in capabilities:
            raise HTTPException(422,'Эта локальная модель не поддерживает чат.')
    return dict(provider=provider,model=model,**({'digest':item['digest']} if provider=='ollama' else {'is_alias':True} if item.get('is_alias') else {}))
