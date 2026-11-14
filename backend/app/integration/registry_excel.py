"""Preview-first XLSX import; one locked transaction uses the normal catalog services."""
import hashlib
import hmac
import json
from uuid import UUID, uuid5, NAMESPACE_URL
from fastapi import Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import ValidationError
from sqlalchemy import text
from app.catalog_excel import MAX_FILE, read_workbook, table, write_workbook
from app.schemas.management import EquipmentCreate, EquipmentEdit, ServiceConfiguration
from app.schemas.registry import ComponentCreate, SystemCreate
from .management import PREFIX, _audit, _edit, _guard, save_equipment, save_service, service_configurations
from .registry import add_component, registry_payload

EQ = ['ID здания','Код системы','Система','Группа','Инвентарный номер','Название','Расположение','Дата ввода','Серийный номер','Состояние','Ревизия','Происхождение']
WORK = ['Инвентарный номер','Код работы','Работа','Вид ТО','Периодичность','Интервал','Опорная дата','Начало действия','Конец действия','Часы','Единица часов','Бригада','Длительность, мин','Инструкция','Пункты регламента','Источник методики','ID привязки','Ревизия','Календарь (JSON)','Настройка (JSON)']
PART = ['Инвентарный номер','Позиция','Деталь','Артикул','Серийный номер','Дата установки','Единица наработки','Начальная наработка','Норматив ресурса','Источник ресурса','ID детали','Текущая наработка','Дата снятия']
GROUPS = {'Электрика':'electricity','Вода':'water','Воздух':'air','electricity':'electricity','water':'water','air':'air'}
GROUP_LABELS = {'electricity':'Электрика','water':'Вода','air':'Воздух'}
UNITS = {'чел.-ч':'person_hour','ч':'elapsed_hour','не подтверждено':'unconfirmed','person_hour':'person_hour','elapsed_hour':'elapsed_hour','unconfirmed':'unconfirmed'}
FREQUENCIES = {'день':'day','неделя':'week','месяц':'month','квартал':'quarter','год':'year','раз в год':'yearly_count','даты':'dates'}


def service_values(asset, service):
    pattern = service['pattern'] or {}
    extra = {k: service[k] for k in ('basis','allowed_lead_days','qualification_ids','checklist','measurement_requirements','required_acts')}
    return [asset, service['code'], service['title'], service['maintenance_type'], pattern.get('frequency'), pattern.get('interval'), pattern.get('anchor_date'), service['valid_from'], service['valid_until'], service['norm_value'], service['norm_unit'], service['crew_size'], service['duration_minutes'], service['instructions'], '\n'.join(c['text'] for c in service['checklist']), service['methodology_ref'], service['binding_id'], service['revision'], json.dumps(pattern, ensure_ascii=False), json.dumps(extra, ensure_ascii=False, default=str)]


def workbook_export(v, template=False):
    data = registry_payload(v)
    eq, work, parts, readings = [EQ], [WORK], [PART], [['Инвентарный номер','ID детали','Дата показания','Наработка','Примечание','Автор','Дата записи']]
    if not template:
        for item in data['items']:
            system = next(s for s in data['systems'] if s['id'] == item['system_id'])
            eq.append([data['site_id'], system['code'], system['name'], GROUP_LABELS.get(system['system_group'], ''), item['asset_code'], item['name'], item['location'], item['commissioned_on'], item['serial_number'], item['status'], item['revision'], item['properties'].get('data_origin','customer')])
            for service in item['services']:
                work.append(service_values(item['asset_code'],service))
            for part in item['components']:
                parts.append([item['asset_code'],part['position_code'],part['name'],part['part_number'],part['serial_number'],part['installed_on'],part['usage_unit'],part['initial_usage'],part['resource_limit'],part['resource_basis'],part['component_id'],part['current_usage'],part['removed_on']])
                for reading in part['readings']:
                    readings.append([item['asset_code'],part['component_id'],reading['measured_at'],reading['usage_value'],reading['note'],reading['recorded_by'],reading['recorded_at']])
    guide = [['Правила заполнения'],['Даты: YYYY-MM-DD; числа без разделителей тысяч, десятичный разделитель — точка.'],
        ['Листы: Оборудование, Работы, Детали. Показания — выгрузка истории; новые показания вносятся на сайте с фото.'],
        ['Группа: Электрика / Вода / Воздух. Система определяется кодом в текущем здании.'],
        ['Для изменения существующего оборудования сохраняйте ревизию. Для новой строки оставьте её пустой.'],
        ['Вид ТО: ТО1 / ТО2 / ТО3. Единица часов: person_hour (чел.-ч), elapsed_hour (длительность), unconfirmed.'],
        ['Периодичность: день / неделя / месяц / квартал / год / раз в год. Для сложного календаря используйте выгруженный JSON.'],
        ['Инструкция и пункты регламента обязательны; каждый пункт с новой строки. Импортированные изменения регламентов сохраняются черновиками.'],
        ['Имеющиеся детали при импорте сверяются и не перезаписываются. Замену и показания оформляйте на сайте.'],
        ['Ресурс детали без источника не принимается. Снятые детали и история не удаляются.'],
        ['Шаблон предназначен для одного выбранного здания. Выгрузка не является резервной копией БД.']]
    return write_workbook({'Оборудование':eq,'Работы':work,'Детали':parts,'Показания':readings,'Инструкция':guide})


