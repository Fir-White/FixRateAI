"""Site-scoped registry, installed parts and append-only usage readings."""
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
from pathlib import Path
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo
from fastapi import Depends, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse
from pydantic import ValidationError
from sqlalchemy import text
from app.db.session import service_transaction
from app.files import MAX_BYTES, validate_upload
from app.schemas.registry import BuildingCreate, ComponentCreate, ComponentMetadata, ComponentReplacement, SiteSelection, SystemEdit, UsageReading
from app.security.sessions import COOKIE, Principal, SQL_ROLES, create_session, digest
from app.storage import safe_storage_path
from .assignments import _lock
from .management import PREFIX, _audit, _edit, _equipment, _guard, _revision, equipment_response, service_configurations


def catalog_lock(v):
    v.session.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:key,0))'),dict(key=f'catalog:{v.principal.site_id}'))


def visible_equipment(v, identity, lock=False):
    if v.principal.role == 'executor' and identity not in v.visible_equipment_ids():
        raise HTTPException(404, 'Оборудование не найдено')
    return _equipment(v, identity, lock)


def component(v, identity, lock=False):
    rows = _lock(v, 'equipment_components', component_id=identity) if lock else v.rows('equipment_components', component_id=identity)
    if not rows: raise HTTPException(404, 'Деталь не найдена')
    visible_equipment(v, rows[0].equipment_id)
    return rows[0]


def component_response(v, row):
    readings = sorted(v.rows('component_usage_readings', component_id=row.component_id), key=lambda r: r.measured_at, reverse=True)
    latest = readings[0] if readings else None
    value = latest.usage_value if latest else row.initial_usage
    remaining = None if row.resource_limit is None else max(Decimal(0), row.resource_limit - value)
    result = {key: getattr(row, key) for key in ('component_id', 'equipment_id', 'position_code', 'name', 'part_number', 'serial_number',
        'installed_on', 'removed_on', 'removal_reason', 'usage_unit', 'resource_basis', 'revision')}
    result.update(initial_usage=f'{row.initial_usage:.3f}', resource_limit=f'{row.resource_limit:.3f}' if row.resource_limit is not None else None,
        current_usage=f'{value:.3f}', remaining_usage=f'{remaining:.3f}' if remaining is not None else None,
        resource_state='removed' if row.removed_on else 'unknown' if remaining is None else 'exhausted' if remaining == 0 else 'available',
        measured_at=latest.measured_at if latest else None,
        readings=[dict(reading_id=r.reading_id, measured_at=r.measured_at, usage_value=str(r.usage_value), note=r.note,
            recorded_at=r.recorded_at, recorded_by=r.recorded_by,
            photo_url=f'{PREFIX}/registry/readings/{r.reading_id}/photo' if r.photo_key else None) for r in readings])
    return result


def add_component(v, equipment_id, data):
    equipment = visible_equipment(v, equipment_id, True)
    if equipment.status == 'retired': raise HTTPException(409, 'Нельзя установить деталь на списанное оборудование')
    if data.installed_on > datetime.now(ZoneInfo(v.principal.timezone)).date(): raise HTTPException(422, 'Дата установки не может быть в будущем')
    if equipment.commissioned_on and data.installed_on < equipment.commissioned_on:
        raise HTTPException(422, 'Дата установки раньше ввода оборудования')
    if any(r.position_code == data.position_code and r.removed_on is None for r in v.rows('equipment_components', equipment_id=equipment_id)):
        raise HTTPException(409, 'На этой позиции уже установлена деталь; используйте замену')
    row = v.repo.add('equipment_components', site_id=v.principal.site_id, equipment_id=equipment_id,
        created_by=v.principal.user_id, **data.model_dump())
    _audit(v, 'equipment_components', row.component_id, 'install', data.model_dump(mode='json'))
    return row


def registry_payload(v):
    _guard(v, 'director', 'admin', 'chief_engineer', 'engineer', 'dispatcher')
    equipment = sorted(v.rows('equipment'), key=lambda r: (r.asset_code, str(r.equipment_id)))
    parts = v.rows('equipment_components')
    return dict(site_id=v.principal.site_id, site_name=v.principal.site_name, timezone=v.principal.timezone,
        systems=[dict(id=r.system_id, code=r.code, name=r.name, system_group=r.system_group, revision=r.revision, is_active=r.is_active)
            for r in sorted(v.rows('engineering_systems'), key=lambda r: (r.name, str(r.system_id)))],
        items=[dict(**equipment_response(row), services=service_configurations(v, row.equipment_id),
            components=[component_response(v, part) for part in parts if part.equipment_id == row.equipment_id]) for row in equipment])


