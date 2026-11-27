"""Private, site-scoped immutable drafts of source catalogs."""
import hashlib
import hmac
import json
from pathlib import PureWindowsPath
from uuid import UUID

from fastapi import Depends, File, Form, HTTPException, Path, Query, Response, UploadFile
from sqlalchemy import text
from pydantic import ValidationError

from app.catalog_excel import MAX_FILE
from app.catalog_import import PARSER_VERSION, inspect_catalog
from app.schemas.catalog import CatalogPreview, CatalogSaved, CatalogList, CatalogDetail, CatalogOperations, CatalogOperationSource, CatalogSummary
from .management import PREFIX, _audit, _edit, _guard

READ_ROLES = ('director','chief_engineer','engineer','dispatcher','admin')


def token(v, data):
    return hashlib.sha256(f'{v.principal.site_id}:{v.principal.user_id}:{PARSER_VERSION}:{data["source_sha256"]}'.encode()).hexdigest()


def inspect(content):
    try:
        data=inspect_catalog(content)
        CatalogSummary.model_validate(data['summary'])
        for row in data['operations']: CatalogOperationSource.model_validate(row)
        return data
    except ValidationError: raise HTTPException(422,'Некорректная структура каталога; проверьте исходные строки') from None
    except ValueError as error: raise HTTPException(422,str(error)) from None


def operation_summary(row):
    return {key:value for key,value in row.items() if key not in ('raw_cells','calendar_marks')}


def persist_draft(v, filename, content, data):
    """Persist a checked workbook within the caller's authorized write transaction."""
    name=''.join(c for c in PureWindowsPath(filename or 'catalog.xlsx').name if ord(c)>=32)[:256] or 'catalog.xlsx'
    params = dict(site=v.principal.site_id, actor=v.principal.user_id, name=name, sha=data['source_sha256'],
                  parser=PARSER_VERSION, kind=data['source_kind'], file=content,
                  summary=json.dumps(data['summary'],ensure_ascii=False), data=json.dumps(data,ensure_ascii=False))
    identity = v.session.scalar(text('''INSERT INTO regulation_catalog_imports
        (site_id,created_by,filename,source_sha256,parser_version,source_kind,source_file,summary,catalog_data)
        VALUES (:site,:actor,:name,:sha,:parser,:kind,:file,CAST(:summary AS jsonb),CAST(:data AS jsonb))
        ON CONFLICT (site_id,source_sha256,parser_version) DO NOTHING RETURNING import_id'''), params)
    inserted = identity is not None
    if inserted:
        _audit(v,'regulation_catalog_imports',identity,'save_draft',dict(
            sha256=data['source_sha256'],parser_version=PARSER_VERSION,operation_count=len(data['operations'])))
    else:
        identity=v.session.scalar(text('''SELECT import_id FROM regulation_catalog_imports
            WHERE site_id=:site AND source_sha256=:sha AND parser_version=:parser'''),params)
    return dict(import_id=identity,status='draft',already_saved=not inserted,summary=data['summary'],ready_for_real_plan=False)


def header(v, identity):
    _guard(v,*READ_ROLES)
    row = v.session.execute(text('''SELECT import_id,filename,source_sha256,parser_version,source_kind,
        status,created_at,summary,catalog_data->'groups' AS groups,catalog_data->'issues' AS issues,
        catalog_data->'sheet2_diagnostic' AS sheet2_diagnostic,catalog_data->'header_context' AS header_context
        FROM regulation_catalog_imports WHERE site_id=:site AND import_id=:id'''),
        dict(site=v.principal.site_id,id=identity)).mappings().first()
    if row is None: raise HTTPException(404,'Каталог не найден')
    return dict(row)