def fingerprint(v, content):
    state = {}
    for name, key in [('engineering_systems','system_id'),('equipment','equipment_id'),('rule_equipment','binding_id'),('equipment_components','component_id')]:
        state[name] = sorted((str(getattr(row,key)),row.revision) for row in v.rows(name))
    body = json.dumps(dict(site=str(v.principal.site_id), actor=str(v.principal.user_id), sha=hashlib.sha256(content).hexdigest(), state=state), sort_keys=True).encode()
    return hashlib.sha256(body).hexdigest()


def preview(v, content):
    sheets = read_workbook(content)
    token = fingerprint(v, content)
    result = dict(format='registry', preview_token=token, rows=[], errors=[], warnings=[], can_import=False)
    if hashlib.sha256(content).hexdigest() == '728f990873b506ca75fb91cd51eebc8cbe6efb9b230bb333338cd9c56c969da0':
        result.update(format='customer_schedule', warnings=['Исходный график 2027 года распознан. Единицы норм, привязки оборудования, состав бригад и часть дат требуют уточнения. Используйте шаблон реестра для сохранения подтверждённых данных.'])
        by_number = dict(sheets['Лист2'])
        for number, code, kind in [(6,'1.1','ТО1'),(7,'1.2','ТО1'),(8,'1.3','ТО1'),(11,'1.4','ТО2'),(12,'1.5','ТО2'),(13,'1.6','ТО2'),(14,'1.7','ТО3'),(15,'1.8','ТО3')]:
            cells = by_number[number]
            result['rows'].append(dict(sheet='Лист2',row=number,action='needs_confirmation',label=f"{code} · {kind} · норма {cells.get('E',{}).get('value','')} (единица не подтверждена)"))
        return result, []
    if 'Оборудование' not in sheets: raise ValueError('Не найден лист «Оборудование». Скачайте шаблон реестра.')
    system_rows = {r.code:r for r in v.rows('engineering_systems')}
    equipment = {r.asset_code:r for r in v.rows('equipment')}
    planned = {code:row.equipment_id for code,row in equipment.items()}
    system_ids = {code:row.system_id for code,row in system_rows.items()}
    systems, actions = {}, []
    seen_equipment, seen_work, seen_parts = set(), set(), set()

    def issue(sheet, number, error):
        if isinstance(error, ValidationError): detail = '; '.join('.'.join(map(str,e['loc']))+': '+e['msg'] for e in error.errors())
        else: detail = str(error)
        result['errors'].append(dict(sheet=sheet,row=number,message=detail))

    def action(sheet, number, kind, label, payload, changes=None):
        result['rows'].append(dict(sheet=sheet,row=number,action=kind,label=label,changes=changes or []))
        actions.append((sheet,kind,payload))

    for number, row in table(sheets['Оборудование']):
        try:
            code, asset = row.get('Код системы',''), row.get('Инвентарный номер','')
            if not code: raise ValueError('Укажите код системы')
            if row.get('ID здания') and row['ID здания'] != str(v.principal.site_id): raise ValueError('Строка относится к другому зданию')
            if asset in seen_equipment: raise ValueError('Повтор инвентарного номера в файле')
            seen_equipment.add(asset)
            group_text = row.get('Группа',''); group = GROUPS.get(group_text)
            if group_text and not group: raise ValueError('Неизвестная группа системы')
            if code in system_rows:
                if group != system_rows[code].system_group: raise ValueError('Группа существующей системы отличается. Сначала измените её на сайте.')
            else:
                system = SystemCreate(code=code, name=row.get('Система',''), system_group=group)
                if code in systems and system != systems[code]: raise ValueError('Для одного кода системы указаны разные параметры')
                systems[code] = system
                system_ids[code] = uuid5(NAMESPACE_URL, f'{v.principal.site_id}:registry:{code}')
            data = EquipmentCreate(system_id=system_ids[code], asset_code=asset, name=row.get('Название',''), location=row.get('Расположение') or None,
                commissioned_on=row.get('Дата ввода') or None, serial_number=row.get('Серийный номер') or None,
                status=row.get('Состояние') or 'active', data_origin=row.get('Происхождение') or 'customer')
            existing = equipment.get(asset)
            revision = int(row['Ревизия']) if row.get('Ревизия') else None
            if existing and revision != existing.revision: raise ValueError('Нужна актуальная ревизия существующего оборудования')
            if not existing and revision is not None: raise ValueError('Ревизия указана для несуществующего оборудования')
            planned[asset] = existing.equipment_id if existing else uuid5(NAMESPACE_URL, f'{v.principal.site_id}:equipment:{asset}')
            changes=[]
            if existing:
                labels={'system_id':'Система','name':'Название','location':'Расположение','commissioned_on':'Дата ввода','serial_number':'Серийный номер','status':'Состояние'}
                changes=[f'{label}: {getattr(existing,key) or "—"} → {getattr(data,key) or "—"}' for key,label in labels.items() if getattr(existing,key)!=getattr(data,key)]
                if data.data_origin!=existing.properties.get('data_origin','customer'):changes.append('Изменение происхождения данных')
                if not changes:
                    action('Оборудование',number,'unchanged',asset+' · '+data.name,None);continue
            action('Оборудование',number,'update' if existing else 'create',asset+' · '+data.name,dict(data=data,identity=existing.equipment_id if existing else None,revision=revision),changes)
        except (ValueError, ValidationError) as error: issue('Оборудование',number,error)

    for number, row in table(sheets.get('Работы',[])):
        try:
            asset, code = row.get('Инвентарный номер',''), row.get('Код работы','')
            if asset not in planned: raise ValueError('Оборудование не найдено в здании или на листе «Оборудование»')
            key = (asset,code)
            if key in seen_work: raise ValueError('Повтор работы для одного оборудования')
            seen_work.add(key)
            binding = UUID(row['ID привязки']) if row.get('ID привязки') else None
            current = None
            if binding:
                current = next((s for s in service_configurations(v,planned[asset]) if s['binding_id']==binding),None)
                if not current: raise ValueError('Привязка работы не найдена у оборудования')
                if int(row.get('Ревизия') or 0) != current['revision']: raise ValueError('Устаревшая ревизия регламента')
                expected = dict(zip(WORK, service_values(asset,current)))
                if all(row.get(k,'') == (str(value).strip() if value is not None else '') for k,value in expected.items()):
                    action('Работы',number,'unchanged',asset+' · '+code,None); continue
            pattern = json.loads(row['Календарь (JSON)']) if row.get('Календарь (JSON)') else dict(frequency=FREQUENCIES.get(row.get('Периодичность'),row.get('Периодичность')),interval=int(row.get('Интервал') or 1),anchor_date=row.get('Опорная дата'),weekend_policy='none')
            # Visible Excel columns take precedence over the advanced round-trip fields.
            if row.get('Периодичность'):pattern['frequency']=FREQUENCIES.get(row['Периодичность'],row['Периодичность'])
            if row.get('Интервал'):pattern['interval']=int(row['Интервал'])
            if row.get('Опорная дата'):pattern['anchor_date']=row['Опорная дата']
            extra = json.loads(row.get('Настройка (JSON)') or '{}')
            if not isinstance(extra,dict): raise ValueError('Настройка должна быть объектом JSON')
            allowed = {'basis','allowed_lead_days','qualification_ids','checklist','measurement_requirements','required_acts'}
            if set(extra)-allowed: raise ValueError('Недопустимые поля настройки')
            if 'checklist' in extra and 'Пункты регламента' in row:
                texts=[text.strip() for text in row['Пункты регламента'].splitlines() if text.strip()]
                original=extra['checklist']
                extra['checklist']=[dict(original[index],text=value) if index<len(original) else dict(text=value) for index,value in enumerate(texts)]
            data = ServiceConfiguration(**(dict(code=code,title=row.get('Работа',''),instructions=row.get('Инструкция',''),maintenance_type=row.get('Вид ТО'),pattern=pattern,
                valid_from=row.get('Начало действия'),valid_until=row.get('Конец действия') or None,crew_size=int(row.get('Бригада') or 0),norm_value=row.get('Часы') or None,
                norm_unit=UNITS.get(row.get('Единица часов'),row.get('Единица часов') or 'unconfirmed'),duration_minutes=int(row['Длительность, мин']) if row.get('Длительность, мин') else None,
                checklist=[dict(text=text.strip()) for text in row.get('Пункты регламента','').splitlines() if text.strip()],allowed_lead_days=0,
                enabled=False,methodology_ref=row.get('Источник методики') or None) | extra))
            if binding:
                data.expected_revision = current['revision']
                current_data = ServiceConfiguration.model_validate({k:current[k] for k in ServiceConfiguration.model_fields if k in current} | dict(enabled=False,expected_revision=current['revision']))
                if data.model_dump(exclude={'operation_id'}) == current_data.model_dump(exclude={'operation_id'}):
                    action('Работы',number,'unchanged',asset+' · '+code,None); continue
            unit_label={'person_hour':'чел.-ч','elapsed_hour':'ч длительности','unconfirmed':'(единица не подтверждена)'}[data.norm_unit]
            changes=[f'{data.maintenance_type} · норма {data.norm_value if data.norm_value is not None else "не указана"} {unit_label} · бригада {data.crew_size} · черновик']
            if current:
                for field,label in [('title','Название'),('norm_value','Норма'),('norm_unit','Единица'),('crew_size','Бригада'),('duration_minutes','Длительность'),('instructions','Инструкция'),('valid_from','Начало действия'),('valid_until','Конец действия')]:
                    before=current.get(field);after=getattr(data,field)
                    if str(before)!=str(after):changes.append(f'{label}: {before if before is not None else "—"} → {after if after is not None else "—"}')
            action('Работы',number,'update' if binding else 'create',asset+' · '+code+' · '+data.title,dict(asset=asset,data=data,binding=binding),changes)
        except (ValueError, ValidationError, TypeError, HTTPException) as error: issue('Работы',number,error.detail if isinstance(error,HTTPException) else error)

    for number, row in table(sheets.get('Детали',[])):
        try:
            asset = row.get('Инвентарный номер','')
            if asset not in planned: raise ValueError('Оборудование не найдено')
            data = ComponentCreate(position_code=row.get('Позиция',''),name=row.get('Деталь',''),part_number=row.get('Артикул') or None,serial_number=row.get('Серийный номер') or None,
                installed_on=row.get('Дата установки'),usage_unit=row.get('Единица наработки') or 'hour',initial_usage=row.get('Начальная наработка') or None,resource_limit=row.get('Норматив ресурса') or None,resource_basis=row.get('Источник ресурса') or None)
            if row.get('ID детали'):
                part = next((p for p in v.rows('equipment_components',equipment_id=planned[asset]) if str(p.component_id)==row['ID детали']),None)
                if not part or any(getattr(part,k)!=value for k,value in data.model_dump().items()): raise ValueError('Существующую деталь нельзя изменить через Excel; используйте замену на сайте')
                action('Детали',number,'unchanged',asset+' · '+data.name,None);continue
            key = (asset,data.position_code)
            if key in seen_parts: raise ValueError('Повтор позиции детали')
            seen_parts.add(key)
            if any(p.position_code==data.position_code and p.removed_on is None for p in v.rows('equipment_components',equipment_id=planned[asset])): raise ValueError('Позиция занята; оформите замену на сайте')
            action('Детали',number,'create',asset+' · '+data.name,dict(asset=asset,data=data))
        except (ValueError, ValidationError) as error: issue('Детали',number,error)
    if any(sheet=='Работы' and kind!='unchanged' for sheet,kind,_ in actions): result['warnings'].append('Новые и изменённые регламенты будут сохранены как черновики. Публикация выполняется отдельно главным инженером.')
    result['can_import'] = bool(actions) and not result['errors']
    return result, (systems, actions)