def register_routes(app, views, storage, runtime_settings):
    @app.get(PREFIX + '/registry')
    def registry(response: Response, v=Depends(views)):
        response.headers['Cache-Control'] = 'private, no-store'
        return registry_payload(v)

    @app.patch(PREFIX + '/registry/systems/{system_id}')
    def classify(system_id: UUID, command: SystemEdit, v=Depends(views)):
        with _edit(v, roles=('chief_engineer', 'admin'), exact_roles=True):
            catalog_lock(v)
            rows = _lock(v, 'engineering_systems', system_id=system_id)
            if not rows: raise HTTPException(404, 'Система не найдена')
            row = rows[0]
            _revision(row, command.expected_revision)
            row.system_group = command.system_group
            row.revision += 1
            _audit(v, 'engineering_systems', row.system_id, 'classify', command.model_dump(mode='json'))
            return dict(id=row.system_id, system_group=row.system_group, revision=row.revision)

    @app.get('/api/v1/auth/sites')
    def sites(response: Response, v=Depends(views)):
        response.headers['Cache-Control'] = 'private, no-store'
        rows = v.session.execute(text('''SELECT s.site_id,s.name,s.address,s.timezone,m.role FROM sites s
            JOIN site_memberships m USING(site_id) WHERE m.user_id=:user AND m.is_active AND s.is_active ORDER BY s.name,s.site_id'''),
            dict(user=v.principal.user_id)).mappings().all()
        return [dict(r, role=SQL_ROLES[r['role']]) for r in rows if r['role'] in SQL_ROLES]

    @app.post('/api/v1/auth/site')
    def switch_site(command: SiteSelection, request: Request, response: Response, v=Depends(views)):
        with service_transaction(v.session):
            member = v.session.execute(text('''SELECT s.site_id,s.name,s.timezone,m.role,u.full_name,u.email FROM sites s
                JOIN site_memberships m USING(site_id) JOIN users u USING(user_id)
                WHERE m.user_id=:user AND s.site_id=:site AND m.is_active AND s.is_active AND u.is_active FOR SHARE OF s,m,u'''),
                dict(user=v.principal.user_id, site=command.site_id)).mappings().first()
            if not member or member['role'] not in SQL_ROLES: raise HTTPException(403, 'Нет доступа к зданию')
            token, csrf = create_session(v.session, v.principal.user_id, command.site_id)
            v.session.execute(text('DELETE FROM fixrate_sessions WHERE token_hash=:token'), dict(token=digest(request.cookies[COOKIE])))
            who = Principal(v.principal.user_id, command.site_id, SQL_ROLES[member['role']], member['full_name'], member['email'], member['name'], member['timezone'])
        response.set_cookie(COOKIE, token, httponly=True, samesite='lax', max_age=28800, secure=runtime_settings.cookie_secure, path='/')
        response.set_cookie('fixrate_csrf', csrf, httponly=False, samesite='lax', max_age=28800, secure=runtime_settings.cookie_secure, path='/')
        return dict(profile=who.profile(), csrfToken=csrf)

    @app.post(PREFIX + '/registry/buildings', status_code=201)
    def create_building(command: BuildingCreate, v=Depends(views)):
        with _edit(v, roles=('chief_engineer', 'admin'), exact_roles=True):
            row = v.repo.add('sites', **command.model_dump())
            v.repo.add('site_memberships', site_id=row.site_id, user_id=v.principal.user_id, role=v.principal.role)
            admins=[m.user_id for m in v.rows('site_memberships') if m.role=='admin' and m.is_active and m.user_id!=v.principal.user_id and v.one('users',user_id=m.user_id).is_active]
            for identity in admins:v.repo.add('site_memberships',site_id=row.site_id,user_id=identity,role='admin')
            _audit(v, 'sites', row.site_id, 'create', command.model_dump() | dict(administrator_ids=[str(identity) for identity in admins]))
            return dict(site_id=row.site_id, name=row.name, address=row.address, timezone=row.timezone, role=v.principal.role)

    @app.get(PREFIX + '/equipment/{equipment_id}/components')
    def components(equipment_id: UUID, v=Depends(views)):
        visible_equipment(v, equipment_id)
        return [component_response(v, row) for row in v.rows('equipment_components', equipment_id=equipment_id)]

    @app.post(PREFIX + '/equipment/{equipment_id}/components', status_code=201)
    def install(equipment_id: UUID, command: ComponentCreate, v=Depends(views)):
        with _edit(v, roles=('chief_engineer', 'admin'), exact_roles=True):
            catalog_lock(v)
            return component_response(v, add_component(v, equipment_id, command))

    @app.patch(PREFIX + '/registry/components/{component_id}')
    def edit_component(component_id: UUID, command: ComponentMetadata, v=Depends(views)):
        with _edit(v, roles=('chief_engineer','admin'), exact_roles=True):
            catalog_lock(v)
            part=component(v,component_id)
            visible_equipment(v,part.equipment_id,True)
            part=component(v,component_id,True)
            _revision(part,command.expected_revision)
            if part.removed_on:raise HTTPException(409,'Параметры снятой детали сохраняются в истории')
            for key,value in command.model_dump(exclude={'expected_revision'}).items():setattr(part,key,value)
            part.revision+=1
            _audit(v,'equipment_components',part.component_id,'update_resource',command.model_dump(mode='json'))
            return component_response(v,part)

    @app.post(PREFIX + '/registry/components/{component_id}/replace')
    def replace(component_id: UUID, command: ComponentReplacement, v=Depends(views)):
        with _edit(v, roles=('chief_engineer', 'admin'), exact_roles=True):
            catalog_lock(v)
            part = component(v, component_id)
            visible_equipment(v, part.equipment_id, True)
            part = component(v, component_id, True)
            _revision(part, command.expected_revision)
            readings = v.rows('component_usage_readings', component_id=component_id)
            last_date = max([part.installed_on] + [r.measured_at.astimezone(ZoneInfo(v.principal.timezone)).date() for r in readings])
            if part.removed_on: raise HTTPException(409, 'Деталь уже снята')
            if not last_date <= command.removed_on <= datetime.now(ZoneInfo(v.principal.timezone)).date():
                raise HTTPException(422, 'Дата снятия раньше установки/последнего показания или в будущем')
            if command.replacement and (command.replacement.installed_on != command.removed_on or command.replacement.position_code != part.position_code):
                raise HTTPException(422, 'Новая деталь должна занимать ту же позицию с даты замены')
            part.removed_on, part.removal_reason = command.removed_on, command.reason
            part.revision += 1
            v.session.flush()
            new = add_component(v, part.equipment_id, command.replacement) if command.replacement else None
            _audit(v, 'equipment_components', part.component_id, 'replace' if new else 'remove', command.model_dump(mode='json'))
            return dict(removed=component_response(v, part), installed=component_response(v, new) if new else None)

    @app.post(PREFIX + '/registry/components/{component_id}/readings', status_code=201)
    def record_reading(component_id: UUID, payload: str = Form(...), photo: UploadFile | None = File(default=None), v=Depends(views)):
        try: command = UsageReading.model_validate_json(payload)
        except ValidationError: raise HTTPException(422, 'Проверьте дату, ревизию, наработку и примечание') from None
        path = None
        try:
            with _edit(v, roles=('chief_engineer', 'admin', 'engineer', 'dispatcher', 'executor'), exact_roles=True):
                catalog_lock(v)
                part = component(v, component_id)
                visible_equipment(v, part.equipment_id, True)
                part = component(v, component_id, True)
                _revision(part, command.expected_revision)
                if part.removed_on: raise HTTPException(409, 'Нельзя добавить наработку снятой детали')
                readings = v.rows('component_usage_readings', component_id=component_id)
                latest = max(readings, key=lambda r: r.measured_at) if readings else None
                day = command.measured_at.astimezone(ZoneInfo(v.principal.timezone)).date()
                if command.measured_at > datetime.now(timezone.utc) or day < part.installed_on:
                    raise HTTPException(422, 'Показание должно быть между датой установки и текущим временем')
                if latest and command.measured_at <= latest.measured_at:
                    raise HTTPException(422, 'Новое показание должно быть позже предыдущего')
                if command.usage_value < (latest.usage_value if latest else part.initial_usage):
                    raise HTTPException(422, 'Наработка не может уменьшаться; замену детали оформляйте отдельно')
                identity = uuid4()
                values = dict(reading_id=identity, site_id=v.principal.site_id, component_id=component_id,
                    measured_at=command.measured_at, usage_value=command.usage_value, note=command.note, recorded_by=v.principal.user_id)
                if photo:
                    data = photo.file.read(MAX_BYTES + 1)
                    try: mime = validate_upload(data, photo.filename, photo.content_type)
                    except Exception: raise HTTPException(422, 'Недопустимое изображение') from None
                    key = f'{v.principal.site_id}/registry/{identity}'
                    path = safe_storage_path(Path(storage), key)
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(data)
                    values.update(photo_key=key, photo_mime=mime, photo_sha256=hashlib.sha256(data).hexdigest())
                v.repo.add('component_usage_readings', **values)
                part.revision += 1
                _audit(v, 'component_usage_readings', identity, 'record', command.model_dump(mode='json'))
                result = component_response(v, part)
            return result
        except BaseException:
            if path: path.unlink(missing_ok=True)
            raise

    @app.get(PREFIX + '/registry/readings/{reading_id}/photo')
    def reading_photo(reading_id: UUID, v=Depends(views)):
        row = v.one('component_usage_readings', reading_id=reading_id)
        component(v, row.component_id)
        if not row.photo_key: raise HTTPException(404, 'Фотография не приложена')
        path = safe_storage_path(Path(storage), row.photo_key)
        if not path.is_file(): raise HTTPException(404, 'Фотография отсутствует в хранилище')
        return FileResponse(path, media_type=row.photo_mime, headers={'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff'})
