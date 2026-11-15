"""Factual paged inventory report; no workbook dependency or model-created facts."""
import re
from fastapi import HTTPException
from .read_transport import read

def requested(question):
    return bool(not re.search(r'excel|xlsx|таблиц|файл|фото',question,re.I) and re.search(r'анализ|обзор|покажи',question,re.I) and re.search(r'оборудован',question,re.I) and re.search(r'объект|доступн|все|всё',question,re.I))

def label(value):return str(value).replace('\n',' ').replace('|','/').replace('`','')[:200]

async def report(app,tool,headers,trace,check):
    lines=[];site_offset=0;offset=0;calls=0;site_names=set()
    while calls<200:
        check();calls+=1
        try:
            _,data=await read(app,tool,dict(query=dict(site_offset=site_offset,offset=offset)),headers,trace)
        except HTTPException as exc:
            lines.append('Проверка не завершена: '+('нет доступа к данным.' if exc.status_code in (401,403) else 'backend недоступен или вернул ошибку. Это не означает, что объектов нет.'))
            break
        site=data.get('site')
        if site is None:
            if not lines:lines.append('Доступных зданий в текущей учётной записи не найдено.')
            break
        if offset==0:
            site_names.add(site['id']);lines.append('\n### '+label(site['name']))
        if site['status']=='access_denied':
            lines.append('Здание доступно, но ваша роль в нём не разрешает чтение реестра оборудования.')
        else:
            systems={str(s['id']):s['name'] for s in data.get('systems',[])}
            if data['total']==0:lines.append('Реестр оборудования пуст.')
            if offset==0:lines.append(f"Единиц оборудования: {data['total']}. Систем: {len(systems)}.")
            for item in data['items']:
                gaps='; '.join(item['planning_gaps']) or 'По проверенным полям конфигурации пробелов не выявлено'
                if item.get('data_origin')=='synthetic_demo':gaps+='; демонстрационные данные'
                lines.append(f"- **{label(item['name'])}** ({label(item['asset_code'])}), система «{label(systems.get(item['system_id'],'не указана'))}»: операций регламента — {item['operations']}, опубликовано — {item['published_operations']}; незавершённых заданий — {item['pending_tasks']}, из них на приёмке — {item.get('in_review_tasks',0)}. {label(gaps)}.")
            offset+=len(data['items'])
            if offset<data['total']:
                if not data['items']:lines.append('Чтение остановлено: страница пуста при ненулевом остатке.');break
                continue
        site_offset+=1;offset=0
        if site_offset>=data['site_total']:break
    else:lines.append('Достигнут предел чтения: список частичный, требуется сузить выборку.')
    return 'Проверено по данным системы. Число операций означает конфигурации обслуживания, а не пункты чек-листа.\n'+'\n'.join(lines)+'\n\nПроверка конфигурации не подтверждает выполнимость графика: для назначения отдельно проверяются смены, допуски и загрузка персонала.'