def register_routes(app, views):
    @app.get(PREFIX+'/registry/excel')
    def export(template:bool=False, v=Depends(views)):
        content = workbook_export(v, template)
        return Response(content,media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',headers={'Content-Disposition':'attachment; filename="fixrate-registry.xlsx"','Cache-Control':'private, no-store'})

    @app.post(PREFIX+'/registry/excel/preview')
    def inspect(file:UploadFile=File(...),v=Depends(views)):
        _guard(v,'chief_engineer','admin')
        try: result,_=preview(v,file.file.read(MAX_FILE+1))
        except ValueError as error: raise HTTPException(422,str(error)) from None
        return result

    @app.post(PREFIX+'/registry/excel/import')
    def apply(preview_token:str=Form(...),file:UploadFile=File(...),v=Depends(views)):
        content=file.file.read(MAX_FILE+1)
        with _edit(v,roles=('chief_engineer','admin'),exact_roles=True):
            v.session.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:key,0))'),dict(key=f'catalog:{v.principal.site_id}'))
            try: result,plan=preview(v,content)
            except ValueError as error: raise HTTPException(422,str(error)) from None
            if not hmac.compare_digest(preview_token,result['preview_token']): raise HTTPException(409,'Данные изменились после предпросмотра. Проверьте файл заново.')
            if not result['can_import']: raise HTTPException(422,'Исправьте ошибки предпросмотра перед импортом')
            systems,actions=plan
            for code,data in systems.items():
                identity=uuid5(NAMESPACE_URL,f'{v.principal.site_id}:registry:{code}')
                row=v.repo.add('engineering_systems',site_id=v.principal.site_id,system_id=identity,**data.model_dump())
                _audit(v,'engineering_systems',row.system_id,'create',data.model_dump())
            for sheet,kind,payload in actions:
                if sheet!='Оборудование' or kind=='unchanged':continue
                data=payload['data']
                if payload['identity']:
                    data=EquipmentEdit(**data.model_dump(exclude={'equipment_type_id','parent_equipment_id','properties'}),expected_revision=payload['revision'])
                save_equipment(v,data,payload['identity'],_locked=True)
            by_asset={e.asset_code:e for e in v.rows('equipment')}
            for sheet,kind,payload in actions:
                if kind=='unchanged' or sheet=='Оборудование':continue
                equipment=by_asset[payload['asset']]
                if sheet=='Работы':
                    data=payload['data']
                    if not payload['binding']:
                        operation=next((o for o in v.rows('operation_templates',system_id=equipment.system_id) if o.code==data.code),None)
                        if operation:data.operation_id=operation.operation_template_id
                    save_service(v,equipment.equipment_id,data,payload['binding'],_locked=True)
                else:add_component(v,equipment.equipment_id,payload['data'])
            _audit(v,'registry_import',uuid5(NAMESPACE_URL,hashlib.sha256(content).hexdigest()),'import',dict(sha256=hashlib.sha256(content).hexdigest(),rows=len(actions)))
            return dict(imported=sum(kind!='unchanged' for _,kind,_ in actions),unchanged=sum(kind=='unchanged' for _,kind,_ in actions))
