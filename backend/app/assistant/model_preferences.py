"""Actor/site/role scoped preference and an immutable per-turn provider snapshot."""
import os
from dataclasses import replace
from fastapi import HTTPException
from sqlalchemy import text
from ml_service.app.providers.aitunnel import AITunnelConfig
from ml_service.app.providers.ollama import OllamaConfig

def config(selection=None):
    name=selection['provider'] if selection else os.environ.get('ASSISTANT_PROVIDER','aitunnel').strip().lower()
    if name=='ollama':
        values=dict(os.environ)
        if selection:values.update(OLLAMA_CHAT_MODEL=selection['model'],OLLAMA_CHAT_DIGEST=selection['digest'])
        return OllamaConfig.from_environment(values)
    if name=='aitunnel':
        values=dict(os.environ)
        if selection:values['AITUNNEL_CHAT_MODEL']=selection['model']
        value=AITunnelConfig.from_environment('chat',values)
        return replace(value,allow_model_alias=bool(selection.get('is_alias') or selection['model']=='auto')) if selection else value
    raise ValueError('ASSISTANT_PROVIDER must be aitunnel or ollama')

def default_selection():
    try:
        value=config()
        return dict(provider='ollama',model=value.model,digest=value.digest) if isinstance(value,OllamaConfig) else dict(provider='aitunnel',model=value.model,**({'is_alias':True} if value.allow_model_alias else {}))
    except ValueError:return None

def available(selection):
    try:
        value=config(selection)
        return isinstance(value,OllamaConfig) or bool(value.api_key)
    except (ValueError,KeyError):return False

def read(session,principal):
    row=session.execute(text('SELECT provider,model,digest,is_alias,revision FROM assistant_model_preferences WHERE user_id=:user AND site_id=:site AND role=:role'),dict(user=principal.user_id,site=principal.site_id,role=principal.role)).mappings().first()
    selection=(dict(provider=row['provider'],model=row['model'],**({'digest':row['digest']} if row['provider']=='ollama' else {'is_alias':True} if row['is_alias'] else {})) if row else default_selection())
    return dict(selection=selection,revision=row['revision'] if row else 0,is_default=row is None,available=available(selection))

def save(session,principal,selection,expected_revision):
    params=dict(user=principal.user_id,site=principal.site_id,role=principal.role,provider=selection['provider'],model=selection['model'],digest=selection.get('digest'),is_alias=selection.get('is_alias',False),revision=expected_revision)
    if expected_revision==0:
        statement='''INSERT INTO assistant_model_preferences(user_id,site_id,role,provider,model,digest,is_alias)
          VALUES (:user,:site,:role,:provider,:model,:digest,:is_alias) ON CONFLICT DO NOTHING RETURNING revision'''
    else:
        statement='''UPDATE assistant_model_preferences SET provider=:provider,model=:model,digest=:digest,is_alias=:is_alias,
          revision=revision+1,updated_at=now() WHERE user_id=:user AND site_id=:site AND role=:role AND revision=:revision RETURNING revision'''
    if session.scalar(text(statement),params) is None:raise HTTPException(409,'Выбор модели уже изменён в другом окне. Обновите его и повторите действие.')
    session.commit()
    return read(session,principal)

def snapshot(preference):
    return {**preference['selection'],'preference_revision':preference['revision']} if preference['selection'] else None