def register_routes(app, views):
    base = PREFIX+'/catalog-imports'

    @app.post(base+'/preview', response_model=CatalogPreview)
    def preview(response:Response, file:UploadFile=File(...),v=Depends(views)):
        _guard(v,'chief_engineer','admin',permission='prepare_catalog')
        data=inspect(file.file.read(MAX_FILE+1))
        response.headers['Cache-Control']='private, no-store'
        return dict(format='hvac_catalog',preview_token=token(v,data),can_save_draft=True,
            parser_version=PARSER_VERSION,source_sha256=data['source_sha256'],
            summary=data['summary'],groups=data['groups'],issues=data['issues'],
            header_context=data['header_context'],sheet2_diagnostic=data['sheet2_diagnostic'],
            operations=[operation_summary(row) for row in data['operations'][:25]],
            total=data['summary']['operation_count'],ready_for_real_plan=False)

    @app.post(base, status_code=201, response_model=CatalogSaved)
    def save(response:Response,preview_token:str=Form(...,min_length=64,max_length=64,pattern='^[0-9a-f]{64}$'),file:UploadFile=File(...),v=Depends(views)):
        content=file.file.read(MAX_FILE+1)
        _guard(v,'chief_engineer','admin',permission='prepare_catalog')
        data=inspect(content)
        if not hmac.compare_digest(preview_token,token(v,data)):
            raise HTTPException(409,'Файл или контекст изменился. Повторите предпросмотр каталога')
        with _edit(v,roles=('chief_engineer','admin'),exact_roles=True,permission='prepare_catalog'):
            result = persist_draft(v, file.filename, content, data)
        if result['already_saved']:
            response.status_code=200
        response.headers['Cache-Control']='private, no-store'
        return result

    @app.get(base, response_model=CatalogList)
    def list_imports(response:Response,offset:int=Query(0,ge=0,le=1000000),limit:int=Query(25,ge=1,le=25),v=Depends(views)):
        _guard(v,*READ_ROLES)
        response.headers['Cache-Control']='private, no-store'
        rows=v.session.execute(text('''SELECT import_id,filename,source_sha256,parser_version,status,created_at,summary
            FROM regulation_catalog_imports WHERE site_id=:site ORDER BY created_at DESC,import_id LIMIT :limit OFFSET :offset'''),
            dict(site=v.principal.site_id,limit=limit,offset=offset)).mappings().all()
        total=v.session.scalar(text('SELECT count(*) FROM regulation_catalog_imports WHERE site_id=:site'),dict(site=v.principal.site_id))
        return dict(items=[dict(row) for row in rows],total=total)

    @app.get(base+'/{identity}', response_model=CatalogDetail)
    def detail(identity:UUID,response:Response,v=Depends(views)):
        response.headers['Cache-Control']='private, no-store'
        return header(v,identity)

    @app.get(base+'/{identity}/operations', response_model=CatalogOperations)
    def operations(identity:UUID,response:Response,offset:int=Query(0,ge=0,le=1000000),limit:int=Query(25,ge=1,le=25),
                   q:str=Query('',max_length=320),group_id:str=Query('',max_length=128),kind:str=Query('',max_length=32),v=Depends(views)):
        _guard(v,*READ_ROLES)
        # Project out the raw cell grid inside PostgreSQL, not after transferring
        # every operation's 31 cells to Python for a 25-row summary page.
        rows=v.session.scalar(text('''SELECT jsonb_agg(operation - 'raw_cells' - 'calendar_marks'
            ORDER BY (operation->>'row')::int) FROM regulation_catalog_imports c,
            LATERAL jsonb_array_elements(c.catalog_data->'operations') operation
            WHERE c.site_id=:site AND c.import_id=:id'''),dict(site=v.principal.site_id,id=identity))
        if rows is None: raise HTTPException(404,'Каталог не найден')
        needle=q.strip().casefold()
        rows=[row for row in rows if (not group_id or row['group_id']==group_id) and (not kind or row['maintenance_type']==kind)
              and (not needle or needle in ' '.join(str(row.get(k) or '') for k in ('code','title','frequency_raw')).casefold())]
        response.headers['Cache-Control']='private, no-store'
        return dict(items=[operation_summary(row) for row in rows[offset:offset+limit]],total=len(rows))

    @app.get(base+'/{identity}/operations/{row_number}', response_model=CatalogOperationSource)
    def operation(identity:UUID,response:Response,row_number:int=Path(...,ge=1,le=1048576),v=Depends(views)):
        _guard(v,*READ_ROLES)
        row=v.session.scalar(text('''SELECT operation FROM regulation_catalog_imports c,
            LATERAL jsonb_array_elements(c.catalog_data->'operations') operation
            WHERE c.site_id=:site AND c.import_id=:id AND (operation->>'row')::int=:row'''),
            dict(site=v.principal.site_id,id=identity,row=row_number))
        if row is None: raise HTTPException(404,'Строка каталога не найдена')
        response.headers['Cache-Control']='private, no-store'
        return row

    @app.get(base+'/{identity}/source')
    def source(identity:UUID,v=Depends(views)):
        _guard(v,*READ_ROLES)
        data=v.session.scalar(text('SELECT source_file FROM regulation_catalog_imports WHERE site_id=:site AND import_id=:id'),dict(site=v.principal.site_id,id=identity))
        if data is None: raise HTTPException(404,'Каталог не найден')
        return Response(bytes(data),media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                        headers={'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff','Content-Disposition':'attachment; filename="catalog-source.xlsx"'})
