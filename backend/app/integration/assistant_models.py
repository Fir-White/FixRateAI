"""Private model discovery and the user's own preference; credentials never leave the server."""
from fastapi import Depends,Response,Query,HTTPException
from app.schemas.assistant import ChatModelPreference
from app.assistant import model_catalog,model_preferences

def register_routes(app,views):
    app.state.assistant_model_catalog=model_catalog.CatalogCache()
    @app.get('/api/v1/assistant/models')
    def models(response:Response,refresh:bool=False,q:str=Query('',max_length=100),v=Depends(views)):
        response.headers['Cache-Control']='private, no-store'
        return model_catalog.catalog(app,refresh,q)
    @app.get('/api/v1/assistant/model-preference')
    def preference(response:Response,v=Depends(views)):
        response.headers['Cache-Control']='private, no-store'
        return model_preferences.read(v.session,v.principal)
    @app.post('/api/v1/assistant/model-preference')
    def choose(command:ChatModelPreference,response:Response,v=Depends(views)):
        response.headers['Cache-Control']='private, no-store'
        if model_preferences.read(v.session,v.principal)['revision']!=command.expected_revision:
            raise HTTPException(409,'Выбор модели уже изменён в другом окне. Обновите его и повторите действие.')
        try:selection=model_catalog.validate_choice(app,command.provider,command.model)
        except model_catalog.CatalogFailure:raise HTTPException(503,'Провайдер моделей недоступен. Выбор не изменён.') from None
        return model_preferences.save(v.session,v.principal,selection,command.expected_revision)
